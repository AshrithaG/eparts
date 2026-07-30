# ADR-012: Emit Stage-by-Stage Telemetry to Datadog for Drift Detection and Operational Monitoring

> Source of truth: [`0012-emit-stage-by-stage-telemetry-to-datadog.md`](https://github.com/AshrithaG/eparts/blob/main/docs/0012-emit-stage-by-stage-telemetry-to-datadog.md) in the eparts repo. This page is a copy for reading; edit the repo, not this page.

## Status

Proposed

## Context

ML systems can degrade silently as supplier data drifts from the training distribution. Without monitoring, incorrect auto-accepts accumulate in PIMS and surface only when contractors order wrong parts. Quality attribute QA-5 (Monitorability) is rated High/High both in importance (because silent degradation is the worst failure mode) and in difficulty (because the team has not yet defined what metrics to track or what baseline to compare against).

eParts uses Datadog as its observability platform, so integration is mandatory rather than chosen. The architectural questions are: where in the pipeline should telemetry be emitted, what signals should be captured, and how should those signals be tied to drift detection.

Telemetry must not block the pipeline. A Datadog outage cannot be allowed to take ingestion or writeback offline.

## Decision

Telemetry is emitted to Datadog from four pipeline stages over fire-and-forget HTTPS:

- **Ingestion Gateway:** ingestion success and failure counts, parsed by supplier and channel.
- **Normalization (Structured Layer):** row counts after canonical schema mapping, broken down by supplier and category.
- **Prediction Service:** per-attribute confidence score distributions and rule-vs-embedding contribution breakdown.
- **Routing Engine:** routing split ratios (auto-accept vs. review) per attribute.
- **Review Queue:** reviewer decision counts (approved, corrected, rejected) and correction rates per attribute.

Telemetry calls do not block the pipeline; failed Datadog writes are logged locally and dropped. Operationally significant signals that must not be lost are also persisted in the audit trail (ADR-010), so Datadog is treated as a dashboard and alerting layer, not as the system of record.

Drift detection thresholds (e.g., "alert when correction rate increases by 10% over a rolling two-week window" or "alert when mean confidence shifts by 15%") are defined as configuration on Datadog and validated empirically once Refinement 1 has produced a baseline.

## Consequences

- The pipeline emits the right signals to detect drift. Confidence distributions reveal model overconfidence or underconfidence; correction rates reveal accuracy degradation; routing split ratios reveal threshold drift.
- Drift detection is operationally complete only when thresholds are defined. The architecture emits the signals; it cannot yet say what deviation from baseline constitutes actionable drift. Refinement 6 in the project plan defines and validates these thresholds against simulated drift.
- Telemetry is tied to the audit trail. Reviewer correction rates in Datadog are computed from the same decisions recorded in the audit trail, so the dashboard and the system of record cannot diverge.
- Datadog outages do not affect pipeline correctness. A telemetry failure is logged locally and the pipeline continues. This is acceptable because the audit trail is the source of truth; the dashboard is a derived view.
- Because telemetry is fire-and-forget, telemetry packets can be lost during a Datadog outage without retry. This means short-term metrics (e.g., a one-hour confidence distribution) may have gaps during incidents. Long-term metrics computed from the audit trail are unaffected.
- Per-supplier telemetry is captured because supplier-specific drift is a likely failure mode (a supplier changes its catalog format, the model's confidence drops, but the threshold doesn't catch it). Per-supplier dashboards in Datadog allow drift to be localized to the offending supplier.
- This decision is Proposed rather than Accepted because the alert thresholds and baselines are not yet defined. Once Refinement 1 and Refinement 6 produce values, this decision moves to Accepted.

## Requirements Traceability

- **FRs:** FR-12 (emit confidence distributions, correction rates, routing decisions, pipeline metrics to Datadog)
- **QASs:** QAS-5 (drift detection from baseline deviation in confidence and correction rates)
- **Constraints:** C-1 (Datadog runs over HTTPS from Azure App Service)
