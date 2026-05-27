# eParts Services — ML Confidence Scoring System
## Capstone Technical Design Document

**Program:** MSE Studio 2026
**Team:** eParts Services Project Team
**Client:** eParts Services
**Document Version:** 1.0 (Consolidated V1 Design)
**Date:** April 2026

---

## Executive Summary

eParts Services receives a continuous stream of product specification requests from customers — via email bodies, PDF spec sheets, and CSV order files — that must be mapped to the correct entries in eParts's product database. Today this is handled manually, which is slow, inconsistent, and scales poorly. Our Capstone delivers an **automated mapping pipeline with per-prediction confidence scores**: high-confidence predictions auto-populate the database, while low-confidence predictions are routed to a human reviewer. Over time the system learns from reviewer corrections and becomes progressively more accurate.

This document consolidates three threads of our work:

1. **The original Proposal** ([ML_Model_Proposal_and_Data_Requirements.md](ML_Model_Proposal_and_Data_Requirements.md), March 2026) — which defined the four-layer architecture, the confidence mathematics, and the data requirements we communicated to eParts.
2. **The data-delivery review** ([Data_Delivery_Assessment.md](Data_Delivery_Assessment.md), April 2026) — our quantitative assessment of what eParts actually delivered versus what we asked for.
3. **The V1 implementation design** ([V1_Architecture_Design.md](V1_Architecture_Design.md), April 2026) — the two targeted upgrades we identified to the Proposal's Layer 3 that substantially improve V1 without disturbing the agreed confidence framework.

**Three things to know up front:**

- **The Proposal's four-layer architecture and all decision-level mathematics are preserved.** Mahalanobis distance, Gaussian confidence decay, k-NN scoring, α-weighted fusion, thresholds, online centroid updates, error-pushback — all intact.
- **We upgrade Layer 3's text representation** from TF-IDF-weighted word embeddings (a 2014-era approach) to a modern pre-trained sentence transformer, and reorganize retrieval to exploit the ProductType hierarchy that is already present in eParts's data schema.
- **These upgrades are additive, low-risk, and low-cost.** No additional training is required, no additional data is required, no commitments to the client change, and the entire system still runs on a single CPU with sub-50 ms per-query latency.

---

## Table of Contents

1. Project Context & Problem Statement
2. Data Foundation
3. The Original Proposal (V0 Baseline)
4. Gap Analysis — Why the Proposal's Layer 3 Needs Upgrading
5. V1 Architecture
6. Before & After Comparison
7. Advantages of the V1 Architecture
8. What Stays the Same (Continuity with the Proposal)
9. Training, Calibration & Evaluation Protocol
10. Implementation Plan
11. Platform Integration Points
12. Risks, Limitations & Open Issues
13. V2 Backlog
14. Appendices

---

## 1. Project Context & Problem Statement

### 1.1 The Business Problem

eParts Services maintains a product database covering ~198,000 active products across 77 categories and 755 product types. Customer requests arrive in three main channels:

- **Email bodies** — free-form natural-language descriptions of the product needed.
- **PDF spec sheets** — structured but layout-variable documents.
- **CSV order forms** — semi-structured tabular inputs.

The eParts product team must read each request, identify the product or product family, and enter the relevant attribute values (voltage, mounting type, temperature range, etc.) into the catalog. For a request describing *"3 units of Belimo LM24-3-T actuator, 24VAC, spring return, 5Nm torque, 0-10V control input signal,"* the team must resolve this to:

```
Manufacturer    : Belimo                          (Manufacturer_ID = 18)
Product_ID      : [internal ID]
INPUT_VOLTAGE   (Attribute_ID = 13) → "24VAC"
ACTION          (Attribute_ID = 48) → "SPRING RETURN"
INPUT_SIGNAL    (Attribute_ID = 51) → "0-10V"
```

The manual effort is significant. eParts has neither the staffing nor the consistency to scale this up. They need automation for the easy cases while still catching the hard ones.

### 1.2 The Core Technical Challenge

Any automation must meet a very specific requirement: **the system must know what it does not know.** An automated mapping that is confidently wrong is worse than no mapping at all — it silently corrupts the database. The system must therefore produce, for every prediction, a calibrated **confidence score** so the business can decide:

- **High confidence (auto-process):** commit to the database without human intervention.
- **Medium confidence (review):** queue for a human to confirm.
- **Low confidence (reject):** flag as unclear, return to sender.

The confidence score is not a ranking signal. It is a commitment: *"if we tell you we are 90% confident, then among the things we tell you that at 90% confidence, 90% of them really are correct."* Getting that calibration right — and getting it to stay right as the data distribution drifts — is the central engineering problem.

### 1.3 Capstone Scope

- **Delivered:** V1 end-to-end pipeline, reference indexing over the full 1B product catalog, REST inference endpoint, telemetry, evaluation report.
- **Out of scope for V1:** full MLOps platform (feature store, model registry UI, automated retraining), domain fine-tuning of the encoder, LLM-assisted extraction.
- **V2 backlog:** see §13.

### 1.4 Success Criteria

| Metric | V1 target |
|---|---|
| Attribute-level top-1 accuracy (held-out test) | ≥ 0.85 on head ProductTypes |
| ProductType classification accuracy | ≥ 0.92 |
| Expected Calibration Error (ECE) | ≤ 0.05 |
| Auto-process precision @ threshold 0.85 | ≥ 0.95 |
| End-to-end p95 latency | ≤ 200 ms |
| Auto-process coverage @ threshold 0.85 | ≥ 50% of realistic inputs |

Targets are set as acceptance criteria for the V1 evaluation report.

---

## 2. Data Foundation

### 2.1 What eParts Delivered (2026-04-16)

