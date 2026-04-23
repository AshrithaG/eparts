# SES Presentation Guide — Jai, Hrishi & Ashritha

**Section 5: Software Engineering System [~7 min]**

Per rubric: "SE System overview, SDLC choice, Processes/artifacts/measurements/resources per meta-model, Evidence that process will be effective particularly with AI, Decisions and reasoning about tradeoffs"

---

## Slide Flow

### Slide 1: SES Overview (1 min)
**Title:** "Our Engineering System Is Engineered"

**Key message:** We don't just use AI ad-hoc — we built a multi-agent framework where every repeatable activity is documented, measured, and connected.

**Visual:** Framework diagram (docs/framework.mmd) showing:
- 7 pipelines, 29 steps, 25 agents
- Triggers → Orchestrator → Domain Agents → MCP Servers → Outputs
- Measurement system wrapping everything

**Speaker notes:**
> "We took the meta-model seriously. Instead of bolting AI onto a traditional SDLC, we engineered a system where Artifacts, Processes, Resources, and Measurements are first-class concepts. Every agent is a Resource that implements a Process, generates Artifacts, and is measured. This is 56 Python files, 7,800+ lines of production code."

---

### Slide 2: SDLC Choice & Meta-Model Mapping (1 min)
**Title:** "Bespoke SDLC — Not Scrum, Not RUP"

**Visual:** Four-quadrant diagram:

| | Artifacts | Measurements |
|---|---|---|
| **Processes** | 31 ETVX-documented | Tokens, latency, success rate |
| **Resources** | 25 agents + 6 MCP servers | Human review rate, corrections |

**Speaker notes:**
> "Following Christian's guidance, we didn't pick an off-the-shelf SDLC. We created a bespoke lifecycle with 7 practice areas. Each has its own pipeline — an ordered chain of agents where data flows from one step to the next. Every process is documented in ETVX format — Entry criteria, Tasks, Verification, Exit. We have 31 documented processes with 100% agent coverage."

---

### Slide 3: End-to-End Requirements Pipeline (2 min) — LIVE DEMO
**Title:** "Requirements Engineering — End-to-End Connected"

**This is the money slide.** Run the demo live.

**Before demo, say:**
> "The rubric asks for at least one practice area with end-to-end connection. Let me show you Requirements Engineering running on a real client meeting from April 2nd."

**Run:** `python demo.py --section requirements --no-pause`

**What audience sees:**
1. Real VTT transcript → transcript_parser extracts 10 action items
2. priority_classifier → 2 P1, 8 P2
3. req_extractor, ticket_creator, minutes_publisher, decision_logger, drift_detector
4. 7/7 SUCCESS in ~120ms

**After demo, say:**
> "That's a real Zoom recording from our April sprint review, going through 7 agents in sequence. The transcript parser does structural extraction without any API calls — it runs entirely locally. Each agent's output feeds the next. The same pipeline processes all 5 of our client meetings."

---

### Slide 4: Coach Session Memory — RAG Pipeline (1.5 min) — LIVE DEMO
**Title:** "Coach Memory — Never Lose Context Between Sessions"

**Before demo:**
> "This is eParts-specific. We have coaching sessions with Cory, Ben, and Dennis. The system embeds every session into ChromaDB so we never walk into a meeting blind."

**Run:** `python demo.py --section coach --no-pause` then `python demo.py --section search --no-pause`

**What audience sees:**
1. Cory's session → 6 pipeline steps → 95 chunks embedded
2. Semantic search: "agent visibility" → Cory's exact advice surfaces
3. "ETVX process documentation" → finds Dennis's risk doc + project overview

**After demo:**
> "317 chunks from 3 coach sessions plus 79 chunks from project documents — all searchable by meaning, not keywords. Before every meeting, the briefing generator assembles last session's recap, open commitments, recurring concerns, and relevant past context into a structured briefing."

---

### Slide 5: Measurement System (1 min)
**Title:** "Every Agent Call Is Measured"

**Visual:** Dashboard screenshot (dashboard/metrics.html) or live browser

**Key metrics to highlight:**
- 8 meetings processed, 53,745 words analyzed, 123 action items extracted
- 396 ChromaDB chunks (317 sessions + 79 knowledge docs)
- 30 commitments tracked, concern patterns detected across 3 sessions
- Per-agent: tokens, latency, success rate, human review rate, corrections

