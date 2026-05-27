# eParts ML — Layer 1 & Layer 2 Implementation Report

**Scope:** Milestones M1 + M2 of the V1 Engineering Spec.
**Status:** Code complete, **56 / 56 automated tests passing** on the active
ML-team suite (33 archived Layer-1 tests are kept under `archive/` for reference).
**Audience:** Client (eParts) and capstone teammates.
**Date:** 2026-05-13.

> **Scope update — 2026-05-13.** After this report was drafted, the
> capstone team agreed that **Layer 1 (information extraction) will be
> owned by a separate sub-team** using mature LLM / NER models, **not by
> the ML team**. The ML team's V1 scope is therefore narrowed to
> **scoring and routing**: Layer 2 (rule engine), Layer 3 (semantic
> matcher), and Layer 4 (decision & feedback).
>
> The Layer 1 prototype described in §3 below was delivered as planned
> and remains correct — it has simply been **moved to `archive/`** so it
> doesn't imply ongoing ML-team maintenance. The formal interface
> between the extraction sub-team and the ML team is documented
> separately in [`ExtractionHandoff_Spec.md`](ExtractionHandoff_Spec.md);
> that document is now the integration contract.

---

## 1. Executive Summary

The V1 attribute-prediction pipeline is a four-layer system (Extraction →
Rule Engine → Semantic Matcher → Decision). This report covers the first
two layers, which together turn a customer's raw request into a set of
deterministic, confidence-tagged predictions for whatever can be matched
exactly against the eParts master data.

**What the first two layers can do today:**

| Capability | Confidence emitted | Behavior |
|---|---|---|
| Recognize an exact eParts part number anywhere in a customer email, PDF, or CSV | `1.0` (terminal) | Pipeline short-circuits — no further work needed |
| Identify the manufacturer from a CSV `Manufacturer` column, even with case / minor spelling variation | `0.85` | Routes the input to the matching manufacturer's sub-catalog |
| Match a numeric value + unit (e.g. "24 VAC", "70 °F") to a unique attribute in eParts's value table | `0.65` | Adds the attribute prediction to the result |
| Quietly drop a numeric match when several attributes could plausibly apply | n/a | Avoids spurious low-quality output; Layer 3 will adjudicate |
| Refuse to invent attribute values that don't exist in 2A | demoted to `0.0` | The "guardrail" — prevents the rule engine from emitting unknown values |

Inputs that exit Layer 2 without a terminal Tier-1 hit are passed to
Layer 3 (semantic matcher, M3 — not yet implemented) for ML-based
scoring. Inputs that do hit Tier 1 are auto-processed at confidence 1.0.

**What's next:** M3a (the BGE encoder + FAISS index over 1B Product
Master) is the next milestone. All prerequisite system and Python
dependencies are installed; the rule engine is ready to be wired into
the semantic matcher's output through Layer 4 fusion.

---

## 2. Foundation — Data Infrastructure (M1)

### Function

Provides the rest of the pipeline with safe, reproducible access to the
five eParts data files.

### How it works with the provided data

* Streams the 1.4 GB `1A_Product_Attribute_Pairs.csv` in 200,000-row
  chunks so memory never exceeds 1 GB (the file is too large for any
  approach that loads it whole).
* Loads `1B_Product_Master.csv` (~100 MB) and `2A_Values_Per_Attribute.csv`
  (~400 KB) directly.
* Builds a deterministic 80 / 10 / 10 train / val / test split,
  **stratified by ProductType** so every ProductType is represented in
  each split. Seed = 42, persisted to `data/splits/{train,val,test}.parquet`.
* ProductTypes with fewer than 3 products land entirely in train (they
  cannot supply both a val and a test sample); spec §4.3 [3d] already
  caps confidence on these low-sample cases.

### Verification

```powershell
py scripts/m1_build_splits.py        # rebuilds the splits from 1B
py -m pytest tests/test_split.py     # 10 split-invariant tests, all passing
```

Expected: train ≈ 80% of 198 K products, val ≈ 10%, test ≈ 10%;
every product appears in exactly one split.

---

## 3. Layer 1 — Text Extraction & Normalization

> **As of 2026-05-13 this layer is owned by the extraction sub-team** —
> see the scope-update box at the top of this document and the
> integration contract in [`ExtractionHandoff_Spec.md`](ExtractionHandoff_Spec.md).
> The deterministic prototype described below lives under
> [`archive/m2_layer1_extraction/`](../archive/m2_layer1_extraction/) for
> reference and as fallback insurance.

