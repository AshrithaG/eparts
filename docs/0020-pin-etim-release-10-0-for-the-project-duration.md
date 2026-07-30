# ADR-020: Pin ETIM Release 10.0 (EI) for the Project Duration

## Status

Accepted

## Context

ETIM is an external standard with its own release cadence. We loaded **ETIM 10.0, language EI**. There will be an 11.0, and between releases classes are added, features are added and deprecated, values are withdrawn, and a class's feature set changes shape.

That raised a question the v1.0 baseline had no equivalent of: what does the platform do when the standard moves underneath it? Two things made it pressing. Requirements written against "the ETIM standard" are implicitly written against a specific release, so the traceability chain from HLR-6 through FR-9 to a published PIMS row is only meaningful if the release is part of the record. And an unmanaged upgrade silently reinterprets historical data — a value that was legal under 10.0 can be invalid under 11.0, and either the row breaks or, worse, it stays and nobody knows which release's rules it satisfies.

Three options were considered.

- **Build a governed upgrade path now.** Load each new release alongside the old one, diff them, re-match affected products through a review queue, and reconcile the client's feature policy against the diff before cutover. Architecturally clean, and it makes upgrades visible rather than silent. But it is a substantial amount of work — a diff report, a bulk re-match path, a second review queue — for an event that will not occur inside this project. It also could not be finished: who authorizes an upgrade, on what trigger, and what happens to already-published rows are client decisions nobody has made.
- **Leave the question open.** Say nothing and handle a future release when it arrives. Rejected because "unspecified" is not the same as "out of scope". FR-10 as originally worded — maintain the dictionary as *versioned* reference data — implies an obligation we were not going to meet, and an assessor or a future maintainer would reasonably read it as a commitment.
- **Pin the release explicitly and put the upgrade path out of scope.** Chosen.

## Decision

**The platform targets ETIM release 10.0, language EI, for the duration of this project.** Adopting later ETIM releases, and migrating already-classified products between releases, are **out of scope**.

This is recorded as **constraint C-4**, introduced in Product Specification **v1.2**, and FR-10 is scoped to "the pinned ETIM release identified in C-4" rather than to versioned reference data generally.

The **release-scoping mechanism in the schema stays exactly as it is.** Every ETIM reference row carries `etim_release_id`, with composite primary keys on `(etim_release_id, …)` across all ten tables (ADR-013); the release is carried through `matched_product_attribute` (ADR-014) and forms part of the PIMS writeback key (ADR-017). Under a pin that field is constant in practice, and we are keeping it for two reasons:

1. **Provenance.** Every published value names the release it was matched under. "This value was matched against ETIM 10.0 EI, on this date, under this policy" stays recoverable from the row alone, which is what makes the audit trail meaningful later.
2. **It costs nothing.** The columns and keys are already built and tested. Removing them to reflect the pin would be work that buys no capability and discards the provenance.

So this ADR narrows the *forward-looking justification* in ADR-013 — release-scoping is no longer defended as a step toward governed upgrades — without changing a line of the schema it describes. ADR-013 is not edited.

If the client later asks for a new ETIM release, that is a **change request against C-4**, and the first option above is the shape the work would take. It is not a gap to be quietly filled.

## Consequences

- The project stops carrying an obligation it was never going to discharge. FR-10 is now satisfiable and testable as written: load and maintain one named release.
- No diff report, no bulk re-match path, no second review queue, and no upgrade-governance owner to chase. This is the largest piece of scope the decision removes, and it removes it in the phase where the critical path is `285 ‖ (297 → 298 → 299)`.
- **We are deliberately accepting that the catalog will go stale** relative to ETIM. If the client's suppliers begin publishing against 11.0 while we classify against 10.0, new classes and features are simply unavailable to us, and products needing them fall to "ETIM Other" handling or to review. For a phase-one valve/actuator pilot that is acceptable. For a production catalogue with a multi-year life it would not be, and this ADR should be revisited before any such transition.
- Provenance is preserved without the machinery. Because `etim_release_id` remains in the reference tables, the interpretation table and the PIMS key, a future un-pinning is a change of scope rather than a schema migration. The door is left open at zero cost.
- **The loader keeps its release-mismatch rejection.** It validates that an archive matches the declared release and refuses a mismatched or truncated one (ADR-013). Under a pin that check becomes more valuable, not less — it is what stops an 11.0 archive being loaded into a 10.0-pinned system by accident.
- The `etim_release_id` field will look redundant to anyone reading the schema without this ADR. That is the cost of keeping it, and this ADR is the answer.
- One open client decision is closed. "ETIM release-upgrade governance" comes off the blocked list, taking the open-decision count from six to five.

## Requirements Traceability

- **Spec:** Product Specification **v1.4** (29 July 2026); C-4 was introduced in v1.2 (28 July) — this ADR is the reason for that version
- **Constraints:** **C-4** (ETIM Release Pinned) — this ADR is the decision C-4 records
- **HLRs:** HLR-6 (classify against the ETIM standard — this ADR fixes *which* ETIM)
- **FRs:** **FR-10** (load and maintain the ETIM reference dictionary for the pinned release); FR-9 (matching is always against release 10.0 EI)
- **DRs:** DR-4 (the release remains part of the PIMS writeback key, so publication stays release-explicit)
- **QASs:** QAS-1 Modifiability — un-pinning would be a scope change, not a structural change to the pipeline
- **Constraints (supporting):** C-1 (cost-effective design — the upgrade path is the expensive option and is deliberately not built); C-3 (breadth-first delivery — one supplier type end to end before adding depth)
- **Source:** `ETIM_IMPLEMENTATION_BRIEF.md`; `ETIM-ADR-ASSESSMENT.md` raised this as *"Standard evolution (currency): ETIM releases (10.0 → next); upgrade governance undefined"* — this ADR resolves that item by scoping it out rather than by building for it
- **Closes:** the open client decision "ETIM release-upgrade governance"
- **Related ADRs:** narrows the forward-looking rationale of **ADR-013** (release-scoped reference layer) without editing it; the release remains in **ADR-014**'s interpretation table and **ADR-017**'s writeback key for provenance; **ADR-019**'s policy overlay no longer needs reconciling against a release diff
