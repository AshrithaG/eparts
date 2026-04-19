# eParts Agentic System — Cursor Vibe Coding Prompt
# Feed this entire file to Cursor (Claude Opus) as project context before writing any code.
# This is the single source of truth for what you are building, why, and how.

---

## WHO YOU ARE BUILDING THIS FOR

You are building an agentic SE system for **Pimsie Supreme** — a 5-person CMU MSE Studio
capstone team (Spring–Fall 2026). The team members are:
- Ashritha Gonuguntla
- Arjun Nair
- Hrishikesh Bhardwaj
- Jaivardhan Singh
- Zheliang Liu

This system is NOT a product being delivered to the client. It is the team's own internal
tooling — an agentic pipeline that helps the team execute the capstone project better.
Think of it as the team's operating system for the project.

---

## THE CAPSTONE PROJECT CONTEXT (what the team is building for the client)

**Client:** eParts Services LLC, Homestead PA. They build eCommerce procurement tools
for construction contractors. Their system of record is PIMS (Product Information
Management System) backed by MSSQL/PostgreSQL.

**The problem:** Supplier product catalogs arrive in heterogeneous formats — PDFs, CSVs,
SFTP drops, email attachments. The current ingestion workflow is entirely manual: ~1.5
FTEs at eParts and ~3 FTEs at sister company Alps Controls interpret, normalize, and map
every supplier attribute before it enters PIMS. This is slow, error-prone, and unscalable.

**What the team is building for the client:**
An Intelligent Product Data Ingestion and Enrichment Platform:
1. Ingestion Gateway — accepts CSV, PDF, email, SFTP, direct upload
2. Canonical staging tables — normalizes heterogeneous input into a standardized schema
3. ML Attribute Prediction Service — maps supplier attributes to PIMS canonical attributes
   with per-attribute confidence scoring
4. Confidence-based routing — high confidence → auto-accept + writeback to PIMS,
   low confidence → Human Review Queue
5. Human Review Queue — Brian and Dewey (catalog team) approve/correct low-confidence
   predictions
6. Idempotent writeback to PIMS staging tables via pyodbc
7. Observability via Datadog

**ML approach (current):** Hybrid rule engine + semantic similarity.
- Rules handle structured/known patterns (high precision)
- Semantic matcher uses all-MiniLM-L6-v2 sentence embeddings + cosine similarity
  for unmatched attributes
- Combined confidence: conf_final = α * conf_rule + (1-α) * conf_embed, α=0.7 (unvalidated)
- Confidence threshold: 0.85 (unvalidated — most sensitive open parameter)
- Zero-shot: no labeled training data required for the embedding layer

**POC results so far:**
- Ran semantic matcher POC using TF-IDF (stand-in for all-MiniLM, no internet in env)
- Index: 487 active PIMS attributes from production database
- Tested on 2 real supplier spec sheets: AIM2 (22 attrs) and RCT Flex CT (20 attrs)
- 86% auto-accepted overall (91% AIM2, 80% RCT)
- Ground truth eval on 217 unique PIMS attributes: 99.1% top-1 accuracy, 100% top-3
- Human review cases were genuinely absent attributes, not bad matches

**Key PIMS data model:**
- Categories (78 active) → ProductTypes/subcategories (755) → Products (2000) → ProductAttributeValues (50k rows)
- Attributes master list: 487 active attributes (e.g., SUPPLY VOLTAGE, OPERATING TEMP, ACCURACY)
- Suffixes: units of measure (VAC, VDC, mA, ohms, etc.)
- Attribute_suffix_mappings: which suffixes are valid for which attributes
- ProductTypeAttributes: which attributes are expected for each product type (the schema)

**Tech stack for client product:**
- Azure App Service (Python backend)
- Azure SQL Database (staging tables, review queue, audit trail)
- Azure Blob Storage (raw file archive)
- Azure Functions (timer-triggered publish/sync job)
- .NET / Vue.js / Nuxt.js (existing eParts stack)
- Datadog (observability)
- No PIMS writeback API exists — idempotency enforced in application code

