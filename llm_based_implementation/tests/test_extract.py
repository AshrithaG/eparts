"""Unit tests for the LLM-track extraction core.

These tests use `MockLLMClient` and do not require Ollama. They cover:

  * happy-path extraction returns a well-formed ExtractionResult
  * provenance is populated and deterministic across runs with identical inputs
  * out-of-vocabulary attribute values are demoted to insufficient_evidence
  * out-of-vocabulary product_type is snapped to a candidate
  * out-of-scope attributes are dropped
  * malformed LLM output triggers a safe abstention
"""

from __future__ import annotations

import json
from pathlib import Path

from llm_layer3 import (
    MockLLMClient,
    build_grounding_pack,
    extract,
    load_fixtures,
    retrieve_top_k_stub,
)
from llm_layer3.schemas import INSUFFICIENT_EVIDENCE


FIXTURE_DIR = Path(__file__).resolve().parent.parent / "data" / "fixtures"


def _pack_for(query: str):
    f = load_fixtures(FIXTURE_DIR)
    neighbors = retrieve_top_k_stub(query, f["catalog"], k=5)
    return build_grounding_pack(query, neighbors, f["pta"], f["canonical"])


def _happy_response() -> str:
    return json.dumps({
        "product_type": "Damper Actuator",
        "product_type_alternatives": [],
        "attributes": [
            {"attribute": "INPUT_VOLTAGE",  "value": "24 vac",       "verbalized_confidence": 0.9, "rationale": "stated", "neighbor_ids": [10001]},
            {"attribute": "CONTROL_SIGNAL", "value": "0-10 vdc",     "verbalized_confidence": 0.8, "rationale": "stated", "neighbor_ids": [10001]},
            {"attribute": "MOUNTING",       "value": "spring return","verbalized_confidence": 0.9, "rationale": "stated", "neighbor_ids": [10001]},
            {"attribute": "RUN_TIME",       "value": "90 sec",       "verbalized_confidence": 0.7, "rationale": "stated", "neighbor_ids": [10001]}
        ]
    })


def test_happy_path_returns_well_formed_result():
    pack = _pack_for("Looking for a 24V damper motor with spring return, 0-10V, 90s")
    client = MockLLMClient(canned={"": _happy_response()})

    result = extract(client, pack)

    assert result.prediction.product_type == "Damper Actuator"
    assert {ap.attribute for ap in result.prediction.attributes} == {
        "INPUT_VOLTAGE", "CONTROL_SIGNAL", "MOUNTING", "RUN_TIME"
    }
    # No warnings on the happy path.
    assert result.validation_warnings == []
    # Provenance is populated.
    assert result.provenance.model == "mock/mock"
    assert len(result.provenance.prompt_hash) == 16
    assert len(result.provenance.grounding_hash) == 16


def test_provenance_hash_is_deterministic_across_runs():
    pack = _pack_for("Looking for a 24V damper motor with spring return, 0-10V, 90s")
    client = MockLLMClient(canned={"": _happy_response()})
    r1 = extract(client, pack)
    r2 = extract(client, pack)
    # Hashes depend only on the (system prompt, user prompt, grounding pack).
    assert r1.provenance.prompt_hash == r2.provenance.prompt_hash
    assert r1.provenance.grounding_hash == r2.provenance.grounding_hash


def test_out_of_vocab_value_demoted_to_insufficient_evidence():
    pack = _pack_for("Need a thermistor that clamps onto a pipe, 10K, outdoor")
    bad = json.dumps({
        "product_type": "Temperature Sensor",
        "product_type_alternatives": [],
        "attributes": [
            {"attribute": "PROBE_TYPE",     "value": "thermistor",       "verbalized_confidence": 0.9, "rationale": "ok",     "neighbor_ids": []},
            # NOT in the canonical set; should be demoted:
            {"attribute": "MOUNTING",       "value": "clamp",            "verbalized_confidence": 0.7, "rationale": "wrong",  "neighbor_ids": []},
            {"attribute": "RESISTANCE_OHM", "value": "10000",            "verbalized_confidence": 0.8, "rationale": "ok",     "neighbor_ids": []},
            {"attribute": "ENVIRONMENT",    "value": "outdoor",          "verbalized_confidence": 0.7, "rationale": "ok",     "neighbor_ids": []},
        ],
    })
    result = extract(MockLLMClient(canned={"": bad}), pack)
    mounting = next(a for a in result.prediction.attributes if a.attribute == "MOUNTING")
    assert mounting.value == INSUFFICIENT_EVIDENCE
    assert mounting.verbalized_confidence == 0.0
    assert any("value_out_of_vocab" in w for w in result.validation_warnings)


def test_out_of_vocab_product_type_snaps_to_candidate():
    pack = _pack_for("Need a thermistor that clamps onto a pipe, 10K, outdoor")
    assert "Temperature Sensor" in pack.candidate_product_types
    bad_pt = json.dumps({
        "product_type": "Made-Up Type",
        "product_type_alternatives": [],
        "attributes": [],
    })
    result = extract(MockLLMClient(canned={"": bad_pt}), pack)
    assert result.prediction.product_type in pack.candidate_product_types
    assert any("product_type_out_of_vocab" in w for w in result.validation_warnings)


def test_out_of_scope_attribute_dropped():
    pack = _pack_for("Need a thermistor that clamps onto a pipe, 10K, outdoor")
    out_of_scope = json.dumps({
        "product_type": "Temperature Sensor",
        "product_type_alternatives": [],
        "attributes": [
            {"attribute": "RUN_TIME", "value": "90 sec", "verbalized_confidence": 0.8, "rationale": "no", "neighbor_ids": []}
        ],
    })
    result = extract(MockLLMClient(canned={"": out_of_scope}), pack)
    assert all(a.attribute != "RUN_TIME" for a in result.prediction.attributes)
    assert any("attribute_out_of_scope_dropped" in w for w in result.validation_warnings)


def test_malformed_response_triggers_safe_abstention():
    pack = _pack_for("Looking for a 24V damper motor")
    result = extract(MockLLMClient(canned={"": "not even JSON {{{"}), pack)
    # We abstain rather than crash.
    assert result.prediction.attributes == []
    assert result.prediction.product_type in pack.candidate_product_types
    assert any("schema_validation_failed" in w for w in result.validation_warnings)