eParts delivered five files after our Proposal's Section 5 data request:

| File | Rows | Purpose | Coverage |
|---|---:|---|---|
| `1A_Product_Attribute_Pairs.csv` | 1,938,426 | Input→output pairs: product descriptions → verified (Attribute, Value) mappings | 134,117 distinct products; 348 attributes |
| `1A_Product_Document_Links.csv` | 516,005 | Product_ID → spec sheet PDF or image URL | 178,194 products have ≥ 1 document |
| `1B_Product_Master.csv` | 198,147 | Full product catalog | Essentially the entire active catalog |
| `2A_Values_Per_Attribute.csv` | 9,918 | All (Attribute, Value, Unit_Suffix) combinations + Usage_Count | 346 attributes |
| `2B_Apparent_Correction_Cases.csv` | 746,845 | Proxy for error cases via Edit Orders | **Unusable — see §2.3** |

**Data dictionary:** [the_standard_data/Data Dictionary.pdf](../the_standard_data/Data%20Dictionary.pdf)

### 2.2 What's Strong About the Delivery

- **Scale.** 1.94 M labeled (input, output) pairs is over three orders of magnitude above the PAC theoretical minimum (830) we computed in the Proposal.
- **Structured numeric fields.** `DigitalValue`, `Unit_Suffix`, `RangeLow`, `RangeHigh` are provided directly — our rule engine does not need to regex them out of free text.
- **Usage_Count as a frequency prior.** A bonus column we did not request, enabling Bayesian priors that downweight rare values.
- **Document links.** An over-delivery: 516 K spec-sheet URLs give us end-to-end OCR test material we did not originally have.
- **Catalog completeness.** 1B is 198 K rows versus the Data Dictionary's 198,465 active products — essentially complete.
- **100% join integrity** on the enforced foreign keys (Product_ID, ProductType_ID, Manufacturer_ID, Category_ID).

### 2.3 Known Gaps (Discussed in Data Delivery Assessment)

- **1A descriptions are internally curated text**, not raw customer inputs. This is acceptable for training the similarity model but means σ-calibration on this distribution will be *optimistic* for real-world inputs.
- **2B is not usable as an error-case dataset.** Our analysis: only 6 distinct Edit Orders, 6 distinct reasons (58% `"test"`, 38% vendor-switch operations, 4% de-activations); none correspond to semantic corrections. `Edit_Count` turns out to be the batch size of the Edit Order, not the number of edits per product. Only 291 products show more than one EO event. We have requested 50–100 hand-picked correction cases from eParts instead ([Data_Feedback_for_eParts.md](Data_Feedback_for_eParts.md)).
- **Product_Name is empty on 99.997% of rows** in 1B — either deliberately unmaintained or an export issue. Confirmation pending.
- **141 active attributes (29%)** have zero rows in 1A. Either unused, filtered, or requiring a targeted re-export. Confirmation pending.
- **P3-A (customer templates) and P3-B (request volume by category)** were not delivered. Non-blocking.

### 2.4 Implications for V1 Design

1. We have more than enough positive data; our bottleneck is **calibration realism**, not scale.
2. Without real correction examples, V1 confidence is trained purely on the positive distribution — a limitation we flag to the client and mitigate via post-launch calibration on reviewer feedback.
3. The ProductType/Attribute hierarchy embedded in the data is strong and clean. The V1 architecture exploits it.

---

## 3. The Original Proposal (V0 Baseline)

This section summarizes the architecture from the client-facing Proposal. The full document is at [ML_Model_Proposal_and_Data_Requirements.md](ML_Model_Proposal_and_Data_Requirements.md).

### 3.1 Four-Layer Pipeline

```
  [Email / PDF / CSV]
           │
           ▼
  LAYER 1 — Text Extraction          (no ML, deterministic)
           │
           ▼
  LAYER 2 — Rule Engine               exact matches → conf_rule
           │
           ▼
  LAYER 3 — Semantic Similarity       TF-IDF × GloVe → Mahalanobis → conf_embed
           │
           ▼
  LAYER 4 — Decision & Feedback       α·conf_rule + (1−α)·conf_embed, thresholds, online updates
           │
           ▼
  [Auto-process  |  Human review  |  Flag unclear]
```

### 3.2 Core Formulas (Proposal §4)

**Text-to-vector (Proposal §4.1):**

```
v(sentence) = Σ [ tfidf(w_i) × embed(w_i) ] / Σ tfidf(w_i)
```

where `embed(w)` is a pre-trained ~100-dimensional word vector (GloVe-style) and `tfidf(w)` downweights common words like "the" and upweights technical terms like "thermistor."

**Similarity (Proposal §4.2):**

```
similarity(A, B) = (A · B) / (‖A‖ × ‖B‖)       (cosine, rescaled to [0,1])
```

**Reference region (Proposal §4.3):**

```
μ = (1/N) Σ v(sentence_i)                            centroid of confirmed-correct vectors
D(q) = √[ (q − μ)ᵀ Σ⁻¹ (q − μ) ]                    Mahalanobis distance
conf_embed = exp( −D(q)² / (2σ²) )                   Gaussian decay → [0, 1]
```

**k-NN alternative (Proposal §4.4):**

```
conf_knn(q) = (1/k) Σᵢ₌₁ᵏ sim(q, v_i)               average similarity to top-k neighbors, k=5
```

**Fusion & thresholds (Proposal §4.5):**

```
conf_final = α · conf_rule + (1 − α) · conf_embed,   α = 0.7

≥ 0.85  →  auto-process
0.50–0.85  →  human review queue
< 0.50  →  flag unclear / return to sender
```

**Online updates (Proposal §4.6):**