**Speaker notes:**
> "The meta-model requires a measurement system. Ours is automatic — every LLM call records tokens, latency, and cost. Every agent run records success, duration, and whether it needed human review. This feeds a real-time dashboard. We use GQIM: our Goal is to get the best out of AI; our Question is how effective are our prompts; our Indicator is re-prompt frequency; our Metric is interactions per task type."

---

### Slide 6: Tradeoffs & Decisions (30 sec)
**Title:** "Decisions and Reasoning"

**Visual:** Decision table

| Decision | Rationale |
|----------|-----------|
| Local embeddings (ONNX MiniLM) over API | No API dependency, runs offline, same model as client POC |
| ChromaDB over Pinecone | Local-first, zero config, swappable to Azure AI Search |
| Prompts as versioned files | Enables regression testing, A/B testing, git history |
| Offline-first agent design | Demo without API keys, Claude enhances but isn't required |
| SQLite → Azure SQL migration path | Start simple, proven upgrade path |

**Speaker notes:**
> "Two key tradeoffs: First, we designed every agent to work offline with pattern matching, then enhance with Claude when available. This means the framework runs anywhere — no API keys needed for the demo you just saw. Second, we version-control prompts as files and run regression tests against golden datasets before deploying changes."

---

## Demo Commands Quick Reference

```bash
# Full demo with pauses between sections (for presentation)
python demo.py

# Individual sections (for targeted demos)
python demo.py --section stats --no-pause
python demo.py --section requirements --no-pause
python demo.py --section coach --no-pause
python demo.py --section search --no-pause
python demo.py --section briefing --no-pause

# Open dashboard in browser
open dashboard/metrics.html

# Start FastAPI server (if needed for live API demo)
cd /Users/ashritha/eparts && source .venv/bin/activate
uvicorn orchestrator.main:app --port 8000
```

---

## Connecting to Other Sections

**For Project Context (Arjun/Liu):**
- "We've processed all 5 client meeting transcripts — Jan 22 through Apr 16"
- "The system extracted 123 action items and 14 decisions automatically"
- Timeline data is in the dashboard Overview tab

**For Management (Arjun/Liu):**
- "30 commitments tracked from coach sessions, with overdue alerting"
- "Measurement plan maps directly to GQIM framework"
- Risk doc from Dennis session is in the knowledge base

**For Requirements (Liu/Arjun):**
- "Requirements pipeline runs end-to-end: transcript → classify → extract → Jira → Confluence → drift check"
- "P0 items automatically flagged for human review"

**For Architecture (Liu/Arjun):**
- "Architecture pipeline includes drift detection — when a meeting discussion contradicts the canonical architecture, it flags it"
- "ADR generation agent drafts Architecture Decision Records from detected decisions"

---

## Rubric Checklist

- [x] SE System overview — framework diagram + dashboard
- [x] SDLC choice — bespoke, not off-the-shelf, justified
- [x] Processes per meta-model — 31 ETVX-documented processes
- [x] Artifacts per meta-model — prompts versioned, ADRs, REQ docs, minutes, briefings
- [x] Measurements per meta-model — tokens, latency, success rate, human review, corrections
- [x] Resources per meta-model — 25 agents (auton/assist) + human reviewers
- [x] Evidence of effectiveness — live demo on real data, 8 meetings processed
- [x] AI use justified — offline-first design, enhancement with Claude, prompts as artifacts
- [x] End-to-end connection — Requirements pipeline (7 steps) + Coach Memory pipeline (6 steps)
- [x] Decisions and reasoning — tradeoff table with rationale

---

## Key Numbers to Remember

| Metric | Value |
|--------|-------|
| Total code | 57 files, 7,800+ lines |
| Pipelines | 7 pipelines, 29 steps |
| Agents | 25 unique |
| MCP Servers | 6 |
| Meetings processed | 8 (5 client + 3 coach) |
| Total words analyzed | 53,745 |
| Action items extracted | 123 |
| ChromaDB chunks | 396 |
| Coach commitments tracked | 30 |
| ETVX processes documented | 31 |
| Pipeline success on real data | 100% (all steps pass) |
