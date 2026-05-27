"""Layer 3 — semantic matcher.

Implements V1_Engineering_Spec §4.3:
    [3a] Sentence-transformer encoder (``BAAI/bge-small-en-v1.5``, 384-d).
    [3b] FAISS IVFFlat index over 1B product descriptions.
    [3c] ProductType consensus from top-K weighted vote.
    [3d] Per-cluster Mahalanobis statistics (μ + Σ⁻¹) with Ledoit-Wolf
         shrinkage, plus per-attribute per-value scoring with Usage_Count
         log prior (this file's :mod:`.scoring`).
"""

from .clusters import (
    ClusterStats,
    ClusterStore,
    build_clusters,
    rehydrate_embeddings,
)
from .consensus import (
    ProductTypeIndex,
    build_pt_index_from_1b,
    compute_pt_consensus,
)
from .encoder import Encoder
from .index import ProductIndex, SearchHit, build_index
from .scoring import (
    SemanticScorer,
    SemanticScorerConfig,
    UsagePrior,
    build_usage_prior_from_2a,
)

__all__ = [
    "ClusterStats",
    "ClusterStore",
    "Encoder",
    "ProductIndex",
    "ProductTypeIndex",
    "SearchHit",
    "SemanticScorer",
    "SemanticScorerConfig",
    "UsagePrior",
    "build_clusters",
    "build_index",
    "build_pt_index_from_1b",
    "build_usage_prior_from_2a",
    "compute_pt_consensus",
    "rehydrate_embeddings",
]
