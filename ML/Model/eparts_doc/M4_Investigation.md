# M4 (Layer 4) — Implementation Investigation

| | |
|---|---|
| Purpose | Fact-collection for a Layer 4 technical document (client + mentor + V2 team) |
| Method | Read-only inspection of source, config, artifacts, tests; one helper script (`data/_m4_sigma_inspect.py`) to dump `sigma_table.parquet` |
| Date | 2026-05-26 |
| Scope | Fusion + caps + routing (§4.4), σ calibration (§5.3), M6 readiness, tests, deviations |

---

## A — Fusion implementation details

### Q1 — File inventory and main entry point

Three source files under [`src/layer4_decision/`](../src/layer4_decision/):

| File | Lines | Role |
|---|---:|---|
| [`fusion.py`](../src/layer4_decision/fusion.py) | 312 | `Layer4Decision` class, caps, routing, Tier-1 short-circuit |
| [`calibration.py`](../src/layer4_decision/calibration.py) | 347 | `SigmaCalibrator`, `SigmaTable`, `ValQuery`, `brier_score`, `expected_calibration_error` |
| [`__init__.py`](../src/layer4_decision/__init__.py) | 26 | Re-exports |

CLI: [`scripts/m4_calibrate_sigma.py`](../scripts/m4_calibrate_sigma.py) (212 lines).

