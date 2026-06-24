# QA Practices & Test Strategy

| Field | Value |
|---|---|
| **Status** | Draft v0.2 — ML team's current testing posture; for QA-coach review |
| **Last updated** | 2026-06-17 |
| **Audience** | QA / Test Engineering, ML team |
| **Purpose** | Document what we currently test, how we run it, where the gaps are, and what specific help we want from QA |

This document is a frank inventory — not a marketing piece. We want
the QA team to read it once, identify the soft spots, and tell us
what to improve. Sections §8–§10 are the asks; everything before is
context. For a verbal-conversation brief, see the one-pager
[`QA_Coach_Talking_Points.md`](QA_Coach_Talking_Points.md).

> **What kind of "LLM system" is this?** The only LLM component the ML
> team owns is a **frozen sentence-embedding model** (`bge-small-en-v1.5`)
> used to turn product descriptions into 384-d vectors — it does not
> *generate* text. Everything downstream is classical statistics
> (Mahalanobis distance, Gaussian confidence decay, fixed thresholds).
> So our QA is **not** generative-LLM QA (no hallucination / prompt-
> injection / sampling-nondeterminism concerns); it is the QA of a
> **deterministic retrieval + scoring pipeline**, which is far more
> testable. Generative LLMs live in the extraction sub-team's Layer 1,
> out of our scope.

---

## 1. Scope of testing in V1

The ML team owns code under [`ML/Model/`](..). V1 is now code-complete
(M1–M7). The active test surface today (2026-06-17):

| Metric | Value |
|---|---|
| Test framework | pytest 8.0+ |
| Test files | **18** (under `tests/`) |
| Test functions | **219** |
| Pass rate | 100% (219/219 green) |
| Wall time, full suite | **~12 s** on stock laptop (encoder cached) |
| Encoder model load | one-time ~60 s on first run; cached afterward |
| Layers tested | Layer 0 (data) · Layer 2 (rules) · Layer 3 [3a/b/c/d] · Layer 4 (fusion + σ calibration + **M6 online updates**) · Evaluation harness (M5) · **Service (M7)** |
| Layers not yet tested | none in V1 scope — all milestones M1–M7 have test coverage |

**Per-file test counts (current):**

| File | Tests | File | Tests |
|---|---:|---|---:|
| test_split.py | 10 | test_layer3_scoring.py | 23 |
| test_part_numbers.py | 10 | test_layer4_fusion.py | 18 |
| test_manufacturers.py | 6 | test_layer4_calibration.py | 16 |
| test_numeric_match.py | 9 | test_layer4_feedback.py | 21 |
| test_guardrail.py | 10 | test_evaluation_metrics.py | 16 |
| test_engine.py | 11 | test_evaluation_report.py | 10 |
| test_layer3_encoder.py | 6 | test_evaluation_runner.py | 4 |
| test_layer3_index.py | 8 | test_service.py | 16 |
| test_layer3_consensus.py | 12 | test_layer3_clusters.py | 13 |
| | | **TOTAL** | **219** |

The archived deterministic Layer 1 prototype has 33 additional tests
under [`archive/m2_layer1_extraction/tests/`](../archive/m2_layer1_extraction/tests/);
they were green when archived but are not part of the active suite
(Layer 1 is owned by the extraction sub-team — see
[`ExtractionHandoff_Spec.md`](ExtractionHandoff_Spec.md)).

---

## 2. Test categories — what each kind asserts

We classify tests by what they prove, not by where they live. A
single `test_*.py` file often contains tests from multiple categories.

### 2.1 Unit tests — most of the suite (~75%)

**Goal.** Exercise one function or method with deterministic inputs
and verify a narrow correctness claim.

**Examples** (with file:line refs):