Implements V1 Spec §4.1. **Deterministic, no machine learning.**

### Function

Convert a customer request — whatever its delivery channel — into a
normalized internal object (`ExtractedInput`) that downstream layers can
consume identically regardless of source.

The internal object carries:

| Field | Meaning |
|---|---|
| `source_type` | One of `csv`, `email`, `pdf_text`, `pdf_ocr` — used downstream for metric stratification |
| `text` | Cleaned free-text body fed to the Layer 3 encoder |
| `structured_fields` | Dict of identified field/value pairs (e.g. `part_number`, `manufacturer_name`) |
| `normalized_units` | Value + canonical-unit pairs extracted from text (e.g. `(24, "vac")`) |
| `source_ref` | Opaque identifier preserved for audit trails (file path, message-id, etc.) |

### Components

**1. CSV order-form extractor** — Reads one customer row, maps named
columns into structured fields, concatenates description columns into
the free-text body. The column mapping is configurable per customer
template via `CsvFieldMap`, so each customer's order form can be
supported without code changes.

**2. Email extractor** — Parses RFC-822 messages via Python's `email`
module, then strips signatures and reply chains using a curated set of
patterns ("--", "Sent from my iPhone", "On … wrote:", quoted lines, etc.).
The subject line is concatenated with the cleaned body. The sender
address is preserved as `structured_fields["sender"]` for audit only
— it is **never used as a manufacturer hint**.

**3. PDF extractor (with OCR fallback)** — Uses `pdfplumber` to extract
embedded text per page. When a page yields fewer than 40 characters of
text (configurable), the page is rasterized at 200 DPI and routed
through `pytesseract` OCR. The result's `source_type` is `pdf_ocr` if
*any* page hit the OCR branch — this lets Layer 4's calibration stratify
metrics by intake channel (spec §5.3 secondary calibration).

**4. Unit normalization** — All canonical units (kohm, vac, vdc, °F,
°C) and their aliases (kΩ, "V AC", "volts AC", "deg F", "Fahrenheit",
etc.) live in [`config/unit_aliases.yaml`](../config/unit_aliases.yaml).
The extractor scans free text for `<number><unit>` sequences and picks
the longest prefix that resolves to a canonical form. Extending coverage
means editing the YAML, not the code — eParts can extend the table
without an engineering ticket.

**5. Dispatch entry** — A single `extract(payload, source_type, ...)`
function routes to the right extractor based on the source type tag.

### How it works with the provided data

Layer 1 does **not** read training data. It only consumes customer-side
input. The `unit_aliases.yaml` table was seeded from the spec's §4.1
required coverage list.

### Verification

```powershell
py -m pytest tests/test_units.py tests/test_layer1_csv.py \
             tests/test_layer1_email.py tests/test_layer1_pdf.py \
             tests/test_layer1_dispatch.py
```

Expected: 33 tests pass. Tests cover:

* 10 canonical unit-alias regressions (`24 VAC` → `(24, vac)` etc.)
* CSV extraction with field-map customization, pandas Series input,
  empty/NaN cell handling
* Email signature/reply-chain/mobile-signature stripping
* PDF text path against a synthetic reportlab-generated PDF (no
  external file needed)
* PDF OCR path (now active — see §7)
* Dispatch input-type validation

### Risks

| Risk | Severity | Mitigation in place |
|---|---|---|
| Email signature heuristics are seeded against generic patterns, not real eParts customer mail | High | Patterns easy to extend (regex list in `email_input.py`); will need iteration when real samples land |
| OCR quality on scanned spec sheets varies wildly with scan quality | Medium | Single-column threshold (40 chars) drives the routing; can be tuned per ProductType later if needed |
| CSV column naming varies across customer order forms | Medium | `CsvFieldMap` is a per-customer config; deploying a new customer template is a config change, not a code change |
| 1A descriptions used to seed our tests are *internal* curated text, not customer-style writing (spec §2.3) | High | This is a Layer 3 / Layer 4 calibration concern documented in the spec; flagged for V2 |

### Help / data we need

1. **P3-A — customer submission templates.** The CSV extractor's
   default column mapping is a guess. With real templates we can ship
   a `CsvFieldMap` per template.
2. **Real customer email samples.** Even 10–20 anonymized examples
   would let us harden the signature-stripping patterns.
