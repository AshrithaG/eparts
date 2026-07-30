# ADR-008: Deploy the Platform as a Single Azure App Service Unit

> Source of truth: [`0008-deploy-platform-as-single-azure-app-service-unit.md`](https://github.com/AshrithaG/eparts/blob/main/docs/0008-deploy-platform-as-single-azure-app-service-unit.md) in the eparts repo. This page is a copy for reading; edit the repo, not this page.

## Status

Accepted

## Context

The platform must be deployed on Azure (a fixed client constraint) and must be operable by a five-person capstone team across one academic year. Quality attributes that bear on deployment topology are QA-2 (model swappability), QA-4 (availability under Prediction Service outage), and a team-size constraint that bounds operational complexity.

Two topologies were analyzed in detail:

- **Single Azure App Service (Python).** All pipeline components — ingestion, normalization, prediction, routing, review-queue access, writeback orchestration — run in one process and one deployment unit. Azure SQL Database holds staging tables, the review queue, and the audit trail. Azure Blob Storage archives raw supplier files. The Publish/Sync Job runs as a separate timer-triggered Azure Function. Components communicate by function call. Scaling is per application unit.
- **Microservices (Azure Container Apps).** Three independent services: Ingestion+Normalization, Prediction, Routing+Writeback. Each scales independently, can be deployed independently, and can fail independently. Inter-service communication is HTTP or Service Bus. Operational requirements include container orchestration, distributed tracing, service-to-service authentication, and three deployment pipelines.

The microservices alternative offers fault isolation and independent scaling, both of which are real benefits for a production system. They are not benefits the current team can absorb operationally during the capstone phase. Distributed tracing alone would consume a substantial fraction of the timeline. The Prediction Service does not currently need GPU instances or independent scaling because supplier ingestion is batched, not real-time.

## Decision

The platform is deployed as a single Azure App Service running Python. All pipeline components live in one process. Azure SQL Database holds all internal pipeline state (staging tables, Human Review Queue, audit trail). Azure Blob Storage archives raw supplier files. The Publish/Sync Job is a timer-triggered Azure Function deployed separately. Inbound channels are SFTP (polled), email (polled), and HTTPS upload. Outbound to PIMS is via `pyodbc` across the trust boundary to PIMS SQL Server. Outbound telemetry to Datadog is fire-and-forget HTTPS.

## Consequences

- One deployment, one log stream, one health check. Operational complexity is bounded.
- Components communicate by function call. This is fast and avoids the complexity of network serialization, retries, and timeouts between filters.
- Fault isolation is reduced. A bug in any component can crash the App Service and take the entire pipeline down. The persistent staging tables and review queue mitigate data loss risk: in-flight work survives a process restart because state is in Azure SQL, not in-memory.
- Independent scaling is not available. If the Prediction Service becomes a hotspot, the entire App Service must be scaled up.
- The module boundaries inside the App Service (described in the module view) are deliberately drawn where service boundaries would go in a microservices deployment. The `prediction` package, `routing` package, and `writeback` package are independent units of code that communicate through typed data contracts. Transitioning to microservices later is therefore adding HTTP serialization at existing boundaries, not rewriting business logic.
- Datadog telemetry is fire-and-forget. Telemetry failures do not block the pipeline. This means a Datadog outage cannot cause a pipeline outage, but it also means dropped telemetry is not retried; operationally significant signals must also be persisted in the audit trail (ADR-009).
- The Publish/Sync Job is intentionally separated as an Azure Function on a timer trigger so that PIMS writeback runs on a controlled schedule rather than synchronously with each ingestion. This decouples PIMS load from supplier ingestion bursts.
- Trigger for reconsideration: production handoff to a larger eParts team, or a Prediction Service that scales independently of ingestion (e.g., GPU-backed inference, multi-model ensembles). At that point, the prediction package is the natural first candidate for extraction into a Container App.

## Requirements Traceability

- **HLRs:** HLR-1 (ingestion endpoints hosted on App Service); HLR-5 (Publish/Sync Azure Function)
- **FRs:** FR-1 (Ingestion Gateway runs on App Service); FR-8 (Publish/Sync Function performs writeback); FR-10 (Azure SQL hosts the persistent queue); FR-13 (Azure Blob hosts raw file archive)
- **DRs:** DR-1 (Blob archive is part of deployment topology)
- **QASs:** QAS-4 (staging tables in Azure SQL provide outage buffering)
- **Constraints:** C-1 (Azure managed services); C-3 / DC-1 (Python App Service); C-7 (single unit chosen over microservices for capstone timeline); DC-3 (Blob Storage archive)
- **Validation:** VAL-1, VAL-3 (deployed components host the tested behavior)