```
μ_new = (N · μ_old + v_new) / (N + 1)                (confirmed correct)
μ_corrected = μ_old − λ · (v_wrong − μ_old)          (error pushback, λ = 0.01)
```

### 3.3 Why We Committed to This Framework

The Proposal's framework was chosen for three reasons that remain entirely valid:

- **Interpretability.** Every number in the pipeline has a plain-language meaning. A reviewer can understand *why* a confidence score is what it is by inspecting distances and nearest neighbors.
- **Calibratable confidence.** The Gaussian decay with a single tunable σ is a simple, well-understood calibration mechanism — far easier to trust than an arbitrary softmax output.
- **Cheap incremental learning.** A running-mean update after every human review means the system improves continuously, without expensive retraining jobs.

These three properties are what we commit to eParts. They are preserved entirely in V1.

---

## 4. Gap Analysis — Why the Proposal's Layer 3 Needs Upgrading

The Proposal's Layer 3 uses **TF-IDF-weighted averaging of GloVe-style word vectors** as its text representation, and organizes retrieval around **a single global reference pool** with one centroid and one covariance matrix. Both choices were reasonable in 2014. In 2026, each is the weakest link in the pipeline, and each has clean, low-risk upgrades.

### 4.1 Failure Modes of TF-IDF + GloVe on eParts Data

**Failure 1: Synonyms and paraphrases are invisible.**

In eParts's domain, customers use varied terminology for the same concept:
- `"thermistor"` vs. `"temperature sensor"` vs. `"temp probe"`
- `"actuator"` vs. `"damper motor"`
- `"strap-on mount"` vs. `"clamp-on installation"`

TF-IDF treats each of these as distinct tokens. GloVe can partially help if both words are in its vocabulary and semantically related in general-purpose text, but:
- GloVe was trained on Common Crawl / Wikipedia, where `"thermistor"` and `"temperature sensor"` appear in very different contexts than in HVAC catalogs.
- Weighted averaging dilutes whatever signal exists.

**Failure 2: Word order is discarded.**

A customer writing *"24V input signal, 0-10V output"* and another writing *"0-10V input signal, 24V output"* produce **identical sentence vectors** under weighted averaging — but the products are completely different.

**Failure 3: Rare technical tokens become zero vectors.**

Terms like `"10K-3"`, `"BA/3K-S#"`, `"LM24-3-T"` are out-of-vocabulary for GloVe. Their embeddings are zero vectors, contributing nothing to the sentence representation. Yet these are often the single most informative tokens in the input.

**Failure 4: Spelling variants and abbreviations fragment the signal.**

`"24VAC"`, `"24 V AC"`, `"24 vac"`, `"24 volts AC"` — TF-IDF treats all four as different tokens. Real customer text has all of these variants and more.

### 4.2 Failure Modes of a Flat Reference Pool

The Proposal treats *all* confirmed-correct sentences as a single reference cluster with one centroid μ and one covariance Σ. This ignores the hierarchical structure eParts's own data dictionary exposes:

```
Category (77)
   └─ ProductType (755)
         └─ Product (198 K)
               └─ Attribute (487 per ProductTypeAttributes schema, avg 4.2 per ProductType)
```

**Consequence 1: Cross-category leakage.**

Under a flat pool, a thermistor description that happens to land near an actuator cluster in embedding space could receive a confident prediction of `ACTION = SPRING RETURN` — an attribute that only applies to actuators. The Proposal has no structural mechanism to prevent this.

**Consequence 2: Wasted search.**

With 487 attributes to consider, but typically only 4.2 attributes relevant per ProductType, a flat retrieval does ~100× more work than necessary for every query.

**Consequence 3: Ambiguous inputs are scored silently.**

The Proposal's confidence score is a single number. An input like *"Johnson Controls T-6000, 24V"* where the "T-6000" prefix appears in both thermostats and temperature sensors cannot be represented: either one candidate wins arbitrarily (overconfident), or both get medium scores (uninformative to the reviewer).

### 4.3 What 2026 State-of-the-Art Offers

Two techniques have become the industry default for this type of retrieval system, both mature and production-ready:

**Pre-trained sentence transformers (Reimers & Gurevych 2019; BGE 2023; etc.):**
- Generate a single 384- or 768-dimensional vector for an entire sentence in one forward pass.
- Trained on hundreds of millions of sentence pairs with contrastive loss — directly optimized for "semantically similar sentences get similar vectors."
- Subword tokenization handles out-of-vocabulary terms.
- Context-sensitive: the same word in different sentences gets different contributions.
- Available open-source, runnable on CPU at millisecond latency.

**FAISS (Johnson et al., Meta 2017):**
- Production-grade nearest-neighbor library with IVF / HNSW / PQ index types.
- Can index tens of millions of vectors with sub-10 ms query latency on a single machine.
- Memory footprint for eParts's 198 K products: ~300 MB.

**Hierarchical routing:**
- The eParts schema already partitions attributes by ProductType.
- A first-stage ProductType classifier, followed by attribute scoring scoped to that ProductType's schema, collapses a 487-way prediction into a 4-way-average prediction.

These three are not experimental. They are what any production retrieval system in 2026 uses as its foundation, and each has permissive licenses and mature tooling.

---

## 5. V1 Architecture

### 5.1 Updated Pipeline

