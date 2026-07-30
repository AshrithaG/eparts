# ADR-016: Decompose Attribute Matching into Staged ETIM Class → Feature → Value/Unit Matching

## Status

Accepted

## Context

ADR-003 framed the matching problem as a single step: map a raw supplier attribute string onto a canonical attribute value, using a rule engine blended with semantic similarity (`conf_final = α·conf_rule + (1−α)·conf_embed`, α = 0.7). That framing was correct for a free-form canonical vocabulary, where every attribute is independent and there is one decision to make per attribute.

ETIM invalidates the independence assumption. Under ETIM (HLR-6, FR-9) an attribute cannot be matched at all until the product's **class** is known, because the set of legal features is a property of the class: `etim_class_feature` says which features belong to `EC…`, and `etim_class_feature_value` says which values are legal for that class-feature pair. Matching "Torque: 120 Nm" is meaningless without first deciding the product is a valve actuator, and matching it against the wrong class produces a confidently wrong answer rather than a low-confidence one.

The value side is not uniform either. ETIM feature types carry different semantics and different failure modes:

| Type | Meaning | What matching must produce |
|---|---|---|
| A | Controlled list value | an `etim_value_id` drawn from the legal set for that class-feature |
| L | Logical yes/no | a boolean |
| N | Numeric | a number **plus** a unit, converted to the ETIM-declared unit |
| R | Numeric range | a min, a max, and a unit |

A single matcher emitting one scalar `predicted_value` with one `confidence_score` cannot express "we are confident this is class EC002714 but unsure whether the torque figure is the rated or the breakaway value," which is exactly the distinction a reviewer needs. It also gives the router a single number where the routing decision now depends on several (see ADR-018).

Two alternatives were considered:

- **Keep one matcher, widen its output.** Emit class, features and values from one model call and one confidence. Cheapest change, but it hides a genuine dependency: a class error silently corrupts every downstream feature match, and there is no place to intervene between the two.
- **A per-class trained model.** One classifier per ETIM class. 5,640 classes make this untrainable at our data volume, and it would still not solve unit normalization.

## Decision

We will decompose matching into an ordered pipeline of stages, each producing its own evidence and its own confidence:

```
class matching → feature matching → value matching → unit normalization
              → ETIM validation → client-policy validation → confidence scoring
```

Each stage is a filter in the ADR-001 sense, and the whole sequence remains behind the single `PredictionServiceInterface` established in ADR-002 — this decomposition is an interface *enrichment*, not a reversal. `PredictionResult` grows to carry candidate classes with confidences, matched features, matched values with feature-type-appropriate typing, and validation status, in place of a single predicted value.

Class matching consumes class names, class descriptions, `etim_class_synonym` rows, and the correction store; feature and value matching continue to use the ADR-003 hybrid of rules plus semantic similarity over the class-restricted candidate set. **A correction store is consulted before general matching at every stage** so that a reviewer's decision on one product resolves the same mapping for later products without retraining.

Stage outputs land in `matched_product_attribute` — the interpretation table introduced by ADR-014 — which carries the ETIM identifiers, the typed normalized values (`normalized_text_value`, `normalized_numeric_value`, `normalized_range_min`/`max`, `normalized_logical_value`), and per-assignment confidence, alongside a foreign key back to the `staging_raw_attribute` evidence row.

**Implementation status: designed, not built.** The reference layer this depends on is live (ADR-013), and the evidence/interpretation tables exist (ADR-014, Alembic `0006`). The matching stages themselves are owned by the ML stream under EPARTS-289/290/291 and are not yet in the running pipeline; the pipeline currently emits source evidence only.

## Consequences

- Class errors become **visible and interceptable** instead of silently poisoning downstream matches. This is what makes the class-review-first routing path in ADR-018 possible.
- Confidence attaches **per ETIM assignment** rather than per raw attribute, which is what DR-4 and the PIMS output contract require and what a reviewer needs in order to accept a class while correcting a single feature.
- Accuracy becomes measurable against a controlled vocabulary rather than against free text: a match is right or wrong against `etim_class_feature_value`, not fuzzily similar to a gold string. This sharpens the golden test set (EPARTS-296) but also makes previously "close enough" answers count as failures, so headline accuracy will drop before it rises.
- Unit normalization becomes a first-class stage rather than a formatting detail, because type N and R features declare a unit in `etim_class_feature.UNITOFMEASID` and a value in the wrong unit is wrong, not merely unformatted.
- More stages means more places to fail and more latency per product. The mitigation is that the stages are cheap relative to the OCR/LLM extraction already in the pipeline, and each stage's output is persisted, so a failure late in the chain does not re-run the expensive early work.
- The α = 0.7 blend and the reconsideration triggers from ADR-003 carry over unchanged to the feature and value stages. ADR-003 is not superseded; it is narrowed in scope from "the matcher" to "two of the matcher's stages."
- Because the correction store is consulted first, the system's behaviour changes as reviewers work. That is deliberate, but it means matching accuracy is not reproducible from the model alone — the correction store must be snapshotted alongside any benchmark run.

## Requirements Traceability

- **Spec:** Product Specification v1.4 (29 July 2026)
- **HLRs:** HLR-6 (classify against ETIM and enrich with class/feature/value/unit identifiers); HLR-2 (the intermediate structure this reads from — mechanical cleanup only, no ETIM keying); HLR-3 (predict with confidence scores)
- **FRs:** FR-9 (match to ETIM classes, features, controlled values/units with per-assignment confidence, preserving the original value); FR-3 (confidence score per predicted attribute)
- **DRs:** DR-4 (ETIM-keyed PIMS output — consumes the identifiers this ADR produces)
- **QASs:** QAS-1 Modifiability — a new supplier format changes the parse stage only, not the matching stages
- **Scenarios:** SCEN-1 step 4 (the ML service matches attributes, then matches them to ETIM class, features and values); SCEN-2 steps 2–3 (per-assignment confidence is what routes the item to review)
- **Validation:** VAL-5 (class review precedes attribute routing) — added in spec v1.4 as the test for this ADR; **specified, not yet executable**, because these stages are designed and not built. VAL-4 covers the reference layer this ADR reads; its 10 unit tests pass, and its integration half skips without the real archive.
- **Source:** `ETIM_IMPLEMENTATION_BRIEF.md` — End-to-End Process steps 7–15, ML/AI Attribute Matching, ETIM Feature Types
- **Tickets:** EPARTS-289 (class matching), EPARTS-290 (feature matching), EPARTS-291 (value/unit matching), EPARTS-296 (golden test set); parent EPARTS-156 (ML)
- **Related ADRs:** narrows ADR-003 (hybrid rule + semantic similarity) to the feature and value stages; enriches the contract of ADR-002 (`PredictionServiceInterface`); writes into the interpretation table of ADR-014; reads the reference layer of ADR-013; feeds the routing signals of ADR-018 and the policy gate of ADR-019
