# ADR-003: Human-in-the-Loop Review Workflow

**Status:** Accepted  
**Date:** 2026-03-05  
**Deciders:** Architecture Lead, Data/ML Lead, QA/Process Lead  
**Traced from:** REQ-005 (Human-in-the-Loop), REQ-003 (Confidence Scoring), ARCH-005  
**Contributing meetings:** Meeting 2026-02-19, Meeting 2026-03-05, Meeting 2026-03-19  
**Contributing sessions:** Christian 2026-02-20, Dennis 2026-03-20

---

## Context

The eParts ML pipeline automates attribute extraction, but full automation is unacceptable for
the production catalog — incorrect data causes procurement errors and compliance violations.
However, routing every prediction to review defeats ML efficiency gains. At ~50,000 attributes
per batch with reviewers Brian and Dewey, full review would exceed current manual process time.

Coach Dennis (Mar 20) flagged reviewer fatigue as a real risk: if reviewers see mostly correct
predictions, they stop paying attention. The workflow must concentrate human effort where it
has highest impact while keeping the queue challenging enough to maintain engagement.

## Decision

We implement a **confidence-calibrated review workflow** with three routing tiers.

| Tier | Condition | Action |
|------|-----------|--------|
| **Auto-promote** | Confidence ≥ threshold AND not P0 | 24-hour hold, then promoted |
| **Review queue** | Confidence < threshold OR drift-flagged | Routed to human reviewer |
| **Mandatory review** | P0 item (safety-critical, high-value, client-flagged) | Always requires human approval |

P0 classification follows business rules in the dashboard configuration — not model confidence.
Examples: safety-critical parts (brakes, electrical), items above a dollar-value threshold.

**Queue Ordering.** Ordered by expected impact, not simply lowest confidence:

    review_priority = (1 − confidence) × attribute_business_weight × batch_volume_factor

Reviewers always work the highest-impact items first.

**Reviewer Actions.** Approve (accept as-is), Edit (correct and promote — logged as training
data), Reject (discard prediction), or Escalate (flag for team discussion).

**Feedback Loop.** Every action feeds back into the ML pipeline: approvals confirm calibration,
edits become gold-labeled retraining data, and rejection patterns identify systematic failures
by attribute type, vendor, or document format.

## Consequences

**Positive:**
- Human effort focuses on predictions most likely wrong or most costly if wrong.
- P0 mandatory review provides a hard safety net regardless of model confidence.
- The feedback loop means review effort directly improves future accuracy, shrinking the
  review queue over time.
- Priority-weighted ordering mitigates reviewer fatigue.

**Negative:**
- Auto-promote with 24-hour hold adds latency for high-confidence predictions.
- Business weight configuration requires ongoing maintenance as catalog priorities evolve.
- Inconsistent reviewer behavior (liberal vs. conservative) creates noisy feedback. Inter-rater
  reliability must be monitored by QA/Process Lead.

## Alternatives Considered

**Review Everything.** Rejected — does not scale. At 50,000 attributes and ~30 seconds per
review, full review requires ~417 reviewer-hours per batch. Also causes severe fatigue.

**Review Nothing (Fully Automated).** Rejected — business risk too high. Client trust in the
ML pipeline is not yet established, and PIMS errors are downstream and difficult to reverse.
May become viable after sustained production accuracy is demonstrated.

**Random Sampling.** Review a fixed random sample (e.g., 10%) for quality monitoring. Rejected
as primary workflow because it provides no protection for individual high-risk predictions.
The team will use sampling as a supplementary monitoring metric alongside this workflow.
