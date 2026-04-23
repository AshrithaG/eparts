# Why Everything — Decision Rationale for Every Component

> "If it can be done by a human, why? If you're using AI, why? What gains?"
>
> Every component in this system exists because we asked "why" and had an answer
> backed by evidence — not vibes, not "because AI is cool."

---

## The Foundation: Why an Agentic System at All?

**Alternative considered:** Use ChatGPT manually for each task. Copy-paste transcripts,
copy-paste outputs, manually track everything in a spreadsheet.

**Why not:** Manual LLM use is ad-hoc by definition. It has no memory (ChatGPT forgets
your last meeting), no consistency (different prompts every time), no measurement
(how many tokens did that cost?), and no traceability (which version of which prompt
produced that meeting summary 3 weeks ago?).

**Why an agentic system:** It gives us:
1. **Memory** — ChromaDB + SharedMemory wiki remember every meeting, every decision
2. **Consistency** — Prompt Registry ensures everyone uses the same versioned prompt
3. **Measurement** — MetricsCollector tracks every LLM call automatically
4. **Traceability** — every output links to its agent, prompt version, and source data
5. **Scalability** — processing meeting 50 is the same effort as meeting 1

**The test:** If we deleted the system and went back to manual, what would we lose?
- 50 wiki entries of accumulated project knowledge → gone
- 371 embedded coach session chunks for RAG → gone
- 16 auto-populated risk entries → back to a blank spreadsheet
- Cross-pipeline triggers (drift → architecture review) → nobody would remember to check
- Full traceability from requirement to source meeting → trust me, bro

---

## Component-by-Component: The "Why" Behind Everything

### 1. BaseAgent + ETVX Framework

| Question | Answer |
|---|---|
| **What is it?** | Abstract base class all 28 agents inherit from, with ETVX process documentation per activity |
| **Why not just scripts?** | Scripts don't have: structured logging, metrics collection, wiki access, event emission, retry logic, prompt version tracking. BaseAgent provides all of these out of the box. Every new agent gets them for free. |
| **Why ETVX?** | The meta-model requires documented processes. ETVX (Entry/Task/Verification/Exit) is the standard the course uses. But more importantly — ETVX forces us to define *when* an activity starts, *what* it does, *how we verify* it worked, and *what "done" means*. Without that, "the agent ran" tells us nothing. |
| **Evidence** | Every agent run is logged with duration, success, token count, and outputs. 100% pipeline success rate across all test runs. |

### 2. Pipeline Executor (Sequential Agent Chaining)

| Question | Answer |
|---|---|
| **What is it?** | Runs agents in sequence, threading data from one step to the next via PipelineContext |
| **Why sequential, not parallel?** | Data dependency. Step 2 (classify priorities) needs Step 1's output (parsed items). Step 7 (drift detection) needs the meeting content from Step 1 and the architecture from ChromaDB. Parallel execution would require complex synchronization for zero benefit — our steps take <300ms total. |
| **Why not one big prompt?** | Prompt decomposition. One mega-prompt ("parse this transcript AND classify priorities AND extract requirements AND check for drift") would be fragile, untestable, and expensive. Seven small prompts are each independently testable, versionable, and replaceable. If the priority classifier is wrong, we fix one prompt — not a 2000-token monster. |
| **Why 7 steps for requirements?** | Each step maps to a distinct meta-model Activity with its own ETVX, artifacts, and measurements. Fewer steps = activities get conflated. More steps = overhead exceeds value. 7 was determined by the natural process decomposition: parse → classify → extract → create tickets → publish → log decisions → check drift. |

### 3. SharedMemory (The Wiki)

| Question | Answer |
|---|---|
| **What is it?** | SQLite-backed namespaced key-value store all agents read and write |
| **Why not just files?** | Files are dead. You can't query a file system for "all commitments related to data access across 4 coach sessions." The wiki can do that in <1ms. Files also don't have change logs — the wiki tracks every write with who, when, and what changed. |
| **Why not a full database?** | SQLite is the right tool for a 5-person team. Zero config, single file, works everywhere. A Postgres instance would be operational overhead for no benefit at our scale. |
| **Why the Karpathy wiki pattern?** | Karpathy's insight: LLMs are more powerful when they incrementally build structured knowledge, not just respond to isolated prompts. Our agents don't just answer questions — they deposit knowledge. Meeting 10's briefing generator benefits from the accumulated context of meetings 1-9. |
| **Evidence** | 50 entries, 7 namespaces, 112 change log entries. The wiki grows monotonically — every meeting makes the system smarter. |