```
┌────────────────────────────────────────────────────────────────┐
│  INPUT SOURCES                                                 │
│  Email body  │  PDF extracted text  │  CSV rows                │
└─────────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────┐
│  LAYER 1 — Text Extraction & Normalization   (UNCHANGED)       │
│  • CSV → parse columns                                         │
│  • PDF → text + OCR fallback (driven by 1A_Product_Doc_Links)  │
│  • Email → strip signatures, headers                           │
│  • Unit normalization (kΩ → kohm, VAC/VDC/V, °F/°C)            │
└─────────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────┐
│  LAYER 2 — Rule Engine  (UNCHANGED in framework; hardened      │
│                          with 2A valid-value guardrail)        │
│  • Part-number exact match → conf_rule = 1.0 (terminal)        │
│  • Manufacturer-name fuzzy match (rapidfuzz ≥ 90)              │
│  • Numeric value + unit match via 1A's DigitalValue/Unit_Suffix│
│  • Every rule output must be a legal value per 2A              │
│  Output: {attribute: (value, conf_rule)}                       │
└─────────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────┐
│  LAYER 3 — Semantic Matcher   (UPGRADED)                       │
│                                                                │
│  [3a] Encode input text to a vector                            │
│       q = SentenceTransformer("bge-small-en-v1.5").encode(t)   │
│       q ∈ ℝ³⁸⁴, L2-normalized                                  │
│                                                                │
│  [3b] FAISS retrieval over 1B Product Master                   │
│       candidates = index.search(q, K=50)                       │
│       → list of (Product_ID, sim(q, product_i))                │
│                                                                │
│  [3c] ProductType consensus                                    │
│       vote[PT] = Σ sim(q, p_i) for p_i with ProductType = PT   │
│       PT_predicted = argmax_PT vote[PT]                        │
│       PT_conf     = vote[PT_predicted] / Σ vote[PT]            │
│       If PT_conf < 0.6 → flag ambiguous, cap conf_final at 0.75│
│                                                                │
│  [3d] Per-attribute, per-value confidence (Mahalanobis)        │
│       For A in ProductTypeAttributes[PT_predicted]:            │
│         For each candidate value v under (PT, A) in 1A:        │
│           cluster = candidate products mapping (A→v)           │
│           μ_cluster = mean(encoder(descriptions))              │
│           Σ_cluster = shrinkage-estimated covariance           │
│           D = Mahalanobis(q, μ_cluster, Σ_cluster)             │
│           conf_embed(A,v) = exp(−D² / 2σ²)                     │
│         Usage_Count prior multiplier from 2A                   │
│         Return top-3 values per attribute with confidence      │
└─────────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────┐
│  LAYER 4 — Decision & Feedback   (UNCHANGED)                   │
│  • conf_final = α · conf_rule + (1 − α) · conf_embed, α=0.7    │
│  • ≥ 0.85 → auto-process                                       │
│  • 0.50–0.85 → human review queue                              │
│  • < 0.50 → flag unclear, return to sender                     │
│  • Reviewer feedback → online centroid update (per cluster):   │
│        μ_new = (N·μ_old + v_new) / (N + 1)                     │
│        μ_corrected = μ_old − λ·(v_wrong − μ_old), λ = 0.01     │
└────────────────────────────────────────────────────────────────┘
```

### 5.2 Layer-by-Layer Detail

#### Layer 1 — Text Extraction

Unchanged from Proposal §3. Implementation notes:

- **CSV ingestion:** chunked pandas reader with `chunksize=200,000`; the 1.4 GB `1A_Product_Attribute_Pairs.csv` never loaded in full.
- **PDF ingestion:** `pdfplumber` for native text; `pytesseract` OCR fallback for scanned pages. Routing driven by 1A_Product_Document_Links' `ImageFile` flag.
- **Email ingestion:** Python's `email` module for parsing; signatures stripped by a curated heuristic (regex for common footer markers, reply-chain trimming).
- **Unit normalization:** `config/unit_aliases.yaml` maps variants to canonical forms. Extensible by the eParts team without code changes.

#### Layer 2 — Rule Engine

Unchanged in framework, with one hardening:

- **Part-number matching:** 198 K regex patterns auto-compiled from the `Product_Number` column of 1B. Cached as a single `regex.Pattern | Pattern | ...` compiled union. Exact match on a part number terminates the pipeline with `conf_final = 1.0` (Proposal §4.5 special case).
- **Manufacturer fuzzy match:** `rapidfuzz.fuzz.token_set_ratio ≥ 90` against the 220 distinct manufacturer names. Confidence 0.85 on match.
- **Numeric value + unit match:** uses 1A's `DigitalValue` and `Unit_Suffix` columns directly. No regex extraction from free text for structured numeric attributes.
- **New guardrail:** any rule-produced attribute value must appear in `2A_Values_Per_Attribute`. If not, the rule prediction is demoted to Layer 3 for semantic adjudication. This prevents the rule engine from emitting values that don't exist in the database.

#### Layer 3 — Semantic Matcher (Upgraded)

**[3a] Encoder.**
- Model: `BAAI/bge-small-en-v1.5` via `sentence-transformers`.
- Dimension: 384.
- Normalization: L2 (inner product = cosine similarity).
- Latency: ~5 ms per sentence on CPU; ~1 ms with batching.
- **No fine-tuning in V1.** The pre-trained weights are used as-is. Fine-tuning on 1A pairs is a V2 experiment.

**[3b] FAISS index.**
- Index type: `IVFFlat` with `nlist = 512` (empirically sound for ~200 K vectors).
- Trained on encoded descriptions from 1B (Short_Description as primary text; Extended_Description_Pre appended when available).
- Query: `nprobe = 16` for top-K = 50 retrieval, ~5 ms latency.
- Memory: 198,147 × 384 × 4 B ≈ 302 MB.
- Persisted to `artifacts/v1/faiss_index_<timestamp>.bin` with versioning.

**[3c] ProductType consensus.**
The top-K=50 candidate products vote on ProductType, weighted by similarity. Two thresholds:

