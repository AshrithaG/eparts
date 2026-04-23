# eParts Capstone Project — Complete Project Overview

**Team:** Pimsie Supreme
**Program:** CMU MSE Studio 2026
**Client:** eParts Services LLC, Homestead PA
**Coach:** Christian Kästner (AI in SE Coach)
**Presentation Mentor:** Jim

---

## 1. Project Context

### 1.1 Who is eParts Services?

eParts Services LLC is a small, highly collaborative company based in Homestead, PA. They build eCommerce procurement tools for construction contractors — centralizing purchasing across branch networks, managing bills of materials, and maintaining robust product data integrated with estimating and accounting tools.

Their system of record is **PIMS** (Product Information Management System), backed by MSSQL and PostgreSQL.

**Key client personnel:**
- **Joe Benscoter** — President
- **Client PM** — Senior ML Developer and Project Manager. Sets accuracy threshold priority, approves model selection.
- **Jake Monroe** — Tech Lead. Owns PIMS integration, defines the write interface and staging table contracts.
- **Brian & Dewey** — Catalog team, primary review workflow users.
- **Alps Controls catalog team** — Sister company, secondary users (3 FTEs).
- **David** — Executive sponsor.

**Client tech stack:** Azure, .NET, Vue.js/Nuxt.js, SQL Server, Elasticsearch, Kafka, Snowflake, PostgreSQL, Datadog, Cursor, Bitbucket.

### 1.2 The Problem

Supplier product specifications arrive in heterogeneous formats — PDFs, CSVs, SFTP file drops, email attachments, and web catalogs. The current ingestion workflow is entirely manual. Roughly 1.5 FTEs at eParts and 3 FTEs at sister company Alps Controls interpret, normalize, and map every supplier attribute before it enters PIMS.

This makes the process:
- Tedious and repetitive
- Error-prone due to manual interpretation inconsistencies
- Slow to update — catalog freshness lags behind supplier changes
- Unscalable as supplier volume grows

### 1.3 What We Are Building (for the Client)

An **Intelligent Product Data Ingestion and Enrichment Platform** with these components:

1. **Ingestion Gateway** — accepts CSV, PDF, email, SFTP, direct upload
2. **Canonical staging tables** — normalizes heterogeneous input into a standardized schema
3. **ML Attribute Prediction Service** — maps supplier attributes to PIMS canonical attributes with per-attribute confidence scoring
4. **Confidence-based routing** — high confidence auto-accepts and writes back to PIMS; low confidence goes to the Human Review Queue
5. **Human Review Queue** — Brian and Dewey approve or correct low-confidence predictions
6. **Idempotent writeback to PIMS** via pyodbc (no PIMS writeback API exists; idempotency enforced in application code)
7. **Observability** via Datadog

---

## 2. PIMS Data Model

```
Categories (78 active)
  └── ProductTypes / Subcategories (755)
        └── Products (~2,000)
              └── ProductAttributeValues (~50,000 rows)
```

- **Attributes master list:** 487 active attributes (e.g., SUPPLY VOLTAGE, OPERATING TEMP, ACCURACY)
- **Suffixes:** units of measure (VAC, VDC, mA, ohms, etc.)
- **Attribute_suffix_mappings:** which suffixes are valid for which attributes
- **ProductTypeAttributes:** which attributes are expected for each product type (the schema)

---

## 3. ML Approach

### 3.1 Current Design: Hybrid Rule Engine + Semantic Similarity

- **Rules** handle structured/known patterns for high precision
- **Semantic matcher** uses `all-MiniLM-L6-v2` sentence embeddings with cosine similarity for unmatched attributes
- **Combined confidence:** `conf_final = α * conf_rule + (1 - α) * conf_embed`, with α = 0.7 (unvalidated)
- **Confidence threshold:** 0.85 (unvalidated — the most sensitive open parameter)
- **Zero-shot:** no labeled training data required for the embedding layer

### 3.2 Why Semantic Matching Over Alternatives

We compared three approaches and chose semantic matching because DistilBERT and CatBoost both need labeled training data (examples of "this supplier attribute maps to this PIMS attribute") before they can learn. We don't have that labeled data. The semantic matcher needs zero labeled data because it isn't learning a mapping — it's comparing meanings. The knowledge of what words mean is already baked into the model from pre-training on massive text corpora.

`all-MiniLM-L6-v2` specifically is a distilled BERT-style model, fine-tuned on sentence similarity via contrastive learning. It's around 22 million parameters, runs fast on CPU, and needs no GPU.

### 3.3 How It Works (Mechanically)

1. Every PIMS attribute name is converted into a dense vector via the embedding model. This becomes the **index**.
2. When a supplier spec sheet arrives, each attribute name is embedded the same way.
3. **Cosine similarity** finds the closest PIMS attribute in the index.
4. The similarity score **is** the confidence score.
5. Above threshold → auto-accept and write to PIMS. Below threshold → human review.

