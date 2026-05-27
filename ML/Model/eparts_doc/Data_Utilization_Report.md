# eParts Data Utilization Report

**Audience:** eParts stakeholders + capstone teammates.
**Date:** 2026-05-13.
**Scope:** How the ML team uses the eParts-provided data at each
milestone — current state (M1 + M2) and planned state (M3+).

This document is the *operational* companion to
[`Data_Delivery_Assessment.md`](Data_Delivery_Assessment.md): that one
audits what we received; this one shows what we do with it.

---

## 1. Total data volume (what eParts provided)

| File | Rows | Approx. size | Status in V1 |
|---|---:|---:|---|
| `1A_Product_Attribute_Pairs.csv` | 1,938,427 | 1.4 GB | **Core training data** for Layer 3 |
| `1A_Product_Document_Links.csv` | 516,006 | ~70 MB | Secondary calibration (M5) |
| `1B_Product_Master.csv` | 198,148 | ~100 MB | Catalog reference + retrieval index |
| `2A_Values_Per_Attribute.csv` | 9,919 | ~400 KB | Valid-value set + Usage_Count prior |
| `2B_Apparent_Correction_Cases.csv` | 746,846 | ~80 MB | **Not used in V1** (see §5.2) |
| **Total** | **~3.4 M rows** | **~1.6 GB** | |

Schema details: see [`the_standard_data/Data Dictionary.pdf`](../the_standard_data/Data%20Dictionary.pdf).
Database snapshot (from the Data Dictionary): 198,465 active products,
77 categories, 755 product types, 487 attributes, 553 manufacturers,
4,080,763 attribute-value records, average 13.1 attributes per product.

---

## 2. What we have already used (M1 + M2 — completed)

At this stage of the project we have **touched ~208K rows (~6% of the
total volume)** — primarily the catalog reference data, not the
attribute-value training data. Layer-3 training (M3+) is where the
heavy 1A consumption begins.

### 2.1 File-by-file usage

| File | Used? | What we read | Where (layer / milestone) |
|---|---|---|---|
| `1B_Product_Master.csv` | **Yes — fully** | `Product_ID`, `Product_Number`, `Manufacturer_Name`, `ProductType_ID`, `Category_ID`, descriptions | M1 splits, Layer 2 Tier 1 & Tier 2 |
| `2A_Values_Per_Attribute.csv` | **Yes — fully** | `Attribute_Name`, `Value`, `Unit_Suffix` | Layer 2 Tier 3 + guardrail |
| `1A_Product_Attribute_Pairs.csv` | **Sampled / streamed** | `Product_ID` only (for split verification) | M1 chunked streaming |
| `1A_Product_Document_Links.csv` | Not yet | — | Reserved for M5 secondary calibration |
| `2B_Apparent_Correction_Cases.csv` | Not used in V1 | — | Confirmed out-of-scope (see §5.2) |

### 2.2 Concrete utilization counts

These are the numbers our M2 demo currently shows on real data (verified
by running `py scripts/m2_rule_engine_demo.py`):

* **189,208 distinct part numbers** indexed from `1B.Product_Number` for
  Tier 1 exact-match (compiled regex union).
* **219 distinct manufacturer names** indexed from
  `1B.Manufacturer_Name` for Tier 2 fuzzy-match (rapidfuzz, threshold 90).
* **7,495 distinct `(Attribute_Name, Value)` pairs** loaded from 2A for
  the rule-engine guardrail.
* **9,918 `(Attribute_Name, Value, Unit_Suffix)` triples** indexed for
  Tier 3 numeric matching.
* **~158K train / ~20K val / ~20K test products** in
  `data/splits/{train,val,test}.parquet`, stratified by ProductType
  with seed = 42 (M1 reproducible output).

---

## 3. What we will use next (M3+ — planned)

Layer 3 (semantic matcher) is where the dataset starts working hard.
**M3 will read the full 1A file** to compute cluster statistics, and
will encode all 1B product descriptions into a 384-dimensional FAISS
index.

### 3.1 Per-milestone data plan

