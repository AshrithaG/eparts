# TA Interview — What I Built and What I Learned

So for our capstone at CMU, my team is building an ML-based catalog system for a client. But the part I want to talk about is the engineering system we built around it — a multi-agent framework with 28 agents in 7 pipelines that automates the engineering coordination. Things like turning meeting transcripts into structured requirements, creating tickets, tracking architecture decisions. The reason I'm bringing this up is that building it forced me to work through almost every topic on this course's syllabus, but in a real system with real stakes.

The first real design problem was context. We have multiple client meetings, coach sessions, architecture documents — and any agent that runs needs relevant pieces of all of that. I tried stuffing everything into the prompt early on and it immediately broke down. A single meeting transcript is 8,000 words, and even if it fit the context window, the signal-to-noise ratio is terrible. So we built a retrieval-augmented generation pipeline — ChromaDB as the vector store with ONNX MiniLM-L6 for local embeddings, so there's no API cost for indexing. The design choice that actually mattered was chunking. We don't do fixed-size token windows because our documents have semantic structure — an architecture section on deployment constraints is meaningfully different from one on data flow, and splitting mid-section destroys that. For meeting transcripts, we chunk by speaker turns, because a speaker's continuous thought is the natural unit of meaning in a conversation. That's a small decision, but it directly affects retrieval quality, which directly affects whether the output is grounded or hallucinated.

The next layer is tool usage. We have eight function-calling wrappers around external APIs — Jira, GitHub, Slack, our vector store. The reason we built this abstraction is that it separates reasoning from execution. An agent reasons about what to do, then calls a structured function like `jira.create_issue()` — it doesn't know how Jira's REST API works. This mattered in practice because we swapped our LLM provider midway through the project, from Anthropic to Gemini, and because the reasoning is decoupled from the tools, we didn't change a single line in any agent. That's the kind of separation that sounds like over-engineering until you actually need it.

For memory, we ended up with two systems because they solve different problems. The first is a persistent key-value store we call the wiki — every agent deposits its outputs there, organized by namespace, and any other agent can query it later. So pipeline A running this week can read what pipeline B produced last week. That's the Karpathy pattern — agents building a shared, accumulating knowledge base rather than each starting from scratch. 

The second is a publish-subscribe event bus. When one agent emits an event, any subscribed agent fires automatically. The wiki solves knowledge sharing across time. The event bus solves real-time triggering across pipelines. Together they're what make it a framework instead of isolated scripts.

One thing I underestimated was how much prompt management matters at scale. With 28 agents and five team members, the naive approach is everyone writes their own prompts, and then you get inconsistent outputs and no way to reproduce results. So we built a prompt registry — every prompt is version-controlled with a content hash, an author, a review status. We can pin agents to specific versions, diff changes, and run regression tests against a golden dataset before a new prompt goes live. This connects directly to prompt sensitivity — the same agent with a subtly different prompt produces structurally different outputs. The registry doesn't eliminate that, but it makes it visible and gives you a rollback mechanism.

The alignment piece was more practical than philosophical. The biggest real risk is the model being confidently wrong in a business context. So for high-stakes outputs — things that could send the team chasing a phantom emergency — the system holds them for human review instead of acting automatically. Low-cost outputs get auto-created because a wrong one is cheap to fix. The guardrail is calibrated to the actual cost of error, not applied uniformly. We also built offline fallbacks everywhere — if the LLM is down or quota is exhausted, every agent degrades to keyword-based heuristics. Less sophisticated, but the pipeline doesn't break. The system should never be more fragile than not having it.

The last piece is measurement. Every LLM call is metered — tokens, latency, cost. Across 160 runs, we've spent about three cents. The point isn't the absolute number. The point is we have the number. Our coach pushed us hard on this — he said the goal of measurement isn't to measure everything perfectly, it's to reduce uncertainty enough to make a better decision about whether AI is worth using for a given task. And if the measurement itself costs more than the value of knowing, you're doing it wrong. That framing changed how I think about evaluation entirely.

So that's the system. The real engineering wasn't in the agents themselves — it was in the retrieval pipeline, the tool abstraction, the memory architecture, prompt governance, and the guardrails. And working through those gave me hands-on experience with pretty much every major topic this course covers.

---

## Syllabus Connections (my reference — not to say out loud)

| What I built | Course topic |
|---|---|
| ChromaDB + ONNX embeddings + semantic chunking | Week 5: RAG |
| MCP servers (Jira, GitHub function calling) | Week 5: Tool Usage |
| Pipeline executor (sequential agent chains) | Week 6: Task Decomposition |
| Prompt Registry (versioning, regression testing) | Week 2: Prompt Sensitivity + Week 6: Auto-Prompting |
| SharedMemory wiki + EventBus | Week 10: Agents — Memory |
| Human review gates, cost-calibrated guardrails | Week 4: Hallucination + Week 8: Guardrails |
| Cross-pipeline event triggers | Week 11: Multi-Agent Collaboration |
| Offline fallback when LLM unavailable | Week 8: Defensive measures |
| MetricsCollector, counterfactual analysis | Evaluation (throughout course) |

## If Asked Follow-Ups

- **"Chunking strategy?"** — Semantic sections for docs, speaker turns for meetings. Not fixed windows. Reason: retrieval precision drops when chunks cross topic boundaries.
- **"How do agents communicate?"** — Two mechanisms: persistent wiki (read/write) and event bus (pub-sub triggers). No direct agent-to-agent calls — avoids tight coupling.
- **"Cost?"** — 6,500 tokens across 160 runs = $0.03. Traceability store uses zero LLM tokens — keyword matching over SQLite.
- **"Fine-tuning?"** — None. All prompt engineering with version control and regression tests. Fine-tuning would've locked us to one model at our scale.
- **"Hallucination handling?"** — Structured JSON output with regex fallback parsing. Confidence-calibrated human review. Offline heuristic fallback when LLM fails.