### 4. EventBus (Cross-Pipeline Communication)

| Question | Answer |
|---|---|
| **What is it?** | Publish-subscribe event system. Agents emit events, pipelines subscribe to event types. |
| **Why not direct function calls?** | If transcript_parser directly calls drift_detector, they're coupled. Changing one requires changing the other. With events, transcript_parser just says "I found drift" — it doesn't know or care who listens. Tomorrow we can add a new subscriber without touching existing code. |
| **Why not a message queue (Kafka/RabbitMQ)?** | 5-person team, local development. SQLite-backed event log is sufficient. The abstraction is the same — upgrading to Kafka later would change the transport, not the API. |
| **Why these specific 10 subscriptions?** | Each maps to a real cross-practice-area dependency: requirements changes MUST trigger architecture review (rubric: "end-to-end connection"). Coach concerns MUST alert PM (risk management). These aren't arbitrary — they're traced to the rubric and meta-model. |
| **Evidence** | 47 events published across 4 types. 10 active subscriptions wiring 6 pipelines together. |

### 5. ChromaDB + Local ONNX Embeddings

| Question | Answer |
|---|---|
| **What is it?** | Vector store for semantic search. 470 chunks across 3 collections (architecture, coach sessions, knowledge base). |
| **Why RAG instead of just passing everything to Claude?** | Context window limits + cost + relevance. A 1-hour transcript is ~15,000 tokens. Embedding it in chunks and retrieving only the relevant 5 chunks saves ~90% of tokens while improving relevance (Claude gets targeted context, not a wall of text). |
| **Why ONNX MiniLM locally, not OpenAI embeddings?** | Embedding is a commodity. MiniLM-L6-v2 produces 384-dim vectors good enough for our retrieval needs (matching meeting chunks, not building a production search engine). Local embeddings cost $0, have zero latency, and work offline. OpenAI embeddings cost $0.0001/1K tokens — small, but adds an API dependency for negligible quality gain at our scale. |
| **Why ChromaDB, not Pinecone/Weaviate?** | Same reasoning as SQLite: zero config, single directory, works everywhere. We don't need multi-tenant search or billion-vector scale. If we did, ChromaDB's API is similar enough to Pinecone that migration is straightforward. |
| **Evidence** | 371 coach session chunks embedded in <5 seconds. Semantic search across all sessions returns relevant results in <50ms. |

### 6. Prompt Registry + Peer Review

| Question | Answer |
|---|---|
| **What is it?** | Version-controlled prompt store with review workflow, regression testing, and A/B testing |
| **Why version-control prompts?** | The meta-model says: "Reusable prompts should be treated as version-controlled artifacts." But more concretely: if the transcript parser suddenly produces worse outputs, we need to know which prompt version caused it. Without versioning, we're debugging in the dark. |
| **Why peer review for prompts?** | Same reason we review code: because the author has blind spots. A "small" prompt change can drastically alter LLM behavior. Hrishik reviewing Ashritha's prompt change catches issues the author didn't test for. |
| **Why temperature=0?** | For deterministic tasks (parsing, classification, extraction), we need the same input to produce the same output. Temperature >0 introduces randomness — meaning Hrishik and Ashritha get different results from the same transcript. That's not engineering, that's gambling. |
| **Why golden test suites?** | Prompt changes without tests are like code changes without tests. Golden tests (known input → expected output) catch regressions automatically. The 10% quality drop threshold is our "build failed" equivalent. |
| **Evidence** | 4 prompts registered, each with content hash. Review workflow demonstrated: Ashritha submits → Hrishik reviews → approved. |

### 7. Risk Register (Auto-Populated)

| Question | Answer |
|---|---|
| **What is it?** | 16 risks auto-populated from architecture report, coach sessions, and meetings |
| **Why auto-populate instead of manual?** | Manual risk registers get stale. Nobody updates them. By pulling risks automatically from real sources (the architecture report literally lists risks in Section 5.4; coach sessions literally raise concerns), the register stays current. |
| **Why link risks to architecture decisions?** | Because a risk without context is useless. RISK-ARCH-01 (threshold miscalibration) links to AD-4 (configurable threshold) and QA-1 (accuracy). When we discuss risk mitigation, we know exactly which architecture decision is affected. |
| **Why severity matrix (likelihood × impact)?** | Standardized prioritization. "Critical" means high likelihood AND high impact (2 risks). "Medium" means one is high, the other low (7 risks). This forces us to distinguish between "likely but low-impact" and "unlikely but catastrophic." |
| **Evidence** | 2 critical, 7 high, 7 medium. Each has mitigation strategy, contingency plan, owner, and linked architecture decisions. |

