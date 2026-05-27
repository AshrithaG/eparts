# eParts Services — ML Confidence Scoring System
## V1 Architecture Design Spec

**Prepared by:** MSE Studio Team
**Date:** April 2026
**Version:** V1.0
**Supersedes (for Layer 3):** [ML_Model_Proposal_and_Data_Requirements.md](ML_Model_Proposal_and_Data_Requirements.md) §4.1 and §4.3
**Status:** Implementation baseline — agreed internally, pending client review

---

## 0. Why a Separate Document

The original [ML Model Proposal](ML_Model_Proposal_and_Data_Requirements.md) remains the authoritative **requirements and data-needs document** for the client. It describes the mathematical framework (confidence scoring via Mahalanobis distance, k-NN averaging, online centroid updates, α-weighted fusion) that we commit to.

This V1 Design Spec is the **implementation-level design**. It preserves the Proposal's four-layer structure and all decision-level mathematics, but makes two specific upgrades inside Layer 3 that reflect state-of-the-art practice in 2026 (vs. the 2014-era TF-IDF + GloVe approach originally sketched):

1. **Sentence-Transformer embeddings** replace TF-IDF-weighted word-vector averaging.
2. **Hierarchical ProductType-aware retrieval** replaces a single flat reference pool.

All downstream math — Mahalanobis distance, confidence decay, α fusion, online updates, thresholds — is **unchanged**.

---

## 1. Change Summary (Diff vs. Proposal)

| Component | Proposal V0 | V1 Design | Rationale |
|---|---|---|---|
| L1 Text Extraction | CSV/PDF/Email + unit normalization | **Unchanged** | Already well-specified |
| L2 Rule Engine | Exact match on part #, manufacturer, value+unit | **Unchanged** | Correct for this use case; LLM cannot replace exact matching |
| **L3.a Text → Vector** | TF-IDF × GloVe word vectors, averaged | **Sentence-Transformer `bge-small-en-v1.5` (384-d)** | Handles synonyms, word order, OOV terms; zero extra training cost |
| **L3.b Retrieval Structure** | Single global reference pool; one centroid μ, one covariance Σ | **Two-stage hierarchical retrieval**: (1) FAISS nearest-Product top-K; (2) aggregate attribute votes weighted by product similarity | Exploits ProductTypeAttributes schema; prevents cross-category leakage (e.g. predicting `ACTION=SPRING RETURN` on a thermistor) |
| L3.c Confidence Math | Mahalanobis `D(q)`, Gaussian decay `exp(−D²/2σ²)`, k-NN average | **Unchanged** — computed per (Attribute, Value) cluster instead of globally | Same math, applied at finer granularity |
| L4 Fusion & Thresholds | `conf_final = α·conf_rule + (1−α)·conf_embed`, α=0.7 | **Unchanged** | Well-justified baseline |
| L4 Feedback Loop | Online centroid update `μ_new = (Nμ_old + v_new)/(N+1)`; error pushback `λ=0.01` | **Unchanged** — applied per cluster | Same formulas, per-cluster scope |
| PAC Sample Bound | `m ≥ (1/ε²)·ln(|H|/δ)` ≈ 830 | **Unchanged** | Theoretical floor still holds |

**Net effect:** Layer 3 is re-engineered; all other layers and all confidence math are preserved.

---

