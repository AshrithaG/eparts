"""CSV order-form extraction for Layer 1.

Implements V1_Engineering_Spec §4.1 "Parse CSV rows from order forms
directly by column".

Customer order CSVs vary in column naming. The :class:`CsvFieldMap` keeps
the mapping configurable; instantiate it from the customer's template and
pass it into :func:`extract_from_csv_row`. Anything outside the map is
ignored — Layer 2 / 3 cannot use fields they don't know about.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from ..config import UnitAliasMap
from ..contracts import ExtractedInput, SourceType
from .units import find_value_unit_pairs


@dataclass(frozen=True, slots=True)
class CsvFieldMap:
    """Column-name → structured-field mapping for a customer CSV template.

    Args:
        part_number: Source column carrying the manufacturer part number.
        manufacturer_name: Source column carrying the manufacturer name.
        description_columns: Ordered tuple of columns to concatenate into
            :attr:`ExtractedInput.text`. Missing columns are skipped silently.
        passthrough_fields: Additional ``source_col → structured_field_name``
            entries (e.g. ``"Voltage"`` → ``"voltage"``) preserved verbatim
            into :attr:`ExtractedInput.structured_fields`.
    """

    part_number: str | None = "Part_Number"
    manufacturer_name: str | None = "Manufacturer"
    description_columns: tuple[str, ...] = ("Short_Description", "Full_Description")
    passthrough_fields: Mapping[str, str] = field(default_factory=dict)


def _stringify(value: object) -> str:
    """Return a stripped string for any reasonable CSV cell value."""
    if value is None:
        return ""
    if isinstance(value, float) and value != value:   # NaN check
        return ""
    return str(value).strip()


def extract_from_csv_row(
    row: Mapping[str, object],
    aliases: UnitAliasMap,
    field_map: CsvFieldMap | None = None,
    source_ref: str | None = None,
) -> ExtractedInput:
    """Map a single CSV row to an :class:`ExtractedInput`.

    Args:
        row: Dict-like row (a pandas ``Series``, a ``csv.DictReader`` row, or
            a plain ``dict``). Keys are column names.
        aliases: Configured unit-alias map for downstream normalization.
        field_map: Column mapping. Defaults to the eParts test template
            column names; override per-customer at the caller.
        source_ref: Opaque identifier preserved on the result (e.g.
            ``"orders_2026Q1.csv:42"``).

    Returns:
        :class:`ExtractedInput` with ``source_type=SourceType.CSV``.
    """
    fmap = field_map or CsvFieldMap()

    structured: dict[str, str] = {}
    if fmap.part_number:
        pn = _stringify(row.get(fmap.part_number))
        if pn:
            structured["part_number"] = pn
    if fmap.manufacturer_name:
        mfg = _stringify(row.get(fmap.manufacturer_name))
        if mfg:
            structured["manufacturer_name"] = mfg
    for src_col, dst_field in fmap.passthrough_fields.items():
        v = _stringify(row.get(src_col))
        if v:
            structured[dst_field] = v

    description_parts = [
        _stringify(row.get(col))
        for col in fmap.description_columns
        if _stringify(row.get(col))
    ]
    text = " ".join(description_parts)

    normalized_units: dict[str, tuple[str, str]] = {}
    # CSV rows rarely embed value+unit pairs in description columns, but the
    # spec's Layer 2 Tier-3 path may still benefit when they do (e.g.
    # "24 VAC actuator"). Collect them under their ordinal so callers can
    # disambiguate by position.
    for i, pair in enumerate(find_value_unit_pairs(text, aliases)):
        normalized_units[f"value_unit_{i}"] = (pair.value, pair.unit)

    return ExtractedInput(
        source_type=SourceType.CSV,
        text=text,
        structured_fields=structured,
        normalized_units=normalized_units,
        source_ref=source_ref,
    )
