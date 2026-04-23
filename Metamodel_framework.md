# AI/LLM Aided Software Engineering (AASE / LASE)

> A variation on the CASE acronym from the days of yore — AASE or LASE depending on how it turns out.
>
> Source: Studio Orientation Day Presentation, Carnegie Mellon University, Software and Societal Systems Department (S3D)

---

## A Change in Mindset

- The time is here to **engineer** systems of production — the Software Engineering System.
- It is no longer labor intensive in the ways it was previously.
- Think of the practice areas working together as a system to be engineered.
- SDLC types are **patterns** of engineering systems. Scrum is a pattern. RUP is a pattern.

---

## The Gist

- **Goal:** Create a framework that can integrate AI into the SDLC without being overly constraining. Enable the creation of a bespoke SDLC.
- **Problem Statement:** GenAI in the Software Development Lifecycle introduces sociotechnical challenges in task delegation, decision authority, artifact quality, and accountability that established software engineering frameworks are inadequate to address.
- **Approach:** Go back to first principles.

---

## Assumptions

- **Authoring software is now inexpensive** (authoring artifacts generally).
  - While generation is cheap, the intellectual losses are high (i.e., outsourcing of expertise — domain, system, requirements, etc.).
- **Existing SDLCs and methodologies are founded, in part, on the idea of authoring software being the most labor-intensive part of development.**
  - Avoid using a preexisting SDLC pattern (i.e., Scrum, RUP) which are fabricated on that idea.
- **Much of the state-of-the-industry is focusing on code.**
  - Include AI in as many places as possible (agents, LLMs, automation…).
- **This is unknown territory with lots of conflicting and anecdotal evidence of success and failures.**
  - Measures are needed to validate any engineering system's performance, improvements, or assertions of successful usage.

---

## The Solution

Use a **meta-model** that stipulates a simplified view of SDLC creation, comprising four core elements:

- **Artifacts**
- **Processes**
- **Resources**
- **Measurements**

### Meta-Model Relationships

```
Resources  ──implements──▶  Processes
Processes  ──generates──▶   Artifacts
Artifacts  ──consumed by──▶ Processes
Measurement ──measures──▶   Resources, Processes, and Artifacts
```

- Resources **implement** Processes
- Processes **consume** and **generate** Artifacts
- Measurement **measures** all three (Resources, Processes, Artifacts)

### Benefits

- A lifecycle process is created to deal explicitly with the project.
- An exploration of the space is enabled.
- Potential patterns of use could emerge.

### Penalties

- Requires thoughtful and skillful use of process modeling.
- Diligence and fidelity are required to execute on plans.

---

## How It Works — In Steps

1. **Contextual Analysis / Project Characterization**
   - Analysis of the project characteristics.
2. **Artifact Selection**
   - Decisions on which primary and intermediary artifacts are necessary.
3. **Process Design**
   - Composing processes and artifacts in production sequences.
4. **Resource Allocation**
   - Assigning resources to processes.
5. **Measurement System Design**
   - Selection of metrics, thresholds, collection methods, and publication.
6. **Engineering Operations**
   - System operates to produce outputs.

---

## Limitations and Expectations

- This 'model' **does not** include significant portions of project management techniques. They are outside of the core technical practice and should be developed secondarily. There is a shift of labor being put into code development into quality and engineering system caring and maintenance.
- This 'model' **does** include the explicit directive of a measurement system. This has a twofold reason — first to monitor performance as stated, but also with the idea that cost estimates (tokens for now) could be quantified. Costs associated with generation are not free.
- It is expected that a 'from scratch' method of process creation is employed, though while simple, can draw on experience and advanced concepts.
- It is expected that process monitoring and improvement activities are performed frequently, though no guidance is presented here.

---

## Design Philosophy — Liberal Application

1. Be opportunistic and ready to experiment.
2. Take risks and keep records, make improvements.
3. Take inventory of techniques and roles.
4. Make value tradeoffs — track time, effort, and costs if you can.
5. Process improvement is reliant on improving AI components/systems.

---

# By Example

## Step 1 — Context (Hypothetical Example)

