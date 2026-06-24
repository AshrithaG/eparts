# ML-CT (Component Testing) — Test Plan

| | |
|---|---|
| Task | ML-CT — component testing, 10 validation hours |
| Scope | The four ML modules only: product search (M3a), category prediction (M3b), attribute scoring (M3c), decision/calibration (M4) |
| Method | Read-only inventory of existing tests + gap analysis + hour breakdown. No code changed. |
| Date | 2026-06-17 |
| Baseline | V1 code-complete (M1–M7); **219** tests passing (verified `grep -c "^def test_" tests/*.py`) |

**Out of ML-CT scope** (named four modules only): Layer 2 rule engine
(`test_engine/guardrail/manufacturers/numeric/part_numbers` — deterministic
rules, not an ML module), M1 split (`test_split`), M5 eval harness
(`test_evaluation_*`), M6 feedback + M7 service (`test_layer4_feedback`,
`test_service` — those belong to ML-IT).

**Headline finding:** ML-CT is overwhelmingly a *triage-and-organize* task,
not a write-from-scratch task. **96 of the 219 tests already cover the four
components.** The gaps are edge cases, not missing core coverage.

---

## Execution status (2026-06-17) — D1–D5 done

The plan below is now **executed** (D6 reporting pending):

| Step | Status |
|---|---|
| D1 — mark the component suite | ✅ `pytestmark = pytest.mark.ml_ct` added at module level to all 7 component files; `ml_ct` marker registered in `pyproject.toml` |
| D2–D5 — P1 boundary tests | ✅ **10** new P1 tests written (the 8 planned, with the faiss-load gap split into missing-dir + corrupt-file for thoroughness) |
| D6 — run + report | ◐ this section |

**Result:** `pytest -m ml_ct` → **106 passed** (96 existing + 10 new),
123 deselected. Full suite **229 passed**, no regressions. Per component:

| Component | ml_ct tests |
|---|---:|
| M3a product search (encoder 7 + index 12) | 19 |
| M3b category prediction (consensus 13 + clusters 13) | 26 |
| M3c attribute scoring | 25 |
| M4 decision / calibration (fusion 20 + calibration 16) | 36 |
| **Total** | **106** |

The 10 new P1 tests (each grep-able as `ml_ct` boundary tests):
`test_empty_string_encodes_to_valid_vector`,
`test_load_missing_faiss_bin_raises`, `test_load_corrupt_faiss_bin_raises`,
`test_ivfflat_matches_flat_when_exhaustive`,
`test_k_greater_than_ntotal_returns_all_without_padding`,
`test_pt_vote_exact_tie_is_deterministic`,
`test_pt_ambiguity_cap_boundary_is_exclusive_at_band_low`,
`test_routing_at_exact_thresholds`,
`test_score_lower_boundary_far_query_drives_conf_embed_to_zero`,
`test_default_sigma_is_one`.

Two execution findings: (1) the `k > ntotal` test was switched to a Flat
(exhaustive) index — an approximate IVFFlat at `nprobe < nlist` returns
only probed-cell vectors and wouldn't exercise the `-1` padding filter;
(2) `band_high` (0.80) has **no** hard branch in the four components
(reporting-only, `m3b_pt_accuracy_eval.py:141`), so only the `band_low`
(0.60) cap boundary is asserted. **P2 backlog (below) is unstarted.**

---

## Part A — Existing component-test inventory

**96 tests across the four ML-CT components:**

| Component | Files | Tests |
|---|---|---:|
| 1. Product search (M3a) | `test_layer3_encoder.py` + `test_layer3_index.py` | 6 + 8 = **14** |
| 2. Category prediction (M3b) | `test_layer3_consensus.py` + `test_layer3_clusters.py` | 12 + 13 = **25** |
| 3. Attribute scoring (M3c) | `test_layer3_scoring.py` | **23** |
| 4. Decision / calibration (M4) | `test_layer4_fusion.py` + `test_layer4_calibration.py` | 18 + 16 = **34** |
| | | **96** |

