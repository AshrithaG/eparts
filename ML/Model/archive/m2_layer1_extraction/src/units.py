"""Unit normalization helpers for Layer 1.

Implements V1_Engineering_Spec §4.1 "Unit normalization map".

Canonical unit forms (``kohm``, ``vac``, ``vdc``, ``f``, ``c``) and their
aliases come from ``config/unit_aliases.yaml``. This module never hard-codes
unit strings — extending coverage means editing the YAML.

Public surface:
    :func:`normalize_unit`         alias → canonical form (or ``None``)
    :func:`find_value_unit_pairs`  scan text → list of ``(value, canonical)``
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

from ..config import UnitAliasMap

# Number scanner. Signed int / float; later combined with a window-based
# unit lookahead to keep matches non-greedy.
_NUMBER_RE = re.compile(r"(?<![A-Za-z\d])-?\d+(?:\.\d+)?")

# Maximum number of unit-side characters we'll consider after the number.
# Covers the longest alias in the YAML (e.g. "fahrenheit" = 10 chars).
_UNIT_WINDOW = 12


@dataclass(frozen=True, slots=True)
class ValueUnit:
    """One ``(value, canonical_unit)`` pair extracted from free text."""

    value: str
    unit: str
    span: tuple[int, int]   # character offsets in the source text


def normalize_unit(raw: str, aliases: UnitAliasMap) -> str | None:
    """Return the canonical form for a unit alias, or ``None`` if unknown.

    Lookup is case-insensitive and whitespace-collapsed.

    Args:
        raw: The raw unit string as it appears in input text (e.g. ``"V AC"``,
            ``"kΩ"``).
        aliases: The configured alias map (typically ``settings.unit_aliases``).

    Returns:
        Canonical form (e.g. ``"vac"``, ``"kohm"``) or ``None`` if the alias
        is not registered.
    """
    if not raw:
        return None
    key = " ".join(raw.lower().split())
    return aliases.alias_to_canonical.get(key)


def find_value_unit_pairs(
    text: str,
    aliases: UnitAliasMap,
) -> Iterator[ValueUnit]:
    """Yield ``(value, canonical_unit)`` pairs found in ``text``.

    For each numeric token, scan a fixed-width window immediately after it
    and pick the *longest* prefix that resolves to a canonical unit. This
    correctly handles multi-token aliases like ``"V AC"`` without slurping
    surrounding prose (``"VAC and the"`` would otherwise resolve).

    Args:
        text: Free-text input (email body, PDF text, etc.).
        aliases: Configured unit-alias map.

    Yields:
        :class:`ValueUnit` instances ordered by occurrence.
    """
    if not text:
        return
    for num_match in _NUMBER_RE.finditer(text):
        num_end = num_match.end()
        # Skip whitespace between number and unit (e.g. "24 VAC").
        i = num_end
        while i < len(text) and text[i] == " ":
            i += 1
        window = text[i : i + _UNIT_WINDOW]
        best_unit: str | None = None
        best_len = 0
        # Prefer the longest resolving prefix so "V AC" beats "V".
        for prefix_len in range(len(window), 0, -1):
            candidate = window[:prefix_len]
            # Trim a trailing word-boundary character so we never claim a
            # partial word; require what follows in the source to be a
            # word boundary.
            if prefix_len < len(window):
                next_char = window[prefix_len]
                if next_char.isalpha():
                    continue
            canonical = normalize_unit(candidate.rstrip(), aliases)
            if canonical is not None:
                best_unit = canonical
                best_len = prefix_len
                break
        if best_unit is None:
            continue
        yield ValueUnit(
            value=num_match.group(),
            unit=best_unit,
            span=(num_match.start(), i + best_len),
        )
