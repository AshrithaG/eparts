# eParts Software Engineering System — Assessment & Measurement Plan

## Part 1: Rubric Self-Assessment

### Criterion 1: Viability of Project and Risk Management (3 pts)

| Requirement | What We Have | Status |
|---|---|---|
| Project plan to end of year | Two-iteration lifecycle (Prototype → Pilot), WBS auto-generated from meetings | ✅ |
| Key risks and mitigation | Risk Register: 16 risks auto-populated from arch report + 4 coach sessions + meetings. 2 critical, 7 high, 7 medium. Each has mitigation + contingency. | ✅ |
| Team roles and responsibilities | SES: Jai, Hrishik, Ashritha. Software System: Arjun, Liu. Roles mapped to pipeline ownership. | ✅ |
| Measurement plan | See Part 2 below — GQIM-based, 4 goals, 12 metrics, all auto-collected | ✅ |
| Resources to implement | See Part 3 below — every activity classified auton/assist/human with justification | ✅ |
| Tracking | MetricsCollector (SQLite): per-LLM-call and per-agent-run metrics. Risk register updated by agents. Commitment tracker from coach sessions. | ✅ |

### Criterion 2: Soundness of Software System Definition (5 pts)
*Arjun/Liu section — architecture report covers this*

| Requirement | Status |
|---|---|
| Goals, requirements, priorities | Architecture report §2: FRs, QAs, priority matrix |
| Quality attributes | 5 QAs with scenarios + utility tree (H/H, H/M, M/M, M/L, H/H) |
| Constraints | 7 constraints with sources and architectural impact |
| Context diagram | System boundary defined §1.3; C&C view §3.3.1 |
| Architectural drivers, tradeoffs | 3 tradeoffs analyzed §5.3 (accuracy vs throughput, simplicity vs modifiability, explainability vs sophistication) |
| Decisions | ADR-1 + 5 ADs with status, rationale, and reconsideration triggers |

### Criterion 3: Strength of Engineering System — DECISION QUALITY (5 pts)

| Requirement | How We Meet It |
|---|---|
| 1. Clear decisions | Every activity has explicit resource allocation (auton/assist/human). SDLC choice documented with rationale. Each agent has a defined ETVX process. |
| 2. Strong justification with evidence | See Part 4: Human-vs-AI Comparison Matrix. Each AI use is justified with measurable cost, time, and quality data. |
| 3. Tradeoffs explained | See Part 5: AI Use Tradeoff Register. Every decision to use/not-use AI has explicit gains, risks, and conditions for reversal. |
| 4. Consistent reasoning | Single framework (meta-model) applied uniformly: Artifacts → Processes → Resources → Measurements for all 28 agent activities. |

### Criterion 4: Strength of Engineering System — ELEMENTS (5 pts)

| Element | What We Have | Count |
|---|---|---|
| **Processes** | 7 pipelines, 28 agent activities, each with ETVX documentation | 28 |
| **Key artifacts** | VTT transcripts, parsed minutes, REQ docs, ADRs, risk register, meeting wiki, decision log, drift reports, prompt versions, metrics DB | 12 types |
| **Measurements** | 12 metrics across 4 GQIM goals (see Part 2). Auto-collected by MetricsCollector on every LLM call and agent run. | 12 |
| **Resources** | 28 agents (auton), Claude API (assist), 5 humans, 8 MCP server integrations, ChromaDB, SQLite | mapped per activity |

### Criterion 5: Crit Performance (2 pts)

| Requirement | Strategy |
|---|---|
| Effective communication | Visual-first: knowledge graph, goal model, WBS, agent flow diagram, traceability matrix |
| Deep, thoughtful reflection | Part 5 (tradeoff register) + Part 6 (lessons learned) |
| Actively engaged with feedback | Coach session memory tracks all commitments and concerns; briefing generator prepares for each session |
| Balanced participation | SES owned by Jai/Hrishik/Ashritha; Software System by Arjun/Liu |

---

## Part 2: Measurement Plan (GQIM)

The meta-model says: "Use GQIM. LLM-related measurements will be very helpful as an indicator of system performance."

### Goal 1: Validate that AI improves engineering productivity

