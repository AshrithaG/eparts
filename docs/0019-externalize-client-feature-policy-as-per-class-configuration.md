# ADR-019: Externalize the Client Feature Policy as Per-Class Configuration

## Status

Accepted

## Context

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

## Decision

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

## Consequences

- The architecture stops being blocked on a client decision. Routing, validation and the reviewer UI can be built against the overlay's contract and exercised with a synthetic policy, then switched to the real one when it arrives.
- The **required-field path is designed but untestable end-to-end** until a real policy exists. Tests can prove that a `required` row routes correctly; they cannot prove the right features are marked required. This gap should be stated rather than papered over — a green test suite here does not mean the validation requirement is satisfied.
- Because policy is per-client, a second client with different editorial standards is a data addition rather than a code change. That is well beyond phase-one scope and is not being built for, but the key shape does not preclude it.
- `conditional` requires a rule language (`condition_rule`), and no rule language has been chosen. Conditional features are therefore accepted into the schema but not evaluated; they behave as `optional` until a rule evaluator exists. This is a known deferral, not an oversight.
- `used_for_compare` and `used_for_filter` are carried in the schema because the Compare Tool and website filter are the stated business motivation for ETIM adoption, but both consumers are **out of phase-one scope**. Storing the flags now avoids a migration later; populating them is deferred.
- Every policy change silently changes routing behaviour. Policy revisions must be versioned and correlated with review-queue volume, or an unexplained spike in the queue will be indistinguishable from a model regression.
- The permissive default means that until the policy lands, **no product will ever be blocked for a missing required field**. Auto-accept rates measured before the policy is populated are therefore optimistic and must not be quoted as steady-state figures.

## Requirements Traceability

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
