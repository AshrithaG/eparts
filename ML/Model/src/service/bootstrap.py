"""Production wiring — load real artifacts and build the service app.

Separated from :mod:`src.service.app` so the route logic stays unit-
testable without loading the 293 MB FAISS index / 2.7 GB covariance
artifact. The launcher (``scripts/m7_serve.py``) calls
:func:`build_default_app`.
"""

from __future__ import annotations

from pathlib import Path

from ..config import Settings, load_settings
from ..data import load_products
from ..layer3_semantic import (
    ClusterStore,
    Encoder,
    ProductIndex,
    SemanticScorer,
    build_pt_index_from_1b,
    build_usage_prior_from_2a,
)
from ..layer4_decision import FeedbackStore, Layer4Decision, SigmaTable
from ..evaluation.runner import InferencePipeline
from .app import create_app
from .metrics import ServiceMetrics, load_baseline_conf_hist


def build_default_app(
    run_dir: Path,
    settings: Settings | None = None,
    baseline_csv: Path | None = None,
    enable_feedback: bool = True,
):
    """Load all V1 artifacts from ``run_dir`` and return a wired FastAPI app.

    Args:
        run_dir: Directory with faiss.bin + ids.npy + centroids.parquet +
            cluster_cov.npz + sigma_table.parquet (e.g. artifacts/v1/current).
        settings: Optional pre-loaded settings; loads from config/ if None.
        baseline_csv: M5 confidence_dist.csv for the drift signal; optional.
        enable_feedback: If False, /feedback returns 503 (read-only deploy).

    Returns:
        A FastAPI app instance ready for uvicorn.
    """
    settings = settings or load_settings()

    product_index = ProductIndex.load(run_dir, settings.faiss)
    cluster_store = ClusterStore.load(run_dir)
    encoder = Encoder(settings.encoder)
    pt_index = build_pt_index_from_1b(
        load_products(columns=["Product_ID", "ProductType_ID", "ProductType_Name"])
    )
    usage_prior = build_usage_prior_from_2a()
    sigma_table = SigmaTable.load(run_dir)
    scorer = SemanticScorer(cluster_store, usage_prior, sigma_by_pt=sigma_table.as_sigma_by_pt())
    decider = Layer4Decision(settings.thresholds)

    # model_version = the run directory name (CAP-ML-03 provenance).
    model_version = run_dir.resolve().name
    pipeline = InferencePipeline(
        encoder, product_index, pt_index, scorer, decider, model_version=model_version
    )

    feedback_store = None
    if enable_feedback:
        feedback_store = FeedbackStore(
            cluster_store,
            artifact_dir=run_dir,
            pushback_lambda=settings.thresholds.online_updates.pushback_lambda,
        )
        # Recover any post-snapshot updates from the audit log on startup.
        feedback_store.replay()

    baseline_hist = load_baseline_conf_hist(baseline_csv) if baseline_csv else None
    metrics = ServiceMetrics(baseline_conf_hist=baseline_hist)

    return create_app(
        pipeline=pipeline,
        feedback_store=feedback_store,
        encoder=encoder if enable_feedback else None,
        metrics=metrics,
    )
