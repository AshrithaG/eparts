"""Layer 3 [3d] — Per-attribute per-value semantic scoring.

Implements V1_Engineering_Spec §4.3 [3d].

Given:
    * a query embedding q (from the encoder)
    * a :class:`ProductTypePrediction` (from PT consensus)
    * a :class:`ClusterStore` (per-cluster μ, Σ⁻¹ from M3b)
    * a :class:`UsagePrior` (2A Usage_Count statistics)
    * per-PT σ values (placeholder σ=1.0 until M4 calibrates)

…produce a :class:`SemanticMatcherResult` containing the top-3 candidate
values per applicable attribute, each with calibrated confidence.

Math (FROZEN — spec §6.1):

    D²(q, v)               = (q − μ)ᵀ · Σ⁻¹ · (q − μ)
    conf_embed(A, v)       = exp(−D² / (2 · σ_PT²))
    usage_prior(A, v)      = 0.5 + 0.5 · log(1 + UC(A, v)) / log(1 + max UC(A))
    conf_embed_final(A, v) = conf_embed(A, v) · usage_prior(A, v)

Low-sample clusters (no Σ⁻¹ stored) score via squared Euclidean as a
fallback — see :class:`ClusterStats.mahalanobis_squared`. Their
``low_sample=True`` flag propagates through :class:`SemanticCandidate`
so Layer 4 can apply the spec's hard confidence cap (default 0.7).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

from ..contracts import (
    ProductTypePrediction,
    SemanticCandidate,
    SemanticHit,
    SemanticMatcherResult,
)
from .clusters import ClusterStats, ClusterStore


# ---------------------------------------------------------------------------
# UsagePrior — 2A.Usage_Count → log prior in [0.5, 1.0]
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UsagePrior:
    """Frequency-weighted prior over ``(Attribute_Name, Value)`` pairs.

    Implements the formula in V1_Engineering_Spec §4.3 [3d]:

        usage_prior(A, v) = 0.5 + 0.5 · log(1 + UC(A, v)) / log(1 + max UC(A))

    The function is monotone in ``Usage_Count``, bounded in ``[0.5, 1.0]``,
    and equals 0.5 exactly when ``UC(A, v) = 0``. Per-attribute
    normalization (using ``max UC`` within that attribute) means a value
    with ``UC = 100`` under a long-tail attribute is treated similarly to
    one with ``UC = 10,000`` under a heavily-used attribute.

    Lookup keys are case-folded and whitespace-collapsed to tolerate
    upstream casing variations.
    """

    counts: Mapping[tuple[str, str], int]
    max_counts: Mapping[str, int]                # by attribute_name (normalized)

    # ---- public API ----------------------------------------------------

    def count(self, attribute_name: str, value: str) -> int:
        """Raw ``Usage_Count`` for an ``(A, v)`` pair. 0 when unknown."""
        return int(self.counts.get((self._norm(attribute_name), self._norm(value)), 0))

    def max_count(self, attribute_name: str) -> int:
        """Maximum ``Usage_Count`` observed under ``attribute_name``."""
        return int(self.max_counts.get(self._norm(attribute_name), 0))

    def prior(self, attribute_name: str, value: str) -> float:
        """Return the prior ``∈ [0.5, 1.0]`` for ``(A, v)``.

        If ``attribute_name`` is unknown or its max usage count is 0
        (e.g. only zero-count rows in 2A), returns 0.5 — the neutral
        midpoint.
        """
        attr_norm = self._norm(attribute_name)
        max_uc = int(self.max_counts.get(attr_norm, 0))
        if max_uc <= 0:
            return 0.5
        uc = int(self.counts.get((attr_norm, self._norm(value)), 0))
        return 0.5 + 0.5 * math.log1p(uc) / math.log1p(max_uc)

    # ---- internal ------------------------------------------------------

    @staticmethod
    def _norm(s: str) -> str:
        return " ".join(str(s or "").strip().lower().split())


def build_usage_prior_from_2a(values_df: pd.DataFrame | None = None) -> UsagePrior:
    """Build a :class:`UsagePrior` from ``2A_Values_Per_Attribute``.

    Args:
        values_df: Pre-loaded 2A DataFrame. When ``None`` loads via
            :func:`src.data.load_values_per_attribute`.

    Required columns: ``Attribute_Name``, ``Value``, ``Usage_Count``.
    Rows with null in any of those columns are dropped silently.
    """
    if values_df is None:
        from ..data import load_values_per_attribute
        values_df = load_values_per_attribute()

    required = {"Attribute_Name", "Value", "Usage_Count"}
    missing = required - set(values_df.columns)
    if missing:
        raise ValueError(f"2A frame is missing required columns: {missing}")

    df = values_df[["Attribute_Name", "Value", "Usage_Count"]].dropna()
    counts: dict[tuple[str, str], int] = {}
    max_counts: dict[str, int] = {}
    for attr, val, uc in zip(df["Attribute_Name"], df["Value"], df["Usage_Count"], strict=False):
        attr_n = UsagePrior._norm(str(attr))
        val_n = UsagePrior._norm(str(val))
        n = int(uc)
        counts[(attr_n, val_n)] = n
        if n > max_counts.get(attr_n, 0):
            max_counts[attr_n] = n
    return UsagePrior(counts=counts, max_counts=max_counts)


# ---------------------------------------------------------------------------
# SemanticScorer — top-3 per attribute under a predicted ProductType
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SemanticScorerConfig:
    """Tunable knobs for the scorer (mirrors config/thresholds.yaml + calibration)."""

    top_n_per_attribute: int = 3                  # spec §4.3 [3d] "top 3 values per attribute"
    default_sigma: float = 1.0                    # placeholder until M4 calibrates per-PT
    min_cluster_size: int = 5                     # mirrors config/thresholds.yaml clusters.min_size


class SemanticScorer:
    """Score every attribute under a predicted ProductType.

    The scorer is stateless aside from its dependencies — safe to share
    across queries. Per-PT σ values (calibrated in M4) are passed in
    via :meth:`set_sigma_by_pt` and default to ``config.default_sigma``
    when missing.
    """

    def __init__(
        self,
        cluster_store: ClusterStore,
        usage_prior: UsagePrior,
        config: SemanticScorerConfig | None = None,
        sigma_by_pt: Mapping[int, float] | None = None,
    ) -> None:
        self._store = cluster_store
        self._usage = usage_prior
        self._config = config or SemanticScorerConfig()
        self._sigma_by_pt: dict[int, float] = dict(sigma_by_pt or {})

    # ---- σ injection (M4 will populate this) --------------------------

    def set_sigma_by_pt(self, sigma_by_pt: Mapping[int, float]) -> None:
        """Override per-PT σ values. Missing PTs fall back to default σ."""
        self._sigma_by_pt = dict(sigma_by_pt)

    def sigma_for(self, product_type_id: int) -> float:
        return float(self._sigma_by_pt.get(int(product_type_id), self._config.default_sigma))

    # ---- public scoring API -------------------------------------------

    def score(
        self,
        query_vector: np.ndarray,
        pt_prediction: ProductTypePrediction,
    ) -> SemanticMatcherResult:
        """Return top-N candidate values for every applicable attribute.

        Args:
            query_vector: ``(D,)`` float32 L2-normalized embedding.
            pt_prediction: Output of :func:`compute_pt_consensus`.

        Returns:
            :class:`SemanticMatcherResult` with one :class:`SemanticHit` per
            attribute that has at least one cluster under
            ``pt_prediction.product_type_id``.
        """
        pt_id = int(pt_prediction.product_type_id)
        sigma = self.sigma_for(pt_id)
        # Pre-compute 1/(2σ²) once per query.
        two_sigma_sq_inv = 1.0 / (2.0 * sigma * sigma)
        attributes = sorted(self._store.attributes_for_pt(pt_id))

        hits: list[SemanticHit] = []
        for attribute_name in attributes:
            clusters = self._store.values_for_pt_attribute(pt_id, attribute_name)
            if not clusters:
                continue
            candidates = [
                self._score_one_cluster(query_vector, c, attribute_name, two_sigma_sq_inv)
                for c in clusters
            ]
            candidates.sort(key=lambda c: c.conf_embed_final, reverse=True)
            top = tuple(candidates[: self._config.top_n_per_attribute])
            if not top:
                continue
            hits.append(
                SemanticHit(
                    attribute_id=None,                # 2A has no Attribute_ID exposed here yet
                    attribute_name=attribute_name,
                    top_candidates=top,
                )
            )

        return SemanticMatcherResult(
            product_type=pt_prediction,
            hits=tuple(hits),
        )

    # ---- per-cluster scoring -----------------------------------------

    def _score_one_cluster(
        self,
        q: np.ndarray,
        cluster: ClusterStats,
        attribute_name: str,
        two_sigma_sq_inv: float,
    ) -> SemanticCandidate:
        d2 = cluster.mahalanobis_squared(q)
        # Mahalanobis squared is non-negative for any PSD Sigma_inv;
        # for low-sample clusters with implicit identity Σ⁻¹ it's
        # squared Euclidean. Floor at 0 defensively in case of
        # roundoff from a borderline-PSD inverse that slipped past
        # the build-time check.
        d2 = max(0.0, d2)
        conf_embed = math.exp(-d2 * two_sigma_sq_inv)
        # Clamp to [0, 1] — exp can produce values > 1 only if d² were
        # negative, which we floored above; this is belt-and-suspenders.
        if conf_embed > 1.0:
            conf_embed = 1.0

        prior = self._usage.prior(attribute_name, cluster.value)
        conf_embed_final = conf_embed * prior
        usage = self._usage.count(attribute_name, cluster.value)

        return SemanticCandidate(
            value=cluster.value,
            conf_embed=float(conf_embed),
            conf_embed_final=float(conf_embed_final),
            cluster_n=int(cluster.n),
            mahalanobis_d2=float(d2),
            usage_count=int(usage),
            low_sample=bool(cluster.low_sample),
        )