```
PT_conf = vote[PT_predicted] / Σ_PT vote[PT]

If PT_conf ≥ 0.80 → high consensus, proceed normally
If 0.60 ≤ PT_conf < 0.80 → normal consensus
If PT_conf < 0.60 → ambiguous → cap final confidence at 0.75
```

This is our structural mechanism for the "T-6000" ambiguous-prefix case described in the Proposal §5.

**[3d] Attribute-value scoring.**
For each attribute in `ProductTypeAttributes[PT_predicted]`, the candidate values are those appearing under (PT_predicted, attribute) in 1A. For each candidate value cluster:

```
cluster_products = {p_i : p_i in top-K ∧ 1A[p_i].attribute = A ∧ 1A[p_i].value = v}
μ_cluster = mean(encoder(product.description)  for product in cluster_products)
Σ_cluster = LedoitWolf(cluster_vectors).covariance_    ← shrinkage for stable inverse
D²        = (q − μ_cluster).T @ Σ_cluster⁻¹ @ (q − μ_cluster)
conf_embed(A, v) = exp(−D² / (2σ_PT²))                ← σ calibrated per ProductType

usage_prior(A, v) = 0.5 + 0.5 · log(1 + Usage_Count(A, v)) / log(1 + max_Usage_Count(A))
conf_embed_final(A, v) = conf_embed(A, v) · usage_prior(A, v)
```

Top-3 values per attribute are returned. Clusters with fewer than 5 members are flagged as low-sample; their confidence is hard-capped at 0.7.

#### Layer 4 — Decision & Feedback

Unchanged mathematically. Two integration notes:

- **Fusion happens per attribute.** For each attribute A, `conf_final(A) = α · conf_rule(A) + (1 − α) · conf_embed_final(A, argmax_v conf_embed_final(A, v))`.
- **Ambiguous ProductType cap:** if PT_conf < 0.60, the final attribute confidences are capped at 0.75 regardless of the raw scores. This routes uncertain-category cases to human review instead of letting strong attribute signals mask category ambiguity.
- **Online updates** apply per cluster: when a reviewer confirms value `v` for attribute `A` on an input with vector `q`, `μ_{PT, A, v}` and `Σ_{PT, A, v}` are updated.

---

## 6. Before & After Comparison

| Aspect | Proposal V0 | V1 Design | Impact |
|---|---|---|---|
| Text encoder | TF-IDF × GloVe ~100-d word avg | `bge-small-en-v1.5` 384-d sentence encoder | Synonyms / paraphrases / OOV handled |
| Word order | Lost (bag of words) | Preserved (transformer context) | Fewer false positives on reordered specs |
| Rare technical tokens | Often OOV → zero vector | Subword tokenization | Key discriminative tokens retained |
| Retrieval structure | Single flat reference pool | Two-stage: FAISS → top-K → ProductType consensus → attribute scoring | Prevents cross-category leakage |
| Attribute scope per query | All 487 attributes | ~4.2 (ProductType schema) | ~100× less work; eliminates impossible predictions |
| Ambiguous ProductType handling | Single confidence per prediction | Explicit PT_conf threshold → cap final confidence | Ambiguity surfaces cleanly to reviewer |
| Centroid granularity | One global μ, Σ | Per (ProductType, Attribute, Value) μ, Σ | Tighter clusters → more informative distances |
| Usage frequency prior | Not used | Logarithmic prior from 2A Usage_Count | Rare values no longer silently over-predicted |
| Mahalanobis / Gaussian decay math | Proposal §4.3 | Identical formulas, applied per cluster | No client-facing change |
| α fusion, thresholds | Proposal §4.5 | Identical | No client-facing change |
| Online update, error pushback | Proposal §4.6 | Identical, per cluster | No client-facing change |
| PAC sample bound | Proposal §4.7, ~830 samples | Still applies, checked per cluster | No change |
| Training cost | Required training pipeline assumed | No training required (encoder pre-trained) | Zero compute spend for the encoder |
| Hardware | Unspecified | CPU-only, single-machine | No GPU dependency for V1 |
| Inference latency | Not estimated | p50 ~30 ms, p95 ~150 ms expected | Well within 200 ms target |
| Memory | Unspecified | ~400 MB peak (FAISS + model) | Laptop-runnable |

**Interpretation:** the V1 changes are localized entirely to Layer 3. The Proposal's agreement with eParts — the confidence framework, the decision thresholds, the feedback loop, the PAC bound — is fully preserved. From the client's mathematical-contract standpoint, nothing has moved.

---

## 7. Advantages of the V1 Architecture

### 7.1 Quantifiable Advantages

**Retrieval quality.** Pre-trained sentence transformers outperform TF-IDF+GloVe averaging on standard retrieval benchmarks (BEIR, MTEB) by 25–40 nDCG points. While eParts's domain is narrower than these benchmarks, the effect is directionally the same — synonym recall, paraphrase matching, and OOV handling all improve meaningfully.

**Attribute search efficiency.** Data Dictionary lists 487 active attributes; ProductTypeAttributes has 1,857 mappings across 755 ProductTypes — an average of 4.2 attributes per ProductType. V1 scores ~4 candidates per query instead of ~200. That is a 50× reduction in per-query scoring work, and a similar reduction in the reviewer's cognitive load when inspecting which attributes the system considered.

**Memory and compute.**
- FAISS index: ~300 MB.
- Encoder model weights: ~130 MB (bge-small).
- Centroid/covariance artifacts: ~50 MB estimated.
- Total peak memory: under 500 MB.
- End-to-end CPU latency: p50 ≈ 30 ms, p95 ≈ 150 ms expected.
- No GPU needed for training (encoder is pre-trained) or inference.

