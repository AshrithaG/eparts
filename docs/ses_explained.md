# The eParts Software Engineering System — Explained

> A complete explanation of how our team builds software, why we built it this way,
> and how AI agents work together as a connected system — not isolated tools.

---

## Table of Contents

1. [What Is This?](#1-what-is-this)
2. [The Big Picture](#2-the-big-picture)
3. [How a Meeting Becomes a Jira Ticket (End-to-End Walkthrough)](#3-how-a-meeting-becomes-a-jira-ticket)
4. [The 7 Pipelines and 28 Agents](#4-the-7-pipelines-and-28-agents)
5. [How Agents Talk to Each Other](#5-how-agents-talk-to-each-other)
6. [The Shared Infrastructure](#6-the-shared-infrastructure)
7. [The Unified Traceability Store](#7-the-unified-traceability-store)
8. [Mapping to the Meta-Model Framework](#8-mapping-to-the-meta-model-framework)
9. [Measuring AI Effectiveness — Counterfactuals](#9-measuring-ai-effectiveness)
10. [Our SDLC: Agent-Augmented Iterative Lifecycle](#10-our-sdlc)
11. [Key Design Decisions](#11-key-design-decisions)

---

## 1. What Is This?

Our team (Pimsie Supreme) is building a product for eParts — a catalog management system that uses ML to extract product attributes from vendor spec sheets. That's the **Software System** (the product for the client).

But there's a second system: the **Software Engineering System (SES)** — the system we use *to build* the product. Think of it like a factory that produces cars. The car is the product. The factory — with its assembly lines, quality checks, inventory tracking, and worker coordination — is the engineering system.

Our SES is powered by **28 AI agents** organized into **7 automated pipelines**. These agents don't write the product code. They handle the engineering overhead:

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
│                          TRIGGERS                                    │
│                                                                      │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐  │
│  │ .vtt file   │ │ GitHub PR   │ │ Cron        │ │ Manual API  │  │
│  │ upload      │ │ (future)    │ │ schedule    │ │ call        │  │
│  │ [ACTIVE]    │ │ [READY]     │ │ [ACTIVE]    │ │ [ACTIVE]    │  │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘  │
└─────────┼───────────────┼───────────────┼───────────────┼──────────┘
          └───────────────┴───────┬───────┴───────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    CENTRAL ORCHESTRATOR                              │
│              FastAPI server · 29 REST endpoints                      │
│     Routes triggers → pipelines · Task queue · Agent registry       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ selects pipeline based on trigger type
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     7 AGENT PIPELINES                                │
│                                                                      │
│  Requirements (7)  │ Architecture (4)  │ Coding (4) │ PM (3)       │
│  Coach Session (6) │ ML Decision (3)   │ Knowledge (2)              │
│                                                                      │
│  Total: 28 unique agents, 29 pipeline steps                         │
│  (some agents appear in multiple pipelines)                          │
└──────────┬──────────────────────────┬───────────────────────────────┘
           │                          │
           ▼                          ▼
┌─────────────────────┐  ┌─────────────────────────────────────────────┐
│  SHARED INFRA       │  │  MCP SERVERS (External API Wrappers)        │
│  (all SQLite-based) │  │                                              │
│                     │  │  Jira      [LIVE]    GitHub    [LIVE]       │
│  SharedMemory       │  │  ChromaDB  [LIVE]    Bitbucket [READY]      │
│  EventBus           │  │  Confluence [READY]  Slack     [READY]      │
│  TraceabilityStore  │  │  Google Drive [READY] Anthropic [READY]     │
│  PromptRegistry     │  │                                              │
│  RiskRegister       │  │  LIVE = wired + tested                      │
│  MetricsCollector   │  │  READY = code complete, needs credentials   │
└─────────┬───────────┘  └──────────────────────┬──────────────────────┘
          │                                      │
          ▼                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          STORAGE                                     │
│                                                                      │
│  All stored locally in the  memory/  folder:                         │
│                                                                      │
│  memory/shared_memory.db   — wiki entries (meetings, decisions...)   │
│  memory/events.db          — cross-pipeline event history            │
│  memory/traceability.db    — artifact links (concerns → Jira)       │
│  memory/coach_sessions.db  — coach session structured data           │
│  memory/ml_decisions.db    — ML experiment logs                      │
│  memory/risk_register.db   — identified risks + mitigations          │
│  memory/prompt_registry.db — prompt versions + review status         │
│  memory/metrics.db         — agent run performance data              │
│  memory/chroma/            — ChromaDB vector store (for RAG)         │
│                                                                      │
│  Why 8 DBs instead of 1? Each can be independently inspected,       │
│  backed up, or reset. Zero infrastructure — no Postgres needed.     │
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
  │               │ Detects       │                         │
  │               │ trigger_type= │                         │
  │               │ "transcript"  │                         │
  │               │ Routes to     │                         │
  │               │ requirements  │                         │
  │               │ pipeline      │                         │
  │               └───────┬───────┘                         │
  │                       │                                 │
  │    Step 1: transcript_parser                            │
  │               ┌───────┴───────┐                         │
  │               │ Parse VTT:    │                         │
  │               │ • Clean text  │                         │
  │               │ • Identify    │                         │
  │               │   speakers    │                         │
  │               │ • Extract:    │                         │
  │               │   3 decisions │                         │
  │               │   7 actions   │                         │
  │               │   2 concerns  │                         │
  │               └───────┬───────┘                         │
  │                       │                                 │
  │                       │ ① Deposits to SharedMemory:     │
  │                       │    wiki["meetings"]["2026-01-22"]│
  │                       │    = {summary, actions, concerns}│
  │                       │                                 │
  │                       │ ② Emits events:                 │
  │                       │    action_items_extracted        │
  │                       │    decision_logged               │
  │                       │                                 │
  │    Step 2: priority_classifier                          │
  │               ┌───────┴───────┐                         │
  │               │ For each item:│                         │
  │               │ Does it       │                         │
  │               │ contain       │                         │
  │               │ "deadline",   │                         │
  │               │ "demo",       │                         │
  │               │ "block"? →P0  │                         │
  │               │ "need",       │                         │
  │               │ "sprint"? →P1 │                         │
  │               │ Otherwise →P2 │                         │
  │  ◄────────────│               │                         │
  │  "Review 2 P0│ With Claude   │                         │
  │   items"     │ API: context-  │                         │
  │               │ aware classify│                         │
  │               └───────┬───────┘                         │
  │                       │                                 │
  │    Step 3: req_extractor                                │
  │               ┌───────┴───────┐                         │
  │               │ Format as     │                         │
  │               │ REQ-XXX.md:   │                         │
  │               │ • Title       │──── commit ────────────▶│ GitHub
  │               │ • Rationale   │                         │ requirements/
  │               │ • Priority    │                         │ parsed/
  │               │ • Acceptance  │                         │ REQ-013.md
  │               │   criteria    │                         │
  │               └───────┬───────┘                         │
  │                       │                                 │
  │                       │ Deposits to wiki:               │
  │                       │ wiki["requirements"]["REQ-013"] │
  │                       │                                 │
  │    Step 4: ticket_creator                               │
  │               ┌───────┴───────┐                         │
  │               │ For each P1/  │                         │
  │               │ P2 item:      │──── create ticket ─────▶│ Jira
  │               │ • summary     │                         │ EPARTS-XX
  │               │ • description │                         │
  │               │ • labels:     │                         │
  │               │   [P1,        │                         │
  │               │    auto-      │                         │
  │               │    created]   │                         │
  │               │ • priority    │                         │
  │               └───────┬───────┘                         │
  │                       │                                 │
  │    Step 5: minutes_publisher                            │
  │               ┌───────┴───────┐                         │
  │               │ Format as     │── (publish) ───────────▶│ Confluence
  │               │ Confluence    │                         │ (when
  │               │ page          │                         │  configured)
  │               └───────┬───────┘                         │
  │                       │                                 │
  │    Step 6: decision_logger                              │
  │               ┌───────┴───────┐                         │
  │               │ For each      │                         │
  │               │ decision:     │                         │
  │               │ • Log to wiki │                         │
  │               │   ["decisions"│                         │
  │               │    /"date:0"] │──── commit ────────────▶│ GitHub
  │               │ • Append to   │                         │ minutes/
  │               │   decisions.  │                         │ decisions.
  │               │   log.md      │                         │ log.md
  │               └───────┬───────┘                         │
  │                       │                                 │
  │    Step 7: drift_detector                               │
  │               ┌───────┴───────┐                         │
  │               │ Take meeting  │                         │
  │               │ decisions     │                         │
  │               │               │──── RAG query ─────────▶│ ChromaDB
  │               │ Query arch    │◀─── similar chunks ────│ (vectors of
  │               │ report chunks │                         │  architecture
  │               │               │                         │  report)
  │               │ Compare via   │                         │
  │               │ keyword match:│                         │
  │               │ does meeting  │                         │
  │               │ contradict    │                         │
  │               │ architecture? │                         │
  │               └───────┬───────┘                         │
  │                       │                                 │
  │                       │ If drift found:                 │
  │                       │ emits "drift_detected" event    │
  │                       │                                 │
  │                  PIPELINE COMPLETE                      │
  │                       │                                 │
  │         The emitted events trigger MORE:               │
  │                       │                                 │
  │    action_items_extracted ──▶ project_mgmt pipeline     │
  │    decision_logged ──────▶ architecture pipeline        │
  │    drift_detected ───────▶ architecture pipeline        │
  │                                                         │
```

**What just happened in human terms:**

1. You uploaded a 45-minute meeting recording
2. The system parsed it into 3 decisions, 7 action items, and 2 concerns
3. Each requirement was formatted as a document and committed to GitHub
4. Items were classified by priority — P0 items were flagged for your review
5. Decisions were logged to a running decision log (wiki + GitHub)
6. The system checked if any meeting decisions contradicted the architecture
7. Jira tickets were automatically created with proper labels and priority
8. Three other pipelines were triggered to handle the downstream effects

**Time for a human to do all of this manually: ~3 hours.**
**Time for the system: ~30 seconds.**

---

## 4. The 7 Pipelines and 28 Agents

### Definitions

- **Agent**: A single Python class that does one specific job. It takes a trigger (input), runs logic, and produces a result (output). Each agent has access to the SharedMemory wiki and EventBus.
- **Pipeline**: An ordered chain of agents where each agent's output feeds the next agent's input. Like an assembly line — each station does one job, then passes the work forward.

### Pipeline → Agent Mapping (from actual code)

```
PIPELINE: requirements
PRACTICE AREA: Requirements Engineering
TRIGGER: .vtt transcript upload
STEPS:
  1. transcript_parser    — Parse VTT into structured JSON
  2. priority_classifier  — Classify items as P0/P1/P2
  3. req_extractor        — Format as REQ-XXX.md, commit to GitHub
  4. ticket_creator       — Create Jira tickets (P0 needs human approval)
  5. minutes_publisher    — Publish minutes to Confluence
  6. decision_logger      — Log decisions to wiki + GitHub
  7. drift_detector       — Check for architecture contradictions via RAG

PIPELINE: coach_session
PRACTICE AREA: Coach Session Memory
TRIGGER: coach/mentor .vtt upload
STEPS:
  1. transcript_parser    — Parse coach transcript
  2. session_memory       — Chunk + embed into ChromaDB for future RAG
  3. commitment_tracker   — Extract commitments with owners/deadlines
  4. concern_tracker      — Detect recurring themes across sessions
  5. coach_linker         — Link session content to open ML decisions
  6. decision_logger      — Log coach session decisions

PIPELINE: architecture
PRACTICE AREA: Architecture
TRIGGER: transcript processed, PR event, drift_detected event
STEPS:
  1. drift_detector       — Compare discussion vs canonical architecture
  2. adr_generator        — Draft Architecture Decision Record if needed
  3. diagram_updater      — Propose diagram updates
  4. traceability_builder — Update the unified traceability matrix

PIPELINE: coding
PRACTICE AREA: Coding
TRIGGER: PR event (future — for when actual coding begins)
STEPS:
  1. pr_reviewer          — Automated PR review (style, tests, traceability)
  2. test_generator       — Generate test stubs for new functions
  3. doc_generator        — Update API documentation
  4. prompt_regression    — Test prompt changes against golden dataset

PIPELINE: ml_decision
PRACTICE AREA: ML Decision Memory
TRIGGER: POC result submitted
STEPS:
  1. evidence_accumulator — Parse POC results and log evidence
  2. readiness_detector   — Check if enough evidence to close decision
  3. coach_linker         — Link evidence to coach session context

PIPELINE: project_mgmt
PRACTICE AREA: Project Management
TRIGGER: Cron (weekly, Friday 6pm)
STEPS:
  1. wbs_updater          — Sync WBS with Jira board state
  2. weekly_digest        — Generate weekly progress digest
  3. alert_agent          — Check project health, fire alerts

PIPELINE: knowledge
PRACTICE AREA: Knowledge Management
TRIGGER: Cron (pre-meeting) or new_session_embedded event
STEPS:
  1. context_packager     — Aggregate project context from wiki + Jira + events
  2. briefing_generator   — Generate pre-meeting briefing document
```

### Agent Count

- **28 unique agents** registered in the system
- **25 appear in pipelines** (some in multiple: `transcript_parser` in 2, `decision_logger` in 2, `drift_detector` in 2, `coach_linker` in 2)
- **3 standalone agents** (triggered on-demand, not part of a pipeline chain):
  - `stale_detector` — finds requirements with no Jira ticket
  - `boilerplate_generator` — scaffolds code from templates
  - `decision_log` — standalone ML decision logger

---

## 5. How Agents Talk to Each Other

Agents don't talk directly. They communicate through two mechanisms:

### Mechanism 1: SharedMemory (The Project Wiki)

Think of it as a shared whiteboard organized into folders (namespaces). Every agent can read and write to it.

**Physically:** A SQLite database at `memory/shared_memory.db` with a `wiki` table.

**How agents use it:**

```python
# transcript_parser deposits a meeting summary
self.wiki.put("meetings", "2026-01-22", {
    "summary": "Discussed ML extraction approach with eParts team...",
    "action_items": ["Set up confidence threshold testing", ...],
    "decisions": ["Primary approach: LLM extraction, not OCR"],
    "concerns": ["Data quality from vendor spec sheets unclear"]
})

# Later, context_packager reads it to build a briefing
meetings = self.wiki.list_namespace("meetings")
# Returns all stored meeting summaries
```

Every write is audited — the `wiki_log` table records who changed what, when, and the old vs new value.

### Namespaces (the "folders")

| Namespace | What's Stored | Example Entry | Written By | Read By |
|-----------|--------------|---------------|-----------|---------|
| `meetings` | Parsed meeting summaries | `{summary: "...", action_items: [...], decisions: [...]}` | transcript_parser | context_packager, weekly_digest |
| `decisions` | All decisions from all sources | `{text: "Use LLM extraction", speaker: "Harsha", context: "..."}` | decision_logger | adr_generator, traceability_builder |
| `concerns` | Recurring themes from coaches | `{theme: "data quality", sessions_raised: 3, severity: "high"}` | concern_tracker | alert_agent, briefing_generator |
| `requirements` | Extracted requirements | `{id: "REQ-003", title: "ML confidence scoring", priority: "P0"}` | req_extractor | stale_detector, traceability_builder |
| `commitments` | Coach session commitments | `{text: "deliver prototype by March 15", owner: "team", status: "pending"}` | session_memory | commitment_tracker, briefing_generator |
| `project_mgmt` | WBS state, sprint data | `{total_tickets: 50, done: 12, in_progress: 8}` | wbs_updater | weekly_digest, alert_agent |

### Mechanism 2: EventBus (Cross-Pipeline Triggers)

When something important happens in one pipeline, it fires an event that can trigger another pipeline.

**Physically:** A SQLite database at `memory/events.db` with an `events` table (history) and a `subscriptions` table (wiring).

**How it works:**

```
1. transcript_parser finishes parsing a meeting
2. It calls: self.emit("action_items_extracted", data={"items": [...]})
3. EventBus stores the event in events.db
4. EventBus looks up subscriptions table:
   "action_items_extracted" → target: project_mgmt pipeline
5. project_mgmt pipeline is queued for execution
```

### The 10 Cross-Pipeline Event Subscriptions

| Event | Fired By | Triggers | What Happens |
|-------|----------|----------|-------------|
| `action_items_extracted` | transcript_parser | project_mgmt | Ticket creation for action items |
| `decision_logged` | decision_logger | knowledge | Decision gets indexed |
| `drift_detected` | drift_detector | architecture | ADR drafting + diagram update |
| `new_session_embedded` | session_memory | knowledge | Briefing refresh |
| `recurring_concern` | concern_tracker | project_mgmt | PM alert for team |
| `commitment_overdue` | commitment_tracker | project_mgmt | Overdue alert |
| `decision_ready` | readiness_detector | coach_session | Link to coach context |
| `poc_evidence_logged` | evidence_accumulator | ml_decision | Readiness check |
| `human_review_needed` | traceability_builder | project_mgmt | Alert for human review |
| `new_requirements` | req_extractor | architecture | Drift check on new reqs |

**The key insight:** No pipeline is an island. The Requirements pipeline's output triggers the Architecture pipeline. The Coach Session pipeline's recurring concerns feed back into Project Management. This is what makes it a **framework** instead of a collection of scripts.

---

## 6. The Shared Infrastructure

### What Each Component Does

**SharedMemory** (`memory/shared_memory.db`)
- A key-value store organized into namespaces
- Agents deposit knowledge → other agents read it later
- Inspired by Karpathy's "wiki" pattern: accumulated intelligence over time
- Includes full audit trail (every write logged with before/after values)

**EventBus** (`memory/events.db`)
- Pub-sub notification system
- Agents fire events → subscribed pipelines get triggered
- Events are persistent (stored in SQLite), not fire-and-forget
- 10 active subscriptions wiring 7 pipelines together

**TraceabilityStore** (`memory/traceability.db`)
- Connects artifacts to each other: concern → requirement → Jira ticket → risk
- Two tables: `artifacts` (the nodes) and `links` (the edges)
- Currently: 184 artifacts, 760 links, 10 artifact types, 7 link types
- All links created via keyword matching — zero LLM calls

**PromptRegistry** (`memory/prompt_registry.db`)
- Every prompt used by agents is version-controlled here
- Each version has: author, content, review_status, active flag
- Ensures consistent AI use across team members (same prompt = same behavior)

**RiskRegister** (`memory/risk_register.db`)
- Identified project risks with severity, likelihood, mitigation status
- Auto-seeded from architecture report + coach sessions
- 16 risks tracked

**MetricsCollector** (`memory/metrics.db`)
- Every agent run logs: duration_ms, success/fail, llm_calls, tokens_used
- Human corrections logged via POST /metrics/correction
- Enables measurement of AI effectiveness (override rates, cost per artifact)

**ChromaDB** (`memory/chroma/`)
- Vector database for semantic similarity search (RAG)
- Stores text as numerical vectors using local ONNX model (no API needed)
- Used by: drift_detector (compare meeting vs architecture), session_memory (recall past coach sessions), briefing_generator (find relevant context)
- Why not SQL? SQL can only do exact text matching (`LIKE '%keyword%'`). ChromaDB finds semantically similar text ("confidence threshold" matches "accuracy calibration")

### Why SQLite? Why Not One Database?

| Consideration | SQLite (our choice) | Postgres |
|--------------|-------------------|----------|
| Setup | Zero — it's a file | Install server, manage connections |
| Cost | Free, runs locally | Free but needs infrastructure |
| Portability | Zip the `memory/` folder, share it | Database dump/restore |
| Concurrent writes | Limited (locks whole file) | Excellent |
| Our use case | Sequential pipeline execution, 1 user | Multi-user production system |

For a capstone demo and team of 5, SQLite is the right choice. For production, you'd migrate to Postgres — but the SQL schema is identical, so migration is straightforward.

---

## 7. The Unified Traceability Store

This answers: **"Where did this come from, and what does it connect to?"**

### What It Is

A SQLite database (`memory/traceability.db`) with two tables:
- `artifacts` — every traceable item (concern, decision, requirement, risk, Jira ticket, etc.)
- `links` — directed edges between artifacts (e.g., concern BECAME requirement)

### Artifact Types and Counts

| Type | Count | Source |
|------|-------|--------|
| meeting | 5 | Parsed from .vtt client meeting files |
| coach_session | 1 | From coach session memory DB |
| concern | 12 | Extracted from meeting transcripts and coach sessions |
| decision | 10 | Logged by decision_logger from meetings |
| action_item | 41 | Extracted by transcript_parser |
| commitment | 31 | Extracted by commitment_tracker from coach sessions |
| requirement | 12 | REQ-001 through REQ-012, defined from project knowledge |
| architecture | 6 | Key decisions from the architecture report |
| risk | 16 | From the risk register |
| jira_ticket | 50 | From live Jira API |

### Link Types

| Link Type | Count | Meaning | Example |
|-----------|-------|---------|---------|
| RAISED_IN | 122 | Originated from a meeting/session | "Data quality concern" RAISED_IN "Meeting Jan 22" |
| BECAME | 60 | Evolved into a different artifact | Concern BECAME Requirement |
| DECIDED_BY | 32 | Shaped by a decision | Requirement DECIDED_BY Architecture decision |
| ADDRESSES | 13 | Responds to a concern | Decision ADDRESSES Concern |
| TRIGGERED | 9 | Spawned another artifact | Decision TRIGGERED Architecture change |
| IMPLEMENTS | 204 | Jira ticket tracks/fulfills | Jira ticket IMPLEMENTS Requirement |
| MITIGATES | 320 | Reduces a risk | Requirement MITIGATES Risk |

### Example Chains (Simple and Meaningful)

**Chain 1: From a client concern to a Jira ticket**
```
[MEETING] Client Meeting Jan 22
    │
    └── RAISED_IN ──▶ [CONCERN] "How do we handle low-confidence predictions?"
                        │
                        └── BECAME ──▶ [REQUIREMENT] REQ-003: ML confidence scoring
                                        │
                                        ├── DECIDED_BY ──▶ [ARCHITECTURE] ARCH-003:
                                        │                   Threshold calibration design
                                        │
                                        ├── IMPLEMENTS ──▶ [JIRA] EPARTS-72:
                                        │                   Explore Azure AI services
                                        │
                                        └── MITIGATES ──▶ [RISK] Confidence threshold
                                                          miscalibration
```

**Why this matters:** If someone asks "why does EPARTS-72 exist?", trace backward:
Jira ticket → REQ-003 → client concern about low-confidence predictions → Meeting Jan 22.

**Chain 2: From a coach commitment to evidence**
```
[COACH SESSION] Christian Feb 20
    │
    └── RAISED_IN ──▶ [COMMITMENT] "We'll deliver a working prototype by March 15"
                        │
                        └── IMPLEMENTS ──▶ [JIRA] EPARTS-74:
                                           Finalize requirements by April 15
```

**Chain 3: From a risk to what mitigates it**
```
[RISK] "Vendor spec sheet formats vary widely"
    │
    └── mitigated by ── [REQUIREMENT] REQ-008: Support multiple document formats
                          (if we handle multiple formats, the format variation risk is reduced)

[RISK] "Confidence threshold miscalibration"
    │
    ├── mitigated by ── [REQUIREMENT] REQ-003: ML confidence scoring on every prediction
    │
    └── mitigated by ── [ARCHITECTURE] ARCH-003: Per-attribute threshold calibration
```

### Where Did All This Data Come From?

The script `pipeline/seed_traceability.py` populates the store from existing data:
1. Client meeting JSONs (from transcript parsing) → meeting + action_item + concern + decision artifacts
2. Coach session DB → commitment artifacts
3. Jira API (live) → jira_ticket artifacts
4. Risk register DB → risk artifacts
5. Architecture report → architecture artifacts (manually curated)
6. Project knowledge → 12 formal requirement artifacts (REQ-001 to REQ-012)

**Links** are created using domain-aware keyword matching and Jira label-based linking — **zero LLM calls**. The data is structured enough (meetings have dates, tickets have labels, requirements have IDs) that pattern matching works.

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

### ARTIFACTS (what gets produced)

| Artifact | Format | Generated By | Validation Gate |
|----------|--------|-------------|-----------------|
| Meeting minutes | JSON + Markdown | transcript_parser | Human reviews summary |
| Requirements (REQ-001..012) | Markdown | req_extractor | P0 items require human approval |
| Architecture Decision Records | Markdown | adr_generator | All ADRs require PR approval |
| Jira tickets | Jira Cloud | ticket_creator | P0 tickets need 1 approval |
| Traceability matrix | SQLite + Markdown | traceability_builder | Gaps flagged automatically |
| Risk register | SQLite | seed_risk_register | Human reviews mitigations |
| Decision log | Markdown | decision_logger | Committed to version control |
| Weekly digest | Markdown | weekly_digest | Published to team |
| Pre-meeting briefings | Text | briefing_generator | Sent before meetings |
| Versioned prompts | SQLite | PromptRegistry | Peer review before activation |

### PROCESSES (how work gets done)

Each process follows **ETVX** (Entry, Task, Verification, Exit):

```
PROCESS: Requirements Engineering (end-to-end)

  ENTRY:  .vtt transcript uploaded to system

  TASK:   7-step pipeline executes:
          parse → classify → extract → create_tickets →
          publish_minutes → log_decisions → detect_drift

  VERIFY: • P0 items flagged for human review
          • Drift detector compares vs architecture (RAG)
          • All outputs deposited to SharedMemory with audit trail
          • Traceability links established

  EXIT:   Requirements committed to GitHub
          Jira tickets created with labels
          Events emitted for downstream pipelines
```

All 7 pipelines are documented processes with ETVX definitions.

### RESOURCES (who/what does the work)

| Resource Type | Count | Role |
|--------------|-------|------|
| AI Agents | 28 | Automated execution of repeatable tasks |
| MCP Servers | 8 | Interface to external services (Jira, GitHub, ChromaDB...) |
| Shared Infra | 6 components | Cross-agent coordination and knowledge |
| Human Team | 5 | Judgment, review, approval gates |
| External Tools | Python 3.12, FastAPI, SQLite, ChromaDB | Runtime platform |

### MEASUREMENTS (how we know it's working)

See Section 9 for the full measurement framework.

---

## 9. Measuring AI Effectiveness — Counterfactuals

> "When evaluating whether it is worth using AI, we should ask what would happen
> if we did not use AI at all." — Christian (Coach)

### The Counterfactual Framework

For every AI-assisted task, we ask: **What is the total cost WITH AI vs WITHOUT AI?**

```
                    WITHOUT AI                    WITH AI
                    ──────────                    ───────
TASK COST           Human time to do the task     AI execution time (seconds)
                                                  + Human review time
                                                  + Token/API cost

ERROR COST          Human mistakes                AI mistakes
                    (forgotten items,             (misclassification,
                    inconsistent formats)          hallucinated items)
                                                  + Time to detect & fix

DOWNSTREAM COST     If error propagates:          If error propagates:
                    rework in later phases         same, but errors are
                                                  consistent and detectable

MEASUREMENT COST    Time to evaluate quality      Automated metrics collection
                    (manual spot-checks)          (agent logs everything)
```

### Applying This to Our Tasks

| Task | Without AI | With AI | Net Assessment |
|------|-----------|---------|----------------|
| **Parse 45-min transcript** | 2-3 hours/meeting × 5 meetings = 10-15 hrs total. Human misses items, inconsistent format. | 30 sec/meeting. May miss nuanced items. Human reviews output (15 min). Repeated weekly → savings accumulate. | **AI worth it.** Repeated task, big time savings, review catches errors. |
| **Classify priority (P0/P1/P2)** | Team discusses each item in a meeting (30-60 min). Subjective, inconsistent across members. | Keyword heuristic: instant but less accurate. With Claude: context-aware but costs tokens. P0 requires human approval regardless. | **AI worth it.** P0 human gate limits downside risk. Consistency across meetings is the real value. |
| **Create Jira tickets** | Team member does it manually, maybe next day. Forgets context. Inconsistent labels. Some items never get ticketed. | Immediate creation with labels. May create duplicate or low-quality tickets. | **AI worth it for P1/P2.** The cost of a missed ticket (forgotten work) exceeds the cost of deleting a bad ticket. |
| **Architecture drift detection** | Someone remembers "didn't we say something different last time?" — unreliable. | RAG query + keyword match: detects contradictions automatically. False positive rate unknown. | **AI worth it.** The cost of undetected drift (building the wrong thing) is very high. Even imperfect detection is better than none. |
| **Traceability matrix** | Manual maintenance: always out of date. Teams skip it because it's tedious. | 760 links via keyword matching, zero tokens. May have false links. | **AI worth it.** Zero marginal cost. The alternative (no traceability) is worse than imperfect traceability. |
| **Pre-meeting briefing** | Check Jira, wiki, notes, coach feedback... 30-60 min per person. | Aggregates from 7 sources in seconds. May miss context a human would catch. | **AI worth it.** Repeated weekly. Even a 70% useful briefing saves team 4+ hours/week. |

### What We Actually Measure (MetricsCollector)

| Metric | How Collected | What It Tells Us |
|--------|--------------|-----------------|
| Agent run duration | Automatic per run | Time cost of AI |
| Success/failure rate | Automatic per run | Reliability |
| LLM token usage | Automatic per call | Dollar cost |
| Human override rate | POST /metrics/correction | AI accuracy proxy |
| Traceability coverage % | TraceabilityStore.get_coverage() | Completeness |
| Tickets created vs deleted | Jira API diff | Precision of ticket creation |
| Commitment delivery rate | commitment_tracker | Team accountability |

### Key Principle: Measurement Should Be Cheaper Than the Decision

> "If a more precise measurement costs more than the value of the better decision,
> it is not worth doing." — Christian

- For **repeated tasks** (meeting parsing, ticket creation): measure carefully. The benefit compounds weekly.
- For **one-time tasks** (architecture doc creation): a rough estimate is enough. Don't over-measure.
- For **low-value tasks**: improve or remove the task rather than measuring AI performance on it.

---

## 10. Our SDLC: Agent-Augmented Iterative Lifecycle

### Why Not Use an Existing SDLC?

The meta-model framework explicitly warns: *"Avoid using a preexisting SDLC pattern which are fabricated on the idea that authoring software is the most labor-intensive part of development."*

With AI agents, authoring (parsing, classifying, drafting) is cheap. The bottleneck shifts to **validation, measurement, and judgment**.

| SDLC | Why We Rejected It |
|------|--------------------|
| **Scrum** | Sprint ceremonies assume the bottleneck is coordination between humans. With agents handling routine coordination, we don't need daily standups for ticket updates — the `weekly_digest` agent does that. |
| **RUP** | Too heavyweight for a 5-person team. RUP's elaborate phase/discipline matrix assumes large teams with dedicated roles. |
| **XP** | Pair programming and continuous integration are valuable, but XP doesn't account for AI agents as first-class team members. |
| **Waterfall** | Our work is iterative (prototype → pilot), not sequential. |

### What Our SDLC Actually Looks Like

```
┌──────────────────────────────────────────────────────────────────┐
│                   AGENT-AUGMENTED ITERATIVE LIFECYCLE              │
│                                                                    │
│  Two iterations with human phase gates between them:               │
│                                                                    │
│  ┌─────────────────────────┐    ┌─────────────────────────┐      │
│  │  ITERATION 1:           │    │  ITERATION 2:           │      │
│  │  PROTOTYPE              │    │  PILOT                  │      │
│  │                         │    │                         │      │
│  │  Goal: Prove ML         │    │  Goal: Prove            │      │
│  │  accuracy is achievable │    │  operational viability  │      │
│  │                         │    │                         │      │
│  │  Core pipeline:         │    │  Production deployment: │      │
│  │  ingest → predict →     │    │  real data, review      │      │
│  │  route → writeback      │    │  workflow, monitoring   │      │
│  └────────────┬────────────┘    └────────────┬────────────┘      │
│               │                              │                    │
│               ▼                              ▼                    │
│       [PHASE GATE]                   [PHASE GATE]                │
│       Human verifies:                Human verifies:              │
│       • Threshold calibrated         • Review workflow tested     │
│       • PIMS schema validated        • Monitoring in place        │
│       • Coach concerns addressed     • Client sign-off            │
│                                                                    │
│  ────────────────────────────────────────────────────────────────  │
│                                                                    │
│  CONTINUOUS ACROSS BOTH ITERATIONS:                                │
│                                                                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │Requirem- │ │Architect-│ │ Project  │ │Knowledge │            │
│  │ents      │ │ure       │ │ Mgmt     │ │          │            │
│  │Pipeline  │ │Pipeline  │ │Pipeline  │ │Pipeline  │            │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘            │
│       └─────────────┴────────────┴─────────────┘                  │
│                          │                                        │
│                   SharedMemory + EventBus                          │
│                   (continuous measurement)                         │
│                                                                    │
│  MEASUREMENT: Not sprint retrospectives.                           │
│  Every agent run logs: duration, tokens, success, corrections.     │
│  Measurement is continuous, automated, and queryable.              │
└──────────────────────────────────────────────────────────────────┘
```

### How Practice Areas Map to Pipelines

| Practice Area | Pipeline | Key Activities | Human Gate |
|--------------|----------|---------------|------------|
| Requirements Engineering | `requirements` | Parse → Classify → Extract → Ticket → Log → Drift Check | P0 approval |
| Architecture | `architecture` | Drift → ADR → Diagram → Traceability | ADR PR approval |
| Construction | `coding` | PR Review → Test → Doc → Prompt Regression | Merge approval |
| Coach Memory | `coach_session` | Parse → Embed → Commitments → Concerns → Link | None (advisory) |
| ML Decisions | `ml_decision` | Evidence → Readiness → Coach Link | Decision closure |
| Project Management | `project_mgmt` | WBS → Digest → Alerts | Alert triage |
| Knowledge | `knowledge` | Context Package → Briefing | None (informational) |

### Why This Works for eParts

1. **The client problem is a data pipeline** — linear architecture maps to linear iterations with clear phase boundaries.
2. **Team size (5) precludes heavyweight processes** — no sprint ceremonies, no Scrum Master. Agents handle repetitive coordination.
3. **AI must be measured to be justified** — continuous measurement gives us data, not anecdotes.
4. **Coach sessions revealed specific risks** — the lifecycle explicitly incorporates risk tracking and commitment tracking.
5. **The bottleneck is judgment, not authoring** — agents draft, humans approve. The SDLC reflects this by putting human phase gates between iterations, not between sprints.

---

## 11. Key Design Decisions

### 1. Offline-First Architecture
Every agent has a pattern-matching fallback when no LLM API key is available. ChromaDB uses local ONNX embeddings. The system is fully functional without any external AI service. You can use any LLM (Anthropic Claude, OpenAI, Gemini, local Llama) by changing one method in `agents/base.py`.

### 2. SQLite Everywhere
7 small database files in `memory/`, each serving one purpose. No infrastructure to maintain. Portable — the entire system state is a folder. Cost: zero.

### 3. Zero LLM Calls for Traceability
760 links created via domain-aware keyword matching. Structured data (dates, labels, IDs) enables deterministic pattern matching. Cost: zero tokens.

### 4. Prompt Governance
PromptRegistry version-controls every prompt, requires peer review before activation. 10 team conventions ensure consistent AI use across all team members.

### 5. Event-Driven Cross-Pipeline Communication
Adding a new pipeline only requires subscribing to events — no existing code changes. This is how the system scales to the coding phase.

### 6. Human-in-the-Loop at Every Critical Point
P0 requirements need human approval. ADRs need PR approval. ML decisions need human closure. The system proposes; humans decide.

---

*Auto-generated from the eParts SES codebase. Last updated: April 2026.*
*CMU MSE Studio 2026 · Pimsie Supreme · Python 3.12 · FastAPI · SQLite · ChromaDB*
