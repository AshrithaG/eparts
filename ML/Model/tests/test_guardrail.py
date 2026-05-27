"""Layer 2 2A guardrail tests (V1 spec §4.2 Guardrail)."""
from __future__ import annotations

import pandas as pd
import pytest

from src.contracts import RuleHit, RuleTier
from src.layer2_rules.guardrail import ValidValueGuardrail, build_from_2a


@pytest.fixture
def guardrail() -> ValidValueGuardrail:
    return ValidValueGuardrail(
        [
            ("INPUT_VOLTAGE", "24"),
            ("INPUT_VOLTAGE", "120"),
            ("MOUNTING", "STRAP-ON"),
            ("MANUFACTURER", "Johnson Controls"),
        ]
    )


def test_valid_pair_returns_true(guardrail):
    assert guardrail.is_valid("INPUT_VOLTAGE", "24") is True
    assert guardrail.is_valid("input_voltage", "  24 ") is True


def test_invalid_pair_returns_false(guardrail):
    assert guardrail.is_valid("INPUT_VOLTAGE", "999") is False
    assert guardrail.is_valid("UNKNOWN_ATTR", "24") is False


def test_validate_keeps_valid_hits_unchanged(guardrail):
    hit = RuleHit(
        attribute_id=None,
        attribute_name="INPUT_VOLTAGE",
        predicted_value="24",
        unit_suffix="vac",
        conf_rule=0.65,
        tier=RuleTier.NUMERIC_UNIT,
        terminal=False,
    )
    out = guardrail.validate(hit)
    assert out is hit                                        # unchanged passthrough
    assert out.demoted_by_2a is False
    assert out.conf_rule == 0.65


def test_validate_demotes_invalid_hits(guardrail):
    hit = RuleHit(
        attribute_id=None,
        attribute_name="INPUT_VOLTAGE",
        predicted_value="999",
        unit_suffix="vac",
        conf_rule=0.65,
        tier=RuleTier.NUMERIC_UNIT,
        terminal=False,
    )
    out = guardrail.validate(hit)
    assert out.demoted_by_2a is True
    assert out.conf_rule == 0.0
    # Original hit is untouched (frozen dataclass).
    assert hit.demoted_by_2a is False


def test_terminal_part_number_hits_bypass_guardrail(guardrail):
    """Tier 1 hits carry no (attribute, value) claim and must never be demoted."""
    hit = RuleHit(
        attribute_id=None,
        attribute_name="",
        predicted_value="T-6000",
        unit_suffix=None,
        conf_rule=1.0,
        tier=RuleTier.EXACT_PART_NUMBER,
        terminal=True,
    )
    out = guardrail.validate(hit)
    assert out.conf_rule == 1.0
    assert out.demoted_by_2a is False


def test_validate_all_processes_iterable(guardrail):
    hits = [
        RuleHit(None, "INPUT_VOLTAGE", "24", "vac", 0.65, RuleTier.NUMERIC_UNIT, False),
        RuleHit(None, "INPUT_VOLTAGE", "999", "vac", 0.65, RuleTier.NUMERIC_UNIT, False),
    ]
    out = guardrail.validate_all(hits)
    assert out[0].demoted_by_2a is False
    assert out[1].demoted_by_2a is True


def test_build_from_2a_dataframe():
    df = pd.DataFrame(
        {
            "Attribute_Name": ["INPUT_VOLTAGE", "MOUNTING", None],
            "Value": ["24", "STRAP-ON", "X"],          # None Attr_Name dropped
        }
    )
    g = build_from_2a(df)
    assert g.size == 2
    assert g.is_valid("INPUT_VOLTAGE", "24") is True
    assert g.is_valid("MOUNTING", "STRAP-ON") is True


def test_build_from_2a_rejects_missing_columns():
    df = pd.DataFrame({"Attribute_Name": ["X"]})         # missing Value
    with pytest.raises(ValueError):
        build_from_2a(df)


def test_exempt_attribute_bypasses_2a_check():
    """Exempt attributes pass the guardrail even when their (A, v) is absent."""
    g = ValidValueGuardrail(
        valid_pairs=[("INPUT_VOLTAGE", "24")],
        exempt_attribute_names=["Manufacturer"],
    )
    mfg_hit = RuleHit(
        attribute_id=None,
        attribute_name="Manufacturer",
        predicted_value="Johnson Controls",
        unit_suffix=None,
        conf_rule=0.85,
        tier=RuleTier.MANUFACTURER_FUZZY,
        terminal=False,
    )
    out = g.validate(mfg_hit)
    assert out.demoted_by_2a is False
    assert out.conf_rule == 0.85


def test_build_from_2a_passes_exemptions(tmp_path):
    df = pd.DataFrame(
        {"Attribute_Name": ["INPUT_VOLTAGE"], "Value": ["24"]}
    )
    g = build_from_2a(df, exempt_attribute_names=["Manufacturer"])
    assert g.is_valid("Manufacturer", "anything") is False    # NOT in pairs
    # But validate() exempts it:
    mfg_hit = RuleHit(
        attribute_id=None,
        attribute_name="Manufacturer",
        predicted_value="Anything",
        unit_suffix=None,
        conf_rule=0.85,
        tier=RuleTier.MANUFACTURER_FUZZY,
        terminal=False,
    )
    assert g.validate(mfg_hit).demoted_by_2a is False
