"""Request / response schemas for the M7 REST service.

Implements the wire contract for V1_Engineering_Spec §7.2 M7:

    POST /predict  → {predictions, product_type, pt_conf,
                      conf_final_per_attribute, latency_ms, model_version}
    POST /feedback → {status, updated}

Pydantic v2 models. These are the *external* HTTP contract — distinct
from the internal :mod:`src.contracts` dataclasses, so the service can
evolve its JSON shape without touching the pipeline's typed core.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# /predict
# ---------------------------------------------------------------------------


class PredictRequest(BaseModel):
    """Inbound prediction request."""

    text: str = Field(..., description="Cleaned product description to score.")
    source_type: Literal["csv", "email", "pdf_text", "pdf_ocr", "image"] = Field(
        default="csv",
        description="Intake channel tag, carried through for metric stratification.",
    )
    source_ref: str | None = Field(
        default=None, description="Opaque trace identifier echoed back on the response."
    )


class AttributePredictionOut(BaseModel):
    """One fused attribute prediction."""

    attribute_name: str
    predicted_value: str
    conf_rule: float
    conf_embed_final: float
    conf_final: float
    routing: str
    low_sample_capped: bool
    pt_ambiguity_capped: bool


class PredictResponse(BaseModel):
    """Outbound prediction response (spec §7.2 M7 shape)."""

    input_ref: str | None
    source_type: str
    product_type_id: int | None
    product_type_name: str | None
    pt_conf: float | None
    predictions: list[AttributePredictionOut]
    conf_final_per_attribute: dict[str, float] = Field(
        ..., description="Convenience map attribute_name → conf_final."
    )
    latency_ms: float
    model_version: str


# ---------------------------------------------------------------------------
# /feedback
# ---------------------------------------------------------------------------


class FeedbackRequest(BaseModel):
    """Inbound reviewer-feedback request (confirm or correct)."""

    action: Literal["confirm", "correct"]
    product_type_id: int
    attribute_name: str
    reviewer_id: str
    text: str = Field(..., description="Description to encode into the query embedding.")
    # confirm:
    value: str | None = Field(default=None, description="Confirmed value (action=confirm).")
    # correct:
    value_wrong: str | None = Field(
        default=None, description="Confidently-wrong value (action=correct, pushback target)."
    )
    value_true: str | None = Field(
        default=None, description="True value (action=correct, confirm target)."
    )


class FeedbackResponse(BaseModel):
    status: Literal["applied"]
    action: str
    updated: dict[str, int] = Field(
        ..., description="Map of value → new cluster N after the update."
    )


# ---------------------------------------------------------------------------
# /healthz
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    model_version: str
    n_clusters: int
    ready: bool
