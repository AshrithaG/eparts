"""Demo driver — runs each fixture scenario end-to-end and prints the result.

Usage:
    python scripts/run_example.py                # all scenarios, real LLM
    python scripts/run_example.py --mock         # canned responses, no Ollama
    python scripts/run_example.py --scenario 2   # only scenario id=2
    python scripts/run_example.py --config path/to/model.yaml

The mock mode is intended for CI and for trying the pipeline before
Ollama is installed. It returns a hand-written response per scenario
that exercises every code path in `extract()` — including a
deliberately out-of-vocab value in scenario 4 to demonstrate the
closed-vocabulary post-validator demoting it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Make the package importable when run as a script.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from llm_layer3 import (  # noqa: E402
    build_client,
    build_grounding_pack,
    extract,
    load_fixtures,
    retrieve_top_k_stub,
)


# Canned responses keyed by a unique substring from each scenario's query.
# These let the demo run without Ollama and exercise:
#   - happy-path extraction (scenarios 1, 2)
#   - ambiguous PT (scenario 3 — model picks the first candidate)
#   - sparse input with a deliberately out-of-vocab value (scenario 4)
MOCK_CANNED: dict[str, str] = {
    "damper motor with spring return": json.dumps({
        "product_type": "Damper Actuator",
        "product_type_alternatives": [],
        "attributes": [
            {"attribute": "INPUT_VOLTAGE",  "value": "24 vac",      "verbalized_confidence": 0.92, "rationale": "Customer says '24V'.", "neighbor_ids": [10001, 10002]},
            {"attribute": "CONTROL_SIGNAL", "value": "0-10 vdc",    "verbalized_confidence": 0.88, "rationale": "Customer says '0-10V signal'.", "neighbor_ids": [10001]},
            {"attribute": "MOUNTING",       "value": "spring return","verbalized_confidence": 0.95, "rationale": "Stated explicitly.", "neighbor_ids": [10001, 10002, 10003]},
            {"attribute": "RUN_TIME",       "value": "90 sec",      "verbalized_confidence": 0.80, "rationale": "Customer says ~90s.", "neighbor_ids": [10001]}
        ]
    }),
    "clamps onto a pipe": json.dumps({
        "product_type": "Temperature Sensor",
        "product_type_alternatives": [],
        "attributes": [
            {"attribute": "PROBE_TYPE",     "value": "thermistor", "verbalized_confidence": 0.95, "rationale": "Customer says 'thermistor'.", "neighbor_ids": [20001]},
            {"attribute": "MOUNTING",       "value": "strap-on",   "verbalized_confidence": 0.88, "rationale": "'Clamps onto a pipe' = strap-on.", "neighbor_ids": [20001, 20003]},
            {"attribute": "RESISTANCE_OHM", "value": "10000",      "verbalized_confidence": 0.90, "rationale": "'10K' = 10000 ohm.", "neighbor_ids": [20001, 20002]},
            {"attribute": "ENVIRONMENT",    "value": "outdoor",    "verbalized_confidence": 0.75, "rationale": "'Outdoor air handler'.", "neighbor_ids": [20001, 20003]}
        ]
    }),
    "Johnson Controls T-6000": json.dumps({
        "product_type": "Temperature Sensor",
        "product_type_alternatives": ["Thermostat"],
        "attributes": [
            {"attribute": "PROBE_TYPE",     "value": "thermistor",             "verbalized_confidence": 0.40, "rationale": "T-6000 thermistor exists but T-6000 thermostat also exists.", "neighbor_ids": [20004]},
            {"attribute": "MOUNTING",       "value": "insufficient_evidence",  "verbalized_confidence": 0.0,  "rationale": "Ambiguous between sensor immersion and thermostat wall mount.", "neighbor_ids": []},
            {"attribute": "RESISTANCE_OHM", "value": "10000",                  "verbalized_confidence": 0.40, "rationale": "Standard for T-6000 series.", "neighbor_ids": [20004]},
            {"attribute": "ENVIRONMENT",    "value": "insufficient_evidence",  "verbalized_confidence": 0.0,  "rationale": "Not stated.", "neighbor_ids": []}
        ]
    }),
    "HVAC pipe temperature monitoring": json.dumps({
        "product_type": "Temperature Sensor",
        "product_type_alternatives": ["Thermostat"],
        "attributes": [
            {"attribute": "PROBE_TYPE",     "value": "thermistor",            "verbalized_confidence": 0.55, "rationale": "Most common HVAC pipe-monitoring probe.", "neighbor_ids": [20001, 20002]},
            {"attribute": "MOUNTING",       "value": "clamp",                 "verbalized_confidence": 0.50, "rationale": "DELIBERATELY OUT-OF-VOCAB to test the post-validator.", "neighbor_ids": [20001]},
            {"attribute": "RESISTANCE_OHM", "value": "10000",                 "verbalized_confidence": 0.45, "rationale": "Most common 10K thermistor.", "neighbor_ids": [20001, 20002]},
            {"attribute": "ENVIRONMENT",    "value": "insufficient_evidence", "verbalized_confidence": 0.0,  "rationale": "Not stated.", "neighbor_ids": []}
        ]
    })
}


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_scenario(scenario: dict[str, Any], fixtures: dict[str, Any], client, top_k: int) -> None:
    print("=" * 78)
    print(f"Scenario {scenario['id']}: {scenario['name']}")
    print(f"Query: {scenario['query']}")
    print("-" * 78)

    neighbors = retrieve_top_k_stub(scenario["query"], fixtures["catalog"], k=top_k)
    pack = build_grounding_pack(
        query=scenario["query"],
        neighbors=neighbors,
        product_type_attributes=fixtures["pta"],
        canonical_values=fixtures["canonical"],
    )

    print(f"Retrieved {len(pack.top_k_neighbors)} neighbors; "
          f"candidate PTs: {pack.candidate_product_types}")

    result = extract(client, pack)

    print(f"Predicted PT: {result.prediction.product_type}")
    if result.prediction.product_type_alternatives:
        print(f"Alternatives: {result.prediction.product_type_alternatives}")
    print("Attributes:")
    for ap in result.prediction.attributes:
        print(f"  {ap.attribute:18} = {ap.value:30}  (conf={ap.verbalized_confidence:.2f})")
        if ap.rationale:
            print(f"    rationale: {ap.rationale}")
    if result.validation_warnings:
        print("Validation warnings:")
        for w in result.validation_warnings:
            print(f"  - {w}")
    print("Provenance:")
    print(f"  model        : {result.provenance.model}")
    print(f"  prompt_hash  : {result.provenance.prompt_hash}")
    print(f"  grounding_h  : {result.provenance.grounding_hash}")
    print(f"  timestamp    : {result.provenance.timestamp}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "model.yaml")
    parser.add_argument("--fixtures", type=Path, default=ROOT / "data" / "fixtures")
    parser.add_argument("--mock", action="store_true", help="Force mock backend (no Ollama needed).")
    parser.add_argument("--scenario", type=int, default=None, help="Run only this scenario id.")
    args = parser.parse_args()

    fixtures = load_fixtures(args.fixtures)

    config = load_config(args.config)
    if args.mock:
        config = {**config, "backend": "mock"}

    if config.get("backend") == "mock":
        from llm_layer3 import MockLLMClient
        client = MockLLMClient(canned=MOCK_CANNED, model=config.get("model", "mock"))
    else:
        try:
            client = build_client(config)
        except Exception as e:  # noqa: BLE001 - print actionable error
            print(f"\nFailed to build client: {e}\n", file=sys.stderr)
            print("Hint: pass --mock to run without a local model, or install Ollama "
                  "and `ollama pull {}`.".format(config.get("model", "qwen2.5:7b-instruct")),
                  file=sys.stderr)
            return 2

    top_k = int(config.get("top_k", 5))

    selected = fixtures["scenarios"]
    if args.scenario is not None:
        selected = [s for s in selected if s["id"] == args.scenario]
        if not selected:
            print(f"No scenario with id={args.scenario}", file=sys.stderr)
            return 1

    for scenario in selected:
        run_scenario(scenario, fixtures, client, top_k)
    return 0


if __name__ == "__main__":
    sys.exit(main())
