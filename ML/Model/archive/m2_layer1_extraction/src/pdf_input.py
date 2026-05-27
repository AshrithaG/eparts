"""PDF spec-sheet extraction for Layer 1.

Implements V1_Engineering_Spec §4.1 "Extract text from PDFs via pdfplumber.
Route scanned pages through pytesseract OCR fallback."

Routing logic:
    1. Open the PDF with ``pdfplumber`` and extract per-page text.
    2. If the *aggregate* text length per page is below
       :attr:`PdfExtractionConfig.min_text_chars_per_page`, treat the page
       as image-only and OCR it through :mod:`pytesseract`.
    3. The result's :attr:`ExtractedInput.source_type` is
       :attr:`SourceType.PDF_OCR` iff *any* page hit the OCR branch — this
       lets downstream calibration stratify metrics per channel (spec §5.3).

The OCR branch requires the ``tesseract`` system binary. When it is not
available we raise :class:`OcrUnavailableError`; callers can opt to mark
the input ``PDF_TEXT`` with whatever sparse text was recovered.
"""

from __future__ import annotations

import io
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from ..config import UnitAliasMap
from ..contracts import ExtractedInput, SourceType
from .units import find_value_unit_pairs


class OcrUnavailableError(RuntimeError):
    """Raised when the OCR fallback is needed but the tesseract binary is missing."""


# Default install locations to probe when ``tesseract`` is not on PATH.
# This keeps the OCR path working on Windows machines using the standard
# UB-Mannheim installer without forcing every developer to edit PATH.
_TESSERACT_FALLBACK_PATHS: tuple[Path, ...] = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe",
)


def locate_tesseract() -> Path | None:
    """Return the resolved tesseract binary path, probing PATH then fallbacks.

    Side effect: when a fallback path is found, ``pytesseract.pytesseract
    .tesseract_cmd`` is set so subsequent OCR calls go straight to it.
    """
    on_path = shutil.which("tesseract")
    if on_path:
        return Path(on_path)
    for candidate in _TESSERACT_FALLBACK_PATHS:
        if candidate.is_file():
            try:
                import pytesseract
                pytesseract.pytesseract.tesseract_cmd = str(candidate)
            except ImportError:                              # pragma: no cover
                pass
            return candidate
    return None


@dataclass(frozen=True, slots=True)
class PdfExtractionConfig:
    """Tunable thresholds for the PDF extraction path."""

    min_text_chars_per_page: int = 40
    ocr_language: str = "eng"
    ocr_dpi: int = 200


def _open_pdf(payload: bytes | str | IO[bytes]) -> "tuple[object, bool]":
    """Open ``payload`` with pdfplumber regardless of whether it's bytes / path / file-like.

    Returns ``(opened_pdf, must_close)``.
    """
    import pdfplumber

    if isinstance(payload, (bytes, bytearray)):
        return pdfplumber.open(io.BytesIO(payload)), True
    if isinstance(payload, str):
        return pdfplumber.open(payload), True
    # Assume file-like
    return pdfplumber.open(payload), True


def _ocr_page(page: object, cfg: PdfExtractionConfig) -> str:
    try:
        import pytesseract
    except ImportError as exc:                                # pragma: no cover
        raise OcrUnavailableError("pytesseract is not installed") from exc

    # Resolve the binary location once per call — cheap and survives any
    # pytesseract state reset between tests.
    if locate_tesseract() is None:
        raise OcrUnavailableError(
            "tesseract binary not found on PATH or in standard install locations; "
            "install Tesseract OCR or set pytesseract.pytesseract.tesseract_cmd"
        )

    try:
        image = page.to_image(resolution=cfg.ocr_dpi).original  # type: ignore[attr-defined]
    except Exception as exc:                                    # pragma: no cover
        raise OcrUnavailableError(f"failed to rasterize PDF page: {exc}") from exc

    try:
        return pytesseract.image_to_string(image, lang=cfg.ocr_language)
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrUnavailableError(
            "tesseract binary not found on PATH; install Tesseract OCR or "
            "set pytesseract.pytesseract.tesseract_cmd"
        ) from exc


def extract_from_pdf(
    payload: bytes | str | IO[bytes],
    aliases: UnitAliasMap,
    cfg: PdfExtractionConfig | None = None,
    source_ref: str | None = None,
    allow_ocr: bool = True,
) -> ExtractedInput:
    """Extract text from a PDF, with OCR fallback per page.

    Args:
        payload: Raw bytes, filesystem path, or file-like object.
        aliases: Configured unit-alias map.
        cfg: Override the default extraction thresholds.
        source_ref: Opaque identifier preserved on the result.
        allow_ocr: If ``False``, never call tesseract — return whatever text
            pdfplumber could find even if pages are mostly empty. Useful in
            CI when the OCR binary is unavailable.

    Raises:
        OcrUnavailableError: If a page needs OCR, ``allow_ocr=True``, and
            tesseract is not callable.
    """
    cfg = cfg or PdfExtractionConfig()
    pdf, must_close = _open_pdf(payload)
    try:
        pages_text: list[str] = []
        any_ocr_used = False
        for page in pdf.pages:                                # type: ignore[attr-defined]
            text = page.extract_text() or ""
            text = text.strip()
            needs_ocr = len(text) < cfg.min_text_chars_per_page
            if needs_ocr and allow_ocr:
                ocr_text = _ocr_page(page, cfg).strip()
                if ocr_text:
                    text = ocr_text
                    any_ocr_used = True
            pages_text.append(text)
    finally:
        if must_close:
            pdf.close()                                       # type: ignore[attr-defined]

    full_text = "\n".join(p for p in pages_text if p)
    source_type = SourceType.PDF_OCR if any_ocr_used else SourceType.PDF_TEXT

    normalized_units: dict[str, tuple[str, str]] = {}
    for i, pair in enumerate(find_value_unit_pairs(full_text, aliases)):
        normalized_units[f"value_unit_{i}"] = (pair.value, pair.unit)

    return ExtractedInput(
        source_type=source_type,
        text=full_text,
        structured_fields={},
        normalized_units=normalized_units,
        source_ref=source_ref,
    )
