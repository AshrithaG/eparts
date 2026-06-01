"""Layer 3 [3d] — Per-cluster centroid + covariance statistics.

Implements V1_Engineering_Spec §4.3 [3d] + §5.2 reference index build.

For each ``(ProductType_ID, Attribute_Name, Attribute_Value)`` triple that
appears in the 1A training split, we compute:

    μ_cluster  = (1 / N) Σᵢ q_i                       # mean embedding
    Σ_cluster  = Ledoit-Wolf shrinkage on q_i − μ      # shrunk covariance
    Σ_inv      = Σ⁻¹                                   # precomputed for Mahalanobis

Clusters with fewer than ``min_size`` members are flagged ``low_sample``
and skip the Σ computation entirely (Layer 4 hard-caps their conf_final
at 0.7 anyway — see ``config/thresholds.yaml``). Storing only μ for the
low-sample clusters keeps the on-disk artifact small.

Persistence layout (under ``artifacts/v1/run_<ts>/``):
    centroids.parquet      cluster metadata + μ vectors (small, queryable)
    cluster_cov.npz        Σ⁻¹ matrices for non-low-sample clusters only
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Mapping

import numpy as np
import pandas as pd

# Acceptance bounds for Σ⁻¹ eigenvalues on a healthy cluster.
#
# Healthy Ledoit-Wolf inverses on L2-normalized 384-d embeddings have
# eigenvalues in the rough range [1, 1000]. Anomalies come in two flavors:
#
#   * min eigenvalue <= 0  (or close)  →  near-singular Σ; np.linalg.inv()
#     produced a matrix with negative-eigenvalue noise. Empirically
#     observed as min_eig ≈ -3.4e+13 on M3b cluster 6350 (NEMA 3R /
#     WIDTH / 32.00 IN., 12 nearly-identical descriptions).
#
#   * max |eigenvalue| huge (e.g. 1e15+)  →  also near-singular but the
#     numerical noise lands in the positive direction instead. Same
#     underlying cause; observed when training fixtures use sub-1e-8
#     jitter on a shared base vector.
#
# Either failure makes the cluster unusable. We demote to ``low_sample``
# so Layer 4's confidence cap (config/thresholds.yaml clusters.
# low_sample_conf_cap) applies.
_PSD_EIG_MIN = 1e-8         # min eigenvalue floor for a healthy Σ⁻¹
_PSD_EIG_MAX_ABS = 1e10     # max abs eigenvalue ceiling for a healthy Σ⁻¹


@dataclass(frozen=True, slots=True)
class ClusterStats:
    """One ``(ProductType, Attribute, Value)`` cluster.

    Fields are immutable; the online μ update in M6 produces a *new*
    :class:`ClusterStats` rather than mutating in place.
    """

    cluster_id: int
    product_type_id: int
    product_type_name: str
    attribute_name: str
    value: str
    n: int                              # cluster size
    mu: np.ndarray                      # shape (D,) float32
    sigma_inv: np.ndarray | None        # shape (D, D) float32, or None for low-sample
    log_det_sigma: float                # 0.0 for low-sample clusters
    low_sample: bool

    def mahalanobis_squared(self, q: np.ndarray) -> float:
        """Return ``(q - μ)ᵀ Σ⁻¹ (q - μ)``.

        For low-sample clusters Σ⁻¹ is implicit identity, so this reduces
        to the squared Euclidean distance ``||q - μ||²`` (which on
        L2-normalized vectors is ``2 - 2 cos(q, μ)``).
        """
        diff = (q - self.mu).astype(np.float32, copy=False)
        if self.sigma_inv is None:
            return float(diff @ diff)
        return float(diff @ self.sigma_inv @ diff)


class ClusterStore:
    """Indexed collection of :class:`ClusterStats` with O(1) lookup."""

    def __init__(self, stats: list[ClusterStats]) -> None:
        self._stats: tuple[ClusterStats, ...] = tuple(stats)
        self._by_key: dict[tuple[int, str, str], ClusterStats] = {
            (s.product_type_id, s.attribute_name, s.value): s for s in stats
        }
        self._attrs_by_pt: dict[int, set[str]] = {}
        # (pt_id, attribute_name) → ordered list of clusters. Built once so
        # values_for_pt_attribute() is an O(1) dict hit instead of an
        # O(total-clusters) linear scan (the dominant Layer-3 score() cost
        # before this index existed — see M7 score-phase profiling).
        self._by_pt_attr: dict[tuple[int, str], list[ClusterStats]] = {}
        for s in stats:
            self._attrs_by_pt.setdefault(s.product_type_id, set()).add(s.attribute_name)
            self._by_pt_attr.setdefault(
                (s.product_type_id, s.attribute_name), []
            ).append(s)

    def __len__(self) -> int:
        return len(self._stats)

    @property
    def stats(self) -> tuple[ClusterStats, ...]:
        return self._stats

    @property
    def n_low_sample(self) -> int:
        return sum(1 for s in self._stats if s.low_sample)

    def lookup(
        self, product_type_id: int, attribute_name: str, value: str
    ) -> ClusterStats | None:
        return self._by_key.get((int(product_type_id), str(attribute_name), str(value)))

    def attributes_for_pt(self, product_type_id: int) -> frozenset[str]:
        """Return the set of attribute names that have any cluster under this PT."""
        return frozenset(self._attrs_by_pt.get(int(product_type_id), set()))

    def values_for_pt_attribute(
        self, product_type_id: int, attribute_name: str
    ) -> tuple[ClusterStats, ...]:
        """Return all :class:`ClusterStats` for one (PT, Attribute) pair.

        O(1) dict lookup via the ``(pt_id, attribute_name)`` index built at
        construction. Order matches insertion order of ``stats`` (stable).
        """
        return tuple(self._by_pt_attr.get((int(product_type_id), attribute_name), ()))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, directory: Path) -> None:
        """Persist as ``centroids.parquet`` + ``cluster_cov.npz``.

        Args:
            directory: Output directory. Created if missing. Existing
                files at the same paths are overwritten.
        """
        directory.mkdir(parents=True, exist_ok=True)

        rows = []
        for s in self._stats:
            rows.append(
                {
                    "cluster_id": s.cluster_id,
                    "product_type_id": s.product_type_id,
                    "product_type_name": s.product_type_name,
                    "attribute_name": s.attribute_name,
                    "value": s.value,
                    "n": s.n,
                    "low_sample": s.low_sample,
                    "log_det_sigma": s.log_det_sigma,
                    "mu": s.mu.astype(np.float32).tolist(),
                }
            )
        df = pd.DataFrame(rows)
        df.to_parquet(directory / "centroids.parquet", index=False)

        # Sigma_inv goes to npz keyed by cluster_id (skip low-sample).
        sigma_dict = {
            f"c{s.cluster_id}": s.sigma_inv
            for s in self._stats
            if s.sigma_inv is not None
        }
        np.savez_compressed(directory / "cluster_cov.npz", **sigma_dict)

    @classmethod
    def load(cls, directory: Path) -> ClusterStore:
        """Rehydrate a previously-saved :class:`ClusterStore`."""
        df = pd.read_parquet(directory / "centroids.parquet")
        cov = np.load(directory / "cluster_cov.npz")
        stats: list[ClusterStats] = []
        for row in df.itertuples():
            mu = np.asarray(row.mu, dtype=np.float32)
            sigma_inv = None
            if not row.low_sample:
                key = f"c{row.cluster_id}"
                if key in cov.files:
                    sigma_inv = np.asarray(cov[key], dtype=np.float32)
            stats.append(
                ClusterStats(
                    cluster_id=int(row.cluster_id),
                    product_type_id=int(row.product_type_id),
                    product_type_name=str(row.product_type_name),
                    attribute_name=str(row.attribute_name),
                    value=str(row.value),
                    n=int(row.n),
                    mu=mu,
                    sigma_inv=sigma_inv,
                    log_det_sigma=float(row.log_det_sigma),
                    low_sample=bool(row.low_sample),
                )
            )
        return cls(stats)


# ---------------------------------------------------------------------------
# Build factory
# ---------------------------------------------------------------------------


@dataclass
class _GroupAccumulator:
    """Internal: collect embeddings for one (PT, A, V) triple during the scan."""

    pt_id: int
    pt_name: str
    attribute_name: str
    value: str
    rows: list[np.ndarray] = field(default_factory=list)


def build_clusters(
    embeddings: np.ndarray,
    product_ids: np.ndarray,
    pt_index: Mapping[int, tuple[int, str]],
    attribute_pairs_chunks: Iterable[pd.DataFrame],
    train_product_id_set: set[int] | frozenset[int] | None = None,
    min_cluster_size: int = 5,
) -> ClusterStore:
    """Build per-cluster statistics from train-split 1A rows + embeddings.

    Args:
        embeddings: ``(N, D)`` float32 array of product embeddings, aligned
            row-for-row with ``product_ids``. Comes from the M3a FAISS
            index (rehydrated via ``index.reconstruct_n``).
        product_ids: ``(N,)`` int64 array of Product_IDs.
        pt_index: ``Product_ID → (ProductType_ID, ProductType_Name)`` map,
            typically built from 1B via :func:`build_pt_index_from_1b`.
        attribute_pairs_chunks: Iterator of 1A DataFrame chunks (e.g. from
            ``iter_attribute_pairs(chunksize=200_000)``). Each chunk must
            contain ``Product_ID``, ``Attribute_Name``, ``Attribute_Value``.
        train_product_id_set: If supplied, only rows whose ``Product_ID`` is
            in this set contribute to clusters. Pass the train-split IDs
            from M1 to honor the spec's train/val/test partition.
        min_cluster_size: Clusters with fewer members than this are flagged
            ``low_sample = True`` and skip the Σ computation (see
            ``config/thresholds.yaml`` for the canonical value).

    Returns:
        :class:`ClusterStore` containing one :class:`ClusterStats` per
        unique ``(ProductType_ID, Attribute_Name, Attribute_Value)`` triple
        encountered in the train-split 1A rows.
    """
    from sklearn.covariance import LedoitWolf

    pid_to_row = {int(pid): i for i, pid in enumerate(product_ids)}
    groups: dict[tuple[int, str, str], _GroupAccumulator] = {}

    for chunk in attribute_pairs_chunks:
        if train_product_id_set is not None:
            mask = chunk["Product_ID"].isin(train_product_id_set)
            chunk = chunk[mask]
        if chunk.empty:
            continue

        for pid, attr, val in zip(
            chunk["Product_ID"],
            chunk["Attribute_Name"],
            chunk["Attribute_Value"],
            strict=False,
        ):
            if pd.isna(attr) or pd.isna(val):
                continue
            pid_i = int(pid)
            row_idx = pid_to_row.get(pid_i)
            if row_idx is None:
                continue
            pt = pt_index.get(pid_i)
            if pt is None:
                continue
            pt_id, pt_name = pt
            key = (int(pt_id), str(attr), str(val))
            group = groups.get(key)
            if group is None:
                group = _GroupAccumulator(
                    pt_id=int(pt_id),
                    pt_name=str(pt_name),
                    attribute_name=str(attr),
                    value=str(val),
                )
                groups[key] = group
            group.rows.append(embeddings[row_idx])

    stats: list[ClusterStats] = []
    n_dim = int(embeddings.shape[1])
    for cluster_id, group in enumerate(groups.values()):
        n = len(group.rows)
        arr = np.stack(group.rows).astype(np.float32, copy=False)
        mu = arr.mean(axis=0).astype(np.float32)

        if n < min_cluster_size:
            stats.append(
                ClusterStats(
                    cluster_id=cluster_id,
                    product_type_id=group.pt_id,
                    product_type_name=group.pt_name,
                    attribute_name=group.attribute_name,
                    value=group.value,
                    n=n,
                    mu=mu,
                    sigma_inv=None,
                    log_det_sigma=0.0,
                    low_sample=True,
                )
            )
            continue

        # Ledoit-Wolf shrinkage covariance — robust to N close to D.
        lw = LedoitWolf().fit(arr)
        sigma = lw.covariance_.astype(np.float64, copy=False)
        sigma_inv: np.ndarray | None
        try:
            # slogdet is more numerically stable than log(det()).
            sign, logdet = np.linalg.slogdet(sigma)
            if sign <= 0:
                raise np.linalg.LinAlgError("non-positive determinant")
            sigma_inv_candidate = np.linalg.inv(sigma)
            # Post-inversion sanity: even when slogdet says "PD", a
            # near-singular sigma can produce an inverse with huge
            # negative-eigenvalue noise. Verify the inverse itself is PD
            # to a meaningful tolerance; otherwise demote to low_sample.
            #
            # Empirical observation (M3b build, 2026-05-18): cluster 6350
            # (NEMA 3R / WIDTH / 32.00 IN., N=12) produced an inverse
            # with min eigenvalue ≈ -3.4e+13 due to near-rank-deficient
            # embeddings. Healthy clusters have min eigenvalue >= ~4.
            inv_eigs = np.linalg.eigvalsh(sigma_inv_candidate)
            inv_eig_min = float(inv_eigs.min())
            inv_eig_max_abs = float(np.abs(inv_eigs).max())
            if inv_eig_min <= _PSD_EIG_MIN or inv_eig_max_abs >= _PSD_EIG_MAX_ABS:
                raise np.linalg.LinAlgError(
                    f"ill-conditioned inverse (min eig {inv_eig_min:.2e}, "
                    f"max |eig| {inv_eig_max_abs:.2e})"
                )
            sigma_inv = sigma_inv_candidate.astype(np.float32)
            low_sample = False
        except np.linalg.LinAlgError:
            # Cluster's covariance is too degenerate to produce a usable
            # inverse. Treat as low-sample so Layer 4 caps confidence
            # at the low-sample threshold.
            sigma_inv = None
            logdet = 0.0
            low_sample = True

        stats.append(
            ClusterStats(
                cluster_id=cluster_id,
                product_type_id=group.pt_id,
                product_type_name=group.pt_name,
                attribute_name=group.attribute_name,
                value=group.value,
                n=n,
                mu=mu,
                sigma_inv=sigma_inv,                  # already float32 above; None for low-sample
                log_det_sigma=float(logdet),
                low_sample=low_sample,
            )
        )

    return ClusterStore(stats)


# ---------------------------------------------------------------------------
# Helper: pull embeddings out of a FAISS index without re-encoding
# ---------------------------------------------------------------------------


def rehydrate_embeddings(index_obj: object) -> np.ndarray:
    """Reconstruct a flat ``(N, D)`` embedding array from a FAISS index.

    Use this to recover the M3a embeddings without re-running the
    ~98-minute encode. Builds an internal direct map on first call.

    Args:
        index_obj: The raw FAISS index (not our :class:`ProductIndex`
            wrapper — pass ``product_index._index``).

    Returns:
        ``(ntotal, dimension)`` float32 array. Rows are aligned with
        ``ProductIndex.product_ids``.
    """
    n = int(index_obj.ntotal)             # type: ignore[attr-defined]
    if hasattr(index_obj, "make_direct_map"):
        index_obj.make_direct_map()       # type: ignore[attr-defined]
    return index_obj.reconstruct_n(0, n)  # type: ignore[attr-defined]
