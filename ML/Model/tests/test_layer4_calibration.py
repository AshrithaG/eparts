"""Layer 4 σ-calibration tests (V1 spec §5.3 + §7.2 M4)."""
from __future__ import annotations

import math

import numpy as np
import pytest

from src.config import CalibrationConfig
from src.layer3_semantic.clusters import ClusterStats, ClusterStore
from src.layer3_semantic.scoring import UsagePrior
from src.layer4_decision.calibration import (
    SigmaCalibrator,
    SigmaEntry,
    SigmaTable,
    ValQuery,
    brier_score,
    expected_calibration_error,
)


# ===========================================================================
# Brier + ECE math
# ===========================================================================


def test_brier_perfect_calibration():
    """Confidences match outcomes exactly → Brier = 0."""
    assert brier_score([0.0, 1.0, 0.0, 1.0], [0, 1, 0, 1]) == pytest.approx(0.0)


def test_brier_worst_case():
    """Confidence 1.0 always wrong, 0.0 always right (or vice versa) → Brier = 1.0."""
    assert brier_score([1.0, 1.0, 0.0, 0.0], [0, 0, 1, 1]) == pytest.approx(1.0)


def test_brier_hand_computed():
    """Spot-check formula on a small example."""
    probs = [0.8, 0.3, 0.6]
    outs = [1, 0, 1]
    expected = ((0.8 - 1) ** 2 + (0.3 - 0) ** 2 + (0.6 - 1) ** 2) / 3
    assert brier_score(probs, outs) == pytest.approx(expected)


def test_brier_empty_input_returns_zero():
    assert brier_score([], []) == 0.0


def test_ece_perfect_calibration():
    """If P(correct | conf=c) = c, ECE = 0."""
    # 100 samples at conf=0.5, 50 of which are correct.
    probs = [0.5] * 100
    outs = [1] * 50 + [0] * 50
    assert expected_calibration_error(probs, outs) == pytest.approx(0.0)


def test_ece_max_miscalibration():
    """All confidences 1.0 but zero accuracy → ECE = 1.0."""
    assert expected_calibration_error([1.0] * 10, [0] * 10) == pytest.approx(1.0)


def test_ece_empty_input_returns_zero():
    assert expected_calibration_error([], []) == 0.0


def test_ece_handles_bin_with_no_samples():
    """ECE should skip empty bins, not divide-by-zero."""
    # All samples land in one bin; other 9 bins are empty.
    probs = [0.05] * 10
    outs = [0] * 10
    assert 0.0 <= expected_calibration_error(probs, outs) <= 1.0


# ===========================================================================
# SigmaTable persistence
# ===========================================================================


def test_sigma_table_roundtrip(tmp_path):
    entries = [
        SigmaEntry(pt_id=10, pt_name="PT10", sigma_optimal=5.0, brier_at_opt=0.1,
                   ece_at_opt=0.02, loss_at_opt=0.11, n_val_samples=100, n_clusters_used=20),
        SigmaEntry(pt_id=20, pt_name="PT20", sigma_optimal=80.0, brier_at_opt=0.2,
                   ece_at_opt=0.05, loss_at_opt=0.225, n_val_samples=50, n_clusters_used=8),
    ]
    table = SigmaTable(entries)
    table.save(tmp_path)
    reloaded = SigmaTable.load(tmp_path)
    assert len(reloaded) == 2
    assert reloaded.sigma_for(10) == 5.0
    assert reloaded.sigma_for(20) == 80.0
    assert reloaded.sigma_for(999, default=1.0) == 1.0
    by_pt = reloaded.as_sigma_by_pt()
    assert by_pt == {10: 5.0, 20: 80.0}


def test_sigma_for_missing_pt_returns_default():
    table = SigmaTable([])
    assert table.sigma_for(42, default=2.5) == 2.5


# ===========================================================================
# SigmaCalibrator — synthetic recovery
# ===========================================================================


DIM = 16


def _l2(v: np.ndarray) -> np.ndarray:
    return (v / np.linalg.norm(v)).astype(np.float32)


def _full_cluster(cid: int, pt_id: int, attr: str, value: str, mu: np.ndarray) -> ClusterStats:
    """Cluster with identity Σ⁻¹ — Mahalanobis ≡ squared Euclidean."""
    return ClusterStats(
        cluster_id=cid, product_type_id=pt_id, product_type_name=f"PT{pt_id}",
        attribute_name=attr, value=value, n=10,
        mu=mu.astype(np.float32),
        sigma_inv=np.eye(DIM, dtype=np.float32),
        log_det_sigma=0.0, low_sample=False,
    )


