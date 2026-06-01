"""M7 REST service tests (V1 spec §7.2 M7).

Uses FastAPI TestClient with INJECTED fakes — no FAISS / encoder / 2.7 GB
artifact load. A canned InferenceOutput exercises the /predict route; a
real (tiny, synthetic) FeedbackStore + fake encoder exercise /feedback.
"""
from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.contracts import (
    AttributePrediction,
    PipelineResult,
    ProductTypePrediction,
    Routing,
    SourceType,
)
from src.layer3_semantic.clusters import ClusterStats, ClusterStore
from src.layer4_decision import FeedbackStore
from src.service.app import create_app
from src.service.metrics import ServiceMetrics, _kl_divergence, _normalize_hist

DIM = 8


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeTrace:
    def __init__(self, total): self.total_ms = total


class _FakeOutput:
    def __init__(self, result): self.result = result; self.trace = _FakeTrace(result.latency_ms)


class FakePipeline:
    """Returns a canned PipelineResult; records the last call args."""

    model_version = "run_test"

    def __init__(self, result: PipelineResult):
        self._result = result
        self.calls: list[tuple] = []

    def predict_from_text(self, text, *, source_type=SourceType.CSV, source_ref=None):
        self.calls.append((text, source_type, source_ref))
        # Echo source_ref / source_type into a fresh result.
        from dataclasses import replace
        r = replace(self._result, input_ref=source_ref, source_type=source_type)
        return _FakeOutput(r)


class FakeEncoder:
    def encode_one(self, text: str) -> np.ndarray:
        # Deterministic non-zero vector; content irrelevant for routing tests.
        return np.ones(DIM, dtype=np.float32)


def _result(preds, pt=ProductTypePrediction(10, "Thermostats", 0.82), latency=12.3):
    return PipelineResult(
        input_ref=None,
        source_type=SourceType.CSV,
        product_type=pt,
        predictions=tuple(preds),
        latency_ms=latency,
        model_version="run_test",
    )


def _pred(attr="INPUT_VOLTAGE", value="24", conf_final=0.62, routing=Routing.HUMAN_REVIEW):
    return AttributePrediction(
        attribute_id=None, attribute_name=attr, predicted_value=value,
        conf_rule=0.0, conf_embed_final=conf_final / 0.3, conf_final=conf_final,
        routing=routing, low_sample_capped=False, pt_ambiguity_capped=False,
    )


def _cluster(cid, pt, attr, value, mu_fill, n=10):
    return ClusterStats(
        cluster_id=cid, product_type_id=pt, product_type_name=f"PT{pt}",
        attribute_name=attr, value=value, n=n,
        mu=np.full(DIM, mu_fill, dtype=np.float32),
        sigma_inv=np.eye(DIM, dtype=np.float32), log_det_sigma=0.0, low_sample=False,
    )


@pytest.fixture
def feedback_store(tmp_path):
    store = ClusterStore([
        _cluster(0, 10, "INPUT_VOLTAGE", "24", 0.0, n=10),
        _cluster(1, 10, "INPUT_VOLTAGE", "120", 1.0, n=8),
    ])
    return FeedbackStore(store, artifact_dir=tmp_path, pushback_lambda=0.01)


@pytest.fixture
def client(feedback_store):
    pipeline = FakePipeline(_result([_pred()]))
    metrics = ServiceMetrics()
    app = create_app(pipeline, feedback_store, FakeEncoder(), metrics)
    return TestClient(app), pipeline, metrics


# ===========================================================================
# /predict
# ===========================================================================


def test_predict_returns_spec_shape(client):
    tc, _, _ = client
    r = tc.post("/predict", json={"text": "24 VAC thermostat", "source_type": "email",
                                  "source_ref": "msg:1"})
    assert r.status_code == 200
    body = r.json()
    # spec §7.2 M7 required fields
    for key in ("predictions", "product_type_id", "pt_conf",
                "conf_final_per_attribute", "latency_ms", "model_version"):
        assert key in body
    assert body["model_version"] == "run_test"
    assert body["source_type"] == "email"
    assert body["input_ref"] == "msg:1"
    assert body["product_type_id"] == 10
    assert body["pt_conf"] == pytest.approx(0.82)
    assert body["conf_final_per_attribute"] == {"INPUT_VOLTAGE": pytest.approx(0.62)}
    assert body["predictions"][0]["routing"] == "human_review"


def test_predict_passes_source_type_to_pipeline(client):
    tc, pipeline, _ = client
    tc.post("/predict", json={"text": "x", "source_type": "pdf_ocr"})
    assert pipeline.calls[-1][1] == SourceType.PDF_OCR