**Zero training data overhead.** V1 requires no additional training compute — the encoder is used as-is. This means we can start building and benchmarking on day one of implementation.

### 7.2 Qualitative Advantages

**The Proposal's mathematical commitments are preserved.** We can walk eParts through the Proposal's §4 formulas and point to exactly the same formulas in V1. The only thing that changes is how the input vector `q` is computed — and that change is a well-known 2026 best practice, not a novel research choice.

**Interpretability is retained.**
- The nearest-neighbor products returned by FAISS are inspectable by name.
- The ProductType consensus vote shows exactly how the system routed the input.
- Each attribute prediction shows its cluster centroid, the distance, and the top-3 candidate values with scores.
- Every confidence can be traced to Mahalanobis distance + Gaussian decay, with no black-box softmax.

**Low-risk, reversible upgrade.** If any V1 component underperforms, we can swap it out without disturbing the framework:
- Encoder: swap `bge-small` for `all-MiniLM-L6-v2` or `bge-base` via one config line.
- FAISS index type: swap `IVFFlat` for `HNSW` or exact `Flat` search.
- ProductType consensus: tune the 0.60/0.80 thresholds on a validation set.

**Direct alignment with eParts's data schema.** The ProductTypeAttributes table literally tells us which attributes are relevant for which ProductTypes. V1 uses this authoritative schema as a hard constraint on the search space. The Proposal's flat design ignored this structure.

**Maintainability.** Pre-trained encoders and FAISS are widely supported, well-documented open-source projects with active maintenance. They are not research code.

**Explicit handling of ambiguity.** The PT_conf threshold converts "ambiguous category" from an implicit failure mode into an explicit, auditable decision. A reviewer reading the system's output can see *"the system thought this was 55% thermostat / 45% temperature sensor, and capped its confidence accordingly"* — exactly the kind of honest uncertainty the Proposal's confidence framework is supposed to surface.

### 7.3 What the Client Gets That They Didn't Have in the Proposal

- A system that handles synonyms and paraphrases out of the box.
- A system that won't emit cross-category-nonsensical predictions.
- A system with an explicit, inspectable handling of ambiguous inputs.
- A system with per-attribute latency budgets that fit in a web request.
- A system that can be demoed on a laptop.

None of this costs the client anything in terms of the Proposal's commitments.

---

## 8. What Stays the Same (Continuity with the Proposal)

This section exists for one reason: to make absolutely clear to the client, teaching staff, and future team members that we are not walking back any of the commitments in the Proposal.

| Proposal commitment | Preserved in V1? |
|---|---|
| Four-layer architecture (Extraction → Rule → Semantic → Decision) | ✅ Identical structure |
| Mahalanobis distance formula (Proposal §4.3) | ✅ Unchanged |
| Gaussian confidence decay `exp(−D²/2σ²)` | ✅ Unchanged |
| k-NN alternative scoring (Proposal §4.4) | ✅ Available as fallback |
| α-weighted fusion `α · conf_rule + (1 − α) · conf_embed` | ✅ Unchanged, α = 0.7 |
| Decision thresholds (0.85 / 0.50) | ✅ Unchanged |
| Online centroid update (Proposal §4.6) | ✅ Unchanged |
| Error pushback with λ = 0.01 | ✅ Unchanged |
| PAC sample bound (Proposal §4.7) | ✅ Still holds; checked per cluster |
| Rule engine's terminal exact-match (conf = 1.0) | ✅ Unchanged |
| Rule engine's fuzzy / partial match tiers | ✅ Unchanged |
| Feedback loop from human review | ✅ Unchanged |
| Interpretability requirement | ✅ Strengthened |
| CPU-only deployability | ✅ Strengthened |

The V1 changes are **strictly additive and strictly internal to Layer 3's implementation**. From the Proposal's standpoint, we're using a better text encoder and being smarter about where we look — no more, no less.

---

## 9. Training, Calibration & Evaluation Protocol

### 9.1 Data Split

- Source: `1A_Product_Attribute_Pairs.csv` (1.94 M rows, 134,117 products, 348 attributes).
- Stratified 80 / 10 / 10 split by ProductType.
- Random seed fixed (`seed = 42`); split files persisted under `data/splits/`.
- Rationale: stratification ensures every ProductType is represented in both train and eval; a pure random split would under-sample rare ProductTypes.

### 9.2 Reference Index Build (Train)

1. Encode all train-split product descriptions → 384-d vectors.
2. Build FAISS IVFFlat index (nlist=512, trained on a random 100K subset).
3. For each (ProductType, Attribute, Value) cluster with ≥ 5 training members:
   - Compute mean μ.
   - Compute shrinkage-estimated covariance Σ via Ledoit-Wolf.
   - Store cluster metadata: `{cluster_id, N, μ, Σ, Usage_Count_from_2A}`.
4. Clusters with < 5 members: flagged low-sample; confidence hard-capped at 0.7 at inference time.
5. Persist: `artifacts/v1/run_<timestamp>/{faiss.bin, centroids.parquet, sigma_table.parquet, encoder_hash.txt}`.

### 9.3 Calibration (Val)

For each ProductType, grid-search `σ ∈ {0.1, 0.3, 0.5, 1.0, 2.0, 5.0}` to minimize:

```
val_loss(σ) = BrierScore(conf_final, y_true) + λ_cal · ECE(conf_final, y_true)
```

where `λ_cal = 0.5` balances sharpness (Brier) against calibration (ECE). Calibration diagram (reliability plot) produced per ProductType as a shipped artifact.

**Known caveat:** because 1A descriptions are internally curated, σ calibrated here is expected to be optimistic for production inputs. Mitigation:
- Secondary calibration pass using OCR'd text from 1A_Product_Document_Links.
- Post-launch recalibration after the first 500 reviewer corrections.