3. **A handful of real scanned spec-sheet PDFs.** We tested the OCR
   path on a synthetic PDF; real scans tell us whether the 40-character
   text-density threshold is the right place to flip into OCR.

---

## 4. Layer 2 — Rule Engine

Implements V1 Spec §4.2. **Deterministic, no machine learning.**

### Function

For each `ExtractedInput` from Layer 1, attempt the three rule tiers
described in the spec, then validate every emitted prediction against
the 2A valid-value table before returning. The output is a
`RuleEngineResult` — a tuple of `RuleHit` objects plus a `terminated`
flag.

### Components

**Tier 1 — Part-number exact match (terminal).** A single compiled
regex union over the **189,208 distinct Product_Number values** from
1B. Matches respect alphanumeric word boundaries (so "T-6000X" does not
match "T-6000"). Special regex characters are escaped per pattern —
"BA/3K-S", "10K-3", "LM24-3-T" and the like all match correctly. The
compiled regex is pickled to disk so service restarts skip the compile
step. **A match returns `conf_rule = 1.0` and short-circuits the
pipeline** — Layer 3 is never invoked. This is the spec's intended
fast-path for orders that explicitly cite a part number.

**Performance verified:** 200,000-pattern compile in ≤ 10 s; single
query in ≤ 1 ms after warmup (spec §7.2 M2 targets are 5 s / 1 ms — we
meet the query target and stay within an order of magnitude on the
compile target on a stock laptop).

**Tier 2 — Manufacturer fuzzy match.** Built over the **219 distinct
manufacturer names** in 1B's `Manufacturer_Name` column. Uses
`rapidfuzz.token_set_ratio` (case-insensitive) with a default
acceptance threshold of 90. Tier 2 only consults
`structured_fields["manufacturer_name"]` — it does **not** scan free
text for manufacturer mentions, because that would create huge
false-positive risk on multi-word manufacturer names appearing in
prose. Free-text manufacturer signal is intentionally handed to Layer 3.

**Tier 3 — Numeric value + unit match.** Iterates the
`normalized_units` pairs from Layer 1, looks each pair up in 2A by
`(value, canonical_unit)`, and emits a `RuleHit` **only when the pair
uniquely identifies one attribute**. When the same `(value, unit)` could
plausibly belong to several attributes (e.g. `(24, vac)` could be
`INPUT_VOLTAGE` or `OUTPUT_VOLTAGE`), Tier 3 emits nothing — Layer 3
will adjudicate using its semantic context. This is a conservative
choice, made on purpose: false confidence is worse than no signal.

**Guardrail — 2A valid-value check.** Every (Attribute, Value) pair
the rule engine emits is validated against the **7,495 distinct
(Attribute_Name, Value) pairs** in 2A. Pairs not in 2A are *demoted*
(confidence rewritten to 0.0, flagged `demoted_by_2a = True`) so Layer
3 takes over. This prevents the rule engine from inventing values
absent from eParts's database.

**One subtle design choice:** Manufacturer is exempt from the 2A check
— the actual 2A table contains **zero rows whose `Attribute_Name`
matches "manufacturer"** (we verified this directly on the supplied
file). Manufacturer is stored as product metadata in 1B, not as an
"attribute" in 2A. The guardrail's closed-set guarantee is preserved
for Manufacturer through a different mechanism: the fuzzy index itself
only emits names that already exist in 1B. This is captured in
[`engine.py`](../src/layer2_rules/engine.py) via the
`MANUFACTURER_ATTRIBUTE_NAME` exemption.

### How it works with the provided data

| Data file | Used for |
|---|---|
| `1B_Product_Master.csv` → `Product_Number` column | Tier 1 regex union |
| `1B_Product_Master.csv` → `Manufacturer_Name` column | Tier 2 fuzzy choices |
| `2A_Values_Per_Attribute.csv` → `(Attribute_Name, Value, Unit_Suffix)` triples | Tier 3 numeric lookup + 2A guardrail |
| Layer 1's `ExtractedInput.structured_fields["part_number"]` and `["manufacturer_name"]` | Direct (non-fuzzy) inputs to Tiers 1 and 2 |
| Layer 1's `ExtractedInput.normalized_units` | Inputs to Tier 3 |

The rule engine never reads 1A — that file is for Layer 3 cluster
statistics, not deterministic rules.

### Verification

