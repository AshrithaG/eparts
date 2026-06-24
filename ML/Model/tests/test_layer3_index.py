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

# ML-CT component: product search (M3a, FAISS index) — every test here is ML-CT.
pytestmark = pytest.mark.ml_ct


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


# ===========================================================================
# ML-CT P1 boundary tests (search) — see eparts_doc/ML_CT_Test_Plan.md Part D
# ===========================================================================


def test_load_missing_faiss_bin_raises(tmp_path):
    """Loading from a directory with no faiss.bin must fail loudly, not
    return a silently-empty / wrong index."""
    cfg = _faiss_config()
    # Empty dir → no faiss.bin / ids.npy at all.
    with pytest.raises(Exception):
        ProductIndex.load(tmp_path, cfg)


def test_load_corrupt_faiss_bin_raises(tmp_path, corpus):
    """A truncated/garbage faiss.bin must raise, not load garbage."""
    embeddings, ids = corpus
    cfg = _faiss_config()
    build_index(embeddings, ids, cfg).save(tmp_path)
    # Corrupt the serialized index in place.
    (tmp_path / "faiss.bin").write_bytes(b"not a real faiss index")
    with pytest.raises(Exception):
        ProductIndex.load(tmp_path, cfg)


def test_ivfflat_matches_flat_when_exhaustive(corpus):
    """IVFFlat with nprobe == nlist searches every Voronoi cell, so it is
    exact and its top-K must match a brute-force Flat index exactly. This
    pins the two index variants against each other (previously each was
    only tested in isolation). nprobe==nlist makes this deterministic and
    non-flaky — no approximate-recall slop."""
    embeddings, ids = corpus
    nlist = 8
    ivf_cfg = FaissConfig(
        index_type="IVFFlat", metric="inner_product", nlist=nlist,
        nprobe=nlist,                       # exhaustive → exact
        top_k=10, training_subset_size=200, training_seed=42,
        input_text_columns=("Short_Description",),
    )
    flat_cfg = FaissConfig(
        index_type="Flat", metric="inner_product", nlist=nlist, nprobe=nlist,
        top_k=10, training_subset_size=200, training_seed=42,
        input_text_columns=("Short_Description",),
    )
    ivf = build_index(embeddings, ids, ivf_cfg)
    flat = build_index(embeddings, ids, flat_cfg)
    q = embeddings[7:8]
    [ivf_hits] = ivf.search(q)
    [flat_hits] = flat.search(q)
    assert [h.product_id for h in ivf_hits] == [h.product_id for h in flat_hits]


def test_k_greater_than_ntotal_returns_all_without_padding(corpus):
    """Asking for more neighbors than the index holds: FAISS pads the
    result with -1, which search() must filter (index.py:111). Uses a
    Flat (exhaustive) index so k > ntotal deterministically forces FAISS
    to emit padding — an approximate IVFFlat at nprobe<nlist would instead
    return only the probed cells' vectors, which wouldn't exercise the
    -1 filter. We expect exactly `ntotal` real hits, no -1 leakage, no
    crash."""
    embeddings, ids = corpus           # 200 vectors
    flat_cfg = FaissConfig(
        index_type="Flat", metric="inner_product", nlist=8, nprobe=8,
        top_k=5, training_subset_size=200, training_seed=42,
        input_text_columns=("Short_Description",),
    )
    idx = build_index(embeddings, ids, flat_cfg)
    [hits] = idx.search(embeddings[0:1], k=250)   # k > 200 → 50 padding slots
    assert len(hits) == 200            # padding (-1) filtered out
    pids = {h.product_id for h in hits}
    assert -1 not in pids
    assert len(pids) == 200            # all distinct real products
