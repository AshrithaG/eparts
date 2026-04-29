# ADR-001: ML Confidence Threshold Calibration

**Status:** Accepted  
**Date:** 2026-03-05  
**Deciders:** Architecture Lead, Data/ML Lead  
**Traced from:** REQ-003 (Confidence Scoring), REQ-005 (Human-in-the-Loop for Low Confidence)  
**Contributing meetings:** Meeting 2026-02-05, Meeting 2026-03-05  
**Contributing sessions:** Christian 2026-02-20

---

## Context

The eParts ML pipeline extracts product attributes from vendor spec sheets. Every prediction
must carry a confidence score that determines whether it is auto-promoted to the production
catalog or routed to human review.

During Meeting 2 (Feb 05), the client emphasized that incorrect data in PIMS is worse than
missing data. POC results from Meeting 4 (Mar 05) revealed that a single global threshold
fails: product names achieve >0.92 confidence on average while technical specifications hover
around 0.65. A flat 0.80 cutoff rejects most spec predictions while rubber-stamping name
predictions that still contain errors.

## Decision

We adopt **per-attribute configurable thresholds** calibrated using **Expected Calibration
Error (ECE)** on a held-out validation set, combined with **alpha-weighted hybrid scoring**.

**Threshold Calibration.** Each attribute type maintains its own threshold in a versioned YAML
configuration file. Thresholds are recalibrated when a new model is deployed or when monitoring
ECE exceeds 0.05. Calibration uses isotonic regression to map raw outputs to well-calibrated
probabilities.

**Hybrid Scoring.** The final confidence score is:

    score = α × fuzzy_match_score + (1 − α) × ml_model_score

For structured fields like category codes, `α` is low (ML-dominant). For free-text fields like
product names, `α` is higher to leverage lexical similarity with existing catalog entries. This
provides a fallback signal when the ML model is uncertain.

**Operational Controls.** Thresholds are exposed in the review dashboard. Every change is logged
in `artifact_versions.db` for traceability. A safety floor prevents thresholds below 0.50
without ML Lead approval.

## Consequences

**Positive:**
- Attribute types with high natural accuracy are not penalized by thresholds set for harder
  attributes, reducing unnecessary review volume.
- ECE calibration ensures a 0.85 score genuinely means 85% correctness likelihood.
- Hybrid scoring provides graceful degradation if the ML model drifts.

**Negative:**
- Requires a labeled validation set per attribute type (minimum 200 examples each).
- Per-attribute thresholds add configuration complexity; misconfigured low-volume attributes
  could go undetected without monitoring alerts.
- Alpha weighting introduces a second hyperparameter per attribute to tune and document.

## Alternatives Considered

**Single Global Threshold.** One cutoff (e.g., 0.80) across all attributes. Rejected — POC
data showed a 27-point spread in mean confidence across attribute types.

**Fixed Percentile Cutoff.** Route the bottom N% to review regardless of absolute confidence.
Rejected — provides no quality guarantee; wastes reviewer time in high-accuracy periods and
leaks bad predictions in degradation periods.

**No Thresholds (Review Everything).** Rejected — at ~50,000 attributes per batch, full review
requires more hours than the current manual process, providing negative ROI.
