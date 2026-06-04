"""Generate the four feasibility graphs from a model_comparison_*.json.

Graphs:
  1. accuracy vs token usage      (overall_accuracy vs tokens_per_item)
  2. accuracy vs model size       (overall_accuracy vs params_b)
  3. confidence accuracy vs model size   (high_conf_accuracy vs params_b)
  4. confidence accuracy vs token usage  (high_conf_accuracy vs tokens_per_item)

"Confidence accuracy" = accuracy among predictions the model asserted at
confidence >= 1.00 (the `high_conf_accuracy` field). A well-calibrated model
would have this near 1.0; the gap below 1.0 is the over-confidence problem.

Usage:
    python scripts/make_graphs.py                       # uses newest comparison JSON
    python scripts/make_graphs.py --input artifacts/model_comparison_*.json
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

FIT_COLOR = "#6BAED6"  # light blue best-fit line

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts"
GRAPHS = ARTIFACTS / "graphs"

STAT_TRACK_ACC = 0.9469  # M3b reference baseline

# Stable colour per model label so the four charts are visually consistent.
COLORS = {
    "llama3.2:3b": "#4C72B0",
    "qwen2.5:7b": "#DD8452",
    "llama3.1:8b": "#55A868",
    "phi4:14b": "#C44E52",
    "qwen2.5:14b": "#8172B3",
}


def newest_comparison() -> Path:
    files = sorted(glob.glob(str(ARTIFACTS / "model_comparison_*.json")))
    if not files:
        print("No model_comparison_*.json in artifacts/. Run run_all_models.py first.",
              file=sys.stderr)
        sys.exit(2)
    return Path(files[-1])


def _annotate(ax, xs, ys, labels):
    for x, y, lab in zip(xs, ys, labels):
        ax.annotate(lab, (x, y), textcoords="offset points", xytext=(6, 6), fontsize=8)


def _fit_line(ax, xs, ys):
    """Draw a single light-blue linear least-squares best-fit line."""
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    if len(xs) < 2 or xs.min() == xs.max():
        return
    slope, intercept = np.polyfit(xs, ys, 1)
    xline = np.linspace(xs.min(), xs.max(), 100)
    ax.plot(xline, slope * xline + intercept, color=FIT_COLOR, lw=2.5,
            zorder=2, label="best fit")


def _scatter(ax, xs, ys, labels, *, xlabel, ylabel, title):
    for x, y, lab in zip(xs, ys, labels):
        ax.scatter(x, y, s=90, color=COLORS.get(lab, "#333333"), zorder=3, edgecolors="white")
    _annotate(ax, xs, ys, labels)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3, zorder=0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default=None)
    args = ap.parse_args()

    path = Path(args.input) if args.input else newest_comparison()
    data = json.loads(path.read_text(encoding="utf-8"))
    summaries = data["summaries"]
    meta = f"n={data['n']}, shortlist={data['shortlist']}, temp={data['temperature']}, seed={data['seed']}"

    # Sort by model size for stable left-to-right ordering.
    summaries.sort(key=lambda s: (s.get("params_b") or 0))
    labels = [s["label"] for s in summaries]
    params = [s.get("params_b") for s in summaries]
    acc = [s["overall_accuracy"] * 100 for s in summaries]
    hi_conf = [(s["high_conf_accuracy"] or 0) * 100 for s in summaries]
    tpi = [s.get("tokens_per_item") for s in summaries]

    GRAPHS.mkdir(parents=True, exist_ok=True)
    saved = []

    # 1. Accuracy vs token usage --------------------------------------------
    fig, ax = plt.subplots(figsize=(7.5, 5))
    _fit_line(ax, tpi, acc)
    _scatter(ax, tpi, acc, labels,
             xlabel="Token usage (avg tokens / classification)",
             ylabel="Overall accuracy (%)",
             title="1. Accuracy vs Token Usage")
    ax.axhline(STAT_TRACK_ACC * 100, ls="--", color="grey", lw=1)
    ax.annotate(f"stat-track baseline {STAT_TRACK_ACC*100:.1f}%",
                (max(tpi), STAT_TRACK_ACC * 100), textcoords="offset points",
                xytext=(-10, 6), ha="right", fontsize=8, color="grey")
    fig.text(0.5, 0.01, meta, ha="center", fontsize=7, color="grey")
    f = GRAPHS / "1_accuracy_vs_tokens.png"
    fig.tight_layout(rect=[0, 0.03, 1, 1]); fig.savefig(f, dpi=150); plt.close(fig); saved.append(f)

    # 2. Accuracy vs model size ---------------------------------------------
    fig, ax = plt.subplots(figsize=(7.5, 5))
    order = sorted(range(len(params)), key=lambda i: params[i])
    px = [params[i] for i in order]; py = [acc[i] for i in order]; pl = [labels[i] for i in order]
    _fit_line(ax, px, py)
    _scatter(ax, px, py, pl,
             xlabel="Model size (billions of parameters)",
             ylabel="Overall accuracy (%)",
             title="2. Accuracy vs Model Size")
    ax.axhline(STAT_TRACK_ACC * 100, ls="--", color="grey", lw=1)
    ax.annotate(f"stat-track baseline {STAT_TRACK_ACC*100:.1f}%",
                (max(px), STAT_TRACK_ACC * 100), textcoords="offset points",
                xytext=(-10, 6), ha="right", fontsize=8, color="grey")
    fig.text(0.5, 0.01, meta, ha="center", fontsize=7, color="grey")
    f = GRAPHS / "2_accuracy_vs_size.png"
    fig.tight_layout(rect=[0, 0.03, 1, 1]); fig.savefig(f, dpi=150); plt.close(fig); saved.append(f)

    # 3. Confidence accuracy vs model size ----------------------------------
    fig, ax = plt.subplots(figsize=(7.5, 5))
    py = [hi_conf[i] for i in order]
    _fit_line(ax, px, py)
    _scatter(ax, px, py, pl,
             xlabel="Model size (billions of parameters)",
             ylabel="Confidence accuracy (% correct when conf = 1.0)",
             title="3. Confidence Accuracy vs Model Size")
    ax.axhline(100, ls="--", color="green", lw=1)
    ax.annotate("perfect calibration (100%)", (max(px), 100), textcoords="offset points",
                xytext=(-10, -12), ha="right", fontsize=8, color="green")
    fig.text(0.5, 0.01, meta, ha="center", fontsize=7, color="grey")
    f = GRAPHS / "3_confidence_accuracy_vs_size.png"
    fig.tight_layout(rect=[0, 0.03, 1, 1]); fig.savefig(f, dpi=150); plt.close(fig); saved.append(f)

    # 4. Confidence accuracy vs token usage ---------------------------------
    fig, ax = plt.subplots(figsize=(7.5, 5))
    _fit_line(ax, tpi, hi_conf)
    _scatter(ax, tpi, hi_conf, labels,
             xlabel="Token usage (avg tokens / classification)",
             ylabel="Confidence accuracy (% correct when conf = 1.0)",
             title="4. Confidence Accuracy vs Token Usage")
    ax.axhline(100, ls="--", color="green", lw=1)
    ax.annotate("perfect calibration (100%)", (max(tpi), 100), textcoords="offset points",
                xytext=(-10, -12), ha="right", fontsize=8, color="green")
    fig.text(0.5, 0.01, meta, ha="center", fontsize=7, color="grey")
    f = GRAPHS / "4_confidence_accuracy_vs_tokens.png"
    fig.tight_layout(rect=[0, 0.03, 1, 1]); fig.savefig(f, dpi=150); plt.close(fig); saved.append(f)

    print("Saved graphs:")
    for f in saved:
        print(f"  {f}")
    print(f"\nSource data: {path}")
    print("\nData table:")
    print(f"  {'model':14}{'params':>8}{'tok/item':>10}{'overall%':>10}{'confAcc%':>10}")
    for s in summaries:
        hc = (s['high_conf_accuracy'] or 0) * 100
        print(f"  {s['label']:14}{str(s.get('params_b'))+'B':>8}{s.get('tokens_per_item'):>10}"
              f"{s['overall_accuracy']*100:>10.1f}{hc:>10.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
