# SDLC Choice: Agent-Augmented Iterative Lifecycle

## Why Not Scrum/RUP/XP

Per the meta-model framework: "Existing SDLCs and methodologies are founded, in part,
on the idea of authoring software being the most labor-intensive part of development."
With AI agents handling artifact generation, the bottleneck shifts from *authoring*
to *validation, measurement, and integration*.

We deliberately avoid naming an existing SDLC. Instead, we compose a bespoke lifecycle
from the meta-model's four elements: **Artifacts, Processes, Resources, Measurements**.

## Our Lifecycle Pattern

```
                    ┌─────────────────────────────────────────────────┐
                    │            ENGINEERING OPERATIONS                │
                    │    (measurement collection + process tuning)     │
                    └─────────┬───────────────────────────┬───────────┘
                              │                           │
    ┌─────────────────────────▼───────────────────────────▼────────────────────┐
    │                                                                          │
    │   Requirements    →   Architecture    →   Construction   →   Quality    │
    │   Engineering         Design              (ML + App)         Assurance  │
    │                                                                          │
    │        │                   │                    │                │        │
    │        ▼                   ▼                    ▼                ▼        │
    │   ┌─────────┐       ┌──────────┐         ┌──────────┐    ┌──────────┐   │
    │   │ Agent   │       │ Agent    │         │ Agent    │    │ Agent    │   │
    │   │ Pipeline│       │ Pipeline │         │ Pipeline │    │ Pipeline │   │
    │   │ (7 steps│       │ (4 steps)│         │ (4 steps)│    │ (cron)   │   │
    │   └────┬────┘       └────┬─────┘         └────┬─────┘    └────┬─────┘   │
    │        │                  │                     │               │         │
    │        └──────────────────┴─────────────────────┴───────────────┘         │
    │                           │                                              │
    │                    ┌──────▼──────┐                                        │
    │                    │ Shared      │                                        │
    │                    │ Memory +    │  ← every agent deposits knowledge      │
    │                    │ Event Bus   │  ← cross-pipeline triggers fire        │
    │                    └─────────────┘                                        │
    │                                                                          │
    │   ◆ Phase Gate (human review of agent outputs before proceeding)         │
    │                                                                          │
    └──────────────────────────────────────────────────────────────────────────┘
                    ▲                                           │
                    │         Iterate (prototype → pilot)       │
                    └───────────────────────────────────────────┘
```

## Key Characteristics

### 1. Agent-First, Human-Verified

Every repeatable activity has an agent implementation. But agents don't ship — humans
verify. The HITL (human-in-the-loop) is explicit at every phase gate:

| Phase              | Agent Role                           | Human Role                        |
|--------------------|--------------------------------------|-----------------------------------|
| Requirements       | Parse transcripts, classify, extract | Review extracted reqs, approve P0 |
| Architecture       | Detect drift, generate ADR drafts    | Approve ADRs, validate tradeoffs  |
| Construction       | Generate boilerplate, review PRs     | Approve merges, design decisions  |
| Quality            | Run regression tests, track metrics  | Interpret metrics, tune thresholds|

### 2. Continuous Measurement (Not Sprint Retrospectives)

Instead of looking back every 2 weeks, the measurement system runs continuously:
- Every LLM call: tokens, latency, cost, prompt version
- Every agent run: success rate, human review rate, correction rate
- Every pipeline: end-to-end duration, step failures, data quality
- Cross-pipeline: event propagation, wiki enrichment, risk evolution

### 3. Two Iterations, Not Sprints

Following the meta-model's guidance:
- **Iteration 1 (Prototype):** Core pipeline (ingestion → prediction → routing → writeback)
  with hybrid model, offline evaluation. Focus: prove accuracy is achievable.
- **Iteration 2 (Pilot):** Production deployment, real data, review workflow, monitoring.
  Focus: prove operational viability.

Phase gate between iterations requires: threshold calibrated, PIMS schema validated,
review workflow tested with Brian/Dewey.

### 4. Practice Areas as Pipelines

Each practice area maps to an agent pipeline with defined data flow:

| Practice Area           | Pipeline              | Activities (Agents)                                         |
|-------------------------|-----------------------|-------------------------------------------------------------|
| Requirements Engineering| `requirements`        | Parse → Classify → Extract → Create Tickets → Drift Check  |
| Architecture            | `architecture`        | Drift Detect → ADR Generate → Diagram Update → Traceability|
| Construction            | `coding`              | Boilerplate → PR Review → Test Generate → Doc Generate      |
| Coach/Mentor Memory     | `coach_session`       | Parse → Embed → Commitments → Concerns → Link → Log        |
| ML Decision Memory      | `ml_decision`         | Log → Evidence → Readiness → Coach Link                     |
| Project Management      | `project_mgmt`        | Tickets → WBS Update → Weekly Digest → Alerts               |

### 5. Cross-Practice Communication via Event Bus

The lifecycle isn't just vertical (within a practice area) — it's horizontal:
- Requirements drift → triggers Architecture review
- Coach concern recurrence → triggers PM alert
- ML evidence accumulation → triggers Coach briefing refresh
- Action items from any meeting → trigger Ticket creation

This is what the meta-model means by "practice areas working together as a system."

## Resource Allocation

| Resource Type | What                                    | Where Used                          |
|---------------|-----------------------------------------|-------------------------------------|
| `auton`       | Agent pipelines, event bus, wiki writes | 28 agent processes                  |
| `assist`      | Claude API for extraction/generation    | LLM-backed agents when API key set  |
| `human`       | Phase gate reviews, threshold tuning    | All P0 items, ADR approval, metrics |
| `tool`        | ChromaDB, SQLite, FastAPI, Datadog      | Infrastructure layer                |

## Justification: Why This Works for eParts

1. **The client problem is a data pipeline** — pipe-and-filter architecture maps directly
   to a linear lifecycle with clear phase boundaries.
2. **Team size (5) precludes heavyweight processes** — no sprint ceremonies, no Scrum Master
   role. Agents handle the repetitive work; humans make decisions.
3. **AI must be measured to be justified** — the meta-model requires evidence of AI
   effectiveness. Continuous measurement gives us data, not anecdotes.
4. **Coach sessions revealed specific risks** — the lifecycle explicitly incorporates risk
   tracking (auto-populated risk register) and commitment tracking (from coach memory).
