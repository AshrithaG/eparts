# Architecture Decision Records — eParts Intelligent Ingestion & Attribute Prediction Platform

Project: Pimsie Supreme (CMU MSE Studio Capstone)
Format: Michael Nygard ADR template (Title, Status, Context, Decision, Consequences), plus a Requirements Traceability section.

**This `docs/00NN-*.md` series is the authoritative ADR set.** See "Known defect" at the foot of this page.

## Index

### Spring baseline — ADRs 0001–0012 (April 2026)

Written against **Product Specification v2.0 (24 April 2026)**. Several are now partly outdated; they are **deliberately left unedited** as the record of what the team decided in April. What changed and why is in [`ETIM-ADR-ASSESSMENT.md`](ETIM-ADR-ASSESSMENT.md).

| # | Title | Status | ETIM verdict |
|---|-------|--------|--------------|
| 0001 | Adopt Pipe-and-Filter as the Primary Architectural Style | Accepted | Valid; the ingestion→ML seam is now explicit (ADR-021) |
| 0002 | Isolate the Prediction Strategy Behind a Stable Internal Interface | Accepted | Valid; contract enriched by ADR-016 |
| 0003 | Use a Hybrid Rule Engine and Semantic Similarity for Attribute Prediction | Tentative | Narrowed by ADR-016 to the feature and value stages |
| 0004 | Route Confidence Decisions at the Attribute Level, Not the Record Level | Accepted | Extended by ADR-018 |
| 0005 | Externalize the Confidence Threshold as Runtime Configuration | Tentative | Widened by ADR-018 to class + attribute thresholds |
| 0006 | Enforce Idempotent PIMS Writeback via a Composite Natural Key | Accepted | Key superseded by ADR-017; mechanism reused |
| 0007 | Use an Attribute-Row Canonical Schema for the Staging Table | Accepted | Superseded in part by ADR-014 |
| 0008 | Deploy the Platform as a Single Azure App Service Unit | Accepted | Topology holds; substrate revisited by ADR-015 |
| 0009 | Implement the Human Review Queue as a Persistent Database Table | Accepted | Mechanism holds; ETIM context added via ADR-018/0019 |
| 0010 | Maintain an Append-Only Audit Trail of Every Pipeline Decision | Accepted | Valid; captured fields extend to the ETIM mapping |
| 0011 | Trigger Retraining Automatically on Human Review Batch Completion | Proposed | Valid; labels are now reviewer ETIM corrections |
| 0012 | Emit Stage-by-Stage Telemetry to Datadog for Drift Detection | Proposed | Valid. Datadog is the production target; Prometheus + OpenTelemetry + structlog is the local development substrate. `ETIM-ADR-ASSESSMENT.md` reads the code as a contradiction; it is a two-environment choice. |

### ETIM change — ADRs 0013–0021 (June–July 2026)

Written against **Product Specification v1.2 (28 July 2026)** — see [`product-spec-changelog.md`](product-spec-changelog.md) and [`etim-requirements-change.md`](etim-requirements-change.md).

| # | Title | Status | Built? |
|---|-------|--------|--------|
| 0013 | Establish a Release-Versioned ETIM Reference Data Layer Owned by Ingestion | Accepted | **Yes** — `models/etim.py`, `etim/loader.py`, `cli/etim.py`, Alembic `0005`; verified against the real ETIM 10.0 EI archive |
| 0014 | Emit a Source-Preserving Product + Attribute Staging Split | Accepted | **Yes** — `models/staging.py`, Alembic `0006` |
| 0015 | Target PostgreSQL Now; Defer the Azure SQL Conversion | Accepted | **Yes** — running substrate |
| 0016 | Decompose Attribute Matching into Staged ETIM Class → Feature → Value/Unit Matching | Accepted | No — designed; ML stream, EPARTS-289/290/291 |
| 0017 | Re-key the PIMS Writeback Contract on ETIM Identifiers | Accepted | No — designed; writer rework EPARTS-299 |
| 0018 | Extend Routing to ETIM Signals, with a Class-Review-First Path | Accepted | No — designed; depends on 0016 |
| 0019 | Externalize the Client Feature Policy as Per-Class Configuration | Accepted | Seam decided; **policy values blocked on client** (EPARTS-287) |
| 0020 | Pin ETIM Release 10.0 (EI) for the Project Duration | Accepted | **Yes** — C-4 in spec v1.2; release-scoping kept in the schema for provenance |
| 0021 | Formalize the Ingestion → ML Boundary as a Frozen `ExtractedInput` Record | Accepted | **Partly** — spec model, builder, Alembic `0007` merged; orchestrator wiring EPARTS-363 outstanding |

## Status legend

- **Accepted** — Decision made and reflected in the architecture. Does *not* imply the code is written; see the "Built?" column.
- **Tentative** — Decision made provisionally; specific parameters await empirical evidence.
- **Proposed** — Decision shape is set; key sub-parameters or ownership are not yet defined. (No ADR currently carries this status.)

## Requirements traceability

Each ADR ends with a **Requirements Traceability** section. ADRs 0001–0012 cite Product Specification v2.0 (24 April 2026); ADRs 0016–0021 cite Product Specification v1.2 (28 July 2026).

A consolidated bidirectional view is in [`REQUIREMENTS-TO-ADR-MAPPING.md`](REQUIREMENTS-TO-ADR-MAPPING.md) — sections 1–9 cover the v2.0 requirement set, section 10 covers the ETIM change.

## Cross-cutting traceability

- **ADR-001** (pipe-and-filter) is the structural premise the rest build on. **ADR-021** makes its most important filter boundary explicit and schema-enforced.
- **ADR-002** (`PredictionServiceInterface`) is the boundary that protects ADR-003 and ADR-011 from leaking model details. **ADR-016** decomposes what sits behind that interface without changing the interface's role.
- **ADR-004**, **ADR-005** and **ADR-007** are mutually reinforcing: per-attribute routing needs the attribute-row schema and a tunable threshold. **ADR-018** extends the routing inputs; **ADR-014** splits the schema.
- **ADR-013 → 0014 → 0016 → 0017** is the ETIM spine: load the dictionary, split evidence from interpretation, match in stages, publish keyed on the result.
- **ADR-019** (client policy) is the only decision gated on an external party, and it gates the validation half of **ADR-018**.
- **ADR-020** pins the standard to ETIM 10.0 EI and puts upgrades out of scope. `etim_release_id` stays in 0013, 0014 and 0017 for provenance, not for coexistence.
- **ADR-010** (audit trail) and **ADR-012** (telemetry) provide the observability layer that ADR-011 and drift detection depend on.

## Known defect: a colliding ADR series

`docs/adr/ADR-001-threshold-calibration.md`, `ADR-002-staging-tables.md`, `ADR-003-human-in-loop.md` and `ADR-004-per-attribute-routing.md` are an **agent-generated second series** whose numbers collide with this one while describing different decisions. `docs/adr_adr_threshold_calibration.md` is a third, thinner duplicate of the same decision.

Only `docs/00NN-*.md` is authoritative. Do not add to `docs/adr/`. Note that `.github/workflows/requirements-extraction.yml` writes generated ADRs into `docs/adr/**`, so the collision will grow until that workflow is repointed or its output is triaged into this series. This is recorded as a known artifact-hygiene defect rather than silently tolerated.