| Milestone | New data engaged | What we compute |
|---|---|---|
| **M3a** — FAISS index | `1B.Short_Description` + `1B.Extended_Description_Pre` for all 198,148 products | One 384-d vector per product → IVFFlat index (~300 MB), persisted under `artifacts/v1/run_<timestamp>/faiss.bin` |
| **M3b** — ProductType consensus | None new; uses M3a's index | Vote tally per query, no new disk reads |
| **M3c** — Per-cluster scoring | Full `1A_Product_Attribute_Pairs` (1.94 M rows, streamed in 200K chunks); `2A.Usage_Count` column | One `(μ, Σ)` cluster per `(ProductType, Attribute, Value)` triple. Ledoit-Wolf shrinkage covariance. Usage_Count log prior |
| **M4** — σ calibration | Validation split (~20K products) | Per-ProductType σ via grid-search on Brier + ECE |
| **M5** — Evaluation + secondary calibration | Test split + `1A_Product_Document_Links` (516K spec-sheet URLs; OCR a sample) | Test-set metrics; recalibrate σ on OCR'd text to mitigate the optimism caveat in spec §2.3 |
| **M6** — Online updates | Reviewer feedback (post-launch, not from eParts data) | Cluster μ refresh + λ=0.01 error pushback |

### 3.2 After M3, total utilization

When M3 finishes, the cumulative utilization picture looks like:

| Bucket | Rows | % of total |
|---|---:|---:|
| Engaged in code logic (1A + 1B + 2A) | ~2.15 M | ~62% |
| Reserved for M5 calibration (1A_Document_Links) | 0.52 M | ~15% |
| Not used in V1 (2B) | 0.75 M | ~22% |
| **Total provided** | **~3.41 M** | **100%** |

The 22% sitting in 2B is the **only data eParts provided that V1 cannot
exploit**. eParts confirmed on 2026-04-23 that 2B is not a formal
correction-tracking table; we treat this as known and budgeted.

---

> **Vocabulary note for non-ML stakeholders.** V1 deliberately performs
> **no neural-network training**. The encoder (`bge-small-en-v1.5`) was
> pre-trained by BAAI and is used with frozen weights (spec §4.3 [3a]
> "Weights: Frozen; no fine-tuning in V1"). What we *do* with the data
> is **encode** product descriptions into vectors, **index** them for
> fast similarity search, **compute** classical statistics (mean and
> Ledoit-Wolf covariance per cluster), and **calibrate** a single
> width parameter σ via grid search. None of these steps involves
> gradient descent, training loops, or learning-rate tuning. Real
> neural-network training (encoder fine-tuning) is deferred to the
> V2 backlog (spec §9.2). This is intentional — keeps V1 CPU-only,
> reproducible, and explainable.

## 4. Methodologies — how we handle their data

The capstone team committed to a set of operational conventions that
keep the work reproducible, auditable, and safe for eParts's data
under §2.2 of the V1 Engineering Spec.

### 4.1 Loading & I/O

* **`the_standard_data/` is read-only.** No source code writes back to
  the raw CSVs. All derived outputs go to `data/` (transient working
  files) or `artifacts/v1/run_<timestamp>/` (immutable training
  artifacts).
* **1A is streamed, never loaded whole.** The 1.4 GB file is read in
  200,000-row chunks via `pandas.read_csv(..., chunksize=200_000)`.
  Peak memory stays below 1 GB on a stock laptop.
* **Column-selective loads.** Each consumer reads only the columns it
  needs (e.g. M1 splits read only `Product_ID`, `ProductType_ID`,
  `Category_ID` from 1B). This reduces I/O and prevents accidental
  dependency on columns we never asked for.
* **Typed loaders.** Every column has an explicit dtype declaration in
  [`src/data/loader.py`](../src/data/loader.py) — pandas does not
  guess. This catches schema drift loudly the first time it appears.

### 4.2 Sampling & splitting

* **Stratified by ProductType, not by row.** Splits are built at the
  *product* level so a single product's attribute rows never spread
  across train and test (that would silently leak the test set into
  training).
* **Seed = 42, persisted.** Every random operation uses the same
  fixed seed; splits are written to parquet so reruns of the pipeline
  use the same train/val/test partition. Re-running
  `m1_build_splits.py` produces byte-identical outputs.
* **ProductTypes with fewer than 3 products land entirely in train.**
  These cannot supply both a val and a test sample anyway; downstream
  Layer 3 has its own ≥5-member cluster guard.

### 4.3 Confidence & explainability

* **Every prediction carries a calibrated confidence score** in `[0, 1]`.
  This is the central commitment of the V1 system to eParts (spec §6.1
  Continuity Contract).
* **Rule predictions are *demoted, not removed*** when they fail the
  2A guardrail. The flag `demoted_by_2a = True` is preserved on the
  output so reviewers can see *why* a rule fell through to Layer 3.
* **Reviewer-facing alternates.** For any prediction routed to human
  review (0.50 ≤ conf < 0.85), Layer 3 will surface top-3 candidate
  values with their individual confidence scores plus nearest-neighbor
  products. The intent is that reviewers never see a black box; they
  see the same evidence the model used.

