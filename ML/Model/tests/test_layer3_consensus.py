"""Layer 3 [3c] ProductType consensus tests (V1 spec §4.3 [3c])."""
from __future__ import annotations

import pandas as pd
import pytest

from src.layer3_semantic.consensus import (
    ProductTypeIndex,
    build_pt_index_from_1b,
    compute_pt_consensus,
)
from src.layer3_semantic.index import SearchHit


@pytest.fixture
def pt_index() -> ProductTypeIndex:
    return ProductTypeIndex(
        pt_id_by_product={
            1001: 10, 1002: 10, 1003: 10,           # PT 10 = "Thermostats"
            1004: 20, 1005: 20,                     # PT 20 = "Actuators"
            1006: 30,                               # PT 30 = "Pressure Sensors"
        },
        pt_name_by_id={
            10: "Thermostats",
            20: "Actuators",
            30: "Pressure Sensors",
        },
    )


def _hit(pid: int, score: float) -> SearchHit:
    return SearchHit(product_id=pid, score=score)


def test_unanimous_top_k_gives_pt_conf_1(pt_index):
    """All 5 hits belong to PT 10 → pt_conf should be 1.0."""
    hits = [_hit(p, s) for p, s in [(1001, 0.95), (1002, 0.90), (1003, 0.85), (1001, 0.80), (1002, 0.75)]]
    pred = compute_pt_consensus(hits, pt_index)
    assert pred is not None
    assert pred.product_type_id == 10
    assert pred.product_type_name == "Thermostats"
    assert pred.pt_conf == pytest.approx(1.0)


def test_split_consensus_proportional_to_weighted_similarity(pt_index):
    """Three PT 10 votes (sum=2.4) vs two PT 20 votes (sum=1.6) → pt_conf = 0.6."""
    hits = [
        _hit(1001, 0.80), _hit(1002, 0.80), _hit(1003, 0.80),     # 2.4 toward PT 10
        _hit(1004, 0.80), _hit(1005, 0.80),                       # 1.6 toward PT 20
    ]
    pred = compute_pt_consensus(hits, pt_index)
    assert pred.product_type_id == 10
    assert pred.pt_conf == pytest.approx(2.4 / 4.0, abs=1e-6)


def test_ambiguous_band_below_0_60(pt_index):
    """Near-tie consensus drops pt_conf below 0.60 — Layer 4 will cap."""
    hits = [
        _hit(1001, 0.55), _hit(1004, 0.50), _hit(1006, 0.45),
    ]
    pred = compute_pt_consensus(hits, pt_index)
    assert pred.pt_conf == pytest.approx(0.55 / (0.55 + 0.50 + 0.45), abs=1e-6)
    assert pred.pt_conf < 0.60   # falls in the ambiguous band


def test_high_consensus_band_above_0_80(pt_index):
    """Strong majority for one PT gives pt_conf ≥ 0.80 → high-consensus band."""
    hits = [
        _hit(1001, 0.95), _hit(1002, 0.90), _hit(1003, 0.85), _hit(1004, 0.40),
    ]
    total = 0.95 + 0.90 + 0.85 + 0.40
    pred = compute_pt_consensus(hits, pt_index)
    assert pred.product_type_id == 10
    assert pred.pt_conf == pytest.approx((0.95 + 0.90 + 0.85) / total, abs=1e-6)
    assert pred.pt_conf >= 0.80


def test_negative_similarity_is_clamped_to_zero(pt_index):
    """Negative inner-product scores (rare on L2-norm vectors) get clamped."""
    hits = [_hit(1001, 0.80), _hit(1004, -0.50)]
    pred = compute_pt_consensus(hits, pt_index)
    # The -0.50 contributes 0 to PT 20's vote, so PT 10 wins with 100% share.
    assert pred.product_type_id == 10
    assert pred.pt_conf == pytest.approx(1.0)


def test_unknown_product_id_is_silently_skipped(pt_index):
    """Hits referencing IDs absent from the PT index are ignored, not crashed."""
    hits = [_hit(9999, 0.95), _hit(1001, 0.50)]
    pred = compute_pt_consensus(hits, pt_index)
    assert pred.product_type_id == 10
    assert pred.pt_conf == pytest.approx(1.0)


def test_top_k_override_restricts_vote(pt_index):
    """top_k=2 only consumes the first 2 hits."""
    hits = [
        _hit(1004, 0.99),                # only this one counted
        _hit(1005, 0.99),                # and this
        _hit(1001, 0.50), _hit(1002, 0.50), _hit(1003, 0.50),  # not counted
    ]
    pred = compute_pt_consensus(hits, pt_index, top_k=2)
    assert pred.product_type_id == 20
    assert pred.pt_conf == pytest.approx(1.0)


def test_empty_hits_returns_none(pt_index):
    assert compute_pt_consensus([], pt_index) is None


def test_all_unresolved_hits_returns_none(pt_index):
    """Every hit references an unknown product → no consensus possible."""
    hits = [_hit(7777, 0.9), _hit(8888, 0.8)]
    assert compute_pt_consensus(hits, pt_index) is None


def test_all_zero_or_negative_scores_returns_none(pt_index):
    """If every clamped weight is zero, the denominator would be 0 — bail."""
    hits = [_hit(1001, 0.0), _hit(1002, -0.1)]
    assert compute_pt_consensus(hits, pt_index) is None


def test_build_pt_index_from_1b():
    """Factory drops null PT rows and constructs the lookup map."""
    df = pd.DataFrame(
        {
            "Product_ID": [1, 2, 3, 4],
            "ProductType_ID": [10, 10, None, 20],
            "ProductType_Name": ["Thermostats", "Thermostats", "X", "Actuators"],
        }
    )
    idx = build_pt_index_from_1b(df)
    assert idx.size == 3
    assert idx.lookup(1) == (10, "Thermostats")
    assert idx.lookup(4) == (20, "Actuators")
    assert idx.lookup(3) is None     # null PT was dropped
    assert idx.lookup(999) is None   # never seen


def test_build_pt_index_rejects_missing_columns():
    df = pd.DataFrame({"Product_ID": [1], "ProductType_ID": [10]})
    with pytest.raises(ValueError):
        build_pt_index_from_1b(df)
