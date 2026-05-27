"""Layer 2 Tier 2 manufacturer-match tests (V1 spec §4.2 Tier 2)."""
from __future__ import annotations

import pytest

from src.layer2_rules.manufacturers import ManufacturerIndex


@pytest.fixture
def index() -> ManufacturerIndex:
    return ManufacturerIndex(
        [
            "Johnson Controls",
            "Honeywell",
            "Belimo",
            "Siemens",
            "ACME Industrial",
        ]
    )


def test_exact_name_returns_max_score(index):
    match = index.best_match("Johnson Controls", min_score=90)
    assert match is not None
    assert match.canonical_name == "Johnson Controls"
    assert match.score >= 99.0


def test_token_set_handles_word_order(index):
    """token_set_ratio treats word order as irrelevant — spec §4.2 Tier 2."""
    match = index.best_match("Controls Johnson", min_score=90)
    assert match is not None
    assert match.canonical_name == "Johnson Controls"


def test_below_threshold_returns_none(index):
    assert index.best_match("Random Vendor LLC", min_score=90) is None


def test_partial_match_below_min_score_drops(index):
    # "Johnson" alone token_set vs "Johnson Controls" scores 100 (subset),
    # so we test a partial like "Jonson Controll" instead to undercut.
    match = index.best_match("Jonson Controll", min_score=95)
    # Below the 95 ceiling — score sits around 85–90 depending on rapidfuzz version.
    assert match is None


def test_empty_candidate_returns_none(index):
    assert index.best_match("", min_score=90) is None


def test_empty_index_returns_none():
    idx = ManufacturerIndex([])
    assert idx.size == 0
    assert idx.best_match("Honeywell", min_score=90) is None
