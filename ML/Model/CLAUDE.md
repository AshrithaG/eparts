# eParts ML Confidence Scoring System

## Project Goal
Build a pipeline that reads customer product specification requests (emails/PDFs/CSVs) and maps them to the correct attributes in the eParts product database, attaching a **confidence score** to every output. High-confidence results auto-process; low-confidence results go to human review.

- Client-facing proposal: [eparts_doc/ML_Model_Proposal_and_Data_Requirements.md](eparts_doc/ML_Model_Proposal_and_Data_Requirements.md)
- **Consolidated Capstone design (authoritative overall):** [eparts_doc/Capstone_Technical_Design.md](eparts_doc/Capstone_Technical_Design.md)
- V1 implementation spec: [eparts_doc/V1_Architecture_Design.md](eparts_doc/V1_Architecture_Design.md)
- Data delivery review: [eparts_doc/Data_Delivery_Assessment.md](eparts_doc/Data_Delivery_Assessment.md)
- Draft feedback to client: [eparts_doc/Data_Feedback_for_eParts.md](eparts_doc/Data_Feedback_for_eParts.md)

## 4-Layer Pipeline Architecture (V1 — see V1_Architecture_Design.md for full detail)
1. **Text Extraction** (no ML) — parse CSV columns, PDF text + OCR, email body cleaning, unit normalization
2. **Rule Engine** — exact match on part numbers, numeric values + units, manufacturer names → `conf_rule`; 2A valid-value guardrail
3. **Semantic Matcher** (ML core, **upgraded from Proposal**):
   - Encoder: **Sentence-Transformer `bge-small-en-v1.5`** (384-d), replaces Proposal's TF-IDF + GloVe
   - Retrieval: **FAISS over 1B Products**, top-K=50
   - Hierarchical routing: **ProductType consensus** from top-K → restricts attribute search to ProductTypeAttributes(PT)
   - Scoring: **unchanged math** — Mahalanobis `D(q, μ)` per (ProductType, Attribute, Value) cluster, `conf_embed = exp(−D²/2σ²)`, Usage_Count prior weighting
4. **Decision & Feedback** — `conf_final = α × conf_rule + (1−α) × conf_embed`, α=0.7
   - ≥ 0.85 → auto-process
   - 0.50–0.85 → human review
   - < 0.50 → flag unclear
   - Ambiguous ProductType (consensus < 0.6) → cap `conf_final` at 0.75
   - Online update: `μ_new = (N × μ_old + v_new) / (N + 1)`; correction pushback λ=0.01 (per cluster)

## Data Inventory — `the_standard_data/`

| File | Rows | Purpose | Caveats |
|---|---|---|---|
| [1A_Product_Attribute_Pairs.csv](the_standard_data/1A_Product_Attribute_Pairs.csv) | 1,938,427 | Input→output pairs: Short/Full/Extended_Description → (Attribute_Name, Attribute_Value, Unit_Suffix, DigitalValue, RangeLow/High) | **Descriptions are internal team-written, NOT raw customer emails**. Good for training similarity model; insufficient for testing Layer 1 robustness. |
| [1A_Product_Document_Links.csv](the_standard_data/1A_Product_Document_Links.csv) | 516,006 | Product_ID → spec sheet / image URL (`ImageFile=1` image, `=0` PDF) | Bonus deliverable — can drive OCR pipeline + end-to-end test from real spec sheets |
| [1B_Product_Master.csv](the_standard_data/1B_Product_Master.csv) | 198,148 | Full catalog: Product_ID, Part_Number, Name, Descriptions, Manufacturer, ProductType, Category, Weight, Tariff | Reference library for similarity search |
| [2A_Values_Per_Attribute.csv](the_standard_data/2A_Values_Per_Attribute.csv) | 9,919 | All (Attribute_Name, Value, Unit_Suffix) combinations + Usage_Count | Enables constrained output + frequency-weighted priors |
| [2B_Apparent_Correction_Cases.csv](the_standard_data/2B_Apparent_Correction_Cases.csv) | 746,846 | Products with Edit_Count>1 as error proxy; has EO_Date, EO_Reason | **Proxy data** — no formal error-tracking. EO_Reason includes non-error ops like "changing vendor". Needs cleaning before use as negative examples. |

Schema details: [the_standard_data/Data Dictionary.pdf](the_standard_data/Data%20Dictionary.pdf)
Provider notes: [the_standard_data/readme.txt](the_standard_data/readme.txt)

### DB stats snapshot (from Data Dictionary)
- 198,465 active products / 77 categories / 755 product types / 487 attributes / 553 manufacturers
- 4,080,763 attribute value rows; avg 13.1 attributes/product
- Only 39,979 products have long descriptions; 397,261 have documents

## Client Clarifications (2026-04-23, resolved)
- **2B correction cases** — eParts confirmed no formal corrections are recorded. V1 trains on 1A only; model will be slightly over-confident, which is accepted. Real correction cases, once collected, will be applied as fine-tuning later (V2 backlog item).
- **141 missing attributes** — eParts confirmed these are genuinely absent from current records (not an export filter). V1 scope is the 348 attributes that do have rows in 1A; missing attributes are out of scope until data appears.

## Still Pending with eParts
- **P3-A** Customer submission templates — not delivered
- **P3-B** Request volume distribution by product category — not delivered
- **Real customer input samples** — 1A descriptions are internal curated text. For post-launch recalibration, need raw email/PDF samples.
- **1C Staging schema** — deferred by eParts until their PIMS side is ready.

## Working Directory Layout
```
i:/Eparts_model/
├── CLAUDE.md                (this file)
├── eparts_doc/              proposal, team docs, architecture diagrams
├── the_standard_data/       eParts-provided CSVs + Data Dictionary
├── data/                    (workspace for processed data)
└── pic/                     diagrams / images
```

## Conventions
- File size warning: `1A_Product_Attribute_Pairs.csv` is 1.4 GB — never `cat`/load fully into memory. Prefer chunked pandas reads or SQL.
- Keep raw `the_standard_data/` immutable; write derived artifacts to `data/`.
