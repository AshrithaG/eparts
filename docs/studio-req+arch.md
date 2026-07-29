# Studio Crit — Requirements & Architecture

**Section:** Software System (requirements + architecture) · ~5 minutes, 4 slides · script: [`talking_script_req_arch_v2.md`](talking_script_req_arch_v2.md)
**Crit:** Thursday 30 July 2026, MSE 265, 300 South Craig Street
**Deck:** [`eParts_Section3_SoftwareSystem.pptx`](../../eParts_Section3_SoftwareSystem.pptx) · rebuild with [`build_section3_deck.py`](build_section3_deck.py)

This page is the index and the argument. It does not restate the artifacts — it points at them and says what each one is for.

---

## The one-line story

ETIM was a **mid-project requirements change against the v1.0 baseline**, not a new project, and it cascaded into the architecture. The system's *WHAT* moved from *"predict arbitrary product attributes"* to *"classify each product into an ETIM class and match its attributes to a controlled vocabulary."* Constrained classification, not free prediction.

The principle everything hangs off:

> **Original supplier data = evidence · ETIM data = standardized interpretation · confidence = how sure we are of the interpretation.**

The rubric asks for exactly this — *"if the architecture and requirements have changed significantly since Spring, these should be mentioned"* — and for requirements and system drivers to be **traceable through architecture, implementation, and validation**. The chain below closes.

---

## Artifact index

### Requirements

| Artifact | What it is |
|---|---|
| [`product-spec-v1.2.pdf`](product-spec-v1.2.pdf) · [`.tex`](product-spec-v1.2.tex) | The authoritative spec. **Version 1.2, 28 July 2026.** The version-history table *is* the change record: 1.1 integrated ETIM, 1.2 pinned the release. |
| [`product-spec-changelog.md`](product-spec-changelog.md) | Greppable companion: every ID added and amended, what no longer holds, the requirement inventory, and three owned defects. |
| [`etim-requirements-change.md`](etim-requirements-change.md) | How the change was **managed** — the four classes of requirements management, the re-scoped baseline, risks with handling tactics, open client decisions. |

**Added in v1.1:** HLR-6 (classify against ETIM, enrich with class/feature/value/unit IDs) · FR-9 (match to ETIM classes/features/controlled values+units, confidence per assignment, preserve the original) · FR-10 (load and maintain the ETIM dictionary) · DR-4 (PIMS writes keyed by ETIM identifiers).

**Added in v1.2:** C-4 — the project targets **ETIM release 10.0 (EI) for its duration**; later releases and cross-release migration are out of scope. FR-10 is scoped to that pinned release.

**Amended:** HLR-1, HLR-2, §2.1, §3.1, glossary, SCEN-1 step 3, SCEN-2 step 1.
**No longer holds:** FR-3 "predict attributes" · the flat `IngestedRecord`.

New IDs were **added, not renumbered** — deliberately, so every existing trace link survives.

### Architecture

| Artifact | What it is |
|---|---|
| [`../diagrams/pipe-filter-architecture-v6.png`](../diagrams/pipe-filter-architecture-v6.png) | **v6.0, July 2026, post-ETIM.** Source: [`.svg`](../diagrams/pipe-filter-architecture-v6.svg). Solid outline = running code, dashed = designed but not built. |
| [`../diagrams/pipe-filter-architecturev5.png`](../diagrams/pipe-filter-architecturev5.png) | v5.0, May 2026, pre-ETIM. Kept for the side-by-side. |
| [`adr-index.md`](adr-index.md) | All 21 ADRs, with a "Built?" column and the ETIM verdict on each spring ADR. |
| [`ETIM-ADR-ASSESSMENT.md`](ETIM-ADR-ASSESSMENT.md) | The change-impact analysis over ADRs 0001–0012, bucketed A/B/C. 29 June. |
| [`REQUIREMENTS-TO-ADR-MAPPING.md`](REQUIREMENTS-TO-ADR-MAPPING.md) | §1–9 map v2.0 → ADRs 0001–0012. **§10** maps v1.2 → ADRs 0013–0021, with forward/backward coverage and known gaps. |

### The five architectural deltas, v5.0 → v6.0

