# Product Specification — change record

Authoritative document: **`product-spec-v1.4.pdf`** — *Product Specification, Intelligent Ingestion & Attribute Prediction System*, eParts Studio Team, **Document Version 1.4, 29 July 2026**. LaTeX source: `product-spec-v1.4.tex`.

This file is the greppable companion to that PDF. ADRs cite requirement IDs; this is where those IDs resolve.

## Version history (verbatim from the spec's own table)

| Version | Date | Change |
|---|---|---|
| 0.1 | Feb 01, 2026 | Initial draft based on eParts architectural review. |
| 0.5 | Feb 10, 2026 | Added detailed functional requirements for Ingestion and ML Service. |
| 1.0 | Apr 24, 2026 | Baseline specification for development. |
| 1.1 | July 23, 2026 | Integrated ETIM classification/enrichment; corrected OCR (Azure Document Intelligence) and ingestion (channels, Azure Blob storage, quarantine). |
| 1.2 | July 28, 2026 | Pinned the project to ETIM release 10.0 (language EI) for its duration (new constraint C-4); scoped FR-10 accordingly and removed the implied obligation to adopt later ETIM releases. |
| **1.3** | **July 29, 2026** | **Corrected the placement of ETIM matching. ETIM class/feature/value matching is performed by the ML service *after* attribute matching, not by the Intermediate Structured Layer during normalization. HLR-2, §2.1 and SCEN-1 amended; FR-9 attributed to the ML service.** |
| **1.4** | **July 29, 2026** | **Closed a trace gap opened by 1.1: the Quality Attribute Scenarios and Validation Requirements sections had not been revised for ETIM. Added QAS-3, VAL-4 and VAL-5. Also corrected three descriptions left inconsistent by 1.3 (the Canonical Table glossary entry and §1.2 both still implied ETIM keying during normalization; §1.2 did not mention ETIM matching at all), and replaced the §2 architecture figure with the current v6.0 diagram. No existing requirement was changed.** |

All four revisions are **changes against the v1.0 baseline**, not re-baselines. New IDs were *added*; existing HLR and DR numbering was preserved so prior trace links survive.

**v1.1** integrated ETIM. **v1.2** fixed the *scope* of that integration — we are pinned to one ETIM release and will not chase later ones ([ADR-020](0020-pin-etim-release-10-0-for-the-project-duration.md)). **v1.3** fixed the *placement* — ETIM matching belongs to the ML service, behind attribute matching, not to normalization ([ADR-016](0016-decompose-matching-into-staged-etim-class-feature-value-stages.md)). **v1.4** fixed our own *trace coverage*: we had spent three revisions on requirements and never revisited the quality scenarios or the validation tests, so for a month those two sections described a pre-ETIM system.

### Added in v1.4 — quality scenario and validation coverage

| ID | Content | Status |
|---|---|---|
| **QAS-3** | Modifiability — the client changes which ETIM features are mandatory for a class; the change is per-class configuration, no matching/routing/validation code is modified ([ADR-019](0019-externalize-client-feature-policy-as-per-class-configuration.md)). Measure: takes effect for the next batch with no code deployment. | Seam built, policy values still open on the client |
| **VAL-4** | Load ETIM 10.0 (EI), then load it again. All 159 groups / 5,640 classes / 17,377 features / 201,284 class-feature-values present; second run is a no-op. | **Covered by automated tests** — `tests/unit/test_etim_loader.py` (10 tests), `tests/integration/test_etim_real_files.py` (1 test, real release files). Both need a DB fixture; run locally, not in CI. |
| **VAL-5** | A below-threshold ETIM class assignment routes the item to class review, and no attribute-level routing happens for it ([ADR-018](0018-extend-routing-to-etim-signals-with-class-review-first.md)). | **Specified, not executable** — the matching stages are designed and not built |

⚠️ **QAS-3 collides by number with the v2.0 lineage's QAS-3 (Accuracy).** QAS-3 is the next free number in *this* document; skipping it to avoid a foreign document's numbering would be worse. This is the same two-lineage reconciliation already recorded under known defects below.

## What ETIM changed

The system's *WHAT* moved from **"predict arbitrary product attributes"** to **"classify each product into the ETIM standard and map its attributes to a controlled vocabulary (class → feature → value / unit)."** Constrained classification, not free prediction.