**Architecture style:** Pipe and filter
- Ingestion → Normalization → Prediction → Routing → Review Queue → Writeback → PIMS
- Single Azure App Service deployment (not microservices — team size constraint)
- PredictionServiceInterface isolates model from routing/writeback
- Per-attribute routing (not per-record) to minimize review volume

**Open architectural decisions (unresolved):**
- ADR-1: Threshold value (0.85 is a guess — needs calibration against real labeled data)
- ADR-2: Alpha weighting (0.7 is a guess — needs sweep across correction data)
- ADR-3: Per-attribute vs per-record routing (pending attribute correlation analysis)
- ADR-4: PIMS staging schema compatibility (Jake has not delivered P1-C schema yet)
- ADR-5: Drift detection baselines not defined

**Key stakeholders:**
- Harsha (eParts) — sets accuracy threshold priority, approves model selection
- Jake (eParts) — PIMS integration, defines write interface and staging table contracts
- Brian & Dewey (eParts) — catalog team, primary review workflow users
- Alps Controls catalog team — secondary users (3 FTEs)
- David (eParts) — executive sponsor
- Christian Kastner — AI in SE coach (CMU professor)
- Jim — presentation mentor

---

## WHAT YOU ARE ACTUALLY BUILDING (the agentic SE system for the team)

A multi-agent pipeline that helps Pimsie Supreme operate as a team. This is not the
client product. This is the team's internal tooling.

**Core philosophy:**
- Agents handle the mechanical 80%, humans own the judgment 20%
- Every high-risk output (architecture changes, P0 tickets, ADRs) requires human approval
- Low-risk outputs (minutes, digests, alerts) write directly
- All agent outputs are versioned in Bitbucket — git history is the audit trail
- Prompts are version-controlled files, not hardcoded strings
- Bitbucket is the single source of truth. Confluence is the human-readable mirror.

---

## ARCHITECTURE OVERVIEW

```
Triggers/Inputs
    → Central Orchestrator Agent (FastAPI + task queue)
        → Domain Agents (5 generic + 2 eParts-specific)
            → MCP Servers (tools)
                → Outputs
```

**Inputs/Triggers:**
- Zoom transcript (.vtt) — auto-polled from Google Drive every 15 min
- Jira webhook events (ticket open/close/update)
- Slack event stream (designated project channel)
- GitHub/Bitbucket webhook (PR open/merge/comment)
- Scheduled cron (Mon 8am, Fri 6pm)
- Manual CLI / API trigger
- POC script run results (for ML Decision agent)

**Central Orchestrator:**
- FastAPI server (always-on)
- Three entry points: webhook endpoint, cron scheduler, manual API
- Shared task queue — agents run sequentially, no race conditions on commits
- Audit log of every agent invocation
- Does NOT make LLM calls itself — pure routing and queue management

---

## DOMAIN AGENTS (5 generic)

### 1. Requirements Agent
Triggered by: transcript upload, manual

Sub-agents:
- **Transcript Parser**: Send .vtt to Claude. Extract: meeting date, attendees, decisions,
  action items with owners, open questions, new requirements. Output: structured markdown.
- **Priority Classifier**: Assign P0/P1/P2 to each item.
  P0 = blocks delivery or client commitment with hard deadline
  P1 = important for current sprint, ticket immediately
  P2 = future sprint
  P0 ticket creation requires human approval gate.
- **REQ Extractor**: Format as REQ-XXX.md, commit to /requirements/parsed/
  Each file: requirement statement, source meeting, date, priority, open questions.
- **Stale REQ Detector**: Runs Mon 8am. Flag REQs with no Jira ticket and not mentioned
  in any meeting in past 14 days. Output: Slack alert + /docs/stale-requirements.md

HITL gate: REQs auto-committed, P0 Jira ticket creation needs 1 team approval.

### 2. Architecture Agent
Triggered by: transcript commit, PR event, manual

