"""M2: rule-engine demo against synthetic ``ExtractedInput`` payloads.

This script demonstrates Layer 2 in isolation by **building
``ExtractedInput`` instances directly**, mimicking the handoff shape that
the extraction sub-team will produce in production. Useful as:

  * A worked example for the extraction team — every payload in
    ``SAMPLE_INPUTS`` is the exact shape Layer 2 expects to receive.
  * A smoke test for Layer 2 against real ``1B + 2A`` data.

See ``eparts_doc/ExtractionHandoff_Spec.md`` for the formal contract.

Usage:
    py scripts/m2_rule_engine_demo.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config import load_settings
from src.contracts import ExtractedInput, RuleEngineResult, SourceType
from src.layer2_rules import build_rule_engine, build_rule_engine_components


# Synthetic payloads in the exact shape we expect from the extraction team.
# Each entry corresponds to one customer request after their pipeline runs.
SAMPLE_INPUTS: list[ExtractedInput] = [
    ExtractedInput(
        source_type=SourceType.CSV,
        text="Temperature sensor 24 VAC strap-on. Thermistor probe for HVAC pipe mounting.",
        structured_fields={
            "part_number": "T-6000",                      # synthetic — not in real 1B
            "manufacturer_name": "Johnson Controls",
        },
        normalized_units={"value_unit_0": ("24", "vac")},
        source_ref="orders_2026Q1.csv:1",
    ),
    ExtractedInput(
        source_type=SourceType.CSV,
        text="Damper actuator 24 VAC 0-10 VDC control",
        structured_fields={"manufacturer_name": "honeywell"},        # fuzzy → Honeywell
        normalized_units={
            "value_unit_0": ("24", "vac"),
            "value_unit_1": ("10", "vdc"),
        },
        source_ref="orders_2026Q1.csv:2",
    ),
    ExtractedInput(
        source_type=SourceType.CSV,
        text="Generic widget at 70 deg F",
        structured_fields={"manufacturer_name": "Random Vendor Co"},  # below threshold
        normalized_units={"value_unit_0": ("70", "f")},
        source_ref="orders_2026Q1.csv:3",
    ),
    ExtractedInput(
        source_type=SourceType.EMAIL,
        text="Need pricing on the Johnson Controls thermistor. Wiring is 24 VAC.",
        structured_fields={},                                         # extraction team chose to leave empty
        normalized_units={"value_unit_0": ("24", "vac")},
        source_ref="msg:demo-001",
    ),
]


def _fmt_result(result: RuleEngineResult) -> str:
    lines = [f"  terminated={result.terminated}, hits={len(result.hits)}"]
    for h in result.hits:
        flags = []
        if h.terminal:
            flags.append("TERMINAL")
        if h.demoted_by_2a:
            flags.append("DEMOTED_2A")
        flag_str = f" [{','.join(flags)}]" if flags else ""
        lines.append(
            f"    · tier={h.tier.value:<22} attr={h.attribute_name!r:<22} "
            f"val={h.predicted_value!r:<26} conf={h.conf_rule:.2f}{flag_str}"
        )
    return "\n".join(lines)


def main() -> None:
    settings = load_settings()

    print("Building rule-engine components from 1B + 2A (slow disk reads) ...")
    t0 = time.perf_counter()
    components = build_rule_engine_components()
    build_secs = time.perf_counter() - t0
    print(
        f"  built in {build_secs:.2f}s: "
        f"{components.part_numbers.size:,} part numbers, "
        f"{components.manufacturers.size:,} manufacturers, "
        f"{components.guardrail.size:,} (attr,value) pairs"
    )

    engine = build_rule_engine(components=components, config=settings.thresholds.rule_engine)

    print()
    for i, payload in enumerate(SAMPLE_INPUTS):
        print(f"[{i}] source={payload.source_type.value:<10} ref={payload.source_ref!r}")
        print(f"     text  : {payload.text[:78]!r}")
        print(f"     fields: {dict(payload.structured_fields)}")
        print(f"     units : {dict(payload.normalized_units)}")
        result = engine.apply(payload)
        print(_fmt_result(result))
        print()


if __name__ == "__main__":
    main()
