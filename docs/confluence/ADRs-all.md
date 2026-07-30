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
## ADR-001: Adopt Pipe-and-Filter as the Primary Architectural Style
### Status

Accepted

### Context

eParts Services LLC ingests heterogeneous supplier catalogs (CSV, PDF, email attachments, SFTP drops, direct uploads) into PIMS through a manual workflow currently absorbing roughly 4.5 FTEs across eParts and Alps Controls. The new platform must transform raw supplier files into validated PIMS records while keeping data integrity high, because incorrect product data propagates into contractor field orders.

The transformation is fundamentally linear: parse → normalize → predict → route → review/auto-accept → write back. Each stage operates on the output of the previous one, and stages have different resource profiles (parsing is I/O-bound, prediction is CPU/memory-bound, review is human-bound).

Several architectural styles were considered:

- **Event-driven architecture** would introduce a message broker and asynchronous coordination. Supplier catalogs arrive in discrete batches rather than continuous streams, so the complexity is not justified.
- **Microservices** would require container orchestration and distributed tracing infrastructure beyond what a five-person capstone team can sustain.

The team is five people working from Spring through Fall 2026, so operational simplicity is a binding constraint.

### Decision

We will structure the platform as a pipe-and-filter system. Independent filters (Ingestion Gateway, Normalization, Prediction Service, Routing Engine, Review/Auto-accept paths, Writeback) communicate through typed data channels. The pipeline is linear with one branch at the Routing Engine where confidence-based routing splits high-confidence attributes (auto-accept) from low-confidence attributes (human review); both paths merge before writeback.

![Pipe-and-Filter Architecture](../diagrams/pipe-filter-architecture.png)

### Consequences

- Each filter can be replaced or evolved independently because filters communicate only through defined data contracts. The Prediction Service can be swapped without touching upstream parsing or downstream writeback (supports QA-2).
- Adding a new product category requires extending the canonical schema and retraining; it does not require changing the filter sequence (supports QA-3).
- Staging tables placed between filters act as checkpoints: a failure at any stage does not lose data already processed upstream (supports QA-4 availability).
- The known weakness of pipe-and-filter is error detection and recovery across the pipeline. We mitigate this with persistent staging tables between stages and idempotent writeback, but cross-stage transactional guarantees are not provided.
- The branch at the Routing Engine departs from a strictly linear pipeline. The two paths must merge before writeback, which introduces merge logic in the writeback service (further explored in ADR-005).
- The architecture mirrors the existing manual workflow stage-for-stage, reducing the risk that the system solves the wrong problem and easing communication with the catalog team.

### Requirements Traceability

- **HLRs:** HLR-1 (multi-format ingestion), HLR-2 (normalization to standard structure)
- **FRs:** FR-1, FR-2 (filter decomposition makes ingestion and normalization distinct stages)
- **QASs:** QAS-2, QAS-3 (style enables filter-level replacement); QAS-4 (staging tables between filters act as checkpoints)
- **Constraints:** C-7 (capstone timeline — pipe-and-filter mirrors existing manual workflow, minimizing rework risk)
- **Scenarios:** SCEN-1, SCEN-2 (the filter sequence is the spine of both scenarios)
- **Validation:** VAL-1 (Ingestion Gateway is the first filter)

---

## ADR-002: Isolate the Prediction Strategy Behind a Stable Internal Interface
### Status

Accepted

### Context

Model selection for the attribute prediction component is unresolved through Phase 2. The team is currently using a hybrid rule + semantic-similarity approach (ADR-003) but expects to evaluate alternatives such as DistilBERT or CatBoost as labeled data accumulates. Quality attribute QA-2 (Modifiability — model swap) is rated High importance / Medium difficulty and explicitly requires that swapping the prediction strategy not ripple into the Routing Engine, Writeback, or any other component.

Three isolation mechanisms were considered:

- **Internal abstract interface** in the same Python application. A swap is a new class plus a configuration change; one redeployment.
- **REST microservice** running the Prediction Service in a separate Azure Container App. Enables independent deployment, canary rollouts, and GPU-backed inference, but adds container orchestration, health checks, service authentication, and distributed tracing.
- **Message queue (Azure Service Bus)** with broker-mediated communication. Two queues introduced; retry and dead-letter offloaded to Service Bus. Suits near-real-time ingestion with multiple consumers.

The current phase processes supplier catalogs in discrete batches and has a single downstream consumer (the Routing Engine). The team does not need canary deployments or GPU inference during the capstone phase. A network boundary between filters would add operational complexity disproportionate to team capacity.

### Decision

We will define `PredictionServiceInterface` as a Python abstract interface that accepts normalized records and returns predictions with per-attribute confidence scores. Concrete implementations (`CatBoostPredictor`, `DistilBERTPredictor`, the current hybrid implementation) live inside the `prediction` package and are selected at startup via configuration. The Routing Engine and all other downstream components depend only on `PredictionResult`, a plain data class, and never on any model-specific type.

### Consequences

- Replacing the prediction strategy is a localized change: a new class in the `prediction` package plus a configuration change. Nothing in `routing`, `writeback`, `review`, or `audit` changes.
- The interface contract — `PredictionResult` with per-attribute confidence — must be defined before the model is finalized. The team must avoid leaking model-specific types (logits, embedding vectors, classifier probabilities) into adjacent packages.
- Retraining and model promotion (described in the MLOps pipeline) operate inside the `prediction` package boundary. The interface does not change when a new model version is promoted, so the Routing Engine sees the prediction service as unchanged.
- This decision does not enable canary deployments or side-by-side model evaluation in production. If the system is later handed off to a larger eParts team that requires those capabilities, the prediction package will need to be extracted into a REST microservice. The module boundaries are drawn deliberately so that this transition is adding network serialization at an existing boundary, not a rewrite.

### Requirements Traceability

- **HLRs:** HLR-3 (predict with confidence — implementation choice deferred behind interface)
- **FRs:** FR-3 (per-attribute prediction contract)
- **QASs:** QAS-2 (model swap localized to prediction package — this ADR is the named mechanism in the QAS response)
- **Constraints:** C-3, DC-1 (Python interface); C-7 (internal interface chosen over REST microservice for capstone timeline)
- **Related ADRs:** ADR-003 (concrete implementation behind this interface); ADR-011 (retraining promotes new versions through this interface)

---

## ADR-003: Use a Hybrid Rule Engine and Semantic Similarity for Attribute Prediction
### Status

Tentative

### Context

The Prediction Service must map raw supplier text to canonical attribute values and emit per-attribute confidence scores that the Routing Engine can compare against a threshold. Three properties matter: accuracy under data scarcity, explainability for the catalog team, and ability to handle free-text inputs that rules cannot anticipate.

The team targets approximately 200 labeled examples for the initial training set, but a calibrated pure-ML classifier typically needs around 830 examples to produce well-behaved confidence scores. eParts has stated an explainability requirement: catalog reviewers need to understand why an item was routed to review.

Three alternatives were considered:

- **Pure rules.** Deterministic and fully explainable, but estimated coverage is only 40–60% of supplier inputs because suppliers use inconsistent terminology that rules cannot enumerate.
- **Pure ML classifier.** Handles unseen text well, but with the available labeled data the confidence scores are not well-calibrated. Confidence scores are also opaque, undermining the explainability requirement.
- **Hybrid: rules first, semantic similarity (TF-IDF + cosine) for unmatched inputs.** Rules give a high-precision fallback when data is scarce; the semantic layer covers free-text inputs the rules miss. Reason codes can be attached to low-confidence items.

A weighted decision matrix scored the hybrid approach highest (2.50) against pure rules (1.85) and pure ML (1.70), with criteria weighted toward accuracy under low data, explainability, and free-text coverage.

### Decision

We will implement the Prediction Service as a hybrid pipeline. A rule engine runs first against each normalized attribute. Where rules do not match, a semantic similarity layer (TF-IDF vectorization with cosine similarity against canonical value embeddings) produces a candidate value. The final confidence is a weighted composite:

```
conf_final = α · conf_rule + (1 - α) · conf_embed
```

with an initial value of `α = 0.7`. Reason codes from the rule layer are attached to each prediction and surfaced in the Human Review Queue for low-confidence items. Both layers live inside the `prediction` package behind `PredictionServiceInterface` (ADR-002).

### Consequences

- Rules carry the prediction under data scarcity, so the system has a usable accuracy floor before sufficient labeled data accumulates.
- Reason codes from the rule layer satisfy the explainability requirement. Reviewers see why an attribute was flagged, which is expected to support adoption by Brian and Dewey on the catalog team.
- The semantic layer can be replaced or upgraded (e.g., to embeddings from a transformer) without touching the rule layer or the Routing Engine, because both layers sit behind `PredictionServiceInterface`.
- The α weighting is a sensitivity point. Wrong α suppresses the more accurate signal source and produces miscalibrated confidence, which propagates directly into routing errors. The initial value of 0.7 is a guess; it must be calibrated against prototype data (see Refinement 3 in the report).
- The decision is tentative and carries explicit reconsideration triggers. If pure rules cover ≥85% of inputs at confidence ≥0.90, the semantic layer adds complexity without value and we should switch to pure rules. If labeled data exceeds ~800 examples and a pure ML model achieves ≥85% accuracy with calibrated confidence, the hybrid approach loses its advantage and we should switch to pure ML.
- Per-attribute-type α weights may be more accurate than a single global α, since some attributes (e.g., `SUPPLY_VOLTAGE`) are inherently easier to predict than others (e.g., `DESCRIPTION`). The retraining pipeline can store learned per-type weights as configuration once Refinement 3 produces evidence.

### Requirements Traceability

- **HLRs:** HLR-3 (predict with confidence)
- **FRs:** FR-3 (per-attribute predictions with confidence scores)
- **QASs:** QAS-1 (accuracy — hybrid provides usable accuracy floor under data scarcity); QAS-5 (reason codes from rules support drift interpretation)
- **Constraints:** C-3, DC-1 (Python ML); C-4 (phase scope limits labeled data, favoring hybrid over pure ML)
- **Scenarios:** SCEN-1 (high-confidence path), SCEN-2 (low-confidence path with reason codes)

---

## ADR-004: Route Confidence Decisions at the Attribute Level, Not the Record Level
### Status

Accepted

### Context

The Routing Engine is the architectural component that enforces the accuracy quality attribute (QA-1, rated High/High). Every record produced by the Prediction Service contains multiple attributes, each with its own predicted value and confidence score. The team must decide whether confidence routing operates at the record level (the whole record is sent to review if any attribute is uncertain) or at the attribute level (each attribute is routed independently).

Two alternatives were considered:

- **Per-record routing.** Conceptually simpler. The review queue holds whole records, and writeback always emits complete records. There is no merge logic. However, a record with ten attributes and one uncertain value sends all ten attributes to review, inflating reviewer workload.
- **Per-attribute routing.** Each attribute is routed independently. Estimated 3–5× lower review volume than per-record because only the attributes the model is unsure about reach the queue. The cost is structural: the writeback service must merge auto-accepted attributes with reviewed attributes for the same record before writing to PIMS, and there is a risk that correlated attributes (e.g., connection type and port size) become inconsistent if reviewed in isolation.

The combined catalog team across eParts and Alps Controls is approximately 4.5 FTEs. Reviewer capacity is the binding constraint on review volume; if the system pushes too many items to review, the labor savings the platform is meant to provide disappear.

### Decision

We will route confidence decisions at the attribute level. The Human Review Queue is keyed on `(record_id, attribute_id)`. The Routing Engine compares each attribute's confidence score against the configured threshold independently. The Writeback Service batches all attributes for a given record and writes them to PIMS as a unit only once all routing paths for that record (auto-accept and review) have resolved.

### Consequences

