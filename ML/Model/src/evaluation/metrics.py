"""M5 — evaluation metrics.

Implements V1_Engineering_Spec §5.4. Re-uses the Brier + ECE helpers
from :mod:`src.layer4_decision.calibration` so the calibration loss
and the evaluation loss are computed identically.

All functions accept aligned sequences and return scalar floats.
Empty input returns 0.0 (NaN-safe).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

# Re-export the Brier/ECE helpers from calibration so importers can
# reach both via :mod:`src.evaluation.metrics`.
from ..layer4_decision.calibration import (
    brier_score,
    expected_calibration_error,
)


__all__ = [
    "AutoProcessStats",
    "PerThresholdStats",
    "brier_score",                            # re-exported
    "expected_calibration_error",             # re-exported
    "top_k_accuracy",
    "auto_process_stats",
    "threshold_sweep",
    "confusion_matrix_counts",
    "latency_percentiles",
]


# ---------------------------------------------------------------------------
# Top-K accuracy
# ---------------------------------------------------------------------------


def top_k_accuracy(
    predicted_ranked_lists: Sequence[Sequence[str]],
    true_values: Sequence[str],
    k: int,
) -> float:
    """Return the fraction of queries whose true value sits in the top-k.

    Args:
        predicted_ranked_lists: One ranked list of predicted values per
            query. Higher rank = position 0.
        true_values: One ground-truth value per query, aligned with
            ``predicted_ranked_lists``.
        k: How far into the ranked list to look.

    Returns:
        Accuracy in ``[0, 1]``. ``0.0`` for empty input.
    """
    if not true_values:
        return 0.0
    if len(predicted_ranked_lists) != len(true_values):
        raise ValueError(
            f"length mismatch: predictions={len(predicted_ranked_lists)} "
            f"truths={len(true_values)}"
        )
    hits = 0
    for ranked, truth in zip(predicted_ranked_lists, true_values, strict=True):
        truth_norm = _norm(truth)
        if any(_norm(v) == truth_norm for v in ranked[:k]):
            hits += 1
    return hits / len(true_values)


# ---------------------------------------------------------------------------
# Auto-process precision + coverage (spec §5.4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AutoProcessStats:
    """Auto-process metrics at one decision threshold (spec §5.4)."""

    threshold: float
    coverage: float                # fraction of inputs with conf_final >= threshold
    precision: float               # accuracy among auto-processed
    n_total: int
    n_auto: int
    n_correct_among_auto: int


def auto_process_stats(
    confidences: Sequence[float],
    outcomes: Sequence[int],
    threshold: float = 0.85,
) -> AutoProcessStats:
    """Compute auto-process precision + coverage at a fixed threshold.

    Args:
        confidences: One ``conf_final`` per (query, attribute) sample.
        outcomes: Aligned ``1`` if the top-1 prediction matched truth
            else ``0``.
        threshold: Decision threshold (spec §1.3 default: 0.85).

    Returns:
        :class:`AutoProcessStats`. Precision is 0.0 when coverage is 0.
    """
    if not confidences:
        return AutoProcessStats(threshold, 0.0, 0.0, 0, 0, 0)
    if len(confidences) != len(outcomes):
        raise ValueError(
            f"length mismatch: confidences={len(confidences)} outcomes={len(outcomes)}"
        )
    n_total = len(confidences)
    conf = np.asarray(confidences, dtype=np.float64)
    out = np.asarray(outcomes, dtype=np.int64)
    mask = conf >= threshold
    n_auto = int(mask.sum())
    if n_auto == 0:
        return AutoProcessStats(threshold, 0.0, 0.0, n_total, 0, 0)
    n_correct = int(out[mask].sum())
    return AutoProcessStats(
        threshold=float(threshold),
        coverage=n_auto / n_total,
        precision=n_correct / n_auto,
        n_total=n_total,
        n_auto=n_auto,
        n_correct_among_auto=n_correct,
    )


# ---------------------------------------------------------------------------
# Threshold sensitivity sweep (diagnostic — not a spec metric)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PerThresholdStats:
    """Auto-process metrics at multiple thresholds for diagnostic comparison."""

    by_threshold: tuple[AutoProcessStats, ...]


def threshold_sweep(
    confidences: Sequence[float],
    outcomes: Sequence[int],
    thresholds: Iterable[float],
) -> PerThresholdStats:
    """Evaluate :func:`auto_process_stats` over a grid of thresholds.

    Useful as a diagnostic — for semantic-only evaluation where
    ``conf_final`` is bounded above by ``1 − α = 0.3``, the spec's
    0.85 target is unreachable but lower thresholds expose the model's
    actual coverage / precision trade-off.
    """
    out = tuple(
        auto_process_stats(confidences, outcomes, t) for t in thresholds
    )
    return PerThresholdStats(by_threshold=out)


# ---------------------------------------------------------------------------
# Top-10 attribute confusion matrix (spec §5.5)
# ---------------------------------------------------------------------------


def confusion_matrix_counts(
    attribute_names: Sequence[str],
    predictions: Sequence[str],
    truths: Sequence[str],
    top_n_attributes: int = 10,
) -> dict[str, dict[tuple[str, str], int]]:
    """Per-attribute (predicted_value, true_value) → count.

    Returned dict is keyed by attribute name (only the ``top_n_attributes``
    most-frequent attributes by sample count are included). Within each
    attribute, the inner dict maps ``(predicted, true)`` tuples to
    counts. Suitable for downstream heatmap generation.

    Args:
        attribute_names: One attribute per (query, attribute) sample.
        predictions: Aligned predicted top-1 value.
        truths: Aligned ground-truth value.
        top_n_attributes: Keep only the most-sampled attributes.

    Returns:
        ``{attribute_name → {(predicted, true) → count}}``
    """
    if not attribute_names:
        return {}
    attr_counts = Counter(attribute_names)
    top_attrs = {a for a, _ in attr_counts.most_common(top_n_attributes)}
    out: dict[str, dict[tuple[str, str], int]] = {}
    for attr, pred, truth in zip(attribute_names, predictions, truths, strict=True):
        if attr not in top_attrs:
            continue
        bucket = out.setdefault(attr, {})
        key = (str(pred), str(truth))
        bucket[key] = bucket.get(key, 0) + 1
    return out


# ---------------------------------------------------------------------------
# Latency
# ---------------------------------------------------------------------------


def latency_percentiles(
    latencies_ms: Sequence[float],
    percentiles: Sequence[float] = (50.0, 90.0, 95.0, 99.0),
) -> dict[str, float]:
    """Return percentile latencies as a ``{"p50": ms, ...}`` dict."""
    if not latencies_ms:
        return {f"p{int(p)}": 0.0 for p in percentiles}
    arr = np.asarray(latencies_ms, dtype=np.float64)
    return {f"p{int(p)}": float(np.percentile(arr, p)) for p in percentiles}


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _norm(s: str) -> str:
    """Same normalization the cluster store uses — case + whitespace folded."""
    return " ".join(str(s or "").strip().lower().split())
