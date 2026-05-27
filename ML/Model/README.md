# eParts ML — Confidence Scoring System (V1)

Capstone project: ML team's portion of the eParts Services platform. A
four-layer pipeline that maps customer product specification requests
(emails / PDFs / CSVs) to attributes in the eParts catalog and attaches
a calibrated confidence score to every output. High-confidence
predictions auto-process; lower-confidence ones route to human review.

| | |
|---|---|
| Status | V1 implementation complete through M5 (evaluation report shipped); M6 + M7 pending |
| Spec | [`eparts_doc/V1_Architecture_Design.md`](eparts_doc/V1_Architecture_Design.md) — authoritative |
| Test suite | 182 tests, all green (~12 s wall) |
| Owner | ML team — eParts Capstone (MSE Studio) |

---

## Architecture at a glance

```
Customer request → [L1 Extraction] → [L2 Rule Engine] → [L3 Semantic] → [L4 Decision]
                   ↑ Extraction sub-team       ↑─────── ML team's scope ────────↑
```

| Layer | Owner | Status | Implementation |
|---|---|---|---|
| **Layer 0 — Data foundation** | ML team | M1 ✓ | [`src/data/`](src/data/) — loaders + stratified splits |
| **Layer 1 — Text extraction** | Extraction sub-team | (their team) | Interface contract: [`eparts_doc/ExtractionHandoff_Spec.md`](eparts_doc/ExtractionHandoff_Spec.md); our deterministic prototype under [`archive/m2_layer1_extraction/`](archive/m2_layer1_extraction/) |
| **Layer 2 — Rule engine** | ML team | M2 ✓ | [`src/layer2_rules/`](src/layer2_rules/) — Tier 1/2/3 + 2A guardrail |
| **Layer 3 — Semantic matcher** | ML team | M3a/b/c ✓ | [`src/layer3_semantic/`](src/layer3_semantic/) — BGE encoder + FAISS + clusters + scoring |
| **Layer 4 — Decision & feedback** | ML team | M4 ✓ / M6 pending | [`src/layer4_decision/`](src/layer4_decision/) — fusion + caps + routing + σ calibration |
| Evaluation harness | ML team | M5 ✓ | [`src/evaluation/`](src/evaluation/) — end-to-end metrics, report bundle generator |
| REST service + telemetry | ML team | M7 pending | (planned) |

Full visual: [`eparts_doc/Architecture_Diagram.md`](eparts_doc/Architecture_Diagram.md).

---

## Quick start

**Setup (~1 GB of dependencies):**

```powershell
cd ML/Model
py -m pip install -r requirements.txt
py -m pip install -r requirements-dev.txt   # ruff / black / mypy / reportlab
winget install --id UB-Mannheim.TesseractOCR --silent      # only needed for the archived L1 OCR path
```

Full setup notes: [`SETUP.md`](SETUP.md) (covers the Python launcher quirk on Windows + system Tesseract).

**Raw data:** ~1.6 GB of eParts CSVs live under `the_standard_data/` after team-internal distribution. Files in that directory are git-ignored (client data, not redistributed via this repo). See `SETUP.md` §3.

**Reproduce the pipeline from a fresh clone:**

```powershell
py scripts/m1_build_splits.py            # ~5 s   — train/val/test parquet
py scripts/m3a_build_index.py            # ~1.5 h — BGE encode + FAISS index over 198K products
py scripts/m3b_build_clusters.py         # ~30 min — per (PT, attr, value) μ + Ledoit-Wolf Σ
py scripts/m4_calibrate_sigma.py         # ~2 min — per-PT σ grid search on val split
py scripts/m5_evaluate.py                # ~25 min — full evaluation on test split, writes reports/v1/run_<ts>/
```

Smoke commands:

```powershell
py -m pytest                              # 182 tests, ~12 s
py scripts/m2_rule_engine_demo.py         # ~5 s  — Layer 2 on synthetic inputs
py scripts/m3a_retrieval_demo.py          # ~10 s — FAISS retrieval on 4 queries
py scripts/m3c_semantic_demo.py           # ~25 s — encoder + FAISS + consensus + scoring
```

---

## What ships in this repo vs. what's reproduced locally