- Review volume scales with actual model uncertainty rather than with record size, expected to reduce reviewer workload by 3–5× compared with per-record routing.
- Reviewers see only the flagged attributes plus their source context, not the entire record. This focuses attention but means reviewers cannot easily catch inconsistencies between an auto-accepted attribute and one they are reviewing.
- The Writeback Service carries merge logic. It must hold the complete record until all routing decisions for that record are resolved, then upsert it as a unit. A partial write — auto-accepted attributes entering PIMS before reviewed attributes are resolved — would produce incomplete records and is explicitly prevented by this batching.
- Correlated attributes are a known risk. If connection type and port size are reviewed independently and the reviewer makes inconsistent choices, an internally inconsistent record can reach PIMS. Mitigation: the review interface presents the full record context to reviewers, but this has not been validated in practice. Refinement 2 in the project plan tests pairwise mutual information between attributes and inspects high-MI pairs.
- Per-attribute thresholds may be required if attribute-level accuracy varies significantly. Some attributes are inherently easier to predict than others. The threshold mechanism is configurable (ADR-005) so per-attribute thresholds can be introduced without code changes.
- If more than 30% of corrections turn out to involve cross-attribute consistency errors, the per-attribute routing decision should be reconsidered in favor of per-record or attribute-group routing.

### Requirements Traceability

- **HLRs:** HLR-4 (Human Review Queue for low-confidence predictions)
- **FRs:** FR-3 (per-attribute predictions); FR-4 (route below-threshold attributes to queue); FR-9 (per-attribute routing decisions)
- **QASs:** QAS-1 (accuracy — per-attribute routing keeps review volume proportional to risk)
- **Scenarios:** SCEN-2 (only the uncertain attribute is routed, not the whole record)
- **Validation:** VAL-2 (low-confidence item appears in Human Review Queue)

---

## ADR-005: Externalize the Confidence Threshold as Runtime Configuration
### Status

Tentative

### Context

The Routing Engine sends attributes with confidence above a threshold to auto-accept and attributes below the threshold to the Human Review Queue. The threshold is the most sensitive parameter in the system: it controls the tradeoff between accuracy (QA-1) and reviewer throughput. A threshold set too high pushes most attributes into review and overwhelms the catalog team, eliminating the labor savings the platform is meant to provide. A threshold set too low lets incorrect predictions through to PIMS, where they cause wrong parts to be ordered by contractors.

The threshold cannot be set during design because no model has yet been run against production-representative data. The team currently uses a placeholder of 0.85 with no empirical support. Refinement 1 in the project plan calibrates the threshold against ≥200 labeled submissions using precision-recall curves between 0.50 and 0.99. Per-attribute variance in accuracy may also drive a per-attribute threshold table rather than a single global value.

Hardcoding the threshold in the Routing Engine would require a code change and redeployment for every recalibration, which is incompatible with the iterative tuning the team expects across the pilot.

### Decision

The confidence threshold is externalized as runtime configuration read by the Routing Engine at startup. The configuration mechanism supports both a global threshold value and an optional per-attribute override table. Threshold changes take effect on application restart without any code change. The Routing Engine reads the threshold(s) once per pipeline run; threshold changes during a run do not affect already-routed attributes.

### Consequences

- The threshold can be retuned during pilot operation without engineering involvement beyond editing configuration and restarting the App Service.
- Per-attribute thresholds are supported architecturally without further code changes. If Refinement 1 reveals that some attributes (e.g., `SUPPLY_VOLTAGE`) are reliably predicted at 0.75 while others (e.g., `DESCRIPTION`) need 0.92, the per-attribute table can be populated.
- The threshold value is a configuration concern, not an architectural concern. This means that the architecture cannot guarantee an accuracy number; it can only guarantee that whatever threshold is set will be applied consistently. The actual accuracy guarantee depends on operational discipline around configuration management.
- Configuration drift is a risk. If the threshold is changed in production without recording the change in the audit trail, later analyses of model accuracy or reviewer workload may be impossible to interpret. The audit trail (ADR-009) records the threshold value alongside each routing decision to mitigate this.
- The decision is tentative because the threshold itself is unsupported. Once Refinement 1 produces evidence and a value is selected, this decision moves to Accepted.
- This decision interacts with monitorability (ADR-012): the threshold value is one of the baselines against which drift is measured. Changing the threshold resets the baseline.

### Requirements Traceability

- **FRs:** FR-4 (route based on threshold); FR-7 (configurable thresholds, calibration TBD); FR-9 (per-attribute routing using configurable thresholds)
- **QASs:** QAS-1 (accuracy lever); QAS-5 (threshold value is part of the drift baseline)
- **Scenarios:** SCEN-1 (above-threshold auto-accept), SCEN-2 (below-threshold review)
- **Validation:** VAL-2 (threshold drives routing behavior tested by VAL-2)

---

## ADR-006: Enforce Idempotent PIMS Writeback via a Composite Natural Key
### Status

Accepted

### Context

The platform writes approved product attributes to PIMS staging tables on SQL Server. PIMS exposes no writeback API and provides no rollback or transactional guarantees back to the platform. Retries of a writeback operation must not produce duplicate records, because duplicates in PIMS staging propagate into wrong bills of materials for contractor orders.

Several mechanisms were considered:

- **Application-side primary key check.** Read-before-write to detect existing records.
- **Database upsert via composite natural key.** A SQL `MERGE` (or equivalent) keyed on a stable identifier matches existing rows and updates them rather than inserting duplicates.
- **Distributed transaction across the platform and PIMS.** Not feasible: PIMS is owned by a different team, has no API, and there is no distributed transaction coordinator across the trust boundary.
- **Idempotency token in PIMS.** Would require schema change in PIMS, which the platform team does not control.

The submission ID is a composite of the company identifier and the product identifier, making it stable across submissions: a new update pushed for the same company–product pair carries the same submission ID. The attribute ID is a stable canonical attribute identifier. Together, `(submission_id, attribute_id)` uniquely identify any value the platform writes. Both are generated inside the platform and stored in the staging tables before the writeback runs.

### Decision

PIMS writeback uses a composite natural key of `(submission_id, attribute_id)`, where `submission_id` is itself derived from `(company_id, product_id)`. The Publish/Sync Job (Azure Function) executes an upsert against the PIMS staging table: if a row with the same key exists, the value is updated in place; otherwise a new row is inserted. Because the submission ID is stable for a given company–product pair, pushing a new update for the same product produces the same key and overwrites the prior values rather than inserting a duplicate. The natural key is generated and stored in the platform's own staging tables before writeback, so a retry of the writeback also uses the identical key and matches the same target row.

### Consequences

- Retries of the Publish/Sync Job are safe. A network failure mid-run, a transient PIMS outage, or a redeployment that interrupts the job can be recovered by simply running the job again.
- Idempotency is enforced in application code, not in PIMS. If PIMS staging tables are altered (e.g., the natural key columns are dropped or renamed), the guarantee disappears silently. The integration test described in Refinement 4 verifies the schema before any production data is written.
- This decision depends on a structural assumption about PIMS staging that has not yet been validated. Jake at eParts has not delivered the P1-C schema. If the staging tables use wide columns (one row per record with attribute values as columns) rather than tall columns (one row per attribute), the natural key strategy needs a translation layer. If the staging tables lack columns to hold the platform's natural key, the team must either negotiate a schema addition with eParts or maintain a team-owned buffer table that holds the mapping.
- No rollback is possible. Once a row is upserted into PIMS staging, the only way to "undo" it is to write a corrected row with the same natural key. This is acceptable because every write goes through human review or auto-accept above a calibrated threshold; the system never writes silently uncertain data.
- This decision interacts with ADR-004 (per-attribute routing). The natural key is keyed on `attribute_id`, not on `record_id`, which is what enables per-attribute routing to write attributes individually as they resolve. If routing were per-record, the natural key would only need `record_id`.

### Requirements Traceability

- **HLRs:** HLR-5 (write approved data to PIMS staging)
- **FRs:** FR-8 (idempotent application-layer writeback); FR-11 (natural key: submission ID + attribute ID)
- **DRs:** DR-3 (Must — retry must not create duplicates)
- **QASs:** QAS-1 (accuracy — prevents duplicate-driven errors); QAS-4 (availability — safe retry on recovery)
- **Constraints:** C-2 (no PIMS API), C-5 (no direct production writes — writeback targets staging only)
- **Scenarios:** SCEN-1 (Step 5), SCEN-2 (Step 6)
- **Validation:** VAL-3 (upsert + no-duplicate on retry)

---

## ADR-007: Use an Attribute-Row Canonical Schema for the Staging Table
### Status

Accepted

### Context

The Normalization stage transforms heterogeneous supplier formats (CSV, PDF, email-extracted key-value pairs) into a canonical structure that the Prediction Service, Routing Engine, and Writeback Service can consume uniformly. The shape of this canonical schema is an architecturally significant decision because it determines how much work it takes to add a new product category, how easily attributes can be routed individually, and how the staging tables grow over time.

The current scope is valves and actuators, but the client (Harsha) has stated that category expansion is expected after the pilot. Quality attribute QA-3 (Modifiability — new category) is rated Medium/Medium and explicitly requires that adding a category not force a structural change to routing or writeback.

Two structural options were considered:

- **Wide schema (one row per record).** Each record is a single row with one column per attribute (`voltage`, `port_size`, `connection_type`, etc.). Adding a new category requires schema migration: new columns, ALTER TABLE statements, and coordination with any system that reads the staging table. Querying a single record is trivial. Per-attribute routing is awkward because attribute-level state (confidence score, routing decision) would need parallel columns for every attribute.
- **Tall schema (one row per attribute).** Each row is `(record_id, attribute_id, raw_value, predicted_value, confidence, routing_status)`. Adding a new attribute is a data change (a new entry in the attribute reference table), not a schema change. Per-attribute routing is direct: routing status is a column on the row.

### Decision

The canonical staging schema is attribute-row: each row represents one attribute of one record. The columns include `submission_id`, `record_id`, `attribute_id`, `supplier_raw_value`, `predicted_value`, `confidence_score`, `routing_status`, and audit metadata. Attribute definitions (name, type, allowed values, category) live in a separate reference table joined as needed. New product categories are added by inserting attribute definitions into the reference table, not by altering the staging schema.

### Consequences

- Adding a new product category does not require a schema migration against the staging tables. The Normalization stage gains new mapping entries; the Prediction Service is retrained on the expanded label set; nothing in the Routing Engine, Review Queue, or Writeback Service changes structurally.
- Per-attribute routing (ADR-004) becomes natural. Each row carries its own routing state, so the Routing Engine reads and updates one row at a time without joining against a wide record schema.
- Per-attribute audit is also natural. The audit trail can reference a single attribute row by its primary key.
- Querying a complete record requires a join or aggregation across multiple rows. This is a small loss in query convenience and is acceptable because the platform's hot-path queries are per-attribute (routing, scoring, review), not per-record.
- The staging tables grow faster than they would under a wide schema (one row per attribute rather than one row per record). For valves and actuators with roughly a dozen attributes, this is a 12× row-count multiplier. Azure SQL Database is sized to handle this comfortably at expected ingestion volumes.
- This schema decision is independent of the PIMS staging schema. ADR-006 covers the writeback contract with PIMS, which may use either a wide or tall structure. If PIMS is wide, the Writeback Service performs an aggregation transform from the platform's tall canonical schema into the wide PIMS schema; this is documented as an open dependency on Refinement 4.
- If Refinement 4 reveals that PIMS staging is rigidly wide and the team-owned mapping is too costly to maintain, the platform may keep its internal canonical schema tall while presenting a wide interface to PIMS through the Publish/Sync Job. The architecture supports this.

### Requirements Traceability

- **HLRs:** HLR-2 (normalize to standardized structure)
- **FRs:** FR-2 (canonical schema before prediction); FR-11 (attribute-level natural key requires attribute-row schema)
- **QASs:** QAS-3 (new category as data change, not schema migration)
- **Constraints:** C-4 (phase scope expansion); C-6 (pricing excluded from canonical schema)
- **Scenarios:** SCEN-1 (Step 3 — canonical normalization)

---

## ADR-008: Deploy the Platform as a Single Azure App Service Unit
### Status

Accepted

### Context

The platform must be deployed on Azure (a fixed client constraint) and must be operable by a five-person capstone team across one academic year. Quality attributes that bear on deployment topology are QA-2 (model swappability), QA-4 (availability under Prediction Service outage), and a team-size constraint that bounds operational complexity.

