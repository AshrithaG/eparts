"""Layer 2 Tier 3 numeric-match tests (V1 spec §4.2 Tier 3)."""
from __future__ import annotations

import pandas as pd
import pytest

from src.layer2_rules.numeric_match import NumericMatcher, collect_value_unit_pairs


@pytest.fixture
def matcher() -> NumericMatcher:
    df = pd.DataFrame(
        {
            "Attribute_Name": [
                "INPUT_VOLTAGE",
                "INPUT_VOLTAGE",
                "OUTPUT_VOLTAGE",
                "OPERATING_TEMP",
            ],
            "Value": ["24", "120", "24", "70"],
            "Unit_Suffix": ["vac", "vac", "vac", "f"],
        }
    )
    return NumericMatcher(df)


def test_match_by_attribute_hits_exact_triple(matcher):
    hit = matcher.match_by_attribute("INPUT_VOLTAGE", "24", "vac")
    assert hit is not None
    assert hit.attribute_name == "INPUT_VOLTAGE"
    assert hit.value == "24"
    assert hit.unit == "vac"
    assert hit.ambiguity == 1


def test_match_by_attribute_returns_none_for_invalid(matcher):
    assert matcher.match_by_attribute("INPUT_VOLTAGE", "999", "vac") is None
    assert matcher.match_by_attribute("UNKNOWN_ATTR", "24", "vac") is None


def test_match_by_attribute_is_case_and_whitespace_tolerant(matcher):
    hit = matcher.match_by_attribute("  input_voltage ", "24", "VAC")
    assert hit is not None
    assert hit.attribute_name == "INPUT_VOLTAGE"


def test_match_by_value_unit_returns_all_candidates(matcher):
    """24 vac maps to both INPUT_VOLTAGE and OUTPUT_VOLTAGE → ambiguity=2."""
    hits = matcher.match_by_value_unit("24", "vac")
    names = {h.attribute_name for h in hits}
    assert names == {"INPUT_VOLTAGE", "OUTPUT_VOLTAGE"}
    assert all(h.ambiguity == 2 for h in hits)


def test_match_by_value_unit_uniqueness(matcher):
    """70 f maps to OPERATING_TEMP only → ambiguity=1."""
    hits = matcher.match_by_value_unit("70", "f")
    assert len(hits) == 1
    assert hits[0].attribute_name == "OPERATING_TEMP"
    assert hits[0].ambiguity == 1


def test_match_by_value_unit_no_match_returns_empty(matcher):
    assert matcher.match_by_value_unit("9999", "vac") == ()


def test_collect_value_unit_pairs_iterates():
    pairs = list(
        collect_value_unit_pairs(
            {"value_unit_0": ("24", "vac"), "value_unit_1": ("12", "vdc")}
        )
    )
    assert pairs == [("24", "vac"), ("12", "vdc")]


def test_collect_value_unit_pairs_skips_blanks():
    pairs = list(
        collect_value_unit_pairs({"v0": ("", "vac"), "v1": ("24", ""), "v2": ("12", "vdc")})
    )
    assert pairs == [("12", "vdc")]


def test_constructor_rejects_missing_columns():
    df = pd.DataFrame({"Attribute_Name": ["A"], "Value": ["v"]})  # missing Unit_Suffix
    with pytest.raises(ValueError):
        NumericMatcher(df)