### 8. Metrics Collector

| Question | Answer |
|---|---|
| **What is it?** | SQLite-backed system that records every LLM call and every agent run |
| **Why measure everything?** | The meta-model says: "Measurement measures Resources, Processes, and Artifacts." You can't improve what you don't measure. More practically: when a professor asks "how do you know AI is helping?", we show numbers — not opinions. |
| **What specifically do we track?** | Per LLM call: tokens in/out, cost, latency, model, prompt version. Per agent run: duration, success, human review flag, correction count. Per pipeline: end-to-end time, step count, events emitted. |
| **Why not just logs?** | Logs are for debugging. Metrics are for decision-making. "The transcript parser used 1,200 tokens at $0.003" is a metric. "2026-04-23 14:40:22 INFO transcript_parser completed" is a log. We need both, but metrics drive the measurement plan. |

### 9. Offline-First Architecture

| Question | Answer |
|---|---|
| **What is it?** | Every agent works without an API key using pattern matching / heuristics. Claude is an upgrade. |
| **Why not just require Claude?** | Three reasons. (1) Demo resilience: the system works in any environment, including a presentation room with bad WiFi. (2) Cost control: offline agents cost $0. (3) Baseline establishment: the offline extraction quality is our baseline. When we add Claude, we measure the IMPROVEMENT. Without a baseline, "Claude is better" is an assertion. With a baseline, it's a fact with a number. |
| **What's the quality tradeoff?** | Offline extraction is structural (regex, speaker turns, keyword matching). It catches explicit action items but misses nuanced ones ("I think we should probably consider..." = implicit action item that Claude would catch). The correction rate (M2) will quantify this gap. |
| **Evidence** | All 7 pipeline steps succeed offline. 57 action items, 18 decisions extracted across 12 meetings without a single API call. |

---

## Non-Ad-Hoc AI Practices — Beyond What Most Teams Do

### Practice 1: Eval-Driven Prompt Development (like TDD for AI)

**Concept:** Write the test BEFORE writing the prompt.

Most teams: write prompt → try it → "looks good" → ship.
Us: define expected output for known inputs → write prompt → run tests → iterate until passing.

This is Test-Driven Development applied to prompts:
1. Take a real VTT transcript
2. Manually identify the correct action items, decisions, attendees
3. Save as golden test case in `/tests/golden/`
4. NOW write the prompt to match
5. Regression tests run on every prompt change

**Why:** Because "looks good" is not a quality measure. A golden test suite is.

### Practice 2: Correction-as-Training-Signal

**Concept:** When a human corrects an agent's output, that correction is captured and used to improve future prompts.

```
Agent output → Human reviews → Correction recorded → 
  → MetricsCollector logs correction type
  → Correction rate per prompt version calculated
  → High correction rate triggers prompt review
  → Corrections become few-shot examples in next prompt version
```

Most teams fix the output and move on. We fix the output AND improve the system.

**Why:** A correction is the most valuable signal about prompt quality. It tells you exactly where the prompt failed and what "correct" looks like. Discarding that signal is engineering malpractice.

### Practice 3: Confidence-Gated Human Review

**Concept:** Not all outputs need human review. Only uncertain ones do.

Our priority classifier already does this:
- P0 items (critical) → mandatory human review
- P1 items (important) → human review recommended
- P2 items (nice-to-have) → auto-processed

This isn't random — it's the same principle as the architecture's confidence-based routing:
high confidence → auto-accept, low confidence → human review queue.

**Why:** Reviewing everything defeats the purpose of automation. Reviewing nothing is dangerous. Confidence-gated review is the efficient middle ground. The architecture report calls this the "accuracy vs throughput tradeoff" (§5.3).

### Practice 4: Prompt Decomposition over Mega-Prompts

**Concept:** Break complex tasks into small, testable, replaceable steps.

Bad (ad-hoc):
```
"Parse this transcript, classify priorities, extract requirements, 
create tickets, check for architecture drift, and publish minutes."
```

