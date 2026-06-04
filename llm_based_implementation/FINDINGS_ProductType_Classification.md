# Feasibility Finding — qwen2.5:7b ProductType Classification on Real eParts Data

**Date:** 2026-06-02
**Model:** `qwen2.5:7b-instruct` (Q4_K_M) via Ollama, local, CPU/GPU laptop
**Data:** `Client Data/Products.csv` (real eParts catalog), 2,000 products, 135 ProductTypes
**Task:** Predict a product's ProductType from its free-text description — the LLM-track
analog of the stat track's M3b "ProductType consensus" step.
**Harness:** `scripts/classify_product_types.py` (seed=42, temperature=0, reproducible)

> This is a POC feasibility artifact, per the 2026-05-28 studio direction to
> "collect artifacts with concrete reasons" rather than asserting LLM quality.
> AI-generated code — pending the QA plan's two-person review.

---

## Headline result

| Metric | Value | Reference |
|---|---|---|
| **Overall accuracy** | **64.0%** (64/100) | Stat track M3b: **94.69%** |
| Shortlist recall (retrieval ceiling) | 97.0% | — |
| Accuracy when true type was in shortlist | 66.0% | — |
| Warm latency | 0.95 s / item | Stat track: ~0.02 s / item |

Sample = 100 products drawn with seed 42 from the 2,000-row catalog. Because there
are 135 ProductTypes, each product is given a **12-candidate shortlist** built by
leave-one-out keyword retrieval (mirroring how the real Layer 3 narrows candidates
before scoring). The LLM then picks one candidate.

**A 7B local model scores ~31 points below the statistical baseline on the real
catalog's ProductType problem.**

---

## Multi-model comparison (same 100 products, shortlist=12, temp=0, seed=42)

Five local models, identical sample, identical harness — the only variable is the
model. All are Q4_K_M quantized, served by Ollama on the same laptop.

| Model | Params | Overall acc. | Acc. when in-shortlist | High-conf acc.¹ | Wrong @ conf 1.0² | sec/item |
|---|---|---|---|---|---|---|
| llama3.2:3b | 3B | 58.0% | 59.8% | 0.69 | 23 / 42 | 1.04 |
| **qwen2.5:7b** | 7B | **64.0%** | 66.0% | 0.69 | 26 / 36 | 1.15 |
| llama3.1:8b | 8B | 67.0% | 69.1% | 0.71 | 26 / 33 | 1.39 |
| **phi4** | 14B | **68.0%** | 70.1% | **0.77** | **17 / 32** | 1.40 |
| qwen2.5:14b | 14B | 63.0% | 65.0% | 0.66 | 32 / 37 | 1.36 |
| *Stat track (M3b)* | — | *94.69%* | — | — | — | *~0.02* |

Retrieval shortlist recall = **97.0%** for all (same retrieval, so it does not explain
the spread). ¹High-conf acc. = accuracy among predictions asserted at confidence ≥ 1.00.
²Wrong @ conf 1.0 = how many of the model's wrong answers were asserted with full confidence.

### What the comparison shows

- **Best local model: phi4 (14B) at 68%** — and it is also the best-calibrated (highest
  high-confidence accuracy, fewest confidently-wrong answers). llama3.1:8b is a close
  second at 67%.
- **Scaling is weak and non-monotonic.** Going 3B → 14B buys only ~10 points, and the
  largest model tested (qwen2.5:14b) *regressed* to 63% — below the 7B and 8B models —
  with the **worst** calibration (32 of 37 wrong answers asserted at confidence 1.0).
  Bigger is not reliably better here.
- **Every model is 27–37 points below the statistical baseline** (94.69%). The best local
  LLM closes only about a third of the gap to the stat track.
- **Latency is not the discriminator** — all five sit at ~1.0–1.4 s/item warm.
- **Calibration is poor across the board.** Even the best (phi4) is right only 77% of the
  time when it claims full confidence; the others are at 66–71%. No model's self-reported
  confidence is trustworthy enough to drive the ≥ 0.95 auto-process gate.

