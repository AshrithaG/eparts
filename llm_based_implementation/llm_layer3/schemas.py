"""Pydantic models for the LLM Layer 3 POC.

Two schema families:

  * The *grounding pack* (`GroundingPack` + helpers) describes what we
    show to the LLM — a deterministic function of (query, retrieval
    result, ProductTypeAttributes table, canonical 2A vocabulary).

  * The *LLM output* (`LLMPrediction` + `AttributePrediction`) is the
    schema the model is forced to fill in. It is also what we hand to
    Ollama as the JSON-schema constraint, so non-conforming output is
    impossible at the decoder level.

`Provenance` and `ExtractionResult` wrap the LLM output with the audit
trail the plan's §6.2 (and the May 1 studio critique) require.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Sentinel used to mark the abstention path. Kept as a constant so it is
# easy to grep for and impossible to mistype across modules.
INSUFFICIENT_EVIDENCE = "insufficient_evidence"


# ---------------------------------------------------------------------------
# Grounding-pack side
# ---------------------------------------------------------------------------

class NeighborDigest(BaseModel):
    """One catalog product surfaced by retrieval, summarized for the LLM."""

    model_config = ConfigDict(extra="forbid")

    product_id: int
    short_description: str
    product_type: str
    similarity: float = Field(ge=0.0, le=1.0)
    # Attribute -> value as recorded on this neighbor in 1A. The LLM uses
    # these as evidence (and we use them as a retrieval-agreement signal
    # for the confidence ensemble in a later milestone).
    values: dict[str, str] = Field(default_factory=dict)


class AttributeSpec(BaseModel):
    """An attribute the LLM may predict, with its closed value vocabulary."""

    model_config = ConfigDict(extra="forbid")

    name: str
    # The canonical 2A values for this attribute. Anything else the LLM
    # produces is post-validated to INSUFFICIENT_EVIDENCE.
    allowed_values: list[str]
    # value -> usage_count from 2A_Values_Per_Attribute.csv. Surfaces the
    # frequency prior for the model and is reused numerically downstream.
    usage_counts: dict[str, int] = Field(default_factory=dict)


class GroundingPack(BaseModel):
    """Everything the LLM is allowed to see for one query."""

    model_config = ConfigDict(extra="forbid")

    query: str
    top_k_neighbors: list[NeighborDigest]
    candidate_product_types: list[str]
    in_scope_attributes: list[AttributeSpec]


# ---------------------------------------------------------------------------
# LLM output side — also acts as the schema fed to the decoder
# ---------------------------------------------------------------------------

class AttributePrediction(BaseModel):
    """One predicted (attribute, value) pair with rationale and evidence."""

    model_config = ConfigDict(extra="forbid")

    attribute: str
    # The model is told to use INSUFFICIENT_EVIDENCE when it cannot
    # commit. Out-of-vocabulary values are demoted to that sentinel by
    # `extract()` (see closed-vocabulary post-validation).
    value: str
    # Self-reported confidence. NOT used for routing — Layer 4 routes on
    # the calibrated `conf_embed_final`. Kept here as a feature for the
    # confidence ensemble (L3 milestone).
    verbalized_confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(max_length=300)
    neighbor_ids: list[int] = Field(default_factory=list)


class LLMPrediction(BaseModel):
    """The structured object the LLM is forced to fill in."""

    model_config = ConfigDict(extra="forbid")

    product_type: str
    product_type_alternatives: list[str] = Field(default_factory=list)
    attributes: list[AttributePrediction]


# ---------------------------------------------------------------------------
# Provenance + wrapped result
# ---------------------------------------------------------------------------

class Provenance(BaseModel):
    """Immutable audit record produced for every extraction.

    Carries the model identity, the deterministic decoding params, and
    the content hashes of the prompt and grounding pack. Re-running with
    identical inputs and a pinned model snapshot must reproduce the
    same prediction byte-for-byte — that is the test of reproducibility
    referenced in the plan's §6.2 and quality-attribute scenario 5.
    """

    model_config = ConfigDict(extra="forbid")

    model: str
    model_options: dict[str, Any] = Field(default_factory=dict)
    prompt_hash: str
    grounding_hash: str
    timestamp: str
    samples_used: int = 1


class ExtractionResult(BaseModel):
    """`extract()`'s return value: prediction + provenance + warnings."""

    model_config = ConfigDict(extra="forbid")

    prediction: LLMPrediction
    provenance: Provenance
    # Verbatim string the LLM returned. Useful for diagnosing why the
    # post-validator demoted something.
    raw_response: str | None = None
    # Each entry describes a post-validation correction (e.g. an
    # out-of-vocab value that was demoted to insufficient_evidence).
    # Empty when the model produced a fully clean prediction.
    validation_warnings: list[str] = Field(default_factory=list)
