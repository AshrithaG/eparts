# eParts SES - The Pitch

> Deliver this as a narrative flow, not a feature list. The audience is intelligent. Don't explain what requirements engineering is. Show them what's different about how you do it.

---

## The Setup (30 seconds)

Our team is building an ML-powered catalog system for eParts. That's the product.

But the product is not what we're presenting today. We're presenting *how we build it* - our Software Engineering System. Specifically, what happens when you take 25 AI agents, connect them through a shared event-driven infrastructure, and point them at the actual engineering overhead of a five-person capstone team.

---

## The Hook (60 seconds)

Here is a recording of our last client meeting. It's a 45-minute .vtt transcript.

I upload it. Within 30 seconds, seven agents execute in sequence:

1. The transcript is parsed into structured data - speakers, decisions, action items, concerns.
2. Every item is priority-classified: P0 (blocks delivery, held for human review), P1 (this sprint), P2 (backlog).
3. Formal requirement documents are synthesized - categorized, with acceptance criteria - and committed to GitHub.
4. Jira tickets are created with auto-populated fields.
5. Meeting minutes are published to Confluence.
6. Decisions are logged to a running decision record.
7. Those decisions are compared against our architecture document using retrieval-augmented generation. If something contradicts what we documented three meetings ago, a drift event fires - and that triggers an entirely separate pipeline.

That last part is the key. These are not seven independent scripts. They are a connected system. The output of one pipeline becomes the input of another through a publish-subscribe event bus. When the requirements pipeline detects drift, the architecture pipeline picks it up and drafts an ADR for the team to review.

---

## What Makes This Different (90 seconds)

Three things separate this from "we used ChatGPT to help with our project."

**First: the agents talk to each other.** Every agent deposits what it learns into a shared memory store - a persistent, namespaced knowledge base we call the project wiki. When the knowledge pipeline runs before our next meeting, it pulls from that wiki, from Jira, from the event bus, and produces a briefing document. Everyone walks into the meeting with the same context. That is not a chatbot. That is institutional memory.

**Second: we measure whether AI actually helps.** Our coach Christian pushed us on this, and he was right. It is not enough to say "AI saved us time." We apply a counterfactual framework: for each task, what would happen if we did not use AI at all? A human takes 2-3 hours to parse a 45-minute meeting and produces inconsistent output. The pipeline takes 30 seconds and produces the same structured format every time. But we also track the review overhead - the 15 minutes a human spends verifying P0 items - because AI is not free. It introduces review cost, rework cost, and token cost. We track all of that.

**Third: we built traceability without spending a single API token.** Our traceability store links concerns to decisions to requirements to risks to Jira tickets to pull requests. That entire matrix is built using structured SQLite queries and domain-aware keyword matching. No LLM calls. The store currently holds 184 artifacts connected by 760 links across 10 relationship types. Zero orphaned artifacts. When someone asks "where did this requirement come from?" we can trace it back to the exact meeting, the exact speaker, and the exact minute of the transcript.

---

## The Design Choices That Matter (60 seconds)

We made three deliberate design choices worth calling out.

**Offline-first.** Every agent has a fallback that works without an LLM. If the API key expires mid-demo, the system degrades gracefully to pattern matching and keyword heuristics. We chose this because a capstone team cannot depend on API availability for their engineering process.

**Human-in-the-loop, not human-out-of-the-loop.** P0 items are held for human approval. ADRs are submitted as pull requests, not auto-merged. The system augments the team's judgment; it does not replace it.

**Prompt governance.** We version-control every prompt in a centralized registry with hash-based versioning, a peer review workflow, and regression testing against golden datasets. When someone on the team changes a prompt, we can measure whether the output got better or worse. This is how you operate AI systematically across a five-person team where everyone uses the same model but could get different results.

---

## The Honest Part (30 seconds)

Not everything is live. Three of our seven pipelines are fully operational - requirements, coach session memory, and knowledge. Two are partially working - architecture and project management. Two are designed but not yet developed - coding and ML decision. We are transparent about this because the value of the system is not that everything is finished. The value is that the infrastructure is in place: the event bus, the shared memory, the traceability store, the prompt registry. When we start the coding phase next sprint, the coding pipeline plugs into the same architecture. Nothing breaks. Nothing gets rebuilt.

---

## The Close (15 seconds)

We did not build a tool. We built an engineering system - one where a single meeting transcript triggers a chain of agents that produce requirements, tickets, minutes, decisions, drift reports, and traceability links, all connected through shared memory and events.

The question we kept asking ourselves was not "can AI do this?" It was "should AI do this, and is the result worth the cost of verifying it?" For the tasks we chose, the answer is yes - and we have the numbers to show it.

---

## Timing Guide

| Section | Duration | Purpose |
|---|---|---|
| The Setup | 30 sec | Frame the distinction: product vs. engineering system |
| The Hook | 60 sec | Live walkthrough of one transcript triggering 7 agents |
| What Makes This Different | 90 sec | Three selling points: connected agents, counterfactual measurement, zero-token traceability |
| Design Choices | 60 sec | Offline-first, HITL gates, prompt governance |
| The Honest Part | 30 sec | Transparency about what's live vs. planned |
| The Close | 15 sec | Restate the core thesis |
| **Total** | **~5 min** | |

---

## Anticipated Questions and One-Line Answers

**"Why not just use ChatGPT directly?"**
ChatGPT is a tool. This is a system. The difference is shared memory, cross-pipeline events, traceability, and prompt governance. A tool gives you an answer. A system gives you accountability.

**"How do you know the AI output is correct?"**
We don't assume it is. P0 items require human approval. We track ticket retention rate (created vs. deleted by humans), drift detection precision, and P0 override rate.

**"Is this over-engineered for a capstone?"**
The infrastructure serves the actual project. Every meeting we have with the client runs through this pipeline. The Jira board is populated by it. The decision log is maintained by it. This is not a demo - it is the team's operating process.

**"What would you do differently?"**
Start the measurement framework earlier. We built the counterfactual analysis after Christian's feedback. If we had it from sprint one, we would have better longitudinal data on AI effectiveness.

**"How does this scale beyond your team?"**
Every component is modular. A new pipeline is a list of agents in a config file. A new MCP server is a class with three methods. The event bus and shared memory are pipeline-agnostic. Adding a "deployment pipeline" or a "security review pipeline" follows the same pattern.
