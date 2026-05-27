"""Layer 4 — per-PT σ calibration via grid search.

Implements V1_Engineering_Spec §5.3 + §7.2 M4 (calibration step only).

For each ProductType present in the validation split, sweeps a grid of
candidate σ values and picks the one that minimizes:

    val_loss(σ) = Brier(conf_embed_final, is_correct)
                + λ_cal · ECE(conf_embed_final, is_correct, n_bins=10)

**Calibration target.** We calibrate the *predictive quality of
``conf_embed_final``* directly — `conf_rule` is held at 0 for
calibration samples because σ has no effect on the rule signal. After
calibration, the fused `conf_final = 0.7 · conf_rule + 0.3 ·
conf_embed_final` inherits whatever calibration we achieved here, plus
the deterministic rule signal.

**Performance trick (per the user's M4 brief).** ``D²(q, μ)`` does not
depend on σ. We compute d² once per (val_query, cluster) pair, cache
it, and replay ``conf_embed = exp(-d² / 2σ²)`` for each candidate σ.
On a typical grid of 8 candidates this is ~10× cheaper than re-scoring
from scratch.

Output: :class:`SigmaTable`, persisted to ``sigma_table.parquet`` in
the active run directory.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from ..config import CalibrationConfig
from ..layer3_semantic.clusters import ClusterStats, ClusterStore
from ..layer3_semantic.scoring import UsagePrior


# ---------------------------------------------------------------------------
# Input + output records
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ValQuery:
    """One validation sample for σ calibration.

    Args:
        pt_id: True ProductType ID for this product.
        product_id: For traceability / debugging.
        query_vector: ``(D,)`` float32 L2-normalized embedding.
        attribute_name: The 1A attribute being calibrated against.
        true_value: The 1A ``Attribute_Value`` for this row — what
            top-1 must match for the prediction to count as correct.
    """

    pt_id: int
    product_id: int
    query_vector: np.ndarray
    attribute_name: str
    true_value: str


@dataclass(frozen=True, slots=True)
class SigmaEntry:
    """One row of the σ calibration table."""

    pt_id: int
    pt_name: str
    sigma_optimal: float
    brier_at_opt: float
    ece_at_opt: float
    loss_at_opt: float          # = brier + lambda_cal · ece
    n_val_samples: int
    n_clusters_used: int


class SigmaTable:
    """Indexed collection of :class:`SigmaEntry` with O(1) lookup."""

    PARQUET_NAME = "sigma_table.parquet"

    def __init__(self, entries: Sequence[SigmaEntry]) -> None:
        self._entries: tuple[SigmaEntry, ...] = tuple(entries)
        self._by_pt: dict[int, SigmaEntry] = {e.pt_id: e for e in entries}

    # ---- public surface ------------------------------------------------

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> tuple[SigmaEntry, ...]:
        return self._entries

    def sigma_for(self, pt_id: int, default: float = 1.0) -> float:
        """Return calibrated σ for ``pt_id`` or ``default`` if not present."""
        entry = self._by_pt.get(int(pt_id))
        return float(entry.sigma_optimal) if entry is not None else default

    def as_sigma_by_pt(self) -> dict[int, float]:
        """Return a ``{pt_id: σ}`` mapping for ``SemanticScorer.set_sigma_by_pt``."""
        return {e.pt_id: float(e.sigma_optimal) for e in self._entries}

    # ---- persistence ---------------------------------------------------

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(
            [
                {
                    "pt_id": e.pt_id,
                    "pt_name": e.pt_name,
                    "sigma_optimal": e.sigma_optimal,
                    "brier_at_opt": e.brier_at_opt,
                    "ece_at_opt": e.ece_at_opt,
                    "loss_at_opt": e.loss_at_opt,
                    "n_val_samples": e.n_val_samples,
                    "n_clusters_used": e.n_clusters_used,
                }
                for e in self._entries
            ]
        )
        df.to_parquet(directory / self.PARQUET_NAME, index=False)

    @classmethod
    def load(cls, directory: Path) -> SigmaTable:
        df = pd.read_parquet(directory / cls.PARQUET_NAME)
        entries = [
            SigmaEntry(
                pt_id=int(row.pt_id),
                pt_name=str(row.pt_name),
                sigma_optimal=float(row.sigma_optimal),
                brier_at_opt=float(row.brier_at_opt),
                ece_at_opt=float(row.ece_at_opt),
                loss_at_opt=float(row.loss_at_opt),
                n_val_samples=int(row.n_val_samples),
                n_clusters_used=int(row.n_clusters_used),
            )
            for row in df.itertuples()
        ]
        return cls(entries)


# ---------------------------------------------------------------------------
# Calibration loss components
# ---------------------------------------------------------------------------


def brier_score(probs: Sequence[float], outcomes: Sequence[int]) -> float:
    """Mean squared error between predicted probability and binary outcome.

    Range: ``[0, 1]``. Lower is better. Returns 0.0 for empty input.
    """
    if not probs:
        return 0.0
    arr = np.asarray(probs, dtype=np.float64)
    out = np.asarray(outcomes, dtype=np.float64)
    return float(np.mean((arr - out) ** 2))


def expected_calibration_error(
    probs: Sequence[float],
    outcomes: Sequence[int],
    n_bins: int = 10,
) -> float:
    """Expected Calibration Error via equal-width binning.

    For each bin compute ``|mean(conf) - mean(accuracy)|`` and average
    over bins weighted by bin size. Range ``[0, 1]``. Returns 0.0 for
    empty input.
    """
    if not probs:
        return 0.0
    arr = np.asarray(probs, dtype=np.float64)
    out = np.asarray(outcomes, dtype=np.float64)
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    # np.digitize with right=False puts bin_edges[i] into bin i; clamp.
    bin_idx = np.clip(np.digitize(arr, bin_edges, right=False) - 1, 0, n_bins - 1)
    total = len(arr)
    ece = 0.0
    for b in range(n_bins):
        mask = bin_idx == b
        if not mask.any():
            continue
        bin_conf = float(arr[mask].mean())
        bin_acc = float(out[mask].mean())
        ece += float(mask.sum()) / total * abs(bin_conf - bin_acc)
    return float(ece)


# ---------------------------------------------------------------------------
# Calibrator
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _CachedSample:
    """Cached d² values for one val query against all clusters under (pt, attr)."""

    val_idx: int
    attribute_name: str
    true_value: str
    cluster_values: tuple[str, ...]                  # candidate value names, aligned
    cluster_d2: np.ndarray                            # (n_clusters,) float32
    cluster_low_sample: np.ndarray                    # (n_clusters,) bool
    usage_priors: np.ndarray                          # (n_clusters,) float32 — fixed across σ


class SigmaCalibrator:
    """Per-PT σ grid-search calibrator with cached d²."""

    def __init__(
        self,
        cluster_store: ClusterStore,
        usage_prior: UsagePrior,
        config: CalibrationConfig,
    ) -> None:
        self._store = cluster_store
        self._usage = usage_prior
        self._config = config
        self._sigma_grid: tuple[float, ...] = tuple(config.sigma_grid)

    # ---- public ---------------------------------------------------------

    def fit(self, val_queries: Iterable[ValQuery]) -> SigmaTable:
        """Run the per-PT σ grid search and return a :class:`SigmaTable`."""
        # 1) Group val queries by ProductType.
        by_pt: dict[int, list[ValQuery]] = {}
        for vq in val_queries:
            by_pt.setdefault(int(vq.pt_id), []).append(vq)

        entries: list[SigmaEntry] = []
        for pt_id, samples in by_pt.items():
            entry = self._fit_one_pt(pt_id, samples)
            if entry is not None:
                entries.append(entry)
        return SigmaTable(entries)

    # ---- per-PT ---------------------------------------------------------

    def _fit_one_pt(self, pt_id: int, samples: list[ValQuery]) -> SigmaEntry | None:
        cached, pt_name, clusters_used = self._cache_d2_for_pt(pt_id, samples)
        if not cached:
            return None

        best_sigma = self._sigma_grid[0]
        best_loss = math.inf
        best_brier = math.inf
        best_ece = math.inf
        for sigma in self._sigma_grid:
            brier, ece = self._score_at_sigma(cached, sigma)
            loss = brier + self._config.lambda_cal * ece
            if loss < best_loss:
                best_loss = loss
                best_sigma = sigma
                best_brier = brier
                best_ece = ece

        return SigmaEntry(
            pt_id=pt_id,
            pt_name=pt_name,
            sigma_optimal=float(best_sigma),
            brier_at_opt=float(best_brier),
            ece_at_opt=float(best_ece),
            loss_at_opt=float(best_loss),
            n_val_samples=len(cached),
            n_clusters_used=clusters_used,
        )

    def _cache_d2_for_pt(
        self, pt_id: int, samples: list[ValQuery]
    ) -> tuple[list[_CachedSample], str, int]:
        attributes_under_pt = self._store.attributes_for_pt(pt_id)
        pt_name = self._pt_name_for(pt_id)
        cached: list[_CachedSample] = []
        unique_clusters: set[int] = set()
        for idx, vq in enumerate(samples):
            if vq.attribute_name not in attributes_under_pt:
                # Spec §2.3 / §4.3 [3d]: attribute may exist in 1A but have
                # no cluster under this PT (e.g. all rows were filtered out
                # of train). Skip; M3c would emit no hit anyway.
                continue
            clusters = self._store.values_for_pt_attribute(pt_id, vq.attribute_name)
            if not clusters:
                continue
            d2_arr = np.empty(len(clusters), dtype=np.float32)
            low_arr = np.empty(len(clusters), dtype=bool)
            prior_arr = np.empty(len(clusters), dtype=np.float32)
            values_list: list[str] = []
            for j, c in enumerate(clusters):
                d2_arr[j] = c.mahalanobis_squared(vq.query_vector)
                low_arr[j] = bool(c.low_sample)
                prior_arr[j] = self._usage.prior(vq.attribute_name, c.value)
                values_list.append(c.value)
                unique_clusters.add(c.cluster_id)
            cached.append(
                _CachedSample(
                    val_idx=idx,
                    attribute_name=vq.attribute_name,
                    true_value=vq.true_value,
                    cluster_values=tuple(values_list),
                    cluster_d2=d2_arr,
                    cluster_low_sample=low_arr,
                    usage_priors=prior_arr,
                )
            )
        return cached, pt_name, len(unique_clusters)

    def _score_at_sigma(
        self, cached: list[_CachedSample], sigma: float
    ) -> tuple[float, float]:
        """Replay cached d² under one σ → (brier, ece)."""
        two_sigma_sq_inv = 1.0 / (2.0 * sigma * sigma)
        probs: list[float] = []
        outcomes: list[int] = []
        for sample in cached:
            # Vectorized exp + prior.
            conf_embed = np.exp(-sample.cluster_d2 * two_sigma_sq_inv)
            conf_embed_final = conf_embed * sample.usage_priors
            top_idx = int(np.argmax(conf_embed_final))
            top_conf = float(min(1.0, max(0.0, conf_embed_final[top_idx])))
            top_value = sample.cluster_values[top_idx]
            is_correct = 1 if self._values_equal(top_value, sample.true_value) else 0
            probs.append(top_conf)
            outcomes.append(is_correct)
        return (
            brier_score(probs, outcomes),
            expected_calibration_error(probs, outcomes, n_bins=self._config.reliability_bins),
        )

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def _values_equal(a: str, b: str) -> bool:
        """Match the same normalization used by 2A guardrail / cluster store."""
        return " ".join(a.strip().lower().split()) == " ".join(b.strip().lower().split())

    def _pt_name_for(self, pt_id: int) -> str:
        for s in self._store.stats:
            if s.product_type_id == pt_id:
                return s.product_type_name
        return ""