### 9.4 Evaluation (Test)

| Metric | Definition | Target |
|---|---|---|
| **Attribute top-1 accuracy** | Fraction of (product, attribute) pairs where predicted top-1 value = true value | ≥ 0.85 on head ProductTypes |
| **Attribute top-3 accuracy** | True value in predicted top-3 | ≥ 0.95 on head ProductTypes |
| **ProductType classification accuracy** | Predicted PT matches true PT | ≥ 0.92 |
| **Expected Calibration Error** | E_{conf}|accuracy(conf) − conf| | ≤ 0.05 |
| **Auto-process rate @ 0.85** | Fraction of test inputs with conf_final ≥ 0.85 | ≥ 0.50 |
| **Auto-process precision @ 0.85** | Accuracy among auto-processed predictions | ≥ 0.95 |
| **p50 / p95 latency** | End-to-end (encode + FAISS + scoring + fusion) | ≤ 50 ms / ≤ 200 ms |

### 9.5 Reporting

A standardized evaluation report, committed under `reports/v1/<timestamp>/`, includes:
- All metrics above, overall and per ProductType.
- Reliability diagram per head ProductType.
- Confusion matrix for top-10 attributes.
- Top-N failure cases (analyst-inspectable).
- Latency histogram.
- Confidence distribution histogram vs. baseline (drift signal).

---

## 10. Implementation Plan

| M | Deliverable | Effort | Dependencies |
|---|---|---:|---|
| M1 | Data loaders, stratified split, unit tests | 2 d | — |
| M2 | Layer 1 extractors (CSV done, PDF/OCR stub, email stub); Layer 2 rule engine with 2A guardrail | 3 d | M1 |
| M3a | Sentence-Transformer encoder integration; FAISS index over 1B; retrieval demo | 2 d | M1 |
| M3b | ProductType consensus; cluster centroid / covariance computation; persistence | 3 d | M3a |
| M3c | Per-attribute per-value scoring with Usage_Count prior | 2 d | M3b |
| M4 | Layer 4 fusion, thresholds, σ calibration loop | 2 d | M3c |
| M5 | Test-set evaluation report | 2 d | M4 |
| M6 | Incremental-update API (online centroid refresh) | 2 d | M5 |
| M7 | REST inference endpoint; telemetry (Prometheus metrics) | 3 d | M5 |

**Total effort:** ~21 working days.

**Testing strategy:**
- **Unit tests** for Layer 1 (extractors, normalization), Layer 2 (rule matches on synthetic inputs).
- **Property tests** for confidence invariants: e.g., `conf_final ∈ [0, 1]`, `conf_final = 1.0` iff part-number exact match.
- **Integration tests** end-to-end on a held-out 100-sample fixture.
- **Regression tests** after every retraining: confidence distribution KL-divergence vs. prior run must be < 0.2.

---

## 11. Platform Integration Points

These hooks align with the client's [Product Specification Document](eParts+Product+Specification+Document.doc), specifically CAP-ML-01 through CAP-ML-05 and CON-07. V1 does not implement a full MLOps platform but persists artifacts in shapes that admit straightforward migration to one.

| Spec requirement | V1 implementation |
|---|---|
| **CAP-ML-01** Cloud resources | Containerized (Docker); deployable on Azure Container Instances or Kubernetes. |
| **CAP-ML-02** Feature store (Delta Lake / Iceberg compatible) | Centroids, covariances, and reference vectors persisted as Parquet. Schema is Delta-compatible; migration path is append-only. |
| **CAP-ML-03** Model registry & versioning | Each training run produces immutable `artifacts/v1/run_<timestamp>/` with encoder version hash, FAISS index, centroids, σ table, evaluation report. |
| **CAP-ML-04** Telemetry & drift | Confidence-distribution histogram and ProductType consensus rate exposed as Prometheus-compatible metrics. Drift signal = KL divergence vs. baseline. |
| **CAP-ML-05** Data quality framework | Input validation hook: empty-vector inputs, failed ProductType consensus, and OOV-heavy inputs logged with reason codes. |
| **CON-07** Snowflake compatibility | Inference exposed as REST; result schema is SQL/VARIANT-queryable. FAISS remains file-based; Snowflake invokes us, not vice versa. |

---

## 12. Risks, Limitations & Open Issues

| Risk | Severity | Mitigation |
|---|---|---|
| σ calibrated on curated 1A text is optimistic for real customer input | High | Secondary calibration on OCR'd text; post-launch recalibration from first 500 reviewer corrections |
| No real correction cases (2B unusable) | High | Request 50–100 hand-picked cases from eParts ([Data_Feedback_for_eParts.md](Data_Feedback_for_eParts.md)); V2 contrastive-loss experiment |
| 141 attributes absent from 1A (29% of active attributes) | Medium | Fall back to rule engine only; request targeted re-export from eParts |
| Long-tail attributes with < 20 samples | Medium | Hard-cap `conf_final ≤ 0.7` for low-sample clusters; V2 LLM-assisted extraction for these |
| Product_Name 99.997% empty in 1B | Low | Use Short_Description as display proxy; request clarification from eParts |
| Encoder drift as new product categories are added | Medium | Periodic encoder revalidation; explicit version pinning in artifacts |
| OCR quality on scanned PDFs | Medium | `pytesseract` fallback; flagged as a V2 improvement target |
| Dependency on eParts's ProductTypeAttributes schema staying accurate | Low | Schema freshness check at startup |

---

## 13. V2 Backlog

Items deferred from V1, ordered by expected impact:

