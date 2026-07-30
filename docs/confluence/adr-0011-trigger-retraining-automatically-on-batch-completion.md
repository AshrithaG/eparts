# ADR-011: Trigger Retraining Automatically on Human Review Batch Completion

> Source of truth: [`0011-trigger-retraining-automatically-on-batch-completion.md`](https://github.com/AshrithaG/eparts/blob/main/docs/0011-trigger-retraining-automatically-on-batch-completion.md) in the eparts repo. This page is a copy for reading; edit the repo, not this page.

## Status

Proposed

## Context

The Prediction Service must improve over time as supplier data changes and as the labeled corpus grows. Reviewer corrections are the primary source of labeled examples. The architectural choice is the trigger mechanism that initiates a retraining run.

Three alternatives were considered:

- **Manual trigger.** An engineer reviews the accumulated corrections, judges that enough new examples exist, runs the training script, evaluates the result, and promotes the new model if it improves on the previous version. Requires no automation but depends entirely on engineer availability and judgment. Poor fit for a five-person capstone team that cannot guarantee weekly engineer cycles.
- **Automatic trigger on review batch completion.** A retraining job fires automatically each time a human review batch is marked complete. The new model version is evaluated against a held-out validation set and promoted only if it outperforms the current version. No engineer initiates the run.
- **Scheduled trigger.** Retraining runs on a fixed cadence (weekly or monthly) regardless of review activity. Predictable, but introduces a fixed lag between when corrections are made and when the model learns from them. Risks training on too few examples if review activity is light, or accumulating too many examples if review activity is heavy.

In all cases, a validation gate is required: a new model version must outperform the current version on a held-out validation set before it is promoted. Without this gate, automatic retraining could promote regressions silently.

## Decision

Retraining is triggered automatically when a human review batch is marked complete. The retraining job reads all corrections flagged as labeled examples since the last training run from the audit trail (ADR-010), combines them with the existing labeled dataset, and trains a new version of the active prediction strategy. The new version is evaluated against a held-out validation set. If validation accuracy improves, the new version is promoted as the active model behind `PredictionServiceInterface` (ADR-002). If it does not improve, the previous version remains active and the result is logged for engineering review. Model version history is stored in Azure Blob Storage with training date, example count, and validation accuracy as metadata.

## Consequences

- The model learns from corrections as soon as a batch is reviewed, with no engineer in the loop. This is the fastest path from a reviewer correction to an improved model.
- The validation gate prevents silent regressions. A worse model is never promoted automatically; it is logged for human review.
- Promotion is transparent to the rest of the pipeline. The Routing Engine, Writeback Service, and Review Queue see the prediction service as unchanged because `PredictionServiceInterface` does not change with model version.
- Rollback is supported. Each model version is tagged in Azure Blob Storage. If a promoted version is later found to perform poorly on production data, engineering can revert by changing the active model pointer in configuration without redeploying the application.
- A minimum batch size before triggering retraining is required to avoid training on sparse data. The minimum example count has not been set and will be established once Refinement 1 produces real review-batch sizes. Until then, this decision is Proposed.
- The validation set must remain representative. If the validation set drifts from production data, the gate becomes meaningless because a model that overfits to stale validation can pass the gate while degrading on real inputs. The validation set itself must be refreshed periodically; this operational discipline is a dependency of the retraining decision.
- Frequent retraining on small batches can produce unstable model versions even with a validation gate, because validation accuracy itself fluctuates on small evaluation sets. If observed, the trigger should be replaced with a hybrid: scheduled retraining with a minimum-correction-count gate.
- Engineering team capacity post-handoff may make manual triggering attractive again. A larger team with regular review cycles may want explicit human oversight on every promotion. The retraining package is decoupled enough from the rest of the pipeline that switching to manual triggering is a configuration change.

## Requirements Traceability

- **HLRs:** HLR-3 (prediction quality maintained over time)
- **DRs:** DR-2 (Future/TBD — corrected data logged for future retraining and offline model improvement)
- **QASs:** QAS-2 (retraining promotes new versions through PredictionServiceInterface without breaking dependents); QAS-5 (closes the loop from drift detection to model improvement)
- **Constraints:** C-3, DC-1 (retraining runs in the Python prediction package)
