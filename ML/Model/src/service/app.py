"""FastAPI application factory for the M7 inference service.

Implements V1_Engineering_Spec §7.2 M7 + §8 (CAP-ML-01/04).

Endpoints:
    POST /predict   — run the M3+M4 pipeline on one text query
    POST /feedback  — apply reviewer confirm/correct (M6 online update)
    GET  /healthz    — liveness + readiness
    GET  /metrics    — Prometheus exposition

The app is built by :func:`create_app`, which takes its dependencies
**injected** (an inference pipeline, a feedback store, an encoder for
feedback queries, and a metrics bundle). This keeps the route logic
testable with lightweight fakes — no 2.7 GB artifact load in unit tests.
The production wiring that loads real artifacts lives in
:mod:`src.service.bootstrap`.
"""

from __future__ import annotations

from typing import Protocol

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ..contracts import SourceType
from ..layer4_decision import ClusterNotFoundError, FeedbackStore
from .metrics import ServiceMetrics
from .schemas import (
    AttributePredictionOut,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    PredictRequest,
    PredictResponse,
)


# ---------------------------------------------------------------------------
# Structural deps (duck-typed so tests can inject fakes)
# ---------------------------------------------------------------------------


class PredictPipeline(Protocol):
    """Minimal surface the /predict route needs (satisfied by InferencePipeline)."""

    @property
    def model_version(self) -> str: ...

    def predict_from_text(self, text: str, *, source_type: SourceType = ...,
                          source_ref: str | None = ...): ...


class QueryEncoder(Protocol):
    """Minimal surface for encoding feedback queries (satisfied by Encoder)."""

    def encode_one(self, text: str): ...


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(
    pipeline: PredictPipeline,
    feedback_store: FeedbackStore | None,
    encoder: QueryEncoder | None,
    metrics: ServiceMetrics,
) -> FastAPI:
    """Build the FastAPI app around injected dependencies.

    Args:
        pipeline: Inference pipeline exposing ``predict_from_text`` +
            ``model_version``.
        feedback_store: M6 :class:`FeedbackStore`. If ``None``, /feedback
            returns 503 (feedback disabled in this deployment).
        encoder: Encoder for feedback query embeddings. Required iff
            ``feedback_store`` is provided.
        metrics: Prometheus collector bundle.
    """
    app = FastAPI(title="eParts ML Confidence Scoring Service", version="v1")

    @app.post("/predict", response_model=PredictResponse)
    def predict(req: PredictRequest) -> PredictResponse:
        try:
            out = pipeline.predict_from_text(
                req.text,
                source_type=SourceType(req.source_type),
                source_ref=req.source_ref,
            )
        except Exception as exc:                                  # pragma: no cover - defensive
            metrics.requests.labels(endpoint="predict", outcome="error").inc()
            raise HTTPException(status_code=500, detail=f"prediction failed: {exc}") from exc

        result = out.result
        preds = [
            AttributePredictionOut(
                attribute_name=p.attribute_name,
                predicted_value=p.predicted_value,
                conf_rule=p.conf_rule,
                conf_embed_final=p.conf_embed_final,
                conf_final=p.conf_final,
                routing=p.routing.value,
                low_sample_capped=p.low_sample_capped,
                pt_ambiguity_capped=p.pt_ambiguity_capped,
            )
            for p in result.predictions
        ]
        conf_map = {p.attribute_name: p.conf_final for p in result.predictions if p.attribute_name}
        pt = result.product_type
        pt_conf = pt.pt_conf if pt is not None else None

        metrics.observe_prediction(
            [p.conf_final for p in result.predictions], pt_conf, result.latency_ms
        )
        metrics.requests.labels(endpoint="predict", outcome="ok").inc()

        return PredictResponse(
            input_ref=result.input_ref,
            source_type=result.source_type.value,
            product_type_id=pt.product_type_id if pt is not None else None,
            product_type_name=pt.product_type_name if pt is not None else None,
            pt_conf=pt_conf,
            predictions=preds,
            conf_final_per_attribute=conf_map,
            latency_ms=result.latency_ms,
            model_version=result.model_version,
        )

    @app.post("/feedback", response_model=FeedbackResponse)
    def feedback(req: FeedbackRequest) -> FeedbackResponse:
        if feedback_store is None or encoder is None:
            raise HTTPException(status_code=503, detail="feedback not enabled on this deployment")
        q = encoder.encode_one(req.text)
        try:
            if req.action == "confirm":
                if not req.value:
                    raise HTTPException(status_code=422, detail="confirm requires 'value'")
                updated = feedback_store.confirm(
                    req.product_type_id, req.attribute_name, req.value, q,
                    reviewer_id=req.reviewer_id,
                )
                result_map = {updated.value: updated.n}
            else:  # correct
                if not req.value_wrong or not req.value_true:
                    raise HTTPException(
                        status_code=422,
                        detail="correct requires 'value_wrong' and 'value_true'",
                    )
                wrong, true = feedback_store.correct(
                    req.product_type_id, req.attribute_name,
                    value_wrong=req.value_wrong, value_true=req.value_true,
                    q=q, reviewer_id=req.reviewer_id,
                )
                result_map = {wrong.value: wrong.n, true.value: true.n}
        except ClusterNotFoundError as exc:
            metrics.requests.labels(endpoint="feedback", outcome="not_found").inc()
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        metrics.feedback_total.labels(action=req.action).inc()
        metrics.requests.labels(endpoint="feedback", outcome="ok").inc()
        return FeedbackResponse(status="applied", action=req.action, updated=result_map)

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        n_clusters = len(feedback_store.cluster_store) if feedback_store is not None else 0
        return HealthResponse(
            status="ok",
            model_version=pipeline.model_version,
            n_clusters=n_clusters,
            ready=True,
        )

    @app.get("/metrics")
    def prometheus_metrics() -> PlainTextResponse:
        return PlainTextResponse(
            generate_latest(metrics.registry).decode("utf-8"),
            media_type=CONTENT_TYPE_LATEST,
        )

    return app
