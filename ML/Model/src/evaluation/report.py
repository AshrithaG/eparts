"""M5 — evaluation report assembly + serialization.

Bundles all metric outputs from one M5 run into:

    metrics.json         Headline scalars (top-k acc, PT acc, ECE, latency)
    per_pt_metrics.csv   Per-ProductType top-1/top-3 acc, ECE, n_samples
    confusion_top10.csv  Top-10 attribute confusion (predicted, true) → count
    failure_cases.csv    Top-N lowest-conf correct + top-N highest-conf wrong
    latency_per_query.csv  One row per query with per-phase ms
    confidence_dist.csv  Histogram bins for the spec §5.5 confidence-drift signal

Visual artifacts (reliability diagrams, latency histogram PNGs) are
emitted by :mod:`.plots` from these CSVs.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from .metrics import AutoProcessStats, PerThresholdStats


@dataclass(frozen=True, slots=True)
class PerPTMetrics:
    """Per-ProductType metric row (spec §5.4 broken down per PT)."""

    pt_id: int
    pt_name: str
    n_samples: int
    top1_accuracy: float
    top3_accuracy: float
    ece: float
    brier: float


@dataclass(frozen=True, slots=True)
class FailureCase:
    """One row of the spec §5.5 failure-case table.

    Two flavors:
      * highest-confidence MISS (model was sure but wrong)
      * lowest-confidence HIT (model was unsure but right)
    """

    rank: int
    kind: str                                       # "high_conf_miss" | "low_conf_hit"
    product_id: int
    attribute_name: str
    true_value: str
    predicted_value: str
    conf_final: float
    pt_id: int
    pt_name: str


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    """Top-level evaluation bundle for one M5 run."""

    run_id: str
    model_version: str
    n_queries_evaluated: int
    n_attribute_samples: int

    # Headline metrics (spec §5.4)
    pt_accuracy_overall: float
    attribute_top1_overall: float
    attribute_top3_overall: float
    ece_overall: float
    brier_overall: float

    # Auto-process @ spec threshold
    auto_process_at_0_85: AutoProcessStats
    threshold_sweep_diagnostic: PerThresholdStats

    # Latency
    latency_percentiles_ms: Mapping[str, float]
    latency_target_p50_ms: float = 50.0
    latency_target_p95_ms: float = 200.0

    # Per-PT breakdown
    per_pt_metrics: tuple[PerPTMetrics, ...] = field(default_factory=tuple)

    # Targets met flags (spec §1.3 / §7.2 M5)
    targets_met: Mapping[str, bool] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # JSON serialization for metrics.json
    # ------------------------------------------------------------------

    def to_metrics_json(self) -> dict:
        return {
            "run_id": self.run_id,
            "model_version": self.model_version,
            "n_queries_evaluated": self.n_queries_evaluated,
            "n_attribute_samples": self.n_attribute_samples,
            "metrics": {
                "pt_accuracy_overall": round(self.pt_accuracy_overall, 4),
                "attribute_top1_overall": round(self.attribute_top1_overall, 4),
                "attribute_top3_overall": round(self.attribute_top3_overall, 4),
                "ece_overall": round(self.ece_overall, 4),
                "brier_overall": round(self.brier_overall, 4),
            },
            "auto_process_at_0_85": asdict(self.auto_process_at_0_85),
            "threshold_sweep_diagnostic": {
                "by_threshold": [asdict(s) for s in self.threshold_sweep_diagnostic.by_threshold],
            },
            "latency_ms": dict(self.latency_percentiles_ms),
            "latency_targets": {
                "p50_ms": self.latency_target_p50_ms,
                "p95_ms": self.latency_target_p95_ms,
            },
            "targets_met": dict(self.targets_met),
        }


# ---------------------------------------------------------------------------
# Persistence helpers — write the full bundle to a run directory
# ---------------------------------------------------------------------------


def write_report_bundle(
    out_dir: Path,
    report: EvaluationReport,
    *,
    confusion: Mapping[str, Mapping[tuple[str, str], int]] | None = None,
    failure_cases: Sequence[FailureCase] | None = None,
    latency_per_query: Sequence[Mapping[str, float]] | None = None,
    confidence_histogram_bins: Sequence[tuple[float, float, int]] | None = None,
) -> None:
    """Serialize every part of the M5 bundle to ``out_dir``.

    The argument set is wide on purpose — every spec §5.5 visual
    artifact has a corresponding optional argument here. ``None``
    arguments mean "skip that file". The :func:`metrics.json` is
    always written.

    Args:
        out_dir: Destination directory. Created if missing.
        report: Top-level :class:`EvaluationReport`.
        confusion: Top-10 attribute confusion matrix counts.
        failure_cases: List of :class:`FailureCase` rows.
        latency_per_query: One ``{"phase": ms, ...}`` dict per query.
        confidence_histogram_bins: List of ``(lo, hi, count)`` bins.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # metrics.json — always
    (out_dir / "metrics.json").write_text(
        json.dumps(report.to_metrics_json(), indent=2),
        encoding="utf-8",
    )

    # Per-PT CSV
    if report.per_pt_metrics:
        pd.DataFrame(
            [asdict(m) for m in report.per_pt_metrics]
        ).to_csv(out_dir / "per_pt_metrics.csv", index=False)

    # Confusion CSV (long-format: attribute, predicted, true, count)
    if confusion:
        rows = []
        for attr, counts in confusion.items():
            for (pred, truth), n in counts.items():
                rows.append(
                    {"attribute_name": attr, "predicted": pred, "true": truth, "count": n}
                )
        pd.DataFrame(rows).to_csv(out_dir / "confusion_top10.csv", index=False)

    # Failure cases CSV
    if failure_cases:
        pd.DataFrame([asdict(f) for f in failure_cases]).to_csv(
            out_dir / "failure_cases.csv", index=False
        )

    # Per-query latency CSV
    if latency_per_query:
        pd.DataFrame(list(latency_per_query)).to_csv(
            out_dir / "latency_per_query.csv", index=False
        )

    # Confidence histogram CSV
    if confidence_histogram_bins:
        pd.DataFrame(
            list(confidence_histogram_bins),
            columns=["bin_lo", "bin_hi", "count"],
        ).to_csv(out_dir / "confidence_dist.csv", index=False)


