# eParts Services LLC — Intelligent Ingestion & Attribute Prediction Platform

## Final Project Report Draft

**Team: Pimsie Supreme**

**Team Members:**
- Arjun R Nair
- Ashritha Gonuguntla
- Hrishikesh Bhardwaj
- Jaivardhan Singh
- Zheliang Liu

**Date:** April 15, 2026

---

## 1. Project Context and System Boundary

### 1.1 Problem Context

eParts Services LLC maintains product data for an eCommerce procurement platform serving construction contractors, with PIMS (Product Information Management System) as the primary system of record. Supplier catalogs arrive in heterogeneous formats including CSV files, PDFs, email attachments, SFTP drops, and direct uploads. The current ingestion workflow is entirely manual: catalog staff at eParts (~1.5 FTEs) and sister company Alps Controls (~3 FTEs) interpret, normalize, and map every supplier attribute before it enters PIMS. This process is error-prone, slow to update, and does not scale.

The CMU MSE Studio Capstone Team (Pimsie Supreme) has been engaged to design an Intelligent Product Data Ingestion and Enrichment Platform that automates this pipeline. The goal is to reduce manual effort while keeping data written into PIMS correct. Incorrect product data causes wrong parts to be ordered by contractors, so data integrity drives every architectural decision.

### 1.2 Stakeholders

| Stakeholder | Architectural Relevance |
|---|---|
| Harsha (eParts) | Sets accuracy threshold priority; chose valves/actuators scope; approves model selection |
| Jake (eParts) | PIMS integration; defines write interface and staging table contracts (P1-C pending) |
| Brian & Dewey (eParts) | Catalog team; primary review workflow users; define low-confidence handling |
| Alps Controls Catalog Team | Secondary users (3 FTEs) the architecture must accommodate |
| David (eParts) | Executive sponsor; resource allocation across teams |
| CMU Studio Team | Design, prototyping, delivery; makes architectural decisions |

### 1.3 System Boundary

The system boundary encloses the path from raw supplier files through ML prediction and controlled writeback into PIMS staging tables. Inside: ingestion/parsing, canonical schema normalization, attribute prediction with confidence scoring, confidence-based routing, a persistent review queue, idempotent writeback, and observability (Datadog). No custom review UI is in scope for the current phase.

Out of scope: downstream systems beyond PIMS, configurable product Options, direct production DB writes, and pricing data in the ML pipeline. Web scraping is a potential future ingestion channel but is not implemented in the current phase; the Ingestion Gateway is designed to accommodate additional input formats without structural change.

### 1.4 System Context and External Dependencies

Figure 1 shows the system in relation to its external actors: suppliers (via email, SFTP, CSV, PDF), human reviewers (Merch Ops), PIMS (SQL Server staging tables), and Datadog. Key external dependencies are captured as constraints in Section 2.2.

> **Figure 1:** System Context Diagram (V3.0, 02/20/26). *[Image: `Context Diagram V3.png`]*

---

## 2. Architectural Drivers

### 2.1 Functional Architecture Drivers

The functional requirements below shape system structure, interfaces, coordination, and evolution.

- **FR-1: Multi-Format Ingestion.** Accept CSV and PDF catalogs via email, SFTP, and direct upload, recording supplier, timestamp, and channel. Drives the Ingestion Gateway as a distinct component.
- **FR-2: Canonical Schema Normalization.** Transform heterogeneous formats into a standardized staging table, decoupling parsing from prediction.
- **FR-3: Per-Attribute ML Prediction with Confidence Scoring.** Prediction at the attribute level (not record level) because routing is per-attribute. Justifies the Prediction Service as a separable component.
- **FR-4: Confidence-Based Routing.** Distinct Routing Engine separates auto-accept from human review so routing logic is adjustable without touching the model.
- **FR-5: Persistent Human Review Queue.** Low-confidence predictions held in a queryable queue, decoupling machine throughput from reviewer availability. Corrections feed retraining.
- **FR-6: Idempotent PIMS Writeback.** No duplicates on retry; enforced in application layer because no writeback API exists.
- **FR-7: Decision Logging and Audit Trail.** Every auto-accept, approval, correction, and rejection logged for auditability and model improvement.

### 2.2 Constraints