The governing principle, now stated in the spec's glossary and §2.1:

> **Original supplier data = evidence · ETIM data = standardized interpretation · confidence = how sure we are of the interpretation.**

### Requirements added in v1.1

| ID | Statement (abridged) |
|---|---|
| **HLR-6** | The system shall classify products against the ETIM standard and enrich supplier attributes with ETIM identifiers (class, feature, value, unit), keeping the original values as evidence. |
| **FR-9** | After attribute matching, the Attribute Prediction Service (ML) shall match attributes to ETIM classes, features, and controlled values/units, attaching a confidence score to each ETIM assignment and preserving the original supplier value. *(Attributed to ML in v1.3.)* |
| **FR-10** | The system shall load and maintain the ETIM reference dictionary (product groups, classes, features, values, units, and class–feature–value mappings) as reference data for the pinned ETIM release identified in C-4. *(Wording scoped in v1.2; originally "as versioned reference data".)* |
| **DR-4** | *(Must, traces HLR-6)* Approved data written to PIMS shall be keyed by ETIM identifiers (release, class, feature); the writeback idempotency key shall include these identifiers. |

### Added in v1.2

| ID | Statement (abridged) |
|---|---|
| **C-4** | *(constraint)* The system shall target ETIM release 10.0 (language EI) for the duration of this project. Adopting later ETIM releases, and migrating already-classified products between releases, are out of scope. |

C-4 exists because FR-10 as first written implied an obligation we were not going to meet. Pinning the release is a decision we can defend; a half-built upgrade path is not. The `etim_release_id` field stays in the schema for provenance — see ADR-020.

### Amended in v1.3 — where ETIM matching happens

The v1.1 edit put ETIM keying in the wrong component. ETIM assignment is a *matching decision with a confidence attached*, so it belongs to the ML service and runs **after** attribute matching. Normalization has no model, no confidence, and no route to human review, so it cannot make that decision.

| ID / section | v1.1–v1.2 said | v1.3 says |
|---|---|---|
| **HLR-2** | "normalize into a standardized, **ETIM-keyed** intermediate structure (mechanical cleanup followed by mapping to ETIM classes, features, and values)" | "normalize into a standardized intermediate structure through **mechanical cleanup only**… ETIM class, feature, and value assignment is performed **downstream by the ML service** (HLR-6, FR-9), not during normalization" |
| **§2.1** Intermediate Structured Layer | converts raw inputs into "ETIM-keyed canonical tables" | converts raw inputs into canonical tables holding the supplier's own values as evidence; "it does **not** assign ETIM identifiers" |
| **§2.1** Attribute Prediction Service | "Runs ML models and heuristic rules" | **"(ML): Owns all matching, in two phases"** — attribute matching, then ETIM matching (class, feature, value/unit, ETIM validation, policy validation) |
| **FR-9** | "The system shall match normalized attributes…" | "**After attribute matching, the Attribute Prediction Service (ML) shall** match attributes…" |
| **SCEN-1** step 3 | normalization "maps to ETIM class/features" | "No ETIM assignment happens here"; step 4 now cites FR-3 **and FR-9** and does both matching phases |

### Requirements amended in v1.1

| ID / section | Before | After |
|---|---|---|
| **HLR-2** | "normalize ingested data into a standardized intermediate structure" | "...into a standardized, **ETIM-keyed** intermediate structure (mechanical cleanup followed by mapping to ETIM classes, features, and values), **preserving original supplier values as evidence**" |
| **HLR-1** | Email/SFTP/CSV/PDF as if all live | SFTP and direct upload **today**; Email and web **planned** |
| **§2.1** Intermediate Structured Layer | "standard canonical tables" | "**ETIM-keyed** canonical tables (class / feature / value), preserving original supplier values as evidence" |
| **§2.1** Ingestion Gateway | generic OCR | Datasheet PDFs OCR'd via **Azure AI Document Intelligence**; text-native CSV/PDF parsed deterministically |
| **§3.1** | — | Azure AI Document Intelligence + Azure OpenAI named; Azure Blob **accessed through an S3-compatible interface (MinIO in local/dev)** |
| **Glossary** | — | ETIM entry added; PIMS entry now states approved output is **keyed by ETIM identifiers** |
| **SCEN-1 step 3** | "Normalizes CSV columns to Canonical Table format" | "Cleans and normalizes CSV columns into the **ETIM-keyed** Canonical Table (maps to ETIM class/features), **retaining original values**" |
| **SCEN-2 step 1** | "Ingests PDF. OCR extraction is messy." | Names the Azure Document Intelligence + LLM extraction path |