| # | Delta | ADR | Built? |
|---|---|---|---|
| 1 | **ETIM reference layer** — 10 release-scoped tables, ETIM 10.0 EI (pinned, C-4) | 0013 | Yes — alembic `0005` |
| 2 | **Matching decomposed** — class → feature → value/unit → ETIM validation → policy validation | 0016 | No — EPARTS-289/290/291 |
| 3 | **Staging split** — evidence (`staging_product` + `staging_raw_attribute`) vs. interpretation (`matched_product_attribute`) | 0014 | Evidence yes (alembic `0006`); interpretation no |
| 4 | **Explicit ingestion → ML seam** — frozen `ExtractedInput`, `extra="forbid"` so no interpretation can cross | 0021 | Partly — alembic `0007` merged; orchestrator wiring EPARTS-363 outstanding |
| 5 | **PIMS contract re-keyed** — `product_id + etim_release_id + etim_class_id + etim_feature_id` | 0017 | No — writer rework EPARTS-299 |

**Unchanged, and that is the point:** the pipe-and-filter spine (ADR-001), per-attribute routing granularity (ADR-004), the `PredictionServiceInterface` boundary (ADR-002), human-in-the-loop, and the append-only audit trail (ADR-010) all survived a major requirements change.

### New ETIM ADRs (0016–0021)

Written this cycle, against spec v1.2. ADRs 0001–0012 were **deliberately left unedited** — they record what the team decided in April. New ADRs supersede *forward* by reference.

| ADR | Decision | Status |
|---|---|---|
| [0016](0016-decompose-matching-into-staged-etim-class-feature-value-stages.md) | Decompose matching into staged class → feature → value/unit | Accepted |
| [0017](0017-rekey-pims-writeback-contract-on-etim-identifiers.md) | Re-key the PIMS writeback contract on ETIM identifiers | Accepted |
| [0018](0018-extend-routing-to-etim-signals-with-class-review-first.md) | Extend routing to ETIM signals, class-review-first | Accepted |
| [0019](0019-externalize-client-feature-policy-as-per-class-configuration.md) | Externalize the client feature policy as per-class configuration | Accepted (values blocked on client) |
| [0020](0020-pin-etim-release-10-0-for-the-project-duration.md) | Pin ETIM release 10.0 (EI) for the project duration | Accepted |
| [0021](0021-formalize-ingestion-to-ml-boundary-as-frozen-extracted-input-record.md) | Formalize the ingestion → ML boundary as a frozen record | Accepted |

---

## Traceability

```
business objective (industry-standard catalog)
  → HLR-6
    → FR-9 / FR-10 / DR-4
      → ADRs 0013–0021
        → tickets EPARTS-285…303
          → golden test set (EPARTS-296) / VAL-1–3
```

**Forward trace = completeness.** Every v1.2 requirement maps to at least one ADR, except **DC-2 (Auth0)** — an open gap, recorded rather than hidden.

**Backward trace = currency.** All nine ETIM ADRs anchor to a v1.2 requirement; none is orphaned, and none was written for work with no requirement behind it.

**Boundary.** Tracing stops at two cross-team interface contracts — ML input (EPARTS-156) and OCR output (EPARTS-159). We own those requirements; another stream implements them. ADR-021 is the ingestion-side half made explicit and schema-enforced.

---

## Evidence, verified

| Claim | Verified against |
|---|---|
| ETIM 10.0 EI: 159 groups, 5,640 classes, 17,377 features, 201,284 class-feature-values | `e2e-ocr-ing/docs/INGESTION_ETIM_PLAN.md`; loader tested against the real archive |
| 10 release-scoped reference tables | `src/eparts_ingestion/models/etim.py` — 10 model classes |
| ETIM 10.0 EI pinned; release-mismatch rejected on import | `src/eparts_ingestion/etim/loader.py` (checksum + release validation), C-4 in spec v1.2 |
| Idempotent checksummed import | `src/eparts_ingestion/etim/loader.py`, `cli/etim.py` |
| Evidence/interpretation split | `src/eparts_ingestion/models/staging.py`, `alembic/versions/0006_create_staging_tables.py` |
| Handoff record forbids interpretation | `src/eparts_ingestion/handoff/spec_model.py` — `extra="forbid"`, `frozen=True` |
| Handoff not yet wired into the pipeline | `src/eparts_ingestion/orchestrator.py` — zero references to `handoff` |
| Migrations | `alembic/versions/0005`, `0006`, `0007` |

