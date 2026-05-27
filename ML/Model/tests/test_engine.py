"""Layer 2 rule-engine integration tests (V1 spec §4.2 end-to-end)."""
from __future__ import annotations

import pandas as pd
import pytest

from src.config import RuleEngineConfig
from src.contracts import ExtractedInput, RuleTier, SourceType
from src.layer2_rules import (
    ManufacturerIndex,
    NumericMatcher,
    PartNumberIndex,
    RuleEngine,
    RuleEngineComponents,
    ValidValueGuardrail,
)


@pytest.fixture
def engine_cfg() -> RuleEngineConfig:
    return RuleEngineConfig(
        conf_exact_part_number=1.0,
        conf_manufacturer_fuzzy=0.85,
        conf_partial=0.65,
        conf_no_match=0.0,
        manufacturer_fuzzy_min_score=90,
    )


@pytest.fixture
def components() -> RuleEngineComponents:
    pn = PartNumberIndex(["T-6000", "LM24-3-T"])
    mfg = ManufacturerIndex(["Johnson Controls", "Honeywell"])
    numeric_df = pd.DataFrame(
        {
            "Attribute_Name": ["INPUT_VOLTAGE", "INPUT_VOLTAGE", "OPERATING_TEMP"],
            "Value": ["24", "120", "70"],
            "Unit_Suffix": ["vac", "vac", "f"],
        }
    )
    numeric = NumericMatcher(numeric_df)
    # Manufacturer is exempt — it's product metadata in 1B, not a 2A entry.
    guardrail = ValidValueGuardrail(
        [
            ("INPUT_VOLTAGE", "24"),
            ("INPUT_VOLTAGE", "120"),
            ("OPERATING_TEMP", "70"),
        ],
        exempt_attribute_names=("Manufacturer",),
    )
    return RuleEngineComponents(pn, mfg, numeric, guardrail)


@pytest.fixture
def engine(components, engine_cfg) -> RuleEngine:
    return RuleEngine(
        part_numbers=components.part_numbers,
        manufacturers=components.manufacturers,
        numeric=components.numeric,
        guardrail=components.guardrail,
        config=engine_cfg,
    )


def _x(text: str = "", **fields) -> ExtractedInput:
    """Helper: build an ExtractedInput with structured fields / units."""
    return ExtractedInput(
        source_type=SourceType.CSV,
        text=text,
        structured_fields=fields.pop("structured_fields", {}),
        normalized_units=fields.pop("normalized_units", {}),
    )


# ---------------------------------------------------------------------------
# Tier 1 — terminal behavior
# ---------------------------------------------------------------------------


def test_tier1_structured_part_number_terminates(engine):
    inp = _x(structured_fields={"part_number": "T-6000"})
    res = engine.apply(inp)
    assert res.terminated is True
    assert len(res.hits) == 1
    only = res.hits[0]
    assert only.tier == RuleTier.EXACT_PART_NUMBER
    assert only.conf_rule == 1.0
    assert only.terminal is True
    assert only.predicted_value == "T-6000"


def test_tier1_free_text_part_number_terminates(engine):
    inp = _x(text="Quote for LM24-3-T please")
    res = engine.apply(inp)
    assert res.terminated is True
    assert res.hits[0].predicted_value == "LM24-3-T"


def test_tier1_skips_other_tiers_when_terminal(engine):
    """When Tier 1 fires, manufacturer and numeric tiers must NOT run."""
    inp = _x(
        text="T-6000",
        structured_fields={"manufacturer_name": "Honeywell"},
        normalized_units={"v0": ("24", "vac")},
    )
    res = engine.apply(inp)
    assert res.terminated is True
    assert len(res.hits) == 1                                # only Tier 1


# ---------------------------------------------------------------------------
# Tier 2 — manufacturer fuzzy
# ---------------------------------------------------------------------------


def test_tier2_emits_manufacturer_hit(engine):
    inp = _x(structured_fields={"manufacturer_name": "johnson controls"})
    res = engine.apply(inp)
    assert res.terminated is False
    mfg_hits = [h for h in res.hits if h.tier == RuleTier.MANUFACTURER_FUZZY]
    assert len(mfg_hits) == 1
    assert mfg_hits[0].predicted_value == "Johnson Controls"
    assert mfg_hits[0].conf_rule == 0.85
    assert mfg_hits[0].attribute_name == "Manufacturer"