### What no longer holds

- **FR-3 "predict product attributes"** → constrained *matching* to ETIM values. This changes both the definition of accuracy and the ML contract.
- **The flat `IngestedRecord`** → `staging_product` + `staging_raw_attribute` split with evidence columns (see ADR-014). The flat path is to be retired.

### New requirement *types* introduced

- **Reference-data requirement** (FR-10) — maintaining an external dictionary is neither a classic behaviour nor a quality attribute. It is tied to an external standard with its own release cadence, which forced a scope decision: we **pin to ETIM 10.0 EI** and put upgrades out of scope (C-4, ADR-020).
- **Derived cascade** (DR-4) — the PIMS idempotency key derives from HLR-6; confidence now attaches **per ETIM assignment**, not per raw attribute.
- **New constraints** — metric-canonical storage where ETIM expects metric units; one ETIM class per sellable SKU; English (EI) ETIM language; phase-one valve/actuator scope only.

## Requirement ID inventory (v1.4)

- **HLR-1 … HLR-6**
- **FR-1 … FR-10**
- **DR-1 … DR-4**
- **QAS-1** Modifiability (extensibility — new supplier format in ≤4 engineering hours) · **QAS-2** Usability (reviewer processes 10 items/min) · **QAS-3** Modifiability (client feature policy is configuration, no deploy)
- **C-1** cost-effective design · **C-2** privacy compliance (GDPR/CCPA deletion) · **C-3** breadth-first delivery · **C-4** ETIM release pinned to 10.0 EI
- **DC-1** Python backend · **DC-2** Auth0 · **DC-3** raw files preserved in Azure Blob
- **VAL-1** ingestion trigger · **VAL-2** routing logic · **VAL-3** PIMS integration · **VAL-4** ETIM dictionary load (runs today) · **VAL-5** class review before attribute routing (specified only)
- **SCEN-1** end-to-end happy path · **SCEN-2** low-confidence human-in-the-loop

## Known traceability defects (owned, not hidden)

1. **Two spec lineages exist.** A parallel document — *Product Specification, "Document Version 2.0", April 24 2026* — carries a different and larger ID set (FR-1…13, QAS-1…5 with QAS-1 = Accuracy ≥95%, C-1…8, DR-1…3). It is **not** an ancestor of this one; this lineage runs 0.1 → 0.5 → 1.0 (Apr 24) → 1.1 → 1.2 → 1.3 → 1.4. That document is not committed here to avoid implying a version chain that does not exist.
2. **ADRs 0001–0015 cite the other lineage's IDs.** References to QAS-4, QAS-5, C-7 and FR-11/12/13 do not resolve against v1.4 at all, and their QAS-3 (Accuracy) resolves to a *different* scenario than this lineage's QAS-3 (client feature policy, added in v1.4). Those ADRs are the spring record and are deliberately left unedited (see `ETIM-ADR-ASSESSMENT.md`); ADRs 0016–0021 cite v1.4 IDs. Reconciling the two ID spaces is open work.
3. **Two ADR series collide.** `docs/00NN-*.md` (the platform series, 0001–0021) and `docs/adr/ADR-00N-*.md` (an agent-generated series) use overlapping numbers for different decisions. Only the `00NN-` series is authoritative. See `adr-index.md`.

## Open client decisions that still gate requirements

Phase-one valve/actuator class list · **feature policy per class** (required / recommended / optional / conditional — this blocks firm validation requirements) · required-field publish blockers · Compare Tool and website-filter feature sets · ETIM "Other" handling · metric-canonical storage and UI display units · PIMS ETIM-ID storage format · one-primary-class-per-SKU confirmation · valve + actuator assemblies · mapping/policy sign-off ownership.

*ETIM release-upgrade governance was on this list and is now closed — C-4 puts it out of scope (ADR-020).*