| Question | Indicator | Metric | Collection Method |
|---|---|---|---|
| How much manual effort does AI save per meeting? | Time comparison: manual minutes vs agent-generated | **M1: Minutes per meeting transcript processed** — manual baseline ~45 min, agent target <1 min | Timer in pipeline executor |
| How accurate is AI extraction vs human? | Agreement rate between agent output and human review | **M2: Human correction rate** — % of agent outputs that require human editing | `record_human_correction()` API |
| What does AI cost vs human cost? | Dollar comparison per activity | **M3: Cost per activity** — LLM tokens × price vs estimated human hourly cost | MetricsCollector tracks tokens + cost per call |

### Goal 2: Ensure AI quality doesn't degrade over time

| Question | Indicator | Metric | Collection Method |
|---|---|---|---|
| Are prompts getting better or worse? | Regression test pass rate across prompt versions | **M4: Prompt regression score** — golden test score per prompt version | `prompt_regression.py` runs on every prompt change |
| How often do we reprompt? | Reprompting frequency by task type | **M5: Reprompt rate** — LLM calls per agent run (>1 means retries/reprompts) | `_run_llm_calls` counter in BaseAgent |
| Is the knowledge base growing? | Wiki entries over time | **M6: Knowledge accumulation rate** — new wiki entries per week | SharedMemory change log timestamps |

### Goal 3: Measure engineering system effectiveness

| Question | Indicator | Metric | Collection Method |
|---|---|---|---|
| Are pipelines completing successfully? | End-to-end success rate | **M7: Pipeline success rate** — % of pipeline runs where all required steps succeed | PipelineResult in metrics DB |
| Are agents triggering the right cross-pipeline actions? | Event emission and consumption | **M8: Event utilization** — % of events that trigger at least one downstream action | EventBus consumed_by tracking |
| Are risks being mitigated? | Risk status changes over time | **M9: Risk mitigation velocity** — risks moving from open → mitigating → closed per week | Risk register status history |

### Goal 4: Justify AI use with cost-benefit evidence

| Question | Indicator | Metric | Collection Method |
|---|---|---|---|
| What is the total AI spend? | Cumulative token cost | **M10: Total LLM cost (USD)** — sum of all API calls | MetricsCollector `llm_calls` table |
| What is the human time saved? | Estimated hours saved | **M11: Hours saved** — (manual baseline per activity) × (activities automated) | Manual baseline × pipeline run count |
| What is the ROI? | Cost saved vs cost spent | **M12: AI ROI** — (M11 × hourly rate) / (M10 + infrastructure cost) | Computed weekly |

### Baseline Collection Schedule

| Interval | What | Why |
|---|---|---|
| Per LLM call | Tokens, latency, cost, model, prompt version | Granular cost tracking |
| Per agent run | Duration, success, outputs, human review flag | Activity-level effectiveness |
| Per pipeline run | End-to-end duration, steps completed, events emitted | Process-level health |
| Weekly | Aggregate dashboard refresh, risk review, metric trends | Management-level visibility |

### Current Measured State (as of April 2026)

| Metric | Current Value | Interpretation |
|---|---|---|
| M1: Processing time per transcript | <1 sec (offline) | 2700× faster than manual (~45 min) |
| M2: Human correction rate | Not yet measured | Need human review sessions to establish |
| M3: Cost per activity | $0 (offline mode) | Will measure when Claude API enabled |
| M5: Reprompt rate | 1.0 (no retries) | Offline agents don't need retries |
| M6: Knowledge accumulation | 50 wiki entries from 12 meetings + 4 coach sessions | ~3 entries per meeting processed |
| M7: Pipeline success rate | 100% (all runs succeeded) | 7/7 steps, 6/6 steps consistently |
| M8: Event utilization | 47 events published | 10 active cross-pipeline subscriptions |
| M9: Risk mitigation | 2/16 in "mitigating" status | 14 still "open" — need action |

---

## Part 3: Resource Allocation — AI Use/Non-Use Justification

The meta-model says: "Use and non-use of AI should be justified with evidence."

The professors want to see REASONING, not just "we used AI because it's cool."
Here is our principled classification for every activity:

### Why Not Just Have Humans Do Everything?

A human *can* do everything an agent does. The question isn't capability — it's **cost, consistency, and scalability**:

| Factor | Human | Agent | Winner |
|---|---|---|---|
| Parse a 1-hour VTT transcript into structured minutes | ~45 min, varies by person | <1 sec, deterministic format | Agent (2700× faster) |
| Classify 10 action items by priority | ~10 min, subjective disagreements | <1 sec, consistent heuristics | Agent for draft, human for P0 review |
| Check meeting against architecture for contradictions | ~30 min, requires reading entire arch doc | <1 sec, queries 31 ChromaDB chunks | Agent (can check every meeting, human can't) |
| Track commitments across 4 coach sessions | Manual spreadsheet, things get lost | Automatic, persistent, queryable | Agent (zero commitment tracking overhead) |
| Detect recurring concerns across sessions | Requires re-reading all session notes | Pattern matching across SQLite, 371 ChromaDB chunks | Agent (impossible to do reliably by hand) |
| Generate pre-meeting briefing with context | ~20 min gathering notes from past meetings | <1 sec, pulls from wiki + ChromaDB | Agent (ensures no context is forgotten) |

### Why Not Have AI Do Everything?

Because AI **lacks judgment** on things that matter most:

| Activity | Why Human, Not AI | Evidence |
|---|---|---|
| P0 requirement approval | Business impact of wrong priority is high. Agent doesn't know client politics. | Architecture report §5.3: "incorrect data causes wrong parts ordered" |
| ADR approval | Architectural decisions have long-term consequences. AI can draft, human must judge tradeoffs in context. | ADR-1 is "Tentative" precisely because empirical validation is needed |
| Threshold calibration | Most sensitive parameter in the system. Small tuning errors have outsized effects. | RISK-ARCH-01 (critical): "0.85 is unsupported by empirical data" |
| Coach session interpretation | Nuance in coach feedback requires understanding the relationship and history | Christian's session: measurement validity concerns are contextual to CMU expectations |
| Risk mitigation decisions | Accepting risk vs mitigating it is a project management judgment call | RISK-ARCH-06: Catalog team capacity is a business decision |

### Per-Activity Resource Classification

| Activity | Resource | Why This Classification |
|---|---|---|
| **Transcript parsing** | `auton` | Structural extraction is deterministic. VTT format is fixed. No judgment needed for extraction. |
| **Priority classification** | `auton` → `human` (P0 only) | Agent draft is fast + consistent. But P0 items (business-critical) must be human-verified because wrong priority = wrong resource allocation. |
| **Requirement extraction** | `auton` | Template-filling from classified items. Format is standardized. |
| **Ticket creation** | `auton` | Mechanical: item → Jira ticket. Agent adds `ai-generated` label so humans can filter. |
| **Architecture drift detection** | `auton` | Checking 31 architecture chunks against every meeting is infeasible by hand. Agent queries ChromaDB in <1 sec. Human reviews only flagged drifts. |
| **Coach session embedding** | `auton` | Chunking + embedding is mechanical. 371 chunks across 4 sessions — no human would do this manually. |
| **Commitment tracking** | `auton` | Pattern extraction from text. Persistent storage in SQLite. Human reviews commitment status weekly. |
| **Concern pattern detection** | `auton` | Cross-session analysis requires querying all past sessions. Agent detects recurring themes; human decides action. |
| **Pre-meeting briefing** | `auton` → `human` review | Agent gathers context from wiki + ChromaDB. Human reviews briefing before meeting to add judgment. |
| **ADR generation** | `assist` → `human` approval | AI drafts ADR from meeting discussions. Human architect approves because ADRs are binding decisions. |
| **Prompt regression testing** | `auton` | Automated: run golden tests against new prompt versions. No human judgment needed for pass/fail. |
| **Weekly digest** | `auton` → `human` review | Agent aggregates metrics, decisions, risks. Human reviews before sending to team. |
| **Threshold tuning** | `human` (AI provides data) | The system provides precision-recall curves and confidence distributions. Human makes the final call because threshold = accuracy vs throughput tradeoff. |
| **Risk register updates** | `auton` seeding → `human` status changes | Agent populates from sources. Human updates status because risk acceptance is a judgment call. |

---

## Part 4: Human vs AI Comparison — Evidence Table

This is the table to show the professors. For each activity, what happens manually vs with the agent:

| Activity | Manual (Human) | Automated (Agent) | Gain | Evidence |
|---|---|---|---|---|
| Parse 1 meeting transcript | 45 min, inconsistent format, misses items | <1 sec, consistent JSON, extracts all speaker turns | **2700× faster**, zero format variance | Pipeline logs: 7 steps in <300ms |
| Classify 10 items by priority | 10 min, subjective, team disagrees | <1 sec, consistent heuristic | **600× faster**, eliminates subjectivity (but needs human P0 review) | Classifier output: 0 P0, 1 P1, 9 P2 consistently |
| Check meeting vs architecture | 30 min per meeting, requires reading entire 406-line arch doc | <1 sec, queries 31 ChromaDB chunks, checks against 6 ADRs + 7 constraints | **Checks every meeting automatically** — human would skip most | drift_detector runs on every pipeline execution |
| Track commitments across 4 sessions | Manual spreadsheet, updated sporadically | Automatic: 31 commitments tracked in SQLite, queryable | **Zero tracking overhead**, nothing forgotten | coach_sessions.db: 31 commitments across 4 sessions |
| Detect recurring concerns | Re-read all session notes, remember patterns | Pattern matching: "general" concern raised 4× across sessions | **Cross-session memory** — impossible to do reliably by hand at scale | concern_tracker found 1 recurring theme ≥2 sessions |
| Generate pre-meeting briefing | 20 min gathering notes, reviewing past sessions | <1 sec, pulls from 371 ChromaDB chunks + wiki + SQLite | **Complete context** — human would inevitably forget something | briefing_generator queries all data sources |
| Maintain decision register | Manual doc, gets stale, items missed | Auto-logged from every meeting, queryable | **Every decision captured**, none lost | wiki: decision entries from all meetings |
| Monitor for scope creep | Relies on team awareness | Agent detects when discussion contradicts constraints | **Continuous monitoring** vs periodic human review | drift_detector checks against 7 architecture constraints |

### What We **Cannot** Automate (and Why)

| Activity | Why Human Required | What AI Provides Instead |
|---|---|---|
| Setting the confidence threshold | Business-critical parameter with cascading effects on accuracy, review volume, and labor savings | Precision-recall curves, confidence distributions, sensitivity analysis — the DATA for the human to decide |
| Deciding whether a risk is acceptable | Risk tolerance is a business judgment, not a technical one | Risk register with severity scores, mitigation options, and links to related architecture decisions |
| Approving an ADR | Architectural decisions bind the team for months. Context matters. | ADR draft with alternatives analysis, traceability to drivers, and evidence from meetings |
| Interpreting coach feedback | Coaches communicate with nuance, context, and relationship history | Structured extraction of commitments, concerns, and decisions — the raw material for human interpretation |
| Choosing between ML approaches | Model selection depends on data volume, accuracy targets, and explainability requirements that evolve | Evidence accumulation dashboard showing POC results, confidence metrics, and readiness scores |

---

## Part 5: AI Use Tradeoff Register

For each significant decision about AI use, the tradeoff and reversal condition:

### Decision 1: Offline-first agents (pattern matching) before Claude API

**Choice:** Agents work offline with regex/heuristics first. Claude is an upgrade, not a dependency.

**Reasoning:** The meta-model says "take some risks, monitor performance, make changes." Starting offline lets us:
- Validate the pipeline architecture independent of LLM quality
- Establish baselines for what structural extraction can achieve
- Measure the DELTA when Claude is added (M2: correction rate improvement)

**Tradeoff:** Offline extraction is less accurate than Claude-powered extraction.
**Gain:** System works without API key, costs $0, and we can measure improvement when Claude is added.
**Reversal condition:** If offline accuracy is sufficient (>80% agreement with human review), Claude may not be worth the cost.

### Decision 2: ChromaDB with local ONNX embeddings, not OpenAI embeddings

**Choice:** Use `ONNXMiniLM_L6_V2` for local embeddings instead of OpenAI/Anthropic embedding APIs.

**Reasoning:** Embedding is a commodity operation. The marginal quality difference between local MiniLM and cloud embeddings doesn't justify the API dependency, cost, and latency for our use case (matching meeting chunks, not precision ranking).

**Tradeoff:** Slightly lower embedding quality (MiniLM-L6 vs text-embedding-3-large).
**Gain:** Zero API cost for embeddings, zero latency, works offline, no auth needed.
**Evidence:** 371 coach session chunks + 31 architecture chunks + 68 knowledge base chunks all indexed locally in <5 seconds.
**Reversal condition:** If semantic search recall drops below acceptable threshold when evaluated against human-curated ground truth.

### Decision 3: Event bus for cross-pipeline communication, not direct function calls

**Choice:** Agents publish events to an EventBus rather than directly calling other pipelines.

**Reasoning:** Direct coupling between pipelines creates a maintenance nightmare. If the requirements pipeline directly calls the architecture pipeline, both must change when either changes. The event bus decouples them: the requirements pipeline publishes "drift_detected" and doesn't care who subscribes.

**Tradeoff:** Indirection adds a layer of complexity. Events can be missed if no subscriber is registered.
**Gain:** Any new pipeline can subscribe to any event without modifying existing code. 10 subscriptions wired with zero cross-pipeline imports.
**Reversal condition:** If the team finds event-based communication too hard to debug, switch to explicit pipeline chaining.

### Decision 4: SharedMemory wiki instead of passing files between agents

**Choice:** Agents deposit structured data into a namespaced SQLite store (the "wiki") instead of writing files that other agents read.

**Reasoning:** This is the Karpathy wiki pattern — the system accumulates intelligence over time. Files are static; a wiki is queryable. An agent can ask "what are all the commitments related to data access?" and get an answer from across all meetings and sessions.

**Tradeoff:** Another database to maintain. Data format must be kept consistent.
**Gain:** 50 wiki entries across 7 namespaces, fully queryable, with 112 change log entries tracking how knowledge evolved. Any agent can search across all project knowledge in <1ms.
**Reversal condition:** If wiki maintenance becomes a burden or data quality degrades, simplify to file-based artifacts.

### Decision 5: Bespoke SDLC, not Scrum

**Choice:** Agent-Augmented Iterative Lifecycle with two iterations, continuous measurement, and pipeline-based practice areas.

**Reasoning:** The meta-model explicitly says "Avoid using a preexisting SDLC pattern (i.e., Scrum, RUP) which are fabricated on the idea of authoring software being the most labor-intensive part." With AI agents, authoring is cheap. The bottleneck is validation, integration, and measurement. Our lifecycle is designed around that reality.

**Tradeoff:** No established ceremony cadence (no sprint planning, no retrospectives).
**Gain:** Continuous measurement replaces periodic retrospectives. Agent pipelines enforce process consistency. Phase gates replace sprint reviews.
**Reversal condition:** If the team struggles without ceremony structure, adopt lightweight standup practices — but keep continuous measurement.

---

## Part 6: What's Missing / Gaps to Close

Being honest about what we haven't done yet:

| Gap | Impact | Plan |
|---|---|---|
| **M2 (Human correction rate) not measured** | Can't prove AI quality without human baseline | Run 3 meetings through pipeline, have team member review outputs, record corrections |
| **Claude API not yet enabled** | All agents running offline — can't show LLM-powered quality difference | Add API key, measure quality delta between offline and Claude-powered extraction |
| **Jira/Bitbucket not connected** | Can't demonstrate real ticket creation or file commits | Provide creds, wire MCP clients, demonstrate end-to-end |
| **Prompt versions not A/B tested** | Meta-model says "A/B test prompts" — we have the framework but no data | Create 2 prompt variants for transcript_parser, run both on same meeting, compare M4 scores |
| **Drift detector hasn't found real drift yet** | Demonstrates capability but not impact | Process a meeting where team discusses something contradicting the architecture (or simulate one) |
| **Risk mitigation tracking is manual** | Agents seed risks but don't auto-update status | Wire agents to update risk status when evidence appears (e.g., data received → RISK-COACH-01 status changes) |

---

## Part 7: Creative Elements — Beyond the Basics

### 7.1 Prompt as First-Class Artifact

The meta-model says: "Reusable prompts should be treated as version-controlled artifacts."

Our system implements this:
- **Prompt files** stored in `/prompts/` with version hashes
- **Prompt regression testing** (`prompt_regression.py`) runs golden tests on every prompt change
- **MetricsCollector** tracks which prompt version was used for every LLM call
- **Prompt performance dashboard** shows accuracy per prompt version over time

This means we can answer: "Did that prompt change make extraction better or worse?" — with data.

### 7.2 Knowledge Accumulation as a Metric

Most teams treat meetings as isolated events. Our system treats them as **incremental knowledge deposits**:

| After Processing | Wiki Entries | ChromaDB Chunks | Events | Risks Tracked |
|---|---|---|---|---|
| 0 meetings | 0 | 0 | 0 | 0 |
| 5 client meetings | 10 | 0 | 20 | 3 |
| + 4 coach sessions | 50 | 371 | 47 | 16 |
| + architecture doc | 55 | 470 | 47 | 16 |

The knowledge base **grows monotonically**. Every meeting makes every future agent smarter. The briefing generator for meeting #10 has context from meetings 1-9 that a human would never fully review.

### 7.3 Decision Provenance Tracking

Every decision in the system has a provenance chain:
```
Raw utterance in meeting → extracted by transcript_parser → classified by priority_classifier
→ logged by decision_logger → deposited in wiki → queryable by drift_detector
→ linked to architecture decisions via traceability
```

A professor can ask: "Where did this requirement come from?" and we can trace it back to the exact meeting, speaker, and timestamp.

### 7.4 Cost Transparency

When Claude API is enabled, every single LLM call records:
- Input tokens, output tokens, total cost
- Which agent, which prompt version, which pipeline
- Aggregated per-agent, per-pipeline, per-day

This lets us answer: "How much does it cost to process one meeting?" and compare it to the human alternative ($50/hr × 45 min = $37.50 per meeting). If the agent costs $0.15 in tokens, that's a **250× cost reduction** — and we have the data to prove it.

### 7.5 The Agentic Patterns We Use (and Don't Use)

The meta-model says: "Be mindful of agentic patterns and know when to use them."

| Pattern | We Use It? | Where / Why Not |
|---|---|---|
| **Sequential Pipeline** | Yes | All 7 pipelines chain agents in sequence with data bridging |
| **Fan-out / Fan-in** | No | Our pipelines are linear; fan-out would add complexity without clear benefit for our data flow |
| **Publish-Subscribe** | Yes | EventBus: 10 cross-pipeline subscriptions. Agents publish, pipelines subscribe. |
| **RAG (Retrieval-Augmented Generation)** | Yes | ChromaDB stores 470 chunks; briefing generator and drift detector query for context |
| **Persistent Memory (Wiki)** | Yes | SharedMemory: 50 entries across 7 namespaces, queryable by all agents |
| **Human-in-the-Loop** | Yes | Phase gates at P0 approval, ADR approval, threshold tuning, risk acceptance |
| **Prompt Versioning + Regression** | Yes | Prompts as files, golden test suite, version tracking in MetricsCollector |
| **Self-improving (fine-tuning on corrections)** | No | Insufficient correction data volume yet. Would require Claude fine-tuning API access. |
| **Multi-model routing** | No | Single model (Claude Sonnet) sufficient. Would add complexity without clear quality gain. |

---

## Part 8: Systematic Team Operation — Solving the Consistency Problem

### The Problem

Five team members, all using LLMs. Even with the same model and the same prompt,
outputs differ because LLMs are probabilistic. Without governance:
- Hrishik's meeting minutes format ≠ Ashritha's format
- A "small prompt tweak" by one person silently degrades quality for everyone
- No one knows which prompt version produced which artifact
- No way to prove quality improved or regressed

### The Solution: Three Layers

#### Layer 1: Prompt Registry (Centralized, Version-Controlled)

Every prompt is a **versioned artifact** in `/prompts/`, tracked in a SQLite registry:

```
/prompts/
├── transcript_parser.txt     ← v=3277a42a (active, reviewed)
├── priority_classifier.txt   ← v=5677a0b9 (active, reviewed)
├── session_extraction.txt    ← v=763d8a27 (active, reviewed)
└── briefing_generator.txt    ← v=e304cdc6 (active, reviewed)
```

- **4 prompts** registered, each with a content hash
- Agents always load from the registry, never from inline strings
- If someone changes a prompt, the old version is preserved and the new one requires review

#### Layer 2: Prompt Peer Review (Like Code Review)

Prompt changes follow a review workflow:

```
Author submits new version → status: pending_review
  → Peer reviews (approve/reject/request_changes)
    → If approved: status: approved → can be activated
    → If rejected: author revises and resubmits
```

**Example from our system:**
1. Ashritha submits new `transcript_parser` v2 (adds priority field to action items)
2. Hrishik reviews: "Good — priority field aligns with classifier downstream" → **approved**
3. Only after approval can the version be activated as the team's canonical prompt

This means no single person can silently change a prompt that affects everyone's outputs.

#### Layer 3: Regression Testing (Golden Test Suites)

Every prompt has golden test cases in `/tests/golden/`:
- Input: a known transcript
- Expected output: the correct extraction result

When a prompt changes, `prompt_regression` agent runs all golden tests and **blocks
the change if quality drops >10%** from baseline. This is the unit test of prompt engineering.

### 10 Team Conventions (Enforced Rules)

| # | Convention | How Enforced |
|---|---|---|
| 1 | All prompts in `/prompts/` as .txt files, never inline | Registry auto-scan detects |
| 2 | Every prompt change requires peer review before activation | Registry review workflow |
| 3 | Temperature=0 for deterministic tasks | BaseAgent default |
| 4 | Every LLM artifact has provenance (agent, prompt version, timestamp, model) | MetricsCollector |
| 5 | HITL required for P0 items and ADRs | Pipeline step config |
| 6 | Golden test cases required for every prompt | Regression agent on PR |
| 7 | Offline-first, Claude as upgrade | BaseAgent fallback pattern |
| 8 | Outputs deposited to wiki, not just files | BaseAgent.wiki |
| 9 | Cross-pipeline events, not direct calls | EventBus |
| 10 | Weekly measurement dashboard review | Team practice |

### Why This Matters

Without these layers, "we used AI" is an anecdote. With them:
- We can prove which prompt version produced which result (traceability)
- We can prove quality didn't degrade when we changed a prompt (regression)
- We can prove all team members used the same prompt (registry)
- We can prove peer review happened (review log)
- We can A/B test prompts with evidence (ab_tests table)

This is the difference between **ad-hoc AI use** and **principled AI use** that the
rubric explicitly asks for.

---

## Part 9: Answers to Likely Professor Questions

**Q: "Everyone's using the same LLM — how do you ensure consistency across team members?"**
A: Three layers. (1) Prompt Registry: every prompt is version-controlled with a content hash. All agents load from the registry, so everyone uses the exact same prompt. (2) Prompt Peer Review: no one can change a prompt unilaterally — it requires approval, just like code review. (3) Temperature=0 for deterministic tasks: we eliminate stochasticity where consistency matters. For the remaining variance, golden test suites catch regressions before they ship.

**Q: "What if someone changes a prompt and it breaks things?"**
A: The prompt regression agent catches it. Every prompt has golden test cases (known input → expected output). When a prompt changes, regression tests run automatically. If quality drops >10% from baseline, the change is blocked. This is literally the same principle as code regression testing, applied to prompts.

**Q: "If a human can do all of this, why build agents?"**
A: A human can write meeting minutes. They can't write them in <1 second, cross-reference against 31 architecture chunks, check for commitment violations across 4 past sessions, and deposit the results into a queryable knowledge base — all simultaneously, for every meeting, consistently. The agent doesn't replace the human. It gives the human superpowers: complete context, zero forgetting, and continuous monitoring.

**Q: "How do you know the AI is actually helping?"**
A: We measure it. M1 (processing time: 2700× faster), M5 (reprompt rate), M7 (pipeline success rate: 100%). When we enable Claude, we'll measure M2 (correction rate) and M3 (cost per activity) to quantify the quality-cost tradeoff. We don't assert "AI helps" — we show the numbers.

**Q: "What happens if the AI is wrong?"**
A: Three safeguards. (1) P0 items always go to human review. (2) Every agent output is logged with provenance — we can audit any decision. (3) Prompt regression testing catches quality degradation before it reaches production. The system is designed to be wrong sometimes and catch it.

**Q: "Why not just use ChatGPT/Copilot?"**
A: ChatGPT is a conversation. Our system is an engineering pipeline. ChatGPT doesn't remember last week's meeting. It doesn't track commitments. It doesn't emit events that trigger other processes. It doesn't maintain a queryable wiki. The value isn't in the LLM — it's in the orchestration, memory, and measurement infrastructure around it.

**Q: "What's your SDLC?"**
A: We designed a bespoke Agent-Augmented Iterative Lifecycle per the meta-model. Not Scrum. Two iterations (prototype → pilot), continuous measurement, pipeline-based practice areas, phase gates for human decisions. Every repeatable activity is automated; every non-repeatable decision is human. The measurement system runs continuously, not retrospectively.
