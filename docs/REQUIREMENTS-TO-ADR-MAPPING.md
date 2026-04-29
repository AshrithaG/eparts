# Requirements-to-ADR Traceability Matrix

This document maps every requirement, constraint, quality attribute scenario, operational scenario, and validation test from the **Product Specification v2.0 (April 24, 2026)** to the Architecture Decision Records that satisfy or constrain it.

Each entry identifies which ADRs are *primary* (the decision that directly addresses the requirement) and which are *supporting* (decisions that the requirement also depends on).

---

## 1. High-Level Requirements (HLRs)

| ID | Requirement | Primary ADRs | Supporting ADRs |
|---|---|---|---|
| HLR-1 | Ingest from diverse supplier formats (Email, SFTP, CSV, PDF) | ADR-001 (pipe-and-filter establishes Ingestion Gateway as a distinct filter) | ADR-008 (App Service hosts the polled SFTP/email/HTTPS inbound channels) |
| HLR-2 | Normalize ingested data into a standardized intermediate structure | ADR-007 (attribute-row canonical schema is the standardized structure) | ADR-001 (Normalization is a separate filter between ingestion and prediction) |
| HLR-3 | Predict attributes and assign confidence scores using ML | ADR-003 (hybrid prediction produces values + confidence) | ADR-002 (PredictionServiceInterface is the contract); ADR-011 (retraining keeps the model current) |
| HLR-4 | Maintain a persistent Human Review Queue for low-confidence predictions | ADR-009 (review queue as persistent DB table) | ADR-004 (per-attribute routing determines what enters the queue); ADR-005 (configurable threshold determines what counts as low-confidence) |
| HLR-5 | Write approved data to PIMS staging tables for downstream reconciliation | ADR-006 (idempotent writeback via composite natural key) | ADR-008 (Publish/Sync Job runs as a timer-triggered Azure Function) |

---

## 2. Functional Requirements (FRs)

| ID | Requirement | Primary ADRs | Supporting ADRs |
|---|---|---|---|
| FR-1 | Ingestion Gateway shall create ingestion record (supplier ID, timestamp, source) on SFTP/Email receipt | ADR-001 (Ingestion Gateway as a distinct filter) | ADR-007 (ingestion record stored in canonical schema); ADR-008 (App Service hosts the gateway) |
| FR-2 | Normalize heterogeneous supplier inputs into canonical schema before prediction | ADR-007 (attribute-row canonical schema) | ADR-001 (normalization filter precedes prediction filter) |
| FR-3 | Generate predictions per-attribute with confidence scores | ADR-003 (hybrid prediction emits per-attribute confidence); ADR-004 (per-attribute routing requires per-attribute scoring) | ADR-002 (PredictionServiceInterface defines the per-attribute contract) |
| FR-4 | Route below-threshold attributes to the persistent Human Review Queue | ADR-004 (per-attribute routing); ADR-005 (configurable threshold) | ADR-009 (queue is the destination) |
| FR-5 | Queue retains prediction, confidence, source file reference, review status | ADR-009 (review queue schema) | ADR-010 (audit trail captures the same fields for history) |
| FR-6 | Log every auto-accept, approval, correction, rejection in append-only audit trail | ADR-010 (append-only audit trail) | — |
| FR-7 | Configurable confidence thresholds (calibration TBD) | ADR-005 (externalized threshold as configuration) | ADR-004 (per-attribute routing makes per-attribute thresholds possible) |
| FR-8 | Write approved attributes to PIMS staging using idempotent application-layer writeback | ADR-006 (idempotent writeback via composite natural key) | ADR-008 (Publish/Sync Job is the writeback runtime); ADR-007 (canonical schema feeds the upsert) |
| FR-9 | Routing Engine makes per-attribute decisions using configurable thresholds | ADR-004 (per-attribute routing); ADR-005 (configurable threshold) | — |
| FR-10 | Human Review Queue shall be persistent and queryable | ADR-009 (queue as persistent DB table is queryable via SQL) | ADR-008 (Azure SQL Database hosts the queue) |
| FR-11 | Writeback idempotent via natural key (submission ID + attribute ID) | ADR-006 (composite natural key) | ADR-007 (attribute-row schema makes attribute-level natural key meaningful) |
| FR-12 | Emit confidence distributions, correction rates, routing decisions, pipeline metrics to Datadog | ADR-012 (stage-by-stage Datadog telemetry) | ADR-010 (audit trail is the durable backing source for these metrics) |
| FR-13 | Archive raw supplier files in Azure Blob Storage for traceability | ADR-008 (deployment topology specifies Blob Storage for raw file archive) | ADR-010 (audit trail references the archived file) |

