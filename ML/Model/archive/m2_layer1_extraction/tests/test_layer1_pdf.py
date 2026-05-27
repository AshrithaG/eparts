"""Layer 1 PDF extraction tests (V1 spec §4.1).

OCR fallback tests are skipped when the tesseract system binary is absent;
they exercise the rasterize+OCR branch when available.
"""
from __future__ import annotations

import importlib.util

import pytest

from src.contracts import SourceType
from src.layer1_extraction import PdfExtractionConfig, extract_from_pdf
from src.layer1_extraction.pdf_input import locate_tesseract


def test_pdf_text_path_pulls_embedded_text(synthetic_pdf_bytes, aliases):
    result = extract_from_pdf(synthetic_pdf_bytes, aliases=aliases, source_ref="syn.pdf")
    assert result.source_type == SourceType.PDF_TEXT
    assert "T-6000" in result.text
    assert "Johnson Controls" in result.text
    # 24 VAC, 0-10 VDC (yields "0" then "10"), 70 deg F → 4 pairs
    units_found = {(p[0], p[1]) for p in result.normalized_units.values()}
    assert ("24", "vac") in units_found
    assert ("10", "vdc") in units_found
    assert ("70", "f") in units_found
    assert result.source_ref == "syn.pdf"


def test_pdf_with_allow_ocr_false_returns_text_path(synthetic_pdf_bytes, aliases):
    """allow_ocr=False must never raise even on sparse pages."""
    result = extract_from_pdf(synthetic_pdf_bytes, aliases=aliases, allow_ocr=False)
    assert result.source_type == SourceType.PDF_TEXT


def _has_tesseract() -> bool:
    if importlib.util.find_spec("pytesseract") is None:
        return False
    return locate_tesseract() is not None


@pytest.mark.skipif(not _has_tesseract(), reason="tesseract binary not installed")
def test_pdf_ocr_path_routes_image_only_page(aliases):
    """Render an image-only page and confirm we hit the OCR branch.

    Build a PDF whose page text is below the min_text_chars_per_page floor,
    so the extractor must fall back to rasterize + OCR.
    """
    import io
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    # Only a very short string — below the default 40-char floor.
    c.setFont("Helvetica", 48)
    c.drawString(72, 720, "OCR")
    c.showPage()
    c.save()

    cfg = PdfExtractionConfig(min_text_chars_per_page=100)
    result = extract_from_pdf(buf.getvalue(), aliases=aliases, cfg=cfg)
    assert result.source_type == SourceType.PDF_OCR
