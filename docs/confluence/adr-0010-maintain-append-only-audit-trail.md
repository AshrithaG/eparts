# ADR-010: Maintain an Append-Only Audit Trail of Every Pipeline Decision

> Source of truth: [`0010-maintain-append-only-audit-trail.md`](https://github.com/AshrithaG/eparts/blob/main/docs/0010-maintain-append-only-audit-trail.md) in the eparts repo. This page is a copy for reading; edit the repo, not this page.

## Status

Accepted

## Context

The platform automates a workflow that previously required human judgment at every step. Two needs follow from this:

1. **Compliance and traceability.** When a wrong product attribute reaches PIMS, eParts needs to determine why: which model version produced the prediction, what confidence the model emitted, whether a reviewer saw the item, and what the reviewer's decision was. Without this trail, root cause analysis is impossible.
2. **Model improvement.** The retraining pipeline (described in the MLOps section of the report) depends on labeled corrections. Reviewer decisions are the primary source of labels. The system must capture the original prediction, the original confidence, the source supplier, and the corrected value as a durable record.

Quality attribute QA-5 (Monitorability) is rated High/High and depends on having a record of every routing and review decision over time so that drift in correction rates can be detected.

A mutable record (overwriting the prediction with the corrected value) would satisfy the immediate writeback need but lose the history needed for audit and retraining. An append-only log preserves both.

## Decision

Every pipeline decision is recorded as a row in an append-only audit trail table in Azure SQL Database. Decisions captured are: auto-accept by the Routing Engine, approval by a reviewer, correction by a reviewer (with the corrected value alongside the original prediction), and rejection by a reviewer. Each row contains the submission ID, attribute ID, source supplier, model version, original predicted value, confidence score, threshold value at decision time, final decision, decided value, decision actor (system or reviewer ID), and timestamp. Rows are never updated or deleted.

## Consequences

- Every value written to PIMS is traceable back to the prediction, the confidence, the threshold, and the reviewer (if any) that produced it.
- The audit trail is the source of truth for retraining. Corrections where the reviewer's value differed from the model's prediction are flagged as labeled training examples and read by the retraining job (ADR-011).
- The model version recorded on each row is essential for retraining safety. When a new model version is promoted, the audit trail allows the team to compare correction rates before and after promotion as a check on regression.
- The audit trail is the basis for drift detection in Datadog (ADR-012). Per-attribute confidence distributions and reviewer correction rates are computed from this table.
- Append-only growth is unbounded. The table will require a retention policy (cold storage to Azure Blob after some period) once production volumes are observed. This is operationally acceptable in the current phase because volumes are low.
- The audit trail is internal to the platform. PIMS does not see it. If PIMS needs an audit record alongside a value, the writeback service includes audit metadata in the upsert; the platform's internal audit trail is the canonical record.
- Reviewer privacy: the reviewer ID is recorded. This is acceptable under eParts' internal policies because the catalog team is salaried staff acting in their official capacity. If the audit trail were ever exposed externally, reviewer IDs would need to be redacted.

## Requirements Traceability

- **FRs:** FR-6 (log every auto-accept, approval, correction, rejection); FR-12 (audit trail backs telemetry signals)
- **DRs:** DR-2 (Future/TBD — corrected data logged for retraining)
- **QASs:** QAS-5 (audit trail is the durable source for drift signals)
- **Scenarios:** SCEN-2 (Step 5 — correction logged)