---

## 3. Derived Requirements (DRs)

| ID | Requirement | Primary ADRs | Supporting ADRs |
|---|---|---|---|
| DR-1 (Must) | Archive raw supplier files in Azure Blob Storage for traceability | ADR-008 (Blob Storage is part of the deployment topology) | ADR-010 (audit trail entries reference archived files) |
| DR-2 (Future / TBD) | Corrected data from review queue logged for future retraining and offline model improvement | ADR-010 (audit trail captures corrections as labeled examples); ADR-011 (retraining pipeline consumes them) | ADR-009 (queue is where corrections originate); ADR-002 (interface contract is preserved across retraining) |
| DR-3 (Must) | Writeback must be idempotent; retry must not create duplicates | ADR-006 (idempotent writeback via composite natural key) | — |

---

## 4. Quality Attribute Scenarios (QASs)

| ID | Attribute | Primary ADRs | Supporting ADRs |
|---|---|---|---|
| QAS-1 | Accuracy — ≥95% auto-accepted attributes correct; no incorrect records reach PIMS without review | ADR-004 (per-attribute routing keeps review volume proportional to risk); ADR-005 (configurable threshold is the accuracy lever); ADR-006 (idempotency prevents mechanical duplication errors) | ADR-003 (hybrid prediction provides the confidence signal); ADR-009 (review queue is the gate before PIMS); ADR-012 (telemetry detects accuracy drift) |
| QAS-2 | Modifiability — model swap localized to prediction package | ADR-002 (PredictionServiceInterface) | ADR-001 (pipe-and-filter style enables filter replacement); ADR-011 (retraining swaps model versions through the same interface) |
| QAS-3 | Modifiability — new product category supported without changing pipeline structure | ADR-007 (attribute-row schema; new categories are data, not schema migrations) | ADR-001 (filter sequence unchanged across categories); ADR-002 (prediction strategy retrained behind stable interface) |
| QAS-4 | Availability — zero data loss during Prediction Service outage | ADR-009 (persistent review queue survives outages); ADR-008 (Azure SQL holds staging tables that buffer in-flight data) | ADR-001 (staging tables between filters act as checkpoints); ADR-006 (idempotent writeback enables safe retry on recovery) |
| QAS-5 | Monitorability — drift detected before accuracy drops below QAS-1 | ADR-012 (Datadog telemetry from each stage); ADR-010 (audit trail is the durable source for drift signals) | ADR-011 (correction rates feed retraining as well as drift detection) |

---

## 5. System Constraints (C-1 to C-8)

