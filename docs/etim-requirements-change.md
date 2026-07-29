# ETIM — requirements change record

**Framing:** ETIM is not a new project. It is a **mid-project requirements change against the v1.0 baseline**, managed as a change and recorded as versions 1.1 and 1.2 of the Product Specification (23 and 28 July 2026).

Companion artifacts: [`product-spec-v1.2.pdf`](product-spec-v1.2.pdf) · [`product-spec-changelog.md`](product-spec-changelog.md) · [`ETIM-ADR-ASSESSMENT.md`](ETIM-ADR-ASSESSMENT.md) · ADRs 0013–0021 in [`adr-index.md`](adr-index.md).

## What ETIM is

A standardized technical product-classification model — **reference data, not supplier data**:

```
Product group (EG) → Class (EC) → Feature (EF) → Value (EV) / Unit (EU)
```

Loaded and verified: **ETIM 10.0 (EI)** — 159 groups, 5,640 classes, 17,377 features, 201,284 class-feature-values. **The project is pinned to this release** for its duration; adopting later ETIM releases is out of scope (C-4, ADR-020). Feature types A / L / N / R (controlled value / boolean / numeric / range). Phase-one scope: **valves and actuators only**.

The principle that now drives every downstream decision:

> **Original supplier data = evidence · ETIM data = standardized interpretation · confidence = how sure we are of the interpretation.**

## 1. How the requirements shifted

**The root change:** the system's *WHAT* moved from *"predict arbitrary product attributes"* to *"classify each product into the ETIM standard and map its attributes to a controlled vocabulary."* Constrained classification, not free prediction. Everything else cascades from that.

Framed on the four dimensions of requirements:

| Dimension | Before ETIM | After ETIM |
|---|---|---|
| **WHY** (objectives) | Automate manual entry into PIMS | **+ New business objective: standardize the catalog to an industry standard** (cross-supplier comparability, website filtering, Compare Tool). Data integrity sharpened to "evidence vs. interpretation." |
| **WHAT** (function) | Predict attributes (Voltage, Material…) with confidence | **Match to ETIM class / feature / value** against a controlled vocabulary. **+ New requirement type: reference-data management** (load and maintain the ETIM dictionary for one pinned release). |
| **WHO** (responsibility) | Ops Reviewer, Supplier | **+ Feature-policy owner** (declares required/optional features per class), **+ Compare-Tool and website-filter consumers** |
| **HOW WELL** (quality) | ≥95% attribute accuracy | Accuracy measured **against a controlled vocabulary**; **+ new modifiability axis: "add a new ETIM class"**; **+ metric-canonical storage constraint** |

The per-ID detail — what was added (HLR-6, FR-9, FR-10, DR-4), what was amended (HLR-1, HLR-2, §2.1, §3.1, glossary, SCEN-1, SCEN-2), and what no longer holds (FR-3, the flat `IngestedRecord`) — is in [`product-spec-changelog.md`](product-spec-changelog.md).

## 2. How the change is being managed

Structured on the four classes of requirements management.

### (a) Change control
ETIM is treated as a formal change against the v1.0 baseline, not a rewrite. The spec is bumped to **v1.1 with a version-history entry** — that entry *is* the change record. Impact was analysed on Wiegers' dimensions (benefit, penalty, cost, risk, effort, quality impact) through ticket gap-analysis.

The same discipline was applied again a week later: pinning the ETIM release removed an obligation FR-10 implied, so it went in as **v1.2 with its own history entry and a new constraint (C-4)** rather than as a silent edit to v1.1.

### (b) Version control
Doc versioned 1.0 → 1.1 → 1.2. New IDs were **added** (HLR-6, FR-9/FR-10, DR-4, then C-4) rather than renumbering the existing set — deliberately, to **preserve existing trace links**. Only items that changed, are reused, or are depended upon were versioned.

### (c) Status tracking

