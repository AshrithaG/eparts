"""Layer 3 [3b] FAISS index tests (V1 spec §4.3 [3b]).

These tests run on synthetic float32 vectors only — no encoder /
sentence-transformers load — so they stay fast and have no model
dependency.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.config import FaissConfig
from src.layer3_semantic import ProductIndex, build_index


def _faiss_config(top_k: int = 5, nlist: int = 8) -> FaissConfig:
    return FaissConfig(
        index_type="IVFFlat",
        metric="inner_product",
        nlist=nlist,
        nprobe=4,
        top_k=top_k,
        training_subset_size=200,
        training_seed=42,
        input_text_columns=("Short_Description",),
    )


def _l2(rows: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(rows, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return (rows / norms).astype(np.float32)


@pytest.fixture
def corpus():
    """200 random 384-d vectors with stable IDs."""
    rng = np.random.default_rng(123)
    raw = rng.standard_normal(size=(200, 384)).astype(np.float32)
    ids = np.arange(1000, 1200, dtype=np.int64)
    return _l2(raw), ids


def test_build_index_populates_n_total(corpus):
    embeddings, ids = corpus
    idx = build_index(embeddings, ids, _faiss_config())
    assert idx.size == 200
    assert idx.dimension == 384


def test_search_returns_top_k_with_self_as_first_neighbor(corpus):
    embeddings, ids = corpus
    cfg = _faiss_config(top_k=5)
    idx = build_index(embeddings, ids, cfg)
    # Query with vector #7 — it should be its own top-1 neighbor at score ≈ 1.0.
    q = embeddings[7:8]
    [hits] = idx.search(q)
    assert len(hits) == 5
    assert hits[0].product_id == int(ids[7])
    assert hits[0].score == pytest.approx(1.0, abs=1e-4)


def test_search_k_override(corpus):
    embeddings, ids = corpus
    idx = build_index(embeddings, ids, _faiss_config(top_k=10))
    [hits] = idx.search(embeddings[0:1], k=3)
    assert len(hits) == 3


def test_persistence_roundtrip(tmp_path, corpus):
    embeddings, ids = corpus
    cfg = _faiss_config()
    idx = build_index(embeddings, ids, cfg)
    idx.save(tmp_path)
    assert (tmp_path / "faiss.bin").exists()
    assert (tmp_path / "ids.npy").exists()

    reloaded = ProductIndex.load(tmp_path, cfg)
    assert reloaded.size == idx.size
    [hits_a] = idx.search(embeddings[3:4])
    [hits_b] = reloaded.search(embeddings[3:4])
    assert [h.product_id for h in hits_a] == [h.product_id for h in hits_b]
    assert np.allclose(
        [h.score for h in hits_a], [h.score for h in hits_b], atol=1e-5
    )


def test_id_length_mismatch_raises(corpus):
    embeddings, ids = corpus
    with pytest.raises(ValueError):
        build_index(embeddings, ids[:-1], _faiss_config())


def test_unknown_index_type_raises(corpus):
    embeddings, ids = corpus
    cfg = FaissConfig(
        index_type="HNSW",                          # not yet wired
        metric="inner_product",
        nlist=8,
        nprobe=4,
        top_k=5,
        training_subset_size=100,
        training_seed=42,
        input_text_columns=("Short_Description",),
    )
    with pytest.raises(ValueError, match="Unknown index_type"):
        build_index(embeddings, ids, cfg)


def test_query_accepts_1d_vector(corpus):
    embeddings, ids = corpus
    idx = build_index(embeddings, ids, _faiss_config())
    # Pass a 1-D vector; index should reshape it internally.
    results = idx.search(embeddings[0])
    assert len(results) == 1
    assert results[0][0].product_id == int(ids[0])


def test_flat_index_variant(corpus):
    """Flat index also works (debug / reference path per spec §6.2)."""
    embeddings, ids = corpus
    cfg = FaissConfig(
        index_type="Flat",
        metric="inner_product",
        nlist=8,
        nprobe=4,
        top_k=3,
        training_subset_size=100,
        training_seed=42,
        input_text_columns=("Short_Description",),
    )
    idx = build_index(embeddings, ids, cfg)
    [hits] = idx.search(embeddings[42:43])
    assert hits[0].product_id == int(ids[42])
