"""Layer 3 [3d] cluster statistics tests (V1 spec §4.3 [3d])."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.layer3_semantic.clusters import (
    ClusterStats,
    ClusterStore,
    build_clusters,
)

# ML-CT component: category prediction (M3b) — every test here is ML-CT.
pytestmark = pytest.mark.ml_ct


# ---------------------------------------------------------------------------
# Test fixtures: synthetic 16-d embeddings + a small 1A-like frame
# ---------------------------------------------------------------------------

DIM = 16
SEED = 7


def _make_embeddings_and_index(n_products: int, dim: int = DIM):
    rng = np.random.default_rng(SEED)
    raw = rng.standard_normal(size=(n_products, dim)).astype(np.float32)
    # L2-normalize per the FAISS index convention.
    raw /= np.linalg.norm(raw, axis=1, keepdims=True).clip(min=1e-9)
    pids = np.arange(1000, 1000 + n_products, dtype=np.int64)
    return raw, pids


def _make_pt_index(n_products: int) -> dict[int, tuple[int, str]]:
    """Assign products 0..n in alternating bands to PT 10 and PT 20."""
    idx: dict[int, tuple[int, str]] = {}
    for i in range(n_products):
        pid = 1000 + i
        if i < n_products // 2:
            idx[pid] = (10, "Thermostats")
        else:
            idx[pid] = (20, "Actuators")
    return idx


def _make_1a_chunk(rows: list[tuple[int, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows, columns=["Product_ID", "Attribute_Name", "Attribute_Value"]
    )


# ---------------------------------------------------------------------------
# ClusterStats unit-level behavior
# ---------------------------------------------------------------------------


def test_mahalanobis_uses_identity_for_low_sample():
    """Low-sample cluster: Σ⁻¹ is None → falls back to squared Euclidean."""
    mu = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    s = ClusterStats(
        cluster_id=0,
        product_type_id=10,
        product_type_name="X",
        attribute_name="A",
        value="v",
        n=3,
        mu=mu,
        sigma_inv=None,
        log_det_sigma=0.0,
        low_sample=True,
    )
    q = np.array([1.0, 2.0, 0.0], dtype=np.float32)
    assert s.mahalanobis_squared(q) == pytest.approx(4.0)  # diff=[0,2,0]; d²=4


def test_mahalanobis_uses_sigma_inv_when_present():
    """With Σ⁻¹ = 4I, d² = 4 * ||q - μ||²."""
    mu = np.zeros(3, dtype=np.float32)
    sigma_inv = (4.0 * np.eye(3)).astype(np.float32)
    s = ClusterStats(
        cluster_id=0,
        product_type_id=10,
        product_type_name="X",
        attribute_name="A",
        value="v",
        n=10,
        mu=mu,
        sigma_inv=sigma_inv,
        log_det_sigma=-3 * np.log(4),
        low_sample=False,
    )
    q = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    assert s.mahalanobis_squared(q) == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# build_clusters end-to-end on synthetic data
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_setup():
    n_products = 40
    embeddings, pids = _make_embeddings_and_index(n_products)
    pt_index = _make_pt_index(n_products)
    return embeddings, pids, pt_index


def test_build_clusters_groups_by_pt_attr_value(synthetic_setup):
    embeddings, pids, pt_index = synthetic_setup
    # Build a 1A chunk where each cluster gets enough samples.
    rows: list[tuple[int, str, str]] = []
    # Cluster (PT=10, A=VOLT, V=24) → 8 members from PT-10 band (pids 1000..1019)
    for i in range(8):
        rows.append((1000 + i, "INPUT_VOLTAGE", "24"))
    # Cluster (PT=10, A=VOLT, V=120) → 6 members from PT-10 band
    for i in range(8, 14):
        rows.append((1000 + i, "INPUT_VOLTAGE", "120"))
    # Cluster (PT=20, A=MOUNT, V=STRAP-ON) → 7 members from PT-20 band
    for i in range(20, 27):
        rows.append((1000 + i, "MOUNTING", "STRAP-ON"))
    # Low-sample: (PT=20, A=COLOR, V=BLUE) → 3 members
    for i in range(30, 33):
        rows.append((1000 + i, "COLOR", "BLUE"))

    chunks = [_make_1a_chunk(rows)]
    store = build_clusters(embeddings, pids, pt_index, chunks, min_cluster_size=5)

    assert len(store) == 4
    assert store.n_low_sample == 1
    # Sanity: lookups resolve to the right cluster
    c = store.lookup(10, "INPUT_VOLTAGE", "24")
    assert c is not None
    assert c.n == 8 and c.low_sample is False
    c_low = store.lookup(20, "COLOR", "BLUE")
    assert c_low.n == 3 and c_low.low_sample is True


def test_cluster_mu_equals_mean_of_member_embeddings(synthetic_setup):
    embeddings, pids, pt_index = synthetic_setup
    rows = [(1000 + i, "X", "v1") for i in range(10)]
    chunks = [_make_1a_chunk(rows)]
    store = build_clusters(embeddings, pids, pt_index, chunks, min_cluster_size=5)
    c = store.lookup(10, "X", "v1")
    expected_mu = embeddings[:10].mean(axis=0).astype(np.float32)
    np.testing.assert_allclose(c.mu, expected_mu, atol=1e-6)


def test_sigma_inv_is_positive_definite_for_full_clusters(synthetic_setup):
    """Every full (non-low-sample) cluster's Σ⁻¹ must be positive-definite."""
    embeddings, pids, pt_index = synthetic_setup
    # Multiple clusters, each with N >= 5
    rows = [
        *[(1000 + i, "A", "v1") for i in range(8)],
        *[(1000 + i, "A", "v2") for i in range(8, 16)],
        *[(1000 + i, "B", "v1") for i in range(20, 28)],
    ]
    chunks = [_make_1a_chunk(rows)]
    store = build_clusters(embeddings, pids, pt_index, chunks, min_cluster_size=5)
    for s in store.stats:
        if s.low_sample:
            continue
        # PD ⇔ all eigenvalues > 0
        eigvals = np.linalg.eigvalsh(s.sigma_inv)
        assert (eigvals > 0).all(), f"cluster {s.cluster_id}: min eig {eigvals.min()}"


