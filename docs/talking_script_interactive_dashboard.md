# Talking script — first dashboard (`interactive_architecture.html`)

Use this file: **`dashboard/interactive_architecture.html`**. Roughly **four to six minutes** if you expand the Requirements panel and scroll slowly. Speak in short paragraphs; pause where it says **[pause]**.

---

## Optional: if you opened `intelligence.html` first (45 seconds)

“Before we zoom into pipelines, this **Project Intelligence** view is the product story in one screen: goal model, work breakdown, agent flow, traceability. The numbers at the top are live-ish counts from our runs—meetings, requirements, events, wiki entries, trace links. I’m going to switch to the **Interactive Architecture** dashboard next, because that’s where we separate the **agentic harness** from the **software engineering harness** and show exactly what runs today.”

**[Switch tab or browser to `interactive_architecture.html`.]**

---

## 1. Land the screen (~30 seconds)

“So this dashboard is titled **eParts Agentic Software Engineering System** — capstone framing is CMU MSE Studio, **Pimsie Supreme**. **[pause]** I’m going to unpack two ideas: the **agentic harness** — how multiple autonomous agents chain together — and the **engineering harness** — how that chain still maps to real **requirements engineering** activities you’d recognize from class: inception, elicitation, specification, validation, management. The UI color-codes **maturity**: green pipelines are ones we actively run, orange is partially there, red is planned for later phases.”

---

## 2. The grid — three rows, three stories (~90 seconds)

**Point at the top row (green).**

“Top row: **Requirements**, **Coach Session**, **Knowledge** — these are **in use**. Requirements turns a meeting transcript into structured output, tickets, and traceable decisions. Coach Session keeps mentor and coach guidance **retrievable**—embeddings, recurring themes. Knowledge rolls project state into **briefings** so nobody walks into a meeting cold.”

**Point at the middle row (orange).**

“Middle row: **Architecture** and **Project Management** — **partially** wired. Architecture is drift detection, ADRs, traceability updates. PM is WBS sync with Jira, digests, alerts. You’ll see more of this as we demo or as the semester progresses.”

**Point at the bottom row (red).**

“Bottom row: **Coding** and **ML Decision** — **future** phase. Coding is PR review, tests, docs, prompt regression. ML Decision is evidence accumulation and **readiness** to close an open model decision. We show them so the **whole** product story is visible, not just what works this week.”

---

## 3. Two harnesses in plain language (~60 seconds)

“**Agentic harness** means: we don’t run one prompt in isolation. We run **named agents** in a **fixed order**, hand off **context** between steps, write to a **shared wiki**, emit **events** when something important happens, and connect to **Jira and GitHub** through a small integration layer. **[pause]**  

**Engineering harness** means: we still teach the same RE lifecycle — we just **automate** the mechanical parts and leave **judgment** where it belongs. The best example is right here: **click Requirements**.”

**[Click the Requirements card so the big panel opens.]**

---

## 4. Requirements pipeline — walk the seven steps (~2 minutes)

“This is the **Requirements Engineering** pipeline: **seven sequential agents**, triggered by uploading a **`.vtt` transcript**. Read it like a factory line from left to right.”

**Step 1 — transcript_parser.**  
“First agent **parses** the transcript into structured JSON — speakers, action items, decisions, concerns. It can also **emit events** — for example when action items are extracted — so other parts of the system can react.”

**Step 2 — priority_classifier.**  
“Second agent **classifies** everything as P0, P1, or P2. **P0** is special: we **don’t** auto-file those as production tickets without a human — that’s the **human-in-the-loop gate** badge you see. That’s intentional risk management.”

**Step 3 — req_extractor.**  
“Third agent turns discussion into **formal REQ documents** — markdown in the repo, `REQ-XXX`, with categories and acceptance criteria. That’s the **specification** step in engineering terms.”

**Step 4 — ticket_creator.**  
“Fourth agent pushes **work into Jira** for the items we’re comfortable automating — P1/P2-style flow — with summaries and labels so the board stays usable.”

**Steps 5 and 6 — minutes_publisher, decision_logger.**  
“Fifth and sixth: **minutes** where Confluence is connected, and a running **decision log** — same decision content the team cares about for audits.”

**Step 7 — drift_detector.**  
“Seventh: **drift** — we compare what was decided in the room against our **canonical architecture** using retrieval, and we can emit **drift_detected** so the **Architecture** pipeline can pick up downstream. That’s **validation** in RE language — ‘does new talk contradict what we already agreed?’”

---

## 5. The SE activity table (~45 seconds)

**[Scroll to “Mapping to SE Requirements Activities.”]**

“This table is the bridge for anyone who cares about **courses and standards**, not jargon. Inception and elicitation map to parsing; negotiation maps to prioritization — humans still **approve P0**. Specification maps to REQ files; validation maps to drift and traceability; management maps to Jira and the decision log. So the **agentic** story and the **software engineering** story are the **same** story with different vocabulary.”

---

## 6. Meta model boxes (~45 seconds)

**[Scroll to the four boxes: Artifacts, Processes, Resources, Measurement.]**

“Four boxes summarize the **meta model** for this pipeline. **Artifacts** — JSON, REQ files, Jira keys, decision logs, drift reports. **Processes** — the seven-step chain from transcript in to GitHub and Jira out. **Resources** — agents, integrations, vector store for RAG, and **people** at the P0 gate. **Measurement** — how much we extract, how often humans override, how drift behaves, whether tickets stick. That’s how we keep the system **accountable**, not magical.”

---

## 7. Counterfactual — why this matters (~45 seconds)

**[Scroll to “Counterfactual Analysis” in the Requirements panel.]**

“This strip is deliberate: **without** automation, somebody spends hours on a forty-five-minute recording; tickets slip; drift stays invisible. **With** automation, end-to-end is **seconds to minutes**, format is **consistent**, and humans focus on **P0** and judgment calls. **[pause]** The value isn’t only time — it’s **consistency** across every meeting and every teammate.”

---

## 8. Close — transition to live demo or next screen (~30 seconds)

“So on one dashboard you’ve seen: **which** pipelines exist, **which** are live versus partial versus future, and **one full path** — Requirements — end to end with RE mapping and artifacts. **[pause]** Next I’ll **[run `demo.py` / show Jira / show GitHub]** so you see the same pipeline **actually execute** on a transcript. Questions before we switch?”

---

## Quick reference — on-screen elements to gesture at

| Where to look | What to say in one phrase |
|---------------|---------------------------|
| Page title | “Agentic SE system — not a single chatbot.” |
| Green / orange / red rows | “Maturity: running now, in progress, planned.” |
| Requirements → 7 agents | “Assembly line; context flows left to right.” |
| P0 badge | “Humans own the riskiest items.” |
| SE activity table | “Same lifecycle you learned in class.” |
| Counterfactual | “Time + consistency + drift visibility.” |

---

## If you start with `intelligence.html` instead

Open the **Goal Model** tab first: “Strategic goals decompose to soft goals, user goals, functional goals — obstacles are first-class.” Then **WBS** for delivery structure, **Agent Flow** for the graph mental model, **Traceability** for requirement–meeting–architecture links. Then **switch** to `interactive_architecture.html` for the pipeline-deep story above.

---

*File path: `dashboard/interactive_architecture.html`. Pair with `docs/ses_architecture_speakable.md` for spoken architecture without the UI.*