### A1 — Product search (M3a) — 14 tests

**Encoder** ([`test_layer3_encoder.py`](../tests/test_layer3_encoder.py)) — real frozen BGE model:

| Test | Line | Asserts |
|---|---|---|
| `test_encoder_advertises_configured_dimension` | 20 | dim=384 from config, no model load at construction |
| `test_encode_returns_float32_with_correct_shape` | 27 | `(N, 384)` float32 |
| `test_encoded_vectors_are_l2_normalized` | 34 | every row unit-norm (atol 1e-5) |
| `test_encode_one_returns_1d_vector` | 42 | single string → `(384,)` |
| `test_semantically_similar_strings_score_higher` | 48 | synonyms closer than disjoint topics |
| `test_config_dimension_mismatch_raises` | 58 | config lies about dim → `ValueError` |

**FAISS index** ([`test_layer3_index.py`](../tests/test_layer3_index.py)) — synthetic vectors:

| Test | Line | Asserts |
|---|---|---|
| `test_build_index_populates_n_total` | 44 | `size==200`, `dimension==384` |
| `test_search_returns_top_k_with_self_as_first_neighbor` | 51 | self is top-1 at score≈1.0 |
| `test_search_k_override` | 63 | `k=3` returns 3 |
| `test_persistence_roundtrip` | 70 | save→load gives identical product_ids + scores |
| `test_id_length_mismatch_raises` | 88 | mismatched ids → `ValueError` |
| `test_unknown_index_type_raises` | 94 | `HNSW` → `ValueError` |
| `test_query_accepts_1d_vector` | 110 | 1-D query auto-reshaped |
| `test_flat_index_variant` | 119 | Flat index also builds + queries |

### A2 — Category prediction (M3b) — 25 tests

**PT consensus** ([`test_layer3_consensus.py`](../tests/test_layer3_consensus.py)):

| Test | Line | Asserts |
|---|---|---|
| `test_unanimous_top_k_gives_pt_conf_1` | 35 | all hits one PT → pt_conf=1.0 |
| `test_split_consensus_proportional_to_weighted_similarity` | 45 | pt_conf = vote share |
| `test_ambiguous_band_below_0_60` | 56 | near-tie lands < 0.60 |
| `test_high_consensus_band_above_0_80` | 66 | strong majority ≥ 0.80 |
| `test_negative_similarity_is_clamped_to_zero` | 78 | negative sim contributes 0 |
| `test_unknown_product_id_is_silently_skipped` | 87 | unknown pid ignored |
| `test_top_k_override_restricts_vote` | 95 | top_k=2 only counts first 2 |
| `test_empty_hits_returns_none` | 107 | no hits → None |
| `test_all_unresolved_hits_returns_none` | 111 | all unknown pids → None |
| `test_all_zero_or_negative_scores_returns_none` | 117 | zero denominator → None |
| `test_build_pt_index_from_1b` | 123 | builds map, drops null PT |
| `test_build_pt_index_rejects_missing_columns` | 140 | missing cols → ValueError |

**Cluster build/persistence** ([`test_layer3_clusters.py`](../tests/test_layer3_clusters.py)):