- Manage work being done by road municipal department to fill potholes.
- All mobile application — shows submitted jobs, job status, and enables taking jobs or rejecting jobs.
- Moderate level of quality required.
- Two releases are needed — beta and production.
- Assume tools are readily available.

**System architecture sketch:**

```
Mobile App  ⇄  Public Internet  ⇄  API  ⇄  App Server  —  Database
```

### Realistically…

- The project's needs to diversify during construction and quality:
  - Need emulators for development.
  - Need hardware — and ways to push software to phones.
  - Deployment — local? Internal release? Production release?
  - Support — Specifically in this example, synthesizing crash/usage reports is 'easy'.
- The example is intentionally general to illustrate the method, not to completely design something for this 'Mobile App'.
- Use the **TOE framework** — Technology, Organization, Environment.

---

## Step 2 — Artifacts (Select Primary Working Artifacts)

- Requirements document
- User stories
- Architecture document
- ADRs (Architecture Decision Records)
- API Specification
- Component Diagrams
- Source code back/front ends
- …

### Artifact Detail

| Artifact | Format | LLM Contribution | Validation Required | State Management |
|---|---|---|---|---|
| **Requirements Document** | YAML + Markdown | Template generation, completeness checking, ambiguity detection | Stakeholder review, feasibility assessment | Draft → Under Review → Approved → Baselined |
| **User Stories** | YAML (structured) | Story template population, acceptance criteria generation | Product owner approval, dev team estimation | Draft → Approved |
| **Architecture Document** | Markdown + Mermaid diagrams | Pattern suggestions, diagram generation, ADR drafting | Architect review, constraint verification, trade-off validation | Draft → Under Review → Approved → Baselined |
| **Architecture Decision Records (ADRs)** | Markdown | ADR template population, alternatives analysis | Tech lead approval, team review | Draft → Approved |

---

## Step 3 — L0 Process Design (Big Picture)

- **Decision:** Two releases = two iterations, one for beta, the other for prod.
- **Release 1** — Fast prototype with enough quality to be useful.
- **Release 2** — Fully tested and revised application.

### High-Level Flow (executed x2)

```
Requirements Engineering
        ↓
Architecture Design
        ↓
Construction
        ↓
Quality Assurance
        ↓
Phase Gate
        ↓
Release ──beta release──▶ (loops back to Requirements Engineering)
        ↓
        prod release
        ↓
Maintenance
```

---

## Step 3 + Step 4 — Process Design + Resource Allocation

- **Process Design** uses **ETVX**.
- Each process has a template:
  - **E**ntry Criteria
  - **T**ask Definition
  - **V**erification
  - e**X**it Criteria
- Resource allocation in this example is simple, so it can be decided here too.

### Legend (used in the L1 diagrams below)

| Symbol | Meaning |
|---|---|
| `LLM File` | LLM-related file artifact |
| `Ext. doc` | External document |
| `doc` | Internal document/artifact |
| `auton` | Autonomous (agent-driven) process |
| `assist` | AI-assisted process |
| `human` | Human-driven process |
| `→` | Information flow |

---

## Step 3/4 — L1 Partial Process Design (Requirements Detail)

- Taking a shortcut and allocating resources here since the system is 'simple'.
- **Requirements Extraction** is AI-assisted; **Req's Doc** is a versioned, managed artifact.
- An **agent watches Req's Doc** for changes then updates user stories.
- **Meeting notes** and **Product Plans** are provided through other means (out of system scope).
- **Question:** Does the RE process need broken down further?

### Flow

```
Meeting Notes  ┐
               ├──▶ Requirements Extraction (assist) ──▶ Req's Doc (doc) ──▶ Requirements Review (human)
Product Plans  ┘                       ▲                       │
                                       │                       ▼
                              Examples/Templates       Agent watches req doc,
                                  (LLM File)           updates user stories (auton)
                                                                │
                                                                ▼
                                                         User Stories (doc)
```

---

## Step 3/4 — L1 Partial Process Design (Architecture Detail)

