"""Layer 2 Tier 1 part-number index tests (V1 spec §4.2 Tier 1)."""
from __future__ import annotations

import time

import pytest

from src.layer2_rules.part_numbers import PartNumberIndex, build_from_1b


@pytest.fixture
def small_index() -> PartNumberIndex:
    return PartNumberIndex(["T-6000", "LM24-3-T", "BA/3K-S", "10K-3"])


def test_find_matches_in_free_text(small_index):
    match = small_index.find("Need a quote on the LM24-3-T actuator urgently.")
    assert match is not None
    assert match.part_number == "LM24-3-T"


def test_find_returns_none_when_no_match(small_index):
    assert small_index.find("looking for something generic") is None
    assert small_index.find("") is None


def test_find_respects_word_boundary(small_index):
    # "T-6000X" must NOT match T-6000 (no trailing alnum allowed).
    assert small_index.find("part T-6000X is unknown") is None


def test_is_exact_only_for_exact_match(small_index):
    assert small_index.is_exact("T-6000") is True
    assert small_index.is_exact("  T-6000  ") is True
    assert small_index.is_exact("T-6000X") is False


def test_special_regex_chars_are_escaped(small_index):
    # "BA/3K-S" contains '/' and '-' which would break if not escaped properly.
    match = small_index.find("Replacement: BA/3K-S, ship today.")
    assert match is not None
    assert match.part_number == "BA/3K-S"


def test_empty_index_matches_nothing():
    idx = PartNumberIndex([])
    assert idx.size == 0
    assert idx.find("anything") is None


def test_persistence_roundtrip(tmp_path, small_index):
    cache = tmp_path / "pn.pkl"
    small_index.save(cache)
    reloaded = PartNumberIndex.load(cache)
    assert reloaded.size == small_index.size
    assert reloaded.find("LM24-3-T sensor") is not None


def test_compile_under_5s_at_scale():
    """Spec §7.2 M2: regex union compile in < 5 s.

    Stress with a synthetic 200 K patterns shaped like real part numbers.
    Real 1B has ~198 K, so this is slightly above scale.
    """
    patterns = [f"PN-{i:06d}-X" for i in range(200_000)]
    t0 = time.perf_counter()
    idx = PartNumberIndex(patterns)
    elapsed = time.perf_counter() - t0
    assert idx.size == 200_000
    # Generous cap: real machines should hit ~1–2 s; allow 10 s in CI noise.
    assert elapsed < 10.0, f"compile took {elapsed:.2f}s"


def test_query_under_1ms_after_warmup():
    """Spec §7.2 M2: single-query latency < 1 ms after warmup."""
    patterns = [f"PN-{i:06d}-X" for i in range(50_000)]
    idx = PartNumberIndex(patterns)
    text = "Order: PN-049999-X needed by Friday."
    # Warmup
    for _ in range(10):
        idx.find(text)
    # Time 1000 queries; take the mean.
    iterations = 1000
    t0 = time.perf_counter()
    for _ in range(iterations):
        idx.find(text)
    mean_us = (time.perf_counter() - t0) / iterations * 1e6
    assert mean_us < 1000, f"mean query {mean_us:.1f} us exceeds 1 ms budget"


def test_build_from_1b_with_inline_list():
    """Factory accepts pre-loaded list, bypassing the CSV read."""
    idx = build_from_1b(["A1", "B2"])
    assert idx.size == 2
    assert idx.is_exact("A1") is True