| Constraint | Source | Status | Architectural Impact |
|---|---|---|---|
| Azure deployment | Client mandate | Fixed | Eliminates non-Azure infrastructure |
| No PIMS writeback API | eParts env (Jake) | Fixed | Idempotency in app code; no rollback |
| Python backend for ML | ML library compat (SOW) | Fixed | Interop layer needed for .NET stack |
| Valves/actuators scope | Client (Harsha) | Fixed (phase) | Schema scoped; expansion must not be blocked |
| No direct prod DB writes | Data governance | Fixed | All ML writes to staging; human verify first |
| No pricing in ML pipeline | Privacy policy (SOW) | Fixed | Pricing excluded from ingestion/prediction |
| Capstone team/timeline | CMU structure | Fixed | Must be prototypable by small team, Spring–Fall 2026 |
| Auth0 for RBAC | eParts identity | Negotiable | Stretch goal; not current-phase constraint |

*Table 1: Constraints, sources, and architectural impacts*

### 2.3 Quality Attributes

| QA | Source | Stimulus | Env. | Artifact | Response / Measure | I/D |
|---|---|---|---|---|---|---|
| Accuracy | Pred. Svc | Batch of normalized attributes submitted | Normal ops | Pred. Svc, Routing Engine | Routing Engine compares per-attribute confidence against threshold; below-threshold diverted to review queue; above-threshold auto-accepted. *M:* ≥95% auto-accept correct; zero incorrect records to PIMS outside review. | H/H |
| Modifiability (model swap) | ML Lead | Replace prediction strategy (e.g., hybrid → DistilBERT) | Design time, Ph. 2 | Pred. Svc | New class behind `PredictionServiceInterface`; selected via config. *M:* Change in `prediction` pkg only. | H/M |
| Modifiability (new cat.) | eParts | New product category post-pilot | Post-pilot | Schema, Gateway, Pred. Svc | New attribute mappings + schema extension + retrain. *M:* No structural change to routing/writeback. | M/M |
| Availability | Infra fault | Prediction Service unavailable | Normal ops | Pred. Svc, Gateway | Staging tables buffer data; resumes on recovery. *M:* Zero data loss. | M/L |
| Monitorability (drift) | Eng. Ops | Supplier data shifts from training distribution | Production | Pred. Svc, Datadog | Emits confidence distributions + correction rates to Datadog; alerts on baseline deviation. *M:* Drift detected before accuracy drops below QA-1. | H/H |

*Table 2: Quality attribute scenarios and utility-tree prioritization*

#### Prioritization Justifications

- **Accuracy (H/H):** Incorrect data causes wrong parts ordered — business-critical. Threshold and model behavior both unresolved.
- **Modifiability–swap (H/M):** Model selection still open; boundary must be drawn now or swaps ripple.
- **Modifiability–category (M/M):** Current scope is valves/actuators; schema must avoid category-specific lock-in.
- **Availability (M/L):** System not on critical path; catalog team is fallback. Staging-table buffer is straightforward.
- **Monitorability (H/H):** Silent degradation is an operational risk; drift metrics and baselines are undefined.

### 2.4 Priorities, Tensions, and Open Uncertainty

Accuracy is the dominant driver. The main tension is between accuracy and throughput: tightening the threshold reduces incorrect auto-accepts but increases review workload. A second tension is simplicity now vs. modifiability later. The biggest open uncertainty is the confidence threshold, which cannot be set until the prototype produces real predictions. Model selection is the second open question.

---

## 3. Proposed Architecture

### 3.1 Primary Architectural Style: Pipe and Filter

The system follows a **pipe-and-filter** style [Bass et al., 2012]: independent filters connected by typed data channels form a linear transformation pipeline. This style was selected for three traced reasons: **modifiability (QA-2)** — each filter communicates through defined data contracts, so the Prediction Service can be replaced without affecting upstream or downstream; **modifiability (QA-3)** — adding a category requires extending the schema and retraining, not changing the filter sequence; and **availability (QA-4)** — staging tables buffer data during Prediction Service outages.

The one departure from a linear pipeline is a **confidence-based branch**: the Routing Engine sends high-confidence attributes to auto-accept and low-confidence to human review; both paths merge before writeback. The audit trail feedback loop operates offline.

### 3.2 Key Tactics

#### Tactic 1: Stable Internal Interface for Model Isolation (QA-2, FR-3)

The Prediction Service exposes `PredictionServiceInterface`: accepts normalized records, returns predictions with per-attribute confidence scores. For the hybrid approach (ADR-1), this score is a weighted composite:

