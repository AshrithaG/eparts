# ETIM Readiness — Assessment of Existing ADRs (0001–0012)

**Date:** 2026-06-29
**Scope:** Whole platform (ingestion, ML/matching, routing, review, audit, writeback).
**Method:** Compared the 12 ADRs against (a) the running ingestion code, (b) `ETIM_IMPLEMENTATION_BRIEF.md`, (c) `INGESTION_ETIM_TICKET_MAP.md`, and (d) the EPARTS Jira backlog (epics EPARTS-154 Ingestion, EPARTS-156 ML POC, EPARTS-159 OCR POC).
**Action:** This is an assessment only — the existing ADR files are left unchanged. Three new ADRs (0013–0015) capture the new ETIM ingestion decisions. The changes recommended below should be actioned by the owning teams.

---

## Why the gap exists

The 12 ADRs describe the platform as designed in the capstone phase: a single **Azure App Service** holding all stages, all internal state in **Azure SQL Database**, **Datadog** telemetry, a single tall attribute-row staging table carrying prediction/routing columns, and a generic "predict canonical attribute values" model. Since then two things changed:

1. **The build diverged from the design.** The ingestion service actually runs on **PostgreSQL + S3/MinIO + Docker**, with **Prometheus + OpenTelemetry + structlog** for observability — not Azure SQL / App Service / Datadog.
2. **ETIM reframed the problem.** Standardization is no longer "predict a canonical value." It is class matching → feature matching → value/unit matching → ETIM validation → client-policy validation → confidence → route. The data model splits into source-evidence (ingestion) and ETIM-interpretation (matching), and the PIMS contract is now keyed on ETIM identifiers.

The ADRs split cleanly into three buckets below.

---

## Bucket A — Outdated on substrate/stack (factually wrong today)

### ADR-008 — Deploy as a Single Azure App Service Unit  ·  **Needs major revision**
- **Drift:** Names Azure App Service + Azure SQL + Blob + Datadog + `pyodbc` to PIMS. Reality: Postgres + S3/MinIO + Docker/`docker-compose`, Prometheus/OTLP. Azure is now an explicitly *deferred* direction (see ADR-015).
- **Still valid:** The "single deployable unit, components communicate in-process, boundaries drawn where service boundaries would go" decision still holds and is sound.
- **Recommend:** Revise to describe the current Docker/Postgres/S3 substrate as the operative topology, with Azure App Service/Azure SQL as the deferred target. Cross-reference **ADR-015**. The new push-to-ML seam (EPARTS-301, transactional outbox) is the first real network boundary and should be noted as the leading candidate for extraction.

### ADR-012 — Emit Stage-by-Stage Telemetry to Datadog  ·  **Needs revision (supersede recommended)**
- **Drift:** Datadog is not used anywhere in the ingestion code; the stack is **Prometheus metrics + OpenTelemetry (OTLP) tracing + structlog**, exposed on `/metrics`. Status is still "Proposed."
- **Still valid:** The *intent* — stage-by-stage signals, fire-and-forget, audit trail as system-of-record, drift detection from baselines — is correct and worth keeping.
- **Recommend:** Supersede with a "stage telemetry via Prometheus/OpenTelemetry" ADR, carrying over the signal list and adding the ETIM-specific metrics the brief calls for: ETIM import success/failure and row counts per release, products classified, class/attribute confidence distributions, auto-accept rate, human-review rate, missing-required-field rate, invalid-value rate, unit-conversion-failure rate, PIMS sync success/failure.

---

## Bucket B — Structurally sound but must become ETIM-aware (semantics changed)

### ADR-007 — Attribute-Row Canonical Schema  ·  **Partially superseded by ADR-014**
- **Change:** The "one tall row per attribute, *not* wide" instinct is retained and reinforced. But ADR-007's single staging table also carried `predicted_value`, `confidence_score`, `routing_status` on the same row. Under ETIM the model splits: ingestion emits **source-evidence only** (`staging_product` + `staging_raw_attribute`), and prediction/match/validation/review state moves to a separate matching-owned table (`matched_product_attribute`). See **ADR-014**.
- **Recommend:** Mark ADR-007 superseded-in-part by ADR-014; keep it as the rationale for the attribute-row (tall) choice.

### ADR-006 — Idempotent PIMS Writeback via Composite Natural Key  ·  **Needs revision**
- **Change:** ADR-006 keys idempotency on `submission_id + attribute_id`. The ETIM brief's PIMS output contract is keyed on **`product_id + etim_release_id + etim_class_id + etim_feature_id`** and carries original value + ETIM IDs + normalized typed values + confidence + approval status. The upsert mechanism is still correct; the key and payload are not.
- **Recommend:** Revise the natural key and payload to the ETIM contract. PIMS may remain SQL Server (external) even though our own stores are Postgres — keep that distinction (ties to ADR-015).

### ADR-003 — Hybrid Rule Engine + Semantic Similarity  ·  **Reframe for ETIM (still Tentative)**
- **Change:** Framed as "map raw supplier text → canonical attribute value." ETIM splits this into **class matching, feature matching, and value matching**, each with its own evidence and confidence, plus a **correction store** applied before general matching. TF-IDF/cosine over canonical embeddings still fits feature/value matching; class matching adds class descriptions + synonyms + correction rules as inputs. The `α = 0.7` blend and reconsideration triggers carry over.
- **Recommend:** Reframe around the three ETIM matching sub-problems and the correction store. Owner: ML (EPARTS-289/290/291).

