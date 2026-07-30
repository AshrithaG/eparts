# Architecture Decision Records

21 ADRs. **The repo is the source of truth** — every row below links to the
file in `eparts/docs/`. This page is a reading copy, so edit the repo rather than the
page, or the two will drift.

ADRs 0001–0012 are the spring baseline and are deliberately left unedited: they record
what we believed in April. ETIM decisions supersede them *forward*, by reference, in
0013–0021. Where a spring ADR is affected but not superseded, the change-impact analysis
is in [`ETIM-ADR-ASSESSMENT.md`](https://github.com/AshrithaG/eparts/blob/main/docs/ETIM-ADR-ASSESSMENT.md).

Requirement IDs cited by 0016–0021 resolve against Product Specification v1.4; the
forward and backward traces are in [`REQUIREMENTS-TO-ADR-MAPPING.md`](https://github.com/AshrithaG/eparts/blob/main/docs/REQUIREMENTS-TO-ADR-MAPPING.md).

| ADR | Decision | Status |
|---|---|---|
| [0001](https://github.com/AshrithaG/eparts/blob/main/docs/0001-adopt-pipe-and-filter-architectural-style.md) | Adopt Pipe-and-Filter as the Primary Architectural Style | Accepted |
| [0002](https://github.com/AshrithaG/eparts/blob/main/docs/0002-isolate-prediction-strategy-behind-stable-interface.md) | Isolate the Prediction Strategy Behind a Stable Internal Interface | Accepted |
| [0003](https://github.com/AshrithaG/eparts/blob/main/docs/0003-use-hybrid-rule-engine-and-semantic-similarity.md) | Use a Hybrid Rule Engine and Semantic Similarity for Attribute Prediction | Tentative |
| [0004](https://github.com/AshrithaG/eparts/blob/main/docs/0004-route-confidence-decisions-at-attribute-level.md) | Route Confidence Decisions at the Attribute Level, Not the Record Level | Accepted |
| [0005](https://github.com/AshrithaG/eparts/blob/main/docs/0005-externalize-confidence-threshold-as-configuration.md) | Externalize the Confidence Threshold as Runtime Configuration | Tentative |
| [0006](https://github.com/AshrithaG/eparts/blob/main/docs/0006-enforce-idempotent-pims-writeback-via-natural-key.md) | Enforce Idempotent PIMS Writeback via a Composite Natural Key | Accepted |
| [0007](https://github.com/AshrithaG/eparts/blob/main/docs/0007-use-attribute-row-canonical-schema.md) | Use an Attribute-Row Canonical Schema for the Staging Table | Accepted |
| [0008](https://github.com/AshrithaG/eparts/blob/main/docs/0008-deploy-platform-as-single-azure-app-service-unit.md) | Deploy the Platform as a Single Azure App Service Unit | Accepted |
| [0009](https://github.com/AshrithaG/eparts/blob/main/docs/0009-implement-human-review-queue-as-database-table.md) | Implement the Human Review Queue as a Persistent Database Table | Accepted |
| [0010](https://github.com/AshrithaG/eparts/blob/main/docs/0010-maintain-append-only-audit-trail.md) | Maintain an Append-Only Audit Trail of Every Pipeline Decision | Accepted |
| [0011](https://github.com/AshrithaG/eparts/blob/main/docs/0011-trigger-retraining-automatically-on-batch-completion.md) | Trigger Retraining Automatically on Human Review Batch Completion | Proposed |
| [0012](https://github.com/AshrithaG/eparts/blob/main/docs/0012-emit-stage-by-stage-telemetry-to-datadog.md) | Emit Stage-by-Stage Telemetry to Datadog for Drift Detection and Operational Monitoring | Proposed |
| [0013](https://github.com/AshrithaG/eparts/blob/main/docs/0013-establish-etim-reference-data-layer.md) | Establish a Release-Versioned ETIM Reference Data Layer Owned by Ingestion | Accepted |
| [0014](https://github.com/AshrithaG/eparts/blob/main/docs/0014-emit-source-preserving-product-attribute-staging-split.md) | Emit a Source-Preserving Product + Attribute Staging Split | Accepted |
| [0015](https://github.com/AshrithaG/eparts/blob/main/docs/0015-target-postgresql-now-defer-azure-sql.md) | Target PostgreSQL Now; Defer the Azure SQL Conversion | Accepted |
| [0016](https://github.com/AshrithaG/eparts/blob/main/docs/0016-decompose-matching-into-staged-etim-class-feature-value-stages.md) | Decompose Attribute Matching into Staged ETIM Class → Feature → Value/Unit Matching | Accepted |
| [0017](https://github.com/AshrithaG/eparts/blob/main/docs/0017-rekey-pims-writeback-contract-on-etim-identifiers.md) | Re-key the PIMS Writeback Contract on ETIM Identifiers | Accepted |
| [0018](https://github.com/AshrithaG/eparts/blob/main/docs/0018-extend-routing-to-etim-signals-with-class-review-first.md) | Extend Routing to ETIM Signals, with a Class-Review-First Path | Accepted |
| [0019](https://github.com/AshrithaG/eparts/blob/main/docs/0019-externalize-client-feature-policy-as-per-class-configuration.md) | Externalize the Client Feature Policy as Per-Class Configuration | Accepted |
| [0020](https://github.com/AshrithaG/eparts/blob/main/docs/0020-pin-etim-release-10-0-for-the-project-duration.md) | Pin ETIM Release 10.0 (EI) for the Project Duration | Accepted |
| [0021](https://github.com/AshrithaG/eparts/blob/main/docs/0021-formalize-ingestion-to-ml-boundary-as-frozen-extracted-input-record.md) | Formalize the Ingestion → ML Boundary as a Frozen `ExtractedInput` Record | Accepted |

---