No generation, no reasoning — purely similarity search in semantic vector space.

---

## 4. POC Results

### 4.1 What We Built

An end-to-end prototype of the semantic matching pipeline using real eParts data.

**Step 1 — Built the index.** Loaded all 487 active PIMS attribute names from the production database and embedded them. Used TF-IDF as a stand-in for `all-MiniLM` (no internet access in the environment) — architecture is identical; one line swap to upgrade.

**Step 2 — Simulated supplier input.** Used two real supplier spec sheets the client provided:
- **AIM2** from Automation Components (22 attributes)
- **RCT Flex CT** from Accuenergy (20 attributes)

**Step 3 — Ran the matcher.** Cosine similarity of each supplier attribute against the full PIMS index, top match with threshold-based routing.

**Step 4 — Evaluated accuracy.** Ground truth evaluation using the existing 50,000 labeled product attribute values in the database.

### 4.2 Numbers

| Metric | Result |
|---|---|
| AIM2 auto-accept rate | 91% (20/22) |
| RCT Flex CT auto-accept rate | 80% (16/20) |
| **Overall auto-accept rate** | **86% (36/42)** |
| Ground truth top-1 accuracy | 99.1% |
| Ground truth top-3 accuracy | 100% |

### 4.3 Honest Caveats

- **Auto-accept rate ≠ accuracy.** A few wrong matches passed the threshold because TF-IDF rewards shared words regardless of meaning (e.g., "Supply Current" → `SUPPLY VOLTAGE` with score 0.468 because both contain "Supply"). `all-MiniLM` should handle this better.
- **The 0.85 threshold is arbitrary.** No statistical basis yet.
- **No human-labeled cross-supplier ground truth set exists.** Next step is getting Brian's team to label a sample.
- The ground truth eval is self-retrieval against the PIMS index — it proves the pipeline works, not that real-world supplier mappings are solved.

---

## 5. Client Product Architecture

### 5.1 Style: Pipe and Filter

```
Ingestion → Normalization → Prediction → Routing → Review Queue → Writeback → PIMS
```

- Single Azure App Service deployment (not microservices — team size constraint)
- `PredictionServiceInterface` isolates the model from routing and writeback
- Per-attribute routing (not per-record) to minimize review volume

### 5.2 Tech Stack

- Azure App Service (Python backend)
- Azure SQL Database (staging tables, review queue, audit trail)
- Azure Blob Storage (raw file archive)
- Azure Functions (timer-triggered publish/sync job)
- .NET / Vue.js / Nuxt.js (existing eParts stack)
- Datadog (observability)

### 5.3 Open Architectural Decisions (Unresolved)

| ADR | Issue | Status |
|---|---|---|
| ADR-1 | Threshold value (0.85 guess) | Needs calibration against real labeled data |
| ADR-2 | Alpha weighting (0.7 guess) | Needs sweep across correction data |
| ADR-3 | Per-attribute vs per-record routing | Pending attribute correlation analysis |
| ADR-4 | PIMS staging schema compatibility | Jake has not delivered P1-C schema yet |
| ADR-5 | Drift detection baselines | Not yet defined |

---

## 6. Software Engineering System (SES)

We explicitly treat this project as a Software Engineering System — not just a codebase. The SES governs all work: code, meetings, reviews, decisions, and documentation.

**Four pillars:**
- **Artifacts** — what we produce (versioned, reviewable, traceable)
- **Processes** — how artifacts are produced and validated, modeled using ETVX (Entry, Task, Verification, Exit)
- **Resources** — who and what performs the work (humans and AI tools)
- **Measurements** — how we evaluate effectiveness and improve over time

This framing creates accountability not just for the product we ship to eParts, but for how our team operates week to week.

### 6.1 Core Artifacts

- **Context Diagram V2** (approved) — system boundary view
- **Notional Workflow Diagram** (in review) — deliberately labeled "notional," not "architecture," since it will mature with client data
- **ADRs** (ongoing) — every major design decision captured with context, options, decision, rationale. Lifecycle: Draft → Review → Approved → Baselined.

---

## 7. Agentic SE System (Team's Internal Tooling)

This is **separate** from the client product. It is our team's operating system — a multi-agent pipeline that helps Pimsie Supreme execute the capstone better.

### 7.1 Core Philosophy

- Agents handle the mechanical 80%, humans own the judgment 20%
- Every high-risk output (architecture changes, P0 tickets, ADRs) requires human approval
- Low-risk outputs (minutes, digests, alerts) write directly
- All agent outputs are versioned in Bitbucket — git history is the audit trail
- Prompts are version-controlled files, not hardcoded strings
- Bitbucket is the single source of truth; Confluence is the human-readable mirror

### 7.2 Agent Domains

