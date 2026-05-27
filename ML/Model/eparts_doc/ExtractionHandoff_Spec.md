# Extraction → Scoring Handoff Specification

| Field | Value |
|---|---|
| **Status** | Draft v0.2 — proposed contract between the **Extraction sub-team** and the **ML team** |
| **Last updated** | 2026-05-19 |
| **Owner** | ML team. Comments / change requests welcome before this becomes v1.0 |
| **Authoritative source for the data shape** | [`src/contracts.py`](../src/contracts.py) — `ExtractedInput` dataclass |

Changelog at §12.

---

## 1. Context

The eParts V1 pipeline runs in four layers (per
[V1 Engineering Spec](V1_Architecture_Design.md) §1.1):

```
Customer request → [L1 Extraction] → [L2 Rule Engine] → [L3 Semantic] → [L4 Decision]
                   ↑ your scope ↑    ↑─────────── ML team's scope ────────────────↑
```

This document defines the **boundary between Layer 1 and Layer 2** — the
exact data shape the extraction team must produce so the ML team's
downstream code can consume it without further adaptation. Architecture
overview lives in
[Architecture_Diagram.md](Architecture_Diagram.md).

---

## 2. The contract — what Layer 1 must emit

For every customer request, regardless of intake format, Layer 1 must
produce exactly **one** `ExtractedInput` Python dataclass instance.
The canonical definition is in
[`src/contracts.py`](../src/contracts.py); the table below is the
human-readable summary.

```python
@dataclass(frozen=True)
class ExtractedInput:
    source_type: SourceType                                # required
    text: str                                              # required
    structured_fields: Mapping[str, str] = {}              # optional but encouraged
    normalized_units: Mapping[str, tuple[str, str]] = {}   # optional
    source_ref: str | None = None                          # optional, for audit
```

### Field semantics