$$\text{conf}_{\text{final}} = \alpha \cdot \text{conf}_{\text{rule}} + (1-\alpha) \cdot \text{conf}_{\text{embed}}$$

The Routing Engine depends on this interface, never on model internals. We chose an internal function-call interface over REST/message queue (Section 4.1) because network boundaries would add complexity disproportionate to team size.

#### Tactic 2: Per-Attribute Configurable Threshold (QA-1, FR-4)

Each attribute carries its own confidence score; the Routing Engine compares it against a configurable threshold. The threshold is externalized as configuration because it cannot be set until Phase 2 (Section 2.4).

#### Tactic 3: Idempotent Writeback via Natural Key (QA-1, FR-6)

PIMS has no writeback API, so idempotency is enforced via natural key matching (`submission_id` + `attribute_id`): existing records are updated rather than duplicated on retry.

#### Tactic 4: Queue Decoupling (QA-4, FR-5) and Tactic 5: Audit Logging (FR-7, QA-5)

The Human Review Queue is a persistent DB table (not in-memory), decoupling prediction throughput from reviewer pace and buffering during outages. Every pipeline decision is logged in an append-only audit trail with prediction, confidence, source file, and reviewer ID, supporting both compliance and offline retraining.

### 3.3 Architectural Views

#### 3.3.1 View 1: Component-and-Connector (Figure 2)

This view answers: *how does data flow from raw input to PIMS, and where does confidence-based branching occur?* The pipeline is linear with one branch at the Routing Engine; both paths merge before a single write path to PIMS. Telemetry flows from four stages to Datadog; audit feedback is offline.

> **Figure 2:** C&C view. Teal = filters, blue dashed = stores, coral = human review, purple = PIMS. Solid = pipes, dashed = telemetry. Diamond = routing decision. *[Image: `pipe_filter_cnc.png`]*

#### 3.3.2 View 2: Module (Figure 3)

Answers: *where are the abstraction boundaries for model swapping and schema extension?* The codebase is organized into eight packages: `ingestion` (format detection, OCR, CSV/PDF parsing, file archival), `normalization` (transforms raw attributes into canonical schema using supplier-specific column mappings), `prediction` (contains `PredictionServiceInterface` and concrete implementations; active strategy selected via configuration), `routing` (reads confidence scores against threshold, produces per-attribute routing decisions), `review` (manages persistent Human Review Queue), `writeback` (idempotent upsert to PIMS via natural key), `audit` (append-only decision logger), and `observability` (structured logging and metrics for Datadog).

**Key dependency rule:** The `routing` package imports `PredictionResult` (a data class), not any model-specific type. The `writeback` package imports from routing output, not from `prediction`. This enforces model isolation (Tactic 1): changes to the prediction strategy cannot ripple past the `PredictionResult` boundary.

#### 3.3.3 View 3: Deployment (Figure 4)

Answers: *how are components allocated to Azure, and where are trust boundaries?* The system is deployed as a single application unit on Azure App Service (Python), driven by the team size constraint: a microservices deployment would require container orchestration and distributed tracing infrastructure that exceeds the team's operational capacity (alternatives analyzed in Section 4.3). Azure SQL Database holds all internal pipeline state (staging tables, review queue, audit trail); Azure Blob Storage archives raw supplier files for traceability. The Publish/Sync Job runs as a timer-triggered Azure Function that reads approved output and writes to PIMS.

**Integration points:** Inbound data arrives via SFTP (polled), email (polled), and HTTP upload — all treated as untrusted. Outbound to PIMS via `pyodbc` across the trust boundary (idempotency enforced in application code). Outbound to Datadog via HTTPS (fire-and-forget; telemetry failures do not block the pipeline).

> **Figure 3:** Module view. Dashed boundary = model isolation. *[Image: `module_view.png`]*
>
> **Figure 4:** Deployment view. Trust boundary separates Azure from PIMS. *[Image: `deployment_view.png`]*

### 3.4 Traceability from Drivers to Design

| Driver | Decision | Effect |
|---|---|---|
| QA-1: Accuracy | Per-attr scoring + threshold + idempotent write | Above-threshold auto-accepted; low-confidence reviewed; no duplicates |
| QA-2: Model swap | `PredictionServiceInterface` | Change localized to `prediction` package |
| QA-3: New category | Attribute-row canonical schema | New mappings + retrain; no structural change |
| QA-4: Availability | Staging buffers + persistent queue | Outage = data queued; zero loss |
| QA-5: Monitorability | Telemetry + audit trail | Drift via correction rate deviation |
| Azure / Team size | Single App Service + SQL + Blob | Avoids microservice overhead; extractable later |

