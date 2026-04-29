# Architecture Decision Records — eParts Intelligent Ingestion & Attribute Prediction Platform

Project: Pimsie Supreme (CMU MSE Studio Capstone)
Format: Michael Nygard ADR template (Title, Status, Context, Decision, Consequences)

## Index

| # | Title | Status |
|---|-------|--------|
| 0001 | Adopt Pipe-and-Filter as the Primary Architectural Style | Accepted |
| 0002 | Isolate the Prediction Strategy Behind a Stable Internal Interface | Accepted |
| 0003 | Use a Hybrid Rule Engine and Semantic Similarity for Attribute Prediction | Tentative |
| 0004 | Route Confidence Decisions at the Attribute Level, Not the Record Level | Accepted |
| 0005 | Externalize the Confidence Threshold as Runtime Configuration | Tentative |
| 0006 | Enforce Idempotent PIMS Writeback via a Composite Natural Key | Accepted |
| 0007 | Use an Attribute-Row Canonical Schema for the Staging Table | Accepted |
| 0008 | Deploy the Platform as a Single Azure App Service Unit | Accepted |
| 0009 | Implement the Human Review Queue as a Persistent Database Table | Accepted |
| 0010 | Maintain an Append-Only Audit Trail of Every Pipeline Decision | Accepted |
| 0011 | Trigger Retraining Automatically on Human Review Batch Completion | Proposed |
| 0012 | Emit Stage-by-Stage Telemetry to Datadog for Drift Detection | Proposed |

## Status legend

- **Accepted** — Decision made and reflected in the architecture.
- **Tentative** — Decision made provisionally; specific parameters await empirical evidence (Refinements 1–6 in the project plan).
- **Proposed** — Decision shape is set; key sub-parameters (alert thresholds, minimum batch sizes) are not yet defined.

## Requirements traceability

Each ADR ends with a **Requirements Traceability** section listing the HLRs, FRs, DRs, QASs, constraints, scenarios, and validation tests it satisfies, drawn from **Product Specification v2.0 (April 24, 2026)**.

A consolidated bidirectional view is in [`REQUIREMENTS-TO-ADR-MAPPING.md`](REQUIREMENTS-TO-ADR-MAPPING.md), which lists every requirement in the spec and the primary + supporting ADRs that satisfy it.

## Cross-cutting traceability

- ADR-001 (pipe-and-filter) is the structural premise the rest of the ADRs build on.
- ADR-002 (PredictionServiceInterface) is the boundary that protects ADR-003 (hybrid prediction) and ADR-011 (auto-retraining) from leaking model details into the rest of the pipeline.
- ADR-004 (per-attribute routing), ADR-005 (configurable threshold), and ADR-007 (attribute-row schema) are mutually reinforcing: per-attribute routing requires the attribute-row schema and an externally tunable threshold to be operationally viable.
- ADR-006 (idempotent writeback) and ADR-009 (review queue as DB table) both depend on ADR-007's natural-key structure.
- ADR-010 (audit trail) and ADR-012 (Datadog telemetry) together provide the observability layer that ADR-011 (auto-retraining) and the drift-detection workflow depend on.
