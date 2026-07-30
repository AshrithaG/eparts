# ADR-001: Adopt Pipe-and-Filter as the Primary Architectural Style

> Source of truth: [`0001-adopt-pipe-and-filter-architectural-style.md`](https://github.com/AshrithaG/eparts/blob/main/docs/0001-adopt-pipe-and-filter-architectural-style.md) in the eparts repo. This page is a copy for reading; edit the repo, not this page.

## Status

Accepted

## Context

eParts Services LLC ingests heterogeneous supplier catalogs (CSV, PDF, email attachments, SFTP drops, direct uploads) into PIMS through a manual workflow currently absorbing roughly 4.5 FTEs across eParts and Alps Controls. The new platform must transform raw supplier files into validated PIMS records while keeping data integrity high, because incorrect product data propagates into contractor field orders.

The transformation is fundamentally linear: parse → normalize → predict → route → review/auto-accept → write back. Each stage operates on the output of the previous one, and stages have different resource profiles (parsing is I/O-bound, prediction is CPU/memory-bound, review is human-bound).

Several architectural styles were considered:

- **Event-driven architecture** would introduce a message broker and asynchronous coordination. Supplier catalogs arrive in discrete batches rather than continuous streams, so the complexity is not justified.
- **Microservices** would require container orchestration and distributed tracing infrastructure beyond what a five-person capstone team can sustain.

The team is five people working from Spring through Fall 2026, so operational simplicity is a binding constraint.

## Decision

We will structure the platform as a pipe-and-filter system. Independent filters (Ingestion Gateway, Normalization, Prediction Service, Routing Engine, Review/Auto-accept paths, Writeback) communicate through typed data channels. The pipeline is linear with one branch at the Routing Engine where confidence-based routing splits high-confidence attributes (auto-accept) from low-confidence attributes (human review); both paths merge before writeback.

![Pipe-and-Filter Architecture](../diagrams/pipe-filter-architecture.png)

## Consequences

- Each filter can be replaced or evolved independently because filters communicate only through defined data contracts. The Prediction Service can be swapped without touching upstream parsing or downstream writeback (supports QA-2).
- Adding a new product category requires extending the canonical schema and retraining; it does not require changing the filter sequence (supports QA-3).
- Staging tables placed between filters act as checkpoints: a failure at any stage does not lose data already processed upstream (supports QA-4 availability).
- The known weakness of pipe-and-filter is error detection and recovery across the pipeline. We mitigate this with persistent staging tables between stages and idempotent writeback, but cross-stage transactional guarantees are not provided.
- The branch at the Routing Engine departs from a strictly linear pipeline. The two paths must merge before writeback, which introduces merge logic in the writeback service (further explored in ADR-005).
- The architecture mirrors the existing manual workflow stage-for-stage, reducing the risk that the system solves the wrong problem and easing communication with the catalog team.

## Requirements Traceability

- **HLRs:** HLR-1 (multi-format ingestion), HLR-2 (normalization to standard structure)
- **FRs:** FR-1, FR-2 (filter decomposition makes ingestion and normalization distinct stages)
- **QASs:** QAS-2, QAS-3 (style enables filter-level replacement); QAS-4 (staging tables between filters act as checkpoints)
- **Constraints:** C-7 (capstone timeline — pipe-and-filter mirrors existing manual workflow, minimizing rework risk)
- **Scenarios:** SCEN-1, SCEN-2 (the filter sequence is the spine of both scenarios)
- **Validation:** VAL-1 (Ingestion Gateway is the first filter)