Two topologies were analyzed in detail:

- **Single Azure App Service (Python).** All pipeline components — ingestion, normalization, prediction, routing, review-queue access, writeback orchestration — run in one process and one deployment unit. Azure SQL Database holds staging tables, the review queue, and the audit trail. Azure Blob Storage archives raw supplier files. The Publish/Sync Job runs as a separate timer-triggered Azure Function. Components communicate by function call. Scaling is per application unit.
- **Microservices (Azure Container Apps).** Three independent services: Ingestion+Normalization, Prediction, Routing+Writeback. Each scales independently, can be deployed independently, and can fail independently. Inter-service communication is HTTP or Service Bus. Operational requirements include container orchestration, distributed tracing, service-to-service authentication, and three deployment pipelines.

The microservices alternative offers fault isolation and independent scaling, both of which are real benefits for a production system. They are not benefits the current team can absorb operationally during the capstone phase. Distributed tracing alone would consume a substantial fraction of the timeline. The Prediction Service does not currently need GPU instances or independent scaling because supplier ingestion is batched, not real-time.

### Decision

The platform is deployed as a single Azure App Service running Python. All pipeline components live in one process. Azure SQL Database holds all internal pipeline state (staging tables, Human Review Queue, audit trail). Azure Blob Storage archives raw supplier files. The Publish/Sync Job is a timer-triggered Azure Function deployed separately. Inbound channels are SFTP (polled), email (polled), and HTTPS upload. Outbound to PIMS is via `pyodbc` across the trust boundary to PIMS SQL Server. Outbound telemetry to Datadog is fire-and-forget HTTPS.

### Consequences

- One deployment, one log stream, one health check. Operational complexity is bounded.
- Components communicate by function call. This is fast and avoids the complexity of network serialization, retries, and timeouts between filters.
- Fault isolation is reduced. A bug in any component can crash the App Service and take the entire pipeline down. The persistent staging tables and review queue mitigate data loss risk: in-flight work survives a process restart because state is in Azure SQL, not in-memory.
- Independent scaling is not available. If the Prediction Service becomes a hotspot, the entire App Service must be scaled up.
- The module boundaries inside the App Service (described in the module view) are deliberately drawn where service boundaries would go in a microservices deployment. The `prediction` package, `routing` package, and `writeback` package are independent units of code that communicate through typed data contracts. Transitioning to microservices later is therefore adding HTTP serialization at existing boundaries, not rewriting business logic.
- Datadog telemetry is fire-and-forget. Telemetry failures do not block the pipeline. This means a Datadog outage cannot cause a pipeline outage, but it also means dropped telemetry is not retried; operationally significant signals must also be persisted in the audit trail (ADR-009).
- The Publish/Sync Job is intentionally separated as an Azure Function on a timer trigger so that PIMS writeback runs on a controlled schedule rather than synchronously with each ingestion. This decouples PIMS load from supplier ingestion bursts.
- Trigger for reconsideration: production handoff to a larger eParts team, or a Prediction Service that scales independently of ingestion (e.g., GPU-backed inference, multi-model ensembles). At that point, the prediction package is the natural first candidate for extraction into a Container App.

### Requirements Traceability

- **HLRs:** HLR-1 (ingestion endpoints hosted on App Service); HLR-5 (Publish/Sync Azure Function)
- **FRs:** FR-1 (Ingestion Gateway runs on App Service); FR-8 (Publish/Sync Function performs writeback); FR-10 (Azure SQL hosts the persistent queue); FR-13 (Azure Blob hosts raw file archive)
- **DRs:** DR-1 (Blob archive is part of deployment topology)
- **QASs:** QAS-4 (staging tables in Azure SQL provide outage buffering)
- **Constraints:** C-1 (Azure managed services); C-3 / DC-1 (Python App Service); C-7 (single unit chosen over microservices for capstone timeline); DC-3 (Blob Storage archive)
- **Validation:** VAL-1, VAL-3 (deployed components host the tested behavior)

---

## ADR-009: Implement the Human Review Queue as a Persistent Database Table
### Status

Accepted

### Context

When the Routing Engine sends a low-confidence attribute to human review, that attribute must wait until a reviewer at eParts or Alps Controls processes it. Reviewer pace is much slower than machine pace: predictions arrive in batches measured in seconds, while reviewer decisions accumulate over hours or days. The queue must therefore decouple machine throughput from reviewer availability.

Two queue mechanisms were considered:

- **In-memory queue or message broker (e.g., Azure Service Bus).** Standard for high-throughput producer/consumer decoupling. Survives normal load patterns but adds an external dependency, requires a consumer process polling for items, and does not naturally support the spreadsheet-style batch review workflow that catalog staff already use.
- **Persistent database table in Azure SQL.** The queue is a table with `(submission_id, attribute_id, predicted_value, confidence, reason_codes, status, reviewer_id, decided_at, corrected_value)`. Reviewers query the table through eParts' existing internal review interface, which already speaks SQL.

The catalog team already accesses internal staging tables through a spreadsheet-style tool. Building a custom review UI is out of scope for the current phase. The existing internal interface reads directly from staging tables, which means the queue must be a table accessible from that tool.

The queue must also feed retraining: every reviewer decision is a labeled example, and the audit trail layer relies on durable storage of reviewer corrections.

### Decision

The Human Review Queue is implemented as a persistent table in Azure SQL Database. Low-confidence attributes are inserted with `status = 'pending'`. Reviewers access the table through eParts' existing internal review interface, edit values individually or in batch, and submit decisions by updating the `status` to `'approved'` or `'rejected'` and writing the `corrected_value`. On each decision, a row is appended to the audit trail. A notification is sent to the catalog team when items are pending and again when items are processed.

### Consequences

- Reviewer pace is fully decoupled from prediction pace. The queue can hold thousands of pending items without backpressure on the upstream pipeline.
- The queue survives App Service restarts and Prediction Service outages. In-flight reviews are preserved across deployments. This directly supports QA-4 (availability).
- The queue is the persistent store for labeled corrections. The retraining pipeline reads from the audit trail (which captures the history of queue decisions) without coordinating with a separate label store.
- The schema of the queue table is a coupling point with eParts' existing internal review interface. Any change to column names, types, or status values requires coordination with the eParts engineering team. This is a recorded constraint on schema evolution.
- Rejected items are not silently dropped. A rejection writes the corrected value back to the queue row with `status = 'rejected'`, appends to the audit trail, and triggers a notification. The corrected value flows into the labeled correction store for retraining.
- The queue is not a true message broker, so it does not provide push-style notification, dead-letter queues, or consumer load balancing. These features are not needed because there is no automated consumer; the consumer is the catalog team.
- If a custom review UI is built in a future phase, Auth0 (the eParts identity provider per the SOW) integrates at the UI layer and reads from the same queue table. The queue's stable schema is what makes that future UI buildable without changes to the ingestion, prediction, or writeback components.

### Requirements Traceability