*Table 3: Traceability from drivers to design*

---

## 4. Architectural Alternatives

Three architecturally significant concerns, each with plausible alternatives compared structurally.

### 4.1 Concern 1: Model Isolation Mechanism

**Driver:** QA-2 (H/M). Determines codebase impact of a swap, redeployment scope, and side-by-side evaluation capability.

- **Alt A: Internal Abstract Interface (current).** `PredictionServiceInterface` in a single app; swap = new class + config change. Nothing outside `prediction` changes.
- **Alt B: REST Microservice.** Prediction Service extracted to separate Container App. Deployment view gains a second unit; pipe becomes HTTP call. Enables canary deployment.
- **Alt C: Message Queue (Service Bus).** Async broker-mediated communication. Two queues introduced; retry/dead-letter offloaded to Service Bus.

| Criterion | A: Interface | B: REST | C: Queue |
|---|---|---|---|
| Swap effort | Config + class; single redeploy | Independent deploy | Independent deploy |
| Side-by-side | In-process branching | Canary at LB level | Competing consumers |
| Op. overhead | Minimal | Container orch., health checks, svc auth | Queue provisioning, dead-letter, schema version |
| Team fit | High | Low–Med | Low |

*Table 4: Model isolation — alternatives comparison*

**Choice: A.** Sufficient for design-time swaps in Phase 2; B/C operational cost exceeds team capacity. **B preferable when:** production handoff; canary deployments or GPU-backed inference needed. **C preferable when:** near-real-time ingestion with multiple consumers.

### 4.2 Concern 2: Confidence Routing Granularity

**Driver:** QA-1 (H/H), accuracy-vs-throughput tension. This is structural: different data models, merge logic, and reviewer interfaces.

- **Alt A: Per-Attribute (current).** Each attribute routed independently; review queue keyed at (record, attribute); writeback must merge auto-accepted and reviewed attributes.
- **Alt B: Per-Record.** Entire record to review if any attribute below threshold; no merge logic needed.

| Criterion | A: Per-Attribute | B: Per-Record |
|---|---|---|
| Review volume | Lower (est. 3–5× reduction) | Higher: full record for 1–2 uncertain attrs |
| Reviewer context | Flagged attrs only; source file available | Full record visible |
| Writeback | Merge auto-accepted + reviewed | Records always complete |
| Accuracy risk | Correlated attrs may be inconsistent | No cross-attr inconsistency |

*Table 5: Routing granularity — alternatives comparison*

**Choice: A.** Catalog team (1.5 + 3 FTEs) is the bottleneck; merge complexity localized to `writeback`. **Key risk:** correlated attributes (e.g., connection type + port size); mitigated by logging full record context but not yet validated. **B preferable when:** >30% of corrections involve cross-attribute errors.

### 4.3 Concern 3: Deployment Topology

**Driver:** Team size constraint, QA-4, QA-2. Interacts with Concern 1.

- **Alt A: Single App Service (current).** All components in one process; function-call communication; scales as a unit.
- **Alt B: Microservices (Container Apps).** Three independent services: Ingestion/Normalization, Prediction, Routing/Writeback. In the deployment view, the single App Service box (Figure 4) would be replaced by three Container App instances with HTTP/Service Bus connections.

| Criterion | A: Single Unit | B: Microservices |
|---|---|---|
| Op. complexity | Low: one deploy, one log stream | High: three deploys, distributed tracing |
| Fault isolation | Low (shared process); mitigated by buffers | High: independent restarts |
| Scaling | Whole app scales as unit | Prediction Service scales independently |
| Timeline fit | High: 5-person team, one semester | Low: infra setup consumes timeline |

*Table 6: Deployment topology — alternatives comparison*

**Choice: A.** Module boundaries (View 2) drawn where service boundaries would go, so transition = adding network serialization at existing interfaces, not rewriting. **B preferable when:** (1) production handoff to larger team, or (2) Prediction Service needs GPU instances.

---

## 5. Architecture Analysis

### 5.1 Why the Architecture Is Plausible