| Where | What it asserts |
|---|---|
| [`test_split.py:36-48`](../tests/test_split.py#L36-L48) | `stratified_product_split(seed=42)` is bit-exact reproducible on the same input |
| [`test_part_numbers.py:25-32`](../tests/test_part_numbers.py#L25-L32) | `PartNumberIndex.find()` returns a match in free text and respects alnum word boundaries |
| [`test_guardrail.py:78-90`](../tests/test_guardrail.py#L78-L90) | An invalid `(Attribute, Value)` pair is *demoted* (conf rewritten to 0) but not removed from the result |
| [`test_layer3_index.py:51-60`](../tests/test_layer3_index.py#L51-L60) | Querying a FAISS index with one of its own vectors returns that vector as top-1 at score ≈ 1.0 |

**Conventions:**
- One assertion concept per test. We prefer 6 small tests over 1 big test.
- Test name is a sentence: `test_<thing>_<expected_behavior>`.
- Fixtures (synthetic data) live inside the test file unless reused across files.
- `pytest.fixture` count: 14 across the suite (10 function-scoped, 3 session-scoped, 1 module-scoped).

### 2.2 Property tests — invariants that must hold for *any* input

**Goal.** Assert a mathematical or contractual property that should
hold regardless of input shape.

**Examples** (live, not aspirational):

| Where | Invariant |
|---|---|
| [`test_layer3_encoder.py:34-39`](../tests/test_layer3_encoder.py#L34-L39) | Every encoded vector has L2 norm = 1.0 (atol=1e-5) |
| [`test_layer3_clusters.py:111-127`](../tests/test_layer3_clusters.py#L111-L127) | Every full-cluster Σ⁻¹ is positive-definite (all eigenvalues > 0) |
| [`test_split.py:51-55`](../tests/test_split.py#L51-L55) | No `Product_ID` appears in more than one of train / val / test |
| [`test_layer3_consensus.py:42-50`](../tests/test_layer3_consensus.py#L42-L50) | When all top-K hits share one PT, `pt_conf = 1.0` exactly |

**Note:** We do not yet use a property-based testing framework
(Hypothesis). Tests above hand-pick the invariant inputs. **This is an
explicit gap — see §10 ask #2.**

### 2.3 Integration tests — multi-module pipeline slices

**Goal.** Exercise the boundary between two or more modules using a
realistic input that touches both.

**Examples:**

| Where | What it integrates |
|---|---|
| [`test_engine.py:60-77`](../tests/test_engine.py#L60-L77) | Layer 2 Tier 1 part-number terminal short-circuit: a CSV-shaped input with `part_number` populated → `terminated=True`, downstream tiers skip |
| [`test_engine.py:184-202`](../tests/test_engine.py#L184-L202) | Layer 2 guardrail demotion: Tier 3 hit for `(INPUT_VOLTAGE, 24)` not in 2A → `demoted_by_2a=True`, `conf_rule=0.0` |
| [`test_layer3_index.py:70-85`](../tests/test_layer3_index.py#L70-L85) | FAISS build → save → reload → query: bit-equivalent results before and after disk persistence |
| [`test_layer3_clusters.py:235-261`](../tests/test_layer3_clusters.py#L235-L261) | Cluster build → save (parquet + npz) → reload → spot-check μ and Σ⁻¹ recoverable |

### 2.4 Sanity-check / acceptance scripts — spec-conformance smoke

**Goal.** Verify the system meets a specific spec acceptance criterion
on real data. These are not pytest tests; they are CLI scripts whose
exit code reflects pass/fail.

| Script | Spec acceptance verified |
|---|---|
| [`scripts/m1_build_splits.py`](../scripts/m1_build_splits.py) | M1 — stratified 80/10/10 split persists; every ProductType present in train, val, test |
| [`scripts/m2_rule_engine_demo.py`](../scripts/m2_rule_engine_demo.py) | M2 — Layer 2 emits the expected hits + confidences for 4 synthetic `ExtractedInput` payloads |
| [`scripts/m3a_build_index.py`](../scripts/m3a_build_index.py) | M3a — index built from 1B; `ntotal == 197,928` (was: 198,147 with empties; we filter 219 blanks) |
| [`scripts/m3a_retrieval_demo.py`](../scripts/m3a_retrieval_demo.py) | M3a — sample queries return semantically sensible top-K |
| [`scripts/m3b_pt_accuracy_eval.py`](../scripts/m3b_pt_accuracy_eval.py) | M3b — ProductType prediction accuracy ≥ 0.95 on 2000 train-sample queries |
| [`scripts/m3b_build_clusters.py`](../scripts/m3b_build_clusters.py) | M3b — clusters built, PSD check passes, persist to parquet + npz |

These scripts produce a `Build summary:` block (key/value list) at the
end. Capturing that block in our reports/manuals is the audit trail.

### 2.5 Performance tests — latency / memory budget gates

**Goal.** Fail loudly if a change regresses performance below spec
budget.

**Currently present:**

| Where | Gate |
|---|---|
| [`test_part_numbers.py:67-83`](../tests/test_part_numbers.py#L67-L83) | Compile a 200K-pattern regex union in < 10 s on synthetic data (spec target 5 s; relaxed for CI) |
| [`test_part_numbers.py:86-99`](../tests/test_part_numbers.py#L86-L99) | After warmup, 1000 queries against a 50K-pattern index average < 1 ms each |

**Measured since v0.1 (benchmarked, not yet a CI gate):**

| Item | Result | Spec | How measured |
|---|---|---|---|
| End-to-end single-query latency | p50 47.6 ms / p95 188.9 ms | ≤ 50 / ≤ 200 ms | warm benchmark, 300 real queries (M7) |
| Live `/predict` warm latency | 18–28 ms | — | running M7 service on real artifacts |

**Still not present:**

| Need | Note |
|---|---|
| Concurrent load test (≥ 50 req/s sustained at p95 ≤ 200 ms) | spec §7.2 M7 — only single-thread warm measured so far; the encoder tail (p99 ≈ 253 ms) is the risk under concurrency |
| FAISS index memory ≤ 500 MB as an asserted gate | the 2.7 GB covariance artifact already exceeds the spec's 500 MB assumption — known, documented |
| Any of the above wired as an automatic CI gate | blocked on having CI at all (§8/§10) |

---

## 3. How to run tests

### 3.1 Full suite

```powershell
cd ML/Model
py -m pytest                            # ~12 s after model is cached
```

Expected: `94 passed in <time> s`.

### 3.2 Single test file or test

```powershell
py -m pytest tests/test_layer3_index.py            # one file
py -m pytest tests/test_layer3_index.py -v          # verbose, per-test names
py -m pytest -k "persistence_roundtrip"             # name substring filter
py -m pytest -x                                     # stop on first failure
```

### 3.3 Sanity-check scripts (end-to-end on real data)

```powershell
py scripts/m2_rule_engine_demo.py                   # ~5 s; Layer 2 on synthetic inputs
py scripts/m3a_retrieval_demo.py                    # ~10 s; FAISS retrieval on 4 queries
py scripts/m3b_pt_accuracy_eval.py --n-samples 200  # ~6 s; quick PT-accuracy smoke
py scripts/m3b_pt_accuracy_eval.py --n-samples 2000 # ~60 s; full PT-accuracy check
```

Outputs go to stdout. To capture for review:

```powershell
py scripts/m3b_pt_accuracy_eval.py --n-samples 2000 > reports/m3b_acc_$(Get-Date -Format yyyyMMdd).txt
```

### 3.4 Build-script (long-running)

```powershell
py scripts/m3a_build_index.py                       # 90–120 minutes wall time
py scripts/m3b_build_clusters.py                    # 10–20 minutes wall time
```

Both are idempotent — each run creates a new immutable directory
under `artifacts/v1/run_<UTC_timestamp>/`. The `current/` pointer
updates to the latest successful run.

### 3.5 Linting + type-checking

```powershell
py -m ruff check src tests scripts                  # style + bug-prone patterns
py -m black --check src tests scripts               # formatting
py -m mypy src                                      # strict typing
```

Configurations are in [`pyproject.toml`](../pyproject.toml). ruff and
mypy are strict; black formatting is mandatory.

---

## 4. Test-data strategy

We use three tiers of data, in increasing order of realism:

### 4.1 Synthetic data inside test files

**Used for** ~90% of unit tests. Constructed inline so the test file
is self-contained and tests run in milliseconds.

**Examples:**

| Helper | Where | Produces |
|---|---|---|
| `_make_products(...)` | [`test_split.py:18-33`](../tests/test_split.py#L18-L33) | DataFrame shaped like 1B with controllable ProductType cardinality and singleton counts |
| `corpus` fixture | [`test_layer3_index.py:35-41`](../tests/test_layer3_index.py#L35-L41) | 200 random 384-d L2-normalized vectors, seed=123, IDs 1000..1199 |
| `_make_embeddings_and_index(...)` | [`test_layer3_clusters.py:21-30`](../tests/test_layer3_clusters.py#L21-L30) | 40 synthetic embeddings with deterministic PT-band assignments |
| `_hit(pid, score)` | [`test_layer3_consensus.py:23-24`](../tests/test_layer3_consensus.py#L23-L24) | One-line constructor for `SearchHit` objects |

**Convention:** all randomness uses `np.random.default_rng(<fixed-int>)`
or `random.Random(<fixed-int>)`. We do not use Python's global
`random` module in tests — that would make outcomes depend on test
ordering.

### 4.2 Session-scoped fixtures (real config + small generated artifacts)

Defined once per pytest session in [`tests/conftest.py`](../tests/conftest.py):

| Fixture | Returns |
|---|---|
| `settings` | The actual `Settings` object loaded from `config/*.yaml`. Tests use the real thresholds + encoder ID, never a fabricated one |
| `aliases` | Convenience handle for `settings.unit_aliases` (used by 0 active tests now that Layer 1 is archived; retained for the extraction-team integration suite) |

### 4.3 Real eParts data (out-of-pytest)

The full 1B + 1A + 2A files live under
[`the_standard_data/`](../the_standard_data/). They are:

* Read-only — no test writes to them
* `.gitignore`d (~1.6 GB) — distributed via shared drive
* Used **only by the sanity-check scripts in §2.4**, not by pytest

**Why not in pytest:** loading 1A (1.4 GB) makes the suite slow.
Loading 1B alone takes ~3 s — also too slow if we want a <15 s feedback
loop. Sanity scripts run on real data on demand instead.

### 4.4 Generated test artifacts

| Artifact | Origin | When invalidated |
|---|---|---|
| `data/splits/{train,val,test}.parquet` | `m1_build_splits.py`, seed=42, deterministic | When 1B itself changes |
| `artifacts/v1/run_<ts>/faiss.bin` + `ids.npy` | `m3a_build_index.py` | When encoder model changes or 1B changes |
| `artifacts/v1/run_<ts>/centroids.parquet` + `cluster_cov.npz` | `m3b_build_clusters.py` | When the train split or 1A changes |

Older runs stay on disk for rollback. The `current/` alias points at
the most recent successful build.

### 4.5 What we DON'T have — real customer samples

Per spec §2.3, the 1A descriptions are **internal eParts team-written
text**, not raw customer emails / order forms. We have not received
real customer-shaped data yet. This means:

* All Layer 1 / Layer 2 fixtures are synthetic prose written by us
* End-to-end calibration validity is unverified until M5
* The "auto-process precision ≥ 0.95" target in spec §1.3 has only
  optimistic projection support, not held-out empirical support

**This is a standing ask of eParts** — see
[`Data_Utilization_Report.md`](Data_Utilization_Report.md) §7.

---

## 5. Sanity checks — at three levels

### 5.1 Build-time sanity (inside the build scripts)

Every long-running build script self-validates its output before
declaring success:

| Script | Sanity gate |
|---|---|
| `m3a_build_index.py` | `index.ntotal` matches the number of non-blank input rows; persistence completes without exception |
| `m3b_build_clusters.py` | Every full-cluster Σ⁻¹ has all eigenvalues > 0 (PSD); count of low-sample clusters is in expected range (spec §7.2 says ~20–30 empirically) |

If a sanity gate fails, the script prints `WARNING:` lines and the
caller is expected to inspect before promoting `current/`.

### 5.2 Run-time sanity (inside the production code path)

| Location | Check |
|---|---|
| [`src/layer3_semantic/encoder.py:42-50`](../src/layer3_semantic/encoder.py#L42-L50) | After loading the sentence-transformer, verify it produces vectors of the dimension declared in `encoder.yaml`. Mismatch raises `ValueError` early, before any FAISS code runs |
| [`src/layer3_semantic/index.py:55-59`](../src/layer3_semantic/index.py#L55-L59) | `ProductIndex.__init__` rejects mismatched lengths between FAISS index and `product_ids` array |
| [`src/layer2_rules/guardrail.py`](../src/layer2_rules/guardrail.py) | The 2A guardrail itself is a sanity check on rule-engine output |

### 5.3 Post-build acceptance (spec §7.2 milestone gates)

For each milestone, the spec's §7.2 lists numeric or behavioral gates
the run must meet. Our scripts produce these as printable summaries —
see §2.4. Example (M3b):

```
PT accuracy report
  samples drawn       : 2,000
  blank descriptions  : 2 (skipped)
  evaluated           : 1,998
  correct             : 1,892
  overall accuracy    : 0.9469
  spec target (M3b)   : 0.9500
  result              : FAIL
```

When acceptance gates miss (as M3b's overall PT accuracy is currently
0.0031 below target), the report records the variance and the team
discusses whether to retune (§6.2 tunable parameters) or escalate.

---

## 6. Reproducibility — the team's hardest rule

ML systems are easy to make unreproducible by accident. Our defenses:

| Practice | Where enforced |
|---|---|
| Fixed seed = 42 for **every** random operation | spec §2.2; verified in all `_make_*` helpers |
| Pinned dependency versions | [`requirements.txt`](../requirements.txt) with `>=` lower + `<` upper bounds (e.g. `torch>=2.2,<3.0`) |
| No hard-coded thresholds in `src/` | spec §11.3; enforced by code review |
| All tunables in `config/*.yaml` | Five files: `unit_aliases`, `encoder`, `faiss`, `thresholds`, `calibration` |
| Each training run writes immutable artifacts | `artifacts/v1/run_<UTC_timestamp>/`; never overwritten |
| Encoder model hash recorded per run | `artifacts/v1/run_<ts>/encoder_hash.txt` |
| Build wall time recorded per run | `build_info.json` |
| pytest auto-seeded via `default_rng(int)` | No reliance on global random state |

**Anti-patterns to flag in review** (and that QA could lint-check):

* `np.random.seed(...)` — global state, brittle
* `random.shuffle(list)` without an `random.Random(seed)` instance
* Reading wall-clock time and embedding into output paths without
  also recording the random seed
* Comparing floats with `==`; always use `pytest.approx` or
  `np.allclose` with explicit `atol`

---

## 7. Workflow standardization

### 7.1 Branch / commit / review

Not currently enforced — there is no CI integration yet. We rely on
human review and the test suite passing locally before merging.
**This is an explicit gap — see §10 ask #1.**

### 7.2 Naming & vocabulary

We follow the V1 Engineering Spec's vocabulary **verbatim**:

| Spec term | Code term |
|---|---|
| Confidence (rule) | `conf_rule` |
| Confidence (embedding) | `conf_embed` |
| Confidence (final, fused) | `conf_final` |
| ProductType consensus confidence | `pt_conf` |
| Cluster centroid | `mu` |
| Cluster covariance inverse | `sigma_inv` |
| Sigma (Gaussian decay width) | `sigma_pt` |
| Mahalanobis distance squared | `mahalanobis_d2` |

We do not introduce synonyms. This costs flexibility but ensures
docs ↔ code ↔ spec all line up without translation.

### 7.3 File / folder layout

```
ML/Model/
├── src/                       importable library code
│   ├── contracts.py           inter-layer dataclasses + Protocols
│   ├── config.py              YAML loader
│   ├── data/                  Layer 0 — loaders + splits
│   ├── layer2_rules/          Layer 2 — rule engine
│   └── layer3_semantic/       Layer 3 — encoder, FAISS, consensus, clusters
├── tests/                     pytest suite
│   ├── conftest.py            session fixtures
│   └── test_*.py              one test file per src module (1:1 mapping)
├── scripts/                   long-running CLI tools (build, evaluate)
├── config/                    YAML — every tunable parameter
├── data/                      derived training data + working caches (gitignored)
├── artifacts/v1/run_<ts>/     immutable build outputs (gitignored)
├── reports/                   evaluation outputs (M5 onward; gitignored)
├── eparts_doc/                team docs (this file)
└── the_standard_data/         eParts raw CSVs (gitignored)
```

Test files mirror src — `src/layer3_semantic/clusters.py` → `tests/test_layer3_clusters.py`.

### 7.4 Coding standards (enforced by tooling)

| Tool | Role | Config |
|---|---|---|
| **ruff** | Lint + import sort + bug-prone patterns | `pyproject.toml` [tool.ruff] |
| **black** | Auto-formatter | `pyproject.toml` [tool.black]; line length 100 |
| **mypy** | Strict static typing | `pyproject.toml` [tool.mypy]; `strict = true` |
| **pytest** | Test runner | `pyproject.toml` [tool.pytest.ini_options] |

All `src/` code is fully type-annotated. Tests are allowed less strict
typing (per `[tool.ruff.lint.per-file-ignores]`).

---

## 7.5 What changed since v0.1 (M4–M7 + a QA win)

This doc's first draft was written at 94 tests (pre-M4). Added since:

| Area | Tests | Notable QA content |
|---|---:|---|
| **M4** fusion + caps + routing | +18 | property tests: `conf_final ∈ [0,1]` for any input; `conf_final = 1.0` **iff** Tier-1 exact match |
| **M4** σ calibration | +16 | Brier/ECE math hand-verified; a perf test asserting `D²` is cached once per (query, cluster), not recomputed per σ candidate |
| **M5** evaluation harness | +30 | metrics module + report serialization + the inference-runner |
| **M6** online updates | +21 | confirm/pushback math vs frozen spec formula; **8-thread × 5-confirm concurrency test** (no update lost); audit-log round-trip; replay recovery |
| **M7** REST service | +16 | FastAPI TestClient — endpoint shape, schema validation, feedback 404/422/503 paths, drift-KL math |

**Test-count progression:** 94 (this doc's v0.1) → 118 (M3c) → 152 (M4)
→ 200 (M6) → 216 (M7) → **219** (after the PR-review regression below).

### A concrete QA win — review caught a real bug

On the M6 PR a reviewer noted there was **no regression test for
replay-after-snapshot**. Working it through:

1. We wrote the requested test and ran it against the **unfixed** code — **it failed**, proving it wasn't merely a missing test: there was a real double-counting bug (`replay()` re-applied updates already baked into the snapshot, so cluster `N` drifted upward on restart).
2. Fixed it — `snapshot()` now rotates the audit log to a numbered archive so `load(snapshot) + replay(live_log)` is drift-free by construction (and the audit trail is preserved, not deleted).
3. Added 3 regression tests; feedback suite 18 → 21.

This is the loop we want QA to help us systematize: **review surfaces a
risk → failing test first → fix → regression test prevents recurrence.**

### Production QA — drift monitoring (M7)

QA does not stop at deployment. The M7 service exposes a **drift signal**:
KL divergence of the live `conf_final` distribution vs the M5 baseline
(`reports/.../confidence_dist.csv`). A rising KL means production traffic
has shifted away from what the model was evaluated on → a signal to
re-evaluate / recalibrate. This is the runtime arm of our QA story
(CAP-ML-04).

---

## 8. Known coverage gaps (where QA help is wanted)

These are gaps **we** see; QA may find more.

### 8.1 Untested edge cases (we know about)

Still-open edge cases (some originally listed at M3a remain open):

| Untested scenario | Layer | Severity |
|---|---|---|
| Empty string `""` passed to `Encoder.encode()` | L3 | Low |
| Very long text (>512 tokens) — truncation behavior | L3 | Low |
| IVFFlat vs Flat top-K **agreement** on the same query (we only test each variant in isolation) | L3 | Medium |
| Loading a missing / corrupt `faiss.bin` | L3 | Medium |
| `ClusterStore.load()` against a `centroids.parquet` whose paired `cluster_cov.npz` is stale | L3 | Medium |
| Encoder's behavior on identical strings ("are batches deterministic?") | L3 | Low |
| **Concurrent load on the M7 `/predict` endpoint** (≥ 50 req/s) — single-thread warm only so far | service | Medium |
| Cold-start behavior (first request lazy-loads the encoder, ~6 s) | service | Low |

### 8.2 Categories we don't yet have

| Category | What it would do |
|---|---|
| **Mutation testing** | Verify that our tests would actually fail if a `==` were silently changed to `!=` (catch trivially-broken assertions) |
| **Coverage measurement** | Branch + line coverage per module; identify untested code paths |
| **Property-based testing** | Random-input fuzz with shrinking, via Hypothesis |
| **Load tests** | Sustained req/s + p95 latency under realistic concurrency — M7 endpoint exists, single-thread warm latency measured; the concurrent ≥ 50 req/s test is still outstanding |
| **Soak / endurance tests** | Long-running pipeline that exercises memory leaks, FD leaks, etc. |
| **Snapshot tests** | Capture rich outputs (full PT-accuracy reports, retrieval top-50 lists) as committed reference files; flag drift on every PR |
| **Contract tests with extraction team** | Validate their team's `ExtractedInput` output against our `src/contracts.py` schema |

### 8.3 Real-data shortfalls

* No real customer emails, PDFs, or images
* No labeled correction cases (spec §2.3 — 50–100 hand-picked
  expected; not delivered yet)
* No production traffic mix data

---

## 9. Open questions for QA

1. **Which CI platform do we adopt?** GitHub Actions / GitLab CI /
   Jenkins / Azure DevOps. The repo currently lacks any CI config; we
   want one that runs ruff + black + mypy + pytest on every PR.
2. **Coverage target.** What % do we aim for, and which type
   (line / branch / mutation)? My instinct: branch coverage ≥ 85%
   on `src/`, no target on `scripts/`. Open to QA's recommendation.
3. **Where should slow tests live?** Some tests (encoder ones, ~60 s
   first run) currently slow the suite. Options: mark with
   `@pytest.mark.slow` and exclude from default run; split into
   a separate "integration" pytest target; or accept the cost.
4. **Test-data fixture management.** When the extraction team
   delivers their first integration fixture set, should those live
   in `tests/fixtures/extraction/` (in-repo, deduplicated) or in a
   shared S3-style location? Tied to the question of whether fixtures
   can hold proprietary eParts data.
5. **Acceptance gate enforcement.** Currently the spec acceptance
   gates (M3b PT accuracy ≥ 0.95, M5 ECE ≤ 0.05, etc.) are
   reported but not automatically blocked. Should a regression of
   these gates fail CI?
6. **Synthetic data realism.** Our current synthetic fixtures are
   hand-written. Should we move toward LLM-generated synthetic data
   (sampled from `bge-small`'s likely-confused neighborhoods) to
   stress-test failure modes?

---

## 10. Specific asks from QA

Now that V1 is code-complete (M1–M7), ordered by impact:

1. **Stand up CI** for ruff + black + mypy + pytest on every push/PR —
   on whichever host we standardize (GitHub Actions or, now that the
   code also mirrors to Bitbucket, Bitbucket Pipelines). This is the
   single biggest gap: 219 tests run manually today. Tag a maintainer.
2. **Run the M7 concurrent load test** (≥ 50 req/s, p95 ≤ 200 ms) — the
   one spec §7.2 acceptance item we have not yet measured. Helps us know
   whether the encoder tail under concurrency breaks the latency budget.
3. **Coverage measurement** — add `pytest-cov`, agree on a target
   (branch coverage on `src/`?), surface it in CI.
4. **Acceptance gates as CI checks** — wire the spec §7.2 numeric
   targets (PT accuracy ≥ 0.92, ECE ≤ 0.05, …) so a regression fails the
   build automatically rather than being caught by eye in the M5 report.
5. **Add Hypothesis** for property-based fuzzing of the invariants we
   currently hand-pick (PSD covariance, L2-normalized vectors,
   monotonic returned scores).
6. **Edge cases from §8.1** — the medium-severity ones (FAISS error
   paths, stale `cluster_cov.npz`, concurrent `/predict`).

---

## 11. Glossary

| Term | Meaning |
|---|---|
| **Unit test** | One function or method, narrow assertion |
| **Property test** | An invariant that must hold over many inputs (currently hand-picked; ideally fuzz-generated) |
| **Integration test** | Multiple modules together, one slice of the pipeline |
| **Sanity-check script** | CLI that runs end-to-end on real data and reports milestone acceptance |
| **Acceptance gate** | A specific spec §7.2 numeric or behavioral pass condition |
| **Smoke test** | Quick `--limit N` variant of a sanity script for sub-minute feedback |
| **Reproducibility** | Same inputs + same seed → bit-identical outputs |
| **Synthetic data** | Hand-written or RNG-generated, NOT from eParts production traffic |
| **Real data** | The five CSV files under `the_standard_data/` |
| **Run directory** | `artifacts/v1/run_<UTC_timestamp>/` — one immutable build's outputs |

---

*Document owner: ML team — eParts Capstone (MSE Studio).*
*Related docs:* [V1_Engineering_Spec](V1_Architecture_Design.md) ·
[V1_Development_Plan.md](V1_Development_Plan.md) ·
[Layer1_Layer2_Implementation_Report.md](Layer1_Layer2_Implementation_Report.md) ·
[ExtractionHandoff_Spec.md](ExtractionHandoff_Spec.md).