# ---------------------------------------------------------------------------
# Helpers for assembling failure cases + histograms
# ---------------------------------------------------------------------------


def collect_failure_cases(
    *,
    product_ids: Sequence[int],
    pt_ids: Sequence[int],
    pt_names: Sequence[str],
    attribute_names: Sequence[str],
    true_values: Sequence[str],
    predicted_values: Sequence[str],
    confidences: Sequence[float],
    outcomes: Sequence[int],
    top_n: int = 20,
) -> tuple[FailureCase, ...]:
    """Pick top-N highest-conf misses + top-N lowest-conf hits."""
    if not product_ids:
        return ()
    n = len(product_ids)
    conf = np.asarray(confidences, dtype=np.float64)
    out_arr = np.asarray(outcomes, dtype=np.int64)
    miss_mask = out_arr == 0
    hit_mask = out_arr == 1

    miss_idx = np.where(miss_mask)[0]
    hit_idx = np.where(hit_mask)[0]

    # Sort misses by descending conf (most confident wrong predictions first).
    miss_idx = miss_idx[np.argsort(-conf[miss_idx])][:top_n]
    # Sort hits by ascending conf (least confident correct predictions first).
    hit_idx = hit_idx[np.argsort(conf[hit_idx])][:top_n]

    cases: list[FailureCase] = []
    for rank, i in enumerate(miss_idx, start=1):
        cases.append(
            FailureCase(
                rank=rank,
                kind="high_conf_miss",
                product_id=int(product_ids[i]),
                attribute_name=str(attribute_names[i]),
                true_value=str(true_values[i]),
                predicted_value=str(predicted_values[i]),
                conf_final=float(conf[i]),
                pt_id=int(pt_ids[i]),
                pt_name=str(pt_names[i]),
            )
        )
    for rank, i in enumerate(hit_idx, start=1):
        cases.append(
            FailureCase(
                rank=rank,
                kind="low_conf_hit",
                product_id=int(product_ids[i]),
                attribute_name=str(attribute_names[i]),
                true_value=str(true_values[i]),
                predicted_value=str(predicted_values[i]),
                conf_final=float(conf[i]),
                pt_id=int(pt_ids[i]),
                pt_name=str(pt_names[i]),
            )
        )
    return tuple(cases)


def confidence_histogram(
    confidences: Sequence[float],
    n_bins: int = 20,
    bin_range: tuple[float, float] = (0.0, 1.0),
) -> tuple[tuple[float, float, int], ...]:
    """Return ``(lo, hi, count)`` bin tuples for the confidence histogram."""
    if not confidences:
        return ()
    arr = np.asarray(confidences, dtype=np.float64)
    edges = np.linspace(bin_range[0], bin_range[1], n_bins + 1)
    counts, _ = np.histogram(arr, bins=edges)
    return tuple(
        (float(edges[i]), float(edges[i + 1]), int(counts[i])) for i in range(n_bins)
    )