The pipe-and-filter architecture is plausible for this project for three reasons. First, the core problem — transforming heterogeneous supplier catalogs into validated PIMS records — is fundamentally a linear data transformation pipeline, and the pipe-and-filter style maps directly onto this data flow without forcing artificial concurrency or event-driven coordination.

Second, the architecture is feasible given the team's constraints. A five-person capstone team operating from Spring to Fall 2026 cannot sustain the operational overhead of distributed microservices, event-driven choreography, or multi-model orchestration frameworks. The centralized deployment (AD-6) keeps infrastructure management minimal while the modular internal package structure preserves the option to decompose later. This is a deliberate sequencing decision: build the correct abstractions now, defer operational complexity until an eParts engineering team can absorb it.

Third, the architecture mirrors what eParts already does manually. The current workflow — catalog staff interpreting supplier files, normalizing data, and entering it into PIMS — maps onto the same filter sequence. The architecture automates each stage while preserving the human-in-the-loop at exactly the point where automation confidence is low. This reduces the risk that the architecture solves the wrong problem.

### 5.2 Traceability: Are Design Choices Proportional?

**Accuracy (H/H):** Three decisions work in concert — confidence scoring identifies risk, the threshold controls acceptable risk, idempotent writeback prevents mechanical errors. Removing any one leaves a gap in the accuracy guarantee. The traceability is strong because each decision addresses a different failure mode: scoring prevents silent misclassification, the threshold prevents over-trust in the model, and idempotency prevents duplicate records from retries.

**Modifiability–swap (H/M):** `PredictionServiceInterface` isolates the prediction strategy. We favor the internal interface over REST because model swaps are design-time activities in Phase 2; if canary deployments are later needed, Section 4.1 Alt B becomes necessary. This depends on the assumption that the team will not need to run two models simultaneously in production during the capstone phase.

**New category (M/M):** Attribute-row schema trades query convenience for extensibility — justified because schema migrations against production PIMS carry disproportionate risk and would require coordination with Jake's team.

**Availability (M/L):** Staging-table buffers are minimal complexity — proportional to a medium-importance driver. We deliberately invested less architectural effort here because the catalog team remains a manual fallback if the system is down.

**Monitorability (H/H):** Structurally realized (telemetry from four pipeline stages, audit trail capturing correction rates) but operationally incomplete — baseline metrics, alert thresholds, and the correction-to-retraining feedback loop have not been defined. This is the key gap: the architectural scaffolding exists, but the operational content that makes it useful is empty. Refinement Activities 1 and 3 are designed to fill this gap.

### 5.3 Tradeoffs

**Tradeoff 1: Accuracy vs. Throughput.** We favor accuracy because incorrect PIMS data causes wrong parts to be ordered — a business-critical failure the client has stated is unacceptable. This is reinforced by per-attribute routing, which keeps review volume proportional to actual model uncertainty. The tradeoff depends on the assumption that the catalog team's capacity (1.5 + 3 FTEs) is sufficient for the review volume at the chosen threshold. If the prototype reveals that even per-attribute routing produces a workload above the team's demonstrated handling capacity, the team would need to either lower the threshold (accepting more accuracy risk) or invest in reviewer tooling that accelerates per-attribute review.

**Tradeoff 2: Simplicity vs. Modifiability.** The architecture consistently chooses simpler implementations now (internal interface over REST, centralized deployment over microservices, hybrid prediction over pure ML) while investing in interfaces that preserve future options. We are favoring simplicity because the capstone timeline is the binding constraint, but this depends on the assumption that the modular internal structure is sufficient to prevent a costly rewrite when the system transitions to production. If eParts takes ownership and immediately requires independent scaling of the Prediction Service, the centralized deployment would need to be revisited first — but the module boundaries in View 2 are designed to make this transition a refactoring effort rather than a rewrite.

**Tradeoff 3: Explainability vs. Sophistication.** The hybrid approach (ADR-1) generates reason codes satisfying eParts' explainability requirement (§6.5). A pure ML classifier could achieve higher accuracy with sufficient training data but produces opaque confidence scores. We favor explainability because trust in routing decisions is essential for catalog staff adoption — a system that routes items to review without explaining why will be treated as a black box. This depends on reason codes being useful to Brian and Dewey in practice, which has not been validated (Refinement 5 tests this).

### 5.4 Risks and Unresolved Issues