---

## Owned defects

Naming these is worth more than hiding them.

1. **Two spec lineages exist.** This one runs 0.1 → 0.5 → 1.0 (24 Apr) → 1.1 → 1.2, with FR-1…10, QAS-1…2, C-1…4. A parallel *"Document Version 2.0"* (24 Apr) carries FR-1…13, QAS-1…5 (QAS-1 = Accuracy ≥95%), C-1…8. It is **not** an ancestor of this one, so it is not committed here — pairing them would imply a version chain that does not exist.
2. **ADRs 0001–0015 cite the other lineage's IDs.** QAS-3/4/5, C-7, FR-11/12/13 do not resolve against v1.2. Reconciling the two ID spaces is open work; the spring ADRs stay unedited.
3. **Two ADR series collide.** `docs/00NN-*.md` (authoritative) and `docs/adr/ADR-00N-*.md` (agent-generated) use overlapping numbers for different decisions, and `.github/workflows/requirements-extraction.yml` writes into `docs/adr/**`, so the collision will grow until that workflow is repointed.
4. **DC-2 (Auth0)** — mandatory in v1.2, a stretch goal in the April document, no ADR either way.
5. **Nothing exercises a second ETIM release**, and under C-4 nothing will. The release-scoping columns are kept for provenance, so they will look redundant to anyone reading the schema without ADR-020.

---

## Open client decisions

Requirements we must still elicit. Two of them gate validation.

Phase-one valve/actuator **class list** (EPARTS-286) · **feature policy per class** (EPARTS-287 — ETIM ships no required-field flag, so "what blocks publish?" is unanswerable until this lands) · required-field publish blockers · Compare Tool / website-filter feature sets · ETIM **"Other"** handling · **metric-canonical** storage and UI display units · PIMS ETIM-ID storage format · one-primary-class-per-SKU confirmation · valve + actuator assemblies · mapping/policy **sign-off ownership**.

*Closed: **ETIM release-upgrade governance.** C-4 pins the project to release 10.0 EI and puts upgrades out of scope (ADR-020). That took the count from six to five.*

ADR-019 holds the policy seam open so the build does not stall waiting on it. ADR-020 closed the release question outright by pinning the standard rather than leaving it unspecified.

---

## Q&A prep

**Telemetry — the one visible inconsistency.** `ETIM-ADR-ASSESSMENT.md` says the stack is Prometheus + OpenTelemetry + structlog and recommends superseding ADR-012, and the code backs that up. The actual position is narrower: **Datadog is the production target; Prometheus + OTel + structlog is the local development substrate.** ADR-012 stands, and the assessment's Bucket A verdict on it is wrong — it was written from the code alone, without the deployment intent. The v6 diagram carries both labels so it reads as a two-environment choice.

**What's running vs. what's designed.** Reference layer, evidence staging split, and the `ExtractedInput` handoff are built and merged. The matching stages, ETIM-aware routing, and the re-keyed writeback are designed only. The diagram marks the distinction; do not claim more.

**Why weren't ADRs 0001–0012 fixed?** They record what we believed in April. Superseding forward keeps the decision history readable; editing in place erases it. `ETIM-ADR-ASSESSMENT.md` is the bridge.

**Why pin ETIM instead of building an upgrade path?** Because the upgrade path is a diff report, a bulk re-match and a second review queue for an event that will not happen inside this project, and it could not be finished anyway — nobody has decided who authorizes an upgrade. Pinning is a decision we can defend; a half-built upgrade path is not. C-4 says so explicitly, so it reads as scope rather than an omission. Un-pinning would be a change request against C-4.

**Why did accuracy get harder?** Matching against a controlled vocabulary is a sharper test than fuzzy string similarity — previously "close enough" answers now count as failures. Auto-accept rate will fall relative to the pre-ETIM baseline before it rises. That is the intended trade: throughput for correctness, on a system where wrong product data becomes a contractor's wrong field order.

**What would we do differently?** Reconcile the two spec lineages earlier, and wire the handoff builder into the orchestrator (EPARTS-363) so the boundary is exercised in production flow rather than only in unit tests.
