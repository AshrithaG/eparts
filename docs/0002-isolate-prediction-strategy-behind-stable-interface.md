# ADR-002: Isolate the Prediction Strategy Behind a Stable Internal Interface

## Status

Accepted

## Context

Model selection for the attribute prediction component is unresolved through Phase 2. The team is currently using a hybrid rule + semantic-similarity approach (ADR-003) but expects to evaluate alternatives such as DistilBERT or CatBoost as labeled data accumulates. Quality attribute QA-2 (Modifiability — model swap) is rated High importance / Medium difficulty and explicitly requires that swapping the prediction strategy not ripple into the Routing Engine, Writeback, or any other component.

Three isolation mechanisms were considered:

- **Internal abstract interface** in the same Python application. A swap is a new class plus a configuration change; one redeployment.
- **REST microservice** running the Prediction Service in a separate Azure Container App. Enables independent deployment, canary rollouts, and GPU-backed inference, but adds container orchestration, health checks, service authentication, and distributed tracing.
- **Message queue (Azure Service Bus)** with broker-mediated communication. Two queues introduced; retry and dead-letter offloaded to Service Bus. Suits near-real-time ingestion with multiple consumers.

The current phase processes supplier catalogs in discrete batches and has a single downstream consumer (the Routing Engine). The team does not need canary deployments or GPU inference during the capstone phase. A network boundary between filters would add operational complexity disproportionate to team capacity.

## Decision

We will define `PredictionServiceInterface` as a Python abstract interface that accepts normalized records and returns predictions with per-attribute confidence scores. Concrete implementations (`CatBoostPredictor`, `DistilBERTPredictor`, the current hybrid implementation) live inside the `prediction` package and are selected at startup via configuration. The Routing Engine and all other downstream components depend only on `PredictionResult`, a plain data class, and never on any model-specific type.

## Consequences

- Replacing the prediction strategy is a localized change: a new class in the `prediction` package plus a configuration change. Nothing in `routing`, `writeback`, `review`, or `audit` changes.
- The interface contract — `PredictionResult` with per-attribute confidence — must be defined before the model is finalized. The team must avoid leaking model-specific types (logits, embedding vectors, classifier probabilities) into adjacent packages.
- Retraining and model promotion (described in the MLOps pipeline) operate inside the `prediction` package boundary. The interface does not change when a new model version is promoted, so the Routing Engine sees the prediction service as unchanged.
- This decision does not enable canary deployments or side-by-side model evaluation in production. If the system is later handed off to a larger eParts team that requires those capabilities, the prediction package will need to be extracted into a REST microservice. The module boundaries are drawn deliberately so that this transition is adding network serialization at an existing boundary, not a rewrite.

## Requirements Traceability

- **HLRs:** HLR-3 (predict with confidence — implementation choice deferred behind interface)
- **FRs:** FR-3 (per-attribute prediction contract)
- **QASs:** QAS-2 (model swap localized to prediction package — this ADR is the named mechanism in the QAS response)
- **Constraints:** C-3, DC-1 (Python interface); C-7 (internal interface chosen over REST microservice for capstone timeline)
- **Related ADRs:** ADR-003 (concrete implementation behind this interface); ADR-011 (retraining promotes new versions through this interface)
