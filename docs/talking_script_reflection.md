# Talking script — Reflection & Closing (~2 minutes)

**Slide:** `eParts_Section3_SoftwareSystem.pptx` **slide 5**, "Two lessons"
**Slot:** end of the team talk, after Management — not straight after slide 4
**Evidence:** `dashboard/data/jira_issues.json` — 290 issues, with the JQL and fetch timestamp recorded in the file

~270 words. Two lessons, one of them about AI in software engineering.

---

## Lesson 1 — the 3-day cycle — 50 sec

> First one is about our own process. We started the summer planning in 3-day ticks — that came out of the agentic-augmented-scrum doc we wrote — and it didn't hold. We're on 7-day cycles in Jira now.
>
> Three reasons. Too much changed inside a single tick to close it cleanly. A small blocker would eat the whole cycle, because at three days there's no slack to absorb one. And the third one is the actual reason: **reviewing an agent's pull request took longer than the agent took to write it.**
>
> That's the thing we didn't see coming. The agents moved our constraint from writing code to reviewing it, and we'd sized the cycle for the old constraint. It's also why we plan capacity in review hours instead of story points now.

---

## Lesson 2 — AI in software engineering — 70 sec

> Second one, and this is the AI one. We gave the agents control of the paperwork — tickets, documentation, PR comments — because they're reading the same repo we are, so they've actually got more context than one of us typing a ticket at the end of the day.
>
> The speed number: about 3 minutes per ticket by hand, about 15 seconds for an agent. Two hundred and thirty-four tickets since May, so roughly 11 hours back. Which is real, but it's under an hour a week, so I don't want to oversell it.
>
> **The number that actually matters is this one.** Of the 56 tickets we wrote by hand in spring, zero had story points and zero were attached to an epic. Of the 234 the agents drafted, 90 percent have points and 94 percent are in the right epic.
>
> A person writing a ticket at 11pm skips those fields. An agent doesn't. And that's the reason the forecasting you just saw works at all — Monte Carlo over our throughput needs points on every ticket. In spring we could not have produced that chart from our own backlog, and we didn't know that was the constraint until the agents removed it.

---

## Delivery notes

- **Lead with the failure.** The 3-day cycle not working is the more credible half; teams that only report wins get probed harder.
- **Say the 11 hours, then undercut it yourself.** "Under an hour a week, so I don't want to oversell it" buys you the credibility to then land the 0% → 90% number, which is the real claim.
- **Connect lesson 2 back to Management.** The forecast is someone else's slide; pointing at it makes the two sections read as one argument rather than two people's lessons.
- Don't say "AI saved us time" as the headline. The honest and more interesting finding is that AI changed *what was possible to measure*, and the time saving was a rounding error next to that.

## If challenged

**"Isn't 90% just because you told it to fill the field?"**

> Partly, yes — that's the point. The instruction was cheap to give once and it holds on every ticket. We tried to hold ourselves to the same standard in spring and hit zero percent, because it's the field you skip when you're tired and the ticket already makes sense to you.

**"Do you review these?"**

> Every one. The 10 percent without points are mostly ones we corrected or closed as duplicates during review.

**"Where do the numbers come from?"**

> A Jira export in the repo, `dashboard/data/jira_issues.json`. It stores the JQL it ran and when it ran, so you can re-derive it. 290 issues total, 56 before May, 234 after.

## Fix before you present

Section 4 has an internal inconsistency that this slide makes visible: **slide 2 says 7-day cycles and slide 7 says 3-day cycles.** Since lesson 1 is explicitly about that change, an assessor who noticed the mismatch earlier will read it as sloppiness rather than as the story you're telling. Change slide 7 to 7-day, or add "(we moved from 3-day — see lesson 1)".
