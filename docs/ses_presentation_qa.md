# SES demo — Question & Answer (speaker notes)

Companion to **`talking_script_ses_infra_trace_liuhandoff.*`** / **`talking_script_ses_six_minute.*`**. Answers here stay **short and speakable** for audience Q&A during or after the SES + trace segment. For file-level detail, line references, and deeper pipeline Q&A, see **`presentation_qa.md`** (Sections 1–2, 8).

---

## SES in one sentence

**Q: What is SES?**  
**A:** SES is our **Software Engineering System**—the way we run **ordered automation** (pipelines of steps), **persist what matters** in SQLite and Git, and **link** meetings, requirements, architecture, risks, and backlog in one trace graph so the story does not live only in chat history.

---

## Harnesses, hierarchy, agents (no jargon version)

**Q: Engineering harness vs agentic harness—why two names?**  
**A:** **Engineering harness** is the **agreement on outcomes**: what each practice must leave behind (files in Git, REQ markdown, DB rows, gates like P0 review). **Agentic harness** is the **runtime mechanic**: register agents once, order them in pipelines, pass results step to step, optionally skip if there is nothing to process. Same system—**policy** plus **execution**.

**Q: How do pipelines and agents relate—who’s on top?**  
**A:** **Pipelines** are named flows; **steps** inside a pipeline are ordered slots; **agents** are the reusable implementations plugged into those slots (~28 registered once, combined differently per pipeline). Hierarchy: **pipeline → ordered steps → agent executes step**.

**Q: Why ordered steps instead of “let the model figure it out”?**  
**A:** Order gives **repeatable behavior**, auditable hand-offs, and predictable failure modes. You can explain “step six did not run because step three produced no ticket payload”—harder when everything is one prompt.

**Q: Is SES the same as using ChatGPT as a team assistant?**  
**A:** No—the difference is **persisted state**, **versioned artifacts**, **typed trace edges**, and **pipelines you can re-run** after a trigger. Chat threads do not replace Git history, `traceability.db`, or an executor that enforces step order.

---

## Shared memory, events, three databases

**Q: What is Shared Memory vs “context in the model”?**  
**A:** **Shared Memory** here means the **wiki-style SQLite store** namespaces agents write to across runs—concerns, decisions, architecture snippets, etc.—so the next trigger does not start from zero. “Context in the model” is ephemeral per call; ** namespaces in `shared_memory.db`** accumulate **project truth** the team agreed should persist (see also **`presentation_qa.md` §1.11**).

**Q: What are `shared_memory.db`, `events.db`, and `traceability.db` for—in plain English?**  
**A:** **Shared memory:** durable key-value style knowledge for agents between runs. **Events:** pub/sub log so one pipeline can signal another (and you keep an audit trail). **Traceability:** the graph of **artifacts and typed links** (meetings, REQ, ARCH, risks, Jira, etc.) powering dashboards and REQ docs.

**Q: Why SQLite locally instead of “a real database” in the cloud?**  
**A:** Capstone choice: **zero ops**, single-machine demos, easy backup (copy files), and alignment with “engineering system we can show on a laptop.” Production could move stores to managed DBs without changing the conceptual model.

---

## Execution, triggers, deployment

**Q: What wakes a pipeline up?**  
**A:** Anything normalized to a **trigger type** plus payload—client transcript ingest, cron-style hooks, Git/PR style triggers, etc.—then **routing picks which pipeline** runs and the **executor walks the steps** (details in **`presentation_qa.md`** infra answers).

**Q: Is SES deployed on Azure?**  
**A:** **SES framework as shown** runs **locally** for this capstone; **eParts product** target infra can be Azure—that is a **separate** deployment story. Don’t conflate “where the ML app runs” with “where SES notebooks/pipelines run today” (see **`presentation_qa.md` §1.10**).

**Q: If one step fails, does the whole pipeline die?**  
**A:** Depends on the step: some paths use **skip** when inputs are missing; hard failures should surface in logs/metrics. **Honest answer for demo:** we design for graceful skips where possible; not every branch is production-hardened—call out **demo vs production** if pressed.

---

## Traceability: diagrams, IDs, REQ-001

**Q: What is `ses_traceability.html` vs `traceability_diagram.html`?**  
**A:** **`ses_traceability.html`**—**SES Traceability** overview: **generic** artifact types and relationship idea. **`traceability_diagram.html`**—same **concept** plus a **compact REQ-001** slice for slides. **`traceability_story.html`**—**same graph as a readable tree** for REQ-001. **`intelligence.html`**—full tabular/trace explorer on the bundled dataset.

**Q: What do IDs like REQ-001, ARCH-002, CON-… mean?**  
**A:** Stable handles in the **trace store**: **REQ-*** requirement records (also align with REQ markdown under `requirements/parsed/`), **ARCH-*** architecture records (ADR-aligned intent), **CON-*** concerns from conversation, **DEC-*** decisions, **RIS-*** risks, **MTG-*** meetings. They let human and machine **cite the same node** across Git, dashboards, and DB.

**Q: Are these traces “real” or just a diagram?**  
**A:** Same nodes and edges **exported** into what dashboards load (**e.g.** `dashboard/traceability_data.json` seeded from ingest); REQ markdown is **committed** separately. Trace is **documentation + data**, not a one-off illustration.

**Q: Why bother with typed links (`MITIGATES`, `BECAME`, etc.)?**  
**A:** **Searchability and audit**: you can query “everything that mitigates this risk” or “what requirement this concern became”—and justify sponsor questions without re-watching recordings.

---

## People, governance, Liu handoff

**Q: Who owns requirements vs architecture vs trace?**  
**A:** **Team convention:** SES framework / pipeline authoring (ownership per your roster—**Ashritha** is cited as SES pipeline owner in **`presentation_qa.md`** around ticket routing); **Liu** and software-system leads own **WBS / SDLC narrative** depth—**explicitly hand off** “why we chose this SDLC” to Liu rather than debating it under SES infra slides.

**Q: Human in the loop where?**  
**A:** **P0** items are flagged for human review before auto-behaviors that could derail sprint (see **`presentation_qa.md` §2.1**); ADR and REQ changes belong in normal **Git/PR review** culture.

---

## Limits & future (honest pivots)

**Q: Accuracy of automated trace links?**  
**A:** Heuristic/fuzzy linking is **good but not oracle** (~85%-class behavior discussed in **`presentation_qa.md` §8.5**). LLM-assisted relinking is a plausible quality pass—not run on every row in demo scope.

**Q: What’s missing you’d build next quarter?**  
**A:** Example pivots: **goal-model** layering on traceability (**§8.1** discussion), tighter **cron** operationalization for briefings, **cloud-hosted** SQLite replacements for team-wide runtime, richer **human review UX** beyond Jira queues.

---

## Quick index to the big doc

| Topic | Primary section in `presentation_qa.md` |
|-------|----------------------------------------|
| Git vs wiki vs Confluence | §1.1 |
| Engineering / agentic harness (deep) | §1.4–1.5 |
| Events store | §1.7 |
| Why / measurement | §1.8 |
| LLM vs offline agents | §1.9 |
| Local storage & deploy | §1.10 |
| SharedMemory / “common bank” | §1.11 |
| Requirements / P0 / REQ files | Section 2 |
| Dashboards / trace / WBS | Section 8 |
