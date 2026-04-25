# The eParts Software Engineering System — Explained

> A complete explanation of how our team builds software, why we built it this way,
> and how AI agents work together as a connected system — not isolated tools.

---

## Table of Contents

1. [What Is This?](#1-what-is-this)
2. [The Big Picture](#2-the-big-picture)
3. [How a Meeting Becomes a Jira Ticket (End-to-End Walkthrough)](#3-how-a-meeting-becomes-a-jira-ticket)
4. [The 7 Pipelines and 24 Agents](#4-the-7-pipelines-and-24-agents)
5. [How Agents Talk to Each Other](#5-how-agents-talk-to-each-other)
6. [The Shared Brain (SharedMemory + EventBus)](#6-the-shared-brain)
7. [The Unified Traceability Store](#7-the-unified-traceability-store)
8. [Mapping to the Meta-Model Framework](#8-mapping-to-the-meta-model-framework)
9. [Why AI? Why Not Just Humans?](#9-why-ai-why-not-just-humans)
10. [Key Design Decisions](#10-key-design-decisions)

---

## 1. What Is This?

Our team (Pimsie Supreme) is building a product for eParts — a catalog management system that uses ML to extract product attributes from vendor spec sheets. That's the **Software System** (the product for the client).

But there's a second system: the **Software Engineering System (SES)** — the system we use *to build* the product. Think of it like a factory that produces cars. The car is the product. The factory — with its assembly lines, quality checks, inventory tracking, and worker coordination — is the engineering system.

Our SES is unusual because it's powered by **24 AI agents** organized into **7 automated pipelines**. These agents don't write the product code. They handle the engineering overhead:

- Parsing meeting transcripts into structured requirements
- Creating Jira tickets from action items
- Detecting when architecture decisions drift from what was discussed
- Tracking commitments made to coaches and verifying delivery
- Maintaining a living traceability matrix connecting every artifact to its origin
- Generating pre-meeting briefings so the team walks in prepared

The key insight: **authoring software is now cheap, but engineering coordination is where teams fail.** Our SES automates the repeatable 80% of coordination while humans own the judgment-heavy 20%.

---

## 2. The Big Picture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        TRIGGERS (Inputs)                            │
│  Meeting VTT │ Jira Webhook │ GitHub PR │ Cron Schedule │ Manual   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    CENTRAL ORCHESTRATOR                              │
│              FastAPI server · 29 REST endpoints                      │
│     Routes triggers → pipelines · Task queue · Agent registry       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ selects pipeline
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     7 AGENT PIPELINES                                │
│                                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │Requirem- │ │Architect-│ │  Coding  │ │ Project  │ │Knowledge │ │
│  │  ents    │ │  ure     │ │          │ │   Mgmt   │ │          │ │
│  │ 7 agents │ │ 4 agents │ │ 4 agents │ │ 4 agents │ │ 4 agents │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│  ┌────────────────────┐ ┌────────────────────┐                      │
│  │  Coach Session     │ │  ML Decision       │                      │
│  │  Memory · 6 agents │ │  Memory · 4 agents │                      │
│  └────────────────────┘ └────────────────────┘                      │
└──────────┬──────────────────────────┬───────────────────────────────┘
           │                          │
           ▼                          ▼
┌─────────────────────┐  ┌─────────────────────────────────────────────┐
│  SHARED INFRA       │  │  MCP SERVERS (External API Wrappers)        │
│                     │  │                                              │
│  SharedMemory (wiki)│  │  Jira     · GitHub   · ChromaDB (vectors)  │
│  EventBus (pub/sub) │  │  Bitbucket · Confluence · Slack             │
│  TraceabilityStore  │  │  Google Drive · Anthropic API               │
│  PromptRegistry     │  │                                              │
│  RiskRegister       │  │  [3 LIVE · 5 READY]                        │
│  MetricsCollector   │  │                                              │
└─────────┬───────────┘  └──────────────────────┬──────────────────────┘
          │                                      │
          ▼                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     STORAGE (7 SQLite DBs + ChromaDB)                │
│  shared_memory.db │ events.db │ traceability.db │ coach_sessions.db │
│  ml_decisions.db  │ risk_register.db │ prompt_registry.db │ metrics │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          OUTPUTS                                     │
│  REQ docs │ ADRs │ Jira tickets │ Meeting minutes │ Traceability    │
│  Risk register │ Weekly digest │ Dashboards │ Pre-meeting briefings │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. How a Meeting Becomes a Jira Ticket

Let's trace what happens when someone uploads a client meeting recording. This is the **end-to-end flow** for the Requirements Engineering practice area.

### Step-by-Step

```
 YOU                    SYSTEM                           EXTERNAL
  │                       │                                 │
  │  Upload meeting.vtt   │                                 │
  │──────────────────────▶│                                 │
  │                       │                                 │
  │               ┌───────┴───────┐                         │
  │               │ ORCHESTRATOR  │                         │
  │               │ Routes to     │                         │
  │               │ "requirements"│                         │
  │               │ pipeline      │                         │
  │               └───────┬───────┘                         │
  │                       │                                 │
  │              Step 1: transcript_parser                   │
  │               ┌───────┴───────┐                         │
  │               │ Parse VTT     │                         │
  │               │ Extract:      │                         │
  │               │ • 3 decisions │                         │
  │               │ • 7 actions   │                         │
  │               │ • 2 concerns  │                         │
  │               └───────┬───────┘                         │
  │                       │ deposits to SharedMemory (wiki) │
  │                       │ emits: action_items_extracted    │
  │                       │ emits: decision_logged           │
  │                       │                                 │
  │              Step 2: req_extractor                       │
  │               ┌───────┴───────┐                         │
  │               │ Format as     │──── commit ────────────▶│ GitHub
  │               │ REQ-XXX.md    │                         │ (requirements/)
  │               │ Deposit to    │                         │
  │               │ wiki          │                         │
  │               └───────┬───────┘                         │
  │                       │                                 │
  │              Step 3: priority_classifier                 │
  │               ┌───────┴───────┐                         │
  │               │ Classify:     │                         │
  │               │ • 2 items P0  │                         │
  │  ◄────────────│ • 3 items P1  │ (P0 = human reviews)   │
  │  "Review P0"  │ • 2 items P2  │                         │
  │               └───────┬───────┘                         │
  │                       │                                 │
  │              Step 4: stale_detector                      │
  │               ┌───────┴───────┐                         │
  │               │ Check wiki +  │──── search ────────────▶│ Jira
  │               │ Jira for old  │◀─── results ───────────│
  │               │ requirements  │                         │
  │               └───────┬───────┘                         │
  │                       │                                 │
  │              Step 5: drift_detector                      │
  │               ┌───────┴───────┐                         │
  │               │ Compare       │──── RAG query ─────────▶│ ChromaDB
  │               │ decisions vs  │◀─── relevant chunks ───│
  │               │ architecture  │                         │
  │               │ report        │                         │
  │               └───────┬───────┘                         │
  │                       │ if drift found: emits drift_detected
  │                       │                                 │
  │              Step 6: decision_logger                     │
  │               ┌───────┴───────┐                         │
  │               │ Log decisions │──── commit ────────────▶│ GitHub
  │               │ to wiki +     │                         │ (decisions.log.md)
  │               │ GitHub        │                         │
  │               └───────┬───────┘                         │
  │                       │                                 │
  │              Step 7: ticket_creator                      │
  │               ┌───────┴───────┐                         │
  │               │ Create Jira   │──── create ticket ─────▶│ Jira
  │               │ tickets with  │                         │ (EPARTS-XX)
  │               │ labels +      │                         │
  │               │ priority      │                         │
  │               └───────┬───────┘                         │
  │                       │                                 │
  │                  PIPELINE COMPLETE                       │
  │                       │                                 │
  │         BUT the emitted events trigger MORE:            │
  │                       │                                 │
  │         action_items_extracted ──▶ project_mgmt pipeline│
  │         decision_logged ──────▶ architecture pipeline   │
  │         drift_detected ───────▶ architecture pipeline   │
  │                       │                                 │
```

**What just happened in human terms:**

1. You uploaded a 45-minute meeting recording
2. The system parsed it into 3 decisions, 7 action items, and 2 concerns
3. Each requirement was formatted as a document and committed to GitHub
4. Items were classified by priority — P0 items were flagged for your review
5. Old requirements with no Jira ticket were identified
6. The system checked if any meeting decisions contradicted the architecture
7. Jira tickets were automatically created with proper labels
8. Three other pipelines were triggered to handle the downstream effects

**Time for a human to do all of this manually: ~3 hours.**
**Time for the system: ~30 seconds.**

---

## 4. The 7 Pipelines and 24 Agents

Each pipeline is a sequence of agents that execute in order. Think of it like an assembly line — each station does one specific job, then passes the work to the next.

```
Pipeline                 Trigger              Agents (in order)
─────────────────────────────────────────────────────────────────────

REQUIREMENTS             .vtt transcript      transcript_parser
(7 agents)                                    → req_extractor
                                              → priority_classifier
                                              → stale_detector
                                              → drift_detector
                                              → decision_logger
                                              → ticket_creator

COACH SESSION            coach .vtt           session_memory
(6 agents)                                    → commitment_tracker
                                              → concern_tracker
                                              → coach_linker
                                              → briefing_generator
                                              → context_packager

ARCHITECTURE             transcript, PR       drift_detector
(4 agents)                                    → adr_generator
                                              → diagram_updater
                                              → traceability_builder

CODING                   PR event             pr_reviewer
(4 agents)                                    → test_generator
                                              → boilerplate_generator
                                              → doc_generator

ML DECISION              POC result           decision_log
(4 agents)                                    → evidence_accumulator
                                              → readiness_detector
                                              → coach_linker

PROJECT MGMT             Cron (Fri 6pm)       alert_agent
(4 agents)                                    → ticket_creator
                                              → wbs_updater
                                              → weekly_digest

KNOWLEDGE                Cron (pre-meeting)   context_packager
(4 agents)                                    → decision_logger
                                              → minutes_publisher
                                              → prompt_regression
```

---

## 5. How Agents Talk to Each Other

Agents don't talk directly. They communicate through two mechanisms:

### Mechanism 1: SharedMemory (The Project Wiki)

Think of SharedMemory as a shared whiteboard that every agent can read and write to.

```
┌────────────────────────────────────────────────────────┐
│                 SharedMemory (Wiki)                      │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  Namespace:   │  │  Namespace:   │  │  Namespace:   │ │
│  │  "meetings"   │  │  "decisions"  │  │  "concerns"   │ │
│  │              │  │              │  │              │ │
│  │ 2026-01-22:  │  │ 2026-01-22:0 │  │ vendor_data: │ │
│  │  {summary,   │  │  {text,       │  │  {theme,      │ │
│  │   actions,   │  │   speaker,    │  │   sessions,   │ │
│  │   concerns}  │  │   context}    │  │   severity}   │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │
│         │                 │                 │          │
│    WRITTEN BY:       WRITTEN BY:       WRITTEN BY:     │
│  transcript_parser  decision_logger  concern_tracker   │
│                                                          │
│    READ BY:          READ BY:          READ BY:          │
│  stale_detector     adr_generator    alert_agent        │
│  context_packager   traceability_    briefing_generator │
│  weekly_digest      builder                             │
└────────────────────────────────────────────────────────┘
```

**Example flow:**
1. `transcript_parser` parses a meeting and writes the summary to `wiki["meetings"]["2026-04-02"]`
2. Later, `context_packager` reads from `wiki["meetings"]` to build a pre-meeting briefing
3. `stale_detector` reads from `wiki["requirements"]` and cross-references with Jira

Every write has an audit trail: who wrote it, when, from which pipeline.

### Mechanism 2: EventBus (Cross-Pipeline Triggers)

The EventBus is like a notification system. When something important happens in one pipeline, it fires an event that triggers another pipeline.

```
                    REQUIREMENTS PIPELINE
                    ┌─────────────────┐
                    │ transcript_     │
                    │ parser runs     │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
    ┌─────────────┐ ┌──────────────┐ ┌──────────────┐
    │ EVENT:      │ │ EVENT:       │ │ EVENT:       │
    │ action_     │ │ decision_    │ │ drift_       │
    │ items_      │ │ logged       │ │ detected     │
    │ extracted   │ │              │ │              │
    └──────┬──────┘ └──────┬───────┘ └──────┬───────┘
           │               │               │
           ▼               ▼               ▼
    ┌──────────────┐┌──────────────┐┌──────────────┐
    │ PROJECT MGMT ││ ARCHITECTURE ││ ARCHITECTURE │
    │ pipeline     ││ pipeline     ││ pipeline     │
    │ picks up     ││ generates    ││ updates      │
    │ action items ││ ADRs         ││ diagrams     │
    └──────────────┘└──────────────┘└──────────────┘
```

### The 6 Cross-Pipeline Events

```
Event                      Source Pipeline    Target Pipeline     What Triggers
─────────────────────────────────────────────────────────────────────────────────
action_items_extracted     requirements    →  project_mgmt       Ticket creation
decision_logged            requirements    →  architecture       ADR drafting
drift_detected             requirements    →  architecture       Diagram update
new_session_embedded       coach_session   →  knowledge          Briefing refresh
recurring_concern          coach_session   →  requirements       REQ re-check
human_review_needed        architecture    →  project_mgmt       Alert creation
```

### The Complete Communication Picture

```
                      ┌─────────────┐
                      │   MEETINGS  │
                      │ (5 client + │
                      │  4 coach)   │
                      └──────┬──────┘
                             │ .vtt upload
                ┌────────────┴────────────┐
                ▼                         ▼
        ┌───────────────┐        ┌───────────────┐
        │ REQUIREMENTS  │───────▶│ COACH SESSION │
        │   PIPELINE    │ events │   PIPELINE    │
        └───────┬───────┘        └───────┬───────┘
                │                        │
          ┌─────┼─────┐            ┌─────┼─────┐
          ▼     ▼     ▼            ▼           ▼
     ┌────────┐│┌────────┐   ┌────────┐  ┌────────┐
     │PROJECT ││ARCHIT-  │   │KNOW-   │  │ML      │
     │ MGMT   │││ECTURE  │   │LEDGE   │  │DECISION│
     └───┬────┘│└───┬────┘   └───┬────┘  └───┬────┘
         │     │    │            │            │
         │     │    │            │            │
         ▼     ▼    ▼            ▼            ▼
     ┌──────────────────────────────────────────┐
     │           SHARED MEMORY (Wiki)            │
     │               + EventBus                  │
     │           + TraceabilityStore              │
     └──────────────────────────────────────────┘
         │              │              │
         ▼              ▼              ▼
     ┌────────┐    ┌────────┐    ┌────────┐
     │  Jira  │    │ GitHub │    │ChromaDB│
     │(tickets│    │ (code, │    │(vector │
     │ board) │    │  docs) │    │ search)│
     └────────┘    └────────┘    └────────┘
```

**The key insight:** No pipeline is an island. The Requirements pipeline's output triggers the Architecture pipeline. The Coach Session pipeline's recurring concerns feed back into Requirements. Project Management reads from everyone's wiki entries. This is what makes it a **framework** instead of a collection of scripts.

---

## 6. The Shared Brain

### SharedMemory (The Wiki)

Every agent has access to a shared knowledge base. When an agent learns something, it deposits it into the wiki so other agents can use it later.

| Namespace | What's Stored | Written By | Read By |
|-----------|-------------|-----------|---------|
| `meetings` | Parsed meeting summaries | transcript_parser | context_packager, weekly_digest |
| `decisions` | All decisions from all sources | decision_logger | adr_generator, traceability_builder |
| `concerns` | Recurring themes from coaches | concern_tracker | alert_agent, briefing_generator |
| `requirements` | Extracted requirements | req_extractor | stale_detector, traceability_builder |
| `commitments` | Coach session commitments | session_memory | commitment_tracker, briefing_generator |
| `project_mgmt` | WBS state, sprint data | wbs_updater | weekly_digest, alert_agent |

This is inspired by **Andrej Karpathy's "wiki" pattern** — agents maintain a persistent, evolving knowledge base that accumulates intelligence over time, rather than each agent starting from scratch.

### EventBus (The Nervous System)

Events are typed, persistent (stored in SQLite), and carry data payloads. When pipeline A emits an event, the EventBus looks up which pipelines are subscribed and triggers them.

```
EVENT LIFECYCLE:

  1. Agent finishes work
  2. Agent calls: self.emit("drift_detected", data={...})
  3. EventBus stores event in SQLite (with timestamp, source, data)
  4. EventBus looks up subscriptions: drift_detected → architecture pipeline
  5. Architecture pipeline is queued for execution
  6. Architecture agents can read the event data to understand context
```

---

## 7. The Unified Traceability Store

This is perhaps the most important piece. It answers the question: **"Where did this come from, and what does it connect to?"**

### What It Tracks

```
184 ARTIFACTS across 10 types, connected by 760 LINKS of 7 types

ARTIFACT TYPES:                    LINK TYPES:
─────────────                      ──────────
meeting (5)                        RAISED_IN (122)    — originated from
coach_session (1)                  BECAME (60)        — evolved into
concern (12)                       DECIDED_BY (32)    — shaped by
decision (10)                      ADDRESSES (13)     — responds to
action_item (41)                   TRIGGERED (9)      — spawned
commitment (31)                    IMPLEMENTS (204)   — tracks/fulfills
requirement (12)                   MITIGATES (320)    — reduces risk
architecture (6)
risk (16)
jira_ticket (50)
```

### An Example Chain

Starting from a client concern and tracing forward through the entire lifecycle:

```
[CONCERN] "Is there sensitive product data from vendors?"
  │       Raised by Hrishik in Meeting 2026-01-22
  │
  ├── BECAME ──▶ [REQUIREMENT] REQ-001: Extract product attributes from vendor spec sheets
  │               │
  │               ├── DECIDED_BY ──▶ [ARCHITECTURE] ARCH-002: Map to industry standards
  │               │                   │
  │               │                   └── ADDRESSES ──▶ [CONCERN] "Can we use LLM instead of OCR?"
  │               │                                      │
  │               │                                      └── BECAME ──▶ [DECISION] "Primary goal: LLM extraction"
  │               │                                                      │
  │               │                                                      └── TRIGGERED ──▶ [ARCHITECTURE] ARCH-004: Staging tables
  │               │
  │               ├── MITIGATES ──▶ [RISK] Confidence threshold miscalibration
  │               │
  │               └── IMPLEMENTS ──▶ [JIRA] EPARTS-74: Finalize requirements by April 15
  │                                  [JIRA] EPARTS-73: Schedule deep-dive with catalog team
  │                                  [JIRA] EPARTS-72: Explore Azure AI services
  │                                  ... (7 tickets total)
  │
  ├── BECAME ──▶ [REQUIREMENT] REQ-003: ML confidence scoring on every predicted attribute
  │               │
  │               ├── DECIDED_BY ──▶ [ARCHITECTURE] ARCH-003: ML confidence scoring
  │               └── DECIDED_BY ──▶ [ARCHITECTURE] ARCH-005: Human-in-the-loop
  │                                   │
  │                                   └── IMPLEMENTS ──▶ [COMMITMENT] "We'll be removing the human part eventually"
  │                                                       │
  │                                                       └── RAISED_IN ──▶ [COACH SESSION] 2026-02-20
  │
  └── BECAME ──▶ [REQUIREMENT] REQ-008: Support multiple vendor document formats
                  ... (continues)
```

**Why this matters:** If someone asks "why does EPARTS-74 exist?", you can trace it back through:
- Jira ticket → requirement → architecture decision → client concern → meeting → speaker → timestamp

Nothing exists without a paper trail. Every artifact has provenance.

**Cost:** Zero LLM calls. All 760 links are created using SQLite and domain-aware keyword matching.

---

## 8. Mapping to the Meta-Model Framework

The CMU meta-model framework says every engineering system has four elements:

```
┌─────────────────────────────────────────────────────────────┐
│                     META-MODEL FRAMEWORK                     │
│                                                              │
│    Resources ──implements──▶ Processes                       │
│    Processes ──generates──▶  Artifacts                       │
│    Artifacts ──consumed by──▶ Processes                      │
│    Measurement ──measures──▶ Resources, Processes, Artifacts │
└─────────────────────────────────────────────────────────────┘
```

Here's how our SES maps to each element:

### ARTIFACTS (what gets produced)

| Artifact | Format | Who Generates It | Validation |
|----------|--------|-----------------|------------|
| Meeting minutes | JSON + Markdown | `transcript_parser` agent | Human reviews summary |
| Requirements (REQ-001..012) | Markdown | `req_extractor` agent | P0 items require human approval |
| Architecture Decision Records | Markdown | `adr_generator` agent | All changes require PR approval |
| Jira tickets | Jira Cloud | `ticket_creator` agent | P0 tickets need 1 approval |
| Traceability matrix | SQLite + Markdown | `traceability_builder` agent | Gaps flagged automatically |
| Risk register | SQLite | `seed_risk_register` + agents | Human reviews mitigations |
| Decision log | Markdown | `decision_logger` agent | Committed to GitHub |
| Weekly digest | Markdown | `weekly_digest` agent | Published to team |
| Pre-meeting briefings | Text | `briefing_generator` agent | Sent before meetings |
| Coach commitment log | SQLite | `session_memory` agent | Cross-checked vs evidence |
| ML decision log | SQLite | `decision_log` agent | Evidence-gated closure |
| WBS (Work Breakdown Structure) | Markdown | `wbs_updater` agent | Synced from Jira state |
| Versioned prompts | SQLite | `PromptRegistry` | Peer review before activation |

### PROCESSES (how work gets done)

Each process follows the **ETVX** pattern (Entry, Task, Verification, Exit):

```
┌─────────────────────────────────────────────────────────────────┐
│  PROCESS: Requirements Engineering (end-to-end)                  │
│                                                                  │
│  ENTRY:  .vtt transcript uploaded to system                      │
│                                                                  │
│  TASK:   7-step pipeline executes:                               │
│          parse → extract → classify → detect_stale →             │
│          detect_drift → log_decisions → create_tickets            │
│                                                                  │
│  VERIFY: • P0 items flagged for human review                     │
│          • Drift detector compares vs architecture (RAG)         │
│          • Stale detector checks for orphan requirements         │
│          • All outputs deposited to SharedMemory with audit trail │
│                                                                  │
│  EXIT:   Requirements committed to GitHub                        │
│          Jira tickets created with labels                        │
│          Events emitted for downstream pipelines                 │
│          Traceability links established                          │
└─────────────────────────────────────────────────────────────────┘
```

**All 7 pipelines are documented processes** with clear entry criteria, task sequences, verification steps, and exit conditions. See `docs/etvx_manifest.yaml` for the full ETVX specification.

### RESOURCES (who/what does the work)

```
RESOURCE TYPE        EXAMPLES                          ROLE
─────────────────────────────────────────────────────────────────
AI Agents (24)       transcript_parser,                Automated execution
                     drift_detector,                   of repeatable tasks
                     ticket_creator, etc.

MCP Servers (8)      Jira, GitHub, ChromaDB,           Interface to external
                     Confluence, Slack, etc.            services

Shared Infra (6)     SharedMemory, EventBus,           Cross-agent
                     TraceabilityStore,                 coordination and
                     PromptRegistry, etc.               knowledge

Human Team (5)       Ashritha, Hrishik, Jai,           Judgment, review,
                     Arjun, Liu                        approval gates

External Tools       Python 3.12, FastAPI,             Runtime platform
                     SQLite, ChromaDB, D3.js
```

**The resource allocation principle:** AI handles repeatable pattern-matching tasks (parsing, classifying, detecting drift, creating tickets). Humans handle judgment calls (approving P0 requirements, reviewing architecture changes, closing ML decisions).

### MEASUREMENTS (how we know it's working)

We use **GQIM** (Goal, Question, Indicator, Metric):

```
GOAL: Ensure AI-generated artifacts are reliable
  QUESTION: How often do humans override AI decisions?
    INDICATOR: Override rate per agent per week
    METRIC: # corrections / # total outputs

GOAL: Ensure nothing falls through the cracks
  QUESTION: What percentage of concerns have traceability?
    INDICATOR: Traceability coverage percentage
    METRIC: Artifacts with ≥1 link / total artifacts (currently 100%)

GOAL: Optimize AI usage cost
  QUESTION: How many tokens are we spending per artifact?
    INDICATOR: Tokens per task type histogram
    METRIC: Total tokens / # artifacts produced

GOAL: Keep the team prepared for meetings
  QUESTION: Are briefings generated before every meeting?
    INDICATOR: Briefing generation success rate
    METRIC: # briefings sent on time / # meetings scheduled
```

**What we actually measure** (collected by MetricsCollector):

| Metric | Collection Method | Storage |
|--------|------------------|---------|
| Agent run count, duration, success rate | Automatic per run | `metrics.db` |
| LLM token usage per call | Automatic per call | `metrics.db` |
| Prompt version, author, review status | PromptRegistry | `prompt_registry.db` |
| Human correction count | POST /metrics/correction | `metrics.db` |
| Traceability coverage | TraceabilityStore.get_coverage() | `traceability.db` |
| Risk mitigation status | RiskRegister.get_all() | `risk_register.db` |
| Event throughput | EventBus.stats() | `events.db` |
| Commitment delivery rate | commitment_tracker | `coach_sessions.db` |

### How the Meta-Model Elements Connect in Our System

```
                    ┌─────────────────────────────────┐
                    │        MEASUREMENTS              │
                    │   MetricsCollector · GQIM plan   │
                    │   Token usage · Run counts        │
                    │   Override rates · Coverage %      │
                    └────┬──────────┬──────────┬───────┘
                         │ measures │ measures │ measures
                         ▼          ▼          ▼
┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│   RESOURCES    │  │   PROCESSES    │  │   ARTIFACTS    │
│                │  │                │  │                │
│ 24 AI Agents   │──│ 7 Pipelines   │──│ REQ docs       │
│ 8 MCP Servers  │  │ ETVX-defined  │  │ ADRs           │
│ 6 Shared Infra │  │ Event-driven  │  │ Jira tickets   │
│ 5 Humans       │  │ HITL gates    │  │ Traceability   │
│ (review/judge) │  │ Cross-pipeline│  │ Risk register  │
│                │  │ triggers      │  │ Meeting minutes│
│  implements ──▶│  │  generates ──▶│  │ Decision log   │
│                │  │◀── consumes   │  │ Prompts        │
└────────────────┘  └────────────────┘  └────────────────┘
```

---

## 9. Why AI? Why Not Just Humans?

Every component has a justification. If a human can do it better or cheaper, we don't use AI.

| Task | Why AI | Why Not Human |
|------|--------|--------------|
| Parse 45-min meeting transcript into structured data | Consistent extraction, never forgets an action item | Human takes 2-3 hours, misses items, inconsistent format |
| Detect architecture drift | Compares against canonical doc every time, no fatigue | Human forgets what was said 3 meetings ago |
| Create Jira tickets from action items | Immediate, properly labeled, no procrastination | Team members forget or delay; inconsistent labeling |
| Track coach commitments vs delivery | Cross-references across 4+ sessions automatically | Humans forget what they promised 6 weeks ago |
| Maintain traceability matrix | 760 links updated automatically on every change | Manual traceability matrices are always out of date |
| Pre-meeting briefing | Aggregates from 7 data sources in seconds | Human would need to check wiki, Jira, events, coach notes... |

| Task | Why Human | Why Not AI |
|------|-----------|-----------|
| Approve P0 requirements | Judgment about business priority | AI can't assess client relationship implications |
| Review architecture PRs | Technical judgment about system fitness | AI can flag drift but can't evaluate trade-offs holistically |
| Close ML decisions | Requires empirical judgment on data sufficiency | Threshold for "enough evidence" is context-dependent |
| Final presentation | Communication, storytelling, defense | AI can prepare content but can't present or respond to critique |

---

## 10. Key Design Decisions

### 1. Bespoke SDLC (Not Scrum, Not RUP)

**Why:** The meta-model framework says "avoid using a preexisting SDLC pattern which are fabricated on the idea that authoring software is the most labor-intensive part." Our SDLC is an **Agent-Augmented Iterative Lifecycle** where practice areas map to agent pipelines. See `docs/sdlc_choice.md`.

### 2. Offline-First Architecture

**Why:** We can't guarantee API access during demos or development. Every agent has a pattern-matching fallback when no LLM API key is available. ChromaDB uses local ONNX embeddings (no OpenAI key needed). The system is fully functional without any external AI service.

### 3. SQLite Everywhere (No Postgres/Redis)

**Why:** Simplicity. 7 small SQLite databases, each serving one purpose. No infrastructure to maintain. Portable — the entire system state is a folder of `.db` files. Cost: zero.

### 4. Zero LLM Calls for Traceability

**Why:** 760 links created via domain-aware keyword matching. If we used an LLM to classify every link, it would cost tokens on every update. The structured nature of the data (meetings have dates, tickets have labels, requirements have IDs) means pattern matching is sufficient and deterministic.

### 5. Prompt Governance

**Why:** The rubric says "move from ad-hoc use of AI to principled use." Our PromptRegistry version-controls every prompt, requires peer review before activation, and supports A/B testing. 10 team conventions ensure consistent AI use across all team members.

### 6. Event-Driven Cross-Pipeline Communication

**Why:** Pipelines need to trigger each other without tight coupling. The EventBus means adding a new pipeline only requires subscribing to events — no existing code needs to change. This is how the system scales to the coding phase without breaking.

---

*Auto-generated from the eParts SES codebase. Last updated: April 2026.*
*CMU MSE Studio 2026 · Pimsie Supreme · Python 3.12 · FastAPI · SQLite · ChromaDB*