### In git
| Path | Contents |
|---|---|
| [`src/`](src/) | Library code (Layer 2 / 3 / 4 + evaluation harness + shared contracts + config loader + data loaders) |
| [`tests/`](tests/) | 182 pytest tests |
| [`scripts/`](scripts/) | One CLI per milestone (m1 / m2 / m3a / m3b / m3c / m4 / m5) |
| [`config/`](config/) | Five YAML files — every tunable parameter |
| [`eparts_doc/`](eparts_doc/) | Spec, architecture, investigation reports, handoff docs |
| [`archive/`](archive/) | Layer 1 deterministic prototype (kept for reference after scope transfer) |
| [`implementation_plan/`](implementation_plan/) | V1 Engineering Specification (.docx) |
| [`artifacts/v1/current/`](artifacts/v1/current/) | **Small reproducibility metadata only**: `RUN_ID`, `build_info.json`, `encoder_hash.txt`, `ids.npy` (1.5 MB), `sigma_table.parquet` (18 KB) |
| [`reports/v1/run_20260525_163610/`](reports/v1/run_20260525_163610/) | M5 evaluation bundle (SUMMARY.md + metrics.json + 5 CSVs + 9 PNGs) |

### Not in git — reproduced locally
| Path | Size | How to reproduce |
|---|---|---|
| `the_standard_data/*` | ~1.6 GB | Distributed via team shared drive (see SETUP.md) |
| `data/splits/*.parquet` | ~12 MB | `py scripts/m1_build_splits.py` |
| `artifacts/v1/current/faiss.bin` | 293 MB | `py scripts/m3a_build_index.py` |
| `artifacts/v1/current/cluster_cov.npz` | 2.7 GB | `py scripts/m3b_build_clusters.py` |
| `artifacts/v1/current/centroids.parquet` | 21 MB | Same as cluster_cov.npz |
| Build / evaluation logs | varies | Per-run, point-in-time |

The `sigma_table.parquet` we DO ship is enough to verify σ calibration matches across rebuilds — see [`eparts_doc/M4_Investigation.md`](eparts_doc/M4_Investigation.md) for the schema and the per-PT distribution.

---

## Documentation map

For the most direct path into any audience's question:

| Question | Doc |
|---|---|
| What does the system do? | [`eparts_doc/Architecture_Diagram.md`](eparts_doc/Architecture_Diagram.md) (Mermaid + prose) |
| What's the V1 contract with eParts? | [`eparts_doc/V1_Architecture_Design.md`](eparts_doc/V1_Architecture_Design.md) (authoritative) |
| Where are we in the plan? | [`eparts_doc/V1_Development_Plan.md`](eparts_doc/V1_Development_Plan.md) |
| How was M5 evaluated? | [`reports/v1/run_20260525_163610/SUMMARY.md`](reports/v1/run_20260525_163610/SUMMARY.md) |
| Why did the worst-performing PT do badly? | [`eparts_doc/PIV_RootCause_Investigation.md`](eparts_doc/PIV_RootCause_Investigation.md) |
| How does Layer 4 (M4) work in detail? | [`eparts_doc/M4_Investigation.md`](eparts_doc/M4_Investigation.md) |
| What does the extraction team need to deliver? | [`eparts_doc/ExtractionHandoff_Spec.md`](eparts_doc/ExtractionHandoff_Spec.md) |
| How does QA test this? | [`eparts_doc/QA_Practices_and_Test_Strategy.md`](eparts_doc/QA_Practices_and_Test_Strategy.md) |
| How does the system use client data? | [`eparts_doc/Data_Utilization_Report.md`](eparts_doc/Data_Utilization_Report.md) |

---

## Spec-frozen vs tunable (per §6.1 / §6.2)

**Frozen** (cannot change without client design review): four-layer architecture, Mahalanobis distance, Gaussian decay `exp(−D²/2σ²)`, α=0.7 fusion, decision thresholds 0.85 / 0.50, Tier-1 terminal `conf=1.0`, online μ update formula, λ=0.01 pushback, PAC bound 830, CPU-only deployability.

**Tunable** (this team's discretion): encoder choice, FAISS hyperparameters, ProductType consensus bands, σ grid, cluster min size, low-sample cap, Usage_Count prior coefficients, library choices.

Current deviations from the V1 spec are catalogued in
[`reports/v1/run_20260525_163610/SUMMARY.md`](reports/v1/run_20260525_163610/SUMMARY.md) §8.

---

## Status of M6 / M7

| Milestone | What it adds | State |
|---|---|---|
| M6 — Online μ updates | Reviewer feedback loop: `μ_new = (N·μ_old + q) / (N+1)` per cluster; error pushback λ=0.01 | Not started; config field exists (`config/thresholds.yaml:38`); no consumer code yet |
| M7 — REST + telemetry | `POST /predict` (FastAPI) + Prometheus metrics; end-to-end integration test with the extraction sub-team | Not started; dependencies already pinned in `requirements.txt` |

---

*ML team — eParts Capstone — MSE Studio, Carnegie Mellon.*