This directly answers the open question from the 2026-05-28 meeting ("larger will be
better, but by how much is unknown"): **for local quantized models up to 14B, not much —
~10 points, and not monotonically.** A frontier/Azure model is the only untested lever
that might change the conclusion, which is the bounded next experiment to fund.

---

## Why it misses — three concrete reasons (the deliverable the mentors asked for)

> The deep-dive below is for **qwen2.5:7b** (the original run). The failure *patterns*
> — granular-taxonomy confusion and over-confidence — recur across all five models.


### 1. Confidence is badly miscalibrated — the decisive finding
- **26 of 36 wrong answers were asserted with confidence = 1.00.**
- Accuracy among `conf = 1.00` predictions was only **69%**.
- The model's self-reported confidence carries almost no signal about correctness.

**Implication for eParts:** the auto-process gate (spec §1.3 requires ≥ 0.95 precision
at the 0.85 threshold) **cannot be driven by the LLM's verbalized confidence** — it
would auto-process confidently-wrong answers. This is exactly the risk the LLM plan
flagged in §5.1, now demonstrated on real data. A calibrated confidence ensemble
(logprob + self-consistency + retrieval agreement) is mandatory, not optional.

### 2. The eParts taxonomy is finer-grained than a 7B model can resolve
Almost all errors (33 of 36) were the LLM choosing the **wrong sibling type from a
shortlist that contained the right one** — not a retrieval failure. Top confusions:

| Count | True type | LLM picked |
|---|---|---|
| 4× | Pre-Packaged Relays (RIB/PAM/MR/CVR) | Power Relays |
| 3× | Enclosed Transformers | Power Supplies |
| 2× | Globe Valves | Accessories - Valves |
| 2× | General Purpose Relays | Power Relays |
| 2× | Accessories - Pneumatic Controls | Pneumatic Thermostat Covers |

The relay family (Power / General Purpose / Pre-Packaged) and the "Accessories - *"
buckets demand distinctions that a one-line description often does not make explicit.
The statistical model learns these boundaries from 1.55M training pairs; the zero-shot
LLM has only its pretraining and the description.

### 3. Over-abstention on ambiguous buckets
The model returned `none_of_these` 7 times; in **6 of those the correct type was in the
shortlist** (e.g. "Accessories - Panel Devices", "Control Cables"). These are avoidable
misses — the model declined rather than commit on generic accessory descriptions.

---

## What is NOT the problem

- **Retrieval** — shortlist recall was 97%; only 3 of 36 errors were retrieval misses.
- **Speed** — 0.95 s/item warm on this laptop (cold model load was a one-time ~130 s).
- **Output validity** — schema-constrained decoding produced 100% parseable JSON; zero
  malformed responses and zero out-of-vocabulary product types.

---

## Reading the three accuracy numbers

- `overall_accuracy` (64%) = end-to-end retrieval + LLM, the number to compare to the
  stat track.
- `shortlist_recall` (97%) = ceiling imposed by the keyword-retrieval stub. Swapping in
  the stat track's bge-small + FAISS index would raise this slightly but cannot fix the
  64%, because the bottleneck is the LLM's choice (point 2 above).
- `accuracy_when_true_in_shortlist` (66%) = the LLM's own discrimination skill once the
  answer is guaranteed to be present.

---

## Recommended next steps (cost-bounded, per the meeting)

1. **Quantify the calibration gap formally** — compute ECE on these predictions; it will
   be far above the ≤ 0.05 target. This is the strongest single artifact for the
   ML-vs-LLM comparison.
2. **Test a larger model on the same 100-item sample** — e.g. `qwen2.5:14b` locally, or a
   medium Azure model — to measure how much accuracy scales with size. The meeting noted
   the team expects improvement "but by how much is unknown"; this harness answers it for
   ~$0 locally and a bounded token spend on Azure.
3. **Add the confidence ensemble** (plan L3) and re-measure auto-process precision —
   verbalized confidence alone is disproven as a routing signal.
4. **Cost/accuracy curve** — run {3B, 7B, 14B local} × {one medium Azure model} on the
   fixed sample and plot accuracy vs. cost-per-1k-queries, the graphic the mentors
   requested.

---

## Reproduce

```powershell
ollama serve
ollama pull qwen2.5:7b-instruct
cd "LLM Based Implementation"
python scripts/classify_product_types.py --n 100 --shortlist 12 --seed 42 --temperature 0
```

Per-item results and the JSON summary are written to `artifacts/`.