**Risks:**
1. **Threshold miscalibration** (0.85 unsupported) — if too high, review queue overwhelms catalog team and the system provides no labor savings; if too low, incorrect data enters PIMS.
2. **Insufficient training data** — if fewer than 200 labeled examples are available, the embedding layer will be undertrained and the hybrid approach falls back toward pure rules.
3. **PIMS schema incompatibility** — Jake has not delivered the P1-C schema; if staging tables use wide columns or lack key columns, the writeback mechanism needs redesign.

**Sensitivity points:**
1. The α weighting in hybrid scoring — small tuning errors have outsized effects on routing behavior.
2. Attribute correlation strength — determines whether per-attribute routing is safe or introduces inconsistency.
3. Catalog team capacity vs. review volume — the entire value proposition depends on this balance.

**Unresolved:**
1. Drift detection metrics and baselines not defined.
2. Per-attribute vs. global threshold — some attributes (e.g., `SUPPLY_VOLTAGE`) are inherently easier to predict than others (e.g., `DESCRIPTION`).
3. Human review interface design not decided.
4. Corrections-to-retraining feedback loop not architecturally specified.

### 5.5 Conditions for Reconsideration of Rejected Alternatives

| Rejected Alternative | Current Choice | Trigger for Reconsideration |
|---|---|---|
| REST microservice (§4.1 Alt B) | Internal interface | eParts takes ownership; canary deployments needed; GPU-backed inference requires independent scaling |
| Message queue (§4.1 Alt C) | Internal interface | Near-real-time ingestion; multiple downstream consumers beyond routing |
| Per-record routing (§4.2 Alt B) | Per-attribute | >30% of corrections involve cross-attribute consistency errors; or model improves enough that few records have multiple uncertain attributes |
| Microservices (§4.3 Alt B) | Single App Service | Production handoff to larger team; Prediction Service scaling diverges from ingestion |
| Pure ML (§7 ADR-1 Alt B) | Hybrid | ≥800 labeled examples and pure ML achieves ≥95% with calibrated confidence |
| Pure rules (§7 ADR-1 Alt A) | Hybrid | Rules alone cover ≥85% at confidence ≥0.90 |

*Table 7: Conditions under which rejected alternatives become preferable*

**Confidence summary.**
- *High:* pipe-and-filter style fits the problem; `PredictionServiceInterface` is the right isolation mechanism; centralized deployment appropriate for team size.
- *Moderate:* per-attribute routing (pending attribute independence validation); hybrid prediction (dependent on rule coverage and data volumes); category-generic schema (pending PIMS compatibility).
- *Low:* threshold value (0.85 untested); α weighting (0.7 initial guess); monitorability design (metrics undefined); review queue operational viability (capacity unmodeled).

---

## 6. Planned Refinements and Next Steps

Each activity targets a named uncertainty with question, rationale, concrete activity, and architectural impact.

### 6.1 Refinement 1: Confidence Threshold Calibration

- **Question:** What threshold achieves ≥95% auto-accept accuracy at sustainable review volume?
- **Why:** Most sensitive parameter; every routing/accuracy/capacity claim depends on it.
- **Activity:** Run prototype on ≥200 labeled submissions; compute precision-recall curves (0.50–0.99); measure per-attribute accuracy variance.
- **Impact:** No viable threshold → improve model or renegotiate target. High per-attribute variance → per-attribute thresholds.

### 6.2 Refinement 2: Attribute Correlation Analysis

- **Question:** Are attributes independent enough for per-attribute routing?
- **Why:** Correlated attributes reviewed independently could produce inconsistent records.
- **Activity:** Pairwise mutual information on labeled data; inspect 50 examples for high-MI pairs; prototype attribute-group routing if needed.
- **Impact:** <10% correlated → validated. Specific pairs → routing groups. >30% → switch to per-record.

### 6.3 Refinement 3: Hybrid Scoring Weight (α) Calibration

- **Question:** What α produces best-calibrated confidence?
- **Why:** Wrong α suppresses the more accurate signal source, causing over- or under-routing.
- **Activity:** Sweep α 0.3–0.9; measure ECE, precision, coverage; compare fixed vs. learned per-attribute-type weights.
- **Impact:** Learned variant better → per-type calibration table. Rule engine dominates → defer embedding layer.

### 6.4 Refinement 4: PIMS Schema Compatibility

