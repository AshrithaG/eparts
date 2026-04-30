# Talking script — SES dashboard (6 minutes, technical, no clicks)

**Context:** Agenda **02 — SES + SDLC**. Hand off to **Agenda 03 — Requirements** when you pivot to trace.  
**Screens:** **`interactive_architecture.html`** first, then **`traceability_story.html`** (tab change only).  
**Timing:** Aim **~6 minutes** of talk; cheatsheet ~15 seconds at end. Short sentences; **[pause]** = breath.  
**Trim if needed:** drop the chips sentence in §3, or shorten §4 branches line.

Plain-language focus: **engineering harness** vs **agentic harness**, **Shared Memory** vs per-run baton, **pipeline → ordered steps → shared agent catalog**, threaded execution—no tour of individual agent class names.

---

## 0. Agenda hook (~20 s)

“**Agenda item two** is the **SDLC story**: **SES** runs on **checked-in pipelines** and on **state that survives the chat**—not ask-once tooling. **[pause]**  

I’ll do **four beats**: **engineering harness** versus **agentic harness**, **Shared Memory** that keeps adding up, what the **infra page** is listing, then **REQ-001** on **`traceability_story`** to tee up requirements.”

---

## 1. Engineering harness versus agentic harness (~75 s)

“The **engineering harness** is our agreement about **what each practice owes in hard form**. **[pause]**  

A **pipeline** is a **named flow**. Inside it you have **steps in order**, and honest delivery means each step is meant to drop something reviewers can touch—**commits**, **database rows**, **tickets**, **publishes**—not just a narrative. **[pause]**  

The **agentic harness** is **how those steps actually run**: **agents** live in **one catalog**, **pipelines** hang together **only** the combinations you registered, and one small **executor** walks the **list step by step**. **[pause]**  

At run time each step inherits a **flat bag** of results from above: upstream **writes keys**, downstream **reads keys**. Steps can **bypass themselves** when a key is missing so the pipeline does not stall. **Same agent type** can repeat in several pipelines—we are **not cloning code** for each flow. **[pause]**  

One line takeaway: **harness one** is **commitments and exits**; **harness two** is **orderly execution and passing the baton** so it behaves like shipped software flows, not like **one mega-prompt** crossing fingers on memory.”

---

## 2. Shared Memory (~55 s)

“The **per-run baton** differs from **Shared Memory**—the baton **resets when that run completes**; **Shared Memory stays in SQLite** and **keeps growing** across triggers and sessions when we write namespaces on purpose there. **[pause]**  

So the Tuesday meeting run can stash parsed decisions, the Wednesday follow-up picks them up without retyping the story, telemetry and trace rows can converge on dashboards from the **exported graph**. **[pause]**  

Separate **events SQLite** lets **listeners react** later. **MCP-style** calls to **Jira** or **Git** plug in only where steps say they should. Throughout, the repeatable cord is **pipelines plus memory that piles up** honestly instead of living in **the last transcript alone**.”

---

## 3. Infra board (~50 s)

“**`interactive_architecture.html`** reads like a **parts list on one screen**: triggers in, routed pipelines out, persistence spelled out. **[pause]**  

Whatever the source—a **transcript ingest**, **cron**, **Git hook**—you **normalize** to **trigger type** plus **payload**, **routing picks pipeline**, **executor** runs step order you already learned. **[pause]**  

You’ll see **distinct pipelines** pulling from the **same twenty-eight agent registrations**; stripe colors mean **deployment readiness for demos** not product judgment. **Chips** call out **prompts**, **risks**, **ancillary stores**—we put them where **we hide nothing on purpose**.”

---

## 4. Traceability landing (~55 s)

“**`traceability_story.html`** is **REQ-001** as a **fold-out tree**—the **same traced graph** as dashboards, **indented for narration**. **Standards branch** and **extraction branch** mirror how ingest linked **meeting**, **architectures**, **concerns**, **decisions**, **offspring requirements**, and **risks**—**IDs line up** with **`traceability.db`** or the bundled **`traceability_data.json`** the dashboards load. **[pause]**  

For a **diagram first**, open **SES Traceability**—that’s **`ses_traceability.html`**, the SES-wide schematic before you drop into **`traceability_diagram.html`**, which also carries the REQ-001 plus concept panels for slides. **Intelligence** tab holds **full tables same dataset** if auditors ask. **[pause]**  

That primes **Agenda three**—**REQ Markdown in-repo** plus **trace edges**, not orphaned backlog blurbs.”

---

## 5. Close (~18 s)

“What’s distinct here packaged is **ordered automation**, **SQLite memory and trace** that outlast chats, **typed links** you can traverse. Rolling into **Agenda three** opens the **REQ language** itself—not only the topology.”

---

## Cheatsheet (~15 seconds)

| Label | Plain meaning |
|------|----------------|
| Engineering harness | Definition of outputs and gates per practice; pipelines as inspectable promises. |
| Agentic harness | Registry-backed agents, executor order, keyed hand-offs inside one run. |
| Shared Memory (+ events SQLite) | Long-lived keyed store; successive runs accumulate. |
| Infra slide | Trigger → router → pipeline → SQLite (+ optional MCP), agent reuse. |
| SES Traceability | **`ses_traceability.html`**—generic SES trace schematic (palette / legend on page). |
| REQ-001 tree | **`traceability_story.html`**—export-accurate fold-out; doorway into REQ docs + trace-backed stories. |
