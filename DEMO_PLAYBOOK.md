# eParts SES — Demo Playbook

## Quick Start

```bash
cd ~/eparts && source .venv/bin/activate

# Full interactive demo (13 sections, pauses between each)
python demo_full.py

# Auto-advance (no pauses — good for screen recording)
python demo_full.py --auto

# Just the requirements pipeline
python demo.py

# Specific transcript
python demo.py transcripts/GMT20260212-190517_Recording.transcript.vtt
```

---

## What the Demo Covers (13 Sections)

### Section 1: System Overview
**What it shows:** The big picture — 28 agents, 7 pipelines, 8 MCP servers, 9 SQLite databases.
**Talking points:**
- "This is a multi-agent framework, not a collection of scripts"
- "Every component is connected through SharedMemory and EventBus"
- Architecture: Triggers → Orchestrator → Agents → MCP → Outputs

### Section 2: LIVE Requirements Pipeline (the star demo)
**What happens:** Uploads the latest client meeting transcript (.vtt) and fires 7 agents in sequence.
**Live output the audience sees:**

| Step | Agent | What happens | Time |
|------|-------|-------------|------|
| 1/7 | transcript_parser | Sends .vtt to Gemini → extracts action items, decisions | ~30s |
| 2/7 | priority_classifier | LLM classifies each item as P0/P1/P2 | ~9s |
| 3/7 | req_extractor | Creates REQ-XXX.md files → **commits to GitHub live** | ~3s |
| 4/7 | ticket_creator | **Creates Jira tickets live** (P0 held for review) | ~9s |
| 5/7 | minutes_publisher | Formats meeting minutes | instant |
| 6/7 | decision_logger | Logs decisions to wiki + GitHub | instant |
| 7/7 | drift_detector | RAG query against ChromaDB architecture | instant |

**After this step:** Open Jira board and GitHub repo to show the live results.

### Section 3: LIVE Coach Session Pipeline
**What happens:** Processes a coach meeting transcript through 6 agents.
**Key outputs:** Session embedded in ChromaDB, commitments extracted, concerns tracked.

### Section 4: Shared Memory (Wiki)
**What it shows:** The SQLite-backed knowledge base that all agents read/write.
**Talking points:**
- "This is the Karpathy wiki pattern — agents accumulate knowledge"
- "62 entries across 8 namespaces"
- "When the architecture agent runs, it queries what requirements said"

### Section 5: Event Bus
**What it shows:** Cross-pipeline publish-subscribe triggers.
**Talking points:**
- "49 events emitted so far"
- "When transcript_parser emits `action_items_extracted`, ticket_creator subscribes"
- "When drift_detector emits `drift_detected`, architecture pipeline triggers"
- "This is what makes it a *framework*, not isolated scripts"

### Section 6: Traceability Store
**What it shows:** 184 artifacts, 760 links, 10 artifact types, 7 link types, zero orphans.
**Talking points:**
- "Every artifact is linked to its origin"
- "A meeting concern → becomes a requirement → becomes a Jira ticket"
- "All links built via keyword matching — zero LLM tokens"
- "Zero orphaned concerns or unmitigated risks"

### Section 7: Risk Register
**What it shows:** 16 risks auto-populated from architecture, coach sessions, meetings.
**Talking points:**
- "2 critical, 7 high, 7 medium"
- "Each risk has severity, category, source, mitigation strategy"
- "Auto-populated from multiple data sources"

### Section 8: Prompt Registry
**What it shows:** Version-controlled prompts with peer review workflow.
**Talking points:**
- "Without this, 5 team members use 5 different prompts for the same task"
- "Each prompt is version-pinned, peer-reviewed, and rollbackable"

### Section 9: Artifact Versioning
**What it shows:** How requirements, architecture, risks, and ADRs evolved over time.
**Talking points:**
- "Requirements doc has 5 versions, architecture has 4"
- "Each version records: who changed it, what triggered the change"
- "Proves evolution, not just a final document"

### Section 10: Metrics
**What it shows:** 160 agent runs, LLM token usage, cost tracking, failure rates.
**Talking points:**
- "Every run is metered — we know exactly what AI costs"
- "160 runs total, 93.75% success rate"
- "Total cost: $0.035 — this is the data for counterfactual analysis"

### Section 11: Live Integrations
**What to open in browser:**
- Jira: https://epartsmse.atlassian.net/jira/software/projects/EPARTS/board
- GitHub: https://github.com/AshrithaG/eparts

### Section 12: Dashboards (opens in Chrome)
- `interactive_architecture.html` — click any pipeline → granular agent view
- `intelligence.html` — knowledge graph, goal model, WBS, agent flow, traceability
- `architecture.html` — static architecture overview
- `metrics.html` — agent performance dashboard

### Section 13: Closing Summary
**Key takeaways to emphasize:**
- 28 agents as a connected framework
- End-to-end traceability: 184 artifacts, 760 links
- Counterfactual: transcript parsing 45min → 30s
- Graceful degradation: works with or without LLM

---

## Before the Demo Checklist

- [ ] `.env` has `GEMINI_API_KEY` (check quota: 5 free calls/minute)
- [ ] `.env` has `GITHUB_TOKEN` and `GITHUB_REPO`
- [ ] `.env` has `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`
- [ ] Virtual env works: `source .venv/bin/activate && python -c "import anthropic; print('ok')"`
- [ ] Jira board is open in a browser tab
- [ ] GitHub repo is open in a browser tab
- [ ] Terminal font is large enough for audience to see

## Gemini Quota Note

Free tier allows 5 requests/minute. The requirements pipeline uses 2 LLM calls
(transcript parsing + classification). If quota is exceeded, agents **gracefully
fall back to offline mode** (keyword heuristics). This is actually a great demo
point about resilient architecture.

If you need unlimited calls: upgrade to Gemini pay-as-you-go, or add an
`ANTHROPIC_API_KEY` to `.env`.

## Individual Pipeline Commands (if needed)

```bash
# Run just the FastAPI orchestrator (for API access)
uvicorn orchestrator.main:app --reload --port 8000

# Trigger via API
curl -X POST http://localhost:8000/pipeline/requirements \
  -H "Content-Type: application/json" \
  -d '{"trigger_type":"transcript","source":"transcripts/GMT20260416-180324_Recording.transcript.vtt"}'

# Quick infrastructure checks
python -c "from pipeline.shared_memory import SharedMemory; print(SharedMemory().stats())"
python -c "from pipeline.event_bus import EventBus; print(EventBus().stats())"
python -c "from pipeline.traceability import TraceabilityStore; print(TraceabilityStore().stats())"
python -c "from pipeline.risk_register import RiskRegister; print(RiskRegister().stats())"
```