def test_ill_conditioned_cluster_is_demoted_to_low_sample():
    """Near-rank-deficient embeddings → inverse has huge negative eigenvalues.

    Regression for the M3b production finding (cluster 6350: NEMA 3R /
    WIDTH / 32.00 IN., N=12 nearly-identical embeddings produced
    Sigma_inv with min eigenvalue ≈ -3.4e+13).  The build path must
    detect this and demote the cluster to ``low_sample`` rather than
    persisting a broken Sigma_inv.
    """
    rng = np.random.default_rng(0)
    # Six near-identical 16-d vectors: one base + tiny per-row jitter.
    # Sample covariance is essentially rank 1; even Ledoit-Wolf shrinkage
    # won't produce a well-conditioned inverse.
    base = rng.standard_normal(16).astype(np.float32)
    jitter = rng.standard_normal(size=(6, 16)).astype(np.float32) * 1e-8
    embs = (base + jitter)
    embs /= np.linalg.norm(embs, axis=1, keepdims=True)
    pids = np.arange(1000, 1006, dtype=np.int64)
    pt_idx = {int(p): (10, "X") for p in pids}
    rows = [(int(p), "A", "v") for p in pids]
    chunk = pd.DataFrame(rows, columns=["Product_ID", "Attribute_Name", "Attribute_Value"])
    store = build_clusters(
        embs.astype(np.float32),
        pids,
        pt_idx,
        [chunk],
        min_cluster_size=5,                 # N=6 ≥ 5, normally a "full" cluster
    )
    cluster = store.lookup(10, "A", "v")
    assert cluster is not None
    assert cluster.n == 6
    # The near-rank-deficient embeddings must trigger the demotion path.
    assert cluster.low_sample is True
    assert cluster.sigma_inv is None


def test_low_sample_clusters_store_only_mu(synthetic_setup):
    embeddings, pids, pt_index = synthetic_setup
    rows = [(1000 + i, "TINY", "v") for i in range(3)]      # only 3 members
    store = build_clusters(embeddings, pids, pt_index, [_make_1a_chunk(rows)])
    c = store.lookup(10, "TINY", "v")
    assert c.low_sample is True
    assert c.sigma_inv is None
    assert c.log_det_sigma == 0.0


