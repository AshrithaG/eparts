"""Layer 1 dispatch (extract) tests (V1 spec §4.1)."""
from __future__ import annotations

import pytest

from src.contracts import SourceType
from src.layer1_extraction import extract


def test_dispatch_csv(aliases):
    row = {"Part_Number": "ABC", "Short_Description": "24 VAC actuator"}
    result = extract(row, SourceType.CSV, aliases=aliases)
    assert result.source_type == SourceType.CSV
    assert result.structured_fields["part_number"] == "ABC"


def test_dispatch_email(aliases):
    raw = (
        b"From: a@b.test\r\nTo: c@d.test\r\nSubject: Test\r\n"
        b"Content-Type: text/plain\r\n\r\nNeed 12 VDC pump.\r\n"
    )
    result = extract(raw, SourceType.EMAIL, aliases=aliases)
    assert result.source_type == SourceType.EMAIL
    assert "pump" in result.text


def test_dispatch_pdf_bytes(synthetic_pdf_bytes, aliases):
    result = extract(synthetic_pdf_bytes, SourceType.PDF_TEXT, aliases=aliases)
    assert result.source_type == SourceType.PDF_TEXT
    assert "T-6000" in result.text


def test_dispatch_unsupported_source_type_raises(aliases):
    with pytest.raises(ValueError):
        extract({"x": 1}, "fax", aliases=aliases)   # type: ignore[arg-type]


def test_dispatch_payload_type_mismatch_raises(aliases):
    with pytest.raises(TypeError):
        extract(b"not-a-row", SourceType.CSV, aliases=aliases)
    with pytest.raises(TypeError):
        extract({"row": 1}, SourceType.PDF_TEXT, aliases=aliases)
    with pytest.raises(TypeError):
        extract({"row": 1}, SourceType.EMAIL, aliases=aliases)