## 2. Updated Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  INPUT SOURCES                                                 │
│  Email body  │  PDF extracted text  │  CSV rows                │
└─────────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────┐
│  LAYER 1 — Text Extraction & Normalization  (unchanged)        │
│  • CSV → parse columns   • PDF → text + OCR (1A-Links driven)  │
│  • Email → strip sig/hdr • Units normalized (kΩ → kohm, etc.)  │
└─────────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────┐
│  LAYER 2 — Rule Engine   (unchanged)                           │
│  • Part-number exact match (→ conf_rule = 1.0, done)           │
│  • Manufacturer-name match                                     │
│  • Numeric value + unit match against 2A valid values          │
│  Output: partial attribute mappings + per-attribute conf_rule  │
└─────────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────┐
│  LAYER 3 — Semantic Matcher   (UPGRADED)                       │
│                                                                │
│  [3a] Encode input:                                            │
│       q = SentenceTransformer("bge-small-en-v1.5")(text)       │
│                                                                │
│  [3b] Product retrieval (FAISS over 1B descriptions):          │
│       top-K products = FAISS.search(q, K=50)                   │
│       each returned with sim(q, product_i)                     │
│                                                                │
│  [3c] ProductType consensus:                                   │
│       PT_predicted = weighted_majority_vote(top-K, weights=sim)│
│       If consensus is weak → flag ambiguous, lower max conf    │
│                                                                │
│  [3d] Per-attribute, per-value confidence:                     │
│       For each attribute A in ProductTypeAttributes(PT):       │
│         For each candidate value v seen in 1A under (PT, A):   │
│           cluster = top-K products that map (A → v)            │
│           μ_cluster = mean of their vectors                    │
│           D(q, μ_cluster) via Mahalanobis                      │
│           conf_embed(A, v) = exp(−D² / 2σ²)                    │
│         Return top-3 values per attribute with conf_embed      │
└─────────────────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────┐
│  LAYER 4 — Decision & Feedback   (unchanged)                   │
│  • conf_final = α·conf_rule + (1−α)·conf_embed,   α=0.7        │
│  • ≥ 0.85 → auto-process                                       │
│  • 0.50–0.85 → human review queue                              │
│  • < 0.50 → flag unclear, return to sender                     │
│  • Reviewer feedback → online centroid update (per cluster)    │
└────────────────────────────────────────────────────────────────┘
```

---

## 3. Layer-by-Layer Detail

### 3.1 Layer 1 — Text Extraction
**No change from Proposal §3.** Implementation notes:
- CSV parsing via pandas (chunked for 1A's 1.4 GB file)
- PDF parsing via `pdfplumber` with `pytesseract` OCR fallback for scanned pages
- Unit normalization map maintained in `/config/unit_aliases.yaml` (extensible)
- 1A_Product_Document_Links drives end-to-end OCR smoke tests

### 3.2 Layer 2 — Rule Engine
**No change from Proposal §3.** Implementation notes:
- Part number regex patterns generated from 1B `Product_Number` column (198K patterns, compiled once)
- Manufacturer name fuzzy match (`rapidfuzz`, ≥ 90 token-set-ratio) against 220 distinct manufacturers
- Numeric + unit match uses 1A's `DigitalValue` / `RangeLow` / `RangeHigh` / `Unit_Suffix` columns directly — no re-parsing from free text
- Valid-value guardrail: any rule-produced attribute value must appear in 2A_Values_Per_Attribute (else demoted to Layer 3)
- Output: `{attribute_id: (predicted_value, conf_rule)}` where `conf_rule ∈ {1.0 exact, 0.85 fuzzy, 0.65 partial, 0 no-match}`

### 3.3 Layer 3 — Semantic Matcher (upgraded)

#### 3.3.1 Text encoder

**Old (Proposal §4.1):**
```
v(sentence) = Σ [ tfidf(w_i) × embed(w_i) ] / Σ tfidf(w_i)
```

**New:**
```
q = SentenceTransformer("BAAI/bge-small-en-v1.5").encode(text)
q ∈ ℝ³⁸⁴, L2-normalized
```

**Model choice:**
- `bge-small-en-v1.5`: 384-d, 33 MB, CPU-capable (~5 ms/sentence)
- Alternatives evaluated if needed: `all-MiniLM-L6-v2` (faster, slightly weaker), `bge-base-en-v1.5` (better quality, 3× slower)
- No fine-tuning in V1. V2 backlog item: domain adaptation on 1A pairs.

**Why this is strictly better than TF-IDF + GloVe:**
| Failure mode | TF-IDF+GloVe | Sentence-Transformer |
|---|---|---|
| `"thermistor"` vs `"temperature sensor"` | Treated as unrelated | Recognized as similar |
| Word order (`"24V input 0-10V output"`) | Lost | Preserved |
| Rare technical tokens (`"10K-3"`) | OOV → zero vector | Subword tokenization handles |
| Multi-word phrases | Averaged away | Encoded contextually |

#### 3.3.2 Product retrieval (FAISS)

Build a FAISS IVF-Flat index over all 198,147 products from 1B, keyed by Product_ID, indexed by the encoder applied to Short_Description (primary) concatenated with Extended_Description_Pre when available.

```
Index: FAISS IVFFlat, nlist = 512, metric = Inner Product (on L2-normalized vectors = cosine)
Memory: 198K × 384 × 4 B ≈ 300 MB
Query latency: ~5 ms on CPU for top-K=50
```

On query:
1. Encode input `q`
2. `product_candidates = index.search(q, K=50)` → list of (Product_ID, similarity)
3. Pass candidates to ProductType consensus step

#### 3.3.3 ProductType consensus

```
For each product_i in candidates, weight = sim(q, product_i)
vote[PT] = Σ weight over products with ProductType = PT
PT_predicted = argmax_PT vote[PT]
PT_confidence = vote[PT_predicted] / Σ vote[PT]
```

If `PT_confidence < 0.6` → flag input as ambiguous; cap final confidence at 0.75 regardless of attribute-level scores. This is our structural handling of the "T-6000 prefix overlaps thermostat and temperature sensor" case described in the Proposal §5.

#### 3.3.4 Per-attribute, per-value confidence

For each attribute `A` listed in `ProductTypeAttributes(PT_predicted)`:
1. Query 1A: pull all (Product_ID, attribute value `v`) rows where Attribute = A and the Product_ID is in our top-K candidates.
2. Group by value `v`. For each cluster:
   - `μ_cluster = mean of encoder(descriptions) for products in this cluster`
   - `Σ_cluster = shrinkage-estimated covariance of the same`
   - `D(q, μ_cluster) = √[(q − μ_cluster)ᵀ Σ_cluster⁻¹ (q − μ_cluster)]`
   - `conf_embed(A, v) = exp(−D² / 2σ²)` (Proposal §4.3)
3. Prior-weight by `Usage_Count` from 2A (rare values get a mild prior penalty):
   - `conf_embed_adjusted(A, v) = conf_embed(A, v) × (0.5 + 0.5 · log(1 + Usage_Count) / log(1 + max_count))`
4. Return top-3 values per attribute with their adjusted confidence.

σ is calibrated per ProductType on a held-out validation slice (below).

### 3.4 Layer 4 — Decision & Feedback

**Unchanged from Proposal §4.5 and §4.6.** The fusion formula, thresholds, online-update formula, and error-pushback rule all apply as specified, scoped per (ProductType, Attribute, Value) cluster rather than globally.

One addition: when PT_confidence < 0.6 (ambiguous ProductType), final confidence is capped at 0.75 — routes borderline cases to human review instead of letting strong attribute-level signals mask ProductType uncertainty.

---

## 4. Training & Calibration Protocol

### 4.1 Data split
- Source: 1A_Product_Attribute_Pairs.csv (1.94 M rows, 134,117 products, 348 attributes)
- Stratified by ProductType: 80% train / 10% val / 10% test
- Random seed fixed; splits persisted to `data/splits/`

### 4.2 Reference index build (train step)
- Encode descriptions of all train-split products → FAISS index
- For each (ProductType, Attribute, Value) cluster with ≥ 5 members: compute `μ` and shrinkage `Σ`
- Clusters with < 5 members: flagged low-sample; confidence capped at 0.7 regardless of query
- Persist: FAISS index + cluster-centroids dict + σ-per-ProductType table

### 4.3 σ calibration (val step)
For each ProductType, grid-search σ ∈ [0.1, 0.5, 1.0, 2.0, 5.0] to maximize:
```
val_loss(σ) = BrierScore(conf_final, y_true) + λ · ECE(conf_final)
```
— i.e. minimize both miscalibration and sharpness loss. Calibration curve (expected vs. actual accuracy across confidence bins) shipped as part of the evaluation report.

### 4.4 Evaluation metrics (test step)
- **Attribute-level accuracy** (top-1, top-3) per ProductType
- **ProductType classification accuracy**
- **Calibration**: Expected Calibration Error (ECE), reliability diagram
- **Operating-point metrics** at threshold 0.85:
  - Auto-process rate (fraction routed to auto)
  - Auto-process precision (accuracy among auto-processed)
  - Human-review rate (fraction to queue)
- **Latency**: p50 / p95 per query, end-to-end

### 4.5 Known calibration caveat
Because 1A descriptions are internally curated (not raw customer text), σ tuned on this distribution will be **optimistic** for production inputs. Mitigation:
1. Secondary calibration pass on OCR'd text from 1A_Product_Document_Links (noisier, closer to real input).
2. Post-launch, use the first 500 human-reviewed cases to re-fit σ.
3. Flagged in §7 for client communication.

---

## 5. Platform Integration Points

These are the hooks required by the client's [Product Specification Document](eParts+Product+Specification+Document.doc) — specifically CAP-ML-01 through CAP-ML-05. V1 does **not** implement the full MLOps platform, but persists artifacts in shapes that can be migrated there later.

| Spec requirement | V1 implementation |
|---|---|
| **CAP-ML-02** Feature Store (Delta Lake / Iceberg) | Reference vectors, cluster centroids, covariance matrices persisted as Parquet in `artifacts/v1/`. Schema is Delta-compatible; migration path is append-only. |
| **CAP-ML-03** Model Registry & Versioning | Each run produces `artifacts/v1/run_<timestamp>/` containing: encoder version hash, FAISS index, centroids, σ-table, evaluation report. Immutable. |
| **CAP-ML-04** Telemetry & Drift | Confidence-distribution histogram and ProductType consensus rate exposed as Prometheus-compatible metrics. Drift signal = KL-divergence between current vs. baseline confidence distributions. |
| **CAP-ML-05** Data Quality Framework | Input validation hook: any input producing empty q-vector, or failing ProductType consensus, is logged with reason code. |
| **CON-07** Snowflake compatibility | Inference exposed as a REST endpoint; result schema is SQL-queryable (JSON → VARIANT). FAISS index stays file-based; Snowflake calls us, not vice versa. |

---

## 6. Implementation Milestones

| M | Deliverable | Est. effort | Blocker |
|---|---|---:|---|
| **M1** | Data loaders + stratified split; unit tests | 2 d | — |
| **M2** | Layer 1 extractors (CSV done; PDF/OCR stub); Layer 2 rule engine + 2A valid-value guardrail | 3 d | — |
| **M3a** | Sentence-Transformer encoder + FAISS index over 1B; end-to-end retrieval demo | 2 d | — |
| **M3b** | ProductType consensus + cluster centroid/covariance persistence | 3 d | — |
| **M3c** | Per-attribute, per-value confidence with Usage_Count prior | 2 d | — |
| **M4** | Layer 4 fusion, thresholds, σ calibration loop | 2 d | — |
| **M5** | Test-set evaluation report: accuracy / calibration / latency | 2 d | — |
| **M6** | Incremental-update API (online centroid refresh) | 2 d | — |
| **M7** | REST inference endpoint + telemetry metrics | 3 d | — |

**Total V1 estimate:** ~21 working days.

---

## 7. Known Limitations → V2 Backlog

| Issue | V1 mitigation | V2 plan |
|---|---|---|
| Training text is internally curated, not raw customer input | σ calibration knowingly optimistic; secondary pass on OCR text | Request and integrate 30–50 real anonymized customer inputs (see [Data_Feedback_for_eParts.md](Data_Feedback_for_eParts.md)) |
| No real correction/error examples (2B unusable) | None — confidence only learns from positive distribution | Request 50–100 hand-picked correction cases; use as contrastive negatives for margin loss |
| 141 active attributes with zero samples in 1A | Fall back to rule engine only on those attributes | Request targeted data pull or confirm they're unused |
| Long-tail attributes (< 20 samples) | Hard cap `conf_final ≤ 0.7` | Explicit low-sample branch using LLM-based few-shot extraction for these attributes only |
| Rule engine regex is hand-written | Manual maintenance | Auto-discover patterns from Product_Number column statistics |
| No automated retraining (CAP-ML-04 mandates manual) | Manual retrain cadence weekly | Dashboard surfaces retrain-trigger signals; still manual approval |

V2-experimental (not committed):
- Cross-encoder re-ranker on top-K=50 candidates
- Domain fine-tuning of encoder on 1A pairs (contrastive loss)
- LLM-assisted extraction for long-tail and cold-start scenarios (evaluated head-to-head vs. V1)

---

## 8. References

- Original Proposal: [ML_Model_Proposal_and_Data_Requirements.md](ML_Model_Proposal_and_Data_Requirements.md)
- Client Spec: [eParts+Product+Specification+Document.doc](eParts+Product+Specification+Document.doc)
- Data Delivery Assessment: [Data_Delivery_Assessment.md](Data_Delivery_Assessment.md)
- Data Feedback to Client: [Data_Feedback_for_eParts.md](Data_Feedback_for_eParts.md)
- Project context: [../CLAUDE.md](../CLAUDE.md)

---

*V1 Design approved by MSE Studio team — 2026-04-16*
*Client review pending.*