| Test | Line | Asserts |
|---|---|---|
| `test_mahalanobis_uses_identity_for_low_sample` | 55 | low-sample → squared Euclidean |
| `test_mahalanobis_uses_sigma_inv_when_present` | 74 | full → quadratic form |
| `test_build_clusters_groups_by_pt_attr_value` | 107 | grouping + low-sample count |
| `test_cluster_mu_equals_mean_of_member_embeddings` | 137 | μ = mean |
| `test_sigma_inv_is_positive_definite_for_full_clusters` | 147 | Σ⁻¹ PD (eigenvalues > 0) |
| `test_ill_conditioned_cluster_is_demoted_to_low_sample` | 166 | near-singular → demoted (the PR-review fix) |
| `test_low_sample_clusters_store_only_mu` | 202 | N<5 → sigma_inv None |
| `test_chunked_streaming_combines_groups_across_chunks` | 212 | groups merge across chunks |
| `test_train_split_filter_drops_non_train_rows` | 223 | only train rows counted |
| `test_unknown_product_id_in_1a_is_skipped` | 240 | bogus pid skipped |
| `test_null_attribute_or_value_is_skipped` | 248 | null attr/value skipped |
| `test_attributes_for_pt_and_values_for_pt_attribute` | 264 | index accessors |
| `test_persistence_roundtrip` | 282 | save→load (parquet + npz) |

### A3 — Attribute scoring (M3c) — 23 tests ([`test_layer3_scoring.py`](../tests/test_layer3_scoring.py))

**UsagePrior** (10):

| Test | Line | Asserts |
|---|---|---|
| `test_zero_count_yields_neutral_prior` | 29 | UC=0 → prior=0.5 (**boundary**) |
| `test_max_count_yields_top_prior` | 35 | UC=max → prior=1.0 (**boundary**) |
| `test_intermediate_count_falls_in_band` | 41 | mid → ~0.75 |
| `test_unknown_attribute_returns_neutral` | 54 | unknown attr → 0.5 |
| `test_zero_max_count_returns_neutral_for_all_values` | 60 | max UC=0 → 0.5 |
| `test_case_and_whitespace_insensitive` | 67 | normalized lookup |
| `test_count_lookup_exposes_raw_value` | 75 | count() raw |
| `test_build_from_2a_aggregates_correctly` | 82 | build from 2A |
| `test_build_from_2a_rejects_missing_columns` | 99 | missing cols → ValueError |
| `test_build_from_2a_drops_null_rows` | 105 | null rows dropped |

**SemanticScorer** (13):

| Test | Line | Asserts |
|---|---|---|
| `test_returns_one_hit_per_attribute` | 200 | one SemanticHit per attr |
| `test_top_n_per_attribute_defaults_to_three` | 207 | top-3 (spec §4.3 [3d]) |
| `test_top_n_can_be_overridden` | 214 | config top_n |
| `test_candidates_sorted_descending_by_conf_embed_final` | 221 | sorted desc |
| `test_scope_is_restricted_to_predicted_pt` | 228 | only PT's attributes scored |
| `test_pt_with_no_clusters_returns_empty_hits` | 235 | unknown PT → empty |
| `test_query_at_cluster_mu_scores_one` | 245 | d²=0 → conf_embed=1.0 (**upper boundary**) |
| `test_all_scores_in_unit_interval` | 257 | all in [0,1] |
| `test_conf_embed_final_never_exceeds_usage_prior` | 267 | property: ≤ prior |
| `test_low_sample_flag_propagates` | 279 | low_sample flag surfaces |
| `test_sigma_override_changes_scoring` | 295 | wider σ → higher conf |
| `test_sigma_missing_pt_falls_back_to_default` | 312 | **σ fallback for uncalibrated PT** |
| `test_usage_count_attached_to_candidate` | 321 | usage_count on candidate |

### A4 — Decision / calibration (M4) — 34 tests

**Fusion + caps + routing** ([`test_layer4_fusion.py`](../tests/test_layer4_fusion.py), 18):

