"""Layer 1 unit-normalization regression tests (V1 spec §4.1)."""
from __future__ import annotations

import pytest

from src.config import load_settings
from src.layer1_extraction import find_value_unit_pairs, normalize_unit


@pytest.fixture(scope="module")
def aliases():
    return load_settings().unit_aliases


# The §4.1 regression set — every canonical form must be covered by at
# least one alias variant the unit-normalization map promises to handle.
NORMALIZATION_CASES = [
    ("kohm", "kohm"),
    ("kΩ", "kohm"),
    ("kilo ohm", "kohm"),
    ("VAC", "vac"),
    ("V AC", "vac"),
    ("volts AC", "vac"),
    ("VDC", "vdc"),
    ("°F", "f"),
    ("deg C", "c"),
    ("Fahrenheit", "f"),
]


@pytest.mark.parametrize("raw, canonical", NORMALIZATION_CASES)
def test_normalize_unit_canonical_forms(aliases, raw, canonical):
    assert normalize_unit(raw, aliases) == canonical


def test_normalize_unit_unknown_returns_none(aliases):
    assert normalize_unit("widgets", aliases) is None
    assert normalize_unit("", aliases) is None


def test_normalize_unit_is_whitespace_insensitive(aliases):
    assert normalize_unit("  V   AC ", aliases) == "vac"


def test_find_value_unit_pairs_basic(aliases):
    text = "Input is 24 VAC and the output is 10 VDC at room temperature 70 deg F."
    pairs = list(find_value_unit_pairs(text, aliases))
    assert [(p.value, p.unit) for p in pairs] == [
        ("24", "vac"),
        ("10", "vdc"),
        ("70", "f"),
    ]


def test_find_value_unit_pairs_ignores_unknown_units(aliases):
    text = "Weight 30 lbs, voltage 12 VDC."
    pairs = list(find_value_unit_pairs(text, aliases))
    # "lbs" is not in the alias map, so only the VDC pair survives.
    assert [(p.value, p.unit) for p in pairs] == [("12", "vdc")]


def test_find_value_unit_pairs_handles_empty_text(aliases):
    assert list(find_value_unit_pairs("", aliases)) == []
