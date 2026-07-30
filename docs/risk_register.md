# eParts Risk Register

**Total Risks:** 21  
**Critical:** 4 | **High:** 8 | **Medium:** 9

**Mitigating:** 3  **Open:** 18  

| # | Severity | Category | Title | Risk Statement | Mitigation | Status | Owner |
|---|----------|----------|-------|----------------|------------|--------|-------|
| 1 | **critical** | technical | Confidence threshold miscalibration | IF the 0.85 confidence threshold is not calibrated with empirical data THEN the review queue either overwhelms the catalog team (threshold too high) or lets incorrect data into PIMS (threshold too lo… | Refinement 1: Run prototype on >=200 labeled submissions, compute precision-recall curves | open | team |
| 2 | **critical** | schedule | Data access delay blocking ML development | IF client data is not available for model training THEN ML development stalls and the team cannot validate the hybrid approach RESULTING IN schedule delays and inability to meet prototype milestones. | Data received ~Feb 22; team started basic model tests. Continue pressing for complete dataset. | mitigating | team |
| 3 | **critical** | health | Team burnout from capstone + coursework overlap | IF team members are overloaded with concurrent capstone and coursework demands THEN productivity and code quality decline as fatigue accumulates RESULTING IN missed deadlines, increased defect rates,… | Establish sustainable sprint cadence; enforce work-hour limits; rotate intensive tasks across members. | open | team |
| 4 | **critical** | team | Single point of failure — key person unavailable | IF a key team member becomes unavailable (illness, emergency, dropout) THEN critical knowledge and in-progress work are inaccessible RESULTING IN blocked deliverables and schedule delays until knowle… | Cross-train on all subsystems; maintain pair-programming rotation; document decisions in SharedMemory. | open | team |
| 5 | **high** | technical | Insufficient training data (<200 labeled examples) | IF fewer than 200 labeled examples are available for training THEN the embedding layer will be undertrained and the hybrid approach falls back to pure rules with limited coverage (~40-60%) RESULTING… | Secure labeled data from eParts; augment with synthetic examples if needed | open | team |
| 6 | **high** | technical | PIMS staging schema incompatibility (P1-C pending) | IF Jake does not deliver the P1-C schema or staging tables use incompatible columns THEN the writeback mechanism requires redesign RESULTING IN schedule delays and potential data integration failures. | Refinement 4: Map P1-C columns to canonical schema; integration-test 10 sample records | open | team |
| 7 | **high** | business | Catalog team capacity vs review volume | IF per-attribute routing still produces too many review items THEN the 1.5 + 3 FTE catalog team cannot handle the volume RESULTING IN no labor savings and failure of the core value proposition. | Measure actual review volume in prototype; adjust threshold iteratively | open | team |
| 8 | **high** | technical | Drift detection metrics and baselines undefined | IF baseline metrics, alert thresholds, and feedback loops are not defined before deployment THEN model drift will go undetected RESULTING IN silent accuracy degradation and no trigger for retraining. | Define baseline metrics before prototype; SES measurement system can track these | open | team |
| 9 | **high** | measurement | Measurement validity for AI effectiveness | IF AI effectiveness is not measured with rigorous before/after comparisons THEN the team cannot demonstrate genuine AI-driven improvement RESULTING IN weak capstone evaluation and inability to justif… | SES measurement system tracks tokens, cost, latency, human review rate, correction rate per agent. Prompt regression testing validates quality over time. | open | team |
| 10 | **high** | technical | Model selection uncertainty | IF the ML model selection remains unresolved and the hybrid approach (ADR-1) is not validated THEN the prediction pipeline lacks a stable foundation RESULTING IN rework risk and delayed confidence in… | ADR-1 hybrid approach with clear trigger conditions for switching to pure ML or pure rules | open | team |
| 11 | **high** | dependency | Integration dependency on Jake (PIMS schema) | IF Jake does not deliver the P1-C staging table schema on time THEN the writeback mechanism cannot be implemented against the real target RESULTING IN critical-path schedule slip and potential redesi… | Refinement 4 scheduled; team-owned buffer table as fallback | open | Hrishik |
| 12 | **high** | schedule | Throughput estimates do not transfer from construction to integration | IF the completion forecast samples weekly throughput from weeks that were entirely construction work, AND the remaining work shifts to integration against the client's PIMS environment where progress… | Reduces impact: weight recent weeks more heavily than older ones once integration work starts, so the sample tracks the kind of work actually being done, and quote the conservative end of the through… | open | Ashritha Gonuguntla |
| 13 | **medium** | technical | Alpha weighting sensitivity in hybrid scoring | IF small tuning errors occur in alpha weighting (currently 0.7) THEN routing behavior changes disproportionately, suppressing the more accurate signal source RESULTING IN misrouted items and unreliab… | Refinement 3: Sweep alpha 0.3-0.9; measure ECE, precision, coverage | open | team |
| 14 | **medium** | technical | Attribute correlation invalidates per-attribute routing | IF correlated attributes are reviewed independently THEN inconsistent records are produced when cross-attribute errors exceed 30% RESULTING IN need to switch from per-attribute to per-record routing,… | Refinement 2: Pairwise mutual information analysis on labeled data | open | team |
| 15 | **medium** | ux | Human review interface design not decided | IF the reviewer walkthrough reveals that tabular export is insufficient for review tasks THEN a custom review UI must be added to scope RESULTING IN scope expansion, additional development effort, an… | Refinement 5: Present 30 sample items to Brian/Dewey; measure time and accuracy | open | team |
| 16 | **medium** | dependency | ETIM release pin leaves the catalog progressively stale | IF the client's suppliers begin publishing against ETIM 11.0 while the platform remains pinned to release 10.0 EI (constraint C-4) THEN new classes, features and values are unavailable to the matcher… | Release pinned explicitly as constraint C-4 rather than left unspecified. Every ETIM reference row, the interpretation table and the PIMS writeback key all carry etim_release_id (ADR-013/014/017), so… | mitigating | team |
| 17 | **medium** | scope | Scope creep risk | IF the team expands beyond valves/actuators scope before the core pipeline is validated THEN development effort is diluted across unvalidated categories RESULTING IN an incomplete core pipeline and m… | Strict phase scoping; architecture designed for category extension without structural change | open | team |
| 18 | **medium** | technical | Azure tool constraints | IF Azure platform limitations (GPU availability, service quotas) conflict with architecture needs THEN design decisions must be reworked for the constrained environment RESULTING IN reduced model per… | Single App Service deployment chosen to minimize Azure operational complexity | open | team |
| 19 | **medium** | team | Communication gaps between distributed team members | IF distributed team members have infrequent or asynchronous-only communication THEN misalignments on requirements, design, and priorities go undetected RESULTING IN integration conflicts, rework, and… | Weekly sync meetings; shared Slack channel for async updates; meeting summaries auto-generated by SES. | open | team |
| 20 | **medium** | schedule | Capstone timeline constraint | IF the 5-person team cannot prototype within the Spring-Fall 2026 semester THEN operational complexity exceeds team capacity RESULTING IN incomplete deliverables and a failed capstone milestone. | Architecture favors simplicity (single App Service, internal interfaces). SES agents automate repetitive tasks to free team capacity. | open | team |
| 21 | **medium** | process | Knowledge loss from manual processes | IF meeting decisions, action items, and rationale are captured manually THEN information is lost or inconsistently documented across artifacts RESULTING IN duplicated effort, contradictory decisions,… | Agentic SE system auto-captures decisions, action items, and commitments from meetings. SharedMemory wiki maintains persistent project knowledge. | mitigating | team |

## Traceability

16 of 21 risks are linked to the requirements or architecture artifacts they threaten.

| Risk | Title | Threatens (requirements) | Threatens (architecture) |
|------|-------|--------------------------|--------------------------|
| `RISK-ARCH-01` | Confidence threshold miscalibration | QA-1, FR-4 | AD-4, routing |
| `RISK-COACH-01` | Data access delay blocking ML development | REQ-DATA | — |
| `RISK-ARCH-02` | Insufficient training data (<200 labeled examples) | FR-3 | ADR-1, prediction |
| `RISK-ARCH-03` | PIMS staging schema incompatibility (P1-C pending) | FR-6 | AD-3, AD-5, writeback |
| `RISK-ARCH-06` | Catalog team capacity vs review volume | QA-1 | routing, review |
| `RISK-ARCH-07` | Drift detection metrics and baselines undefined | QA-5 | observability |
| `RISK-COACH-04` | Measurement validity for AI effectiveness | REQ-SES | — |
| `RISK-COACH-05` | Model selection uncertainty | — | ADR-1 |
| `RISK-PM-02` | Integration dependency on Jake (PIMS schema) | — | AD-3, AD-5 |
| `RISK-PM-04` | Throughput estimates do not transfer from construction to i… | — | C-4 |
| `RISK-ARCH-04` | Alpha weighting sensitivity in hybrid scoring | QA-1 | ADR-1 |
| `RISK-ARCH-05` | Attribute correlation invalidates per-attribute routing | QA-1, FR-4 | routing |
| `RISK-ARCH-08` | Human review interface design not decided | FR-5 | review |
| `RISK-ARCH-09` | ETIM release pin leaves the catalog progressively stale | FR-10, HLR-6, FR-9 | ADR-020, ADR-013, ADR-014, ADR-017, C-4 |
| `RISK-COACH-02` | Scope creep risk | QA-3 | — |
| `RISK-COACH-03` | Azure tool constraints | — | AD-6 |

## Exit-condition check

All risks have both an owner and a mitigation, so every entry has cleared the exit gate.

---
_Generated from `memory/risk_register.db` by `pipeline/render_risk_register.py` on 2026-07-29. Do not edit by hand: change the source in `pipeline/risk_register.py` and re-run._