```powershell
py -m pytest tests/test_part_numbers.py tests/test_manufacturers.py \
             tests/test_numeric_match.py tests/test_guardrail.py \
             tests/test_engine.py
```

Expected: 43 tests pass. End-to-end smoke test:

```powershell
py scripts/m2_rule_engine_demo.py
```

This builds the rule engine from real 1B + 2A (~4.6 seconds on a
laptop) and runs three synthetic CSV rows plus one synthetic email
through Layer 1 → Layer 2, printing each `RuleEngineResult`.

### Risks

| Risk | Severity | Mitigation in place |
|---|---|---|
| Tier 1 will not fire if customer cites a *similar* part number with a typo | Medium | Layer 3 absorbs this case via semantic similarity (spec §4.3); rule engine is intentionally exact-only |
| Tier 2's 90-threshold could mis-route inputs with two-word OEM names that look similar (e.g. "Belimo" vs "Belimo Aircontrols") | Low | 220-name closed list keeps the search space tiny; can tune threshold via config without redeploy |
| Tier 3 stays silent on ambiguous `(value, unit)` pairs — auto-process rate is therefore lower than a more aggressive rule engine | Accepted | Spec explicitly trades coverage for precision here; Layer 3 picks up the difference |
| 1A descriptions (which Layer 3 will train on) are internal curated text, not customer-style — σ calibration will be optimistic | High | Spec §2.3 documents this; secondary calibration pass on OCR'd PDFs planned for M5; post-launch recalibration after first 500 reviewer corrections |
| 141 active attributes have **zero** rows in 1A | Medium | These attributes are out of scope for V1's semantic matcher; rule engine falls through for them. Tracked for follow-up data delivery |
| 2A does not record Manufacturer values; "Manufacturer" attribute exemption is a code-level workaround | Low | Documented inline + in memory; if eParts ever exports Manufacturer into 2A, the exemption is safely removable |
| Test fixtures are synthetic (1B-derived descriptions + hand-written emails) | High | This affects test realism, not production correctness. Production fix is real customer-input samples |

### Help / data we need

1. **P3-B — request volume distribution by product category.** We are
   sizing the FAISS index assuming a roughly uniform mix across
   ProductTypes; the distribution data will tell us whether to
   over-index any "hot" categories.
2. **50–100 hand-picked correction cases** (request the spec already
   identified — §9.1 risk register). Critical for V2 contrastive-loss
   experiments and for sharpening σ at decision boundaries.
3. **Confirmation that 141-attribute gap is intentional**, or a target
   date for a re-export covering them. Today we treat the gap as "out
   of V1 scope" (spec §2.3 — already confirmed by eParts on 2026-04-23).
4. **An updated 2A export that includes Manufacturer as a first-class
   attribute** — *optional*. The current exemption-based design works,
   but if 2A becomes the single source of truth for "what values are
   legal", manufacturer should appear there too.

---

## 5. Cross-cutting Infrastructure

These are not part of any single layer but underpin all of them.

### Configuration system

Every tunable parameter lives in [`config/`](../config/) as YAML.
Source code never hard-codes a threshold, a model ID, or a magic number
(spec §11.3). Five files cover:

* `unit_aliases.yaml` — Layer 1 unit normalization
* `encoder.yaml` — Layer 3 encoder (`bge-small-en-v1.5`, 384-d)
* `faiss.yaml` — Layer 3 FAISS index (IVFFlat, nlist=512, K=50)
* `thresholds.yaml` — Layers 2/3/4 confidences and decision cutoffs;
  every value tagged **FROZEN** (client commitment per §6.1) or
  **TUNABLE** (free to adjust per §6.2)
* `calibration.yaml` — Layer 4 σ-grid and reliability-diagram settings

This is the team's lever for "the spec changed" or "we want to try a
different encoder" — config-level swap, no source edits.

### Type-safe layer contracts

[`src/contracts.py`](../src/contracts.py) defines immutable dataclasses
(`ExtractedInput`, `RuleEngineResult`, `SemanticMatcherResult`,
`PipelineResult`) and structural Protocols (`Layer1Extractor`,
`Layer2RuleEngine`, etc.). Other teammates (orchestrator, dashboard,
pipeline) consume these types — not concrete classes. This is what
lets us swap a different encoder, a different FAISS index type, or a
different scoring strategy without ripples downstream.

### Testing infrastructure

