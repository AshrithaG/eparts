# eParts Agentic Software Engineering System

Multi-agent pipeline for **Pimsie Supreme** — CMU MSE Studio capstone team (Spring–Fall 2026).

This is the team's **Software Engineering System (SES)**, not the client product. Agents handle the mechanical 80% of project operations; humans own the judgment 20%.

## How It Works — The Trigger Flow

```
                    ┌──────────────────────────────────────┐
                    │           EXTERNAL TRIGGERS           │
                    │  Zoom .vtt  │  Jira  │  GitHub PR    │
                    │  Coach VTT  │  Cron  │  Manual API   │
                    └──────────┬───────────────────────────┘
                               │
                    ┌──────────▼───────────────────────────┐
                    │      CENTRAL ORCHESTRATOR (FastAPI)   │
                    │  POST /webhook → Router → TaskQueue   │
                    │  POST /pipeline/{name} → Executor     │
                    └──────────┬───────────────────────────┘
                               │
             ┌─────────────────┼─────────────────┐
             │                 │                 │
    ┌────────▼──────┐ ┌───────▼───────┐ ┌───────▼───────┐
    │  PIPELINE      │ │  PIPELINE      │ │  PIPELINE      │
    │  requirements  │ │  coach_session │ │  architecture  │
    │  7 agents      │ │  6 agents      │ │  4 agents      │
    └────────┬──────┘ └───────┬───────┘ └───────┬───────┘
             │                │                 │
    ┌────────▼──────────────────────────────────▼───────┐
    │              SHARED INFRASTRUCTURE                 │
    │  SharedMemory (Wiki)  │  EventBus  │  Metrics DB  │
    └────────┬──────────────┬────────────┬─────────────┘
             │              │            │
    ┌────────▼──────┐ ┌────▼────┐ ┌─────▼─────┐
    │  MCP SERVERS   │ │ ChromaDB│ │  SQLite   │
    │  GitHub, Jira  │ │ (RAG)  │ │  (state)  │
    │  Slack, Conf.  │ └────────┘ └───────────┘
    └───────────────┘
```

### The Cycle — Where Does It End?

The system is **event-driven**, not circular. Here's the lifecycle:

1. **Trigger** → A `.vtt` transcript, Jira webhook, PR event, or cron timer fires
2. **Route** → Orchestrator maps trigger type to pipeline(s)
3. **Execute** → Pipeline runs agents sequentially; each step's output feeds the next
4. **Deposit** → Every agent result goes to SharedMemory (the project wiki)
5. **Emit** → Agents fire events on the EventBus when significant things happen
6. **Cross-Trigger** → EventBus subscriptions may trigger other pipelines
7. **Terminate** → When no new events are generated, the cycle stops

**The cycle is self-terminating** because events flow downstream only:
- `transcript → requirements → architecture` (never back to transcript)
- `coach_session → concerns → PM alerts` (never back to coach session)
- Cross-pipeline events are one-shot; they don't re-fire the source

### Cross-Pipeline Communication (EventBus)

| Event | Source | Triggers |
|-------|--------|----------|
| `drift_detected` | requirements pipeline | → architecture pipeline |
| `new_requirements` | transcript_parser | → drift_detector |
| `recurring_concern` | concern_tracker | → PM alert_agent |
| `commitment_overdue` | commitment_tracker | → PM alert_agent |
| `action_items_extracted` | transcript_parser | → PM ticket_creator |
| `new_session_embedded` | session_memory | → briefing_generator |
| `decision_ready` | readiness_detector | → coach_linker |
| `poc_evidence_logged` | evidence_accumulator | → readiness_detector |
| `decision_logged` | any pipeline | → knowledge decision_logger |
| `human_review_needed` | any agent | → PM alert_agent |

## Architecture

### 7 Pipelines × 6 Practice Areas

| Pipeline | Practice Area | Steps | Trigger |
|----------|--------------|-------|---------|
| `requirements` | Requirements Engineering | 7 | `.vtt` transcript upload |
| `coach_session` | Coach Session Memory | 6 | Coach `.vtt` upload |
| `architecture` | Architecture | 4 | Transcript, PR event |
| `coding` | Coding | 4 | PR event |
| `ml_decision` | ML Decision Memory | 3 | POC result |
| `project_mgmt` | Project Management | 3 | Cron (Friday 6pm) |
| `knowledge` | Knowledge Management | 2 | Cron (pre-meeting) |

### 24 Domain Agents

| Domain | Agents |
|--------|--------|
| Requirements | `transcript_parser`, `priority_classifier`, `req_extractor`, `stale_detector` |
| Architecture | `drift_detector`, `adr_generator`, `diagram_updater`, `traceability_builder` |
| Coding | `boilerplate_generator`, `pr_reviewer`, `test_generator`, `doc_generator` |
| Project Mgmt | `ticket_creator`, `wbs_updater`, `weekly_digest`, `alert_agent` |
| Knowledge | `minutes_publisher`, `decision_logger`, `prompt_regression`, `context_packager` |
| Coach Memory | `session_memory`, `commitment_tracker`, `concern_tracker`, `briefing_generator` |
| ML Decision | `decision_log`, `evidence_accumulator`, `readiness_detector`, `coach_linker` |

