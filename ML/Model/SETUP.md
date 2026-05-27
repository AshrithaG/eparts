# eParts ML — local setup

This page lists everything a developer needs after cloning the repo. The
ML pipeline lives entirely under `ML/Model/`; the rest of the
`eparts-main` repository (orchestrator, dashboard, pipeline) is owned by
other teams.

## 1. Python environment

Requires Python 3.10–3.13. On Windows the Microsoft Store stub `python.exe`
on PATH does not work — use the [Python launcher](https://docs.python.org/3/using/windows.html#python-launcher-for-windows)
(`py`) or activate the real interpreter explicitly.

```powershell
# From ML/Model/
py -m pip install -r requirements.txt
py -m pip install -r requirements-dev.txt   # ruff / black / mypy / reportlab
```

`requirements.txt` includes the heavy ML libs (`torch`, `sentence-transformers`,
`faiss-cpu`). The torch install is ~200 MB pip download / ~1 GB on disk.
For CPU-only Windows installs you can speed this up by pointing pip at the
PyTorch CPU index:

```powershell
py -m pip install --index-url https://download.pytorch.org/whl/cpu torch
py -m pip install sentence-transformers faiss-cpu
```

## 2. System dependencies

### Tesseract OCR (required for the PDF-OCR path)

Layer 1's PDF extractor falls back to OCR when a page has no embedded text
(spec §4.1). This requires the `tesseract` binary.

**Windows:**

```powershell
winget install --id UB-Mannheim.TesseractOCR --silent
```

The installer drops `tesseract.exe` at `C:\Program Files\Tesseract-OCR\`.
Our extractor probes that path automatically (see
[`src/layer1_extraction/pdf_input.py:locate_tesseract`](src/layer1_extraction/pdf_input.py))
so you do not need to edit PATH — but adding it is recommended:

```powershell
# Persistent for new shells
[Environment]::SetEnvironmentVariable(
    "PATH",
    [Environment]::GetEnvironmentVariable("PATH", "User") + ";C:\Program Files\Tesseract-OCR",
    "User"
)
```

**Linux/macOS:**

```bash
# Debian/Ubuntu
sudo apt-get install tesseract-ocr

# macOS
brew install tesseract
```

When tesseract is unavailable the OCR test (`tests/test_layer1_pdf.py`)
auto-skips and the PDF extractor raises `OcrUnavailableError` when a page
needs OCR. The text-extraction branch works without it.

## 3. Raw eParts data — out-of-band

The raw client CSVs (1.6 GB combined) are **not** in git. After cloning,
drop them into `ML/Model/the_standard_data/`:

| File | Size | Source |
|---|---|---|
| `1A_Product_Attribute_Pairs.csv` | 1.4 GB | eParts capstone shared drive |
| `1A_Product_Document_Links.csv` | ~70 MB | eParts capstone shared drive |
| `1B_Product_Master.csv` | ~100 MB | eParts capstone shared drive |
| `2A_Values_Per_Attribute.csv` | ~0.4 MB | eParts capstone shared drive |
| `2B_Apparent_Correction_Cases.csv` | (V1 unused — see spec §2.3) | optional |
| `Data Dictionary.pdf` | small | tracked in git |
| `readme.txt` | small | tracked in git |

Spec §2.2 conventions:
* `the_standard_data/` is **read-only**. Derived artifacts go to `data/` or
  `artifacts/`.
* Never `cat`/load `1A_Product_Attribute_Pairs.csv` fully into memory;
  always stream via `src.data.iter_attribute_pairs(chunksize=200_000)`.

## 4. Build M1 derived splits

```powershell
py scripts/m1_build_splits.py
```

Writes `data/splits/{train,val,test}.parquet` (stratified by ProductType,
seed=42, deterministic). These are `.gitignore`d — re-run after cloning.

## 5. Run the test suite

```powershell
py -m pytest
```

All tests should pass on a fresh setup. Expected output: `89 passed`
(includes the OCR test now that tesseract is installed).

## 6. M2 end-to-end smoke

```powershell
py scripts/m2_rule_engine_demo.py
```

Builds the rule engine from 1B + 2A and runs three synthetic CSV rows
plus one synthetic email through Layer 1 → Layer 2. Useful for confirming
the rule engine is wired up correctly on your machine.

## What does NOT get committed to git

See [.gitignore](.gitignore) for the authoritative list. Headline items:

* `the_standard_data/` raw CSVs (too large; distributed out-of-band).
* `data/splits/*.parquet` and other `data/<channel>/*` working files
  (reproducible from scripts).
* `artifacts/v1/run_*/` training outputs — FAISS index (~300 MB),
  centroids, σ tables, evaluation reports. Each training run produces a
  new immutable directory under `artifacts/v1/`; the most recent is
  aliased via `artifacts/v1/current/`.
* `reports/v1/<timestamp>/` evaluation outputs.
* Model framework caches (`~/.cache/huggingface/`, any in-tree `models--*/`).
* `*.pkl` (e.g. compiled Tier-1 regex caches).

If you need to share a specific run's artifacts with another team member,
upload it to the capstone shared drive — never force it into git.
