"""Layer 3 [3d] scoring tests (V1 spec §4.3 [3d] + §7.2 M3c)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.contracts import ProductTypePrediction
from src.layer3_semantic.clusters import ClusterStats, ClusterStore
from src.layer3_semantic.scoring import (
    SemanticScorer,
    SemanticScorerConfig,
    UsagePrior,
    build_usage_prior_from_2a,
)


# ===========================================================================
# UsagePrior — formula correctness
# ===========================================================================


def _prior(uc: dict[tuple[str, str], int], maxc: dict[str, int]) -> UsagePrior:
    return UsagePrior(counts=uc, max_counts=maxc)


def test_zero_count_yields_neutral_prior():
    """UC = 0 → prior should be exactly 0.5 (the neutral midpoint)."""
    p = _prior({("input_voltage", "24"): 0}, {"input_voltage": 1000})
    assert p.prior("INPUT_VOLTAGE", "24") == pytest.approx(0.5)


def test_max_count_yields_top_prior():
    """When (A, v) has the max UC under A, prior should equal 1.0."""
    p = _prior({("input_voltage", "24"): 1000}, {"input_voltage": 1000})
    assert p.prior("INPUT_VOLTAGE", "24") == pytest.approx(1.0)


def test_intermediate_count_falls_in_band():
    """Half the log-max usage → prior strictly between 0.5 and 1.0."""
    max_uc = 1000
    half_log = math.log1p(max_uc) / 2.0
    mid_uc = int(round(math.expm1(half_log)))
    p = _prior({("a", "v"): mid_uc}, {"a": max_uc})
    val = p.prior("A", "v")
    assert 0.5 < val < 1.0
    # By construction prior(mid) ≈ 0.75 (50% of the way through the half-range).
    # Allow ~0.01 tolerance for the integer-rounding of mid_uc.
    assert val == pytest.approx(0.75, abs=0.01)


def test_unknown_attribute_returns_neutral():
    """Asking about an attribute not in 2A returns 0.5."""
    p = _prior({}, {})
    assert p.prior("MYSTERY_ATTR", "anything") == 0.5


def test_zero_max_count_returns_neutral_for_all_values():
    """If every UC under an attribute is 0, the formula's denominator is 0."""
    p = _prior({("a", "v1"): 0, ("a", "v2"): 0}, {"a": 0})
    assert p.prior("A", "v1") == 0.5
    assert p.prior("A", "v2") == 0.5


def test_case_and_whitespace_insensitive():
    """Lookup keys are normalized — casing/whitespace shouldn't matter."""
    p = _prior({("input_voltage", "24"): 50}, {"input_voltage": 100})
    a = p.prior("  Input_Voltage  ", "24")
    b = p.prior("INPUT_VOLTAGE", " 24")
    assert a == pytest.approx(b)


def test_count_lookup_exposes_raw_value():
    p = _prior({("a", "v"): 42}, {"a": 42})
    assert p.count("A", "v") == 42
    assert p.count("A", "missing") == 0
    assert p.max_count("A") == 42


def test_build_from_2a_aggregates_correctly():
    df = pd.DataFrame(
        {
            "Attribute_Name": ["A", "A", "B", "B"],
            "Value": ["v1", "v2", "v3", "v4"],
            "Usage_Count": [10, 50, 200, 200],
        }
    )
    p = build_usage_prior_from_2a(df)
    assert p.count("A", "v1") == 10
    assert p.count("A", "v2") == 50
    assert p.max_count("A") == 50
    assert p.max_count("B") == 200
    assert p.prior("A", "v2") == pytest.approx(1.0)
    assert p.prior("B", "v3") == pytest.approx(1.0)


def test_build_from_2a_rejects_missing_columns():
    df = pd.DataFrame({"Attribute_Name": ["A"], "Value": ["v"]})        # no Usage_Count
    with pytest.raises(ValueError):
        build_usage_prior_from_2a(df)


def test_build_from_2a_drops_null_rows():
    df = pd.DataFrame(
        {
            "Attribute_Name": ["A", None, "A"],
            "Value": ["v1", "v2", None],
            "Usage_Count": [5, 10, 15],
        }
    )
    p = build_usage_prior_from_2a(df)
    assert p.max_count("A") == 5      # only the (A, v1, 5) row survived


# ===========================================================================
# SemanticScorer — top-3 + invariants + low-sample propagation
# ===========================================================================


DIM = 16