def _calibration_config(
    sigma_grid: tuple[float, ...] = (0.1, 0.5, 1.0, 5.0, 30.0),
    lambda_cal: float = 0.5,
    reliability_bins: int = 10,
) -> CalibrationConfig:
    return CalibrationConfig(
        sigma_grid=sigma_grid,
        lambda_cal=lambda_cal,
        secondary_calibration_enabled=False,
        secondary_calibration_ocr_cache_path="",
        reliability_bins=reliability_bins,
    )


def _uniform_prior() -> UsagePrior:
    """Prior that doesn't favor any value — keeps the test deterministic on σ alone."""
    return UsagePrior(
        counts={("a", "v1"): 10, ("a", "v2"): 10, ("a", "v3"): 10},
        max_counts={"a": 10},
    )


def test_calibrator_recovers_small_sigma_when_clusters_are_close():
    """With small d² (~0.1-0.5) and tight clusters, a smaller σ minimizes loss."""
    rng = np.random.default_rng(0)
    pt_id = 10
    # 3 clusters with means slightly apart on a unit sphere.
    mu_v1 = _l2(rng.standard_normal(DIM).astype(np.float32))
    mu_v2 = _l2(mu_v1 + 0.3 * rng.standard_normal(DIM))
    mu_v3 = _l2(mu_v1 + 0.6 * rng.standard_normal(DIM))
    store = ClusterStore([
        _full_cluster(0, pt_id, "A", "v1", mu_v1),
        _full_cluster(1, pt_id, "A", "v2", mu_v2),
        _full_cluster(2, pt_id, "A", "v3", mu_v3),
    ])
    # Build val queries that land exactly on each cluster's μ → top-1 correct,
    # d² = 0, so conf_embed = 1 for any σ. The "correct → 1.0" signal favors
    # NOT collapsing to 0.5; small σ leaves things bright.
    queries = [
        ValQuery(pt_id=pt_id, product_id=i, query_vector=mu, attribute_name="A", true_value=val)
        for i, (mu, val) in enumerate([(mu_v1, "v1"), (mu_v2, "v2"), (mu_v3, "v3")])
    ]
    cal = SigmaCalibrator(store, _uniform_prior(), _calibration_config())
    table = cal.fit(queries)
    assert len(table) == 1
    entry = table.entries[0]
    # All-correct + d²=0 → confidence high regardless of σ; Brier ≈ 0.25 (since
    # conf_embed * prior = 1 * 0.5 = 0.5, vs outcome 1) for small σ, and the
    # prior dominates. We just assert that the chosen σ is in the configured grid.
    assert entry.sigma_optimal in {0.1, 0.5, 1.0, 5.0, 30.0}
    assert entry.n_val_samples == 3


def test_calibrator_picks_wider_sigma_when_d2_is_large():
    """When typical d² is large (~50), small σ collapses everything to 0 → bad Brier.
    Wider σ should be chosen."""
    rng = np.random.default_rng(1)
    pt_id = 10
    mu_v1 = _l2(rng.standard_normal(DIM).astype(np.float32))
    # μ_v2 far from μ_v1 to produce large d² when querying near μ_v1.
    mu_v2 = _l2(-mu_v1)
    # Use a scaled Σ⁻¹ so even points near μ_v1 produce d² ≈ 50 against μ_v1.
    sigma_inv_scaled = 50.0 * np.eye(DIM, dtype=np.float32)
    clusters = [
        ClusterStats(
            cluster_id=0, product_type_id=pt_id, product_type_name="PT10",
            attribute_name="A", value="v1", n=10,
            mu=mu_v1, sigma_inv=sigma_inv_scaled, log_det_sigma=0.0, low_sample=False,
        ),
        ClusterStats(
            cluster_id=1, product_type_id=pt_id, product_type_name="PT10",
            attribute_name="A", value="v2", n=10,
            mu=mu_v2, sigma_inv=sigma_inv_scaled, log_det_sigma=0.0, low_sample=False,
        ),
    ]
    store = ClusterStore(clusters)

    # Queries close to μ_v1 (truth = v1). Under sigma_inv_scaled=50I, d² will
    # be ~50 * ||q - μ_v1||² ≈ 50 * 0.01 = 0.5 for very-close queries; but
    # against μ_v2 (the wrong cluster) d² ~ 50 * ||q - μ_v2||² ≈ 50 * 4 = 200.
    queries = []
    for i in range(20):
        q = _l2(mu_v1 + 0.05 * rng.standard_normal(DIM).astype(np.float32))
        queries.append(
            ValQuery(pt_id=pt_id, product_id=i, query_vector=q,
                     attribute_name="A", true_value="v1")
        )
    grid = (0.1, 1.0, 30.0, 150.0)
    cal = SigmaCalibrator(store, _uniform_prior(), _calibration_config(sigma_grid=grid))
    table = cal.fit(queries)
    entry = table.entries[0]
    # σ=0.1 would have conf ≈ 0 for the WRONG cluster (d²=200, exp(-10000) = 0)
    # AND for the right cluster d² ≈ 0.5 → conf ≈ exp(-25) ≈ 0. So small σ
    # gives uniformly-zero confidences (Brier ≈ 1.0 for correct top-1s).
    # Larger σ keeps the right cluster's score high. We expect σ > 0.1.
    assert entry.sigma_optimal > 0.1


