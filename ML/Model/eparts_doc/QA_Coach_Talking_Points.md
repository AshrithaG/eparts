# QA Coach Conversation — Talking Points

| | |
|---|---|
| Purpose | One-page brief for the ML team's QA-coach conversation |
| Audience | (us) presenting to the QA / quality-assurance coach |
| Date | 2026-06-17 |
| Snapshot | 219 automated tests, all green; V1 pipeline code-complete (M1–M7) |

Read top to bottom — it's ordered the way the conversation should flow.

---

## 0. Open by reframing what kind of "LLM system" this is

**Say this first.** The coach will hear "LLM system" and expect
generative-LLM QA topics (hallucination, prompt injection, output
non-determinism, toxicity). Ours is **not** a generative system:

> "Our LLM component is a *frozen sentence-embedding model* (BGE), not a
> text generator. It only turns a product description into a 384-d
> vector. Everything downstream is classical statistics — Mahalanobis
> distance, a Gaussian confidence decay, fixed thresholds. So our QA
> looks different from generative-LLM QA, and that difference is
> actually a strength: the system is **deterministic and therefore
> testable**."

| | Generative LLM | Our system |
|---|---|---|
| LLM role | generates text | frozen encoder → vectors only |
| Output | free text | structured prediction + calibrated confidence |
| Determinism | non-deterministic (sampling) | deterministic (frozen weights, seed=42, no sampling) |
| Testability | hard | easy — *by design* |

(The generative LLMs live in the **extraction sub-team's** Layer 1 — not
our scope. We consume their output via a typed contract.)

---

## 1. The core message: we run QA at two layers

This is the spine of the whole talk — separate **code correctness** from
**model quality**:

| Layer | What it checks | How | Pass/fail? |
|---|---|---|---|
| **Code correctness** | functions behave | 219 pytest tests (unit / property / integration) | binary |
| **Model quality** | predictions are good *and* well-calibrated | held-out evaluation (M5) + calibration metrics | distributional, not binary |

A QA coach's key takeaway should be: **ML quality can't be a unit test.
We validate it separately, statistically, on held-out data.**

---

## 2. We made the ML system testable on purpose (determinism)

Most ML systems are hard to test because they're non-deterministic. We
removed that on purpose:

* Encoder weights **frozen** (no fine-tuning in V1)
* Every random op uses **seed = 42** (splits, FAISS training subset, sampling)
* **Classical math** downstream — no sampling, no temperature
* Each training run writes **immutable artifacts** (`run_<timestamp>/`, never overwritten)

→ Same input + same seed = **bit-identical output**. That's the
precondition for everything else.

---

## 3. Test types, with concrete examples

**219 tests across 18 files.** Breakdown by what they prove:

**Unit (~most of the suite)** — one function, narrow claim
- split reproducibility; part-number regex word-boundary; 2A guardrail demotes invalid values

**Property tests** — invariants that must hold for *any* input (you can't enumerate all product descriptions)
- `conf_final ∈ [0, 1]` always
- `conf_final = 1.0` **iff** exact part-number match
- every full cluster's covariance Σ⁻¹ is positive-definite
- no product appears in more than one split

**Integration** — layer boundaries
- Tier-1 exact match short-circuits the whole pipeline
- demoted rule hit doesn't contribute to fused confidence

**Principle we follow:** test the **contract** (shape, range, routing),
not specific values (e.g. NOT "this description must produce this exact
vector" — that's brittle, breaks the moment the encoder is swapped).

---

## 4. Model-quality validation — the ML-specific layer (coach will care most)

The **M5 evaluation harness** runs the full pipeline on 12,958 held-out
products (143,409 attribute samples) and reports:

* ProductType accuracy **95.74 %** (spec target ≥ 92 % — PASS)
* Attribute top-1 **60 %** / top-3 **85 %**
* **Calibration: ECE + Brier** — does "80 % confident" actually mean
  "right 80 % of the time"?
* reliability diagrams, confusion matrix, top-N failure cases

**Key point for the coach:** ML quality is *distributional*, not
pass/fail. We measure **calibration error** (is the confidence
trustworthy?), not just accuracy. A confident-but-wrong model is worse
than an uncertain-and-honest one in a human-review pipeline.

---

## 5. QA doesn't stop at deployment — drift monitoring

The M7 service computes a **drift signal** in production: KL divergence
of the live confidence distribution vs. the M5 baseline. If customers
start asking about product categories the model hasn't seen, the
distribution shifts, KL rises → alarm: "re-evaluate / recalibrate."
**Quality assurance continues at runtime.**

---

## 6. A concrete "QA caught a bug" story (tell this one)

A reviewer commented on the M6 PR: *"there's no regression test for
replay-after-snapshot."* What happened next:

1. Wrote the test they asked for → ran it on the **unfixed** code → **it failed** → proved it wasn't just a missing test, there was a real double-counting bug (replay re-applied updates already baked into the snapshot, so the cluster count drifted upward).
2. Fixed it (snapshot now rotates the audit log).
3. Re-ran → passed. Added 3 regression tests.

This shows three things at once: **code review works**, **TDD** (failing
test first), and **regression tests prevent recurrence**. 18 → 21
feedback tests; suite 216 → 219.

---

## 7. Be honest about gaps (coaches respect this more than "we test everything")

| Gap | Status |
|---|---|
| **No CI** — 219 tests run manually, locally | the biggest gap; see asks below |
| **Concurrent load test not run** — M7 needs ≥ 50 req/s; only single-thread measured | tracked |
| **No real customer data** — fixtures are synthetic (1B-derived + hand-written) | waiting on eParts |
| **Attribute top-1 = 60 %** (target 85 %) | real quality gap, not a test gap; V2 contrastive fine-tune |
| **No coverage measurement / mutation testing** | not set up yet |

---

## 8. What we want from the coach (make it a two-way conversation)

1. **CI** — we want to run the 219 tests + ruff + black + mypy on every push (GitHub Actions or Bitbucket Pipelines). Recommended setup?
2. **Coverage** — what target/metric makes sense for an ML system? Is line coverage enough, or should we look at branch/mutation?
3. **Acceptance gates as CI checks** — how to wire the spec §7.2 numeric targets (PT accuracy ≥ 0.92, ECE ≤ 0.05, …) so a regression fails the build automatically?
4. **Calibration cadence** — how often to re-measure ECE in production, and what drift-KL threshold should trip an alert?
5. **Synthetic-data realism** — until eParts delivers real samples, is LLM-generated synthetic test data a sound practice, or does it risk training-to-the-test?

---

## 9. 30-second elevator version (if time is short)

> "We run QA at two layers. Code correctness: 219 deterministic tests —
> unit, property-based invariants, integration — all green. Model
> quality: a separate held-out evaluation that measures not just
> accuracy but *calibration* (ECE/Brier), because in a human-review
> pipeline a trustworthy confidence score matters as much as the
> prediction. We made the system deterministic on purpose (frozen
> encoder, fixed seeds, classical math) so it's reproducible and
> testable — unlike a generative LLM. Our biggest gap is no CI yet, and
> that's where we'd like your help."

---

*Full detail in [`QA_Practices_and_Test_Strategy.md`](QA_Practices_and_Test_Strategy.md).*