def _mu(d: int, seed: int) -> np.ndarray:
    """Deterministic L2-normalized DIM-d vector."""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(d).astype(np.float32)
    v /= np.linalg.norm(v)
    return v


def _identity_inv(d: int) -> np.ndarray:
    return np.eye(d, dtype=np.float32)


def _cluster(
    cid: int, pt_id: int, attr: str, val: str, mu: np.ndarray, n: int = 10,
    low_sample: bool = False, sigma_inv: np.ndarray | None = None,
) -> ClusterStats:
    if low_sample:
        sigma_inv = None
    elif sigma_inv is None:
        sigma_inv = _identity_inv(len(mu))
    return ClusterStats(
        cluster_id=cid,
        product_type_id=pt_id,
        product_type_name=f"PT{pt_id}",
        attribute_name=attr,
        value=val,
        n=n,
        mu=mu.astype(np.float32),
        sigma_inv=sigma_inv,
        log_det_sigma=0.0,
        low_sample=low_sample,
    )


@pytest.fixture
def store_with_two_pts():
    """ClusterStore with PT=10 (one attribute, 5 values) and PT=20 (untouched)."""
    pt = 10
    attr = "INPUT_VOLTAGE"
    stats = [
        _cluster(i, pt, attr, f"v{i}", _mu(DIM, seed=i + 100))
        for i in range(5)
    ]
    # Decoy PT to verify scope isolation
    stats.append(_cluster(99, 20, "MOUNTING", "STRAP-ON", _mu(DIM, seed=999)))
    return ClusterStore(stats)


@pytest.fixture
def usage_prior_uniform():
    # Same count for all (A, v) → prior is constant ≈ log(1+UC)/log(1+max)·0.5 + 0.5
    counts = {("input_voltage", f"v{i}"): 10 for i in range(5)}
    counts[("mounting", "strap-on")] = 10
    return UsagePrior(
        counts=counts,
        max_counts={"input_voltage": 100, "mounting": 100},
    )


@pytest.fixture
def scorer(store_with_two_pts, usage_prior_uniform):
    return SemanticScorer(store_with_two_pts, usage_prior_uniform)


def _pt_pred(pt_id: int, conf: float = 0.9) -> ProductTypePrediction:
    return ProductTypePrediction(
        product_type_id=pt_id,
        product_type_name=f"PT{pt_id}",
        pt_conf=conf,
    )


# -------- behavior --------------------------------------------------------


def test_returns_one_hit_per_attribute(scorer):
    q = _mu(DIM, seed=42)
    result = scorer.score(q, _pt_pred(10))
    assert len(result.hits) == 1
    assert result.hits[0].attribute_name == "INPUT_VOLTAGE"


def test_top_n_per_attribute_defaults_to_three(scorer):
    """Spec §4.3 [3d] says 'top 3 values per attribute'."""
    q = _mu(DIM, seed=42)
    result = scorer.score(q, _pt_pred(10))
    assert len(result.hits[0].top_candidates) == 3


def test_top_n_can_be_overridden(store_with_two_pts, usage_prior_uniform):
    cfg = SemanticScorerConfig(top_n_per_attribute=5)
    s = SemanticScorer(store_with_two_pts, usage_prior_uniform, config=cfg)
    result = s.score(_mu(DIM, seed=42), _pt_pred(10))
    assert len(result.hits[0].top_candidates) == 5


def test_candidates_sorted_descending_by_conf_embed_final(scorer):
    """Returned top candidates must be in descending confidence order."""
    result = scorer.score(_mu(DIM, seed=42), _pt_pred(10))
    confs = [c.conf_embed_final for c in result.hits[0].top_candidates]
    assert confs == sorted(confs, reverse=True)


def test_scope_is_restricted_to_predicted_pt(scorer):
    """A query under PT=10 must NOT return MOUNTING hits (which live under PT=20)."""
    result = scorer.score(_mu(DIM, seed=42), _pt_pred(10))
    attribute_names = {h.attribute_name for h in result.hits}
    assert "MOUNTING" not in attribute_names


def test_pt_with_no_clusters_returns_empty_hits(scorer):
    """A PT with zero registered clusters should produce empty hits, not crash."""
    result = scorer.score(_mu(DIM, seed=42), _pt_pred(99999))   # unknown PT
    assert result.hits == ()
    assert result.product_type.product_type_id == 99999


# -------- math / invariants -----------------------------------------------