- Taking a shortcut and allocating resources here since the system is 'simple'.
- **Architecture Practice** is AI-assisted and takes the requirements and product plans as input.
- **Architecture Review/Decision** is a twofold process that both reviews and approves the architectural artifacts for downstream use.
- Items (either documents or individual elements) get a revision number and are source-controlled.
- Review/Decision is currently a human-allocated task but it can easily be converted to assisted.

### Flow

```
Reqt's        ┐
              ├──▶ Architecture Practice (assist) ──┬──▶ Arch Doc (doc)  ──┐
Product Plans ┘                       ▲             ├──▶ ADR (doc)        ─┼──▶ Architecture Review/Decision (human)
                                      │             └──▶ API Spec (doc)   ─┘
                             Examples/Templates
                                 (LLM File)
```

---

## Step 5 — Measurement System Design

- Here it helps to understand how the project management will go, BUT…
- Since we have better tools, we can collect more project data easily.
- **LLM-related measurements** will be very helpful as an indicator of system performance. Start with these.
- Use existing tools — catalog of metrics, **GQM/GQIM**, etc.

### Using GQIM for a Seed Question

- **Goal:** Get the best out of an LLM.
- **Question:** How often is the LLM reprompted?
- **Indicator:** Prompting frequency histography by task type.
- **Metric:** The number of interactions with an LLM per task and task type.

---

## Step 5 — L1 Partial Measurement Design (Requirements Detail)

For the process steps, consider what is a measurement of importance that can be an indicator of process effectiveness. These measurements are examples and should be further considered by the PM practice.

### Measurements Overlaid on the Requirements Flow

| Element | Suggested Measurements |
|---|---|
| Requirements Extraction (assist) | prompt effectiveness, tokens used, example quality |
| Requirements Review (human) | time, # defects, type of defect, reviewer |
| Agent watches req doc / updates user stories (auton) | run history, story deltas, tokens used |

---

## Step 3/4 — L1 Partial Process Design (Architecture Detail) — With Measurements

The measurements should assist in closing the loop on any problems in the architecture development as well as inform LLM use and effectiveness.

| Element | Suggested Measurements |
|---|---|
| Architecture Practice (assist) | prompt effectiveness, tokens used, example quality, doc deltas |
| Architecture Review/Decision (human) | time, # defects, type of defect, reviewer |

---

## Step 6 — Engineering Operations

- **Goal:** Quantitatively manage engineering.
- Begin engineering operations, collect data from processes.
- **Decide:**
  - Time interval for baseline measurements (1 day? 1 week? Different schedules?).
  - Measurements taken as artifacts are changed/updated (i.e., the set of user stories).
- **Note:** Resource allocation should be mapped — meaning who is doing which task/process, leading overall process metrics as well as making tweaks to allocations.
- It'll help to use **GQIM** and consider the things that are already available to measure.

---

## Step 3/4 — L1 Partial Process Design (Crash Reporting)

Extends the Requirements flow with a **Crash Reports → Triage → Defects/Issues → Bug Review → User Stories** loop.

```
Crash Reports ──▶ Agent watches crash reports, triages issues (auton) ──▶ Defects/Issues (doc)
                                       ▲                                          │
                                       │                                          ▼
                                  Req's Doc                                  Bug Review (human)
                                                                                  │
                                                                                  ▼
                                                                            User Stories (doc)
```

Combined with the Requirements Extraction flow, this closes the loop between live production signals and the requirements/user-stories backlog — with the same measurement overlays (prompt effectiveness, tokens used, example quality, run history, story deltas, time, # defects, type defect, reviewer).

---

## Guidance

1. Keep it simple, then expand on AI use.
2. Take some risks, monitor performance, make changes.
3. Iterate fast, refactor (the engineering system) fast.
4. Keep track of the zoo of artifacts — a catalog is advisable but don't make it heavy.
5. Prompting is an important skill/asset. **A/B test prompts.**
6. Be mindful of **agentic patterns** and know when to use them.
7. **Diagramming is extremely helpful** — consider it a system architecture.
8. If there's a problem with the 'framework' bring it up fast — come with data.
9. There's probably more — should we construct a **BoK (Body of Knowledge)**?

---

*End of presentation conversion.*