Sub-agents:
- **Drift Detector**: After every meeting, read canonical architecture.mmd + meeting
  minutes. Detect: new ingestion sources, routing changes, new downstream consumers,
  layer splits/renames, decisions contradicting existing diagram. Output: drift report
  committed to /docs/drift/YYYY-MM-DD.md
- **ADR Generator**: When significant technical decision detected in transcript or Slack
  → auto-draft ADR.md with context, options considered, rationale, consequences.
  Committed as PR — never direct commit. Specifically tracks these open decisions:
  threshold value, alpha weighting, per-attr vs per-record routing, PIMS schema compat.
- **Diagram Updater**: Propose Mermaid diff as PR against architecture.mmd.
  PR description quotes the meeting excerpt that triggered each change.
  Requires 2 team approvals to merge. Never direct commit.
- **Traceability Builder**: Maintain /docs/traceability.md — living matrix:
  REQ ID | Description | Jira ticket | PR | Test status | Last updated
  Updated on every relevant commit.

HITL gate: All architecture changes require PR approval. No direct commits.

### 3. Coding Agent (PARTIAL — not full autonomous coding)
Triggered by: Jira ticket assigned, PR opened

Sub-agents:
- **Boilerplate Generator**: When new ticket tagged as new service/module → scaffold
  directory structure, interface stubs, basic test file from ADR + REQ context. Output: PR.
- **PR Reviewer**: On every PR open → auto-comment on style, missing test coverage,
  whether PR references correct REQ ID and Jira ticket, new API surface documentation.
  Comment only — human decides on merge.
- **Test Generator**: Generate unit test stubs from function signatures when module scaffolded.
- **Doc Generator**: When API endpoint changes in PR → auto-update API docs in same PR.

HITL gate: All code PRs require human review and merge. No auto-merge ever.

### 4. Project Management Agent
Triggered by: transcript, cron, Jira webhook

Sub-agents:
- **Jira Ticket Creator**: From P0/P1 items → create tickets with description, assignee
  suggestion based on domain, priority label, link to source REQ file.
  P0 held in review queue for 1-click approval.
- **WBS Updater**: Maintain /sprint/wbs.md — task breakdown synced to Jira state.
  When tickets close → WBS updates. When new tickets created → appear under correct epic.
- **Weekly Digest Agent**: Runs every Friday 6pm. Reads all commits that week.
  Output format:
  ```
  ## Week of YYYY-MM-DD — Project digest
  ### Decisions made this week
  ### Requirements changes (added/modified)
  ### Sprint health (open/closed tickets, velocity)
  ### Architecture (drift detected/resolved)
  ### Next week preview
  ```
  Published to Confluence + Slack.
- **Alert Agent**: Monitors sprint state every 6 hours. Fires Slack alert when:
  ticket velocity off-track, must-have REQ has no Jira ticket, P0 ticket unassigned >48hrs,
  drift detected but no PR opened within 24hrs.

HITL gate: P1/P2 tickets auto-created. P0 tickets need 1 approval.

### 5. Knowledge Agent
Triggered by: commit to /minutes/, cron, PR events

Sub-agents:
- **Minutes Publisher**: Format meeting minutes → push to Confluence under correct parent
  (client meeting / mentor meeting / standup). Bitbucket = permanent record, Confluence = mirror.
- **Decision Logger**: Extract decisions from all sources → /minutes/decisions.log.md
  Each entry: decision, source, date, people present.
- **Prompt Regression Tester**: On any PR modifying /pipeline/prompts/ → run against
  golden dataset. Score on correctness, completeness, format. Block PR if score drops >10%
  below baseline.
- **Context Packager**: Runs Mon 7am (1hr before typical mentor meeting). Reads week's
  commits, open REQs, stale items, pending ADRs. Produces 1-page briefing. Slack-pinned.

---

## EPARTS-SPECIFIC AGENTS (2 unique — core differentiators)

These two agents cannot exist on any other capstone project. They are specific to:
1. The CMU coached capstone structure (recurring coach sessions with Christian Kastner)
2. The fact that the team is building a live ML system that produces empirical signals

