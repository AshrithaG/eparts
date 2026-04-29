# ADR-006: Enforce Idempotent PIMS Writeback via a Composite Natural Key

## Status

Accepted

## Context

The platform writes approved product attributes to PIMS staging tables on SQL Server. PIMS exposes no writeback API and provides no rollback or transactional guarantees back to the platform. Retries of a writeback operation must not produce duplicate records, because duplicates in PIMS staging propagate into wrong bills of materials for contractor orders.

Several mechanisms were considered:

- **Application-side primary key check.** Read-before-write to detect existing records.
- **Database upsert via composite natural key.** A SQL `MERGE` (or equivalent) keyed on a stable identifier matches existing rows and updates them rather than inserting duplicates.
- **Distributed transaction across the platform and PIMS.** Not feasible: PIMS is owned by a different team, has no API, and there is no distributed transaction coordinator across the trust boundary.
- **Idempotency token in PIMS.** Would require schema change in PIMS, which the platform team does not control.

The submission ID is a composite of the company identifier and the product identifier, making it stable across submissions: a new update pushed for the same company–product pair carries the same submission ID. The attribute ID is a stable canonical attribute identifier. Together, `(submission_id, attribute_id)` uniquely identify any value the platform writes. Both are generated inside the platform and stored in the staging tables before the writeback runs.

## Decision

PIMS writeback uses a composite natural key of `(submission_id, attribute_id)`, where `submission_id` is itself derived from `(company_id, product_id)`. The Publish/Sync Job (Azure Function) executes an upsert against the PIMS staging table: if a row with the same key exists, the value is updated in place; otherwise a new row is inserted. Because the submission ID is stable for a given company–product pair, pushing a new update for the same product produces the same key and overwrites the prior values rather than inserting a duplicate. The natural key is generated and stored in the platform's own staging tables before writeback, so a retry of the writeback also uses the identical key and matches the same target row.

## Consequences

- Retries of the Publish/Sync Job are safe. A network failure mid-run, a transient PIMS outage, or a redeployment that interrupts the job can be recovered by simply running the job again.
- Idempotency is enforced in application code, not in PIMS. If PIMS staging tables are altered (e.g., the natural key columns are dropped or renamed), the guarantee disappears silently. The integration test described in Refinement 4 verifies the schema before any production data is written.
- This decision depends on a structural assumption about PIMS staging that has not yet been validated. Jake at eParts has not delivered the P1-C schema. If the staging tables use wide columns (one row per record with attribute values as columns) rather than tall columns (one row per attribute), the natural key strategy needs a translation layer. If the staging tables lack columns to hold the platform's natural key, the team must either negotiate a schema addition with eParts or maintain a team-owned buffer table that holds the mapping.
- No rollback is possible. Once a row is upserted into PIMS staging, the only way to "undo" it is to write a corrected row with the same natural key. This is acceptable because every write goes through human review or auto-accept above a calibrated threshold; the system never writes silently uncertain data.
- This decision interacts with ADR-004 (per-attribute routing). The natural key is keyed on `attribute_id`, not on `record_id`, which is what enables per-attribute routing to write attributes individually as they resolve. If routing were per-record, the natural key would only need `record_id`.

## Requirements Traceability

- **HLRs:** HLR-5 (write approved data to PIMS staging)
- **FRs:** FR-8 (idempotent application-layer writeback); FR-11 (natural key: submission ID + attribute ID)
- **DRs:** DR-3 (Must — retry must not create duplicates)
- **QASs:** QAS-1 (accuracy — prevents duplicate-driven errors); QAS-4 (availability — safe retry on recovery)
- **Constraints:** C-2 (no PIMS API), C-5 (no direct production writes — writeback targets staging only)
- **Scenarios:** SCEN-1 (Step 5), SCEN-2 (Step 6)
- **Validation:** VAL-3 (upsert + no-duplicate on retry)
