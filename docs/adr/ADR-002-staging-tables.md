# ADR-002: Staging Tables Before Production

**Status:** Accepted  
**Date:** 2026-02-19  
**Deciders:** Architecture Lead, Engineering Lead  
**Traced from:** REQ-010 (PIMS Integration), ARCH-004  
**Contributing meetings:** Meeting 2026-02-05, Meeting 2026-02-19, Meeting 2026-03-05  
**Contributing sessions:** Ben 2026-03-10

---

## Context

The eParts ML pipeline produces attribute predictions that must be written to the production
PIMS catalog. PIMS is the system of record feeding downstream procurement, e-commerce, and
compliance processes.

Writing predictions directly to PIMS risks corrupting production data — a miscalibrated model
or malformed vendor spec sheet could affect thousands of SKUs. The client stated in Meeting 3
(Feb 19) that incorrect catalog data has caused procurement errors before, and automation must
not increase that risk. The PIMS schema is also subject to infrequent but high-impact changes
(Risk 4). All infrastructure must be Azure-native, deployed via Bicep.

## Decision

All ML output is written to **staging tables** in Azure SQL Database. No prediction is written
directly to production PIMS. Promotion occurs only after human approval or an automated holding
period for above-threshold predictions (see ADR-003).

**Staging Schema.** Mirrors the PIMS schema with additional columns: `prediction_confidence`,
`model_version`, `source_document_id`, `review_status` (pending/approved/rejected/auto_promoted),
`reviewed_by`, `staged_at`, and `promoted_at`.

**Promotion Workflow:**
1. ML pipeline writes predictions with `review_status = pending`.
2. Above-threshold predictions enter a 24-hour hold, then auto-promote unless flagged.
3. Below-threshold predictions remain pending in the review queue.
4. Reviewers approve, reject, or edit via the dashboard.
5. A scheduled job copies approved/auto-promoted rows to PIMS via its API.

**Retention.** Staged records are retained 90 days post-promotion for rollback. Rejected records
are kept indefinitely as negative training examples.

## Consequences

**Positive:**
- Production PIMS is never exposed to unreviewed ML output.
- Staging provides a full audit trail from source document through model version to review
  decision to production write.
- PIMS schema changes can be absorbed by updating the promotion job without modifying the
  ML pipeline.
- Rejected predictions become labeled data for model retraining.

**Negative:**
- Introduces minimum 24-hour latency between prediction and production availability.
- Doubles storage during the retention window.
- The promotion job adds operational complexity — failures and partial promotions must be
  handled transactionally and monitored.

## Alternatives Considered

**Direct Production Write with Rollback.** Write to PIMS and maintain a rollback log. Rejected
because PIMS serves downstream consumers in near-real-time; by the time a bad batch is detected,
procurement systems may have acted on incorrect data. Rollback cannot undo downstream effects.

**Shadow Mode (Read-Only Comparison).** Run ML in parallel with manual entry and compare.
Rejected as permanent architecture — it requires maintaining the full manual workflow. The team
will use shadow mode during Iteration 1 as a validation technique, not as production design.

**Dual-Write (Staging + Production Simultaneously).** Write to both in a single transaction.
Rejected because it eliminates the review gate and complicates cross-system transaction management.