### ADR-004 — Per-Attribute Routing  ·  **Extend signals**
- **Change:** Routing now depends on more than one confidence-vs-threshold check. The brief's routing table keys on **ETIM class confidence, attribute match confidence, ETIM validation result, client required-field policy, missing values, invalid values, and unit-conversion failures** — including a *class-review-first* path when class confidence is low or competing classes are close.
- **Recommend:** Keep per-attribute routing; extend the decision inputs to the ETIM signal set and add the class-level routing stage ahead of attribute routing (EPARTS-289, EPARTS routing work).

### ADR-005 — Externalized Confidence Threshold  ·  **Mostly valid; widen**
- **Change:** Still correct (and still Tentative). Under ETIM there are now at least two thresholds — **class-selection confidence** and **attribute-match confidence** — and the "ETIM Other" handling is a policy knob (auto-select vs route to review). Per-attribute override table generalizes to per-class-feature.
- **Recommend:** Generalize the config to cover class and attribute thresholds and the "Other" policy; otherwise unchanged.

### ADR-009 — Human Review Queue as DB Table  ·  **Make ETIM-aware**
- **Change:** Queue mechanism (persistent table, reviewer pace decoupled) is unchanged. Reviewers now need ETIM context: suggested class/feature/value, allowed-value dropdowns, numeric/range/boolean controls, and the ability to change class, mark unknown, and **save a correction rule**. Review statuses expand (pending, approved, corrected, rejected, class_changed, attribute_unknown, not_required).
- **Recommend:** Extend the queue row/contract with ETIM suggestion + review-status fields; reference the correction store. Owner: EPARTS-294.

### ADR-010 — Append-Only Audit Trail  ·  **Extend captured fields**
- **Change:** Append-only design is unchanged and still correct. It must now also capture the ETIM mapping: suggested class/feature/value, ETIM validation status, the corrected ETIM value, and the ETIM release in force — not just predicted-vs-corrected scalar values.
- **Recommend:** Extend the recorded columns to the ETIM mapping set; everything else stands.

---

## Bucket C — Still valid as written

### ADR-001 — Pipe-and-Filter  ·  **Valid**
The parse → normalize → match → route → review/auto-accept → writeback spine still describes the system. One addition: the **ingestion→ML handoff is becoming an explicit async seam** (transactional outbox + circuit breaker, EPARTS-301) rather than a pure in-process function call. Worth a one-line note, not a rewrite.

### ADR-002 — Prediction Strategy Behind a Stable Interface  ·  **Valid; enrich the contract**
The interface-isolation decision holds. The `PredictionResult` contract should be enriched to carry ETIM outputs (candidate classes with confidence, matched features/values, validation status) rather than a single predicted value — an interface evolution, not a reversal.

### ADR-011 — Retraining on Batch Completion  ·  **Valid (still Proposed)**
Mechanism unchanged. Under ETIM the "labeled examples" are reviewer ETIM corrections and the correction store; otherwise the validation-gate + promotion design stands.

---

## Summary table

| ADR | Verdict | Action |
|---|---|---|
| 001 Pipe-and-filter | Valid | Note the async ingestion→ML outbox seam |
| 002 Prediction interface | Valid | Enrich `PredictionResult` for ETIM outputs |
| 003 Hybrid rule + semantic | Reframe | Recast as class/feature/value matching + correction store |
| 004 Per-attribute routing | Extend | Add ETIM class conf, validation, client policy signals |
| 005 Externalized threshold | Widen | Class + attribute thresholds; "Other" policy |
| 006 PIMS idempotent writeback | Revise | Re-key to `product+release+class+feature`; new payload |
| 007 Attribute-row staging | Superseded-in-part | By ADR-014 (evidence vs interpretation split) |
| 008 Single Azure App Service | Major revision | Postgres/S3/Docker now; Azure deferred (ADR-015) |
| 009 Human review queue | ETIM-aware | Add ETIM suggestion + expanded review statuses |
| 010 Append-only audit | Extend | Capture ETIM mapping + release + validation status |
| 011 Retraining trigger | Valid | None (corrections = ETIM corrections) |
| 012 Datadog telemetry | Supersede | Prometheus/OTLP + ETIM metric set |

## New ADRs authored alongside this assessment

- **ADR-013** — Establish a release-versioned ETIM reference data layer owned by ingestion (documents the built EPARTS-285 work).
- **ADR-014** — Emit a source-preserving product + attribute staging split (`staging_product` + `staging_raw_attribute`); supersedes the staging shape in ADR-007.
- **ADR-015** — Target PostgreSQL now; defer the Azure SQL conversion (resolves ING-E0; revisits ADR-008's substrate).

## Open items that block firming up some of the above

From the ticket map and brief, still needing a client/team answer: authoritative `supplier_sku` field per supplier format; behavior when a record has no extractable SKU (quarantine vs synthesized id); whether the ML push payload is per-product or per-attribute; which ETIM features are required/recommended/optional per class (client policy); whether "ETIM Other" auto-selects or routes to review; and how ETIM release upgrades are governed.