### 6. Coach Session Memory Agent
Triggered by: transcript of any coach / mentor session

**Why this is eParts-specific:** The team has structured recurring sessions with Christian
Kastner (AI in SE coach) and other mentors where feedback is given, commitments are made,
and progress is evaluated. This feedback currently lives in meeting minutes and gets
partially forgotten by the next session. This agent maintains persistent memory across
ALL sessions.

Sub-agents:
- **Persistent Session Memory (RAG)**: Embeds all past coach/mentor session transcripts
  into a vector store (ChromaDB locally, Azure AI Search in prod). On each new session,
  retrieves semantically relevant past context before generating outputs.
- **Commitment Tracker**: Extracts explicit commitments from each session
  (e.g., "we will define confidence baselines by next week"). Cross-checks against
  Bitbucket commits and Jira closures to verify delivery status.
  Maintains: commitment → deadline → delivery status → evidence.
- **Pre-Meeting Briefing Generator**: Runs 1hr before every coach/mentor meeting.
  Produces structured briefing:
  - What Christian flagged last session
  - What the team committed to
  - What was delivered (with evidence links)
  - What is still open
  - Christian's recurring concerns across all sessions (pattern detection)
  Slacked to team channel.
- **Evolving Concern Tracker**: Tracks Christian's recurring themes across sessions.
  Currently known concerns: monitorability (flagged multiple times), evidence-based AI
  (not adding AI for sake of it), HITL design, threshold calibration.
  Surfaces pattern: "Christian has flagged monitorability in 3 of 4 sessions."

Technical implementation:
- Vector store: ChromaDB (local dev) → Azure AI Search (prod)
- Embedding model: all-MiniLM-L6-v2 (same model used in client ML POC — consistent)
- Memory schema:
  ```
  session_id, date, session_type (coach/mentor/standup),
  participant, commitments[], concerns[], decisions[], evidence_links[]
  ```
- RAG query: before generating any briefing, retrieve top-5 most relevant past sessions

HITL gate: Briefing auto-published to Slack. No gate needed — informational only.

### 7. ML Decision Memory Agent
Triggered by: POC script run completing, new labeled data commit, meeting transcript
touching ML decisions, manual trigger