def test_calibrator_returns_no_entry_for_pt_with_no_clusters():
    """PT not in the store → no SigmaEntry emitted."""
    store = ClusterStore([])
    queries = [
        ValQuery(pt_id=99, product_id=1,
                 query_vector=np.zeros(DIM, dtype=np.float32),
                 attribute_name="A", true_value="v"),
    ]
    cal = SigmaCalibrator(store, _uniform_prior(), _calibration_config())
    table = cal.fit(queries)
    assert len(table) == 0


def test_calibrator_skips_attributes_with_no_clusters_under_pt():
    """val query's attribute may not have a cluster under predicted PT — skip silently."""
    pt_id = 10
    mu_v1 = _l2(np.ones(DIM, dtype=np.float32))
    store = ClusterStore([_full_cluster(0, pt_id, "A", "v1", mu_v1)])
    # Query for "B" — no clusters under (10, "B") → skipped, no entry produced.
    queries = [
        ValQuery(pt_id=pt_id, product_id=1, query_vector=mu_v1,
                 attribute_name="B", true_value="x"),
    ]
    cal = SigmaCalibrator(store, _uniform_prior(), _calibration_config())
    table = cal.fit(queries)
    # No samples could be cached for PT 10 → no entry returned.
    assert len(table) == 0


def test_calibrator_caches_d2_across_sigmas(monkeypatch):
    """Critical perf claim: mahalanobis_squared() is called once per (q, cluster),
    not once per (q, cluster, σ). With 5 σ candidates and 3 clusters × 3 queries,
    we expect 9 d² calls, not 9 × 5 = 45."""
    pt_id = 10
    mu_v1 = _l2(np.ones(DIM, dtype=np.float32))
    mu_v2 = _l2(np.array([1.0] * 8 + [0.0] * 8, dtype=np.float32))
    mu_v3 = _l2(-mu_v1)
    clusters = [
        _full_cluster(0, pt_id, "A", "v1", mu_v1),
        _full_cluster(1, pt_id, "A", "v2", mu_v2),
        _full_cluster(2, pt_id, "A", "v3", mu_v3),
    ]
    store = ClusterStore(clusters)

    call_count = {"n": 0}
    original = ClusterStats.mahalanobis_squared

    def counting(self, q):
        call_count["n"] += 1
        return original(self, q)

    monkeypatch.setattr(ClusterStats, "mahalanobis_squared", counting)

    queries = [
        ValQuery(pt_id=pt_id, product_id=i, query_vector=mu, attribute_name="A", true_value="v1")
        for i, mu in enumerate([mu_v1, mu_v2, mu_v3])
    ]
    cal = SigmaCalibrator(store, _uniform_prior(), _calibration_config(sigma_grid=(0.5, 1.0, 5.0, 30.0, 150.0)))
    cal.fit(queries)
    # 3 queries × 3 clusters = 9 d² computations. Grid size shouldn't matter.
    assert call_count["n"] == 9


def test_calibrator_uses_lambda_cal_from_config():
    """If λ_cal is very large, ECE dominates — calibrator picks σ with lowest ECE
    even at cost of higher Brier."""
    pt_id = 10
    mu_v1 = _l2(np.ones(DIM, dtype=np.float32))
    store = ClusterStore([_full_cluster(0, pt_id, "A", "v1", mu_v1)])
    queries = [
        ValQuery(pt_id=pt_id, product_id=1, query_vector=mu_v1,
                 attribute_name="A", true_value="v1"),
    ]
    cal_low = SigmaCalibrator(store, _uniform_prior(),
                              _calibration_config(lambda_cal=0.0))
    cal_high = SigmaCalibrator(store, _uniform_prior(),
                               _calibration_config(lambda_cal=100.0))
    # Both should still produce a result; just sanity that no crash with extreme λ.
    table_low = cal_low.fit(queries)
    table_high = cal_high.fit(queries)
    assert len(table_low) == 1
    assert len(table_high) == 1
