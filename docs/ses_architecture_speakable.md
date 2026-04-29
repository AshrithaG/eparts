# SES architecture — speakable script (natural language)

Use this when you present the **Software Engineering System** to teammates. Read it almost as-is; breathe at the paragraph breaks. Pause after “So in plain terms” lines.

---

## Opening (about 45 seconds)

Hey — I want to give you a mental model of SES, our **Software Engineering System**, in one go. The main idea is: this is **not** a pile of one-off scripts that someone runs by hand. It’s a **framework**. You’ve got specialized **agents**, wired into **pipelines** that belong to real **practice areas**, like requirements or architecture. Things that happen in the outside world — a meeting transcript lands, a PR opens, a cron fires — we call those **triggers**. Inside, data flows through steps in order, and agents can read and write **shared memory**, raise **events**, and update a **traceability graph**. If you remember only one sentence: **things come in, pipelines run in order, artifacts and links get recorded, and events can fan out to other parts of the system.**

---

## Layer 1 — Something has to start the work (triggers)

So first: **what kicks this off?** In practice it’s things like: we drop a **Zoom-style transcript** — that’s usually a `transcript` trigger. A **pull request** — that’s often a `pr_event`. A **proof-of-concept result** might be `poc_result`. There are also **scheduled** triggers, like Friday evening for project-management digests, or a pre-meeting window for prep. Each of these has a small string label, a **trigger type**, and that label decides which **family of workflows** is even in play.

Takeaway for the room: **nothing magical** — it’s “something external happened, we label it, that label routes the work.”

---

## Layer 2 — Two ways to actually run the workflows (orchestration)

There are **two** execution styles worth naming, because we use both.

**First**, the **live service** path: FastAPI exposes **webhooks**. When the outside world POSTs an event, we don’t block the HTTP call on a half-hour pipeline; we **enqueue** work on a **task queue** and agents pick it up. Good for production-style, async operation.

**Second**, the **demo / batch** path: something like **`demo.py`** runs **one full pipeline** synchronously with a **pipeline executor** — same ordered steps every time, deterministic for a customer demo. That’s why the live demo feels like a script: it’s **explicitly** walking the whole DAG in order.

Say this clearly: **Same building blocks; different shell — async API versus one-shot runner.**

---

## Layer 3 — Pipelines are the spine (what happens inside)

Think of a **pipeline** as a **recipe**: step one, step two, step three. Each step calls **one agent by name**. Output from step one doesn’t vanish; it lands in a **context object** — keyed fields like “parsed minutes,” “classified items,” “requirements.” Step two reads those keys. If a step depends on something being empty — we can **skip** it without failing the whole run. So the system is **honest** about partial data.

Walk them through **one** chain they care about — usually **requirements** on a transcript:

1. **Parse** the transcript into structured minutes — action items, decisions, that kind of thing.  
2. **Classify priority** — what’s urgent versus what can wait.  
3. **Pull out formal requirements** — the REQ-style artifacts.  
4. **Create tickets** where it makes sense — often with human review for the highest risk items.  
5. **Publish minutes** where integrations exist.  
6. **Log decisions** so we have an audit trail.  
7. **Check drift** against the architecture we’ve already agreed on — lightweight sanity check after the meeting.

You can say: **“That’s seven stations on an assembly line — each station is an agent, one after the other.”**

There are **other** pipelines in the framework — coach sessions, heavier architecture work on a PR, coding support on a PR, ML decision evidence, Friday PM rollups, knowledge prep for meetings. Don’t list all seven unless someone asks; the point is **multiple practice areas**, each with its own recipe.

---

## Layer 4 — How pieces talk without being glued together (events)

Agents don’t only hand data to the **next** step. They can **emit events** — publish-and-subscribe style. Example: we noticed **drift** versus the canonical architecture. Something else might care — the **architecture** side of the house, or alerting. Another example: **action items** hit the wire — project management or ticketing might react. Those event names are basically a **contract** between subsystems: **if you emit this, downstream is allowed to subscribe and react.**

In the real implementation, events get **stored** so we can audit what happened and who should have reacted. For demos, handlers often run **in process**; in a bigger deployment you’d picture a **queue** behind that.

Sound bite: **“Pipelines are sequential; events are how the rest of the organism hears about important outcomes.”**

---

## Meta model — how we think about “truth” in the product (about 60 seconds)

Two stores, one story.

**Shared memory** — we sometimes call it the **wiki pattern**. Think namespaced buckets: requirements-ish stuff, decisions, risks, meetings, whatever your agents need to **read before they write the next thing**. Every write can say **which agent** did it, so you’re not blindly trusting a black box.

**Traceability** — think **graph**, not document. There are **artifacts**: a concern, a requirement, a decision, a ticket, a PR, a risk, an ADR — typed nodes. Between them we have **links** with meaning: this concern **became** a requirement; this ticket **implements** a requirement; this decision **mitigates** a risk. That’s how you answer an auditor or a PM who asks: **“Where did this requirement come from, and where did it land in engineering?”** — you follow the chain.

Optional line: we also tag some steps with **process IDs** — ETVX-style — so **process documentation** and **automation** stay aligned.

Closer for this section: **“The wiki is fast context for agents; the traceability store is the evidence graph for humans and compliance.”**

---

## Touching the outside world (MCP)

Agents don’t hallucinate Jira tickets into the void — they go through **integrations**: Jira, GitHub, Confluence, whatever we’ve wired as **MCP clients**. If credentials aren’t there, the code is written to **fail soft**: log it, fall back to heuristics or skip, which is why demos still run on a laptop without every secret.

---

## If someone asks “how do we extend this?”

Short answer: **Register a new agent**, **drop it into a pipeline step** or **trigger route**, and if it should notify other areas, **emit an event** and/or **write traceability**. Four moving parts, same pattern every time.

---

## One-liner endings (pick one)

- **“Triggers in, ordered pipelines, shared wiki, event bus, traceability graph — that’s SES.”**  
- **“It’s connected agents, not lonely scripts.”**  
- **“We can show the live path in the demo, and the architecture doc has the full catalogue when you need to wire something new.”**

---

*Paired with `ses_architecture.md` for diagrams and file references. Synthetic demo content in the repo stays clearly labeled for education.*