def test_predict_rejects_missing_text(client):
    tc, _, _ = client
    r = tc.post("/predict", json={"source_type": "csv"})
    assert r.status_code == 422       # pydantic validation


def test_predict_rejects_bad_source_type(client):
    tc, _, _ = client
    r = tc.post("/predict", json={"text": "x", "source_type": "fax"})
    assert r.status_code == 422


def test_predict_increments_request_counter(client):
    tc, _, metrics = client
    tc.post("/predict", json={"text": "a"})
    tc.post("/predict", json={"text": "b"})
    val = metrics.requests.labels(endpoint="predict", outcome="ok")._value.get()
    assert val == 2.0


# ===========================================================================
# /feedback
# ===========================================================================


def test_feedback_confirm_applies_and_returns_new_n(client):
    tc, _, _ = client
    r = tc.post("/feedback", json={
        "action": "confirm", "product_type_id": 10, "attribute_name": "INPUT_VOLTAGE",
        "value": "24", "reviewer_id": "alice", "text": "some description",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "applied"
    assert body["updated"] == {"24": 11}     # n 10 -> 11


def test_feedback_correct_applies_pushback_and_confirm(client):
    tc, _, _ = client
    r = tc.post("/feedback", json={
        "action": "correct", "product_type_id": 10, "attribute_name": "INPUT_VOLTAGE",
        "value_wrong": "24", "value_true": "120", "reviewer_id": "bob", "text": "desc",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["updated"]["24"] == 10       # pushback: n unchanged
    assert body["updated"]["120"] == 9       # confirm: 8 -> 9


def test_feedback_unknown_cluster_returns_404(client):
    tc, _, _ = client
    r = tc.post("/feedback", json={
        "action": "confirm", "product_type_id": 10, "attribute_name": "INPUT_VOLTAGE",
        "value": "999", "reviewer_id": "x", "text": "desc",
    })
    assert r.status_code == 404


def test_feedback_confirm_without_value_is_422(client):
    tc, _, _ = client
    r = tc.post("/feedback", json={
        "action": "confirm", "product_type_id": 10, "attribute_name": "INPUT_VOLTAGE",
        "reviewer_id": "x", "text": "desc",
    })
    assert r.status_code == 422


def test_feedback_disabled_returns_503():
    pipeline = FakePipeline(_result([_pred()]))
    app = create_app(pipeline, feedback_store=None, encoder=None, metrics=ServiceMetrics())
    tc = TestClient(app)
    r = tc.post("/feedback", json={
        "action": "confirm", "product_type_id": 10, "attribute_name": "A",
        "value": "v", "reviewer_id": "x", "text": "d",
    })
    assert r.status_code == 503


# ===========================================================================
# /healthz + /metrics
# ===========================================================================


def test_healthz_reports_ready(client):
    tc, _, _ = client
    r = tc.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["ready"] is True
    assert body["model_version"] == "run_test"
    assert body["n_clusters"] == 2


def test_metrics_endpoint_exposes_prometheus(client):
    tc, _, _ = client
    tc.post("/predict", json={"text": "x"})
    r = tc.get("/metrics")
    assert r.status_code == 200
    assert "eparts_requests_total" in r.text
    assert "eparts_predict_latency_ms" in r.text
    assert "eparts_conf_final" in r.text


# ===========================================================================
# Drift signal (KL) — unit-level
# ===========================================================================


def test_kl_divergence_zero_for_identical():
    p = np.array([0.25, 0.25, 0.25, 0.25])
    assert _kl_divergence(p, p) == pytest.approx(0.0, abs=1e-6)


def test_kl_divergence_positive_for_different():
    p = np.array([0.9, 0.1, 0.0, 0.0])
    q = np.array([0.25, 0.25, 0.25, 0.25])
    assert _kl_divergence(p, q) > 0.0


def test_normalize_hist_sums_to_one():
    out = _normalize_hist(np.array([3.0, 1.0, 0.0, 6.0]))
    assert out.sum() == pytest.approx(1.0)


def test_drift_kl_set_after_predictions_with_baseline():
    # Baseline concentrated in low-confidence bins; live predictions are mid.
    baseline = np.zeros(20); baseline[1] = 100.0
    metrics = ServiceMetrics(baseline_conf_hist=baseline)
    pipeline = FakePipeline(_result([_pred(conf_final=0.62)]))
    app = create_app(pipeline, None, None, metrics)
    tc = TestClient(app)
    for _ in range(5):
        tc.post("/predict", json={"text": "x"})
    # Live conf (0.62) differs from baseline (≈0.05-0.10 bin) → KL > 0.
    assert metrics.live_drift_kl > 0.0