1. **Real correction-case integration.** Once eParts delivers hand-picked cases, use them as contrastive negatives in a margin loss to sharpen σ calibration at decision boundaries.
2. **Encoder domain adaptation.** Contrastive fine-tuning on 1A pairs to close the gap between the pre-trained encoder's generic knowledge and eParts's HVAC/industrial vocabulary. Expected to further improve synonym recall.
3. **LLM-assisted extraction for long-tail attributes.** For attributes with < 20 training samples, delegate to a few-shot LLM call with structured output. Evaluate head-to-head against V1 on the same held-out set.
4. **Cross-encoder re-ranker.** Re-rank FAISS's top-50 with a pairwise (query, candidate) cross-encoder. Expected modest accuracy lift at 5-10 ms additional latency.
5. **Active learning loop.** Prioritize reviewer attention on inputs near the 0.85 threshold — the highest-value feedback for tightening the decision boundary.
6. **End-to-end OCR pipeline.** Productionize PDF → text → pipeline for the spec-sheet ingestion path.
7. **Multi-tenant feature store.** Align with CAP-ML-02's Delta Lake / Iceberg direction when the platform side is ready.
8. **Automated retraining cadence.** CAP-ML-04 explicitly disallows automated retraining; V2 delivers a human-triggered retraining dashboard.

---

## 14. Appendices

### Appendix A — Key Formulas Reference

**Input encoding:**
```
q = SentenceTransformer("BAAI/bge-small-en-v1.5").encode(text)
q ∈ ℝ³⁸⁴, L2-normalized (so inner product = cosine similarity)
```

**Cluster statistics (per ProductType × Attribute × Value):**
```
μ_cluster = (1/N) Σᵢ q_i                              over confirmed-correct references
Σ_cluster = Ledoit-Wolf shrinkage on {q_i − μ_cluster}
```

**Mahalanobis-based confidence:**
```
D² = (q − μ_cluster)ᵀ · Σ_cluster⁻¹ · (q − μ_cluster)
conf_embed(A, v) = exp(−D² / (2σ_PT²))
```

**Usage-count prior:**
```
usage_prior(A, v) = 0.5 + 0.5 · log(1 + Usage_Count(A, v)) / log(1 + max_Usage_Count(A))
conf_embed_final(A, v) = conf_embed(A, v) · usage_prior(A, v)
```

**Fusion:**
```
conf_final(A) = α · conf_rule(A) + (1 − α) · conf_embed_final(A, v*), α = 0.7
where v* = argmaxᵥ conf_embed_final(A, v)
```

**ProductType ambiguity cap:**
```
if PT_conf < 0.60:
    conf_final(A) := min(conf_final(A), 0.75)   for all attributes A
```

**Online update on reviewer confirmation:**
```
μ_new = (N · μ_old + q) / (N + 1),    N := N + 1   (per cluster)
```

**Error pushback on confidently-wrong prediction:**
```
μ_corrected = μ_old − λ · (q_wrong − μ_old),   λ = 0.01   (per cluster)
```

### Appendix B — Data Inventory Summary

See [Data_Delivery_Assessment.md](Data_Delivery_Assessment.md) for full details.

| File | Rows | Purpose in V1 | Status |
|---|---:|---|---|
| 1A_Product_Attribute_Pairs | 1,938,426 | Training pairs for Layer 3 cluster statistics | ✅ Primary training source |
| 1A_Product_Document_Links | 516,005 | End-to-end OCR test material; secondary calibration source | 🎁 Bonus over-delivery |
| 1B_Product_Master | 198,147 | Reference catalog for FAISS index | ✅ Full catalog |
| 2A_Values_Per_Attribute | 9,918 | Rule engine guardrail + Usage_Count prior | ✅ Complete |
| 2B_Apparent_Correction_Cases | 746,845 | Error-aware calibration | ❌ Unusable; requesting replacement |

### Appendix C — Document Map

- Original client-facing requirements: [ML_Model_Proposal_and_Data_Requirements.md](ML_Model_Proposal_and_Data_Requirements.md)
- Data delivery quantitative assessment: [Data_Delivery_Assessment.md](Data_Delivery_Assessment.md)
- Client feedback draft: [Data_Feedback_for_eParts.md](Data_Feedback_for_eParts.md)
- V1 implementation design (internal): [V1_Architecture_Design.md](V1_Architecture_Design.md)
- Client Product Specification: [eParts+Product+Specification+Document.doc](eParts+Product+Specification+Document.doc)
- Project context for future Claude sessions: [../CLAUDE.md](../CLAUDE.md)

### Appendix D — Glossary

- **Attribute:** a named property of a product (e.g., `INPUT_VOLTAGE`, `MOUNTING`).
- **Category:** top-level product grouping (77 active).
- **Confidence score:** a number in [0, 1] representing the system's own assessment of prediction correctness. Calibrated so that predictions scored at `c` are correct ~`c` fraction of the time.
- **FAISS:** Facebook AI Similarity Search; a nearest-neighbor library.
- **Mahalanobis distance:** a distance measure that accounts for the shape of the data distribution (via covariance), not just Euclidean distance.
- **OCR:** Optical Character Recognition.
- **ProductType:** sub-category under a Category (755 active).
- **PAC bound:** "Probably Approximately Correct"; a theoretical lower bound on training data quantity for a target accuracy.
- **Sentence Transformer:** a neural model fine-tuned to embed whole sentences as vectors such that semantically similar sentences have similar vectors.
- **Shrinkage covariance (Ledoit-Wolf):** a covariance estimator that trades bias for lower variance, essential when the sample size is close to the dimension.
- **TF-IDF:** Term Frequency × Inverse Document Frequency; a classical word-importance weighting.

---

*Document prepared by MSE Studio Capstone Team — eParts Services Project*
*April 2026*