Good (principled):
```
Step 1: Parse transcript → structured JSON         (1 prompt, testable)
Step 2: Classify items → P0/P1/P2                   (1 prompt, testable)
Step 3: Extract requirements → REQ-XXX.md           (1 prompt, testable)
Step 4: Create tickets → Jira                        (no LLM needed)
Step 5: Publish minutes → Confluence                 (no LLM needed)
Step 6: Log decisions → wiki                         (no LLM needed)
Step 7: Check drift → architecture comparison        (1 prompt, testable)
```

**Why:** Each small prompt can be independently tested, versioned, and improved. If classification is wrong, you fix one prompt — not a 2000-token mega-prompt where changing one sentence breaks extraction. This is the Single Responsibility Principle applied to prompts.

### Practice 5: Knowledge Accumulation (Not Just Q&A)

**Concept:** Every agent run makes the system smarter. Not by fine-tuning, but by depositing structured knowledge.

Most AI systems are stateless: prompt in, response out, forgotten.
Our system is stateful:

```
Meeting 1 processed → wiki: 3 entries, ChromaDB: 0 coach chunks
Meeting 5 processed → wiki: 15 entries, ChromaDB: 0 coach chunks
+ 4 coach sessions → wiki: 50 entries, ChromaDB: 371 chunks
+ architecture doc → wiki: 55 entries, ChromaDB: 470 chunks
```

The briefing generator for session #5 knows about sessions 1-4. The drift detector checks against the accumulated architecture knowledge. The concern tracker detects patterns across ALL sessions.

**Why:** This is the fundamental difference between "using an LLM" and "building an AI-augmented engineering system." A tool answers questions. A system accumulates intelligence.

### Practice 6: Provenance Chains (Full Audit Trail)

**Concept:** Every artifact can be traced back to its source.

```
Jira ticket PIMSIE-42
  ← created by ticket_creator agent
    ← from P1 action item "integrate Azure blob storage"
      ← classified by priority_classifier (prompt v=5677a0b9)
        ← extracted by transcript_parser (prompt v=3277a42a)
          ← from GMT20260402 client meeting transcript
            ← attended by Hrishik, Ashritha, Jaivard, Arjun
```

**Why:** When a professor asks "where did this requirement come from?", we don't say "someone mentioned it in a meeting." We show the exact provenance chain: which meeting, which speaker, which agent, which prompt version, which pipeline step. That's engineering rigor.

### Practice 7: Process Mining on Agent Logs

**Concept:** Analyze the agent execution logs to find inefficiencies.

Our JSONL audit trail (`pipeline/logs/agent_runs.jsonl`) contains every agent invocation with timing data. We can analyze:
- Which agents are slowest? (optimization targets)
- Which agents fail most? (reliability issues)
- Which agents produce the most human review items? (prompt quality issues)
- Which pipeline steps are most frequently skipped? (maybe they're not needed)

**Why:** The meta-model says "process improvement is reliant on improving AI components." Process mining gives us data-driven improvement targets instead of guessing.

### Practice 8: Semantic Deduplication

**Concept:** Don't process the same information twice.

When a new meeting transcript mentions the same concern that was raised in 3 previous meetings, the concern_tracker doesn't create a new concern — it increments `times_raised` on the existing one. When the same commitment is mentioned again, it updates rather than duplicates.

**Why:** Without deduplication, processing 12 meetings creates 12 separate entries for the same risk. With it, we get 1 entry with 12 supporting references. This is the difference between a data dump and intelligence.

---

## Summary: Ad-Hoc vs Principled

| Dimension | Ad-Hoc (most teams) | Principled (our system) |
|---|---|---|
| **Prompt management** | Copy-paste from ChatGPT history | Version-controlled registry with peer review and regression testing |
| **Consistency** | Everyone uses different prompts | Shared prompt registry, temperature=0, golden tests |
| **Measurement** | "We used AI and it seemed helpful" | 12 GQIM metrics, auto-collected, dashboarded |
| **Memory** | Each conversation starts fresh | 470 ChromaDB chunks + 50 wiki entries + SQLite stores |
| **Cross-practice** | Siloed: requirements team doesn't talk to architecture team's AI | EventBus: 10 subscriptions wiring 6 pipelines together |
| **Quality control** | "Looks good to me" | Regression tests, correction tracking, confidence-gated review |
| **Traceability** | "I think this came from a meeting" | Full provenance chain: artifact → agent → prompt version → source |
| **Cost awareness** | No idea what AI costs | Per-call token tracking, cost per activity, ROI calculation |
| **Improvement** | Fix outputs ad-hoc | Corrections become training signals, process mining on logs |
| **Documentation** | Afterthought | ETVX per activity, auto-generated from system execution |
