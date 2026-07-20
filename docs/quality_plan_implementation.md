# Quality Plan → Implementation Matrix

**Verified:** 2026-07-20, against `epartsservices/intelligent-attribute-prediction`
`master` (post CI-adoption merge) and the two **pending** test PRs
(`zhelianl/ml-ct-and-docs`, `zhelianl/ml-it-and-feedback-fix`, open since 2026-06-24).
**Scope:** Quality Plan (Draft 7) modules **3.3 Prediction** and **3.4 Routing** —
the ML modules whose tests exist today. Ingestion/normalization/writeback
modules are pre-implementation and their T-x.y rows remain *Planned* as the
plan states.

**Method:** every claimed status was checked against actual pytest functions
(file::name cited below), not against docs. This is the provenance the
impromptu review asked for.

---

## Headline facts

- **`master` today: 219 tests**, all green in CI on every PR (ruff + black +
  mypy + pytest with **branch coverage ≥ 85% hard gate** on `src/`).
- **+27 tests (246 total), the `ml_ct`/`ml_it` markers, the exact-boundary
  tests, and the G2 online-feedback fix + regression guard are in the two
  PENDING PRs** — approved-count zero since Jun 24. ⚠️ **Action: review and
  merge PR #2 and PR #3 before the crit.** Several PARTIALs below flip to
  VERIFIED on merge.
- The audit-trail, online-feedback, calibration, and drift-monitoring areas
  (plan modules 3.8–3.10 analogues) already have real coverage on master —
  better than the plan's "Planned" labels admit (details §3).

## 1. Module 3.3 — Prediction Service

| Test | Plan claim | On `master` today | After pending PRs merge | Implementing tests (master) |
|---|---|---|---|---|
| T-3.1 exact PN terminal @1.0; near-miss not exact | Passing | ✅ **VERIFIED** | ✅ | `test_layer4_fusion.py::test_conf_final_equals_one_iff_tier1_terminal`, `::test_tier1_terminal_emits_single_auto_processed_prediction`, `test_engine.py::test_tier1_*_terminates`, `test_part_numbers.py::test_is_exact_only_for_exact_match` |
| T-3.2 manufacturer fuzzy flips at cutoff | Passing | ⚠️ **PARTIAL** — above/below covered; no just-below/at/above triplet at one fixed cutoff | ⚠️ PARTIAL (not in pending PRs) | `test_manufacturers.py::test_below_threshold_returns_none`, `::test_partial_match_below_min_score_drops`, `test_engine.py::test_tier2_below_threshold_no_hit` |
| T-3.3 index identical across reload; recall ≥ 0.95 | Passing | ⚠️ **PARTIAL** — reload identity fully verified; recall≥0.95 is a per-vector spot check, no aggregate assertion | ⚠️ PARTIAL | `test_layer3_index.py::test_persistence_roundtrip`, `::test_search_returns_top_k_with_self_as_first_neighbor` |
| T-3.4 ambiguous PT → below auto-accept → review | Passing | ✅ **VERIFIED** (band + 0.75 cap each asserted; end-to-end chain implicit) | ✅ (+ exclusive-boundary test at 0.60) | `test_layer3_consensus.py::test_ambiguous_band_below_0_60`, `test_layer4_fusion.py::test_pt_ambiguity_cap_when_pt_conf_below_band_low` |
| T-3.5 thin clusters treated cautiously | Passing | ✅ **VERIFIED** | ✅ | `test_layer3_clusters.py::test_mahalanobis_uses_identity_for_low_sample`, `::test_ill_conditioned_cluster_is_demoted_to_low_sample`, `test_layer4_fusion.py::test_low_sample_cap_when_top_candidate_is_low_sample` |
| T-3.6 conf ∈ [0,1]; bands tested at each cutoff | Passing | ⚠️ **PARTIAL** — [0,1] fully verified (+ defensive clamp); bands sampled mid-range (0.985/0.835/0.15), never exactly at 0.85/0.50 | ✅ **VERIFIED** — pending PR adds routing tests at exact 0.85 and 0.50 | `test_layer4_fusion.py::test_conf_final_always_in_unit_interval`, `::test_routing_*` |

## 2. Module 3.4 — Routing Engine

| Test | Plan claim | On `master` today | After pending PRs merge | Notes |
|---|---|---|---|---|
| T-4.1 bands route correctly; flip only at cutoffs | Passing | ⚠️ **PARTIAL** — same mid-band sampling gap as T-3.6; `>=` inclusivity at exactly 0.85/0.50 unpinned | ✅ **VERIFIED** | boundary tests are in the pending ml_ct PR |
| T-4.2 100% branch coverage on routing module | Being written | ❌ **NOT IMPLEMENTED as specified** — global `fail_under=85` branch gate exists and is enforced in CI, but no per-module 100% gate | ❌ unchanged | decide: add a routing-module coverage check, or amend the plan to the global gate with rationale |
| T-4.3 capped attribute can never auto-accept | Passing | ⚠️ **PARTIAL** — caps (0.75/0.70) tested and numerically below 0.85, but no test asserts `routing != AUTO_PROCESS` on a capped prediction; invariant only holds via config numbers | ⚠️ PARTIAL | one small invariant test closes it |

## 3. Coverage the plan under-claims (already real on master)

| Plan area | Status in plan | Reality on master |
|---|---|---|
| Audit trail (3.8 analogue: feedback audit log) | Planned | `test_layer4_feedback.py` — append-exactly-one-line, JSON round-trip, snapshot archival, replay-without-drift, concurrent-writes-don't-lose-updates |
| Learning loop (3.9 analogue: online updates) | Planned | spec-formula tests for confirm/pushback + service-level `/feedback` tests |
| Monitoring/drift (3.10 analogue) | Being written | drift **KL gauge tested** (`test_service.py::test_drift_kl_set_after_predictions_with_baseline`), Prometheus endpoint tested |
| Calibration honesty (QA-2) | — | 16 tests in `test_layer4_calibration.py` (Brier, ECE, per-PT σ recovery) |

## 4. Follow-up actions (each is a ticket)

1. **Review + merge pending PRs #2/#3** (owner: reviewers listed on the PRs) — unblocks 246 tests, markers, boundary tests, G2 regression guard. ⚠️ also a process lesson: 3+ weeks of review latency on our highest-value test work.
2. Add the **capped-never-auto invariant test** (T-4.3, ~30 min).
3. Add **cutoff-triplet test for manufacturer fuzzy** (T-3.2, ~30 min).
4. Add **aggregate self-retrieval recall ≥ 0.95 test** (T-3.3, ~1 h).
5. **Decide T-4.2**: per-module 100% branch gate for routing vs. amending the plan to the enforced global 85% gate. Recommend amending with rationale — a documented decision beats an unenforced claim.
6. Update Quality Plan statuses per §3 (several "Planned" areas are further along than claimed — under-claiming is also a provenance defect).

---

*Every VERIFIED/PARTIAL verdict above cites the implementing test functions;
re-derive any row with `pytest <file>::<name>` against the stated branch.*
