# eParts Requirements Artifact Set

This folder holds the **Requirements artifact** for the eParts Intelligent Ingestion
& Attribute Prediction System, produced and maintained under the project's
Software Engineering System (SES) and the LLM-Aided SE Framework.

It is **not a single document**. It is a small, versioned artifact set that flows
together through the Requirements Engineering process described below.

---

## 1. Artifacts in this folder

| File | Purpose | Format | Owner | Lifecycle |
|---|---|---|---|---|
| `eparts_requirements.md` | Human-readable body of the requirements specification (Introduction, HLRs, FRs in EARS, DRs, QAS, Operational Scenarios, Design Constraints, Validation). | Markdown | Requirements Lead | Draft → Under Review → Approved → Baselined |
| `eparts_requirements.yaml` | Structured front matter and machine-readable mirror of the requirements tables (HLR / FR / DR / QAS / DC / VAL). Source of truth for downstream agents. | YAML | Requirements Lead | Draft → Under Review → Approved → Baselined |
| `user_stories.yaml` | One story per FR/DR with acceptance criteria. Auto-maintained by an agent that watches `eparts_requirements.yaml`. | YAML | Product Owner (approves) / Agent (drafts) | Draft → Approved |
| `traceability.csv` | HLR ↔ FR ↔ DR ↔ QAS ↔ VAL ↔ Test traceability matrix. Regenerated whenever the YAML changes. | CSV | Requirements Lead | Regenerated artifact |
| `requirements.metrics.yaml` | Process measurements for the Requirements Engineering process itself (time, defects, reviewer, prompt effectiveness, tokens, story deltas, run history). | YAML | QA / Process Lead | Append-only log |
| `../adrs/` | Architecture Decision Records linked from requirements when a requirement locks in an architectural choice. | Markdown | Architecture Lead | Draft → Approved |
| `README.md` | This file. Describes the ETVX of the Requirements Engineering process. | Markdown | Requirements Lead | Living document |

All artifacts (except `requirements.metrics.yaml`, which is an append-only log)
follow the SES lifecycle: **Draft → Under Review → Approved → Baselined**.
The current state is recorded in the front matter of each file.

---

## 2. Source inputs (out-of-folder)

These inputs feed the Requirements Engineering process and are referenced from
`eparts_requirements.yaml.source_inputs`:

- `../Revised eParts Project Statement of Work.docx`
- `../eParts General Info.pdf`
- `../Context Diagram V3.pdf` / `Context Diagram V3.png`
- `../Notional Software Workflow Diagram_version2 (02_11).pdf`
- `../Software Engineering System (SES).pdf`
- `../LLM Aided SE Framework - Studio Orientatiojn Day Presentation.pdf`
- Meeting notes and design discussion summaries (linked per requirement where applicable)

Per SES §4.2.1, **meeting notes and discovery discussions feed into requirements
artifacts**; they are not optional inputs.

---

## 3. Requirements Engineering process (ETVX)

This is the L1 process that produces and maintains the artifacts above. It is an
instantiation of SES §4.2.1 and the LLM-Aided SE Framework's L1 Requirements
diagram (slide 16).

### Entry criteria

The process may begin a new revision cycle when **any** of the following hold:

1. A new or revised source input is available (SOW change, new meeting notes,
   updated product plan, new context diagram).
2. A stakeholder change request is filed against an Approved or Baselined
   requirement.
3. A defect found downstream (architecture, implementation, test) traces back
   to a missing, ambiguous, or incorrect requirement.
4. A scheduled review interval elapses (default: end of each iteration).

Pre-conditions:
- Source inputs are accessible and version-pinned.
- The current `eparts_requirements.yaml` state is known (Draft / Under Review /
  Approved / Baselined).
- The Requirements Lead and at least one Stakeholder Reviewer are identified.

### Tasks

1. **Requirements Extraction (AI-assisted).**
   The Requirements Lead, with LLM assistance, extracts or revises:
   - HLRs (high-level requirements)
   - FRs in EARS form
   - DRs (derived requirements) with priority and HLR trace
   - QAS using the SEI 6-part template
   - Operational scenarios with per-step requirement refs
   - Design constraints with source attribution
   - Validation requirements
   The LLM contributes: template generation, completeness checking, ambiguity
   detection, and cross-reference checks. **The human owns scope, meaning, and
   approval (SES §4.2.1).**
2. **Structured Mirror Update.**
   Update `eparts_requirements.yaml` so that the structured tables match the
   Markdown body. The YAML is the source of truth for downstream agents.
3. **User Story Sync (Agentic).**
   An agent watches `eparts_requirements.yaml` and updates `user_stories.yaml`
   so that every FR and "Must"/"Should" DR has a corresponding story with
   acceptance criteria. Story deltas are logged.
4. **Traceability Refresh.**
   Regenerate `traceability.csv` so HLR ↔ FR ↔ DR ↔ QAS ↔ VAL ↔ Test links are
   complete.
