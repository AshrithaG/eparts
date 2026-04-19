# eParts Agentic System

Multi-agent pipeline for **Pimsie Supreme** — CMU MSE Studio capstone team (Spring–Fall 2026).

This is the team's internal operating system, not the client product. Agents handle the mechanical 80% of project operations; humans own the judgment 20%.

## Architecture

```
Triggers (Zoom transcripts, Jira webhooks, Slack, GitHub, cron, manual)
    → Central Orchestrator (FastAPI + task queue)
        → Domain Agents (5 generic + 2 eParts-specific)
            → MCP Servers (Jira, Slack, Confluence, Bitbucket, Drive, ChromaDB, Anthropic)
                → Outputs (REQ docs, ADRs, Jira tickets, Confluence pages, digests)
```

### Domain Agents

| Agent | Purpose | Trigger |
|---|---|---|
| Requirements | Parse transcripts → extract REQs, priorities, stale detection | Transcript upload, cron |
| Architecture | Drift detection, ADR generation, diagram updates, traceability | Transcript, PR events |
| Coding | Boilerplate scaffolding, PR review, test/doc generation | Jira ticket, PR open |
| Project Mgmt | Jira ticket creation, WBS sync, weekly digest, alerts | Transcript, cron, Jira |
| Knowledge | Minutes → Confluence, decision log, prompt regression, briefings | Commit, cron |
| **Coach Memory** | RAG over coach sessions, commitment tracking, concern patterns | Coach session transcript |
| **ML Decision** | Track open ML ADRs, accumulate evidence, readiness alerts | POC results, transcripts |

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
# Fill in your API keys in .env

# Run the orchestrator
uvicorn orchestrator.main:app --reload --port 8000

# Run tests
pytest tests/ -v
```

## Project Structure

```
eparts/
├── orchestrator/          # FastAPI app, task queue, routing
├── agents/
│   ├── base.py            # Base Agent class (all agents inherit)
│   ├── requirements/      # Transcript parsing, priority, REQ extraction
│   ├── architecture/      # Drift detection, ADR, diagram, traceability
│   ├── coding/            # Boilerplate, PR review, test/doc gen
│   ├── project_mgmt/      # Jira tickets, WBS, digest, alerts
│   ├── knowledge/         # Minutes, decisions, prompt regression
│   ├── coach_memory/      # eParts-specific: coach session RAG
│   └── ml_decision/       # eParts-specific: ML decision tracking
├── mcp/                   # MCP server wrappers (Jira, Slack, etc.)
├── memory/                # SQLite DBs + ChromaDB vector store
├── prompts/               # All LLM prompts as versioned .txt files
├── tests/golden/          # Golden test inputs + expected outputs
├── data/seed/             # Seed data (transcripts, POC results)
└── pipeline/logs/         # Agent run logs (JSONL)
```

## Conventions

- All LLM calls go through `BaseAgent.call_claude()` — never call Anthropic SDK directly
- All prompts live in `/prompts/` as `.txt` files — never hardcode prompt strings
- All external API calls go through `/mcp/` — never call Jira/Slack/etc directly
- Every agent logs its run to `pipeline/logs/agent_runs.jsonl`
- Commit messages: `[agent:name] description`
- Bitbucket is the single source of truth; Confluence is the human-readable mirror

## Team

Ashritha Gonuguntla · Arjun Nair · Hrishikesh Bhardwaj · Jaivardhan Singh · Zheliang Liu