| Field | Required? | Type | Description |
|---|---|---|---|
| `source_type` | **Yes** | enum | The intake channel that produced this request — used downstream for metric stratification. One of: `csv`, `email`, `pdf_text`, `pdf_ocr`, `image` (see §3) |
| `text` | **Yes** | `str` | The **cleaned natural-language body**. This is what our Layer 3 sentence-transformer encoder consumes. **Do not pre-chunk, do not pad, do not tokenize** — see §6 |
| `structured_fields` | Optional | dict | Identified entities you want to share with Layer 2 (part numbers, manufacturer names, etc.). Use only the canonical keys in §4 |
| `normalized_units` | Optional | dict | Value + canonical-unit pairs you extracted from the text (e.g. `{"value_unit_0": ("24", "vac")}`). Powers Layer 2 Tier 3 — see §5 |
| `source_ref` | Optional | str | Opaque identifier (filename, message-id, ticket #) preserved on the result for audit logging. ML team does not interpret it |

---

## 3. Input channels

We anticipate **five** intake formats. Tag each `ExtractedInput` with the
appropriate `source_type`:

| Format | `source_type` | Notes |
|---|---|---|
| Customer order CSV | `csv` | Already structured. One row → one `ExtractedInput`. Map known columns into `structured_fields` |
| Customer email | `email` | Free-text body with signature blocks, reply chains, possibly HTML. Strip aggressively (§7) |
| Text-bearing PDF | `pdf_text` | Spec sheets / quote requests with embedded text. Extract via `pdfplumber` or similar |
| Scanned PDF (image-only) | `pdf_ocr` | Requires OCR. Tag as `pdf_ocr` so downstream calibration treats it as the noisier channel |
| Standalone image (JPG/PNG) | `image` | Spec-sheet photos, screenshots. Same OCR pipeline as `pdf_ocr` but tagged separately |

**Routing signal for PDFs:** the `ImageFile` column in
[`the_standard_data/1A_Product_Document_Links.csv`](../the_standard_data/)
tells you per product whether to route through text-bearing (`=0`) or
OCR (`=1`) at training time. For runtime inputs, you'll need your own
text-density heuristic (the ML team's archived prototype used "≥40 chars
of extractable text per page" as the threshold — see
[`archive/m2_layer1_extraction/src/pdf_input.py`](../archive/m2_layer1_extraction/src/pdf_input.py)
for reference).

---

## 4. Canonical `structured_fields` keys

The ML team consumes these keys when present. Use the names *exactly*
(`lower_snake_case`). Unknown keys are silently ignored — they do no
harm but produce no benefit.

| Key | Type | Description | Used by |
|---|---|---|---|
| `part_number` | string | Manufacturer / OEM part number. Anything matching 1B's `Product_Number` triggers our Tier-1 terminal short-circuit (confidence 1.0). | L2 Tier 1 |
| `manufacturer_name` | string | Manufacturer name as the customer wrote it. We run rapidfuzz `token_set_ratio ≥ 90` against 1B's 219 canonical names. Case-insensitive. | L2 Tier 2 |
| `sender` | string | Email sender address. **Audit-only — never treat as a manufacturer hint.** Preserve as-is for traceability. | (audit log) |

You may include additional entity types you've identified — we'll start
consuming new keys as needs grow. New keys should be proposed via PR
against this document.

---

## 5. `normalized_units` — required canonical forms

Use these exact strings as the unit half of each `(value, unit)` tuple.
Full alias table lives in
[`config/unit_aliases.yaml`](../config/unit_aliases.yaml) — that file is
the source of truth, this table is a snapshot for convenience.

| Canonical | Accepted customer-written variants |
|---|---|
| `kohm` | "kΩ", "kohm", "k ohm", "kilo-ohm", "kilo ohm" |
| `vac` | "VAC", "V AC", "volts AC", "volts alternating current" |
| `vdc` | "VDC", "V DC", "volts DC", "volts direct current" |
| `f` | "°F", "deg F", "degF", "Fahrenheit" |
| `c` | "°C", "deg C", "degC", "Celsius" |

If you extract a unit form not in the table, **leave the entry out of
`normalized_units`** — do not invent a canonical form. We will extend
the YAML when new units appear in real data; raising a "please add
`psi`" request is the right path.

**Value half:** plain string of the numeric token (`"24"`, `"-10"`, `"0.5"`).

**Key half:** any unique identifier per entry (`"value_unit_0"`,
`"value_unit_1"`, … by convention).

---

## 6. **What NOT to do (and why)**

Things teams sometimes propose that would actively hurt our pipeline:

### 6.1 Do NOT pre-chunk or pad `text` to fixed length

Our Layer 3 encoder (`BAAI/bge-small-en-v1.5`) is a **sentence
transformer**. It:

* Accepts variable-length input natively (up to 512 tokens)
* Produces one pooled 384-d embedding regardless of input length
* Is trained on natural-language sentences and paragraphs
* Will treat padding tokens / padding spaces as **content noise**, not
  as "no content"

Pre-chunking the text into fixed-length windows and padding short ones
with whitespace would *measurably degrade* our retrieval quality.
That pattern belongs to a different architecture family (older RNN /
CNN text classifiers); modern sentence encoders specifically eliminate
the need.

**Just hand us the cleaned natural-language body.** Layer 3 handles
length internally; if a description exceeds 512 tokens, the encoder
truncates (this is fine — product descriptions don't approach this
limit in practice).

### 6.2 Do NOT use GBDT models (CatBoost / LightGBM / XGBoost) for extraction

GBDTs are tabular structured-prediction models — they take numeric +
categorical feature columns as input and predict a label or
regression target. They **cannot extract text from images or parse
emails**. The right tool families for Layer 1 are:

| Tool family | What it does | Examples |
|---|---|---|
| **OCR engines** | pixels → text | Tesseract, PaddleOCR, EasyOCR, AWS Textract, Azure Form Recognizer, Google Document AI |
| **NER / token classifiers** | text → labeled entity spans | spaCy NER, HuggingFace token-classification models, GLiNER |
| **LLMs (zero-/few-shot)** | text → structured JSON | GPT-4o, Claude, Gemini, open-weight Qwen / Llama |
| **Layout-aware document models** | text + position → structured records | LayoutLM, Donut, Nougat, Marker |

GBDTs *could* be useful **after** extraction — for instance, classifying
the request type (quote / RMA / complaint) from extracted features —
but that's downstream, not part of the extraction step itself.

### 6.3 Do NOT pass us your model's internal confidences

Our Layer 4 fusion formula
(`conf_final = α · conf_rule + (1 − α) · conf_embed`) is **frozen**
per spec §6.1 and combines exactly two confidence signals.

If your team's NER / LLM produces useful confidence scores, save them
out-of-band (logs, metadata) so we can evaluate folding them in for
V2. Adding a third confidence dimension to V1's fusion math requires
a client design review.

### 6.4 Do NOT emit top-k alternates per slot

If your LLM produces top-3 candidates for a part number, **emit only
the top-1.** Layer 3 will surface alternates from semantic neighbors;
duplicating that work upstream creates ambiguity in Layer 2's
deterministic tiers.

---

## 7. **What we want CLEANED out of `text`**

These reduce downstream noise and improve semantic match quality:

* **Email signatures** — separator lines (`--`, `__`), name + title
  blocks, contact info, disclaimers, "Sent from my iPhone" sigs
* **Reply chains** — `> >` quoted prior emails, `On [date], [person]
  wrote:` markers, original-message blocks
* **HTML tags** if the email is multipart — render plain text only
* **Boilerplate** — "Please find attached…", "Hope this finds you
  well…", "Thanks in advance", legal footers
* **PDF page numbers, headers, footers, watermarks** — repeating
  text that doesn't reflect product content
* **OCR garbage characters** — sequences of disconnected
  punctuation/symbols, isolated single characters, clearly-failed
  recognition

---

## 8. **What we want KEPT** (do not strip these)

These often look like noise but carry signal:

* **Brand names, part numbers, model numbers** even if they look
  cryptic (e.g. "BA/3K-S#", "LM24-3-T") — these are exactly what
  Layer 2 Tier 1 matches against
* **Technical specifications** of any length — "24 VAC", "0–10 V",
  "10K ohm", "strap-on", "spring return"
* **Order quantities and units** — "qty 25", "2 each"
* **Customer-mentioned locations / facility names** — sometimes
  correlates with ProductType ("rooftop unit", "boiler room")
* **Compatibility / interoperability notes** — "for Belimo actuators",
  "replaces Honeywell L4006" — semantic gold

---

## 9. Implementation freedom

The following are your team's choice, **not contractual**:

* **Text extraction method** — LLM, NER model, regex heuristics, or
  any combination
* **OCR engine** — Tesseract is what our archived prototype used; you
  can pick any of the alternatives in §6.2
* **Email parser** — Python's `email`, `mailparser`, custom
* **PDF parser** — `pdfplumber`, `pymupdf`, `pdfminer.six`, `Marker`,
  etc.
* **Whether to populate `structured_fields`** — optional but valuable
* **Whether to populate `normalized_units`** — optional; if you don't,
  our archived `units.py` could be restored to do free-text unit
  scanning on our side. Cleanest is for you to populate it

You can swap any of these later without affecting our pipeline, as
long as the `ExtractedInput` output remains valid.

---

## 10. Worked example — what each channel looks like

### CSV
**Input row:**
```csv
Part_Number,Manufacturer,Short_Description,Full_Description
T-6000,Johnson Controls,Temperature sensor 24 VAC strap-on,Thermistor probe for HVAC pipe mounting.
```
**Expected `ExtractedInput`:**
```python
ExtractedInput(
    source_type=SourceType.CSV,
    text="Temperature sensor 24 VAC strap-on. Thermistor probe for HVAC pipe mounting.",
    structured_fields={
        "part_number": "T-6000",
        "manufacturer_name": "Johnson Controls",
    },
    normalized_units={"value_unit_0": ("24", "vac")},
    source_ref="orders_2026Q1.csv:1",
)
```

### Email
**Input (raw):**
```
From: buyer@customer.test
Subject: Quote: Johnson Controls T-6000 ASAP

Need pricing on the Johnson Controls T-6000 thermistor.
Wiring is 24 VAC.

--
Jane Buyer, ACME Corp
555-1234
```
**Expected `ExtractedInput`:**
```python
ExtractedInput(
    source_type=SourceType.EMAIL,
    text="Quote: Johnson Controls T-6000 ASAP\nNeed pricing on the Johnson Controls T-6000 thermistor. Wiring is 24 VAC.",
    structured_fields={
        "manufacturer_name": "Johnson Controls",
        "part_number": "T-6000",
        "sender": "buyer@customer.test",
    },
    normalized_units={"value_unit_0": ("24", "vac")},
    source_ref="msg:abc-123",
)
```
Note: name, phone, and signature delimiter all removed from `text`. `sender` preserved in `structured_fields` for audit.

### PDF / Image
**Input:** scanned spec sheet image.
**Expected `ExtractedInput`:**
```python
ExtractedInput(
    source_type=SourceType.PDF_OCR,     # or IMAGE for standalone images
    text="MODEL XYZ-2200. INPUT: 24 VAC. OUTPUT: 0-10 VDC. MOUNTING: STRAP-ON.",
    structured_fields={"part_number": "XYZ-2200"},
    normalized_units={
        "value_unit_0": ("24", "vac"),
        "value_unit_1": ("0", "vdc"),
        "value_unit_2": ("10", "vdc"),
    },
    source_ref="spec-sheets/xyz-2200.pdf",
)
```

---

## 11. Operational details

### 11.1 PII / data sensitivity

Out of V1 contract scope — discuss separately if eParts has GDPR /
CCPA-style requirements. The fields we use downstream
(`text`, `source_type`, `structured_fields`, `normalized_units`) are
not inherently personal data unless your team chooses to include
identifiers. The `sender` field is the obvious exception; redact or
hash before storage if compliance requires it.

### 11.2 Multi-language inputs

V1 assumes English. The BGE encoder is English-only. If you encounter
non-English requests, flag them via `structured_fields["language"]`
(non-canonical key — we will agree on handling separately) and
include the original-language text. We will likely route these to
human review for V1.

### 11.3 Integration test fixtures

After your pipeline is live we want **≥4 representative payloads** —
one per channel (csv, email, pdf_text, pdf_ocr or image) — committed
to `tests/fixtures/extraction/`. These become a shared regression
suite for both teams.

### 11.4 Latency budget

Our downstream budget is **p95 ≤ 200 ms end-to-end** per spec §1.2.
Your pipeline plus ours must fit eParts's overall response-time SLA.
LLM-based extraction can be slow (multi-second) — design for batching
or async if you go that route.

### 11.5 Failure modes

If your extraction fails partway:
* Empty `text` is allowed — our pipeline will emit zero hits and
  route to `flag_unclear`. Better than fabricating content
* Missing `source_type` or `text` field → reject the request
  upstream; do not pass through to Layer 2

---

## 12. Open questions for the extraction team

1. Which OCR / NER / LLM stack are you planning to use? Not a
   constraint — helps us anticipate failure modes and latency
2. Do you need access to `1B_Product_Master.csv` to validate
   extracted part numbers / manufacturer names against the catalog
   before emission? We can grant that explicitly
3. Multi-page PDFs and emails with attachments — your team's plan?
4. Languages other than English — your team's plan?
5. What end-to-end latency are you targeting per request?
6. Do you want us to upstream a Python type stub / pydantic model so
   you can validate `ExtractedInput` shape on your side? We can ship
   one in 30 minutes

---

## 13. Change log

| Date | Version | Author | Change |
|---|---|---|---|
| 2026-05-13 | 0.1 | ML team | Initial draft. `ExtractedInput` contract, canonical keys, unit forms, error handling, channel notes |
| 2026-05-19 | 0.2 | ML team | Added `image` channel (§3). Added §6 "What NOT to do" with explicit guidance against fixed-length chunking, GBDTs for extraction, model internal confidences, and top-k alternates. Added §7 "what to clean" and §8 "what to keep" lists. Added §10 worked examples per channel. Added §11.4 latency budget. Reorganized open questions in §12 |
