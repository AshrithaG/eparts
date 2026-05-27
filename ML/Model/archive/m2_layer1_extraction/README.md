# Archived — Layer 1 (Text Extraction & Normalization)

**Status:** Obsolete on the ML team's side as of 2026-05-13.
**Reason:** Layer 1 (information extraction) was reassigned to the
extraction sub-team, which will use mature LLM / NER models in place
of this deterministic implementation. The ML team's V1 scope is now
**Layer 2 (rule engine) + Layer 3 (semantic matcher) + Layer 4
(decision & feedback)** only.

## What's in here

```
src/
├── csv_input.py        deterministic CSV row → ExtractedInput
├── email_input.py      email parsing + signature/reply stripping
├── pdf_input.py        pdfplumber + tesseract OCR fallback
└── units.py            unit alias normalization (kΩ/V AC/°F/...)

tests/
├── test_layer1_csv.py
├── test_layer1_email.py
├── test_layer1_pdf.py
├── test_layer1_dispatch.py
└── test_units.py
```

All five test files were green at the time of archival (33 tests).

## Why we kept the code instead of deleting it

1. **Reference for the extraction team.** The deterministic logic here
   spells out the exact behaviors the spec §4.1 requires — unit
   normalization map, signature regex set, PDF-text-vs-OCR routing
   threshold (40 chars/page), etc. Useful as a check on whatever the
   mature-model pipeline produces.
2. **Insurance.** If the LLM/NER approach hits a quality or latency wall,
   we can restore this code as a fallback by moving the four files back
   under `src/layer1_extraction/` and re-adding the tests.
3. **Audit trail.** The capstone report needs evidence of work; this
   record keeps it visible without cluttering the active source tree.

## How to restore (if ever needed)

```powershell
# from ML/Model/
mkdir src/layer1_extraction
Move-Item archive/m2_layer1_extraction/src/* src/layer1_extraction/
Move-Item archive/m2_layer1_extraction/tests/* tests/
```

You will also need to re-add the package init file:

```python
# src/layer1_extraction/__init__.py
from .csv_input import CsvFieldMap, extract_from_csv_row
from .email_input import extract_from_email
from .pdf_input import OcrUnavailableError, PdfExtractionConfig, extract_from_pdf, locate_tesseract
from .units import ValueUnit, find_value_unit_pairs, normalize_unit
```

…and restore the `extract()` dispatch function from git history.

## Interface this code used to fulfil

The Layer 1 → Layer 2 boundary was the `ExtractedInput` dataclass in
[`src/contracts.py`](../../src/contracts.py). **That contract is now
the integration surface between the extraction team and the ML team.**
See [`eparts_doc/ExtractionHandoff_Spec.md`](../../eparts_doc/ExtractionHandoff_Spec.md)
for the formal spec.