| Test | Line | Asserts |
|---|---|---|
| `test_conf_final_always_in_unit_interval` | 145 | conf ∈ [0,1] over 5 extremes |
| `test_conf_final_equals_one_iff_tier1_terminal` | 166 | conf=1.0 **iff** Tier-1 exact match |
| `test_fusion_formula_with_alpha_07` | 203 | conf = 0.7·rule + 0.3·embed |
| `test_no_rule_hit_means_conf_rule_zero` | 216 | **conf_rule=0 path** |
| `test_demoted_rule_hit_does_not_contribute` | 228 | demoted hit ignored |
| `test_pt_ambiguity_cap_when_pt_conf_below_band_low` | 246 | PT<0.60 → cap 0.75 |
| `test_pt_ambiguity_cap_doesnt_lower_already_lower_score` | 261 | cap doesn't raise |
| `test_low_sample_cap_when_top_candidate_is_low_sample` | 274 | low-sample → cap 0.70 |
| `test_both_caps_fire_smaller_cap_wins` | 289 | **both caps → min(0.75,0.70)=0.70** |
| `test_routing_auto_process_at_or_above_0_85` | 310 | 0.985 → AUTO |
| `test_routing_human_review_in_band` | 321 | 0.835 → REVIEW |
| `test_routing_flag_unclear_below_0_50` | 335 | 0.15 → FLAG |
| `test_tier1_terminal_emits_single_auto_processed_prediction` | 350 | **Tier-1 short-circuit** |
| `test_tier1_terminal_ignores_semantic_result` | 365 | Tier-1 wins over semantic |
| `test_no_semantic_no_rules_yields_empty_predictions` | 383 | empty → empty |
| `test_semantic_hit_with_no_candidates_is_skipped` | 392 | empty candidates skipped |
| `test_predicted_value_comes_from_semantic_top_1` | 402 | v* = semantic argmax |
| `test_latency_and_model_version_pass_through` | 417 | passthrough |

**σ calibration + Brier/ECE** ([`test_layer4_calibration.py`](../tests/test_layer4_calibration.py), 16):

| Test | Line | Asserts |
|---|---|---|
| `test_brier_perfect_calibration` | 27 | Brier=0 |
| `test_brier_worst_case` | 32 | Brier=1 |
| `test_brier_hand_computed` | 37 | formula spot-check |
| `test_brier_empty_input_returns_zero` | 45 | empty → 0 |
| `test_ece_perfect_calibration` | 49 | ECE=0 |
| `test_ece_max_miscalibration` | 57 | ECE=1 |
| `test_ece_empty_input_returns_zero` | 62 | empty → 0 |
| `test_ece_handles_bin_with_no_samples` | 66 | empty bins skipped |
| `test_sigma_table_roundtrip` | 79 | save→load |
| `test_sigma_for_missing_pt_returns_default` | 97 | **SigmaTable default for missing PT** |
| `test_calibrator_recovers_small_sigma_when_clusters_are_close` | 147 | grid picks small σ |
| `test_calibrator_picks_wider_sigma_when_d2_is_large` | 178 | grid picks wide σ |
| `test_calibrator_returns_no_entry_for_pt_with_no_clusters` | 223 | no clusters → no entry |
| `test_calibrator_skips_attributes_with_no_clusters_under_pt` | 236 | skip absent attr |
| `test_calibrator_caches_d2_across_sigmas` | 252 | d² cached once per (query,cluster) |
| `test_calibrator_uses_lambda_cal_from_config` | 286 | λ_cal honored |

---

## Part B — Gap analysis (by component, priority-tagged)

Legend: **P1** = should do in the 10h · **P2** = backlog beyond 10h.
"✅ covered" rows correct hypotheses that turned out already-tested.

### Component 1 — Product search (M3a)

| Gap | Status | Priority |
|---|---|---|
| Empty description `""` → encoder | ❌ not tested | **P1** |
| Missing / corrupt `faiss.bin` on load | ❌ not tested (only happy-path roundtrip at index:70) | **P1** |
| IVFFlat vs Flat **agreement** on same query (each tested in isolation only) | ❌ not tested | **P1** |
| `k > ntotal` (FAISS pads with -1; search() at index.py:111 filters -1 but untested) | ❌ not tested | **P1** |
| Empty index (ntotal=0) query | ❌ not tested | P2 |
| Very long text (>512 tokens) truncation | ❌ not tested | P2 |
| OOV / rare token (e.g. "BA/3K-S#") → valid non-zero vector | ❌ not tested | P2 |
| Encoder determinism (same string twice → identical vector) | ❌ not tested | P2 |
| Duplicate identical vectors in index | ❌ not tested | P2 |