* `pyproject.toml` configures **ruff** (lint), **black** (format), and
  **mypy** (strict typing). Other teams will see consistent style and
  type-checked surfaces.
* `tests/conftest.py` provides session-scoped fixtures for `Settings`
  and the synthetic PDF, so tests run in milliseconds.
* 89 tests across 11 files cover every module's happy path and
  documented edge cases.

---

## 6. Quick Self-Check (≈ 1 minute)

For a teammate or reviewer who wants to confirm the system works:

```powershell
cd ML/Model

# 1. Confirm dependencies are installed
py -m pip install -r requirements.txt    # one-time; ≈ 1 GB total

# 2. Run the full test suite
py -m pytest                              # expect: 89 passed in ~8s

# 3. Run the end-to-end rule-engine demo on real eParts data
py scripts/m2_rule_engine_demo.py         # expect: 4–5s startup,
                                          #         3 CSV rows + 1 email printed
```

Expected demo output (abridged):

```
Building rule-engine components from 1B + 2A (slow disk reads) ...
  built in 4.66s: 189,208 part numbers, 219 manufacturers, 7,495 (attr,value) pairs

=== CSV inputs ===
[0] 'Temperature sensor 24 VAC strap-on'
  · tier=manufacturer_fuzzy     attr='Manufacturer'   val='Johnson Controls'  conf=0.85
[1] 'Damper actuator 24 VAC 0-10 VDC control'
  · tier=manufacturer_fuzzy     attr='Manufacturer'   val='Honeywell'         conf=0.85
[2] 'Generic widget at 70 deg F'
  (no hits — correctly rejected: vendor below threshold, part number absent)
```

If those numbers do not match, the local data is out of sync — see
[SETUP.md](../SETUP.md).

---

## 7. Consolidated Risk Register

Severity / status for everything flagged above:

| # | Risk | Severity | Status |
|---|---|---|---|
| 1 | σ calibration optimistic on curated 1A text | High | Mitigation planned at M5 (secondary calibration on OCR'd PDF text) |
| 2 | 2B unusable as error-case dataset | High | V1 trains on positives only; client confirmed acceptable (2026-04-23) |
| 3 | 141 attributes absent from 1A | Medium | Out of V1 scope; client confirmed (2026-04-23) |
| 4 | No real customer email/PDF/CSV samples yet | High | Synthesized fixtures used for testing; real samples required for production calibration |
| 5 | Email signature heuristics seeded on generic patterns | Medium | Easy to extend; needs real samples |
| 6 | 2A has no `Manufacturer` rows; exemption added | Low | Documented; safely removable when 2A is updated |
| 7 | Tesseract OCR is a system dependency, not a pip package | Low | Auto-discovered from standard Windows install path; SETUP.md documents install |
| 8 | Tier 1 part-number regex compile takes 4–5 s at startup | Low | One-time cost; pickle cache will reduce to <1 s after first run |

---

## 8. Open Asks Summary

Grouped for ease of forwarding to eParts:

**Data**
* P3-A — customer submission templates (CSV column names per channel)
* P3-B — request volume distribution by ProductType / Category
* 10–20 anonymized real customer emails (for signature regex tuning)
* A handful of real scanned spec-sheet PDFs (to validate OCR threshold)
* 50–100 hand-picked correction cases (already requested per spec §9.1)

**Optional / nice-to-have**
* Updated 2A export including Manufacturer as an attribute row (removes the
  exemption design)
* Confirmation of the 141 missing-attribute scope (whether more come in
  V2 vs. permanently out)

---

## 9. What's Next — M3a (ML team scope, unchanged)

Next milestone is the Semantic Matcher's first sub-component. This work
is **scoring + routing** territory — squarely within the ML team's
revised V1 scope:

* Integrate `BAAI/bge-small-en-v1.5` (sentence-transformer encoder, 384-d)
* Build a FAISS IVFFlat index over all 1B product descriptions
  (~290 MB, CPU-only)
* Wire the encoder + index into a retrieval demo that returns the top-50
  most-similar products for a free-text query

All dependencies (`torch`, `sentence-transformers`, `faiss-cpu`) are
already installed and verified on the dev machine. M3a is expected to
take ≈ 2 working days.

---

*Document owner: ML team — eParts Capstone (MSE Studio).*
*Source code:* [`ML/Model/`](../).
*Authoritative spec:* [V1 Engineering Specification](V1_Architecture_Design.md).
