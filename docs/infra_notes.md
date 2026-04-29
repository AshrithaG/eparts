# Infrastructure Notes — Answers to Open Questions

---

## 1. Coding Pipeline — Tests and Quality Management

**Current state:** The coding pipeline has 4 steps: `pr_reviewer → test_generator → doc_generator → prompt_regression`. It triggers on PR events.

**"Create tests (done by human)" — what does the agent do then?**

Right now the `test_generator` agent generates *test stubs* — it reads the source code, identifies public functions, and produces a pytest skeleton with descriptive test names, fixture setup, and TODO comments where assertions need real values. The human writes the actual assertions and edge cases. The agent handles the boilerplate that nobody wants to write (imports, class setup, parameterization scaffolding), and the human handles the judgment: what *should* this function return? What's the boundary condition that matters?

This is a deliberate design choice. Fully AI-generated test assertions are dangerous because the test would just mirror whatever the code does — it's circular. If the code has a bug, the AI-generated assertion would test *for* the bug. Human-written assertions encode *intent*, which is independent of the implementation.

**Quality Management — how are we ensuring it?**

Quality assurance runs at multiple levels:

| Level | Mechanism | What it catches |
|-------|-----------|-----------------|
| **Per-agent** | Every agent has ETVX (Entry/Task/Verification/Exit) criteria | Agent-level correctness — did it produce valid output? |
| **Per-pipeline** | Pipeline executor tracks step success/failure, skips, duration | Pipeline-level health — did the chain complete? |
| **Per-prompt** | Prompt regression testing against golden datasets | Prompt-level quality — did a prompt change degrade output? |
| **Per-LLM-call** | Structured JSON output with regex fallback parsing | LLM output format reliability |
| **Cross-pipeline** | EventBus triggers (e.g., drift_detected → architecture review) | System-level consistency — are pipelines contradicting each other? |
| **Human gates** | `requires_human_review` flag, P0 items held | High-stakes decisions need human judgment |
| **Metrics** | MetricsCollector tracks success rate (93.75%), failure rate (6.2%), human correction rate (<1%) | Aggregate quality tracking over time |

The quality *system* is: agents do the work → pipeline executor validates each step → metrics record everything → anomalies trigger alerts → humans review high-stakes items. Quality isn't a separate phase — it's embedded in every pipeline step via the ETVX verification criteria.

---

## 2. Project Management — SDLC, Sprints, Velocity

**Which SDLC?**

We use a bespoke "Agent-Augmented Iterative Lifecycle" (documented in `docs/sdlc_choice.md`). We deliberately don't use Scrum, RUP, or XP because the meta-model framework says existing SDLCs assume authoring code is the bottleneck. With AI agents, the bottleneck shifts to validation, measurement, and integration. So we designed a lifecycle around that.

**Sprints? Velocity tracking?**

Not traditional sprints. We have 2 iterations (not sprints):
- **Iteration 1 (Prototype):** Prove accuracy is achievable — core ML pipeline, offline evaluation
- **Iteration 2 (Pilot):** Prove operational viability — production deployment, real data, review workflow

Instead of sprint velocity, we track:
- **Agent metrics:** 160 runs, 93.75% success rate, $0.03 total cost
- **Pipeline throughput:** end-to-end duration per pipeline (e.g., requirements pipeline: ~33s)
- **Human review rate:** <1% — meaning 99% of agent output is good enough without correction
- **Risk evolution:** risk register tracks status changes over time (16 risks: 2 mitigating, 14 open)

The `wbs_updater` agent syncs with Jira board state to maintain a work breakdown structure, and the `weekly_digest` agent generates progress summaries. The `alert_agent` monitors for anomalies (stale tickets, blocked items, overdue commitments).

**How are decisions made?**

Decisions are tracked automatically:
- The `decision_logger` agent extracts decisions from every meeting and commits them to `minutes/decisions.log.md` on GitHub
- Architectural decisions become ADRs (tracked in `artifact_versions.db` with version history)
- The risk register auto-populates from architecture docs, coach sessions, and meetings
- Everything is linked in the traceability store (184 artifacts, 760 links)

---

## 3. Principled Use of AI — Shared Context in Byte-Sized Chunks

**"How are we making sure of this?"**

Three mechanisms:

**a) Prompt Registry — same prompt for everyone**
When any team member triggers the transcript parser, they all use the same version-pinned prompt (e.g., `transcript_parser v3277a42a`). Nobody can accidentally use a different prompt. Every change requires a review. This eliminates the "I got a different answer" problem that comes from probabilistic models + inconsistent prompts.

**b) SharedMemory wiki — accumulated context, not one-shot**
Every agent deposits structured knowledge. After 160 runs, the wiki has 62 entries across 8 namespaces. When a new agent runs, it doesn't start from zero — it queries the wiki for relevant prior context. This means the 50th meeting processed benefits from the knowledge accumulated from the first 49.

