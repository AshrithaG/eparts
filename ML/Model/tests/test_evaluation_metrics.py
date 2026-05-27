"""M5 evaluation metric tests."""
from __future__ import annotations

import pytest

from src.evaluation.metrics import (
    auto_process_stats,
    confusion_matrix_counts,
    latency_percentiles,
    threshold_sweep,
    top_k_accuracy,
)


# ===========================================================================
# top_k_accuracy
# ===========================================================================


def test_top1_accuracy_all_correct():
    preds = [["a", "b", "c"], ["x", "y"], ["v"]]
    truths = ["a", "x", "v"]
    assert top_k_accuracy(preds, truths, k=1) == pytest.approx(1.0)


def test_top1_accuracy_all_wrong():
    preds = [["a", "b"], ["x"]]
    truths = ["z", "z"]
    assert top_k_accuracy(preds, truths, k=1) == pytest.approx(0.0)


def test_top3_picks_truth_at_position_2():
    preds = [["a", "b", "c"]]
    truths = ["c"]
    assert top_k_accuracy(preds, truths, k=1) == 0.0      # not in top-1
    assert top_k_accuracy(preds, truths, k=3) == 1.0      # in top-3


def test_top_k_normalizes_case_and_whitespace():
    preds = [["  Strap-On  "]]
    truths = ["STRAP-ON"]
    assert top_k_accuracy(preds, truths, k=1) == 1.0


def test_top_k_empty_input_returns_zero():
    assert top_k_accuracy([], [], k=3) == 0.0


def test_top_k_length_mismatch_raises():
    with pytest.raises(ValueError):
        top_k_accuracy([["a"]], ["a", "b"], k=1)


# ===========================================================================
# auto_process_stats
# ===========================================================================


def test_auto_process_below_threshold_yields_zero_coverage():
    stats = auto_process_stats([0.4, 0.5, 0.6], [1, 1, 0], threshold=0.85)
    assert stats.coverage == 0.0
    assert stats.precision == 0.0
    assert stats.n_auto == 0


def test_auto_process_above_threshold_computes_precision():
    # 3 of 4 above 0.85; 2 of those 3 are correct → precision = 2/3
    stats = auto_process_stats(
        [0.90, 0.95, 0.88, 0.4],
        [1, 0, 1, 1],
        threshold=0.85,
    )
    assert stats.n_auto == 3
    assert stats.coverage == pytest.approx(3 / 4)
    assert stats.precision == pytest.approx(2 / 3)


def test_auto_process_handles_empty_input():
    stats = auto_process_stats([], [], threshold=0.5)
    assert stats.coverage == 0.0
    assert stats.precision == 0.0


def test_auto_process_length_mismatch_raises():
    with pytest.raises(ValueError):
        auto_process_stats([0.9], [1, 0], threshold=0.5)


def test_threshold_sweep_returns_one_per_threshold():
    sweep = threshold_sweep(
        [0.1, 0.3, 0.5, 0.7, 0.9],
        [0, 0, 1, 1, 1],
        thresholds=[0.2, 0.4, 0.6, 0.8],
    )
    assert len(sweep.by_threshold) == 4
    # Coverage monotonically decreases with rising threshold.
    coverages = [s.coverage for s in sweep.by_threshold]
    assert coverages == sorted(coverages, reverse=True)


# ===========================================================================
# confusion_matrix_counts
# ===========================================================================


def test_confusion_keeps_top_n_attributes_by_sample_count():
    attrs = ["A"] * 10 + ["B"] * 5 + ["C"] * 1
    preds = ["x"] * 16
    truths = ["x"] * 16
    out = confusion_matrix_counts(attrs, preds, truths, top_n_attributes=2)
    assert set(out.keys()) == {"A", "B"}
    assert "C" not in out


def test_confusion_aggregates_pred_truth_pairs():
    attrs = ["A", "A", "A"]
    preds = ["x", "x", "y"]
    truths = ["x", "y", "y"]
    out = confusion_matrix_counts(attrs, preds, truths, top_n_attributes=1)
    bucket = out["A"]
    assert bucket[("x", "x")] == 1
    assert bucket[("x", "y")] == 1
    assert bucket[("y", "y")] == 1


def test_confusion_empty_input_returns_empty_dict():
    assert confusion_matrix_counts([], [], [], top_n_attributes=10) == {}


# ===========================================================================
# latency_percentiles
# ===========================================================================


def test_latency_percentiles_computes_default_quartet():
    out = latency_percentiles([10.0, 20.0, 30.0, 40.0, 50.0])
    assert set(out.keys()) == {"p50", "p90", "p95", "p99"}
    assert out["p50"] == pytest.approx(30.0)
    assert out["p99"] >= out["p95"] >= out["p90"]


def test_latency_percentiles_empty_input_returns_zeros():
    out = latency_percentiles([])
    assert all(v == 0.0 for v in out.values())