**Why this is eParts-specific:** The team has a live ML system (semantic matcher) with
several open architectural decisions that depend on empirical evidence that accumulates
over time. No other capstone team has this problem. The open decisions are:
- Confidence threshold (currently 0.85 — unvalidated)
- Alpha weighting in hybrid model (currently 0.7 — unvalidated)
- Per-attribute vs per-record routing (pending correlation analysis)
- PIMS schema compatibility (Jake's P1-C schema not delivered)

These decisions cannot be closed by discussion alone — they need data. This agent
tracks the evidence state for each decision and tells the team when they have enough
to close it.

Sub-agents:
- **Open ML Decision Log**: Maintains living log of every unresolved ML architectural
  decision. Schema per entry:
  ```
  decision_id, name, current_value, basis (guess/empirical/validated),
  evidence_needed, evidence_so_far[], status (open/ready_to_close/closed),
  last_updated, source_adr
  ```
  Seeded from SW.pdf architectural decisions (ADR-1 through ADR-5).
- **Evidence Accumulator**: When POC results come in (new labeled data, precision-recall
  curves, auto-accept rates, correction patterns) → automatically updates relevant
  decision entries. Parses structured output from POC scripts.
  Tracks: labeled count, precision@threshold, recall@threshold, per-attribute variance,
  correction rate, alpha sweep results.
- **Decision Readiness Detector**: When accumulated evidence crosses a defined threshold
  → fires Slack alert: "Enough data to close [decision name] — run calibration now."
  Thresholds: ≥200 labeled examples → threshold calibration ready,
  ≥100 correction pairs → alpha calibration ready,
  ≥50 reviewed records → per-attribute correlation analysis ready.
- **Coach Session Linker**: Cross-references open ML decisions against coach session
  transcripts. When Christian asks about threshold calibration (he has), this agent
  surfaces: what decision is open, what evidence exists today, what is still needed,
  and links to the relevant ADR. Feeds into Coach Memory Agent briefings.

Technical implementation:
- Decision log: SQLite table locally → Azure SQL in prod
- Evidence parsing: structured JSON output from POC scripts ingested automatically
- Integration: feeds into Coach Memory Agent — ML decision state appears in pre-meeting
  briefings when relevant

HITL gate: Slack alerts auto-sent. Decision closure requires team member to manually
mark decision as closed after reviewing evidence.

---

## MCP SERVERS (tools available to all agents)

All external tool access goes through MCP servers. No agent has hardcoded credentials
or makes direct HTTP calls to external services.

| MCP Server | Tools | Used by |
|---|---|---|
| Jira MCP | create_ticket, update_ticket, get_sprint_state, add_comment | Requirements, PM agents |
| GitHub/Bitbucket MCP | commit_file, open_pr, add_pr_comment, get_pr_status | All agents writing to repo |
| Confluence MCP | create_page, update_page, get_page | Knowledge, Architecture agents |
| Slack MCP | send_message, read_channel, pin_message | Alert, Digest, Coach Memory agents |
| Google Drive MCP | list_files, read_file, watch_folder | Transcript parser, Notes agent |
| Anthropic API | claude_completion (claude-opus-4-5 or claude-sonnet-4-5) | All agents — all LLM calls |
| Vector Store MCP | embed, query, upsert, delete | Coach Memory, ML Decision agents |
| Bitbucket MCP | commit, branch, open_pr | All agents writing to repo |

---

## REPO STRUCTURE TO SET UP

```
eparts-agentic/
├── orchestrator/
│   ├── main.py              ← FastAPI app, all webhook + cron endpoints
│   ├── queue.py             ← shared task queue, sequential execution
│   └── router.py            ← trigger type → agent mapping
├── agents/
│   ├── base.py              ← base Agent class all agents inherit
│   ├── requirements/
│   │   ├── __init__.py
│   │   ├── transcript_parser.py
│   │   ├── priority_classifier.py
│   │   ├── req_extractor.py
│   │   └── stale_detector.py
│   ├── architecture/
│   │   ├── drift_detector.py
│   │   ├── adr_generator.py
│   │   ├── diagram_updater.py
│   │   └── traceability_builder.py
│   ├── coding/
│   │   ├── boilerplate_generator.py
│   │   ├── pr_reviewer.py
│   │   ├── test_generator.py
│   │   └── doc_generator.py
│   ├── project_mgmt/
│   │   ├── ticket_creator.py
│   │   ├── wbs_updater.py
│   │   ├── weekly_digest.py
│   │   └── alert_agent.py
│   ├── knowledge/
│   │   ├── minutes_publisher.py
│   │   ├── decision_logger.py
│   │   ├── prompt_regression.py
│   │   └── context_packager.py
│   ├── coach_memory/        ← eParts-specific
│   │   ├── __init__.py
│   │   ├── session_memory.py     ← RAG over past sessions
│   │   ├── commitment_tracker.py
│   │   ├── briefing_generator.py
│   │   └── concern_tracker.py
│   └── ml_decision/         ← eParts-specific
│       ├── __init__.py
│       ├── decision_log.py       ← SQLite-backed open decision store
│       ├── evidence_accumulator.py
│       ├── readiness_detector.py
│       └── coach_linker.py
├── mcp/
│   ├── jira.py
│   ├── slack.py
│   ├── bitbucket.py
│   ├── confluence.py
│   ├── drive.py
│   └── vector_store.py      ← ChromaDB wrapper
├── memory/
│   ├── coach_sessions.db    ← SQLite: session memory, commitments
│   ├── ml_decisions.db      ← SQLite: open decision log, evidence
│   └── chroma/              ← ChromaDB vector store
├── prompts/                 ← ALL prompts as versioned .txt files
│   ├── transcript_parser.txt
│   ├── priority_classifier.txt
│   ├── drift_detector.txt
│   ├── adr_generator.txt
│   ├── briefing_generator.txt
│   ├── weekly_digest.txt
│   └── ...
├── tests/
│   └── golden/
│       ├── transcripts/     ← real past .vtt files as test inputs
│       └── expected/        ← expected outputs paired with each input
├── data/
│   └── seed/
│       ├── christian_session_2026_02_16.pdf  ← seed for coach memory
│       ├── SW.pdf                             ← seed for ML decision log
│       └── poc_results.json                  ← semantic matcher POC output
├── .env.example
├── requirements.txt
└── README.md
```

---

## BUILD ORDER (implement in this exact order)

1. `agents/base.py` — base Agent class. Abstract run(), structured JSON logging,
   error handling with retry, call_claude() helper using Anthropic SDK.
   Get this right before touching anything else.

2. `orchestrator/main.py` — FastAPI with one working POST /webhook endpoint
   and one GET /health. Just routing, no agent logic yet.

3. `mcp/slack.py` — easiest to test. Implement send_message() and verify end-to-end.

4. `mcp/bitbucket.py` — commit_file() and open_pr(). Test with a dummy file.

5. `agents/coach_memory/session_memory.py` — RAG foundation.
   ChromaDB setup, embed(), query(). Seed with Christian's session PDF.
   Test: query "what did Christian say about monitorability" → returns relevant chunks.

6. `agents/coach_memory/commitment_tracker.py` — extract commitments from transcript,
   store in SQLite, cross-check against Bitbucket commits.

7. `agents/coach_memory/briefing_generator.py` — full pre-meeting briefing.
   End-to-end test: feed in Christian's Feb 16 session, generate briefing.

8. `agents/ml_decision/decision_log.py` — SQLite schema, seed from SW.pdf ADRs.
   Pre-populate: threshold (0.85, basis=guess), alpha (0.7, basis=guess),
   per-attr routing (open), PIMS schema (blocked on Jake).

9. `agents/ml_decision/evidence_accumulator.py` — parse POC JSON output,
   update decision entries. Test with semantic matcher POC results.

10. `agents/ml_decision/readiness_detector.py` — threshold checks + Slack alert.

11. `agents/requirements/transcript_parser.py` — full transcript → structured output.

12. `agents/requirements/priority_classifier.py` — P0/P1/P2 with eParts context.

13. `mcp/jira.py` — create_ticket(). Test end-to-end with one P1 item.

14. `agents/project_mgmt/ticket_creator.py` — full ticket creation pipeline.

15. Everything else in order: architecture agent, knowledge agent, coding agent,
    PM agent remaining sub-agents, weekly digest, alert agent.

16. `orchestrator/queue.py` + `orchestrator/router.py` — wire everything together.

17. Prompt regression test suite — seed golden dataset, wire to Bitbucket Pipelines.

---

## BASE AGENT CLASS SPEC

Every agent must inherit from this. Implement this first.

```python
class BaseAgent:
    def __init__(self, name: str, mcp_clients: dict):
        self.name = name
        self.mcp = mcp_clients
        self.logger = StructuredLogger(agent_name=name)

    @abstractmethod
    def run(self, trigger: AgentTrigger) -> AgentResult:
        # Every agent implements this
        pass

    def call_claude(self, prompt: str, system: str = None,
                    model: str = "claude-opus-4-5",
                    max_tokens: int = 4096) -> str:
        # Calls Anthropic API. Loads prompt from /prompts/ if prompt is a filename.
        # Logs input/output/tokens/latency to structured log.
        # Retries up to 3 times with exponential backoff on rate limit.
        pass

    def load_prompt(self, filename: str, **kwargs) -> str:
        # Loads prompt template from /prompts/{filename}.txt
        # Substitutes kwargs as template variables
        pass

    def log_run(self, trigger, result, duration_ms: int):
        # Appends to /pipeline/logs/agent_runs.jsonl
        # Format: {timestamp, agent, trigger_type, success, duration_ms, output_summary}
        pass
```

---

## KEY DATA SCHEMAS

### AgentTrigger
```python
@dataclass
class AgentTrigger:
    trigger_type: str  # "transcript", "jira_webhook", "slack", "pr", "cron", "manual", "poc_result"
    source: str        # file path, webhook payload, etc.
    metadata: dict     # trigger-specific context
    timestamp: datetime
```

### AgentResult
```python
@dataclass
class AgentResult:
    agent: str
    success: bool
    outputs: list[AgentOutput]  # files committed, tickets created, messages sent
    errors: list[str]
    requires_human_review: bool
    review_items: list[dict]    # items waiting for human approval
```

### Coach Session (SQLite)
```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    date TEXT,
    session_type TEXT,  -- coach/mentor/standup/client
    participants TEXT,  -- JSON array
    raw_transcript_path TEXT,
    processed_at TEXT
);

CREATE TABLE commitments (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    commitment_text TEXT,
    owner TEXT,
    deadline TEXT,
    status TEXT,  -- open/delivered/missed
    evidence_link TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE concerns (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    concern_text TEXT,
    raised_by TEXT,
    theme TEXT,  -- monitorability/hitl/evidence/threshold/etc
    times_raised INTEGER DEFAULT 1
);
```

### ML Decision Log (SQLite)
```sql
CREATE TABLE ml_decisions (
    decision_id TEXT PRIMARY KEY,
    name TEXT,
    current_value TEXT,
    basis TEXT,  -- guess/empirical/validated
    evidence_needed TEXT,
    status TEXT,  -- open/ready_to_close/closed
    source_adr TEXT,
    last_updated TEXT
);

CREATE TABLE evidence (
    id INTEGER PRIMARY KEY,
    decision_id TEXT,
    evidence_type TEXT,  -- poc_result/labeled_data/coach_feedback/correction_analysis
    description TEXT,
    value TEXT,  -- JSON
    collected_at TEXT,
    FOREIGN KEY (decision_id) REFERENCES ml_decisions(decision_id)
);
```

### Pre-populated ML Decisions (seed data — insert on first run)
```python
SEED_DECISIONS = [
    {
        "decision_id": "ADR-1-threshold",
        "name": "Confidence threshold value",
        "current_value": "0.85",
        "basis": "guess",
        "evidence_needed": "Precision-recall curves from ≥200 labeled submissions. Per-attribute accuracy variance.",
        "status": "open",
        "source_adr": "ADR-4"
    },
    {
        "decision_id": "ADR-1-alpha",
        "name": "Hybrid model alpha weighting",
        "current_value": "0.7",
        "basis": "guess",
        "evidence_needed": "Alpha sweep 0.3-0.9 across correction data. ECE, precision, coverage at each value.",
        "status": "open",
        "source_adr": "ADR-1"
    },
    {
        "decision_id": "ADR-2-routing",
        "name": "Per-attribute vs per-record routing",
        "current_value": "per-attribute",
        "basis": "empirical (partial)",
        "evidence_needed": "Pairwise mutual information on labeled data. ≥50 reviewed records inspected for cross-attribute inconsistency.",
        "status": "open",
        "source_adr": "ADR-2"
    },
    {
        "decision_id": "ADR-3-schema",
        "name": "PIMS staging schema compatibility",
        "current_value": "assumed compatible",
        "basis": "unvalidated",
        "evidence_needed": "Jake delivers P1-C schema. Map P1-C columns to canonical schema. Integration test 10 sample records.",
        "status": "blocked",
        "source_adr": "ADR-5"
    },
    {
        "decision_id": "ADR-4-drift",
        "name": "Drift detection baselines and alert thresholds",
        "current_value": "undefined",
        "basis": "guess",
        "evidence_needed": "Baseline confidence distribution from first 2 weeks of production data. Correction rate baseline.",
        "status": "open",
        "source_adr": "ADR-5"
    }
]
```

---

## ENVIRONMENT VARIABLES (.env.example)

```
# Anthropic
ANTHROPIC_API_KEY=

# Jira
JIRA_SERVER=https://epartsmse.atlassian.net/
JIRA_EMAIL=
JIRA_API_TOKEN=
JIRA_PROJECT_KEY=EPARTS

# Slack
SLACK_BOT_TOKEN=
SLACK_TEAM_CHANNEL=
SLACK_ALERT_CHANNEL=

# Bitbucket / GitHub
BITBUCKET_WORKSPACE=
BITBUCKET_REPO=
BITBUCKET_TOKEN=

# Confluence
CONFLUENCE_URL=
CONFLUENCE_TOKEN=
CONFLUENCE_SPACE_KEY=

# Google Drive
GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=
GOOGLE_DRIVE_TRANSCRIPT_FOLDER_ID=

# Vector store
CHROMA_PERSIST_DIR=./memory/chroma

# Database
SQLITE_DB_PATH=./memory/

# Agent config
CLAUDE_MODEL=claude-opus-4-5
CRON_POLL_INTERVAL_MIN=15
STALE_REQ_THRESHOLD_DAYS=14
P0_APPROVAL_REQUIRED=true
CONFIDENCE_THRESHOLD_READINESS=200
ALPHA_CALIBRATION_READINESS=100
```

---

## CODING CONVENTIONS

- Every agent file starts with a docstring: what it does, what triggers it, what it outputs
- All LLM calls go through `self.call_claude()` — never call the Anthropic SDK directly
- All prompts live in /prompts/ as .txt files — never hardcode prompt strings in Python
- All external API calls go through /mcp/ — never call Jira/Slack/etc directly from agents
- Use dataclasses for all data structures (not dicts)
- Every agent logs its run to /pipeline/logs/agent_runs.jsonl
- Commit messages follow convention: [agent:name] description of what was done
- SQLite for local dev, Azure SQL for prod — use the same schema

---

## FIRST THING TO BUILD

Start here. Get this right before anything else:

```
agents/base.py
```

Requirements:
- Abstract BaseAgent class
- Abstract run() method
- call_claude() that loads prompts from /prompts/, calls Anthropic SDK,
  logs input/output/tokens/latency, retries on rate limit
- load_prompt() that reads .txt file and substitutes template variables
- log_run() that appends to /pipeline/logs/agent_runs.jsonl
- StructuredLogger helper class

Once base.py is done and tested, move to orchestrator/main.py.
Do NOT start building multiple agents simultaneously. One file at a time.

---

## SEED DATA AVAILABLE

The following real files exist and should be used to seed and test the agents:

1. **Christian Kastner coach session transcript (Feb 16 2026)** — seed for Coach Memory Agent.
   Key themes extracted: evidence-based AI adoption, HITL design, measurement of AI
   effectiveness, targeted automation of high-frequency tasks, modular design.
   Key commitments extracted: propose formalized AI integration process with evidence,
   experiment with automating repeatable weekly tasks, investigate MCP server deployment.

2. **SW.pdf (Final Project Report Draft)** — seed for ML Decision Agent.
   Contains all 5 open ADRs with current values, rationale, and reconsideration triggers.

3. **Semantic matcher POC results** — seed evidence for ADR-1-threshold:
   - 42 attributes tested across AIM2 and RCT spec sheets
   - 86% auto-accept rate at threshold 0.25 (note: threshold was arbitrary for POC)
   - 99.1% top-1 accuracy on 217 PIMS attributes (self-retrieval test)
   - 6 human-review cases were genuinely absent attributes, not bad matches

4. **PIMS production data** — available as CSVs:
   - Attributes.csv (487 active PIMS attributes)
   - Product_attribute_values.csv (50k labeled rows)
   - Products.csv (2000 products)
   - Categories.csv (78 categories)
   - Product_Types_aka_subcategories.csv (755 product types)

---

*End of prompt. Start with agents/base.py.*