### Component 2 — Category prediction (M3b)

| Gap | Status | Priority |
|---|---|---|
| PT_conf **exactly** at band edges (== 0.60, == 0.80) — `>=` vs `>` behavior | ❌ in-band tested (56, 66) but not the exact boundary | **P1** |
| PT-vote **tie** (two PTs exactly equal vote) — argmax tie-break | ❌ not tested | **P1** |
| Single neighbor (top-K=1) | ❌ smallest tested is 2–3 hits | P2 |
| Single-member cluster (N=1) in build | ❌ low-sample tested at N=3 (clusters:202), N=1 not isolated | P2 |

### Component 3 — Attribute scoring (M3c)

| Gap | Status | Priority |
|---|---|---|
| Score lower boundary **exactly 0** (huge d² → conf_embed→0) | ❌ only upper boundary (d²=0→1) tested at scoring:245 | **P1** |
| Low-sample cluster scored **through `score()`** end-to-end (identity-Σ Mahalanobis in the scoring path) | ⚠️ flag propagation tested (279); the score-path math for a low-sample cluster not asserted | P2 |
| usage prior boundaries (0.5 / 1.0) | ✅ **covered** (scoring:29, 35) | — |
| top-3 / sorted / scope / [0,1] | ✅ **covered** (207, 221, 228, 257) | — |

### Component 4 — Decision / calibration (M4)

| Gap | Status | Priority |
|---|---|---|
| Routing at **exact threshold** (conf_final == 0.85 and == 0.50) — `>=` boundary | ❌ tests use 0.985 / 0.835 / 0.15 (fusion:310-342), never the exact edge | **P1** |
| **σ fallback for the 137 uncalibrated PTs** (default σ) | ✅ **covered** — `test_sigma_missing_pt_falls_back_to_default` (scoring:312) + `test_sigma_for_missing_pt_returns_default` (calibration:97). *Reinforcing nit:* both use a fabricated default (2.0) and arbitrary PT id, not the production default 1.0 — a one-line assertion that `SemanticScorerConfig().default_sigma == 1.0` would close it. | P2 |
| Both caps simultaneously | ✅ **covered** (fusion:289) | — |
| Tier-1 short-circuit | ✅ **covered** (fusion:350, 365) | — |
| conf_rule=0 | ✅ **covered** (fusion:216) | — |

**Net new P1 tests to write: ~8** (search 4, category 2, scoring 1, decision 1).
Everything else is either already covered or P2 backlog.

---

## Part C — Data requirement: **NO new data needed** (confirmed with evidence)

