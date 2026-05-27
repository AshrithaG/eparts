"""M5 — matplotlib visualizations for spec §5.5 artifacts.

Reads the CSV / inline data emitted by :mod:`.report` and produces:

  * reliability_<pt_name>.png   per head ProductType (spec §5.5)
  * confusion_top10.png         heatmap of top-10 attribute confusion
  * latency_histogram.png       distribution of per-query total latency
  * confidence_distribution.png conf_final histogram (drift signal baseline)

Matplotlib is imported lazily so the rest of the M5 pipeline runs even
when matplotlib is unavailable. Plot generation returns ``None``
silently in that case.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

import numpy as np


__all__ = [
    "reliability_diagram",
    "confusion_heatmap",
    "latency_histogram",
    "confidence_histogram_plot",
]


def _matplotlib_available() -> bool:
    try:
        import matplotlib                          # noqa: F401
        return True
    except ImportError:                            # pragma: no cover
        return False


# ---------------------------------------------------------------------------
# Reliability diagram (per ProductType)
# ---------------------------------------------------------------------------


def reliability_diagram(
    confidences: Sequence[float],
    outcomes: Sequence[int],
    out_path: Path,
    *,
    title: str = "Reliability diagram",
    n_bins: int = 10,
) -> Path | None:
    """Save a reliability diagram to ``out_path``.

    For each bin: mean predicted confidence vs observed accuracy.
    Perfect calibration → points on the diagonal.
    """
    if not _matplotlib_available() or not confidences:
        return None
    import matplotlib.pyplot as plt
    out_path.parent.mkdir(parents=True, exist_ok=True)

    conf = np.asarray(confidences, dtype=np.float64)
    out = np.asarray(outcomes, dtype=np.float64)
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_idx = np.clip(np.digitize(conf, bin_edges, right=False) - 1, 0, n_bins - 1)

    mean_conf, mean_acc, weights = [], [], []
    for b in range(n_bins):
        mask = bin_idx == b
        if not mask.any():
            continue
        mean_conf.append(conf[mask].mean())
        mean_acc.append(out[mask].mean())
        weights.append(mask.sum())

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], "--", color="gray", label="Perfect calibration")
    if mean_conf:
        sizes = np.asarray(weights) / max(weights) * 200 + 20
        ax.scatter(mean_conf, mean_acc, s=sizes, color="steelblue", label="Observed", alpha=0.7)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Mean predicted confidence (per bin)")
    ax.set_ylabel("Observed accuracy (per bin)")
    ax.set_title(title)
    ax.legend(loc="lower right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# Confusion heatmap (top-10 attributes)
# ---------------------------------------------------------------------------


def confusion_heatmap(
    confusion: Mapping[str, Mapping[tuple[str, str], int]],
    out_path: Path,
    *,
    max_values_per_attribute: int = 8,
) -> Path | None:
    """Render one small heatmap per attribute side-by-side in a single figure."""
    if not _matplotlib_available() or not confusion:
        return None
    import matplotlib.pyplot as plt
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_attrs = len(confusion)
    n_cols = min(n_attrs, 3)
    n_rows = (n_attrs + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(5 * n_cols, 5 * n_rows), squeeze=False)
    flat_axes = axes.flatten()

    for ax_idx, (attr, counts) in enumerate(confusion.items()):
        # Pick the top-N most-frequent values for both axes.
        value_pop: dict[str, int] = {}
        for (pred, truth), n in counts.items():
            value_pop[pred] = value_pop.get(pred, 0) + n
            value_pop[truth] = value_pop.get(truth, 0) + n
        top_vals = sorted(value_pop, key=lambda v: -value_pop[v])[:max_values_per_attribute]
        idx = {v: i for i, v in enumerate(top_vals)}
        mat = np.zeros((len(top_vals), len(top_vals)), dtype=np.int64)
        for (pred, truth), n in counts.items():
            if pred in idx and truth in idx:
                mat[idx[truth], idx[pred]] += n
        ax = flat_axes[ax_idx]
        im = ax.imshow(mat, cmap="Blues", aspect="auto")
        ax.set_xticks(range(len(top_vals)))
        ax.set_yticks(range(len(top_vals)))
        ax.set_xticklabels([v[:14] for v in top_vals], rotation=45, ha="right", fontsize=8)
        ax.set_yticklabels([v[:14] for v in top_vals], fontsize=8)
        ax.set_xlabel("Predicted")
        ax.set_ylabel("True")
        ax.set_title(attr[:30], fontsize=10)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    for ax in flat_axes[len(confusion):]:
        ax.set_visible(False)

    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# Latency histogram
# ---------------------------------------------------------------------------


def latency_histogram(
    latencies_ms: Sequence[float],
    out_path: Path,
    *,
    p50_target: float = 50.0,
    p95_target: float = 200.0,
) -> Path | None:
    if not _matplotlib_available() or not latencies_ms:
        return None
    import matplotlib.pyplot as plt
    out_path.parent.mkdir(parents=True, exist_ok=True)

    arr = np.asarray(latencies_ms, dtype=np.float64)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(arr, bins=40, color="steelblue", alpha=0.8, edgecolor="white")
    ax.axvline(p50_target, linestyle="--", color="green", label=f"p50 target = {p50_target} ms")
    ax.axvline(p95_target, linestyle="--", color="red", label=f"p95 target = {p95_target} ms")
    ax.axvline(float(np.percentile(arr, 50)), linestyle="-", color="black", alpha=0.4, label=f"observed p50 = {np.percentile(arr, 50):.1f} ms")
    ax.axvline(float(np.percentile(arr, 95)), linestyle="-", color="black", alpha=0.6, label=f"observed p95 = {np.percentile(arr, 95):.1f} ms")
    ax.set_xlabel("Latency (ms)")
    ax.set_ylabel("Query count")
    ax.set_title("End-to-end latency distribution (spec §1.2 budget)")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# Confidence distribution (drift baseline)
# ---------------------------------------------------------------------------


def confidence_histogram_plot(
    confidences: Sequence[float],
    out_path: Path,
    *,
    auto_threshold: float = 0.85,
    review_floor: float = 0.50,
) -> Path | None:
    if not _matplotlib_available() or not confidences:
        return None
    import matplotlib.pyplot as plt
    out_path.parent.mkdir(parents=True, exist_ok=True)

    arr = np.asarray(confidences, dtype=np.float64)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(arr, bins=40, color="darkorange", alpha=0.8, edgecolor="white")
    ax.axvline(auto_threshold, linestyle="--", color="green", label=f"auto-process @ {auto_threshold}")
    ax.axvline(review_floor, linestyle="--", color="goldenrod", label=f"human review floor @ {review_floor}")
    ax.set_xlabel("conf_final")
    ax.set_ylabel("Sample count")
    ax.set_title("Confidence distribution — baseline for drift monitoring (§5.5 / CAP-ML-04)")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path