### 7 MCP Servers (External API Wrappers)

| MCP | Status | Purpose |
|-----|--------|---------|
| `github` | **LIVE** | Commit files, create branches/PRs |
| `jira` | **LIVE** | Create/search issues, transitions |
| `bitbucket` | Ready | Alternate repo for client project code |
| `slack` | Ready | Alerts, digests, pinned messages |
| `confluence` | Ready | Meeting minutes, wiki pages |
| `drive` | Ready | Google Drive file access |
| `vector_store` | **LIVE** | ChromaDB embeddings (ONNX local) |

### Shared Infrastructure

| Component | Purpose | Storage |
|-----------|---------|---------|
| **SharedMemory** | Project wiki — agents deposit and query knowledge | SQLite |
| **EventBus** | Cross-pipeline pub/sub communication | SQLite |
| **MetricsCollector** | Token usage, costs, success rates, durations | SQLite |
| **PromptRegistry** | Version-controlled prompts with peer review | SQLite |
| **RiskRegister** | Auto-populated from architecture + coach sessions | SQLite |
| **ChromaDB** | Vector store for RAG (meetings, architecture, coach) | Local ONNX |

## Setup

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt

# Copy environment config
cp .env.example .env
# Fill in API keys (see .env.example for required values)

# Run the orchestrator
uvicorn orchestrator.main:app --reload --port 8000

# Ingest all transcripts
curl -X POST http://localhost:8000/ingest

# Run a pipeline manually
curl -X POST http://localhost:8000/pipeline/requirements \
  -H "Content-Type: application/json" \
  -d '{"trigger_type":"transcript","source":"transcripts/example.vtt"}'
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | System health + queue status |
| `/agents` | GET | All registered agents and routes |
| `/webhook` | POST | External event ingestion |
| `/trigger` | POST | Manual agent trigger |
| `/pipeline/{name}` | POST | Execute a named pipeline |
| `/pipelines` | GET | Framework summary |
| `/metrics` | GET | SES measurement dashboard data |
| `/dashboard` | GET | Interactive metrics dashboard |
| `/wiki` | GET | SharedMemory contents |
| `/events` | GET | EventBus log |
| `/risks` | GET | Risk register |
| `/prompts` | GET | Prompt registry |
| `/conventions` | GET | Team conventions |
| `/etvx` | GET | ETVX process model |
| `/framework` | GET | Complete SES overview |
| `/integrations` | GET | GitHub + Jira connection status |
| `/github/status` | GET | GitHub repo info |
| `/jira/status` | GET | Jira board status |

## Project Structure

```
eparts/
├── orchestrator/          # FastAPI app, task queue, routing, registry
├── agents/
│   ├── base.py            # BaseAgent (call_claude, wiki, events, metrics)
│   ├── requirements/      # transcript_parser, priority, req_extractor, stale
│   ├── architecture/      # drift_detector, adr, diagram, traceability
│   ├── coding/            # boilerplate, pr_review, test_gen, doc_gen
│   ├── project_mgmt/      # tickets, wbs, digest, alerts
│   ├── knowledge/         # minutes, decisions, prompt_regression, context
│   ├── coach_memory/      # session_memory, commitments, concerns, briefing
│   └── ml_decision/       # decision_log, evidence, readiness, coach_linker
├── mcp/                   # MCP server wrappers (GitHub, Jira, Slack, etc.)
├── pipeline/              # SharedMemory, EventBus, Metrics, Pipelines, ETVX
├── dashboard/             # Interactive HTML dashboards (metrics, intelligence)
├── docs/                  # SES assessment, SDLC, practice areas, why-everything
├── prompts/               # All LLM prompts as versioned .txt files
├── transcripts/           # Raw client meeting .vtt files
├── coach_meetings/        # Coach/mentor session .vtt files
├── minutes/               # Processed meeting minutes (JSON + MD)
├── tests/golden/          # Prompt regression golden datasets
└── memory/                # SQLite DBs + ChromaDB (gitignored)
```

## Conventions

- All LLM calls go through `BaseAgent.call_claude()` — never call Anthropic SDK directly
- All prompts live in `/prompts/` as `.txt` files — never hardcode prompt strings
- All external API calls go through `/mcp/` — never call Jira/Slack/etc directly
- Every agent logs its run to metrics DB + JSONL
- Commit messages from agents: `[agent:name] description`
- GitHub is the live repo; Bitbucket reserved for client project code

## Extending for Real PRs (Coding Phase)

When the team starts writing actual client code:

1. **PR events** trigger the `coding` pipeline automatically via GitHub webhooks
2. `pr_reviewer` reviews the diff, `test_generator` creates test stubs, `doc_generator` updates API docs
3. The `architecture` pipeline runs `drift_detector` against the PR to catch architectural drift
4. `traceability_builder` links the PR to requirements and Jira tickets
5. No changes needed — just configure the GitHub webhook to POST to `/webhook`

## Team

Ashritha Gonuguntla · Arjun Nair · Hrishikesh Bhardwaj · Jaivardhan Singh · Zheliang Liu

**Mentor:** Dennis Grinberg · **Coaches:** Ben, Christian, Cory