### 4.4 Reproducibility & versioning

* **Per-run immutable artifacts.** Every training run writes to
  `artifacts/v1/run_<YYYYMMDD_HHMMSS>/` — encoder hash, FAISS index,
  cluster centroids, σ table. Old runs are never overwritten. The
  most recent valid run is aliased via `artifacts/v1/current/`.
* **Configuration in YAML, not code.** Every tunable parameter
  (encoder ID, FAISS hyperparameters, thresholds, σ grid) lives in
  [`config/`](../config/). Source code never hard-codes a magic
  number. eParts can re-run the pipeline against a different encoder
  by editing one file.

---

## 5. Data insufficiency — how we address it

Spec §2.3 catalogues the gaps in the supplied data. Here is how each
gap is handled in code today, plus what we ask of eParts when help
would close the gap.

### 5.1 1A descriptions are internal text, not customer language

**Impact.** The Layer 3 σ parameter calibrated on 1A will be tighter
than reality justifies — i.e. the model will be slightly over-confident
on real customer text.

**Mitigation in code.**
1. M5 will do a **secondary calibration pass on OCR'd text** from
   `1A_Product_Document_Links.csv` (which links to *real* spec-sheet
   PDFs). This recalibrates σ on a noisier distribution closer to
   what production traffic will look like.
2. After launch, a **third recalibration** uses the first ~500
   reviewer corrections, accumulated through the human-review queue.

**What we still need from eParts:** any anonymized real customer
emails or order-form CSVs would let us close this gap earlier.

### 5.2 2B is not usable as an error-case dataset

**Impact.** Without negative examples, V1 cannot train a contrastive
loss to sharpen σ at decision boundaries.

**Mitigation in code.** V1 trains on positives only. Confidence is
derived from the distribution of *correct* examples, not from a
positive/negative contrast. This is a conscious V1 simplification.

**What we still need from eParts:** **50–100 hand-picked correction
cases** (already a standing ask per spec §9.1). With these, V2 will
add a contrastive-loss fine-tuning step. Until then, the model is
slightly less calibrated near the 0.85 auto-process threshold than it
will eventually become.

### 5.3 141 attributes have zero rows in 1A

**Impact.** V1's semantic matcher cannot score these attributes because
it has no examples to build clusters from.

**Mitigation in code.** Layer 2's **rule engine still runs for these
attributes**. If the customer's text contains a numeric value + unit
that resolves uniquely in 2A, the rule engine emits a Tier-3 prediction.
If nothing matches, the result is routed to human review (conf = 0).

**What we still need from eParts:** confirmation of whether these 141
attributes are genuinely empty (already confirmed 2026-04-23) or will
be re-exported. V1 scope is the 348 attributes with 1A rows.

### 5.4 Low-sample clusters (< 5 members) downstream

**Impact.** A `(ProductType, Attribute, Value)` cluster with only 1–4
training members would give Mahalanobis distances that are statistically
unstable.

**Mitigation in code.** Per spec §4.3, clusters below 5 members are
**flagged at build time and hard-capped at confidence 0.7**. They are
never auto-processed — they always route to human review. This caps
the impact of sparse clusters at "wasted reviewer attention", never
"silent bad data".

**What we still need from eParts:** nothing immediate. Coverage will
grow naturally as eParts continues to add product specifications.

### 5.5 Ambiguous (value, unit) pairs in 2A

**Impact.** Some `(value, unit)` pairs map to several attributes in 2A
(e.g. `(24, vac)` could be `INPUT_VOLTAGE` or `OUTPUT_VOLTAGE`). Without
context the rule engine can't pick one.

**Mitigation in code.** Layer 2 Tier 3 **emits nothing** for
ambiguous pairs — Layer 3's semantic scoring will adjudicate using
context the rule engine doesn't see. This trades coverage for
precision deliberately.

**What we still need from eParts:** nothing — this is handled in code.

### 5.6 No real customer inputs yet

**Impact.** All our test fixtures are synthetic (1B-derived
descriptions, hand-written emails, reportlab-generated PDFs). We
can't validate Layer 1's robustness or Layer 4's calibration on
production-shaped data.

