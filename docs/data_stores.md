# Data Stores — What Lives Where and Why

The SES uses **9 SQLite databases + 1 ChromaDB vector store**. Each exists because it solves a specific storage problem that the others don't.

---

## 1. shared_memory.db (618 KB) — The Project Wiki

**What it is:** A namespaced key-value store where every agent deposits structured knowledge. Any agent can read any namespace.

**Why it exists:** Without this, each agent starts from zero. With it, the transcript parser's output from January is available to the drift detector in April. Knowledge accumulates rather than being discarded after each run.

| Namespace | Entries | What's stored |
|-----------|---------|---------------|
| `requirements_engineering` | 34 | Pipeline run results, parsed meeting data |
| `coach_session_memory` | 20 | Extracted coach session summaries |
| `requirements` | 9 | Formal REQ-XXX definitions with category, priority |
| `latest_runs` | 9 | Most recent output per agent (quick lookup) |
| `architecture` | 5 | Drift reports, architectural style, quality attributes |
| `commitments` | 4 | Coach commitments with owners and deadlines |
| `meetings` | 3 | Meeting metadata: date, type, participant count |
| `concerns` | 1 | Recurring concerns flagged across sessions |

Every write is logged in a `wiki_log` audit table — who wrote it, when, which agent, which pipeline.

---

## 2. events.db (90 KB) — The Event Bus

**What it is:** A publish-subscribe event store. Agents emit events; subscribed agents trigger automatically.

**Why it exists:** This is how pipelines talk to each other without hard-coded dependencies. The requirements pipeline doesn't call the architecture pipeline directly — it emits `decision_logged` and the architecture pipeline subscribes.

| Event Type | Count | What triggers it |
|------------|-------|------------------|
| `action_items_extracted` | 24 | transcript_parser finishes a meeting |
| `decision_logged` | 24 | transcript_parser or decision_logger finds a decision |
| `new_session_embedded` | 4 | session_memory embeds a coach meeting into ChromaDB |
| `recurring_concern` | 3 | concern_tracker detects a topic appearing in 3+ sessions |
| `requirements_extracted` | 3 | req_extractor produces formal requirements |

10 active subscriptions route these events to downstream agents.

---

## 3. traceability.db (311 KB) — Unified Traceability Store

**What it is:** A graph of artifacts and their relationships. Every concern, decision, requirement, risk, Jira ticket, and PR is an artifact. Links describe how they relate: RAISED_IN, BECAME, IMPLEMENTS, MITIGATES, etc.

**Why it exists:** The rubric requires traceability. More importantly, when a professor asks "where did this requirement come from?", we can trace it back to a specific speaker in a specific meeting.

| Artifact Type | Count | Examples |
|---------------|-------|---------|
| `jira_ticket` | 50 | EPARTS-42, EPARTS-82, etc. |
| `action_item` | 41 | Items extracted from 5 client meetings |
| `commitment` | 31 | Promises made to coaches |
| `risk` | 16 | From architecture doc, coach sessions |
| `concern` | 12 | Recurring themes across meetings |
| `requirement` | 12 | REQ-001 through REQ-012 |
| `decision` | 10 | Architecture and process decisions |
| `architecture` | 6 | ADRs and architecture components |
| `meeting` | 5 | 5 client meetings |
| `coach_session` | 1 | Coach sessions as a collective source |

760 links across 7 link types. Zero orphaned concerns. Zero unmitigated risks.

All links are created via domain-aware keyword matching — zero LLM tokens.

---

## 4. risk_register.db (24 KB) — Risk Register

**What it is:** Every identified risk with severity, likelihood, impact, mitigation, status, and owner.

**Why it exists:** Risks were scattered across meeting notes, coach feedback, and architecture documents. This consolidates them into one queryable store with proper risk statements.

19 risks total: 2 critical, 7 high, 7 medium, 3 team/health risks.

---

## 5. prompt_registry.db (53 KB) — Prompt Governance

**What it is:** Version-controlled store for all LLM prompts used by agents.

**Why it exists:** Without this, 5 team members use 5 different prompts for the same task. Results become non-reproducible. The registry pins each agent to a specific, peer-reviewed prompt version.

| Prompt | Versions | Author | Active Version |
|--------|----------|--------|----------------|
| `transcript_parser` | 2 | Ashritha | v3277a42a |
| `priority_classifier` | 1 | Ashritha | v5677a0b9 |
| `req_extractor` | 1 | Ashritha | vb8b387c7 |
| `session_extraction` | 1 | Ashritha | v763d8a27 |
| `briefing_generator` | 1 | Ashritha | ve304cdc6 |

Each version has a content hash. If the prompt file changes, a new version is automatically registered. The agent always uses the active version, not whatever's in the file.

---

## 6. coach_sessions.db (32 KB) — Coach Session Memory

**What it is:** Structured records of coach/mentor meetings — extracted topics, commitments, concerns, and links to ChromaDB chunks.

**Why it exists:** Coach sessions contain critical project guidance. This makes them queryable (e.g., "what did Christian say about measurement?") rather than locked in .vtt files.

---

## 7. ml_decisions.db (20 KB) — ML Decision Log

**What it is:** Tracks open ML decisions (model selection, threshold calibration, data strategy) with evidence accumulation and readiness scoring.

**Why it exists:** ML decisions need evidence from multiple sources before they're ready to close. This tracks the evidence trail — POC results, benchmark numbers, coach feedback — per decision.

---

## 8. artifact_versions.db (40 KB) — Artifact Versioning

**What it is:** Version history for key documents: requirements, architecture, risk register, ADRs.

**Why it exists:** The presentation needs to show document evolution. "The requirements document went through 5 versions — here's what changed each time and what triggered the change."

6 artifacts tracked, 14 total versions recorded.

---

## 9. metrics.db (inside MetricsCollector) — Agent Performance

**What it is:** Every agent run is recorded: duration, success/failure, LLM calls, tokens, cost, errors.

**Why it exists:** Without this, "AI helped us" is a vibe. With this, "AI processed 183 tasks at 94.5% success rate for $0.07 total" is evidence.

---

## 10. ChromaDB (memory/chroma/) — Vector Store for RAG

**What it is:** Local vector database using ONNX MiniLM-L6-v2 embeddings. Stores document chunks for semantic retrieval.

**Why it exists:** Agents need relevant context from large documents without stuffing everything into the prompt. ChromaDB retrieves the top-K most similar chunks for any query.

**Collections:**
- `coach_sessions` — 371 embedded chunks from 4 coach/mentor meetings
- `architecture` — Chunks from eParts_architecture_report.md
- `project_docs` — Chunks from project overview, meta-model framework, risk doc

All embeddings run locally (ONNX) — no API cost for indexing.
