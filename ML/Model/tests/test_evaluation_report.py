"""M5 report assembly + serialization tests."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.evaluation.metrics import auto_process_stats, threshold_sweep
from src.evaluation.report import (
    EvaluationReport,
    FailureCase,
    PerPTMetrics,
    collect_failure_cases,
    confidence_histogram,
    write_report_bundle,
)


def _toy_report() -> EvaluationReport:
    auto = auto_process_stats([0.9, 0.95, 0.4], [1, 0, 1], threshold=0.85)
    sweep = threshold_sweep([0.9, 0.95, 0.4], [1, 0, 1], thresholds=[0.5, 0.8, 0.85])
    return EvaluationReport(
        run_id="run_20260519_120000",
        model_version="run_20260518_193055",
        n_queries_evaluated=10,
        n_attribute_samples=42,
        pt_accuracy_overall=0.92,
        attribute_top1_overall=0.86,
        attribute_top3_overall=0.95,
        ece_overall=0.04,
        brier_overall=0.18,
        auto_process_at_0_85=auto,
        threshold_sweep_diagnostic=sweep,
        latency_percentiles_ms={"p50": 15.0, "p95": 30.0},
        per_pt_metrics=(
            PerPTMetrics(pt_id=10, pt_name="Thermostats", n_samples=20,
                         top1_accuracy=0.9, top3_accuracy=0.98, ece=0.03, brier=0.1),
            PerPTMetrics(pt_id=20, pt_name="Actuators", n_samples=15,
                         top1_accuracy=0.83, top3_accuracy=0.93, ece=0.05, brier=0.2),
        ),
        targets_met={"pt_accuracy": True, "top1": True, "ece": True},
    )


def test_metrics_json_serialization_roundtrips_through_disk(tmp_path):
    report = _toy_report()
    write_report_bundle(tmp_path, report)
    payload = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))
    assert payload["run_id"] == "run_20260519_120000"
    assert payload["metrics"]["pt_accuracy_overall"] == 0.92
    assert payload["auto_process_at_0_85"]["threshold"] == 0.85
    assert payload["targets_met"]["pt_accuracy"] is True


def test_per_pt_csv_written_when_data_present(tmp_path):
    report = _toy_report()
    write_report_bundle(tmp_path, report)
    df = pd.read_csv(tmp_path / "per_pt_metrics.csv")
    assert len(df) == 2
    assert "top1_accuracy" in df.columns
    assert set(df["pt_name"]) == {"Thermostats", "Actuators"}


def test_confusion_csv_written_in_long_format(tmp_path):
    confusion = {
        "INPUT_VOLTAGE": {("24", "24"): 5, ("120", "24"): 1},
        "MOUNTING": {("STRAP-ON", "STRAP-ON"): 8},
    }
    write_report_bundle(tmp_path, _toy_report(), confusion=confusion)
    df = pd.read_csv(tmp_path / "confusion_top10.csv")
    assert set(df.columns) == {"attribute_name", "predicted", "true", "count"}
    assert df["count"].sum() == 14


def test_failure_cases_csv_written(tmp_path):
    cases = (
        FailureCase(
            rank=1, kind="high_conf_miss", product_id=1, attribute_name="A",
            true_value="x", predicted_value="y", conf_final=0.95, pt_id=10, pt_name="PT10",
        ),
    )
    write_report_bundle(tmp_path, _toy_report(), failure_cases=cases)
    df = pd.read_csv(tmp_path / "failure_cases.csv")
    assert len(df) == 1
    assert df["kind"].iloc[0] == "high_conf_miss"


def test_latency_per_query_csv_written(tmp_path):
    latency = [
        {"encode_ms": 15.0, "search_ms": 1.0, "score_ms": 5.0, "total_ms": 21.0},
        {"encode_ms": 14.0, "search_ms": 1.2, "score_ms": 6.0, "total_ms": 21.2},
    ]
    write_report_bundle(tmp_path, _toy_report(), latency_per_query=latency)
    df = pd.read_csv(tmp_path / "latency_per_query.csv")
    assert len(df) == 2
    assert df["total_ms"].iloc[0] == 21.0


def test_confidence_histogram_csv_written(tmp_path):
    bins = ((0.0, 0.1, 5), (0.1, 0.2, 12))
    write_report_bundle(tmp_path, _toy_report(), confidence_histogram_bins=bins)
    df = pd.read_csv(tmp_path / "confidence_dist.csv")
    assert set(df.columns) == {"bin_lo", "bin_hi", "count"}
    assert df["count"].sum() == 17


# ===========================================================================
# collect_failure_cases
# ===========================================================================


def test_failure_cases_picks_top_n_misses_and_hits():
    cases = collect_failure_cases(
        product_ids=[1, 2, 3, 4, 5, 6],
        pt_ids=[10] * 6, pt_names=["PT10"] * 6,
        attribute_names=["A"] * 6,
        true_values=["x"] * 6,
        predicted_values=["x", "y", "x", "y", "x", "y"],
        confidences=[0.95, 0.90, 0.5, 0.85, 0.3, 0.80],
        outcomes=[1, 0, 1, 0, 1, 0],
        top_n=2,
    )
    high_conf_miss = [c for c in cases if c.kind == "high_conf_miss"]
    low_conf_hit = [c for c in cases if c.kind == "low_conf_hit"]
    assert len(high_conf_miss) == 2
    assert len(low_conf_hit) == 2
    # Most confident wrong predictions first.
    assert high_conf_miss[0].conf_final >= high_conf_miss[1].conf_final
    # Least confident correct predictions first.
    assert low_conf_hit[0].conf_final <= low_conf_hit[1].conf_final


def test_failure_cases_empty_input_returns_empty():
    cases = collect_failure_cases(
        product_ids=[], pt_ids=[], pt_names=[],
        attribute_names=[], true_values=[], predicted_values=[],
        confidences=[], outcomes=[],
    )
    assert cases == ()


# ===========================================================================
# confidence_histogram
# ===========================================================================


def test_confidence_histogram_returns_n_bins_tuples():
    bins = confidence_histogram([0.05, 0.15, 0.25, 0.85, 0.95], n_bins=10)
    assert len(bins) == 10
    total = sum(b[2] for b in bins)
    assert total == 5


def test_confidence_histogram_empty_input():
    assert confidence_histogram([]) == ()