def test_query_at_cluster_mu_scores_one(store_with_two_pts, usage_prior_uniform):
    """D² = 0 when q = μ → conf_embed = exp(0) = 1.0."""
    # Custom store: one cluster, identity Σ⁻¹, σ=1.0
    mu = _mu(DIM, seed=7)
    store = ClusterStore([_cluster(0, 10, "A", "v", mu)])
    s = SemanticScorer(store, UsagePrior(counts={("a", "v"): 50}, max_counts={"a": 50}))
    result = s.score(mu, _pt_pred(10))
    candidate = result.hits[0].top_candidates[0]
    assert candidate.conf_embed == pytest.approx(1.0, abs=1e-6)
    assert candidate.mahalanobis_d2 == pytest.approx(0.0, abs=1e-6)


def test_all_scores_in_unit_interval(scorer):
    """conf_embed and conf_embed_final must be in [0, 1] for every candidate."""
    q = _mu(DIM, seed=42)
    result = scorer.score(q, _pt_pred(10))
    for h in result.hits:
        for c in h.top_candidates:
            assert 0.0 <= c.conf_embed <= 1.0
            assert 0.0 <= c.conf_embed_final <= 1.0


def test_conf_embed_final_never_exceeds_usage_prior(scorer, usage_prior_uniform):
    """Spec §7.2 M3c property: conf_embed_final ≤ usage_prior(A, v)."""
    q = _mu(DIM, seed=42)
    result = scorer.score(q, _pt_pred(10))
    for h in result.hits:
        prior = usage_prior_uniform.prior(h.attribute_name, h.top_candidates[0].value)
        for c in h.top_candidates:
            # Since conf_embed ∈ [0, 1], conf_embed_final = conf_embed * prior ≤ prior.
            current_prior = usage_prior_uniform.prior(h.attribute_name, c.value)
            assert c.conf_embed_final <= current_prior + 1e-9


def test_low_sample_flag_propagates(usage_prior_uniform):
    """A low-sample cluster's flag must surface on the SemanticCandidate."""
    mu = _mu(DIM, seed=11)
    store = ClusterStore(
        [
            _cluster(0, 10, "A", "v1", mu, low_sample=False),
            _cluster(1, 10, "A", "v2", _mu(DIM, seed=12), n=3, low_sample=True),
        ]
    )
    s = SemanticScorer(store, usage_prior_uniform)
    result = s.score(mu, _pt_pred(10))
    candidates_by_value = {c.value: c for c in result.hits[0].top_candidates}
    assert candidates_by_value["v1"].low_sample is False
    assert candidates_by_value["v2"].low_sample is True


def test_sigma_override_changes_scoring(store_with_two_pts, usage_prior_uniform):
    """Larger σ → flatter Gaussian → conf_embed closer to 1.0 for far-away queries."""
    s = SemanticScorer(store_with_two_pts, usage_prior_uniform)
    q = _mu(DIM, seed=42)
    with_default = s.score(q, _pt_pred(10))
    s.set_sigma_by_pt({10: 100.0})    # very wide
    with_wide = s.score(q, _pt_pred(10))
    # Every candidate gets a higher conf_embed under the wider σ.
    for default_c, wide_c in zip(
        with_default.hits[0].top_candidates,
        with_wide.hits[0].top_candidates,
        strict=False,
    ):
        if default_c.value == wide_c.value:
            assert wide_c.conf_embed >= default_c.conf_embed


def test_sigma_missing_pt_falls_back_to_default(store_with_two_pts, usage_prior_uniform):
    cfg = SemanticScorerConfig(default_sigma=2.0)
    s = SemanticScorer(store_with_two_pts, usage_prior_uniform, config=cfg)
    assert s.sigma_for(10) == 2.0       # uncalibrated → default
    s.set_sigma_by_pt({10: 0.5})
    assert s.sigma_for(10) == 0.5
    assert s.sigma_for(999) == 2.0     # still falls back


def test_usage_count_attached_to_candidate(usage_prior_uniform):
    """Every SemanticCandidate exposes the raw Usage_Count from 2A."""
    mu = _mu(DIM, seed=3)
    store = ClusterStore([_cluster(0, 10, "INPUT_VOLTAGE", "v0", mu)])
    counts = {("input_voltage", "v0"): 42}
    s = SemanticScorer(
        store,
        UsagePrior(counts=counts, max_counts={"input_voltage": 100}),
    )
    result = s.score(mu, _pt_pred(10))
    assert result.hits[0].top_candidates[0].usage_count == 42
