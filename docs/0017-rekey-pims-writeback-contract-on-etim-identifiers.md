# ADR-017: Re-key the PIMS Writeback Contract on ETIM Identifiers

## Status

Accepted

## Context

ADR-006 established idempotent PIMS writeback via a composite natural key of `submission_id + attribute_id`, upserted rather than inserted, so that a retried write cannot create duplicates. The mechanism was and remains correct.

The key is not. Two things broke it.

**The key no longer identifies the thing being written.** Under ETIM the unit of published data is not "an attribute of a submission" but "the value of a specific ETIM feature, of a specific ETIM class, of a specific product, under a specific ETIM release" (HLR-6, DR-4). `submission_id` is an artefact of *how the data arrived*, not of *what it describes*. The same product arriving twice — a corrected catalogue re-sent by the supplier, or a second file covering the same SKU — produces two submission IDs and therefore two rows for one real-world fact. The upsert would not collide, and PIMS would accumulate duplicates that are invisible to the idempotency check.

**The payload no longer carries enough to be useful downstream.** ADR-006's row was a value plus a confidence. The PIMS output contract now has to carry both the interpretation and the evidence behind it, because the whole point of the standardization objective is that a consumer can compare products across suppliers *and* audit where a value came from.

Alternatives considered:

- **Keep `submission_id + attribute_id`, add ETIM IDs as payload columns.** Minimal change, but leaves the duplicate-on-resubmission defect in place and makes "the current value of feature EF021864 for this product" unanswerable without scanning submissions.
- **Key on `product_id + etim_class_id + etim_feature_id`, omitting the release.** Simpler, but conflates ETIM releases: a value matched under 10.0 and a value matched under a future 11.0 would collide even though the feature definition may have changed between them. That defeats the release-scoping established in ADR-013.

## Decision

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

## Consequences

- Re-sending a corrected catalogue for a product now **updates** the published row instead of appending a second one. This is the defect the old key could not see.
- "What is the current published value of feature X for product Y under release Z" becomes a primary-key lookup. Cross-supplier comparison and website filtering — the business objective that motivated ETIM adoption — depend on exactly that query being cheap.
- The release is part of the key for **provenance**: every published value names the ETIM release it was matched under. Under ADR-020 the project is pinned to 10.0 EI, so in practice the field is constant — it is carried so the row is self-describing, and so that un-pinning later would be a change of scope rather than a schema migration.
- The key requires a stable `product_id`, which requires a resolvable `supplier_sku` per supplier format. **This is an open dependency**: the authoritative SKU field per format, and the behaviour when a record has no extractable SKU (quarantine versus synthesized identifier), are both unresolved. Until they are, products from formats without a clean SKU cannot be published idempotently.
- Products carrying a feature that ETIM does not define ("ETIM Other") have no `etim_feature_id` and therefore no key. Their handling is an open client decision; they are held out of the published set rather than given a synthetic identifier.
- The payload is wider than ADR-006's, so PIMS staging rows grow. Given the phase-one valve/actuator scope this is not a capacity concern, and carrying the evidence alongside the interpretation is what makes the published data auditable.
- ADR-006 is **not edited**. It stands as the record of the April decision and of the upsert mechanism, which this ADR reuses. Where the two disagree on the key, this ADR governs.

## Requirements Traceability

- **Spec:** Product Specification v1.3 (29 July 2026)
- **HLRs:** HLR-6 (enrich with ETIM identifiers); HLR-5 (write approved data back to PIMS)
- **FRs:** FR-8 (write attributes to PIMS upon final approval); FR-9 (preserve the original supplier value alongside the ETIM assignment)
- **DRs:** **DR-4** — *"Approved data written to PIMS shall be keyed by ETIM identifiers (release, class, feature); the writeback idempotency key shall include these identifiers"* — this ADR is the direct realization of DR-4; DR-3 (writeback must be idempotent; retry must not duplicate)
- **Constraints:** DC-3 (raw files preserved as evidence — the published row references that evidence)
- **Scenarios:** SCEN-1 step 5 and SCEN-2 step 6 (auto-accepted and human-approved data both take this path)
- **Validation:** VAL-3 (approve an item; the PIMS write succeeds and a retry does not duplicate — the retry case is now tested against the ETIM key)
- **Source:** `ETIM_IMPLEMENTATION_BRIEF.md` — PIMS Output Contract, PIMS Sync; `INGESTION_ETIM_PLAN.md` — design decisions
- **Tickets:** EPARTS-299 (writer rework), EPARTS-295 (PIMS sync); parent EPARTS-154 (Ingestion)
- **Related ADRs:** supersedes the natural key defined in ADR-006 while reusing its upsert mechanism; consumes the identifiers produced by ADR-016; depends on the release scoping of ADR-013; the datastore distinction is governed by ADR-015