**Mitigation in code.** Synthetic fixtures cover the unit / structural
test cases. Production calibration is explicitly deferred to M5
(via OCR'd PDFs) and post-launch (via reviewer corrections).

**What we still need from eParts:**
* **P3-A** — customer submission templates (the CSV column shapes
  customers actually use)
* **P3-B** — request volume distribution by ProductType / Category
* **10–20 anonymized real customer emails**
* **A handful of real scanned spec-sheet PDFs**

### 5.7 2A has no rows for Manufacturer

**Impact.** The rule engine's 2A guardrail would demote every
Tier-2 manufacturer hit because Manufacturer isn't a 2A attribute.

**Mitigation in code.** The guardrail accepts an `exempt_attribute_names`
set; the engine factory passes `{"Manufacturer"}`. Canonical-name
closure for manufacturers is enforced upstream by the fuzzy index
(which is built directly from 1B's distinct manufacturer list, so by
construction it never invents a name). This is safe — see
[Layer1_Layer2_Implementation_Report.md §4](Layer1_Layer2_Implementation_Report.md)
for the full rationale.

**What we still need from eParts:** *optional*. If 2A is intended to
be the single source of truth for valid attribute values, adding
Manufacturer rows would let us remove the exemption. Either approach
works.

---

## 6. Visual — data → layer flow

The diagram below shows which data file feeds which layer, plus
whether the use is build-time (training the index / computing
cluster statistics) or query-time (looking up at inference).

```mermaid
flowchart LR
    subgraph DATA ["eParts data (the_standard_data/)"]
        D1A[(1A Product<br/>Attribute Pairs<br/>1.94 M rows)]:::data
        D1B[(1B Product<br/>Master<br/>198 K rows)]:::data
        D2A[(2A Values per<br/>Attribute<br/>9.9 K rows)]:::data
        DLNK[(1A Document<br/>Links<br/>516 K rows)]:::data
        D2B[(2B Apparent<br/>Corrections<br/>747 K rows)]:::unused
    end

    subgraph M1 ["M1 ✓"]
        SPLIT[Stratified splits<br/>train · val · test]:::done
    end

    subgraph M2 ["M2 ✓"]
        T1[Tier 1<br/>Part-number]:::done
        T2[Tier 2<br/>Manufacturer]:::done
        T3[Tier 3<br/>Numeric+unit]:::done
        GUARD[2A guardrail]:::done
    end

    subgraph M3 ["M3 pending"]
        FAISS[FAISS index<br/>build-time]:::pending
        CLUST[Cluster μ + Σ<br/>build-time]:::pending
        PRIOR[Usage_Count prior]:::pending
    end

    subgraph M5 ["M5 pending"]
        CAL[Secondary calibration<br/>via OCR'd PDFs]:::pending
    end

    D1B -. Product_Number .-> T1
    D1B -. Manufacturer_Name .-> T2
    D2A -. Attr · Value · Unit .-> T3
    D2A -. valid-value set .-> GUARD
    D1B -. Product_ID .-> SPLIT

    D1B -. Short / Extended Description .-> FAISS
    D1A -. 1.94 M attribute-value pairs .-> CLUST
    D2A -. Usage_Count .-> PRIOR

    DLNK -. 516 K spec-sheet URLs .-> CAL
    D1A -. test split descriptions .-> CAL

    D2B -. NOT USED IN V1 .-> X((✗)):::unused

    classDef data fill:#fff2cc,stroke:#d6b656,color:#000
    classDef unused fill:#f0f0f0,stroke:#999,color:#666,stroke-dasharray: 5 5
    classDef done fill:#d5e8d4,stroke:#82b366,color:#000
    classDef pending fill:#dae8fc,stroke:#6c8ebf,color:#000
```

**Reading guide:**
* Green = data flow already implemented (M1 + M2).
* Blue = data flow planned for upcoming milestones (M3 + M5).
* Grey / dashed = data we deliberately do not use in V1 (2B).

---

## 7. Quick reference — open data asks

For convenience when forwarding to eParts:

**Strongly requested (close known gaps):**
1. P3-A — customer submission templates (CSV column shapes per channel)
2. P3-B — request volume distribution by ProductType / Category
3. 10–20 anonymized real customer emails
4. A handful of real scanned spec-sheet PDFs
5. 50–100 hand-picked correction cases (standing ask per spec §9.1)

**Optional / nice-to-have:**
6. Updated 2A export including Manufacturer as a first-class attribute
7. Re-export including the 141 currently-empty attributes (if not
   permanently out of scope)

---

*Document owner: ML team — eParts Capstone (MSE Studio).*
*Related docs:* [Data_Delivery_Assessment.md](Data_Delivery_Assessment.md) ·
[V1 Engineering Spec §2 (Data Foundation)](V1_Architecture_Design.md) ·
[ExtractionHandoff_Spec.md](ExtractionHandoff_Spec.md).
