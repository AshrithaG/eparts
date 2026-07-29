# Product Specification — change record

Authoritative document: **`product-spec-v1.2.pdf`** — *Product Specification, Intelligent Ingestion & Attribute Prediction System*, eParts Studio Team, **Document Version 1.2, 28 July 2026**. LaTeX source: `product-spec-v1.2.tex`.

This file is the greppable companion to that PDF. ADRs cite requirement IDs; this is where those IDs resolve.

## Version history (verbatim from the spec's own table)

| Version | Date | Change |
|---|---|---|
| 0.1 | Feb 01, 2026 | Initial draft based on eParts architectural review. |
| 0.5 | Feb 10, 2026 | Added detailed functional requirements for Ingestion and ML Service. |
| 1.0 | Apr 24, 2026 | Baseline specification for development. |
| 1.1 | July 23, 2026 | Integrated ETIM classification/enrichment; corrected OCR (Azure Document Intelligence) and ingestion (channels, Azure Blob storage, quarantine). |
| **1.2** | **July 28, 2026** | **Pinned the project to ETIM release 10.0 (language EI) for its duration (new constraint C-4); scoped FR-10 accordingly and removed the implied obligation to adopt later ETIM releases.** |

Both revisions are **changes against the v1.0 baseline**, not re-baselines. New IDs were *added*; existing HLR and DR numbering was preserved so prior trace links survive.

**v1.1** integrated ETIM. **v1.2** fixed the scope of that integration: we are pinned to one ETIM release and will not chase later ones — see [ADR-020](0020-pin-etim-release-10-0-for-the-project-duration.md).

## What ETIM changed

The system's *WHAT* moved from **"predict arbitrary product attributes"** to **"classify each product into the ETIM standard and map its attributes to a controlled vocabulary (class → feature → value / unit)."** Constrained classification, not free prediction.

The governing principle, now stated in the spec's glossary and §2.1:

> **Original supplier data = evidence · ETIM data = standardized interpretation · confidence = how sure we are of the interpretation.**

### Requirements added in v1.1

| ID | Statement (abridged) |
|---|---|
| **HLR-6** | The system shall classify products against the ETIM standard and enrich supplier attributes with ETIM identifiers (class, feature, value, unit), keeping the original values as evidence. |
| **FR-9** | The system shall match normalized attributes to ETIM classes, features, and controlled values/units, attaching a confidence score to each ETIM assignment and preserving the original supplier value. |
| **FR-10** | The system shall load and maintain the ETIM reference dictionary (product groups, classes, features, values, units, and class–feature–value mappings) as reference data for the pinned ETIM release identified in C-4. *(Wording scoped in v1.2; originally "as versioned reference data".)* |
| **DR-4** | *(Must, traces HLR-6)* Approved data written to PIMS shall be keyed by ETIM identifiers (release, class, feature); the writeback idempotency key shall include these identifiers. |

### Added in v1.2

| ID | Statement (abridged) |
|---|---|
| **C-4** | *(constraint)* The system shall target ETIM release 10.0 (language EI) for the duration of this project. Adopting later ETIM releases, and migrating already-classified products between releases, are out of scope. |

C-4 exists because FR-10 as first written implied an obligation we were not going to meet. Pinning the release is a decision we can defend; a half-built upgrade path is not. The `etim_release_id` field stays in the schema for provenance — see ADR-020.

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

## Requirement ID inventory (v1.2)

- **HLR-1 … HLR-6**
- **FR-1 … FR-10**
- **DR-1 … DR-4**
- **QAS-1** Modifiability (extensibility — new supplier format in ≤4 engineering hours) · **QAS-2** Usability (reviewer processes 10 items/min)
- **C-1** cost-effective design · **C-2** privacy compliance (GDPR/CCPA deletion) · **C-3** breadth-first delivery · **C-4** ETIM release pinned to 10.0 EI
- **DC-1** Python backend · **DC-2** Auth0 · **DC-3** raw files preserved in Azure Blob
- **VAL-1** ingestion trigger · **VAL-2** routing logic · **VAL-3** PIMS integration
- **SCEN-1** end-to-end happy path · **SCEN-2** low-confidence human-in-the-loop

## Known traceability defects (owned, not hidden)

1. **Two spec lineages exist.** A parallel document — *Product Specification, "Document Version 2.0", April 24 2026* — carries a different and larger ID set (FR-1…13, QAS-1…5 with QAS-1 = Accuracy ≥95%, C-1…8, DR-1…3). It is **not** an ancestor of this one; this lineage runs 0.1 → 0.5 → 1.0 (Apr 24) → 1.1 → 1.2. That document is not committed here to avoid implying a version chain that does not exist.
2. **ADRs 0001–0015 cite the other lineage's IDs.** References to QAS-3, QAS-4, QAS-5, C-7, FR-11/12/13 do not resolve against v1.2. Those ADRs are the spring record and are deliberately left unedited (see `ETIM-ADR-ASSESSMENT.md`); ADRs 0016–0021 cite v1.2 IDs. Reconciling the two ID spaces is open work.
3. **Two ADR series collide.** `docs/00NN-*.md` (the platform series, 0001–0021) and `docs/adr/ADR-00N-*.md` (an agent-generated series) use overlapping numbers for different decisions. Only the `00NN-` series is authoritative. See `adr-index.md`.

## Open client decisions that still gate requirements

Phase-one valve/actuator class list · **feature policy per class** (required / recommended / optional / conditional — this blocks firm validation requirements) · required-field publish blockers · Compare Tool and website-filter feature sets · ETIM "Other" handling · metric-canonical storage and UI display units · PIMS ETIM-ID storage format · one-primary-class-per-SKU confirmation · valve + actuator assemblies · mapping/policy sign-off ownership.

*ETIM release-upgrade governance was on this list and is now closed — C-4 puts it out of scope (ADR-020).*