- **Question:** Does PIMS staging support attribute-row structure (AD-5) and natural-key idempotency (AD-3)?
- **Why:** Writeback design assumes a schema Jake hasn't delivered.
- **Activity:** Map P1-C columns to canonical schema; integration-test 10 sample records.
- **Impact:** Aligned → validated. Wide columns → translation layer. Missing keys → team-owned buffer table.

### 6.5 Refinement 5: Reviewer Walkthrough and Writeback Failure Modes

- **Questions:**
  - (a) Is review queue context sufficient for correct decisions?
  - (b) Does the writeback mechanism handle all failure modes?
- **Why:** Review experience affects accuracy and throughput directly; writeback is the trust boundary where output enters PIMS with no rollback.
- **Activity:**
  - (a) Present 30 sample items to Brian/Dewey; record time, accuracy, reason-code usage, cross-attribute needs. If tabular export is insufficient, custom UI scope may need renegotiation.
  - (b) Enumerate failure modes (timeout, rejection, partial batch, concurrent execution); trace through idempotent logic; test against test SQL Server.
- **Impact:**
  - (a) Source files needed → add Blob links; reason codes ignored → reconsider pure ML; cross-attr context needed → reconsider per-attribute routing.
  - (b) Race conditions → distributed lock; partial inconsistency → transactional batch writes.

---

## 7. Architecture Decisions and Uncertainty

Several decisions remain provisional: model selection not finalized, threshold not calibrated, staging schema not delivered.

### 7.1 ADR-1: Hybrid Rule Engine + Semantic Similarity

**Issue.** The Prediction Service must map raw supplier text to canonical values with confidence scores. Section 4 analyzes *how* the filter is isolated; this ADR addresses *what* runs inside it.

**Alternatives.**
- **(A) Pure rules** — deterministic, explainable, but coverage ~40–60%.
- **(B) Pure ML** — handles unseen text, but needs ~830 labels for calibration (team targets 200); opaque confidence.
- **(C) Hybrid (current)** — rules for structured inputs; TF-IDF + cosine similarity for unmatched.

$$\text{conf}_{\text{final}} = \alpha \cdot \text{conf}_{\text{rule}} + (1-\alpha) \cdot \text{conf}_{\text{embed}}, \quad \alpha = 0.7$$

Reason codes attached to low-confidence items.

**Decision.** C. Both layers inside `prediction` behind `PredictionServiceInterface`.

**Rationale.** Rules provide high-precision fallback under data scarcity; reason codes satisfy eParts §6.5 explainability; ML layer replaceable independently.

**Status.** Tentative. POC running; α unvalidated.

**Triggers:** ≥800 labels + ML ≥95% → Alt B. Rules cover ≥85% at ≥0.90 → Alt A.

### 7.2 Decision Aid: Weighted Matrix

| Criterion | Wt | A | B | C |
|---|:---:|:---:|:---:|:---:|
| Accuracy (<200 labels) | .30 | 2 | 1 | 3 |
| Explainability | .20 | 3 | 1 | 3 |
| Free-text coverage | .20 | 1 | 3 | 2 |
| Model swappability | .15 | 0 | 2 | 3 |
| Impl. complexity | .15 | 3 | 2 | 1 |
| **Weighted total** | | **1.85** | **1.70** | **2.50** |

*Table 8: Decision matrix for ADR-1*

### 7.3 Other Architectural Decisions

| ID | Decision | Status | Rationale | Reconsideration |
|---|---|---|---|---|
| AD-2 | Stable prediction interface (T1) | Proposed | Isolates model from routing/writeback (H/M). Alts in §4.1. | Production handoff; canary needed. |
| AD-3 | Idempotent writeback: `submission_id` + `attribute_id` (T3) | Proposed | No PIMS API; composite key prevents duplicates (FR-6). | P1-C schema incompatible. |
| AD-4 | Configurable threshold (T2) | Tentative | Controls accuracy vs. review (H/H); 0.85 estimate. | High per-attr variance → per-attr thresholds. |
| AD-5 | Attribute-row canonical schema | Proposed | New categories via ref table, not migration (M/M). | P1-C reveals incompatibility. |
| AD-6 | Single App Service (Fig. 4) | Proposed | Team size; module boundaries preserve extractability. | Pred. Svc needs independent scaling. |

*Table 9: Architectural decisions, rationale, and reconsideration triggers*

---

## References

1. L. Bass, P. Clements, and R. Kazman, *Software Architecture in Practice*, 3rd ed. Addison-Wesley, 2012.
