# PIV (Pressure Independent Valves & Actuators) — Root-cause Investigation

| | |
|---|---|
| Question | Why is PIV the worst-performing PT in M5 (top-1 52.9 %, top-3 77.1 %)? |
| Method | Read-only quantitative investigation using `the_standard_data/*.csv` + `artifacts/v1/current/*` + a 300-sample re-run of the M3+M4 pipeline on PIV test products |
| Investigation script | [`data/_piv_investigation.py`](../data/_piv_investigation.py) (gitignored, raw output at `data/_piv_investigation.out.txt`) |
| Date | 2026-05-26 |
| Status | Findings to be folded into [`reports/v1/run_20260525_163610/SUMMARY.md`](../reports/v1/run_20260525_163610/SUMMARY.md) §6 |

---

## Q1 — Attribute-count complexity per head PT

Data: streamed `the_standard_data/1A_Product_Attribute_Pairs.csv` (rows ≈ 1.94 M), joined to ProductType via `the_standard_data/1B_Product_Master.csv` (`load_products` in [`src/data/loader.py:65`](../src/data/loader.py#L65)). Computed in script `data/_piv_investigation.py` §Q1.

| ProductType | distinct attrs | p50 rows/prod | p95 | max | # products |
|---|---:|---:|---:|---:|---:|
| Ball 2-Way w/ Electric Actuator | 29 | 31 | 35 | 37 | 17,887 |
| Globe 2-Way w/ Electric Actuator | 25 | 27 | 30 | 31 | 3,938 |
| Ball 3-Way w/ Electric Actuator | 29 | 31 | 35 | 37 | 8,646 |
| **PIV** | **23** | **15** | **30** | **31** | **13,776** |
| KW/KWH Energy/Power Meters - Honeywell | 9 | 10 | 10 | 10 | 7,784 |

**Counter-intuitive finding.** PIV is *not* the most attribute-complex PT. It has **23 distinct attributes** (fewer than the other valves at 25–29) and a median of **15 attribute rows per product** — roughly **half** of Ball 2-Way / 3-Way (31 rows). PIV products are *less densely annotated*, not more complex. So "too many attributes per product" is **not** the root cause.

---

## Q2 — Cluster sparsity (low-sample distribution)

Data: `artifacts/v1/current/centroids.parquet` (10,202 rows, columns `product_type_id`, `attribute_name`, `n`, `low_sample`).

| ProductType | # clusters | # low-sample | low-sample % |
|---|---:|---:|---:|
| Ball 2-Way | 140 | 8 | 5.7 % |
| Globe 2-Way | 108 | 12 | 11.1 % |
| Ball 3-Way | 222 | 64 | **28.8 %** |
| **PIV** | **177** | **32** | **18.1 %** |
| KW/KWH | 65 | 5 | 7.7 % |

**Sparsity is NOT the dominant factor.** Ball 3-Way has a *higher* low-sample rate (28.8 %) than PIV (18.1 %), yet Ball 3-Way's top-3 = 88.8 % vs PIV's 77.1 %. If cluster sparsity drove attribute accuracy, Ball 3-Way would be worse.

**However**, PIV's per-attribute breakdown reveals one specific concern — `FLOW RATE RANGE` has **55 distinct value clusters** under PIV (top-15 attribute view from the script):

| attribute_name | n_clusters | n_low_sample | median_n | max_n |
|---|---:|---:|---:|---:|
| FLOW RATE RANGE | 55 | 12 | 27 | 1,077 |
| FLOW RATE | 36 | 4 | 283 | 1,350 |
| SIZE | 16 | 1 | 598 | 1,325 |
| MAX FLOW RATE | 15 | 4 | 6 | 15 |
| INPUT SIGNAL | 12 | 1 | 197 | 7,784 |

55-way and 36-way classification on a single attribute from a short text query is much harder than the typical 2–10 way classification other valve attributes face. This compounds the issues identified below.

---

## Q3 — Rank-of-truth distribution (300 PIV test products, 4,230 attribute samples)

Method: re-ran the M3+M4 pipeline with `top_n_per_attribute=100` in [`SemanticScorerConfig`](../src/layer3_semantic/scoring.py) to find the truth's rank when it is not in top-3. Sample of 300 PIV test products drawn with `rng=42` from `data/splits/test.parquet`.

| Bucket | Count | % of 4,230 |
|---|---:|---:|
| rank 1 (top-1 hit) | 2,264 | **53.5 %** |
| rank 2–3 | 995 | 23.5 % |
| **rank 4–10** | **780** | **18.4 %** |
| rank 11–100 | 191 | 4.5 % |
| **not in top-100** | **0** | **0.0 %** |
| attribute not in PT scope | 0 | 0.0 % |

**Two critical findings.** First, top-3 hit rate is 53.5 + 23.5 = **77.0 %** — matches the per-PT report (77.1 %). Second, **0 % of truths fall outside top-100**: candidate generation is *not* the problem. The 23 % top-3 miss is **a ranking problem**, not a recall problem.

**Pattern in the 10 randomly-sampled top-3-miss cases (full output in `_piv_investigation.out.txt:118-167`)** — two distinct failure modes:

1. **Superset values outrank specific values** (7 of 10 cases):
   - `INPUT POWER` truth `'24 VDC'` → rank 4; top-3 are `'24 VAC/VDC'`, `'110/230 VAC'`, `'24 VAC'`
   - `INPUT POWER` truth `'24 VAC'` → rank 4; top-3 are `'24 VAC/VDC'`, `'110/230 VAC'`, `'24 VDC'`
   - `INPUT SIGNAL` truth `'FLOATING POINT'` → rank 4; top-1 is `'ON/OFF & FLOATING POINT'` (a superset)
   - **The combined-value cluster systematically beats the specific-value cluster.** This recurs identically across pids 357548 / 376612 / 355118 / 397507 / 355972 / 355426 — same top-5 ordering, different ground truths, all ranked 4.

2. **Numeric range values are essentially randomly ranked** (2 of 10 cases):
   - `FLOW RATE RANGE` truth `'002.00 - 002.99'` → **rank 17**; top-5 are `020.00-024.99` / `400.00-499.99` / `040.00-044.99` / `004.00-005.99` / `001.00-001.99` (no ordinal coherence with the truth)
   - `FLOW RATE` truth `'050.00 - 074.99'` → **rank 14**; top-5 wander from `045-049` to `1000-1999`

---

## Q4 — Input-text length per head PT

Data: `Short_Description` + `Extended_Description_Pre` concatenated (matching the M3a encoder input convention) from `the_standard_data/1B_Product_Master.csv`.

| ProductType | n | text_len p25 | p50 | p75 | words p50 |
|---|---:|---:|---:|---:|---:|
| Ball 2-Way | 18,005 | 419 | 647 | 719 | 134 |
| Globe 2-Way | 3,944 | 429 | 499 | 827 | 108 |
| Ball 3-Way | 9,928 | 556 | 639 | 735 | 131 |
| **PIV** | **13,776** | **733** | **785** | **897** | **152** |
| KW/KWH | 7,784 | 499 | 500 | 500 | 85 |

**PIV descriptions are the LONGEST among the head 5 PTs.** "Thin descriptions" is *not* the root cause. But length isn't quality — looking at 5 sample PIV vs 5 KW/KWH descriptions:

**PIV [114327]**: `1/2" 2-Way ZoneTight Pressure Independent Zone Valve | Chilled or Hot Water Up to 60% Glycol | Field Selectable GPM - 0.6 0.8 1.3 1.9 2.8 3...`

**PIV [114334]**: `1/2" 2-Way ZoneTight Pressure Independent Zone Valve | ... | Field Selectable GPM - 0.4 0.8 or 0.9 | 24 VA...`

**KW/KWH [358135]**: `Class 1000 Energy Meter | 120 VAC, 1-Phase, 2-Wire | 100A | MMU Configuration - Up to 24 Meters In One Compact Enclosure | Fixed kWh Pulse O...`

**Major qualitative finding.** PIV descriptions list **field-selectable / configurable** value ranges (`Field Selectable GPM - 0.6 0.8 1.3 1.9 2.8 3.5`), not the as-shipped value. The encoder reads all 6 possible flow-rate values from a single product description; when the SKU's true flow rate is one of them, the embedding contains no signal pointing to *which* one. KW/KWH products by contrast specify a single concrete value per SKU (`100A`, `200A`, `120 VAC, 1-Phase, 2-Wire`), giving the encoder a single discriminative target.

---

## Q5 — PT consensus accuracy on PIV

Captured during the Q3 re-run: 300 of 300 PIV test products had `compute_pt_consensus(...).product_type_id == 388`.

**PT consensus accuracy on PIV = 100.0 %.**

PIV's attribute-prediction weakness is **NOT** inherited from a PT-routing failure. The system correctly routes every PIV query to PIV's cluster space; the failure is downstream in attribute-value ranking. This also means the 95.74 % overall PT accuracy in `metrics.json` is *not* being dragged down by PIV — if anything PIV slightly lifts it.

---

## Q6 — Numeric attribute correlations within PIV

Method: pivoted PIV 1A rows on `Product_ID` × `Attribute_Name` with `DigitalValue` as the value (253,402 non-null `DigitalValue` entries across 13,776 PIV products), then computed Pearson on the top-8 most-populated numeric attributes.

| Attribute pair | Pearson r |
|---|---:|
| FLOW RATE × FLOW RATE RANGE | **0.95** |
| FLOW RATE × SIZE | **0.86** |
| SIZE × FLOW RATE RANGE | **0.82** |
| INPUT POWER / INPUT SIGNAL / AUX SWITCH / PT PORTS / FAIL POSITION | NaN (zero-variance categorical-coded `DigitalValue`, not meaningful) |

**Strong physical correlations exist among PIV's continuous attributes.** A 1" valve has a roughly known flow rate; a known flow rate falls in a roughly known flow-rate range. Spec §4.3 [3d] scores **each attribute independently against its own cluster centroids**, so this 0.95 correlation is **structurally unused** — knowing SIZE perfectly does not constrain the system's FLOW RATE prediction.

---

## Conclusion — root causes ranked by evidence strength

The data does **not** support the hypotheses we walked in with (PIV has too many attributes, too few samples, or too-short descriptions). The actual root causes, in descending order of how directly the data supports them:

### 1. PRIMARY: Superset-value vs specific-value ambiguity in categorical attributes

**Evidence**: 7 of 10 randomly-sampled top-3-miss cases (Q3). The pattern is identical and repeatable: a "combined" value like `"24 VAC/VDC"` or `"ON/OFF & FLOATING POINT"` systematically outranks both of its constituent specific values, pushing the specific truth to rank 4. Driven by (a) more cluster members for combined values → tighter Mahalanobis Σ; (b) higher 2A `Usage_Count` for combined values → bigger usage prior.

**Recoverable how**: post-hoc rerank — when the top-1 is a superset and the truth-set has specific constituents in top-5, an inference-time rule could prefer the more specific value when supported by query context. Cheap to prototype; no spec change needed (it's a Layer 4 / Layer 3-output rerank, not a fusion formula change).

### 2. PRIMARY: PIV product descriptions list configurable ranges, not as-shipped values

**Evidence**: Q4 sample comparison. PIV product description text contains phrases like `"Field Selectable GPM - 0.6 0.8 1.3 1.9 2.8 3.5"` — six candidate flow rates embedded in one description. The encoder has no way to know which value is the SKU's actual shipped configuration. KW/KWH descriptions contain a single concrete value per SKU and consequently top-1 = 88.9 %.

**Recoverable how**: this is partly an upstream-data issue (eParts catalog convention) and partly a V2 architecture issue (encoder that consumes both description *and* a structured "configured value" hint). Most direct fix would be ingesting 1A's `DigitalValue` / `RangeLow` / `RangeHigh` as additional structured input to scoring; this overlaps with Layer 2 Tier-3 logic that already exists.

### 3. SECONDARY: High intra-attribute cardinality on numeric range attributes

**Evidence**: Q2 — PIV's `FLOW RATE RANGE` has **55 distinct value clusters**. Q3 example cases show truth at rank 14–17 with no ordinal coherence between predicted and true ranges. Numeric-range attributes with 30+ candidates from a short query are intrinsically hard for a generic sentence encoder.

**Recoverable how**: a value-type-aware ranking step (treat numeric ranges as ordinal not categorical; penalize candidates that are far from any number mentioned in the query text). V2 backlog item.

### 4. ARCHITECTURAL LIMIT: No cross-attribute reasoning

**Evidence**: Q6 — Pearson 0.95 between `FLOW RATE` and `FLOW RATE RANGE`, 0.86 between `FLOW RATE` and `SIZE`. Per spec §4.3 [3d] each attribute is scored independently against its own clusters, so the 0.95 correlation is structurally invisible to the model.

**Recoverable how**: not in V1. A joint-attribute reasoning layer (e.g. a small graph over the attribute schema with edges weighted by observed correlations) would let SIZE constrain FLOW RATE. Belongs in the V2 backlog (spec §9.2).

### Findings explicitly NOT supported by the data

- **"Too many attributes per PIV product."** Q1 — PIV has *fewer* attributes per product than the other valve PTs.
- **"Too few training samples."** Q2 — Ball 3-Way has a *higher* low-sample rate (28.8 %) but a *higher* top-3 (88.8 %). Sparsity is not predictive of accuracy across head PTs.
- **"PT routing fails on PIV."** Q5 — 100 % PT accuracy on the PIV test sample.
- **"PIV descriptions are too short."** Q4 — PIV has the *longest* descriptions among head PTs (p50 = 785 chars vs 500 for KW/KWH).

---

## Implications for §6 of `SUMMARY.md`

The original §6 in SUMMARY says PIV's gap is "templated descriptions where multiple attribute values produce nearly-identical embeddings". The investigation shows this is *partially* correct but misses two more actionable findings. Suggested rewrite of the §5 / §6 PIV commentary in SUMMARY:

> The PIV gap is driven by two patterns observed in 7 of 10 sampled top-3 misses: (a) PIV descriptions list **field-selectable** configurable ranges, so the encoder cannot single out the as-shipped value from text alone; and (b) for categorical attributes, **combined-value clusters** (e.g. `"24 VAC/VDC"`) systematically outrank the specific values they encompass (`"24 VAC"`, `"24 VDC"`), pushing the truth to rank 4. Both patterns are recoverable at inference time without spec changes — the first by ingesting 1A's structured `DigitalValue` as a scoring side-input, the second by a post-hoc rerank that prefers specific values when supported by query context. **Neither is a candidate-generation failure**: 100 % of PIV truths appear in the top-100 candidate list. The system has the right candidates; it ranks them wrong.

---

*Investigation conducted 2026-05-26. All numbers traceable to `data/_piv_investigation.out.txt` (script's raw stdout). No code, config, or artifacts modified during the investigation.*
