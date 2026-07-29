# ADR-018: Extend Routing to ETIM Signals, with a Class-Review-First Path

## Status

Accepted

## Context

ADR-004 established per-attribute routing: each predicted attribute is compared against a configurable confidence threshold (ADR-005), and the attribute — not the whole record — goes to auto-accept or to the human review queue. The granularity decision was right and is unchanged by this ADR.

What changed is that a single confidence-versus-threshold comparison is no longer sufficient to decide whether a value is safe to publish. After ETIM there are several independent ways for an attribute to be unfit, and only one of them is low confidence:

- The **class** may be wrong or contested. Class confidence is a distinct signal from attribute-match confidence, and it dominates: every feature match under a wrong class is wrong, no matter how confident.
- The value may be confidently matched but **invalid against ETIM** — a type A value not in the legal set for that class-feature, a type N value with no unit, a type R range with min above max.
- The value may be valid but **fail client policy** — a feature the client marks `required` for this class is missing, which blocks publish regardless of how confident everything else is (ADR-019).
- **Unit conversion may have failed**, leaving a numerically plausible figure in the wrong unit. This is the most dangerous case: high confidence, valid type, wrong magnitude.

Routing on confidence alone would auto-accept all four of these. The consequence is the one thing the project exists to prevent: wrong product data reaching PIMS, and from there a contractor's field order.

A further problem is ordering. With a flat per-attribute queue, a product whose class is uncertain generates one review item per attribute — dozens of decisions that all become void the moment the reviewer changes the class. Alternatives considered:

- **Route on confidence only, catch validity later at publish time.** Keeps routing simple, but moves the failure to a stage with no human in it, so invalid data either blocks silently or is dropped.
- **Escalate any invalid attribute to whole-record review.** Safe but wasteful: one bad attribute pulls a hundred good ones into a manual queue, which is precisely the per-record behaviour ADR-004 rejected.

## Decision

Routing keeps its per-attribute granularity and gains a **class-level stage in front of it**.

**Stage 1 — class routing.** If ETIM class confidence is below the class threshold, or the top two candidate classes are within a configured margin of each other, the *product* is routed to class review before any attribute is matched. Attribute matching for that product is deferred until a class is confirmed.

**Stage 2 — attribute routing.** Once the class is settled, each attribute is routed on the full signal set:

| Signal | Effect |
|---|---|
| Attribute match confidence below threshold | → review |
| ETIM validation failure (value not in legal set, missing unit, malformed range) | → review, regardless of confidence |
| Unit conversion failure | → review, regardless of confidence |
| Client policy `required` and value missing | → review, and blocks publish for the product |
| Client policy `not_used` | → not published, not queued |
| All checks pass and confidence above threshold | → auto-accept |

The rule that governs the combination: **validation and policy failures are not overridden by high confidence.** Confidence answers "did we read it right"; validation answers "is it a legal ETIM value"; policy answers "does the client need it". These are independent questions and a failure in any one routes to a human.

Thresholds are externalized per ADR-005, now generalized to at least two — class-selection confidence and attribute-match confidence — with per-class-feature overrides replacing the per-attribute override table.

**Implementation status: designed, not built.** The signals this routing consumes are produced by the matching stages of ADR-016 (EPARTS-289/290/291), which are not yet in the running pipeline. Routing today evaluates confidence only.

## Consequences

- The highest-leverage failure mode — a confidently wrong unit or an out-of-vocabulary value — is now caught by a deterministic check rather than by hoping the model was unsure. This directly serves the data-integrity driver behind the whole platform.
- Class-review-first collapses what would have been dozens of void attribute decisions into one class decision. Reviewer throughput (QAS-2, 10 items/minute) is protected by not queuing work that is about to be invalidated.
- Deferring attribute matching until the class is confirmed introduces a **wait state** in the pipeline: a product can sit unprocessed pending a human class decision. The staging tables (ADR-014) hold that state durably, so nothing is lost, but end-to-end latency for uncertain products is now bounded by reviewer response time rather than by compute.
- More routing inputs means more ways to be wrong about routing. Each signal must be independently observable in telemetry — class confidence distribution, validation-failure rate, unit-conversion-failure rate, missing-required-field rate — or a regression in one will be invisible inside an aggregate auto-accept rate.
- Auto-accept rate will fall relative to the ADR-004 baseline, because attributes that previously passed on confidence now also have to pass validation and policy. This is the intended trade: throughput for correctness. The rate should be reported against the pre-ETIM baseline so the drop is not misread as a regression.
- The policy signal makes routing **dependent on client configuration that does not yet exist** (ADR-019). Until the feature policy is supplied, the policy check defaults to permissive — nothing is treated as required — which means the required-field path is designed but untestable.
- ADR-004 and ADR-005 are **not edited**. Per-attribute granularity and externalized thresholds are reused as decided; this ADR extends the inputs and adds a preceding stage.

## Requirements Traceability

- **Spec:** Product Specification v1.3 (29 July 2026)
- **HLRs:** HLR-4 (human review of low-confidence predictions); HLR-6 (ETIM classification and enrichment)
- **FRs:** FR-4 (route below-threshold items to the review queue); FR-7 (authorized Ops Leads adjust the auto-acceptance threshold); FR-9 (per-ETIM-assignment confidence is the signal being routed on); FR-3 (confidence score per prediction)
- **QASs:** QAS-2 Usability — class-review-first is what keeps the reviewer at 10 items/minute by not queuing work that a class change would void
- **Scenarios:** SCEN-2 steps 2–3 (a 0.45-confidence value routes to review; under this ADR it would also route on a validation or unit failure at any confidence)
- **Validation:** VAL-2 (mock a low-confidence response; the item appears in the review queue) — extended to cover validation-failure and unit-failure routing at high confidence
- **Source:** `ETIM_IMPLEMENTATION_BRIEF.md` — Request Router, Human Review, End-to-End Process steps 13–17
- **Tickets:** EPARTS-289 (class matching and class routing), EPARTS-294 (ETIM-aware review queue); parent EPARTS-156 (ML)
- **Related ADRs:** extends ADR-004 (per-attribute routing) and ADR-005 (externalized thresholds); consumes the staged outputs of ADR-016; depends on the policy overlay of ADR-019; the review-queue contract it feeds is ADR-009
