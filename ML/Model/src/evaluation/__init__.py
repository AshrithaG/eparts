"""M5 — evaluation framework.

Composes M3a + M3b + M3c + M4 into an end-to-end inference pipeline,
runs it over the M1 test split, and produces the spec §5.4 metric set
+ spec §5.5 visual artifacts.
"""

from .metrics import (
    AutoProcessStats,
    PerThresholdStats,
    auto_process_stats,
    brier_score,
    confusion_matrix_counts,
    expected_calibration_error,
    latency_percentiles,
    threshold_sweep,
    top_k_accuracy,
)
from .report import (
    EvaluationReport,
    FailureCase,
    PerPTMetrics,
    collect_failure_cases,
    confidence_histogram,
    write_report_bundle,
)
from .runner import InferenceOutput, InferencePipeline, InferenceTrace

__all__ = [
    "AutoProcessStats",
    "EvaluationReport",
    "FailureCase",
    "InferenceOutput",
    "InferencePipeline",
    "InferenceTrace",
    "PerPTMetrics",
    "PerThresholdStats",
    "auto_process_stats",
    "brier_score",
    "collect_failure_cases",
    "confidence_histogram",
    "confusion_matrix_counts",
    "expected_calibration_error",
    "latency_percentiles",
    "threshold_sweep",
    "top_k_accuracy",
    "write_report_bundle",
]