**c) Chunked, retrievable context via RAG — not "dump everything"**
Instead of stuffing 40,000 words of meeting transcripts into a prompt (which would exceed context windows and dilute signal), we embed everything into ChromaDB in semantic chunks. An agent retrieves only the 3-5 most relevant chunks for its specific task. This is principled because:
- It respects token budgets (cost-efficient)
- It improves relevance (only related context, not noise)
- It's auditable (we can see exactly which chunks were retrieved for any given run)

---

## 4. LLM-as-Judge — Can We Apply It?

**"LLMs judging each other — can that concept be applied here?"**

Yes, and there are at least three places it fits naturally:

**a) PR Review (already exists, can be strengthened)**
The `pr_reviewer` agent already reviews code and posts comments. A natural extension: after the `test_generator` produces test stubs and a human fills in assertions, a *second* LLM call could evaluate whether the test actually covers the requirement it claims to cover. Agent 1 generates, Agent 2 evaluates. This is the LLM-as-judge pattern — one model produces, another critiques.

**b) Requirement Quality Check**
After `req_extractor` produces REQ-XXX documents, a validation agent could check: "Is this requirement testable? Is the acceptance criteria measurable? Does it conflict with any existing requirement?" This is essentially chain-of-verification — the first agent extracts, the second verifies.

**c) Prompt Regression as Judge**
The `prompt_regression` agent already tests prompt changes against golden datasets. This could be extended to use an LLM to *judge* output quality rather than just checking for structural correctness. Feed it the old output, the new output, and ask "which is better and why?" — that's LLM-as-judge for prompt evaluation.

**For the coding pipeline specifically:**

The ideal chain would be:
```
PR submitted
    → Agent 1: test_generator (generates test stubs from code)
    → Human: fills in assertions (encodes intent)
    → Agent 2: pr_reviewer (reviews code + tests for coverage, style, traceability)
    → Agent 3: quality_judge (LLM evaluates: do these tests actually verify the requirement?)
    → Human: final merge decision
```

Three agents, two human touchpoints. Each agent has a different role. The human handles judgment (what should this do? should we merge?), the agents handle analysis (is this well-formed? is this consistent?).

---

## 5. Engineering Harness — What Is It? Who Orchestrates?

**"What is the engineering harness?"**

The engineering harness is the entire shared infrastructure layer that all agents plug into. It's the "factory floor" that individual agents stand on:

```
┌──────────────────────────────────────────────────────────────────┐
│                    ENGINEERING HARNESS                            │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ BaseAgent    │  │ Pipeline     │  │ Central Orchestrator │   │
│  │ (abstract    │  │ Executor     │  │ (FastAPI server)     │   │
│  │  base class) │  │ (chains      │  │                      │   │
│  │              │  │  agents)     │  │ Routes triggers to   │   │
│  │ Provides:    │  │              │  │ correct pipeline.    │   │
│  │ - LLM calls  │  │ Provides:    │  │ Manages task queue.  │   │
│  │ - Wiki access│  │ - Context    │  │ Exposes health API.  │   │
│  │ - Event emit │  │   threading  │  │                      │   │
│  │ - Metrics    │  │ - Step skip  │  │ Decides WHAT runs    │   │
│  │ - Logging    │  │ - Failure    │  │ and WHEN.            │   │
│  │ - Retry      │  │   handling   │  │                      │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              SHARED INFRASTRUCTURE                        │   │
│  │                                                           │   │
│  │  SharedMemory ── EventBus ── MetricsCollector             │   │
│  │  PromptRegistry ── RiskRegister ── TraceabilityStore      │   │
│  │  ArtifactVersioning ── ChromaDB (RAG)                     │   │
│  │                                                           │   │
│  │  9 SQLite databases + 1 vector store                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              MCP SERVERS (Tool Layer)                      │   │
│  │                                                           │   │
│  │  Jira ── GitHub ── Confluence ── Slack ── Drive            │   │
│  │  ChromaDB ── Bitbucket ── VectorStore                     │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

**"Who is orchestrating this?"**

The **Central Orchestrator** (`orchestrator/main.py`) — a FastAPI server. It:
1. **Receives triggers** (POST `/webhook` for external events, POST `/trigger` for manual, POST `/pipeline/{name}` for direct pipeline execution)
2. **Routes to the correct pipeline** using `orchestrator/router.py` which maps trigger types → agent names
3. **Manages a task queue** (`orchestrator/queue.py`) that executes agents sequentially within a pipeline
4. **Registers all 28 agents** at startup via `orchestrator/registry.py`, wiring each agent to its MCP dependencies

The orchestrator is pure routing — it doesn't make LLM calls or contain business logic. It decides *what* runs and *when*. The agents decide *how*.

The Pipeline Executor is the next level down — it chains agents within a single pipeline, threading context from step to step. Step 1's output becomes Step 2's input. If a required step fails, the pipeline stops. If an optional step fails, it skips and continues.

So the hierarchy is:
- **Orchestrator** decides which pipeline to run (based on trigger type)
- **Pipeline Executor** runs the steps in order within that pipeline
- **BaseAgent** provides the common capabilities each step uses
- **Shared Infrastructure** provides persistence, memory, events, metrics
- **MCP Servers** provide external tool access