| ID | Constraint | Primary ADRs | Supporting ADRs |
|---|---|---|---|
| C-1 | Azure deployment using managed services | ADR-008 (single Azure App Service unit; Azure SQL; Azure Blob; Azure Function) | — |
| C-2 | No PIMS API; integrate via staging tables | ADR-006 (idempotent writeback via natural key, application-layer enforced because no API/rollback) | ADR-008 (Publish/Sync Job uses pyodbc across the trust boundary) |
| C-3 | Python backend for ML | ADR-008 (single Python Azure App Service); ADR-002 (Python `PredictionServiceInterface`) | ADR-003 (hybrid implementation in Python); ADR-011 (retraining job in the Python prediction package) |
| C-4 | Phase scope: valves and actuators only initially | ADR-007 (attribute-row schema designed so category expansion is a data change, not a structural one) | ADR-003 (hybrid approach tolerates the small initial labeled set typical of phase scope) |
| C-5 | No direct production writes; use staging | ADR-006 (writeback targets staging tables only) | ADR-009 (review queue mediates before any approval); ADR-010 (audit trail records every staging write) |
| C-6 | No pricing in ML pipeline | (System-wide scope rule; not specifically addressed by any single ADR — ADR-007's canonical schema simply excludes pricing attributes) | ADR-007 (canonical schema scope) |
| C-7 | Capstone timeline | ADR-008 (single deployment unit chosen specifically because microservices exceed team capacity); ADR-002 (internal interface chosen over REST microservice for the same reason) | ADR-001 (pipe-and-filter mirrors existing manual workflow, reducing risk and rework) |
| C-8 | Auth0 stretch goal for RBAC | ADR-009 (review queue is a DB table with stable schema; Auth0-gated UI would read from it without changes elsewhere) | — |

---

## 6. Design Constraints (DC-1 to DC-3)

| ID | Constraint | Primary ADRs | Supporting ADRs |
|---|---|---|---|
| DC-1 | Python-based backend | ADR-008 (Python on Azure App Service); ADR-002 (Python interface) | ADR-003, ADR-011 (Python prediction and retraining) |
| DC-2 | Auth0 negotiable, stretch goal | ADR-009 (queue schema stable enough to plug an Auth0-gated UI on top later) | — |
| DC-3 | Raw supplier files archived in Azure Blob Storage | ADR-008 (Blob Storage in deployment topology) | ADR-010 (audit trail references archived files) |

---

## 7. Operational Scenarios (SCEN-1, SCEN-2)

| ID | Scenario | ADRs Exercised |
|---|---|---|
| SCEN-1 | End-to-end ingestion happy path: supplier upload → ingestion record → normalization → high-confidence prediction → auto-accept → PIMS staging | ADR-001 (filter sequence); ADR-007 (canonical schema for normalization); ADR-003 (prediction with confidence); ADR-004 (per-attribute routing decision); ADR-005 (threshold comparison); ADR-006 (idempotent writeback); ADR-008 (App Service + Publish/Sync Function); ADR-010 (audit trail entries at each stage); ADR-012 (telemetry at each stage) |
| SCEN-2 | Low-confidence human-in-the-loop: messy PDF → low-confidence prediction → review queue → reviewer correction → idempotent writeback | ADR-001 (filter sequence); ADR-003 (hybrid prediction emits low confidence with reason codes); ADR-004 (per-attribute routing of the low-confidence attribute only); ADR-005 (threshold comparison); ADR-009 (review queue holds the item); ADR-010 (correction recorded in audit trail and flagged as labeled example); ADR-011 (correction feeds next retraining cycle); ADR-006 (idempotent writeback of corrected value) |

---

## 8. Validation Requirements (VAL-1 to VAL-3)

| ID | Validation Test | ADRs Validated |
|---|---|---|
| VAL-1 | Ingestion trigger: file upload → ingestion record in DB within 30s | ADR-001 (Ingestion Gateway as filter); ADR-008 (App Service receiving inbound); ADR-007 (canonical schema persists ingestion record) |
| VAL-2 | Routing logic: mock ML response with Conf=0.2 → item appears in Human Review Queue | ADR-004 (per-attribute routing); ADR-005 (configurable threshold); ADR-009 (persistent review queue) |
| VAL-3 | PIMS integration: approve item → upsert into PIMS staging; retry does not duplicate | ADR-006 (idempotent writeback via composite natural key); ADR-008 (Publish/Sync Function performs the upsert) |

---

## 9. Coverage Check

Every requirement, constraint, scenario, and validation test in the spec maps to at least one ADR.

ADRs that are not directly traced from any single FR/HLR but support the spec's overall architecture:

- **ADR-001 (pipe-and-filter)** is the structural premise of Section 2 ("System Architecture") in the spec ("The system follows a pipe-and-filter pipeline architecture..."). It is the architectural decision that enables every functional requirement that decomposes the pipeline into stages.
- **ADR-002 (PredictionServiceInterface)** is the formal mechanism behind QAS-2's response ("...added behind the existing PredictionServiceInterface..."), which is the only place the spec names the interface.
- **ADR-011 (auto-retraining)** addresses DR-2, which the spec marks Future/TBD. The ADR is `Proposed` rather than `Accepted` because the requirement itself is future-scoped.
- **ADR-012 (Datadog telemetry)** addresses FR-12 and QAS-5 directly; thresholds remain unspecified pending Refinement 6.

ADRs derived from the architecture report that the spec does *not* mention explicitly:

- **ADR-007 (attribute-row canonical schema)** — the spec mentions "canonical schema" (FR-2, glossary) but does not specify its shape. The ADR records the structural decision behind that schema.
- **ADR-008 (single Azure App Service)** — the spec calls out hosting on Azure App Service (Section 3.1) but does not justify the single-unit topology. The ADR records the alternatives considered and why microservices were rejected.
- **ADR-010 (append-only audit trail)** — FR-6 requires the audit trail; the ADR records the append-only design and the rationale for keeping it as the system of record behind ADR-012's dashboards.