| Status | Items |
|---|---|
| **Implemented** | EPARTS-285 (ETIM reference schema + import), EPARTS-297 (field mapping) |
| **Approved / in progress** | EPARTS-274 (canonical schema design), 298 (staging migrations), 299 (writer rework) |
| **Proposed / blocked on client** | EPARTS-286 (class scope), 287 (feature policy) |

### (d) Tracing
The chain for the new requirements:

```
business objective (standardization) → HLR-6 → FR-9 / FR-10 → tickets → golden test set (EPARTS-296) → QAS
```

**Forward trace = completeness** (does every new ETIM requirement have downstream tickets and tests?). **Backward trace = currency** (does every new ticket trace to a requirement — catching gold plating?).

**Traceability boundary:** two cross-team contracts are interface requirements — the **ML input contract (EPARTS-156)** and the **OCR output contract (EPARTS-159)**. Our tracing stops at those contracts; we own the requirement, another stream owns the implementation.

### Re-scoped baseline

- **In:** valve/actuator classes, ETIM 10.0 EI (pinned), class/feature/value matching, evidence preservation, PIMS ETIM-keyed sync.
- **Out / deferred:** all-classes coverage, pricing (still out), Compare-Tool feature sets, ETIM "Other" handling, valve+actuator assemblies, **any ETIM release after 10.0**.
- **Structure:** a 12-ticket MVP (EPARTS-285 → 296) plus 7 ingestion engineering tickets (297 → 303).
- **Critical path:** `285 ‖ (297 → 298 → 299)` — everything hangs off 299.

Prioritization follows the critical path and dependencies rather than ad-hoc judgement: 274 → 298 → 299 are Must and time-sensitive; evidence preservation is a regulatory Must; 286/287 are Must but **blocked on the client**, which is a dependency risk rather than a scheduling one.

## 3. Risks

| Risk | Handling tactic |
|---|---|
| **Validation blocker** — ETIM files carry **no required-field flag**, so "what blocks publish?" is unanswerable and firm validation requirements cannot be written | Client must define a **feature policy** per class (required / recommended / optional / conditional). The seam is recorded in **ADR-019** so the architecture does not stall while the values are pending. |
| **Feasibility** — matching accuracy against a controlled vocabulary is unproven; threshold uncalibrated | Prototyping + **golden test set (EPARTS-296)**. Owned by ML (EPARTS-289/290/291). |
| **Structural / dependency** — two hard cross-team contracts (ML-156, OCR-159) gate Phase-3 tickets (300/301/303) | Freeze both contracts early. **ADR-021** makes the ingestion→ML side of this an explicit, schema-frozen record. |
| **Data-model migration** — flat `IngestedRecord` → product + attribute split | Zero-data-loss cutover (EPARTS-301/302). Schema landed in ADR-014 / migration `0006`. |
| **Standard evolution (currency)** — ETIM will publish releases after 10.0 | **Scoped out.** The project is pinned to ETIM 10.0 EI (C-4, **ADR-020**). We deliberately accept that the catalog goes stale relative to ETIM rather than half-build an upgrade path. `etim_release_id` stays in the schema so published rows name the release they were matched under. Un-pinning would be a change request against C-4. |
| **Scope creep** — Compare-Tool / website-filter feature sets could pull in more classes and features | Held out of the phase-one baseline explicitly (see re-scope above). |

## 4. Open client decisions

These are requirements we must still elicit. They are blockers, not nice-to-haves.

- Phase-one valve/actuator **class list** (gates EPARTS-286)
- **Feature policy per class** — required / recommended / optional / conditional (gates EPARTS-287)
- Required-field **publish blockers**
- **Compare Tool / website filter** feature sets
- ETIM **"Other"** handling (attributes with no ETIM home)
- **Metric-canonical** storage and UI display units
- **PIMS ETIM-ID** storage format
- **One primary class per SKU** (confirm the rule)
- **Valve + actuator assemblies** handling
- **Mapping/policy approval ownership** — who signs off

*Closed since v1.1: **ETIM release-upgrade governance** — C-4 pins the project to release 10.0 EI and puts upgrades out of scope (ADR-020).*