5. **Metrics Capture.**
   Append a run record to `requirements.metrics.yaml` (see §5).

### Verification

A revision is verified before it can advance state.

- **Completeness check (AI-assisted):** every HLR has at least one FR; every
  FR has at least one VAL; every DR traces to an HLR; every QAS has a Measure.
- **Ambiguity check (AI-assisted):** flag EARS violations, vague modal verbs,
  unmeasurable QAS, and missing acceptance criteria in user stories.
- **Stakeholder review (human):** Ops Reviewer, Architecture Lead, and Data/ML
  Lead read the diff. Comments are resolved or recorded as deferred.
- **Feasibility assessment (human):** Engineering Lead confirms each FR/DR is
  buildable within the iteration, or the requirement is moved out of scope.
- **Traceability check:** `traceability.csv` has no orphan rows.

A revision fails verification if any of the above is open. Failures return the
artifact to **Draft** state with review comments captured in the metrics log.

### Exit criteria

A revision exits the process when **all** of the following are true:

1. All verification checks pass.
2. All review comments are resolved or explicitly deferred with a tracked
   follow-up.
3. The state field in `eparts_requirements.yaml` is advanced:
   - **Draft** while authoring.
   - **Under Review** when verification is in progress.
   - **Approved** when the Requirements Lead and required reviewers sign off.
   - **Baselined** when the iteration's scope is locked; further changes
     require a new revision cycle.
4. `user_stories.yaml`, `traceability.csv`, and `requirements.metrics.yaml`
   are updated and committed in the same change.
5. The new version is recorded in the Version History block of
   `eparts_requirements.md`.

---

## 4. Resources (who does what)

Per SES §5.1 / §5.2:

| Role | Responsibility in this process |
|---|---|
| Requirements Lead (Team/Project Lead) | Owns scope, runs extraction, drives reviews, advances state. |
| Architecture Lead | Reviews requirements for architectural feasibility; raises ADRs when a requirement implies a decision. |
| Data / ML Lead | Validates ML-related FRs (confidence scoring, routing thresholds, retraining). |
| Engineering Lead | Feasibility and buildability sign-off. |
| QA / Process Lead | Owns `requirements.metrics.yaml`, validation requirements, and quality gates. |
| Ops Reviewer (stakeholder) | Validates personas, operational scenarios, and review-UI requirements. |
| **AI / LLM** | Drafts, completeness-checks, detects ambiguity, generates user-story templates and acceptance criteria, regenerates traceability. **Does not approve.** No proprietary data is uploaded to external AI tools (SES §5.2). |

---

## 5. Measurements

Captured per run in `requirements.metrics.yaml`. Aligned with the LLM-Aided SE
Framework slide 19 (L1 Partial Measurement Design - Requirements Detail) and
SES §6.

Per-run fields:

- `run_id`, `timestamp`, `triggered_by`
- `time_spent_minutes` (total, and broken down by extraction / review / sync)
- `defects_found` (count, by type, by reviewer)
- `prompt_effectiveness` (re-prompt rate, useful-output ratio)
- `tokens_used` (input / output)
- `example_quality` (subjective 1-5 from author + reviewer)
- `story_deltas` (count of stories added / changed / removed)
- `run_history_ref` (link to the conversation or commit that produced the change)

Aggregate metrics reviewed at each iteration boundary:

- Documentation churn (changes per requirement per iteration)
- Number of times a requirement is revisited after Baselined
- Review latency (Under Review → Approved time)
- Human correction volume vs LLM draft size

---

## 6. Conventions

- **IDs are stable.** Once an HLR/FR/DR/QAS/DC/VAL ID is published in an
  Approved revision, it is never reused or renumbered. Deprecated requirements
  are marked `state: deprecated` rather than deleted.
- **EARS form** for all FRs: *"When/While/If \<trigger>, the \<system> shall
  \<response>."* Ambient requirements use *"The \<system> shall \<response>."*
- **Traceability is mandatory.** Every DR cites its parent HLR. Every VAL cites
  the requirement(s) it verifies.
- **One requirement per row / list item.** No compound requirements joined by
  "and".
- **No proprietary supplier data** in any file in this folder, including
  examples (SES §5.2).

---

## 7. Quick start for a new revision

1. Create a working branch.
2. Set `state: Draft` in `eparts_requirements.yaml` front matter and bump the
   version (`X.Y` minor for content changes, `X.0` major for scope changes).
3. Run extraction; edit `eparts_requirements.md` and mirror into
   `eparts_requirements.yaml`.
4. Let the user-story agent regenerate `user_stories.yaml` and review the diff.
5. Regenerate `traceability.csv`.
6. Append a run record to `requirements.metrics.yaml`.
7. Move state to `Under Review`, request reviewers.
8. Resolve comments → `Approved` → at iteration lock → `Baselined`.
