# ADR-004: Route Confidence Decisions at the Attribute Level, Not the Record Level

## Status

Accepted

## Context

The Routing Engine is the architectural component that enforces the accuracy quality attribute (QA-1, rated High/High). Every record produced by the Prediction Service contains multiple attributes, each with its own predicted value and confidence score. The team must decide whether confidence routing operates at the record level (the whole record is sent to review if any attribute is uncertain) or at the attribute level (each attribute is routed independently).

Two alternatives were considered:

- **Per-record routing.** Conceptually simpler. The review queue holds whole records, and writeback always emits complete records. There is no merge logic. However, a record with ten attributes and one uncertain value sends all ten attributes to review, inflating reviewer workload.
- **Per-attribute routing.** Each attribute is routed independently. Estimated 3–5× lower review volume than per-record because only the attributes the model is unsure about reach the queue. The cost is structural: the writeback service must merge auto-accepted attributes with reviewed attributes for the same record before writing to PIMS, and there is a risk that correlated attributes (e.g., connection type and port size) become inconsistent if reviewed in isolation.

The combined catalog team across eParts and Alps Controls is approximately 4.5 FTEs. Reviewer capacity is the binding constraint on review volume; if the system pushes too many items to review, the labor savings the platform is meant to provide disappear.

## Decision

We will route confidence decisions at the attribute level. The Human Review Queue is keyed on `(record_id, attribute_id)`. The Routing Engine compares each attribute's confidence score against the configured threshold independently. The Writeback Service batches all attributes for a given record and writes them to PIMS as a unit only once all routing paths for that record (auto-accept and review) have resolved.

## Consequences

- Review volume scales with actual model uncertainty rather than with record size, expected to reduce reviewer workload by 3–5× compared with per-record routing.
- Reviewers see only the flagged attributes plus their source context, not the entire record. This focuses attention but means reviewers cannot easily catch inconsistencies between an auto-accepted attribute and one they are reviewing.
- The Writeback Service carries merge logic. It must hold the complete record until all routing decisions for that record are resolved, then upsert it as a unit. A partial write — auto-accepted attributes entering PIMS before reviewed attributes are resolved — would produce incomplete records and is explicitly prevented by this batching.
- Correlated attributes are a known risk. If connection type and port size are reviewed independently and the reviewer makes inconsistent choices, an internally inconsistent record can reach PIMS. Mitigation: the review interface presents the full record context to reviewers, but this has not been validated in practice. Refinement 2 in the project plan tests pairwise mutual information between attributes and inspects high-MI pairs.
- Per-attribute thresholds may be required if attribute-level accuracy varies significantly. Some attributes are inherently easier to predict than others. The threshold mechanism is configurable (ADR-005) so per-attribute thresholds can be introduced without code changes.
- If more than 30% of corrections turn out to involve cross-attribute consistency errors, the per-attribute routing decision should be reconsidered in favor of per-record or attribute-group routing.

## Requirements Traceability

- **HLRs:** HLR-4 (Human Review Queue for low-confidence predictions)
- **FRs:** FR-3 (per-attribute predictions); FR-4 (route below-threshold attributes to queue); FR-9 (per-attribute routing decisions)
- **QASs:** QAS-1 (accuracy — per-attribute routing keeps review volume proportional to risk)
- **Scenarios:** SCEN-2 (only the uncertain attribute is routed, not the whole record)
- **Validation:** VAL-2 (low-confidence item appears in Human Review Queue)
