"""Layer 3 [3b] — FAISS IVFFlat index over the 1B product catalog.

Implements V1_Engineering_Spec §4.3 [3b].

The index maps an ``int64`` ``Product_ID`` to a 384-d L2-normalized
embedding. Queries return ``(scores, product_ids)`` for the top-K
nearest neighbors under inner-product similarity.

Index hyperparameters (``nlist``, ``nprobe``, ``top_k``) live in
``config/faiss.yaml`` (spec §11.3). Switching to a flat or HNSW index
is a config change — this module's :func:`build_index` factory inspects
``config.index_type`` so callers don't need to know which variant they
get.

Persistence:
    * ``faiss.bin``    — the FAISS-native serialization
    * ``ids.npy``      — the int64 array of product IDs aligned with the
                          embedding rows (FAISS only stores rows, not labels)
Both files live together under ``artifacts/v1/run_<ts>/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import FaissConfig


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One nearest-neighbor result from a FAISS query."""

    product_id: int
    score: float          # inner-product on L2-normalized vectors = cosine similarity


class ProductIndex:
    """FAISS index over the 1B product catalog.

    Construct via :func:`build_index` (encodes and trains a fresh index)
    or :meth:`load` (rehydrates from disk).
    """

    def __init__(
        self,
        index: object,
        product_ids: np.ndarray,
        config: FaissConfig,
    ) -> None:
        if product_ids.dtype != np.int64:
            product_ids = product_ids.astype(np.int64, copy=False)
        if index.ntotal != len(product_ids):                      # type: ignore[attr-defined]
            raise ValueError(
                f"index has {index.ntotal} vectors but {len(product_ids)} "  # type: ignore[attr-defined]
                "product IDs were supplied"
            )
        self._index = index
        self._product_ids = product_ids
        self._config = config
        # Configure query-time probe count once at construction.
        if hasattr(self._index, "nprobe"):
            self._index.nprobe = config.nprobe                     # type: ignore[attr-defined]

    @property
    def size(self) -> int:
        return int(self._index.ntotal)                             # type: ignore[attr-defined]

    @property
    def dimension(self) -> int:
        return int(self._index.d)                                  # type: ignore[attr-defined]

    @property
    def product_ids(self) -> np.ndarray:
        return self._product_ids

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def search(
        self,
        query_vectors: np.ndarray,
        k: int | None = None,
    ) -> list[list[SearchHit]]:
        """Return top-K nearest neighbors per query vector.

        Args:
            query_vectors: ``(B, dimension)`` float32 array. Must be
                L2-normalized for the inner-product metric to act as
                cosine similarity.
            k: Override the configured top-K (defaults to
                ``config.top_k``).

        Returns:
            One list per query row, each containing up to ``k``
            :class:`SearchHit` entries sorted by descending similarity.
        """
        if query_vectors.dtype != np.float32:
            query_vectors = query_vectors.astype(np.float32, copy=False)
        if query_vectors.ndim == 1:
            query_vectors = query_vectors.reshape(1, -1)
        topk = k if k is not None else self._config.top_k
        scores, idxs = self._index.search(query_vectors, topk)    # type: ignore[attr-defined]
        results: list[list[SearchHit]] = []
        for row_scores, row_idxs in zip(scores, idxs, strict=True):
            row: list[SearchHit] = []
            for score, idx in zip(row_scores, row_idxs, strict=True):
                if idx == -1:                                       # FAISS pads short results with -1
                    continue
                row.append(
                    SearchHit(
                        product_id=int(self._product_ids[idx]),
                        score=float(score),
                    )
                )
            results.append(row)
        return results

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, directory: Path) -> None:
        """Persist the FAISS index and the aligned product-ID array.

        Args:
            directory: Output directory. Created if missing. Two files
                are written: ``faiss.bin`` and ``ids.npy``.
        """
        import faiss

        directory.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(directory / "faiss.bin"))
        np.save(directory / "ids.npy", self._product_ids)

    @classmethod
    def load(cls, directory: Path, config: FaissConfig) -> ProductIndex:
        """Rehydrate a previously-saved index from ``directory``."""
        import faiss

        index = faiss.read_index(str(directory / "faiss.bin"))
        product_ids = np.load(directory / "ids.npy")
        return cls(index, product_ids, config)


# ---------------------------------------------------------------------------
# Build factory
# ---------------------------------------------------------------------------


def build_index(
    embeddings: np.ndarray,
    product_ids: np.ndarray,
    config: FaissConfig,
    rng: np.random.Generator | None = None,
) -> ProductIndex:
    """Build a fresh FAISS index per the supplied ``config``.

    Args:
        embeddings: ``(N, dimension)`` float32 array, L2-normalized.
        product_ids: ``(N,)`` int64 array aligned with ``embeddings``.
        config: FAISS configuration (index type, nlist, nprobe, etc.).
        rng: Random generator for training-subset selection. When
            ``None`` we use ``np.random.default_rng(config.training_seed)``.

    Returns:
        Trained and populated :class:`ProductIndex`.
    """
    import faiss

    if embeddings.dtype != np.float32:
        embeddings = embeddings.astype(np.float32, copy=False)
    n, d = embeddings.shape
    if len(product_ids) != n:
        raise ValueError(
            f"embeddings has {n} rows but product_ids has {len(product_ids)}"
        )

    metric = (
        faiss.METRIC_INNER_PRODUCT
        if config.metric == "inner_product"
        else faiss.METRIC_L2
    )

    if config.index_type == "Flat":
        index: object = (
            faiss.IndexFlatIP(d) if metric == faiss.METRIC_INNER_PRODUCT
            else faiss.IndexFlatL2(d)
        )
    elif config.index_type == "IVFFlat":
        quantizer = (
            faiss.IndexFlatIP(d) if metric == faiss.METRIC_INNER_PRODUCT
            else faiss.IndexFlatL2(d)
        )
        # nlist is capped by what the data can support — a Voronoi cell
        # needs at least one point to train against, and FAISS warns
        # below ~30 points/cell. For small synthetic corpora (tests) we
        # quietly cap nlist to ensure trainability.
        max_nlist = max(1, n // 4)
        nlist = min(config.nlist, max_nlist)
        index = faiss.IndexIVFFlat(quantizer, d, nlist, metric)
    else:
        raise ValueError(f"Unknown index_type: {config.index_type!r}")

    # Train the IVF clusters on a random subset.
    if not index.is_trained:                                       # type: ignore[attr-defined]
        rng = rng or np.random.default_rng(config.training_seed)
        train_n = min(config.training_subset_size, n)
        train_idx = rng.choice(n, size=train_n, replace=False)
        train_vecs = embeddings[train_idx]
        index.train(train_vecs)                                    # type: ignore[attr-defined]

    index.add(embeddings)                                          # type: ignore[attr-defined]
    return ProductIndex(index, product_ids, config)
