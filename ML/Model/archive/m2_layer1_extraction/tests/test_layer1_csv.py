"""Layer 1 CSV extraction tests (V1 spec §4.1)."""
from __future__ import annotations

import pandas as pd

from src.contracts import SourceType
from src.layer1_extraction import CsvFieldMap, extract_from_csv_row


def test_csv_extracts_structured_fields_and_text(aliases):
    row = {
        "Part_Number": "T-6000",
        "Manufacturer": "Johnson Controls",
        "Short_Description": "Temperature sensor 24 VAC",
        "Full_Description": "Strap-on thermistor for HVAC pipe mounting.",
    }
    result = extract_from_csv_row(row, aliases=aliases, source_ref="row:1")
    assert result.source_type == SourceType.CSV
    assert result.structured_fields["part_number"] == "T-6000"
    assert result.structured_fields["manufacturer_name"] == "Johnson Controls"
    assert "thermistor" in result.text.lower()
    assert result.normalized_units == {"value_unit_0": ("24", "vac")}
    assert result.source_ref == "row:1"


def test_csv_accepts_pandas_series(aliases):
    df = pd.DataFrame([{"Part_Number": "X1", "Short_Description": "Pump 12 VDC"}])
    result = extract_from_csv_row(df.iloc[0], aliases=aliases)
    assert result.structured_fields == {"part_number": "X1"}
    assert result.normalized_units == {"value_unit_0": ("12", "vdc")}


def test_csv_field_map_passthrough(aliases):
    field_map = CsvFieldMap(
        part_number=None,                                # customer doesn't carry one
        manufacturer_name=None,
        description_columns=("Item_Description",),
        passthrough_fields={"Customer_PO": "po_number", "Voltage": "voltage"},
    )
    row = {"Item_Description": "Damper actuator", "Customer_PO": "PO-9001", "Voltage": "24 VAC"}
    result = extract_from_csv_row(row, aliases=aliases, field_map=field_map)
    assert result.structured_fields == {"po_number": "PO-9001", "voltage": "24 VAC"}
    assert "actuator" in result.text


def test_csv_ignores_blank_and_nan_cells(aliases):
    row = {"Part_Number": "", "Manufacturer": None, "Short_Description": "Heat exchanger"}
    result = extract_from_csv_row(row, aliases=aliases)
    assert "part_number" not in result.structured_fields
    assert "manufacturer_name" not in result.structured_fields
    assert result.text == "Heat exchanger"


def test_csv_missing_description_columns_yields_empty_text(aliases):
    row = {"Part_Number": "Z9", "Manufacturer": "ACME"}
    result = extract_from_csv_row(row, aliases=aliases)
    assert result.text == ""
    assert result.structured_fields == {"part_number": "Z9", "manufacturer_name": "ACME"}