def test_tier2_no_manufacturer_field_no_hit(engine):
    inp = _x(text="generic search")
    res = engine.apply(inp)
    assert all(h.tier != RuleTier.MANUFACTURER_FUZZY for h in res.hits)


def test_tier2_below_threshold_no_hit(engine):
    inp = _x(structured_fields={"manufacturer_name": "Random Vendor Co"})
    res = engine.apply(inp)
    assert all(h.tier != RuleTier.MANUFACTURER_FUZZY for h in res.hits)


# ---------------------------------------------------------------------------
# Tier 3 — numeric + unit
# ---------------------------------------------------------------------------


def test_tier3_unique_value_unit_fires(engine):
    inp = _x(normalized_units={"v0": ("70", "f")})
    res = engine.apply(inp)
    numeric = [h for h in res.hits if h.tier == RuleTier.NUMERIC_UNIT]
    assert len(numeric) == 1
    assert numeric[0].attribute_name == "OPERATING_TEMP"
    assert numeric[0].predicted_value == "70"
    assert numeric[0].conf_rule == 0.65


def test_tier3_ambiguous_value_unit_suppressed(engine):
    """24 vac maps to both INPUT_VOLTAGE and OUTPUT_VOLTAGE in 2A; with our
    fixture only INPUT_VOLTAGE exists, so this also serves as the
    'matches-existing-attr' positive case."""
    # Build a fresh ambiguous fixture.
    numeric_df = pd.DataFrame(
        {
            "Attribute_Name": ["INPUT_VOLTAGE", "OUTPUT_VOLTAGE"],
            "Value": ["24", "24"],
            "Unit_Suffix": ["vac", "vac"],
        }
    )
    ambiguous = NumericMatcher(numeric_df)
    guardrail = ValidValueGuardrail(
        [("INPUT_VOLTAGE", "24"), ("OUTPUT_VOLTAGE", "24")]
    )
    eng_amb = RuleEngine(
        part_numbers=PartNumberIndex([]),
        manufacturers=ManufacturerIndex([]),
        numeric=ambiguous,
        guardrail=guardrail,
        config=RuleEngineConfig(1.0, 0.85, 0.65, 0.0, 90),
    )
    inp = _x(normalized_units={"v0": ("24", "vac")})
    res = eng_amb.apply(inp)
    # Ambiguous → engine emits nothing; Layer 3 will adjudicate.
    assert all(h.tier != RuleTier.NUMERIC_UNIT for h in res.hits)


# ---------------------------------------------------------------------------
# Guardrail — demotion path
# ---------------------------------------------------------------------------


def test_guardrail_passes_through_exempt_manufacturer_attr(engine):
    """Manufacturer is exempt from the 2A check — Tier 2 must always pass."""
    inp = _x(structured_fields={"manufacturer_name": "Honeywell"})
    res = engine.apply(inp)
    mfg_hits = [h for h in res.hits if h.tier == RuleTier.MANUFACTURER_FUZZY]
    assert len(mfg_hits) == 1
    assert mfg_hits[0].demoted_by_2a is False
    assert mfg_hits[0].conf_rule == 0.85


def test_guardrail_demotes_numeric_hit_absent_from_2a(engine_cfg):
    """A numeric (A, v) not in 2A is demoted (the spec's intended guard)."""
    pn = PartNumberIndex([])
    mfg = ManufacturerIndex([])
    # 2A has INPUT_VOLTAGE=24 only.
    df = pd.DataFrame(
        {
            "Attribute_Name": ["INPUT_VOLTAGE"],
            "Value": ["24"],
            "Unit_Suffix": ["vac"],
        }
    )
    numeric = NumericMatcher(df)
    # …but the guardrail's valid set is intentionally empty so Tier 3's hit
    # for INPUT_VOLTAGE=24 falls outside it.
    guardrail = ValidValueGuardrail([])
    engine = RuleEngine(pn, mfg, numeric, guardrail, engine_cfg)

    inp = _x(normalized_units={"v0": ("24", "vac")})
    res = engine.apply(inp)
    numeric_hits = [h for h in res.hits if h.tier == RuleTier.NUMERIC_UNIT]
    assert len(numeric_hits) == 1
    assert numeric_hits[0].demoted_by_2a is True
    assert numeric_hits[0].conf_rule == 0.0


# ---------------------------------------------------------------------------
# Empty input — graceful degradation
# ---------------------------------------------------------------------------


def test_empty_input_yields_empty_result(engine):
    res = engine.apply(_x())
    assert res.terminated is False
    assert res.hits == ()