| Agent Group | Purpose |
|---|---|
| **Requirements** | Transcript parser, priority classifier, requirement extractor, stale detector |
| **Architecture** | Drift detector, ADR generator, diagram updater, traceability matrix builder |
| **Coding** | Boilerplate generator, PR reviewer, test generator, doc generator (feasibility: partial — full autonomous coding not yet) |
| **Project Management** | Ticket creator, WBS updater, weekly digest, alert agent |
| **Knowledge** | Minutes publisher, decision logger, prompt regression, context packager |
| **Coach Memory** (eParts-specific) | RAG over past sessions, commitment tracker, briefing generator, concern tracker |
| **ML Decision** (eParts-specific) | Open decision store, evidence accumulator, readiness detector |

### 7.3 How It's Specific to Our Project

The agents are generic in *type* but specific in *context*:
- **Supplier catalog workflow** — an agent pre-populates attribute mapping templates for spec sheets like AIM2/RCT before human review
- **Named ETVX stages** — transcript agent extracts against our defined SES processes, not generic "action items"
- **Named stakeholders** — agents tag commitments by person ("Jake committed to delivering P1-C schema by X")
- **Named open risks** — agents monitor threshold calibration, Jake's schema delivery, alpha validation and flag meeting discussions that touch them
- **Rubric-tied metrics** — agents aggregate prompt count, re-prompt rate, correction volume, time saved for mentor meetings

### 7.4 MCP Servers (Tool Access Layer)

| MCP Server | Tools | Used By |
|---|---|---|
| Jira | create_ticket, update_ticket, get_sprint_state | Requirements, PM agents |
| GitHub/Bitbucket | commit, branch, open_pr, add_pr_comment | All agents writing to repo |
| Confluence | create_page, update_page, get_page | Knowledge, Architecture agents |
| Slack | send_message, read_channel, pin_message | Alert, Digest, Coach Memory agents |
| Google Drive | list_files, read_file, watch_folder | Transcript parser, Notes agent |
| Anthropic API | claude_completion | All agents for LLM calls |
| Vector Store | embed, query, upsert, delete | Coach Memory, ML Decision agents |

No agent has hardcoded credentials or makes direct HTTP calls.

### 7.5 Infrastructure Stack

- **FastAPI** — orchestrator server, webhook endpoints, cron scheduler
- **Python** — all agent logic
- **SQLite → Azure SQL** — task queue, session memory, ML decision log
- **ChromaDB** — local vector store for RAG (swappable to Azure AI Search)
- **Bitbucket API / GitHub API** — repo reads and writes
- **Anthropic SDK** — all Claude calls

### 7.6 Repo Skeleton

```
eparts-agentic/
├── orchestrator/
│   ├── main.py          # FastAPI app, webhook endpoints
│   ├── queue.py         # task queue, sequential execution
│   └── router.py        # trigger → agent routing
├── agents/
│   ├── base.py          # base agent class
│   ├── requirements/
│   ├── architecture/
│   ├── coding/
│   ├── project_mgmt/
│   ├── knowledge/
│   ├── coach_memory/    # eParts-specific
│   └── ml_decision/     # eParts-specific
├── mcp/
│   ├── jira.py
│   ├── slack.py
│   ├── bitbucket.py
│   └── drive.py
├── memory/
│   ├── vector_store.py  # ChromaDB wrapper
│   └── decision_log.py  # ML decision state
├── prompts/             # version-controlled prompts
├── tests/
│   └── golden/
├── .env.example
└── README.md
```

---

## 8. Current Open Challenges

1. **Baseline measurement.** No production traffic yet, so establishing a meaningful baseline for human review time and effort is hard.
2. **Confidence threshold governance.** Calibration on a validation set vs. empirical reviewer feedback — unresolved.
3. **Train/serve consistency.** TF-IDF POC vs. all-MiniLM production — need to verify equivalent behavior post-swap.
4. **PIMS staging schema.** Waiting on Jake's P1-C schema delivery.
5. **Correction-to-retraining pipeline.** Architecturally unspecified — how corrections by Brian/Dewey flow back into model improvement.
6. **Drift detection baselines.** Not yet defined for supplier-specific drift.

---

## 9. Key Questions for Mentor Discussions

- How to establish a meaningful baseline for human review time without production traffic?
- Calibration on a validation set vs. empirical threshold tuning — which approach?
- Temporal vs. random test-set splitting for product catalog data where suppliers repeat?
- Top three operational metrics to instrument in the first vertical slice?
- Patterns for capturing reviewer corrections as retraining labels without over-engineering the feedback loop?

---

## 10. Evaluation & Measurement

Per the rubric, 50% weights the strength of the SES. Our measurement plan tracks:
- Prompt count and re-prompt rate
- Correction volume and pattern
- Time saved on recurring tasks (minutes, digests, ADRs)
- AI effectiveness metrics (not just product metrics)
- ETVX compliance per process

This directly aligns with Christian's core focus: measuring AI effectiveness — productivity, quality, and impact — with clear metrics and data collection.

---

*Last updated: April 2026*
