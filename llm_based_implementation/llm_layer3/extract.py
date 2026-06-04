"""End-to-end extraction.

`extract(client, pack)` is the single entry point Layer 4 (and the
demo) call. It:

  1. Renders the user prompt from the grounding pack.
  2. Hands the JSON schema + prompts to the backend (the model is
     forced to emit a syntactically valid LLMPrediction).
  3. Parses the model output. If parsing fails (it shouldn't, with
     schema-constrained decoding, but defenses-in-depth) it abstains.
  4. Runs the closed-vocabulary post-validator — any value not in the
     2A canonical set for its attribute is demoted to
     `insufficient_evidence`. Same goes for an out-of-vocab
     product_type, which is snapped to the top retrieval candidate.
  5. Stamps a Provenance record onto the result.

Confidence calibration (L3 in the plan) is NOT done here yet. The
returned `verbalized_confidence` is feature-only; the calibrated
`conf_embed_final` that Layer 4 routes on is computed downstream
once the confidence ensemble is implemented.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .llm_client import LLMClient
from .prompt import SYSTEM_PROMPT, render_user_prompt
from .schemas import (
    AttributePrediction,
    ExtractionResult,
    GroundingPack,
    INSUFFICIENT_EVIDENCE,
    LLMPrediction,
    Provenance,
)


def _hash16(s: str) -> str:
    """Short stable hash for provenance. 16 hex chars = 64 bits ≈ no collisions in practice."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def extract(
    client: LLMClient,
    pack: GroundingPack,
    client_options: dict[str, Any] | None = None,
) -> ExtractionResult:
    """Run one extraction. Pure function in everything except the LLM call."""
    user_prompt = render_user_prompt(pack)
    schema = LLMPrediction.model_json_schema()

    raw, meta = client.extract(SYSTEM_PROMPT, user_prompt, schema, client_options)
    warnings: list[str] = []

    # ---- Parse ----------------------------------------------------------
    prediction = _parse_or_abstain(raw, pack, warnings)

    # ---- Closed-vocabulary post-validation -----------------------------
    _enforce_closed_vocab(prediction, pack, warnings)

    # ---- Provenance -----------------------------------------------------
    grounding_blob = pack.model_dump_json(round_trip=True)
    prov = Provenance(
        model=client.model_id,
        model_options=meta,
        prompt_hash=_hash16(SYSTEM_PROMPT + "\n---\n" + user_prompt),
        grounding_hash=_hash16(grounding_blob),
        timestamp=datetime.now(timezone.utc).isoformat(),
        samples_used=1,
    )

    return ExtractionResult(
        prediction=prediction,
        provenance=prov,
        raw_response=raw,
        validation_warnings=warnings,
    )


def _parse_or_abstain(
    raw: str,
    pack: GroundingPack,
    warnings: list[str],
) -> LLMPrediction:
    """Parse the model response; abstain to a safe empty prediction if malformed."""
    try:
        return LLMPrediction.model_validate_json(raw)
    except Exception as e1:  # noqa: BLE001 - we genuinely want any parse error
        # Try to recover by parsing as raw JSON first (handles some
        # backends that wrap the response in code fences).
        try:
            obj = json.loads(_strip_fences(raw))
            return LLMPrediction.model_validate(obj)
        except Exception as e2:  # noqa: BLE001
            warnings.append(f"schema_validation_failed: {type(e1).__name__}: {e1}; "
                            f"fallback: {type(e2).__name__}: {e2}")
            # Safe abstention: top candidate PT (if any) and zero attributes.
            fallback_pt = pack.candidate_product_types[0] if pack.candidate_product_types else "unknown"
            return LLMPrediction(
                product_type=fallback_pt,
                product_type_alternatives=[],
                attributes=[],
            )


def _strip_fences(s: str) -> str:
    """Remove leading/trailing markdown code fences if present."""
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
    if s.endswith("```"):
        s = s.rsplit("```", 1)[0]
    return s.strip()


def _enforce_closed_vocab(
    prediction: LLMPrediction,
    pack: GroundingPack,
    warnings: list[str],
) -> None:
    """Demote any out-of-vocabulary value or PT to a safe alternative.

    This is the structural anti-hallucination guarantee — it runs
    regardless of how the model produced the value (sampled, greedy,
    schema-constrained or not).
    """
    # ProductType
    candidate_pts = pack.candidate_product_types
    if candidate_pts and prediction.product_type not in candidate_pts:
        warnings.append(
            f"product_type_out_of_vocab: '{prediction.product_type}' "
            f"-> '{candidate_pts[0]}'"
        )
        prediction.product_type = candidate_pts[0]

    # Attributes
    allowed_by_attr = {s.name: set(s.allowed_values) for s in pack.in_scope_attributes}
    in_scope_names = set(allowed_by_attr.keys())
    cleaned: list[AttributePrediction] = []
    for ap in prediction.attributes:
        # Drop attributes the LLM invented that are not in scope at all.
        if ap.attribute not in in_scope_names:
            warnings.append(f"attribute_out_of_scope_dropped: '{ap.attribute}'")
            continue
        allowed = allowed_by_attr[ap.attribute]
        if ap.value == INSUFFICIENT_EVIDENCE:
            pass  # already abstaining
        elif ap.value not in allowed:
            warnings.append(
                f"value_out_of_vocab: {ap.attribute}='{ap.value}' "
                f"-> {INSUFFICIENT_EVIDENCE}"
            )
            ap.value = INSUFFICIENT_EVIDENCE
            ap.verbalized_confidence = 0.0
        cleaned.append(ap)
    prediction.attributes = cleaned
