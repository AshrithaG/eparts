"""Layer 3 [3c] — ProductType consensus from FAISS top-K neighbors.

Implements V1_Engineering_Spec §4.3 [3c].

Math (per spec):
    vote[PT]        = Σ sim(q, p_i)  for p_i in top-K with ProductType = PT
    PT_predicted    = argmax_PT vote[PT]
    PT_conf         = vote[PT_predicted] / Σ vote[PT]

Three bands (FROZEN per §4.3 [3c]; cap thresholds in config/thresholds.yaml):
    PT_conf ≥ 0.80    → high consensus
    0.60 ≤ < 0.80     → normal consensus
    PT_conf < 0.60    → ambiguous; Layer 4 caps conf_final at 0.75 for all attributes
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import pandas as pd

from ..contracts import ProductTypePrediction
from .index import SearchHit


@dataclass(frozen=True, slots=True)
class ProductTypeIndex:
    """Lookup table from ``Product_ID`` to ``(ProductType_ID, ProductType_Name)``.

    Built once at service startup from 1B; used by ProductType consensus to
    resolve each FAISS hit's product into a PT vote.
    """

    pt_id_by_product: Mapping[int, int]
    pt_name_by_id: Mapping[int, str]

    @property
    def size(self) -> int:
        return len(self.pt_id_by_product)

    def lookup(self, product_id: int) -> tuple[int, str] | None:
        """Return ``(pt_id, pt_name)`` for ``product_id``, or ``None`` if absent."""
        pt_id = self.pt_id_by_product.get(int(product_id))
        if pt_id is None:
            return None
        return int(pt_id), self.pt_name_by_id.get(int(pt_id), "")


def build_pt_index_from_1b(products_df: pd.DataFrame | None = None) -> ProductTypeIndex:
    """Build :class:`ProductTypeIndex` from 1B's Product_ID → ProductType columns.

    Args:
        products_df: Pre-loaded 1B DataFrame with columns ``Product_ID``,
            ``ProductType_ID``, ``ProductType_Name``. When ``None``, loads
            from disk via :func:`src.data.load_products`.
    """
    if products_df is None:
        from ..data import load_products
        products_df = load_products(
            columns=["Product_ID", "ProductType_ID", "ProductType_Name"]
        )

    required = {"Product_ID", "ProductType_ID", "ProductType_Name"}
    missing = required - set(products_df.columns)
    if missing:
        raise ValueError(f"1B frame is missing required columns: {missing}")

    df = products_df.dropna(subset=["Product_ID", "ProductType_ID"]).copy()
    pt_id_by_product = {
        int(pid): int(ptid)
        for pid, ptid in zip(df["Product_ID"], df["ProductType_ID"], strict=False)
    }
    pt_name_by_id: dict[int, str] = {}
    for ptid, name in zip(df["ProductType_ID"], df["ProductType_Name"], strict=False):
        if pd.notna(name):
            pt_name_by_id[int(ptid)] = str(name)

    return ProductTypeIndex(
        pt_id_by_product=pt_id_by_product,
        pt_name_by_id=pt_name_by_id,
    )


def compute_pt_consensus(
    hits: Iterable[SearchHit],
    pt_index: ProductTypeIndex,
    top_k: int | None = None,
) -> ProductTypePrediction | None:
    """Compute the ProductType consensus from a list of FAISS hits.

    Args:
        hits: FAISS search results for one query. Already sorted by descending
            similarity (FAISS guarantees this).
        pt_index: Resolves Product_ID → (PT_ID, PT_Name).
        top_k: Optionally restrict the vote to the first ``top_k`` hits.
            Defaults to using all supplied hits (which should be top-K
            from FAISS already).

    Returns:
        :class:`ProductTypePrediction` with the winning ProductType and
        the normalized consensus confidence ``pt_conf ∈ [0, 1]``. Returns
        ``None`` only if no hit could be resolved through ``pt_index``
        (e.g. a corrupt index that references unknown Product_IDs).

    Notes:
        Similarities below 0 are clamped to 0 (inner-product on
        L2-normalized vectors is in [-1, 1]; negative similarity should
        not pull weight away from the rest of the ballot).
    """
    vote_by_pt: dict[int, float] = {}
    pt_name_by_id: dict[int, str] = {}

    consumed = 0
    for hit in hits:
        if top_k is not None and consumed >= top_k:
            break
        consumed += 1
        resolved = pt_index.lookup(hit.product_id)
        if resolved is None:
            continue
        pt_id, pt_name = resolved
        weight = max(hit.score, 0.0)
        vote_by_pt[pt_id] = vote_by_pt.get(pt_id, 0.0) + weight
        pt_name_by_id.setdefault(pt_id, pt_name)

    if not vote_by_pt:
        return None

    total = sum(vote_by_pt.values())
    if total <= 0.0:
        return None

    pt_predicted = max(vote_by_pt, key=lambda k: vote_by_pt[k])
    pt_conf = vote_by_pt[pt_predicted] / total

    return ProductTypePrediction(
        product_type_id=pt_predicted,
        product_type_name=pt_name_by_id.get(pt_predicted, ""),
        pt_conf=float(pt_conf),
    )
