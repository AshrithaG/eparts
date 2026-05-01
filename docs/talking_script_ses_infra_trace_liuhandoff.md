# Talking script — SES landing · trace weave · REQ-001 → Liu (~4 minutes total)

Use this flow when you stay high-level first, then SES Traceability, then **`traceability_story.html`** REQ-001, then hand **SDLC choice** depth to **Liu**.

Tone: conversational. Skip acronyms unless someone asks—you can say **“saved runs”**, **“one shared pool of agents”**, **“memory that survives the chat”**.

**Screens (suggested):** `interactive_architecture.html` → `ses_traceability.html` → `traceability_story.html`.

---

## Part 1 — What SES is showing you (~2 minutes)

“On this SES landing view you’re basically seeing three layers knitted together—not three products.

**First, pipelines.** We don’t freestyle every week off a blank slate. Capstone automation is spelled out as a small set of **named flows**. Each flow is **steps in a fixed order**: meeting ingest, architectural follow-up, knowledge pull, coding checks—whatever slice we wired for SES. Same pattern everywhere: steps run **one after another**.

**Second, agents—think “functions,” not mascots.** We keep **one pool** of ~twenty-eight agent roles registered once. Different pipelines pick different subsets and order them. Nobody’s copy-pasting a new script each time—the **hierarchy is simple**: **pipelines sit on top**, **steps are slots in order**, **agents are the reusable workers** plugged into those slots.

**Third, harness—two halves of one idea.**  

- **Engineering harness** answers: **what does “done” look like per practice for us?** It’s commits, requirement files in Git, DB rows someone can audit, gates we agreed on—not vibes.  

- **Agentic harness** answers: **how does the machinery actually march?** The baton passes **within a single run**: each step hands forward **named blobs** so the next step reads what yesterday’s chunk produced. Steps can politely **skip** if there’s nothing to act on—they don’t have to wedge errors.

That’s wired to **Shared Memory** separately: shorter-lived run data resets when that run finishes, but Shared Memory lives in SQLite and **keeps stacking** credible project state—the next transcript or webhook **starts richer** instead of pretending the room has amnesia.  

**Infrastructure on this slide** is just honesty in one frame: triggers land the same shape, routing picks **which pipeline** to run, and we name the **three little databases that matter—shared memory for durable context, events for subscribers, traceability for the relationship graph.** Plus the integrations we aren’t pretending we skipped.

So in one breath: **ordered pipelines**, **reuse agent roster**, **two harness halves**, **SQLite memory that accrues**—that’s SES before we talk product math.”  

**[pause, breathe]**

---

## Part 2 — We weave that into one trace matrix (~45–55 seconds)

“Separately from ‘how jobs run,’ we maintain **how everything talks to everything else.**

SES Traceability—you can open **`ses_traceability.html`**—is the **generic picture**: artifacts as boxes, arrows as commitment types across the life of the program. **[pause]**  

The **idea** is boring on purpose **in a good way**: **one matrix** stitches **meetings**, **things we surfaced as concerns**, **requirements**, **architecture decisions**, **risks**, and **tracked work**. You don’t reconcile five slide decks—we already recorded **typed links**.”  

**[flip to REQ example when ready]**

---

## Part 3 — REQ-001 in one minute (IDs, commits, why bother) → Liu

“**`traceability_story.html`** unfolds **REQ-001** from the same graph the dashboards use—**two real branches**: standards-mapping on one limb, extraction and ML-confidence on another—meetings feeding concerns feeding follow-on requirements, architectures, and risks—all **labeled with stable IDs.**  

Those codes aren’t garnish: **`REQ-XXX` mirrors Markdown in-repo**, **`ARCH-XXX` anchors ADR-aligned intent**, **`CON-`** is what someone actually said bothered them, **`DEC-`** is what we pinned as a stance, **`RIS-`** is explicit risk—we can diff them, ticket off them, and **commit** deltas so auditors see **intent + provenance**.  

Why keep this? Sponsor gets **one storyline** spanning voice → spec → mitigation → backlog without archaeology.  

**I'm going to pause on SDLC theology here—handing narrative choice and trade depth to Liu, who will walk our SDLC choice next.** ”

---

## Ultra-tight cheatsheet (~20 seconds whisper)

| Beat | Said simply |
|------|----------------|
| Pipelines | Few named flows, steps ordered, repeatable. |
| Agents | Shared pool; pipelines pick who runs when. |
| Harnesses | “What we owe in writing” + “how computers stage the work.” |
| Shared Memory | SQLite store that piles up credible context across triggers. |
| Infra slide | Incoming trigger → routing → pipeline run → databases + integrations named. |
| Trace matrix | One linked map of conversation → commitments → architecture → risk → work. |
| REQ-001 | Same IDs hit Git/trace export; REQ-001 is the worked example slide. |

---

_Timing hint: Parts 1–3 land ~4 min; shorten Part 1 by tightening the infra sentence if Liu needs slack._
