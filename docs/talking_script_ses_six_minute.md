# Talking script — SES dashboard (6 minutes, technical, no clicks)

**Context:** Agenda **02 — SES + SDLC**. Hand off to **03 — Requirements** when you pivot to trace.  
**Screens:** **`interactive_architecture.html`**, then **`traceability_story.html`** (tab change only; no interactions).  
**Pacing:** Short sentences; **[pause]** = breath. If long on time, drop the *[optional]* sentence in §1.

Prefer **implementations** over slogans: **pipeline**, **`trigger_type`**, **agent**, **SQLite**, **MCP**, graph **edge**.

---

## 0. Agenda hook (~22 s)

“Item **two** is **SDLC choice**, not tooling theater: **SES** treats capstone automation as **versioned pipelines** plus **persisted state**, not lone Chat threads. **[pause]**  

I’ll cover **three things**: tying **engineering practice** to **concrete artifacts and gates**, **how runs execute mechanically**, **what infra is deployed**, then **REQ-001** read off **`traceability.db`** semantics.”

---

## 1. Engineering harness = practice → artifacts + gates (~55 s)

“**Engineering harness**, on this team, means **each practice area emits inspectable artifacts** with explicit policy. **[pause]**  

Take **requirements**: seven agents in **`PipelineStep` order**, triggered off **`trigger_type`** **`transcript`**. **`transcript_parser`** writes structured **`parsed_minutes`**. **`priority_classifier`** tags **`P0`**, **`P1`**, **`P2`**; **`P0` does not auto-open Jira**—that bypass is deliberate. **`req_extractor`** writes **`REQ-XXX.md`** via **Git**; **`ticket_creator`** uses **MCP-Jira**. **`minutes_publisher`**, **`decision_logger`** write externally where configured. **`drift_detector`** reads **Chroma-retrieved canon** and can **`emit("drift_detected", …)`**. **[pause]**  

That is **engineering harness**: **gates + file formats + external tickets**, enumerated in **`pipeline/pipelines.py`**, not ‘alignment.’ *[optional]* Every step names **`input_keys` / `output_key`** merged into **`PipelineContext`** so downstream reads are deterministic.**[pause]**  

No mysticism—it is **callable code paths** wired to artifacts your sponsor can grep.”

---

## 2. Agentic harness = DAG + buses (~60 s)

“**Agentic harness** is **`Pipeline`** composition: register agents in **`orchestrator/registry.py`**, instantiate **`PipelineExecutor`**, run **`execute(pipeline, payload)`**. **[pause]**  

**Cross-step data** is **`ctx.data`**—upstream **`AgentResult.data`** merges in; **`skip_if_empty`** skips a step cleanly if a prerequisite key is missing. **`BaseAgent`** writes namespaced blobs to **SharedMemory** (namespaced KV); **`emit`** appends **`event_type`** rows to **`events.db`** so **`EventBus.publish`** can fan out to subscribers.**[pause]**  

**Coding** / **architecture** pipelines show the same skeleton on **`trigger_type`** **`pr_event`**, **`poc_result`**, etc.—not every path is demo-green, but **`TRIGGER_ROUTES`** in **`router`** list what exists today.**[pause]**  

Harness two in one clause: **`PipelineContext`** + **`emit`** + MCP side effects—not one-shot completion APIs.”

---

## 3. SES infra as inventory (~68 s)

“**`interactive_architecture.html`** is deliberately an **inventory**. **[pause]**  

**Ingress:** transcripts, **`cron_friday_6pm`**, PR hooks—all reduce to **`POST /webhook`** bodies with **`trigger_type`**. **`TaskQueue`** in **FastAPI** runs async **`AgentTrigger`** payloads; **`demo.py`** is synchronous **`PipelineExecutor`** for reproducible scripting.**[pause]**  

You see **seven `Pipeline` constructors** (**requirements**, **`coach_session`**, **`architecture`**, **`project_mgmt`**, **`knowledge`**, **`coding`**, **`ml_decision`**), **twenty-eight agents**. **Green / amber / red**: **deployment maturity** for stakeholder demos, **not subjective quality**. **[pause]**  

**SQLite triple:** **`shared_memory.db`**, **`events.db`**, **`traceability.db`**. Chips list **PromptRegistry**, **risk_register**, metric stores—anything we claim SES ‘owns,’ we pinned on-screen.**[pause]**  

Integrations enumerated are **four MCP-capable backends** (**Jira, GitHub, Chroma, Confluence**). That is the infra list: **routing → execution → persisted buses → outbound MCP**.”

---

## 4. Traceability → Agenda 03 (~72 s)

“Flip to **`traceability_story.html`**: **REQ-001** root exposes **dual architecture threads** mirrored in ingest: **`MTG-2026-01-22`**, **`ARCH-002`** → **`CON-3d2b20`** → **`REQ-002`** → clustered **risk IDs**; **`ARCH-003`** → **`CON-daffed`** → **`DEC-e9b865`** → **`ARCH-004`**. Tree indent folds graph **`depth`** for readability; **`traceability.db`** edges still encode link types (**`MITIGATES`**, **`BECAME`**, **`DECIDED_BY`**, etc.).**[pause]**  

**Colored pills** enumerate **`artifact_type`** literals—the same taxonomy the **Intelligence** tab loads.**[pause]**  

**`traceability_diagram.html`** shows a **concept graph** plus **this REQ skeleton** schematic—optional if slides need a diagram before the text tree.**[pause]**  

Bridge to agenda **three**: requirements here mean **`REQ-*` markdown in Git** wired to **`traceability.db`** link rows, not one-off backlog notes.”

---

## 5. Close (~18 s)

“SES delta vs ‘LLM tooling’: **`PipelineDAG`**, **`SQLite` side effects**, **typed trace edges**. Next: drill **REQ** content—not just graph shape.”

---

## Cheatsheet (15 seconds)

| Label | Mechanical meaning |
|------|---------------------|
| Engineering harness | **Pipeline-defined outputs**: REQ md, drift emit, ticketing policy. |
| Agentic harness | **`PipelineExecutor` + `PipelineContext` + `emit`** + MCP **`BaseAgent`**. |
| Infra chips | Routing, **SQLite buses**, MCP quartet, registries. |
| REQ-001 slide | Projection of **`traceability.db`** / **`traceability_data.json`** graph. |
