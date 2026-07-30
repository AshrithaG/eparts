# ADR-009: Implement the Human Review Queue as a Persistent Database Table

> Source of truth: [`0009-implement-human-review-queue-as-database-table.md`](https://github.com/AshrithaG/eparts/blob/main/docs/0009-implement-human-review-queue-as-database-table.md) in the eparts repo. This page is a copy for reading; edit the repo, not this page.

## Status

Accepted

## Context

When the Routing Engine sends a low-confidence attribute to human review, that attribute must wait until a reviewer at eParts or Alps Controls processes it. Reviewer pace is much slower than machine pace: predictions arrive in batches measured in seconds, while reviewer decisions accumulate over hours or days. The queue must therefore decouple machine throughput from reviewer availability.

Two queue mechanisms were considered:

- **In-memory queue or message broker (e.g., Azure Service Bus).** Standard for high-throughput producer/consumer decoupling. Survives normal load patterns but adds an external dependency, requires a consumer process polling for items, and does not naturally support the spreadsheet-style batch review workflow that catalog staff already use.
- **Persistent database table in Azure SQL.** The queue is a table with `(submission_id, attribute_id, predicted_value, confidence, reason_codes, status, reviewer_id, decided_at, corrected_value)`. Reviewers query the table through eParts' existing internal review interface, which already speaks SQL.

The catalog team already accesses internal staging tables through a spreadsheet-style tool. Building a custom review UI is out of scope for the current phase. The existing internal interface reads directly from staging tables, which means the queue must be a table accessible from that tool.

The queue must also feed retraining: every reviewer decision is a labeled example, and the audit trail layer relies on durable storage of reviewer corrections.

## Decision

The Human Review Queue is implemented as a persistent table in Azure SQL Database. Low-confidence attributes are inserted with `status = 'pending'`. Reviewers access the table through eParts' existing internal review interface, edit values individually or in batch, and submit decisions by updating the `status` to `'approved'` or `'rejected'` and writing the `corrected_value`. On each decision, a row is appended to the audit trail. A notification is sent to the catalog team when items are pending and again when items are processed.

## Consequences

- Reviewer pace is fully decoupled from prediction pace. The queue can hold thousands of pending items without backpressure on the upstream pipeline.
- The queue survives App Service restarts and Prediction Service outages. In-flight reviews are preserved across deployments. This directly supports QA-4 (availability).
- The queue is the persistent store for labeled corrections. The retraining pipeline reads from the audit trail (which captures the history of queue decisions) without coordinating with a separate label store.
- The schema of the queue table is a coupling point with eParts' existing internal review interface. Any change to column names, types, or status values requires coordination with the eParts engineering team. This is a recorded constraint on schema evolution.
- Rejected items are not silently dropped. A rejection writes the corrected value back to the queue row with `status = 'rejected'`, appends to the audit trail, and triggers a notification. The corrected value flows into the labeled correction store for retraining.
- The queue is not a true message broker, so it does not provide push-style notification, dead-letter queues, or consumer load balancing. These features are not needed because there is no automated consumer; the consumer is the catalog team.
- If a custom review UI is built in a future phase, Auth0 (the eParts identity provider per the SOW) integrates at the UI layer and reads from the same queue table. The queue's stable schema is what makes that future UI buildable without changes to the ingestion, prediction, or writeback components.

## Requirements Traceability

- **HLRs:** HLR-4 (persistent Human Review Queue)
- **FRs:** FR-4 (queue is the destination for low-confidence attributes); FR-5 (queue retains prediction, confidence, source ref, status); FR-10 (persistent and queryable)
- **QASs:** QAS-4 (queue survives Prediction Service outages)
- **Constraints:** C-8, DC-2 (queue's stable schema accommodates a future Auth0-gated UI without changes elsewhere)
- **Scenarios:** SCEN-2 (Steps 3–5)
- **Validation:** VAL-2 (item appears in Human Review Queue)