- **HLRs:** HLR-4 (persistent Human Review Queue)
- **FRs:** FR-4 (queue is the destination for low-confidence attributes); FR-5 (queue retains prediction, confidence, source ref, status); FR-10 (persistent and queryable)
- **QASs:** QAS-4 (queue survives Prediction Service outages)
- **Constraints:** C-8, DC-2 (queue's stable schema accommodates a future Auth0-gated UI without changes elsewhere)
- **Scenarios:** SCEN-2 (Steps 3–5)
- **Validation:** VAL-2 (item appears in Human Review Queue)

---

## ADR-010: Maintain an Append-Only Audit Trail of Every Pipeline Decision
### Status

Accepted

### Context

The platform automates a workflow that previously required human judgment at every step. Two needs follow from this:

1. **Compliance and traceability.** When a wrong product attribute reaches PIMS, eParts needs to determine why: which model version produced the prediction, what confidence the model emitted, whether a reviewer saw the item, and what the reviewer's decision was. Without this trail, root cause analysis is impossible.
2. **Model improvement.** The retraining pipeline (described in the MLOps section of the report) depends on labeled corrections. Reviewer decisions are the primary source of labels. The system must capture the original prediction, the original confidence, the source supplier, and the corrected value as a durable record.

Quality attribute QA-5 (Monitorability) is rated High/High and depends on having a record of every routing and review decision over time so that drift in correction rates can be detected.

A mutable record (overwriting the prediction with the corrected value) would satisfy the immediate writeback need but lose the history needed for audit and retraining. An append-only log preserves both.

### Decision

Every pipeline decision is recorded as a row in an append-only audit trail table in Azure SQL Database. Decisions captured are: auto-accept by the Routing Engine, approval by a reviewer, correction by a reviewer (with the corrected value alongside the original prediction), and rejection by a reviewer. Each row contains the submission ID, attribute ID, source supplier, model version, original predicted value, confidence score, threshold value at decision time, final decision, decided value, decision actor (system or reviewer ID), and timestamp. Rows are never updated or deleted.

### Consequences

- Every value written to PIMS is traceable back to the prediction, the confidence, the threshold, and the reviewer (if any) that produced it.
- The audit trail is the source of truth for retraining. Corrections where the reviewer's value differed from the model's prediction are flagged as labeled training examples and read by the retraining job (ADR-011).
- The model version recorded on each row is essential for retraining safety. When a new model version is promoted, the audit trail allows the team to compare correction rates before and after promotion as a check on regression.
- The audit trail is the basis for drift detection in Datadog (ADR-012). Per-attribute confidence distributions and reviewer correction rates are computed from this table.
- Append-only growth is unbounded. The table will require a retention policy (cold storage to Azure Blob after some period) once production volumes are observed. This is operationally acceptable in the current phase because volumes are low.
- The audit trail is internal to the platform. PIMS does not see it. If PIMS needs an audit record alongside a value, the writeback service includes audit metadata in the upsert; the platform's internal audit trail is the canonical record.
- Reviewer privacy: the reviewer ID is recorded. This is acceptable under eParts' internal policies because the catalog team is salaried staff acting in their official capacity. If the audit trail were ever exposed externally, reviewer IDs would need to be redacted.

### Requirements Traceability

- **FRs:** FR-6 (log every auto-accept, approval, correction, rejection); FR-12 (audit trail backs telemetry signals)
- **DRs:** DR-2 (Future/TBD — corrected data logged for retraining)
- **QASs:** QAS-5 (audit trail is the durable source for drift signals)
- **Scenarios:** SCEN-2 (Step 5 — correction logged)

---

## ADR-011: Trigger Retraining Automatically on Human Review Batch Completion
### Status

Proposed

### Context

The Prediction Service must improve over time as supplier data changes and as the labeled corpus grows. Reviewer corrections are the primary source of labeled examples. The architectural choice is the trigger mechanism that initiates a retraining run.

Three alternatives were considered:

- **Manual trigger.** An engineer reviews the accumulated corrections, judges that enough new examples exist, runs the training script, evaluates the result, and promotes the new model if it improves on the previous version. Requires no automation but depends entirely on engineer availability and judgment. Poor fit for a five-person capstone team that cannot guarantee weekly engineer cycles.
- **Automatic trigger on review batch completion.** A retraining job fires automatically each time a human review batch is marked complete. The new model version is evaluated against a held-out validation set and promoted only if it outperforms the current version. No engineer initiates the run.
- **Scheduled trigger.** Retraining runs on a fixed cadence (weekly or monthly) regardless of review activity. Predictable, but introduces a fixed lag between when corrections are made and when the model learns from them. Risks training on too few examples if review activity is light, or accumulating too many examples if review activity is heavy.

In all cases, a validation gate is required: a new model version must outperform the current version on a held-out validation set before it is promoted. Without this gate, automatic retraining could promote regressions silently.

### Decision

Retraining is triggered automatically when a human review batch is marked complete. The retraining job reads all corrections flagged as labeled examples since the last training run from the audit trail (ADR-010), combines them with the existing labeled dataset, and trains a new version of the active prediction strategy. The new version is evaluated against a held-out validation set. If validation accuracy improves, the new version is promoted as the active model behind `PredictionServiceInterface` (ADR-002). If it does not improve, the previous version remains active and the result is logged for engineering review. Model version history is stored in Azure Blob Storage with training date, example count, and validation accuracy as metadata.

### Consequences

- The model learns from corrections as soon as a batch is reviewed, with no engineer in the loop. This is the fastest path from a reviewer correction to an improved model.
- The validation gate prevents silent regressions. A worse model is never promoted automatically; it is logged for human review.
- Promotion is transparent to the rest of the pipeline. The Routing Engine, Writeback Service, and Review Queue see the prediction service as unchanged because `PredictionServiceInterface` does not change with model version.
- Rollback is supported. Each model version is tagged in Azure Blob Storage. If a promoted version is later found to perform poorly on production data, engineering can revert by changing the active model pointer in configuration without redeploying the application.
- A minimum batch size before triggering retraining is required to avoid training on sparse data. The minimum example count has not been set and will be established once Refinement 1 produces real review-batch sizes. Until then, this decision is Proposed.
- The validation set must remain representative. If the validation set drifts from production data, the gate becomes meaningless because a model that overfits to stale validation can pass the gate while degrading on real inputs. The validation set itself must be refreshed periodically; this operational discipline is a dependency of the retraining decision.
- Frequent retraining on small batches can produce unstable model versions even with a validation gate, because validation accuracy itself fluctuates on small evaluation sets. If observed, the trigger should be replaced with a hybrid: scheduled retraining with a minimum-correction-count gate.
- Engineering team capacity post-handoff may make manual triggering attractive again. A larger team with regular review cycles may want explicit human oversight on every promotion. The retraining package is decoupled enough from the rest of the pipeline that switching to manual triggering is a configuration change.

### Requirements Traceability

- **HLRs:** HLR-3 (prediction quality maintained over time)
- **DRs:** DR-2 (Future/TBD — corrected data logged for future retraining and offline model improvement)
- **QASs:** QAS-2 (retraining promotes new versions through PredictionServiceInterface without breaking dependents); QAS-5 (closes the loop from drift detection to model improvement)
- **Constraints:** C-3, DC-1 (retraining runs in the Python prediction package)

---

## ADR-012: Emit Stage-by-Stage Telemetry to Datadog for Drift Detection and Operational Monitoring
### Status

Proposed

### Context

ML systems can degrade silently as supplier data drifts from the training distribution. Without monitoring, incorrect auto-accepts accumulate in PIMS and surface only when contractors order wrong parts. Quality attribute QA-5 (Monitorability) is rated High/High both in importance (because silent degradation is the worst failure mode) and in difficulty (because the team has not yet defined what metrics to track or what baseline to compare against).

eParts uses Datadog as its observability platform, so integration is mandatory rather than chosen. The architectural questions are: where in the pipeline should telemetry be emitted, what signals should be captured, and how should those signals be tied to drift detection.

Telemetry must not block the pipeline. A Datadog outage cannot be allowed to take ingestion or writeback offline.

### Decision

Telemetry is emitted to Datadog from four pipeline stages over fire-and-forget HTTPS:

- **Ingestion Gateway:** ingestion success and failure counts, parsed by supplier and channel.
- **Normalization (Structured Layer):** row counts after canonical schema mapping, broken down by supplier and category.
- **Prediction Service:** per-attribute confidence score distributions and rule-vs-embedding contribution breakdown.
- **Routing Engine:** routing split ratios (auto-accept vs. review) per attribute.
- **Review Queue:** reviewer decision counts (approved, corrected, rejected) and correction rates per attribute.

Telemetry calls do not block the pipeline; failed Datadog writes are logged locally and dropped. Operationally significant signals that must not be lost are also persisted in the audit trail (ADR-010), so Datadog is treated as a dashboard and alerting layer, not as the system of record.

Drift detection thresholds (e.g., "alert when correction rate increases by 10% over a rolling two-week window" or "alert when mean confidence shifts by 15%") are defined as configuration on Datadog and validated empirically once Refinement 1 has produced a baseline.

### Consequences

- The pipeline emits the right signals to detect drift. Confidence distributions reveal model overconfidence or underconfidence; correction rates reveal accuracy degradation; routing split ratios reveal threshold drift.
- Drift detection is operationally complete only when thresholds are defined. The architecture emits the signals; it cannot yet say what deviation from baseline constitutes actionable drift. Refinement 6 in the project plan defines and validates these thresholds against simulated drift.
- Telemetry is tied to the audit trail. Reviewer correction rates in Datadog are computed from the same decisions recorded in the audit trail, so the dashboard and the system of record cannot diverge.
- Datadog outages do not affect pipeline correctness. A telemetry failure is logged locally and the pipeline continues. This is acceptable because the audit trail is the source of truth; the dashboard is a derived view.
- Because telemetry is fire-and-forget, telemetry packets can be lost during a Datadog outage without retry. This means short-term metrics (e.g., a one-hour confidence distribution) may have gaps during incidents. Long-term metrics computed from the audit trail are unaffected.
- Per-supplier telemetry is captured because supplier-specific drift is a likely failure mode (a supplier changes its catalog format, the model's confidence drops, but the threshold doesn't catch it). Per-supplier dashboards in Datadog allow drift to be localized to the offending supplier.
- This decision is Proposed rather than Accepted because the alert thresholds and baselines are not yet defined. Once Refinement 1 and Refinement 6 produce values, this decision moves to Accepted.

### Requirements Traceability

- **FRs:** FR-12 (emit confidence distributions, correction rates, routing decisions, pipeline metrics to Datadog)
- **QASs:** QAS-5 (drift detection from baseline deviation in confidence and correction rates)
- **Constraints:** C-1 (Datadog runs over HTTPS from Azure App Service)

---

## ADR-013: Establish a Release-Versioned ETIM Reference Data Layer Owned by Ingestion
### Status

Accepted

### Context

The platform is adopting ETIM as the classification standard for catalog standardization (valves and actuators in phase one). ETIM is a controlled technical dictionary: product groups (EG), product classes (EC), features (EF), feature groups (EFG), units (EU), and controlled values (EV), plus the mappings that say which features belong to a class and which values are allowed for a class-feature. ETIM is not supplier data — it provides no SKUs, prices, or product documents. Before the platform can match any supplier product to ETIM (class matching, feature matching, value matching, validation), it needs the ETIM dictionary loaded, queryable, and under version control.

The supplied ETIM data has awkward physical characteristics that make it a poor fit for ad-hoc loading: the production archive is a set of CSV files encoded **UTF-16 little-endian, semicolon-delimited**, for a specific release (10.0) and language (EI, English International). ETIM publishes new releases over time, and class/feature/value definitions change between releases, so a single un-versioned copy would silently conflate releases and make historical mappings unauditable.

A key question was **ownership**: the reference loader could sit in the ML/matching component (the primary consumer) or in ingestion (which already owns file parsing, encoding handling, idempotent batch loads, and Alembic migrations). Two further options for storage shape were considered:

- **Denormalized blob / JSON document per class.** Fast to load and to read a whole class, but cannot enforce referential integrity, makes cross-class queries (e.g. "all classes using feature EF000513") expensive, and couples readers to a single release's shape.
- **Normalized relational tables mirroring the ETIM model**, scoped by release ID. Enforces FKs and composite keys, supports multi-release coexistence, and lets the matcher query class→feature→value relationships directly.

### Decision

We will model ETIM as a **normalized relational reference layer of ten tables**, every row scoped by a release identifier, and we will make the **ingestion team the owner** of both the schema and the import job.

The tables are `etim_release`, `etim_group`, `etim_class`, `etim_class_synonym`, `etim_feature_group`, `etim_feature`, `etim_unit`, `etim_value`, `etim_class_feature`, and `etim_class_feature_value`, with composite primary keys on `(etim_release_id, …)` so that multiple ETIM releases can coexist without collision. The release identifier is a stable, human-readable string of the form `ETIM-{version}-{language}` (e.g. `ETIM-10.0-EI`).

A dedicated **ETIM Reference Loader** import job reads the UTF-16 LE, semicolon-delimited CSV archive, validates that the expected columns are present per file, rejects incomplete or release-mismatched archives, and loads the rows into the reference tables. It records the release version, language, source name, an import timestamp, and a **SHA-256 checksum over the archive**. Re-importing the same release is **idempotent** (no-op when the checksum matches; controlled replace only with an explicit `--force`). The job is exposed as a CLI entry point (`eparts etim import …`) mirroring the existing Typer CLI, and is delivered as Alembic migration `0005_create_etim_reference` plus `etim/loader.py`, `models/etim.py`, and `cli/etim.py`.

This decision is implemented and verified against the real ETIM 10.0 EI archive (EPARTS-285).

### Consequences

- The matcher (ETIM class/feature/value matching) can treat ETIM as a stable, queryable dependency. Loading the dictionary is no longer entangled with matching logic, so the two can evolve independently.
- Release versioning is first-class. Because every row is keyed by `etim_release_id`, a future ETIM 11.0 can be loaded alongside 10.0, and any product's mapping can name the exact release it was matched against. This is a prerequisite for governed ETIM upgrades (an open client decision in the brief).
- Idempotent, checksummed import makes the load safe to re-run in CI and across environments without producing duplicates or partial state. A mismatched or truncated archive is rejected with a clear error rather than loaded silently.
- Placing ownership in ingestion reuses existing strengths (encoding handling, batch idempotency, Alembic, the Typer CLI) and keeps the file-handling concerns in the team that already does file handling. The cost is a coordination point: the matching team consumes a schema that ingestion owns, so reference-table changes require a published contract.
- The reference layer is read-mostly and modest in size (~160 groups, ~5,600 classes, ~17,000 features, ~16,000 values, ~200,000 class-feature-value links for 10.0 EI). Normalized storage on the current Postgres stack handles this comfortably.
- ETIM does not supply a client-ready "required field" flag. The reference layer deliberately stores ETIM as published and leaves required/recommended/optional policy to a separate client policy overlay (`catalog_feature_policy`, owned downstream). This ADR does not cover that overlay.
- The loader currently targets the CSV archive only. The Excel workbook (useful for analyst review and metric/imperial crosswalks) is intentionally out of scope for production import.

### Requirements Traceability

- **Source:** `ETIM_IMPLEMENTATION_BRIEF.md` (ETIM Reference Loader, ETIM Reference Tables, Acceptance Criteria 1)
- **Tickets:** EPARTS-285 (Create ETIM reference schema and import job — Done); EPARTS-275 (ETIM research); parent EPARTS-154 (Ingestion)
- **Implements:** ETIM reference schema, release tracking, idempotent import, golden row-count validation
- **Related ADRs:** ADR-014 (staging split consumes the reference layer for matching); ADR-015 (Postgres-now datastore the tables are built on); ADR-007 (the prior canonical-schema decision this complements)

---

## ADR-014: Emit a Source-Preserving Product + Attribute Staging Split
### Status

Accepted

### Context

ETIM standardization rests on a core principle: **original supplier data is evidence; ETIM data is a standardized interpretation laid on top; confidence is how sure the system is about that interpretation.** For this to hold, ingestion must hand the matching stage data that (a) separates a *product* (the sellable SKU) from its *attributes*, and (b) preserves every original value together with where it came from — file, page, row, raw text, raw unit — so that any later ETIM mapping can be traced back to its source.

Today ingestion emits a single flat `IngestedRecord` (one row per source record, with `raw_fields` as a JSONB bag). That shape preserves source vocabulary but does not express product-vs-attribute granularity, gives attributes no individual identity, and has nowhere to carry per-attribute evidence (source page/row) or per-attribute confidence. It also forces every downstream consumer to re-derive product and attribute structure from an untyped blob.

There is also a real granularity mismatch across sources that the staging shape must absorb: a **CSV row** is naturally one product with many attribute *columns*, whereas a **datasheet PDF** is one product (a SKU) with many attribute *rows* extracted from the document. Both must land in the same canonical staging shape.

Options considered:

- **Keep the flat `IngestedRecord`** and let the matcher split product/attributes from the JSONB bag. Smallest ingestion change, but pushes structure-recovery and evidence-tracking into every consumer, and gives attributes no stable identity for per-attribute routing, confidence, or audit.
- **One wide staging row per product** with attributes as columns. Convenient for whole-product reads, but cannot carry per-attribute evidence/confidence without parallel columns, and reintroduces schema migration for every new attribute.
- **A two-table split: `staging_product` + `staging_raw_attribute`** (one product row; one evidence row per attribute). Each attribute row carries its own source evidence and confidence and has a stable identity. This matches the brief's staging model and is the natural input to per-attribute ETIM matching, routing, and audit.

### Decision

Ingestion will emit a **product + attribute split**: a `staging_product` row per sellable SKU and a `staging_raw_attribute` row per attribute, replacing the flat `IngestedRecord` as the output contract.

`staging_product` carries product identity and provenance: `supplier_id`, `supplier_sku`, `manufacturer`, `supplier_category`, `description`, `source_file_id`, `submission_id`, `processing_status`. Product identity for idempotency is `supplier_id + supplier_sku` (per source). `staging_raw_attribute` carries one row of evidence per attribute: `product_id`, `source_attribute_name`, `source_value`, `source_unit`, `source_text`, `source_page`, `source_row_number`, and `source_confidence`. Attribute identity for idempotency is `product_id + source_attribute_name`. Both tables are written with idempotent upserts, batched in one transaction per product, preserving the existing raw-bytes archival and quarantine paths unchanged.

Which source fields populate product identity versus become attribute rows is **declared per source** via `ProductMapping` on the source/parser config (`sku_field`, `manufacturer_field`, `category_field`, `description_field`, `unit_field`, `attribute_fields`, `exclude_fields`), so the CSV-column and PDF-row granularities both resolve to the same staging shape without code changes per source.

Crucially, ingestion **does not interpret** these values into ETIM. No field renaming, no ETIM class/feature/value assignment, no unit conversion happens here — those belong to the ETIM-aware matching stage, which reads staging and writes its results to its own tables (e.g. `matched_product_attribute`). ETIM must never overwrite ingestion's source-preserving output.

The legacy flat `IngestedRecord` path is retired after cutover (deprecate or dual-write during transition; tracked by EPARTS-302). Until a source declares a `ProductMapping`, it continues on the legacy flat path.

### Consequences

- Nothing from the supplier catalog is lost or flattened. Every value is individually addressable and traceable to file/page/row/raw-text, which is the evidence backbone the entire ETIM story depends on.
- Per-attribute identity makes per-attribute confidence (ADR-005/ADR-004 routing), per-attribute ETIM matching, and per-attribute audit natural — each is keyed on a real attribute row rather than reconstructed from a blob.
- The product/attribute boundary is configuration, not code. New sources and formats are onboarded by declaring a mapping; the CSV-vs-datasheet granularity difference is absorbed in config.
- Row counts grow relative to the flat shape (one row per attribute rather than one per record). For valve/actuator products with ~12–40 attributes this is a sizeable multiplier; the current Postgres stack (ADR-015) handles expected volumes, with indexes for product lookups.
- This **supersedes the staging design in ADR-007** in practice. ADR-007 specified a single tall staging table that also carried prediction/routing columns (`predicted_value`, `confidence_score`, `routing_status`). Under ETIM, ingestion's staging holds only *source evidence*; predicted values, match confidence, validation status, and review status move to a separate matching-owned table. ADR-007's "attribute-row, not wide" instinct is retained and reinforced; its column set and single-table assumption are not.
- The PIMS writeback contract shifts accordingly. The brief keys PIMS output on `product_id + etim_release_id + etim_class_id + etim_feature_id` rather than `submission_id + attribute_id`; ADR-006's idempotency mechanism needs to be revisited against this (flagged in the ADR assessment, not resolved here).
- A clean cutover is required to avoid two parallel write paths. The transition (dual-write vs deprecate) and the update to the §6.1 output contract are explicit follow-ups (EPARTS-302).
- Missing-SKU handling must be defined (quarantine vs synthesized id) — an open item feeding the source mapping config.

### Requirements Traceability

- **Source:** `ETIM_IMPLEMENTATION_BRIEF.md` (Staging Layer; Staging Tables; "Original supplier data = evidence"); `INGESTION_ETIM_TICKET_MAP.md` (ING-E4/E5/E6/E7/E9)
- **Tickets:** EPARTS-297 (ProductMapping config); EPARTS-298 (staging schema); EPARTS-299 (writer rework); EPARTS-302 (retire flat path); parent EPARTS-154
- **QASs:** QAS-1 (accuracy — evidence preserved for traceable correction); QAS-3 (new category/attribute as data + config, not schema migration)
- **Related ADRs:** ADR-007 (superseded in part — see above); ADR-013 (reference layer the staged data is matched against); ADR-015 (datastore); ADR-004/ADR-005 (per-attribute routing/threshold consume attribute identity); ADR-006 (PIMS idempotency to be re-keyed)

---

## ADR-015: Target PostgreSQL Now; Defer the Azure SQL Conversion
### Status

Accepted

### Context

The ETIM implementation brief specifies its schemas in **SQL Server / Azure SQL dialect** (`DATETIME2`, `NVARCHAR(MAX)`, `BIT`), consistent with the original platform design (ADR-008), which placed all internal pipeline state in **Azure SQL Database** and deployed the platform as a single Azure App Service. Several earlier ADRs assume this Azure SQL substrate (ADR-006 PIMS writeback, ADR-007 staging, ADR-008 deployment, ADR-009 review queue, ADR-010 audit trail).

The ingestion service as actually built does not run on Azure SQL. It runs on **PostgreSQL** with SQLAlchemy 2.x + Alembic migrations, uses **JSONB** for semi-structured fields, archives raw bytes to **S3/MinIO**, and is packaged with Docker/`docker-compose` (Postgres + MinIO) rather than App Service. The existing migrations (`0001`–`0005`, including the ETIM reference tables) are all Postgres.

The ETIM schema tickets (reference tables, staging split) were therefore blocked on a datastore question (ING-E0): author the new ETIM and staging tables for Azure SQL to match the brief, or for Postgres to match the running service? Authoring for Azure SQL now would mean building against a database the platform does not yet use, maintaining a dialect the rest of the codebase does not use, and carrying that divergence indefinitely. Authoring for Postgres now keeps the entire ingestion service on one coherent stack and translates the brief's SQL Server DDL to Postgres equivalents.

A migration to Azure SQL is a real future possibility — it is the original target and ties to the broader platform-on-Azure direction (EPARTS-64) — but it is a separate, platform-level effort that is not in flight today.

### Decision

All new ETIM reference tables and staging tables target **PostgreSQL (the current stack) for now**, using Alembic migrations and JSONB where useful, matching the existing ingestion service. The brief's SQL Server DDL is translated to Postgres equivalents: `DATETIME2 → timestamptz`, `NVARCHAR(MAX) → text`, `BIT → boolean`, with JSONB used where a flexible column is warranted.

A later conversion to **Azure SQL is explicitly deferred** to the future move of the wider platform onto Azure, and is treated as a separate effort rather than a constraint on current ETIM work. This decision **unblocks the ETIM schema tickets** (ING-E0 is resolved). It does not retract ADR-008's eventual Azure direction; it records that the *current* substrate is Postgres and that ETIM work builds on Postgres rather than waiting for, or pre-building against, Azure SQL.

### Consequences

- The ingestion service stays on a single coherent persistence stack (Postgres + Alembic + JSONB + S3). New ETIM and staging migrations sit in the same migration chain as everything else, with one dialect to test and operate.
- The ETIM schema and staging tickets are unblocked and can proceed immediately, which is the critical path for the rest of the ETIM matching work.
- A divergence is now on record between several existing ADRs (which name Azure SQL / SQL Server) and the running system (Postgres). ADR-008 in particular is now partially stale on the datastore and deployment topology; this is captured in the ADR assessment for whole-platform follow-up rather than silently ignored.
- A future Azure SQL port is a known, bounded piece of work. It would touch: column-type translation back to the SQL Server dialect, JSONB usage (which has no exact Azure SQL analogue and would need `nvarchar(max)`/JSON functions), Postgres-specific features in use (advisory locks for run-level exclusivity, `ON CONFLICT` upserts), and the migration tooling. Keeping Postgres-specific features behind the storage layer limits the blast radius of that future port.
- Because the decision is "now vs later" rather than "never," teams should avoid leaning on Postgres-only behavior in business logic above the storage layer, so the deferred port stays a storage-layer concern.
- PIMS itself remains external and may stay on SQL Server regardless; this ADR governs the platform's *own* internal stores, not the PIMS target (see ADR-006).

### Requirements Traceability

- **Source:** `INGESTION_ETIM_TICKET_MAP.md` (ING-E0 — RESOLVED: "PostgreSQL now; Azure SQL conversion deferred"); `ETIM_IMPLEMENTATION_BRIEF.md` (Data Model — SQL Server DDL, here translated)
- **Tickets:** EPARTS-285 (built on Postgres migration 0005); EPARTS-298 (staging schema, Postgres); EPARTS-64 (future platform-on-Azure)
- **Constraints:** C-1 (Azure managed services — eventual direction, deferred); C-7 (capstone operational simplicity — one stack)
- **Related ADRs:** ADR-008 (revisits its Azure App Service + Azure SQL topology — now partially superseded on substrate); ADR-013 and ADR-014 (the reference and staging tables this decision places on Postgres); ADR-006 (PIMS target datastore, separate)

---

## ADR-016: Decompose Attribute Matching into Staged ETIM Class → Feature → Value/Unit Matching
### Status

Accepted

### Context

ADR-003 framed the matching problem as a single step: map a raw supplier attribute string onto a canonical attribute value, using a rule engine blended with semantic similarity (`conf_final = α·conf_rule + (1−α)·conf_embed`, α = 0.7). That framing was correct for a free-form canonical vocabulary, where every attribute is independent and there is one decision to make per attribute.

ETIM invalidates the independence assumption. Under ETIM (HLR-6, FR-9) an attribute cannot be matched at all until the product's **class** is known, because the set of legal features is a property of the class: `etim_class_feature` says which features belong to `EC…`, and `etim_class_feature_value` says which values are legal for that class-feature pair. Matching "Torque: 120 Nm" is meaningless without first deciding the product is a valve actuator, and matching it against the wrong class produces a confidently wrong answer rather than a low-confidence one.

The value side is not uniform either. ETIM feature types carry different semantics and different failure modes:

| Type | Meaning | What matching must produce |
|---|---|---|
| A | Controlled list value | an `etim_value_id` drawn from the legal set for that class-feature |
| L | Logical yes/no | a boolean |
| N | Numeric | a number **plus** a unit, converted to the ETIM-declared unit |
| R | Numeric range | a min, a max, and a unit |

A single matcher emitting one scalar `predicted_value` with one `confidence_score` cannot express "we are confident this is class EC002714 but unsure whether the torque figure is the rated or the breakaway value," which is exactly the distinction a reviewer needs. It also gives the router a single number where the routing decision now depends on several (see ADR-018).

Two alternatives were considered:

- **Keep one matcher, widen its output.** Emit class, features and values from one model call and one confidence. Cheapest change, but it hides a genuine dependency: a class error silently corrupts every downstream feature match, and there is no place to intervene between the two.
- **A per-class trained model.** One classifier per ETIM class. 5,640 classes make this untrainable at our data volume, and it would still not solve unit normalization.

### Decision

We will decompose matching into an ordered pipeline of stages, each producing its own evidence and its own confidence:

```
class matching → feature matching → value matching → unit normalization
              → ETIM validation → client-policy validation → confidence scoring
```

Each stage is a filter in the ADR-001 sense, and the whole sequence remains behind the single `PredictionServiceInterface` established in ADR-002 — this decomposition is an interface *enrichment*, not a reversal. `PredictionResult` grows to carry candidate classes with confidences, matched features, matched values with feature-type-appropriate typing, and validation status, in place of a single predicted value.

Class matching consumes class names, class descriptions, `etim_class_synonym` rows, and the correction store; feature and value matching continue to use the ADR-003 hybrid of rules plus semantic similarity over the class-restricted candidate set. **A correction store is consulted before general matching at every stage** so that a reviewer's decision on one product resolves the same mapping for later products without retraining.

Stage outputs land in `matched_product_attribute` — the interpretation table introduced by ADR-014 — which carries the ETIM identifiers, the typed normalized values (`normalized_text_value`, `normalized_numeric_value`, `normalized_range_min`/`max`, `normalized_logical_value`), and per-assignment confidence, alongside a foreign key back to the `staging_raw_attribute` evidence row.

**Implementation status: designed, not built.** The reference layer this depends on is live (ADR-013), and the evidence/interpretation tables exist (ADR-014, Alembic `0006`). The matching stages themselves are owned by the ML stream under EPARTS-289/290/291 and are not yet in the running pipeline; the pipeline currently emits source evidence only.

### Consequences

- Class errors become **visible and interceptable** instead of silently poisoning downstream matches. This is what makes the class-review-first routing path in ADR-018 possible.
- Confidence attaches **per ETIM assignment** rather than per raw attribute, which is what DR-4 and the PIMS output contract require and what a reviewer needs in order to accept a class while correcting a single feature.
- Accuracy becomes measurable against a controlled vocabulary rather than against free text: a match is right or wrong against `etim_class_feature_value`, not fuzzily similar to a gold string. This sharpens the golden test set (EPARTS-296) but also makes previously "close enough" answers count as failures, so headline accuracy will drop before it rises.
- Unit normalization becomes a first-class stage rather than a formatting detail, because type N and R features declare a unit in `etim_class_feature.UNITOFMEASID` and a value in the wrong unit is wrong, not merely unformatted.
- More stages means more places to fail and more latency per product. The mitigation is that the stages are cheap relative to the OCR/LLM extraction already in the pipeline, and each stage's output is persisted, so a failure late in the chain does not re-run the expensive early work.
- The α = 0.7 blend and the reconsideration triggers from ADR-003 carry over unchanged to the feature and value stages. ADR-003 is not superseded; it is narrowed in scope from "the matcher" to "two of the matcher's stages."
- Because the correction store is consulted first, the system's behaviour changes as reviewers work. That is deliberate, but it means matching accuracy is not reproducible from the model alone — the correction store must be snapshotted alongside any benchmark run.

### Requirements Traceability

- **Spec:** Product Specification v1.4 (29 July 2026)
- **HLRs:** HLR-6 (classify against ETIM and enrich with class/feature/value/unit identifiers); HLR-2 (the intermediate structure this reads from — mechanical cleanup only, no ETIM keying); HLR-3 (predict with confidence scores)
- **FRs:** FR-9 (match to ETIM classes, features, controlled values/units with per-assignment confidence, preserving the original value); FR-3 (confidence score per predicted attribute)
- **DRs:** DR-4 (ETIM-keyed PIMS output — consumes the identifiers this ADR produces)
- **QASs:** QAS-1 Modifiability — a new supplier format changes the parse stage only, not the matching stages
- **Scenarios:** SCEN-1 step 4 (the ML service matches attributes, then matches them to ETIM class, features and values); SCEN-2 steps 2–3 (per-assignment confidence is what routes the item to review)
- **Validation:** VAL-5 (class review precedes attribute routing) — added in spec v1.4 as the test for this ADR; **specified, not yet executable**, because these stages are designed and not built. VAL-4 covers the reference layer this ADR reads; its 10 unit tests pass, and its integration half skips without the real archive.
- **Source:** `ETIM_IMPLEMENTATION_BRIEF.md` — End-to-End Process steps 7–15, ML/AI Attribute Matching, ETIM Feature Types
- **Tickets:** EPARTS-289 (class matching), EPARTS-290 (feature matching), EPARTS-291 (value/unit matching), EPARTS-296 (golden test set); parent EPARTS-156 (ML)
- **Related ADRs:** narrows ADR-003 (hybrid rule + semantic similarity) to the feature and value stages; enriches the contract of ADR-002 (`PredictionServiceInterface`); writes into the interpretation table of ADR-014; reads the reference layer of ADR-013; feeds the routing signals of ADR-018 and the policy gate of ADR-019

---

## ADR-017: Re-key the PIMS Writeback Contract on ETIM Identifiers
### Status

Accepted

### Context

ADR-006 established idempotent PIMS writeback via a composite natural key of `submission_id + attribute_id`, upserted rather than inserted, so that a retried write cannot create duplicates. The mechanism was and remains correct.

The key is not. Two things broke it.

**The key no longer identifies the thing being written.** Under ETIM the unit of published data is not "an attribute of a submission" but "the value of a specific ETIM feature, of a specific ETIM class, of a specific product, under a specific ETIM release" (HLR-6, DR-4). `submission_id` is an artefact of *how the data arrived*, not of *what it describes*. The same product arriving twice — a corrected catalogue re-sent by the supplier, or a second file covering the same SKU — produces two submission IDs and therefore two rows for one real-world fact. The upsert would not collide, and PIMS would accumulate duplicates that are invisible to the idempotency check.

**The payload no longer carries enough to be useful downstream.** ADR-006's row was a value plus a confidence. The PIMS output contract now has to carry both the interpretation and the evidence behind it, because the whole point of the standardization objective is that a consumer can compare products across suppliers *and* audit where a value came from.

Alternatives considered:

- **Keep `submission_id + attribute_id`, add ETIM IDs as payload columns.** Minimal change, but leaves the duplicate-on-resubmission defect in place and makes "the current value of feature EF021864 for this product" unanswerable without scanning submissions.
- **Key on `product_id + etim_class_id + etim_feature_id`, omitting the release.** Simpler, but conflates ETIM releases: a value matched under 10.0 and a value matched under a future 11.0 would collide even though the feature definition may have changed between them. That defeats the release-scoping established in ADR-013.

### Decision

The PIMS writeback natural key becomes:

```
product_id + etim_release_id + etim_class_id + etim_feature_id
```

The upsert mechanism from ADR-006 is unchanged — application-layer idempotent upsert through the staging integration, honouring constraint C-2/DC-3 that we do not write directly to production PIMS tables.

The published row carries the interpretation, the evidence, and the provenance together:

| Group | Fields |
|---|---|
| ETIM interpretation | `etim_release_id`, `etim_class_id`, `etim_feature_id`, `etim_value_id`, `etim_unit_id`, feature type |
| Normalized typed value | text / numeric / range-min / range-max / logical, per feature type |
| Original evidence | original attribute name, original value, original unit, source text reference |
| Decision metadata | confidence, approval status (auto-accepted or human-approved) |

`submission_id` remains on the row as provenance — it answers "which file did this arrive in" — but it is no longer part of the identity.

Two distinctions this ADR preserves deliberately: PIMS may remain SQL Server even though our own stores are PostgreSQL (ADR-015 governs *our* datastore, not the client's), and the write remains to staging rather than production tables.

**Implementation status: designed, not built.** The identifiers this key depends on are produced by the matching stages of ADR-016, which are not yet in the pipeline. The writer rework is EPARTS-299, on the critical path `285 ‖ (297 → 298 → 299)`.

### Consequences

- Re-sending a corrected catalogue for a product now **updates** the published row instead of appending a second one. This is the defect the old key could not see.
- "What is the current published value of feature X for product Y under release Z" becomes a primary-key lookup. Cross-supplier comparison and website filtering — the business objective that motivated ETIM adoption — depend on exactly that query being cheap.
- The release is part of the key for **provenance**: every published value names the ETIM release it was matched under. Under ADR-020 the project is pinned to 10.0 EI, so in practice the field is constant — it is carried so the row is self-describing, and so that un-pinning later would be a change of scope rather than a schema migration.
- The key requires a stable `product_id`, which requires a resolvable `supplier_sku` per supplier format. **This is an open dependency**: the authoritative SKU field per format, and the behaviour when a record has no extractable SKU (quarantine versus synthesized identifier), are both unresolved. Until they are, products from formats without a clean SKU cannot be published idempotently.
- Products carrying a feature that ETIM does not define ("ETIM Other") have no `etim_feature_id` and therefore no key. Their handling is an open client decision; they are held out of the published set rather than given a synthetic identifier.
- The payload is wider than ADR-006's, so PIMS staging rows grow. Given the phase-one valve/actuator scope this is not a capacity concern, and carrying the evidence alongside the interpretation is what makes the published data auditable.
- ADR-006 is **not edited**. It stands as the record of the April decision and of the upsert mechanism, which this ADR reuses. Where the two disagree on the key, this ADR governs.

### Requirements Traceability

- **Spec:** Product Specification v1.4 (29 July 2026)
- **HLRs:** HLR-6 (enrich with ETIM identifiers); HLR-5 (write approved data back to PIMS)
- **FRs:** FR-8 (write attributes to PIMS upon final approval); FR-9 (preserve the original supplier value alongside the ETIM assignment)
- **DRs:** **DR-4** — *"Approved data written to PIMS shall be keyed by ETIM identifiers (release, class, feature); the writeback idempotency key shall include these identifiers"* — this ADR is the direct realization of DR-4; DR-3 (writeback must be idempotent; retry must not duplicate)
- **Constraints:** DC-3 (raw files preserved as evidence — the published row references that evidence)
- **Scenarios:** SCEN-1 step 5 and SCEN-2 step 6 (auto-accepted and human-approved data both take this path)
- **Validation:** VAL-3 (approve an item; the PIMS write succeeds and a retry does not duplicate — the retry case is now tested against the ETIM key)
- **Source:** `ETIM_IMPLEMENTATION_BRIEF.md` — PIMS Output Contract, PIMS Sync; `INGESTION_ETIM_PLAN.md` — design decisions
- **Tickets:** EPARTS-299 (writer rework), EPARTS-295 (PIMS sync); parent EPARTS-154 (Ingestion)
- **Related ADRs:** supersedes the natural key defined in ADR-006 while reusing its upsert mechanism; consumes the identifiers produced by ADR-016; depends on the release scoping of ADR-013; the datastore distinction is governed by ADR-015

---

## ADR-018: Extend Routing to ETIM Signals, with a Class-Review-First Path
### Status

Accepted

### Context

ADR-004 established per-attribute routing: each predicted attribute is compared against a configurable confidence threshold (ADR-005), and the attribute — not the whole record — goes to auto-accept or to the human review queue. The granularity decision was right and is unchanged by this ADR.

What changed is that a single confidence-versus-threshold comparison is no longer sufficient to decide whether a value is safe to publish. After ETIM there are several independent ways for an attribute to be unfit, and only one of them is low confidence:

- The **class** may be wrong or contested. Class confidence is a distinct signal from attribute-match confidence, and it dominates: every feature match under a wrong class is wrong, no matter how confident.
- The value may be confidently matched but **invalid against ETIM** — a type A value not in the legal set for that class-feature, a type N value with no unit, a type R range with min above max.
- The value may be valid but **fail client policy** — a feature the client marks `required` for this class is missing, which blocks publish regardless of how confident everything else is (ADR-019).
- **Unit conversion may have failed**, leaving a numerically plausible figure in the wrong unit. This is the most dangerous case: high confidence, valid type, wrong magnitude.

Routing on confidence alone would auto-accept all four of these. The consequence is the one thing the project exists to prevent: wrong product data reaching PIMS, and from there a contractor's field order.

A further problem is ordering. With a flat per-attribute queue, a product whose class is uncertain generates one review item per attribute — dozens of decisions that all become void the moment the reviewer changes the class. Alternatives considered:

- **Route on confidence only, catch validity later at publish time.** Keeps routing simple, but moves the failure to a stage with no human in it, so invalid data either blocks silently or is dropped.
- **Escalate any invalid attribute to whole-record review.** Safe but wasteful: one bad attribute pulls a hundred good ones into a manual queue, which is precisely the per-record behaviour ADR-004 rejected.

### Decision

Routing keeps its per-attribute granularity and gains a **class-level stage in front of it**.

**Stage 1 — class routing.** If ETIM class confidence is below the class threshold, or the top two candidate classes are within a configured margin of each other, the *product* is routed to class review before any attribute is matched. Attribute matching for that product is deferred until a class is confirmed.

**Stage 2 — attribute routing.** Once the class is settled, each attribute is routed on the full signal set:

| Signal | Effect |
|---|---|
| Attribute match confidence below threshold | → review |
| ETIM validation failure (value not in legal set, missing unit, malformed range) | → review, regardless of confidence |
| Unit conversion failure | → review, regardless of confidence |
| Client policy `required` and value missing | → review, and blocks publish for the product |
| Client policy `not_used` | → not published, not queued |
| All checks pass and confidence above threshold | → auto-accept |

The rule that governs the combination: **validation and policy failures are not overridden by high confidence.** Confidence answers "did we read it right"; validation answers "is it a legal ETIM value"; policy answers "does the client need it". These are independent questions and a failure in any one routes to a human.

Thresholds are externalized per ADR-005, now generalized to at least two — class-selection confidence and attribute-match confidence — with per-class-feature overrides replacing the per-attribute override table.

**Implementation status: designed, not built.** The signals this routing consumes are produced by the matching stages of ADR-016 (EPARTS-289/290/291), which are not yet in the running pipeline. Routing today evaluates confidence only.

### Consequences

- The highest-leverage failure mode — a confidently wrong unit or an out-of-vocabulary value — is now caught by a deterministic check rather than by hoping the model was unsure. This directly serves the data-integrity driver behind the whole platform.
- Class-review-first collapses what would have been dozens of void attribute decisions into one class decision. Reviewer throughput (QAS-2, 10 items/minute) is protected by not queuing work that is about to be invalidated.
- Deferring attribute matching until the class is confirmed introduces a **wait state** in the pipeline: a product can sit unprocessed pending a human class decision. The staging tables (ADR-014) hold that state durably, so nothing is lost, but end-to-end latency for uncertain products is now bounded by reviewer response time rather than by compute.
- More routing inputs means more ways to be wrong about routing. Each signal must be independently observable in telemetry — class confidence distribution, validation-failure rate, unit-conversion-failure rate, missing-required-field rate — or a regression in one will be invisible inside an aggregate auto-accept rate.
- Auto-accept rate will fall relative to the ADR-004 baseline, because attributes that previously passed on confidence now also have to pass validation and policy. This is the intended trade: throughput for correctness. The rate should be reported against the pre-ETIM baseline so the drop is not misread as a regression.
- The policy signal makes routing **dependent on client configuration that does not yet exist** (ADR-019). Until the feature policy is supplied, the policy check defaults to permissive — nothing is treated as required — which means the required-field path is designed but untestable.
- ADR-004 and ADR-005 are **not edited**. Per-attribute granularity and externalized thresholds are reused as decided; this ADR extends the inputs and adds a preceding stage.

### Requirements Traceability

- **Spec:** Product Specification v1.4 (29 July 2026)
- **HLRs:** HLR-4 (human review of low-confidence predictions); HLR-6 (ETIM classification and enrichment)
- **FRs:** FR-4 (route below-threshold items to the review queue); FR-7 (authorized Ops Leads adjust the auto-acceptance threshold); FR-9 (per-ETIM-assignment confidence is the signal being routed on); FR-3 (confidence score per prediction)
- **QASs:** QAS-2 Usability — class-review-first is what keeps the reviewer at 10 items/minute by not queuing work that a class change would void
- **Scenarios:** SCEN-2 steps 2–3 (a 0.45-confidence value routes to review; under this ADR it would also route on a validation or unit failure at any confidence)
- **Validation:** VAL-2 (mock a low-confidence response; the item appears in the review queue) — extended to cover validation-failure and unit-failure routing at high confidence. **VAL-5** (added in spec v1.4) is the specific test for class-review-first: a below-threshold class assignment routes to class review and no attribute-level routing happens for that item. Specified, not yet executable.
- **Source:** `ETIM_IMPLEMENTATION_BRIEF.md` — Request Router, Human Review, End-to-End Process steps 13–17
- **Tickets:** EPARTS-289 (class matching and class routing), EPARTS-294 (ETIM-aware review queue); parent EPARTS-156 (ML)
- **Related ADRs:** extends ADR-004 (per-attribute routing) and ADR-005 (externalized thresholds); consumes the staged outputs of ADR-016; depends on the policy overlay of ADR-019; the review-queue contract it feeds is ADR-009

---

## ADR-019: Externalize the Client Feature Policy as Per-Class Configuration
### Status

Accepted

### Context

ETIM tells us which features *exist* for a class. It does not tell us which ones *matter*.

`ETIMARTCLASSFEATUREMAP.csv` — the file that binds features to classes — contains `ARTCLASSFEATURENR`, `ARTCLASSID`, `FEATUREID`, `FEATURETYPE`, `UNITOFMEASID`, `SORTNR`. It contains no `required`, no `mandatory`, no `blocks_publish`, no `used_for_compare`. This is not an oversight in the export; ETIM is a shared industry dictionary and requiredness is a property of a particular catalogue's editorial standards, not of the standard.

The consequence is concrete and blocking. A valve class may define 60 features. A supplier datasheet may supply 12 of them. Whether that product is publishable depends entirely on which of the 60 the client considers required — and nobody has told us. Until someone does:

- **"What blocks publish?" is unanswerable**, so firm validation requirements cannot be written.
- The routing rule in ADR-018 that sends missing-required-features to review has no data to evaluate.
- The reviewer UI cannot distinguish "this field is empty and that is fine" from "this field is empty and the product cannot ship."

This is currently the project's most significant requirements risk, and it is owned by the client, not by us. Two open tickets (EPARTS-286 class scope, EPARTS-287 feature policy) are blocked on it.

The architectural question is what to do in the meantime. Alternatives considered:

- **Wait for the policy, then design around it.** Leaves the validation and routing paths unbuilt and the critical path idle on an external dependency with no committed date.
- **Hard-code a provisional policy** from our own reading of the valve datasheets. Fast, and wrong in a way that is expensive to detect: the system would enforce a standard nobody agreed to, and the resulting review queue would reflect our guesses rather than the client's requirements.
- **Derive requiredness statistically** — treat a feature as required if most suppliers populate it. Tempting, but it encodes current supplier behaviour as the target standard, which inverts the business objective. The client adopted ETIM precisely because current supplier coverage is inadequate.

### Decision

The feature policy is modelled as a **client-owned configuration overlay, external to the ETIM reference layer**, keyed per client, release, class and feature:

```
catalog_feature_policy(client_id, etim_release_id, etim_class_id, etim_feature_id)
  → requirement_level ∈ { required, recommended, optional, conditional, not_used }
    blocks_publish, used_for_compare, used_for_filter, display_order, condition_rule
```

Three properties of this decision matter more than the schema:

**It is an overlay, not an edit.** ETIM reference tables (ADR-013) store the standard exactly as published. Policy lives in its own table and joins on the ETIM keys. Policy revisions do not require reloading ETIM, and the standard's own structure is never edited to record a client preference.

**It is data, not code.** Changing requiredness for a class is a configuration change reviewed by the policy owner, not a deployment. Given that the client has not yet decided and will revise once they see real review volumes, requiredness must be cheap to change.

**The default is permissive and explicit.** Absent a policy row, a feature is treated as `optional` and nothing blocks publish. The system does not guess. Where a policy is absent and a value is missing, the product publishes with the gap recorded, rather than silently enforcing an invented standard.

The decision also creates a role that did not exist in the v1.0 baseline: a **feature-policy owner** on the client side who declares the levels and signs off on changes.

**Implementation status: the seam is decided; the values are pending.** The overlay's position in the architecture and its consumption by routing (ADR-018) and by the reviewer UI are settled. The policy content is an open client decision (EPARTS-287) and the table is not yet populated.

### Consequences

- The architecture stops being blocked on a client decision. Routing, validation and the reviewer UI can be built against the overlay's contract and exercised with a synthetic policy, then switched to the real one when it arrives.
- The **required-field path is designed but untestable end-to-end** until a real policy exists. Tests can prove that a `required` row routes correctly; they cannot prove the right features are marked required. This gap should be stated rather than papered over — a green test suite here does not mean the validation requirement is satisfied.
- Because policy is per-client, a second client with different editorial standards is a data addition rather than a code change. That is well beyond phase-one scope and is not being built for, but the key shape does not preclude it.
- `conditional` requires a rule language (`condition_rule`), and no rule language has been chosen. Conditional features are therefore accepted into the schema but not evaluated; they behave as `optional` until a rule evaluator exists. This is a known deferral, not an oversight.
- `used_for_compare` and `used_for_filter` are carried in the schema because the Compare Tool and website filter are the stated business motivation for ETIM adoption, but both consumers are **out of phase-one scope**. Storing the flags now avoids a migration later; populating them is deferred.
- Every policy change silently changes routing behaviour. Policy revisions must be versioned and correlated with review-queue volume, or an unexplained spike in the queue will be indistinguishable from a model regression.
- The permissive default means that until the policy lands, **no product will ever be blocked for a missing required field**. Auto-accept rates measured before the policy is populated are therefore optimistic and must not be quoted as steady-state figures.

### Requirements Traceability

- **Spec:** Product Specification v1.4 (29 July 2026)
- **HLRs:** HLR-6 (ETIM classification and enrichment); HLR-4 (human review of items needing attention)
- **FRs:** FR-9 (ETIM matching — policy validation gates what a match is sufficient for); FR-4 (routing to review); FR-7 (authorized adjustment of auto-acceptance behaviour, of which policy is now part)
- **Constraints:** C-3 (breadth-first delivery — a full end-to-end flow for one supplier type before optimizing depth; a permissive default is what allows the flow to complete)
- **QASs:** QAS-3 Modifiability (client feature policy) — added in spec v1.4 specifically to hold this decision: a policy change is configuration, applied to the next batch without a code deployment
- **Validation:** VAL-2 (routing) — the required-field branch is designed here and **cannot be validated until the policy is supplied**; this is a known open item, not a satisfied requirement
- **Source:** `ETIM_IMPLEMENTATION_BRIEF.md` — Important ETIM Limitation, Client Policy Tables
- **Tickets:** EPARTS-287 (feature policy — **blocked on client**), EPARTS-286 (phase-one class scope — **blocked on client**), EPARTS-294 (review UI consumes the policy)
- **Open client decisions this ADR holds a place for:** feature policy per class; required-field publish blockers; Compare Tool and website-filter feature sets; mapping and policy sign-off ownership
- **Related ADRs:** deliberately kept out of the reference layer of ADR-013; supplies the policy signals routed on in ADR-018; the validation stage that consumes it is part of ADR-016; the reviewer contract that displays it is ADR-009

---

## ADR-020: Pin ETIM Release 10.0 (EI) for the Project Duration
### Status

Accepted

### Context

ETIM is an external standard with its own release cadence. We loaded **ETIM 10.0, language EI**. There will be an 11.0, and between releases classes are added, features are added and deprecated, values are withdrawn, and a class's feature set changes shape.

That raised a question the v1.0 baseline had no equivalent of: what does the platform do when the standard moves underneath it? Two things made it pressing. Requirements written against "the ETIM standard" are implicitly written against a specific release, so the traceability chain from HLR-6 through FR-9 to a published PIMS row is only meaningful if the release is part of the record. And an unmanaged upgrade silently reinterprets historical data — a value that was legal under 10.0 can be invalid under 11.0, and either the row breaks or, worse, it stays and nobody knows which release's rules it satisfies.

Three options were considered.

- **Build a governed upgrade path now.** Load each new release alongside the old one, diff them, re-match affected products through a review queue, and reconcile the client's feature policy against the diff before cutover. Architecturally clean, and it makes upgrades visible rather than silent. But it is a substantial amount of work — a diff report, a bulk re-match path, a second review queue — for an event that will not occur inside this project. It also could not be finished: who authorizes an upgrade, on what trigger, and what happens to already-published rows are client decisions nobody has made.
- **Leave the question open.** Say nothing and handle a future release when it arrives. Rejected because "unspecified" is not the same as "out of scope". FR-10 as originally worded — maintain the dictionary as *versioned* reference data — implies an obligation we were not going to meet, and an assessor or a future maintainer would reasonably read it as a commitment.
- **Pin the release explicitly and put the upgrade path out of scope.** Chosen.

### Decision

**The platform targets ETIM release 10.0, language EI, for the duration of this project.** Adopting later ETIM releases, and migrating already-classified products between releases, are **out of scope**.

This is recorded as **constraint C-4**, introduced in Product Specification **v1.2**, and FR-10 is scoped to "the pinned ETIM release identified in C-4" rather than to versioned reference data generally.

The **release-scoping mechanism in the schema stays exactly as it is.** Every ETIM reference row carries `etim_release_id`, with composite primary keys on `(etim_release_id, …)` across all ten tables (ADR-013); the release is carried through `matched_product_attribute` (ADR-014) and forms part of the PIMS writeback key (ADR-017). Under a pin that field is constant in practice, and we are keeping it for two reasons:

1. **Provenance.** Every published value names the release it was matched under. "This value was matched against ETIM 10.0 EI, on this date, under this policy" stays recoverable from the row alone, which is what makes the audit trail meaningful later.
2. **It costs nothing.** The columns and keys are already built and tested. Removing them to reflect the pin would be work that buys no capability and discards the provenance.

So this ADR narrows the *forward-looking justification* in ADR-013 — release-scoping is no longer defended as a step toward governed upgrades — without changing a line of the schema it describes. ADR-013 is not edited.

If the client later asks for a new ETIM release, that is a **change request against C-4**, and the first option above is the shape the work would take. It is not a gap to be quietly filled.

### Consequences

- The project stops carrying an obligation it was never going to discharge. FR-10 is now satisfiable and testable as written: load and maintain one named release.
- No diff report, no bulk re-match path, no second review queue, and no upgrade-governance owner to chase. This is the largest piece of scope the decision removes, and it removes it in the phase where the critical path is `285 ‖ (297 → 298 → 299)`.
- **We are deliberately accepting that the catalog will go stale** relative to ETIM. If the client's suppliers begin publishing against 11.0 while we classify against 10.0, new classes and features are simply unavailable to us, and products needing them fall to "ETIM Other" handling or to review. For a phase-one valve/actuator pilot that is acceptable. For a production catalogue with a multi-year life it would not be, and this ADR should be revisited before any such transition.
- Provenance is preserved without the machinery. Because `etim_release_id` remains in the reference tables, the interpretation table and the PIMS key, a future un-pinning is a change of scope rather than a schema migration. The door is left open at zero cost.
- **The loader keeps its release-mismatch rejection.** It validates that an archive matches the declared release and refuses a mismatched or truncated one (ADR-013). Under a pin that check becomes more valuable, not less — it is what stops an 11.0 archive being loaded into a 10.0-pinned system by accident.
- The `etim_release_id` field will look redundant to anyone reading the schema without this ADR. That is the cost of keeping it, and this ADR is the answer.
- One open client decision is closed. "ETIM release-upgrade governance" comes off the blocked list, taking the open-decision count from six to five.

### Requirements Traceability

- **Spec:** Product Specification **v1.4** (29 July 2026); C-4 was introduced in v1.2 (28 July) — this ADR is the reason for that version
- **Constraints:** **C-4** (ETIM Release Pinned) — this ADR is the decision C-4 records
- **HLRs:** HLR-6 (classify against the ETIM standard — this ADR fixes *which* ETIM)
- **FRs:** **FR-10** (load and maintain the ETIM reference dictionary for the pinned release); FR-9 (matching is always against release 10.0 EI)
- **DRs:** DR-4 (the release remains part of the PIMS writeback key, so publication stays release-explicit)
- **QASs:** QAS-1 Modifiability — un-pinning would be a scope change, not a structural change to the pipeline
- **Constraints (supporting):** C-1 (cost-effective design — the upgrade path is the expensive option and is deliberately not built); C-3 (breadth-first delivery — one supplier type end to end before adding depth)
- **Source:** `ETIM_IMPLEMENTATION_BRIEF.md`; `ETIM-ADR-ASSESSMENT.md` raised this as *"Standard evolution (currency): ETIM releases (10.0 → next); upgrade governance undefined"* — this ADR resolves that item by scoping it out rather than by building for it
- **Closes:** the open client decision "ETIM release-upgrade governance"
- **Related ADRs:** narrows the forward-looking rationale of **ADR-013** (release-scoped reference layer) without editing it; the release remains in **ADR-014**'s interpretation table and **ADR-017**'s writeback key for provenance; **ADR-019**'s policy overlay no longer needs reconciling against a release diff

---

## ADR-021: Formalize the Ingestion → ML Boundary as a Frozen `ExtractedInput` Record
### Status

Accepted

### Context

ADR-001 established pipe-and-filter as the platform's style, with filters communicating through typed data channels. In practice the ingestion→matching channel was the weakest of them: ingestion parsed a supplier file into a `RawRecord` and the matching stream read whatever fields happened to be there. Adequate while both sides were one team and one process; untenable now.

Three pressures forced the boundary to become explicit.

**It is a cross-team contract.** Ingestion (EPARTS-154) and ML matching (EPARTS-156) are separate streams with separate backlogs. The ETIM requirements-change record names this contract as one of two places where our traceability deliberately stops — we own the requirement, another stream owns the implementation. A trace boundary that is not a schema boundary is not a boundary at all.

**Ingestion must not leak interpretation.** ADR-014 established the principle that supplier data is *evidence* and ETIM is a *standardized interpretation* over it. If ingestion hands the matcher a confidence score or a ranked list of candidate attribute names, it has already begun interpreting, and the evidence/interpretation split becomes a convention rather than a property of the system. The temptation is real: the OCR path (Azure Document Intelligence plus an LLM extraction) *has* per-field confidences available, and passing them along would be a one-line change.

**Source provenance differs by channel and matters downstream.** A value read from a CSV cell, a value read from a text-native PDF, and a value read from OCR over a scanned page carry different reliability, and the matcher and the reviewer both need to know which they are looking at. A generic dictionary of fields loses that.

Alternatives considered:

- **Keep passing `RawRecord`.** Zero work, and it makes every ingestion-side refactor a potential silent break for the ML stream, because nothing declares what the ML stream is entitled to rely on.
- **Put the boundary behind an HTTP service now.** Genuinely the right long-term shape, and premature: it adds deployment, retry and tracing surface for a boundary that currently runs in one process. ADR-008's single-deployable-unit decision still holds; what this ADR fixes is the *contract*, not the *topology*.
- **Document the contract in prose only.** The 460-line handoff specification already exists. Documentation that is not enforced drifts, and this contract's whole value is that it cannot drift.

### Decision

The ingestion→ML boundary is a **single, versioned, schema-frozen record type**, `ExtractedInput`, specified in `docs/extraction_handoff_spec.md` and enforced in code:

| Field | Meaning |
|---|---|
| `source_type` | one of `csv`, `email`, `pdf_text`, `pdf_ocr`, `image` — the channel, so the consumer knows what kind of evidence this is |
| `text` | the extracted text; required, and an empty string is valid |
| `structured_fields` | the parsed field/value pairs as the supplier wrote them |
| `normalized_units` | mechanical unit normalization only, as `(value, unit)` pairs |
| `source_ref` | pointer back to the archived raw artefact |

Two properties do the real work.

**The schema forbids interpretation by construction.** The Pydantic model is declared `extra="forbid"` and `frozen=True`. Confidence scores, ranked alternates, predicted ETIM classes — anything that constitutes an interpretation — *cannot be represented*, so they cannot cross the boundary by accident. The evidence/interpretation split of ADR-014 is enforced by the type system rather than by reviewer vigilance.

**The record is persisted, not just passed.** `extracted_inputs` (Alembic `0007`) stores each handoff record, which turns the boundary into a durable checkpoint: the matching stream can be down, restarted, or re-run against the same inputs without re-doing OCR, and a matching bug can be diagnosed against exactly the input that produced it.

Cleaning (spec §3) and unit normalization (spec §4) are injectable seams on the ingestion side of the boundary. This keeps mechanical tidying — whitespace, encoding, unit spelling — with the party that knows the source format, while leaving anything requiring domain judgement to the matcher.

**Implementation status: built and merged.** `handoff/spec_model.py`, `handoff/builder.py`, `models/extracted_input.py` and migration `0007` are on the main line (EPARTS-357, EPARTS-358). The cleaning and unit implementations (EPARTS-359, EPARTS-362) and the provenance split between `pdf_text` and `pdf_ocr` (EPARTS-361) are on open branches; on the main line those seams are pass-throughs. Wiring the builder into the orchestrator is EPARTS-363 and is not yet done, so the record type exists and is validated but is not yet produced on every run.

### Consequences

- The two streams can move independently. Ingestion can change parsers, add a channel, or swap the OCR engine without coordinating, so long as the record still validates. The ML stream has a written, enforced statement of what it may rely on.
- **`extra="forbid"` will reject rather than ignore** an ingestion-side addition. That is the intended behaviour — it makes contract changes loud — but it means adding a field is a deliberate, two-team, spec-versioning act, not a convenience. Expect this to feel obstructive at least once; that is the cost being paid on purpose.
- Persisting the record makes matching **replayable**. Re-running the matcher over stored `extracted_inputs` costs nothing in Azure Document Intelligence or LLM calls, which materially changes the economics of iterating on the matching stages of ADR-016.
- This turns ADR-001's in-process function call into an explicit asynchronous seam, and it is consequently **the leading candidate for extraction into a service** if the deployment topology of ADR-008 is ever revisited. Nothing about the contract assumes co-location.
- The boundary is a queue-shaped thing without a queue. Delivery today is a table plus a poll; the transactional outbox and circuit breaker planned under EPARTS-301 are not built. Until they are, there is no delivery guarantee beyond "the row is committed" — adequate, because the row *is* the durable state, but not the same as at-least-once delivery to a live consumer.
- The record carries no confidence, which means the matcher cannot preferentially trust a high-confidence OCR field over a low-confidence one. This is a deliberate loss of information: OCR confidence measures character recognition, not semantic correctness, and treating it as the latter is the mistake the split exists to prevent. If the matcher later needs a reliability signal, it should come from `source_type` and from measured per-channel accuracy, not from the OCR engine's self-report.
- Because the builder is not yet wired into the orchestrator, the contract is currently **enforced but unexercised in production flow**. The unit tests validate the shape; no end-to-end run has yet produced a record. This should not be described as a working boundary until EPARTS-363 lands.

### Requirements Traceability

- **Spec:** Product Specification v1.4 (29 July 2026)
- **HLRs:** HLR-2 (normalize into a standardized intermediate structure preserving original supplier values as evidence); HLR-1 (ingest from diverse supplier sources — `source_type` enumerates the channels); HLR-3 (the ML service that consumes this record)
- **FRs:** FR-1 (ingestion record with supplier, timestamp, source channel); FR-2 (validation before processing — an invalid handoff record is a validation failure, not a silent pass); FR-9 (matching consumes this record)
- **DRs:** DR-1 (raw file archived as evidence — `source_ref` is the pointer to it)
- **QASs:** QAS-1 Modifiability — a new supplier format is a new `source_type` and a new parser; the boundary and everything downstream of it are unchanged
- **Constraints:** DC-1 (Python backend); DC-3 (raw files preserved for re-processing and traceability — replayability depends on this)
- **Scenarios:** SCEN-1 step 3 and SCEN-2 step 1 (both scenarios cross this boundary; SCEN-2's OCR path is `pdf_ocr`)
- **Source:** `docs/extraction_handoff_spec.md` (§1 channels, §2 record shape, §3 cleaning, §4 unit normalization, §5 structured fields, §6 per-channel examples)
- **Tickets:** EPARTS-357 (schema + migration `0007` — Done), EPARTS-358 (builder + spec model — Done), EPARTS-359 (units), EPARTS-361 (pdf_text/pdf_ocr provenance), EPARTS-362 (text cleaning), EPARTS-363 (orchestrator wiring — **not done**), EPARTS-301 (transactional outbox — not built); contract boundary between EPARTS-154 (Ingestion) and EPARTS-156 (ML)
- **Related ADRs:** makes explicit the filter boundary of ADR-001; enforces the evidence/interpretation split of ADR-014; feeds the matching stages of ADR-016; does not alter the single-deployable-unit topology of ADR-008, but is the natural extraction point if that is revisited