**Main entry point** — [`fusion.py:182`](../src/layer4_decision/fusion.py#L182):

```python
def fuse(
    self,
    x: ExtractedInput,
    rules: RuleEngineResult,
    semantic: SemanticMatcherResult | None,
    *,
    model_version: str,
    latency_ms: float,
) -> PipelineResult:
    """Return a :class:`PipelineResult` for one customer request."""
```

Satisfies the `src.contracts.Layer4Decision` Protocol.

### Q2 — `conf_final` computation

Spec §10.5 formula: `conf_final = 0.7 · conf_rule + 0.3 · conf_embed_final` (FROZEN per §6.1).

Implementation: [`fusion.py:129-131`](../src/layer4_decision/fusion.py#L129-L131):

```python
alpha = thresholds.fusion.alpha
conf_embed_final = float(top.conf_embed_final)
conf_final = alpha * conf_rule + (1.0 - alpha) * conf_embed_final
```

α is **NOT hardcoded** — pulled from `ThresholdsConfig.fusion.alpha`, sourced from [`config/thresholds.yaml:28`](../config/thresholds.yaml#L28): `alpha: 0.7  # FROZEN`. A second usage at [`fusion.py:289`](../src/layer4_decision/fusion.py#L289) (rule-hits-only fallback path) reads from the same config field.

### Q3 — Caps implementation

**PT-ambiguity cap (PT_conf < 0.60 → 0.75)** — [`fusion.py:135-140`](../src/layer4_decision/fusion.py#L135-L140):

```python
pt_cap = thresholds.fusion.pt_ambiguity_cap        # = 0.75 (thresholds.yaml:29)
band_low = thresholds.product_type_consensus.band_low   # = 0.60 (thresholds.yaml:19)

pt_capped = False
if pt_conf < band_low and conf_final > pt_cap:
    conf_final = pt_cap
    pt_capped = True
```

**Low-sample cap (cluster with N<5 → 0.70)** — [`fusion.py:142-145`](../src/layer4_decision/fusion.py#L142-L145):

```python
low_sample_cap = thresholds.clusters.low_sample_conf_cap    # = 0.7 (thresholds.yaml:24)
...
if top.low_sample and conf_final > low_sample_cap:
    conf_final = low_sample_cap
    low_sample_capped = True
```

The `top.low_sample` flag arrives from M3c's `SemanticCandidate.low_sample` field (contracts.py), which is set from `ClusterStats.low_sample` at scoring time in [`src/layer3_semantic/scoring.py`](../src/layer3_semantic/scoring.py). The chain is `centroids.parquet (column low_sample) → ClusterStore.load() → SemanticScorer._score_one_cluster() → SemanticCandidate.low_sample → fusion._fuse_one_attribute()`.

**Both caps fire — sequential `min` semantics.** Caps are applied in order (PT first, then low-sample). Each only kicks in if `conf_final` is *currently* above the cap value — so the smaller of the two values wins. With pt_cap=0.75 and low_sample_cap=0.70, after both fire conf_final becomes 0.70. Behavior verified by the explicit test `test_both_caps_fire_smaller_cap_wins` ([`tests/test_layer4_fusion.py`](../tests/test_layer4_fusion.py)). Both flags (`pt_ambiguity_capped`, `low_sample_capped`) propagate independently onto the emitted `AttributePrediction`.

### Q4 — Routing decision

Routing function — [`fusion.py:73-79`](../src/layer4_decision/fusion.py#L73-L79):

```python
def _route(conf_final: float, thresholds: ThresholdsConfig) -> Routing:
    if conf_final >= thresholds.decision.auto_process:        # = 0.85
        return Routing.AUTO_PROCESS
    if conf_final >= thresholds.decision.human_review_floor:  # = 0.50
        return Routing.HUMAN_REVIEW
    return Routing.FLAG_UNCLEAR
```

Thresholds are **config-driven**, sourced from [`config/thresholds.yaml:32-34`](../config/thresholds.yaml#L32-L34):

```yaml
decision:
  auto_process: 0.85
  human_review_floor: 0.50
```

Return type: `Routing` enum from `src.contracts` (values `AUTO_PROCESS`, `HUMAN_REVIEW`, `FLAG_UNCLEAR`). Wrapped into one `AttributePrediction` per attribute; all attributes for one query land in `PipelineResult.predictions`.

---

## B — σ calibration implementation details

### Q5 — Calibration entry script and grid-search loop

Entry script: [`scripts/m4_calibrate_sigma.py`](../scripts/m4_calibrate_sigma.py).

`val_loss = Brier + 0.5 · ECE` implementation — [`calibration.py:256-257`](../src/layer4_decision/calibration.py#L256-L257):

```python
brier, ece = self._score_at_sigma(cached, sigma)
loss = brier + self._config.lambda_cal * ece
```

`λ_cal` from [`config/calibration.yaml:30`](../config/calibration.yaml) (`lambda_cal: 0.5`).

Grid-search structure — [`calibration.py:230-273`](../src/layer4_decision/calibration.py#L230-L273):

1. **Outer**: group `ValQuery` records by `pt_id` (line 233-235).
2. **Per PT — d² cache phase** ([`_cache_d2_for_pt`](../src/layer4_decision/calibration.py#L275-L312)): for each `(query, attribute)` pair, pre-compute `cluster.mahalanobis_squared(query_vector)` against every cluster under that `(pt_id, attribute)`. Stores `_CachedSample` records with `cluster_d2` arrays + fixed `usage_priors` arrays.
3. **Per PT — σ replay phase** ([`_score_at_sigma`](../src/layer4_decision/calibration.py#L314-L334)): for each σ in `_sigma_grid`, vectorized `np.exp(-cluster_d2 * (1/(2σ²)))`, multiply by cached usage_priors, take `argmax` for top-1 prediction, compute Brier + ECE.

The `d²` is computed **once per (query, cluster) pair**; the 8-σ replay reuses it via vectorized `np.exp`. Test `test_calibrator_caches_d2_across_sigmas` ([`tests/test_layer4_calibration.py`](../tests/test_layer4_calibration.py)) asserts `mahalanobis_squared` is called exactly `n_queries × n_clusters` times, not multiplied by grid size.

**Wall time (real run, 2026-05-19 17:08, log at `data/m4_calibrate.log`):**

- Cluster store load: ~17 s
- Build 143,658 ValQuery records from val split (19,845 products): ~5 s
- **Per-PT σ grid search: 77.4 s** → 242 PTs calibrated
- Persistence: 0.01 s
- Total end-to-end: ~100 s

### Q6 — `sigma_table.parquet` contents

Path: `artifacts/v1/current/sigma_table.parquet`. Size **18,246 bytes** (~18 KB). **242 rows.** (Not 379 — only the 244 PTs that have val-split coverage produce entries, minus 2 PTs whose val attributes had no clusters under their PT.)

**Schema** (from `SigmaTable.save` in [`calibration.py:111-128`](../src/layer4_decision/calibration.py#L111-L128)):

| Column | dtype | Source |
|---|---|---|
| `pt_id` | int64 | PT identifier from 1B |
| `pt_name` | object (string) | ProductType name |
| `sigma_optimal` | float64 | σ from the configured grid that minimized `val_loss` |
| `brier_at_opt` | float64 | Brier score at the chosen σ |
| `ece_at_opt` | float64 | ECE at the chosen σ |
| `loss_at_opt` | float64 | `brier_at_opt + 0.5 · ece_at_opt` |
| `n_val_samples` | int64 | # of `(query, attribute)` pairs used for this PT |
| `n_clusters_used` | int64 | # of distinct clusters seen across all `(attribute, value)` pairs |

**σ distribution (242 PTs × 8 grid candidates):**

| σ | # PTs | % | Visual |
|---:|---:|---:|---|
| **0.50** | **102** | **42.1 %** | █████████████████████ |
| 1.00 | 12 | 5.0 % | ██ |
| 5.00 | 2 | 0.8 % | |
| 10.00 | 7 | 2.9 % | █ |
| **30.00** | **59** | **24.4 %** | ████████████ |
| 80.00 | 27 | 11.2 % | ██████ |
| 150.00 | 6 | 2.5 % | █ |
| 300.00 | 27 | 11.2 % | ██████ |

All 8 grid candidates are used by at least one PT (min=0.5, max=300). **Distribution is strongly bimodal**: 47 % of PTs land at σ ≤ 1 (low-sample-dominated regime, d² ∈ [0,4]), 49 % at σ ≥ 30 (full-cluster regime, d² ≈ 10²-10⁴). Mid-range σ values (5, 10) are rarely optimal. Median chosen σ = 10.

**Aggregate Brier / ECE at chosen σ** (from inspection script and `m4_calibrate.log`):

| | min | median | max |
|---|---:|---:|---:|
| Brier | 0.0000 | 0.1823 | 0.4579 |
| ECE | 0.0000 | 0.2446 | 0.6376 |
| Loss | 0.0000 | 0.2907 | 0.7767 |

**n_val_samples per PT**: min=1, p25=4, p50=20, p75=136, max=33,846. Heavy-tailed — half the PTs have ≤20 val samples to calibrate against.

### Q7 — Head-5 PTs

From the inspection script's join of M5's head-5 PTs with `sigma_table.parquet`:

| ProductType | pt_id | σ_optimal | n_val_samples | Brier | ECE |
|---|---:|---:|---:|---:|---:|
| KW/KWH Energy/Power Meters — Honeywell | 902 | **30.0** | 7,610 | 0.2079 | 0.2887 |
| Globe 2-Way w/ Electric Actuator | 13 | **30.0** | 5,539 | 0.2297 | 0.1141 |
| Ball 3-Way w/ Electric Actuator | 55 | **80.0** | 17,049 | 0.2507 | 0.2243 |
| Ball 2-Way w/ Electric Actuator | 1 | **30.0** | 33,846 | 0.2495 | 0.1471 |
| PIV — Pressure Independent Valves & Actuators | 388 | **30.0** | 19,608 | 0.2712 | 0.2188 |

All head-5 PTs land in the σ ∈ {30, 80} range (the full-cluster regime). Spread is narrow within head 5 — head PTs all share the high-d² Mahalanobis regime; the bimodal split visible in §Q6's full distribution shows up only when including the long-tail PTs.

---

## C — Online updates (M6)

### Q8 — M6 implementation status

Spec §4.4 / §10.7 prescribes the online μ update (`μ_new = (N · μ_old + q) / (N + 1)`) and error pushback (`μ_corrected = μ_old − λ · (q_wrong − μ_old)`, `λ = 0.01`).

**Current implementation: configuration-only stub. No code reads or applies the formulas anywhere.**

Evidence:

1. **Config exists** — [`config/thresholds.yaml:36-38`](../config/thresholds.yaml#L36-L38):
   ```yaml
   online_updates:
     pushback_lambda: 0.01   # error pushback coefficient (FROZEN)
   ```
2. **Config dataclass + loader exists** — [`src/config.py:131`](../src/config.py#L131) defines `OnlineUpdateConfig.pushback_lambda`; loader at lines 242-244 populates it.
3. **Zero consumers in `src/`** — `grep -rn "pushback_lambda\|μ_new\|mu_new\|online_update" src/` (excluding the config-loading lines above) returns no matches.
4. **Zero consumers in `scripts/`** — same grep returns no matches.
5. **One stray docstring mention** at [`fusion.py:18`](../src/layer4_decision/fusion.py#L18) — refers to "reviewers" in a comment about cap flags, unrelated to μ updates.

This is **consistent with the V1 milestone schedule** in [`eparts_doc/V1_Development_Plan.md`](V1_Development_Plan.md): M4 covers fusion + σ calibration, M6 covers online updates. The `OnlineUpdateConfig` was added during M4 as a placeholder so M6 can wire in without touching the YAML schema.

No reviewer-feedback endpoint, audit log, lock/WAL, or μ-rewrite code exists yet.

---

## D — Tests + deviations

### Q9 — M4 pytest files

Two M4-specific test files:

| File | # tests | Lines |
|---|---:|---:|
| [`tests/test_layer4_fusion.py`](../tests/test_layer4_fusion.py) | 18 | 425 |
| [`tests/test_layer4_calibration.py`](../tests/test_layer4_calibration.py) | 16 | 304 |
| **Total M4 tests** | **34** | |

**Suite-wide test count over time:**

| At milestone | Active suite size | Δ vs prior |
|---|---:|---:|
| End of M3c | 118 | — |
| End of M4 | 152 | +34 (fusion + calibration) |
| End of M5 | 182 | +30 (3 evaluation modules) |

Current total: **182** tests (verified by counting `^def test_` across all `tests/*.py` — full breakdown in the investigation script output).

**Key property tests covering V1 spec §7.2 M4 acceptance:**

| Spec property | Test |
|---|---|
| `conf_final ∈ [0, 1]` for any inputs | `test_conf_final_always_in_unit_interval` ([`test_layer4_fusion.py`](../tests/test_layer4_fusion.py)) — sweeps 5 extreme `(conf_rule, conf_embed, pt_conf)` combinations |
| `conf_final = 1.0` iff Tier-1 exact match | `test_conf_final_equals_one_iff_tier1_terminal` — explicit positive + negative cases (close-to-1 non-terminal must NOT reach 1.0) |
| Fusion formula uses α from config | `test_fusion_formula_with_alpha_07` — asserts `conf_final == 0.7·conf_rule + 0.3·conf_embed_final` to 1e-9 |
| PT_conf < 0.60 → cap 0.75 | `test_pt_ambiguity_cap_when_pt_conf_below_band_low`, `test_pt_ambiguity_cap_doesnt_lower_already_lower_score` |
| Low-sample → cap 0.70 | `test_low_sample_cap_when_top_candidate_is_low_sample` |
| Both caps fire → min wins | `test_both_caps_fire_smaller_cap_wins` |
| Routing thresholds 0.85 / 0.50 | `test_routing_auto_process_at_or_above_0_85`, `test_routing_human_review_in_band`, `test_routing_flag_unclear_below_0_50` |
| Tier-1 short-circuit | `test_tier1_terminal_emits_single_auto_processed_prediction`, `test_tier1_terminal_ignores_semantic_result` |
| Demoted rule hit doesn't contribute | `test_demoted_rule_hit_does_not_contribute` |
| d² cached across σ candidates | `test_calibrator_caches_d2_across_sigmas` — monkey-patches `mahalanobis_squared`, asserts call count is `n_queries × n_clusters`, not multiplied by `len(sigma_grid)` |
| Brier / ECE math | 4 Brier tests, 4 ECE tests including perfect-calibration, worst-case, hand-computed values, empty input |

### Q10 — Spec deviations in current M4 implementation

| # | Spec ref | Deviation | Notes |
|---|---|---|---|
| 1 | §5.3 default σ grid `{0.1, 0.3, 0.5, 1.0, 2.0, 5.0}` | **Widened to `{0.5, 1.0, 5.0, 10.0, 30.0, 80.0, 150.0, 300.0}`** — 8 candidates, max 60× larger than spec's max | Documented in [`config/calibration.yaml`](../config/calibration.yaml) header (~30 lines of rationale). Permitted under §6.2 (σ grid is tunable). Reason: spec grid empirically invalid — full-cluster d² is in the 6,500–22,700 range, σ ≤ 5 collapses conf_embed to 0 |
| 2 | §7.2 M4 "Per-PT σ table" | Output `sigma_table.parquet` covers **242 of 379** active PTs — the 135 PTs without val-split coverage receive no entry and fall back to `default_sigma=1.0` at inference time via `SemanticScorer.sigma_for` | Behavior is `default` from `SigmaTable.sigma_for(pt_id, default=1.0)` at [`calibration.py:100-103`](../src/layer4_decision/calibration.py#L100-L103). Not documented in spec as a deviation; could surface in M5 report |

**No other spec deviations in M4.** Things explicitly **NOT** deviating:

- `alpha = 0.7` — config-driven, matches §10.5.
- Cap values 0.75 and 0.70 — config-driven, match §4.4.
- Routing thresholds 0.85 / 0.50 — config-driven, match §4.4.
- Tier-1 `conf_final = 1.0` short-circuit — preserved at [`fusion.py:266-275`](../src/layer4_decision/fusion.py#L266-L275).
- Brier + ECE formula and `λ_cal = 0.5` — config-driven, match §5.3.
- ECE bin count = 10 — `reliability_bins` config, matches §5.3.

**No "magic numbers" hardcoded in M4 source.** Every threshold and coefficient resolves to a `config/thresholds.yaml` or `config/calibration.yaml` field. Spot-checked: searched `fusion.py` and `calibration.py` for `0.7`, `0.85`, `0.50`, `0.75`, `0.70`, `0.60`, `0.01`; all occurrences are either docstrings, defensive clamps (`max(0.0, ...)` and `min(1.0, ...)`), or test fixtures — not behavior-determining constants.

---

## Inventory of inputs / outputs that touch M4

**Reads:**
- `config/thresholds.yaml` (fusion + caps + routing thresholds)
- `config/calibration.yaml` (σ grid + λ_cal + bins)
- `artifacts/v1/current/centroids.parquet` + `cluster_cov.npz` (loaded as `ClusterStore`)
- `artifacts/v1/current/faiss.bin` + `ids.npy` (for embedding rehydration during calibration, indirectly via M3a `ProductIndex`)
- `data/splits/val.parquet` (M1 val split, used only during calibration)
- `the_standard_data/1A_Product_Attribute_Pairs.csv` (streamed for ValQuery construction)
- `the_standard_data/1B_Product_Master.csv` (Product_ID → PT mapping)
- `the_standard_data/2A_Values_Per_Attribute.csv` (Usage_Count prior)

**Writes:**
- `artifacts/v1/current/sigma_table.parquet` (the one M4 artifact)

**No other artifact paths touched by M4 code.**

---

*Investigation date 2026-05-26. Helper script `data/_m4_sigma_inspect.py` is a throwaway used only to dump the parquet. Raw output at `data/_m4_sigma_inspect.out.txt`. No source, config, or artifacts modified during this investigation.*