ML-CT requires *controllable, known-answer* inputs. Real customer data —
whose correct attribute values are unlabeled and whose phrasing is
uncontrolled — is **unsuitable** for component testing (you can't assert
"expected output" on an input whose answer you don't know). The hypothesis
"we need new data" is **rejected**.

**Evidence — every component test already uses synthetic or frozen-model inputs:**

| Component | Test data source | Reusable generator |
|---|---|---|
| Encoder | real frozen `bge-small` + hardcoded HVAC strings; `settings` fixture | [`conftest.py`](../tests/conftest.py) `settings` |
| FAISS index | synthetic random L2-normalized vectors, `np.random.default_rng(123)`, 200×384 | `corpus` fixture (index:35) + `_l2` (index:29) |
| Consensus | hand-built `SearchHit` + synthetic `ProductTypeIndex` | `pt_index` fixture (consensus), `_hit` (consensus) |
| Clusters | synthetic embeddings, seed 7; synthetic 1A `DataFrame` | `_make_embeddings_and_index` (clusters:21), `_make_1a_chunk` (clusters:47) |
| Scoring | deterministic `_mu` vectors + hand-built `UsagePrior`/`ClusterStore` | `_mu` / `_cluster` (scoring:~155) |
| Fusion | hand-built dataclasses + in-test `ThresholdsConfig` | `_thresholds` / `_pred` / `_candidate` (fusion:~50) |
| Calibration | synthetic `ValQuery` + identity Σ⁻¹ | `_full_cluster` / `_calibration_config` (calibration:~120) |

**Conclusion:** all 96 existing tests + the ~8 new P1 tests run on synthetic
inputs or the frozen encoder. Zero ML-CT tests require eParts data. (The
*separate* standing ask for real customer samples serves production-realism
validation and V2 — **not** component testing. Do not bundle them.)

The held-out `data/splits/test.parquet` is **not needed for ML-CT** either —
that's an ML-IT asset (end-to-end correctness on real held-out products).

---

## Part D — 10-hour breakdown

Two buckets: **triage** (organize what exists — fast) and **new tests**
(fill P1 gaps — slower). P2 gaps are listed as backlog beyond the 10h.

| # | Task | Type | Est. |
|---|---|---|---:|
| D1 | **Triage & label the 96 tests into an ML-CT suite.** Add a `@pytest.mark.ml_ct` marker (or a `component_tests` path convention) so `pytest -m ml_ct` runs exactly these 96. Produce a one-page component-coverage matrix (Part A is the draft). | triage | **3.0h** |
| D2 | **Search (M3a) P1 tests** — empty description, missing/corrupt `faiss.bin`, IVFFlat-vs-Flat top-K agreement, `k > ntotal`. | new | **2.0h** |
| D3 | **Category (M3b) P1 tests** — exact band-edge PT_conf (0.60 / 0.80), PT-vote tie-break. | new | **1.5h** |
| D4 | **Scoring (M3c) P1 test** — score lower boundary (huge d² → conf_embed→0). | new | **0.5h** |
| D5 | **Decision (M4) P1 tests** — routing at exact thresholds (conf == 0.85, == 0.50); + 1-line σ default=1.0 assertion. | new | **1.0h** |
| D6 | **Run `pytest -m ml_ct`, confirm all green, write the ML-CT result section** (pass/fail per component + coverage matrix). | triage | **1.0h** |
| | **Total** | | **9.0h** |
| | Buffer (flaky-test debugging, review fixes) | | **1.0h** |
| | **Grand total** | | **10.0h** |

**Fast vs slow split:** D1 + D6 (4.0h) are organization of existing tests.
D2–D5 (5.0h) are the ~8 new P1 edge-case tests. The work is **~60% new
tests / 40% triage**, but no test is large — they all reuse the existing
synthetic fixtures (Part C), so each new test is ~10–25 lines.

### P2 backlog (beyond the 10h, if hours free up)
Empty index, >512-token truncation, OOV token, encoder determinism,
duplicate vectors (search); single-neighbor, N=1 cluster (category);
low-sample scoring through `score()` (scoring). ~6 tests, ~2–3h.

---

## Reusable-fixture cheat-sheet (so new tests don't reinvent)

| Need | Reuse |
|---|---|
| A `Settings` / config | `conftest.py::settings` |
| Synthetic L2-normalized vectors | `test_layer3_index.py::corpus`, `_l2` |
| Synthetic cluster + store | `test_layer3_clusters.py::_make_embeddings_and_index`, `test_layer3_scoring.py::_cluster` |
| Hand-built fusion inputs | `test_layer4_fusion.py::_pred`, `_candidate`, `_semantic`, `_thresholds` |
| Synthetic 1A chunk | `test_layer3_clusters.py::_make_1a_chunk` |

---

*Read-only plan, 2026-06-17. All claims cite `file:line` / test name. No
code, config, or artifacts modified. Companion to the (separately planned)
ML-IT effort.*