def test_chunked_streaming_combines_groups_across_chunks(synthetic_setup):
    embeddings, pids, pt_index = synthetic_setup
    chunk_a = _make_1a_chunk([(1000 + i, "A", "v") for i in range(0, 4)])
    chunk_b = _make_1a_chunk([(1000 + i, "A", "v") for i in range(4, 9)])
    store = build_clusters(embeddings, pids, pt_index, [chunk_a, chunk_b])
    c = store.lookup(10, "A", "v")
    assert c is not None
    assert c.n == 9
    assert c.low_sample is False  # 9 ≥ 5


def test_train_split_filter_drops_non_train_rows(synthetic_setup):
    embeddings, pids, pt_index = synthetic_setup
    rows = [
        (1000 + i, "A", "v") for i in range(20)
    ]  # 20 members — but only first 10 in train
    train_ids = {1000 + i for i in range(10)}
    store = build_clusters(
        embeddings,
        pids,
        pt_index,
        [_make_1a_chunk(rows)],
        train_product_id_set=train_ids,
    )
    c = store.lookup(10, "A", "v")
    assert c.n == 10  # only train rows counted


def test_unknown_product_id_in_1a_is_skipped(synthetic_setup):
    embeddings, pids, pt_index = synthetic_setup
    rows = [(99999, "A", "v")] + [(1000 + i, "A", "v") for i in range(6)]
    store = build_clusters(embeddings, pids, pt_index, [_make_1a_chunk(rows)])
    c = store.lookup(10, "A", "v")
    assert c.n == 6   # the bogus 99999 did not crash anything


def test_null_attribute_or_value_is_skipped(synthetic_setup):
    embeddings, pids, pt_index = synthetic_setup
    rows = [
        (1001, None, "v"),
        (1002, "A", None),
        *[(1000 + i, "A", "v") for i in range(6)],
    ]
    store = build_clusters(embeddings, pids, pt_index, [_make_1a_chunk(rows)])
    assert store.lookup(10, "A", "v").n == 6


# ---------------------------------------------------------------------------
# ClusterStore API
# ---------------------------------------------------------------------------


def test_attributes_for_pt_and_values_for_pt_attribute(synthetic_setup):
    embeddings, pids, pt_index = synthetic_setup
    rows = [
        *[(1000 + i, "A", "v1") for i in range(8)],
        *[(1000 + i, "A", "v2") for i in range(8, 16)],
        *[(1000 + i, "B", "v1") for i in range(0, 8)],
    ]
    store = build_clusters(embeddings, pids, pt_index, [_make_1a_chunk(rows)])
    assert store.attributes_for_pt(10) == {"A", "B"}
    values = store.values_for_pt_attribute(10, "A")
    assert {v.value for v in values} == {"v1", "v2"}


# ---------------------------------------------------------------------------
# Persistence roundtrip
# ---------------------------------------------------------------------------


def test_persistence_roundtrip(tmp_path, synthetic_setup):
    embeddings, pids, pt_index = synthetic_setup
    rows = [
        *[(1000 + i, "A", "v1") for i in range(8)],     # full cluster
        *[(1000 + i, "A", "v2") for i in range(8, 11)], # low-sample (3)
    ]
    store = build_clusters(embeddings, pids, pt_index, [_make_1a_chunk(rows)])
    store.save(tmp_path)

    assert (tmp_path / "centroids.parquet").exists()
    assert (tmp_path / "cluster_cov.npz").exists()

    reloaded = ClusterStore.load(tmp_path)
    assert len(reloaded) == len(store)
    assert reloaded.n_low_sample == store.n_low_sample

    # Spot-check both branches
    c_full = reloaded.lookup(10, "A", "v1")
    c_low = reloaded.lookup(10, "A", "v2")
    assert c_full.sigma_inv is not None
    assert c_low.sigma_inv is None
    # μ vectors are float32-equal
    original_full = store.lookup(10, "A", "v1")
    np.testing.assert_allclose(c_full.mu, original_full.mu, atol=1e-6)
    np.testing.assert_allclose(c_full.sigma_inv, original_full.sigma_inv, atol=1e-5)
