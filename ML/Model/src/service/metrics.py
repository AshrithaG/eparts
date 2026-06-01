"""Prometheus telemetry + drift signal for the M7 service.

Implements V1_Engineering_Spec §7.2 M7 + §8 CAP-ML-04:

    * request count (by endpoint + outcome)
    * end-to-end latency histogram
    * confidence (conf_final) distribution histogram
    * ProductType-consensus (pt_conf) distribution histogram
    * drift signal = KL divergence of the live conf_final distribution
      vs the M5 baseline distribution

Metrics live in a private :class:`CollectorRegistry` so multiple app
instances (and the test suite) don't collide on the global default
registry.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

# conf_final ∈ [0, 1]; pt_conf ∈ [0, 1]. Shared bucket edges.
_CONF_BUCKETS = (0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0)
# Latency buckets in milliseconds spanning the spec gate (50 / 200 ms).
_LATENCY_BUCKETS = (5, 10, 20, 30, 50, 75, 100, 150, 200, 300, 500, 1000)
# Drift histogram bin count (must match how the baseline was binned).
_DRIFT_BINS = 20


class ServiceMetrics:
    """Bundle of Prometheus collectors + a live conf_final accumulator."""

    def __init__(self, baseline_conf_hist: np.ndarray | None = None) -> None:
        self.registry = CollectorRegistry()

        self.requests = Counter(
            "eparts_requests_total",
            "Total requests by endpoint and outcome.",
            ["endpoint", "outcome"],
            registry=self.registry,
        )
        self.latency_ms = Histogram(
            "eparts_predict_latency_ms",
            "End-to-end /predict latency in milliseconds.",
            buckets=_LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.conf_final = Histogram(
            "eparts_conf_final",
            "Distribution of conf_final over auto/review/flag predictions.",
            buckets=_CONF_BUCKETS,
            registry=self.registry,
        )
        self.pt_conf = Histogram(
            "eparts_pt_conf",
            "Distribution of ProductType consensus confidence.",
            buckets=_CONF_BUCKETS,
            registry=self.registry,
        )
        self.drift_kl = Gauge(
            "eparts_conf_drift_kl",
            "KL divergence of live conf_final distribution vs the M5 baseline.",
            registry=self.registry,
        )
        self.feedback_total = Counter(
            "eparts_feedback_total",
            "Reviewer feedback events by action.",
            ["action"],
            registry=self.registry,
        )

        # Normalized baseline distribution over _DRIFT_BINS (or None).
        self._baseline = _normalize_hist(baseline_conf_hist) if baseline_conf_hist is not None else None
        # Live accumulator of conf_final values for drift computation.
        self._live_counts = np.zeros(_DRIFT_BINS, dtype=np.float64)

    # ---- recording -----------------------------------------------------

    def observe_prediction(self, conf_final_values: list[float], pt_conf: float | None,
                           latency_ms: float) -> None:
        self.latency_ms.observe(latency_ms)
        if pt_conf is not None:
            self.pt_conf.observe(pt_conf)
        for c in conf_final_values:
            self.conf_final.observe(c)
            b = min(_DRIFT_BINS - 1, max(0, int(c * _DRIFT_BINS)))
            self._live_counts[b] += 1.0
        self._refresh_drift()

    def _refresh_drift(self) -> None:
        if self._baseline is None or self._live_counts.sum() == 0:
            return
        live = _normalize_hist(self._live_counts)
        self.drift_kl.set(_kl_divergence(live, self._baseline))

    # ---- accessors for tests ------------------------------------------

    @property
    def live_drift_kl(self) -> float:
        return float(self.drift_kl._value.get())   # noqa: SLF001 — test introspection


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _normalize_hist(counts: np.ndarray) -> np.ndarray:
    """Normalize a count vector to a probability distribution (sums to 1)."""
    counts = np.asarray(counts, dtype=np.float64)
    total = counts.sum()
    if total <= 0:
        return np.full(len(counts), 1.0 / len(counts))
    return counts / total


def _kl_divergence(p: np.ndarray, q: np.ndarray, eps: float = 1e-9) -> float:
    """KL(P || Q) with Laplace smoothing so zero bins don't explode.

    Both inputs are probability vectors of equal length. Returns nats.
    """
    p = np.asarray(p, dtype=np.float64) + eps
    q = np.asarray(q, dtype=np.float64) + eps
    p /= p.sum()
    q /= q.sum()
    return float(np.sum(p * np.log(p / q)))


def load_baseline_conf_hist(csv_path: Path, n_bins: int = _DRIFT_BINS) -> np.ndarray | None:
    """Build the baseline conf_final histogram from an M5 confidence_dist.csv.

    The M5 report's ``confidence_dist.csv`` has columns ``bin_low, bin_high,
    count`` (20 equal-width bins over [0, 1]). Returns the count vector, or
    ``None`` if the file is missing / unreadable so the service degrades to
    "no drift signal" rather than failing to start.
    """
    if not csv_path.exists():
        return None
    try:
        import pandas as pd
        df = pd.read_csv(csv_path)
        # Be liberal about column naming — accept a 'count' column.
        count_col = next((c for c in df.columns if c.lower() == "count"), None)
        if count_col is None:
            return None
        counts = df[count_col].to_numpy(dtype=np.float64)
        if len(counts) != n_bins:
            # Rebin by interpolation if the CSV used a different bin count.
            xs = np.linspace(0, 1, len(counts))
            target = np.linspace(0, 1, n_bins)
            counts = np.interp(target, xs, counts)
        return counts
    except Exception:
        return None
