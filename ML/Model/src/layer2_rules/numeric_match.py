"""Layer 2 Tier 3 — numeric value + unit match.

Implements V1_Engineering_Spec §4.2 Tier 3:

    Use 1A's DigitalValue, RangeLow, RangeHigh, and Unit_Suffix columns
    directly. Never regex-extract a numeric attribute from free text when
    the structured column is available.

The "structured column" the spec refers to is a customer-side CSV column
(e.g. ``Voltage`` on an order form). When the customer ships a structured
hint, Tier 3 trusts that hint and validates the value against 2A. When
only free-text extraction (:attr:`ExtractedInput.normalized_units`) is
available, Tier 3 is conservative: it emits a hit *only* if the
``(value, canonical_unit)`` combination uniquely identifies one attribute
in 2A — otherwise the prediction is too ambiguous and Layer 3 should
adjudicate.

Output confidence is :attr:`RuleEngineConfig.conf_partial` (default 0.65)
because Tier 3 is not as strong as Tier 1's terminal exact match.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import pandas as pd


@dataclass(frozen=True, slots=True)
class NumericHit:
    """Candidate ``(attribute, value, unit)`` resolution from Tier 3.

    Args:
        attribute_name: Resolved 2A attribute name.
        value: Value as it appears in 2A (display string).
        unit: Canonical unit (matches the YAML canonical form, lower-case).
        ambiguity: 1 when uniquely resolved, > 1 when multiple attributes
            shared the same ``(value, unit)``. Engine emits one hit per
            candidate; reviewer disambiguates.
    """

    attribute_name: str
    value: str
    unit: str
    ambiguity: int


class NumericMatcher:
    """Index over 2A keyed by ``(value, unit)`` and by ``(attribute_name, ...)``.

    The index is built from the *2A* table because 2A is the closed list
    of valid attribute values — by construction every Tier 3 hit also
    passes the 2A guardrail.
    """

    def __init__(self, values_df: pd.DataFrame) -> None:
        required = {"Attribute_Name", "Value", "Unit_Suffix"}
        missing = required - set(values_df.columns)
        if missing:
            raise ValueError(f"2A frame is missing required columns: {missing}")

        # Normalize once for fast lookup.
        df = values_df[["Attribute_Name", "Value", "Unit_Suffix"]].dropna(
            subset=["Attribute_Name", "Value"]
        ).copy()
        df["_attr_norm"] = df["Attribute_Name"].astype(str).str.strip().str.lower()
        df["_value_norm"] = df["Value"].astype(str).str.strip().str.lower()
        df["_unit_norm"] = df["Unit_Suffix"].fillna("").astype(str).str.strip().str.lower()

        # Map (value, unit) → list of attribute names.
        self._by_value_unit: dict[tuple[str, str], list[str]] = {}
        for attr_norm, value_norm, unit_norm, attr_orig, value_orig in zip(
            df["_attr_norm"],
            df["_value_norm"],
            df["_unit_norm"],
            df["Attribute_Name"].astype(str),
            df["Value"].astype(str),
            strict=False,
        ):
            self._by_value_unit.setdefault(
                (value_norm, unit_norm), []
            ).append(attr_orig)

        # Map attribute_name_norm → set of (value, unit) tuples it accepts.
        self._by_attribute: dict[str, set[tuple[str, str]]] = {}
        for attr_norm, value_norm, unit_norm in zip(
            df["_attr_norm"], df["_value_norm"], df["_unit_norm"], strict=False
        ):
            self._by_attribute.setdefault(attr_norm, set()).add((value_norm, unit_norm))

        # Map (attribute_norm, value_norm, unit_norm) → display value, attribute_name as in 2A.
        self._canonical: dict[tuple[str, str, str], tuple[str, str]] = {
            (attr_norm, value_norm, unit_norm): (attr_orig, value_orig)
            for attr_norm, value_norm, unit_norm, attr_orig, value_orig in zip(
                df["_attr_norm"],
                df["_value_norm"],
                df["_unit_norm"],
                df["Attribute_Name"].astype(str),
                df["Value"].astype(str),
                strict=False,
            )
        }

    @staticmethod
    def _norm(s: str) -> str:
        return " ".join(str(s or "").strip().lower().split())

    def match_by_attribute(
        self,
        attribute_hint: str,
        value: str,
        unit: str,
    ) -> NumericHit | None:
        """Resolve a ``(attribute_hint, value, unit)`` triple via 2A.

        Used when the customer's CSV has a column named after a known
        attribute. Returns ``None`` when the triple is not present in 2A.
        """
        attr_norm = self._norm(attribute_hint)
        value_norm = self._norm(value)
        unit_norm = self._norm(unit)
        canonical = self._canonical.get((attr_norm, value_norm, unit_norm))
        if canonical is None:
            return None
        return NumericHit(
            attribute_name=canonical[0],
            value=canonical[1],
            unit=unit_norm,
            ambiguity=1,
        )

    def match_by_value_unit(
        self,
        value: str,
        unit: str,
    ) -> tuple[NumericHit, ...]:
        """Resolve a ``(value, unit)`` pair via 2A when no attribute hint exists.

        Returns hits ordered by attribute name. Length > 1 means the pair
        was ambiguous across multiple attributes; the engine still emits
        them all (with ``ambiguity > 1``) so reviewers can choose.
        """
        value_norm = self._norm(value)
        unit_norm = self._norm(unit)
        candidates = self._by_value_unit.get((value_norm, unit_norm), [])
        if not candidates:
            return ()
        ambiguity = len(candidates)
        hits = []
        for attr_orig in candidates:
            canonical = self._canonical[(self._norm(attr_orig), value_norm, unit_norm)]
            hits.append(
                NumericHit(
                    attribute_name=canonical[0],
                    value=canonical[1],
                    unit=unit_norm,
                    ambiguity=ambiguity,
                )
            )
        return tuple(hits)


def collect_value_unit_pairs(
    normalized_units: Mapping[str, tuple[str, str]] | None,
) -> Iterable[tuple[str, str]]:
    """Iterate the ``(value, unit)`` pairs from an :class:`ExtractedInput`."""
    if not normalized_units:
        return
    for value, unit in normalized_units.values():
        if value and unit:
            yield value, unit


def build_from_2a(values_df: pd.DataFrame | None = None) -> NumericMatcher:
    """Build :class:`NumericMatcher` from the 2A table.

    Args:
        values_df: Pre-loaded 2A DataFrame. When ``None`` loads from disk.
    """
    if values_df is None:
        from ..data import load_values_per_attribute
        values_df = load_values_per_attribute()
    return NumericMatcher(values_df)
