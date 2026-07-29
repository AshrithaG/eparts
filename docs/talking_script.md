# Talking script — Requirements & Architecture

**Speaker:** Arjun · picks up from Jai after he covers construction, quality and risk
**Deck:** `eParts_Section3_SoftwareSystem.pptx`, 4 slides
**Length:** 825 words, about five and a half minutes at a normal speaking pace. Two cuts from the table at the bottom get you under five.

Everything in a blockquote is meant to be said out loud as written. Cues sit on their own lines outside the quotes.

---

## Handoff

> Thanks Jai.
>
> I'm going to talk about our requirements and our architecture, and how both changed over the summer. ETIM is the reason they changed, so it'll come up a lot. Jai mentioned it as a risk a minute ago, and I'll show you what it actually did to the system.
>
> Everything I refer to is linked at the bottom of each slide, if you'd rather read the document than my summary of it.

---

## Slide 1 — Requirements: v1.0 → v1.3

> We baselined the requirements document at the end of April, and it's been through three revisions since then. This table compares where we started with where we are now.
>
> We went from nineteen requirements to twenty-four. That's one new high-level requirement, two new functional ones, one derived requirement, and one new constraint. All five of those came out of ETIM.
>
> The number on the right is the one I'd point at, though. Eighty-nine percent of what we wrote in April is still exactly as we wrote it, and only two of the nineteen had to be rewritten. The churn figure says thirty-seven percent, but most of that is us adding requirements rather than changing our minds about ones we'd already agreed.
>
> Both of the rewrites were about ingestion. One was which channels we actually support, and the other was what normalization is responsible for, which I'll come back to.

---

## Slide 2 — How we managed the change

> This is how we handled those three revisions.

Point at the card.

> When we added a requirement we gave it a new ID instead of editing an existing one. ETIM classification became HLR-6, the two matching requirements became FR-9 and FR-10, and the constraint became C-4. We renumbered nothing, which matters, because every trace link we built in April still points where it did.
>
> Each revision got its own entry in the version history, so the document explains its own changes. Open it and you can see what changed in 1.1, 1.2 and 1.3, and why.
>
> Two of those three revisions were us correcting ourselves rather than the client changing their mind. We could have quietly folded them back into the original document, but then there'd be no record that we'd got something wrong and fixed it.

---

## Slide 3 — How the architecture changed

Give them a couple of seconds to look at the two diagrams before you start.

> On the left is our architecture from May. On the right is where it is now.
>
> The first thing worth pointing out is how much of it is the same. The pipe-and-filter shape hasn't moved, routing still happens per attribute, a person still reviews anything the system isn't confident about, and the audit trail is unchanged. ETIM was a large change and it didn't force us to restructure anything.
>
> Five things did change. Two of them are worth explaining properly.

Point at change two.

> The second one is about matching. ML was already matching attributes and that part hasn't changed. What ETIM adds is a second step behind it, in the same component: once you know which attribute you're looking at, you work out which ETIM class the product is, which ETIM feature that attribute maps onto, and which allowed value and unit to use.
>
> The order matters, because the legal features depend on the class. If we pick the wrong class then every feature underneath it is wrong too, and it'll be wrong with high confidence, so routing won't catch it. That's why there's a class review step in front of the attribute routing.

Point at change three.

> The third one is that we split staging into two tables. One holds what the supplier sent us, the other holds what we think it means in ETIM terms. If both live in the same row you can't tell them apart afterwards, and we lose the ability to explain where a published value came from.
>
> One last thing on this slide. The solid outlines are code that runs today, and the dashed outlines are things we've designed but haven't built. The ETIM dictionary, the staging split and the handoff format are real. The matching steps aren't built yet.

---

## Slide 4 — Decisions, and what we chose against

> Last slide. These are four decisions we made, and next to each one is the option we didn't take.
>
> We decided ML does all the matching. The alternative was doing the ETIM lookup during normalization, and we rejected that because an ETIM assignment carries a confidence and may need a person to confirm it, and normalization has neither.
>
> We kept the supplier's raw values in their own table rather than in one row with everything else, so we can always trace a published value back.
>
> When ETIM changed a decision we wrote a new ADR rather than editing the April one, because the old ones record what we believed at the time.
>
> And we're staying on ETIM 10.0 for the rest of the project instead of building an upgrade path. Doing that properly means diffing the new release, re-matching everything affected, and reviewing whatever came out different. That's a lot of work for something that won't happen before we finish.
>
> There are five decisions we still need from the client, and two of them are blocking us from finishing validation.

---

## If you're running long

Cut in this order. The timings are measured, not guessed.

| Cut | Saves |
|---|---|
| Slide 1, the last paragraph about the two rewritten requirements | 20 s |
| Slide 2, the last paragraph about correcting ourselves | 22 s |
| Slide 4, the raw-values paragraph — it repeats change three on slide 3 | 18 s |
| Slide 3, the second half of the class-order explanation, keeping only "if we pick the wrong class, everything underneath it is wrong too" | 15 s |

Don't cut the wrong-class explanation entirely, and don't cut the solid-versus-dashed line. Those two are the difference between explaining the architecture and listing it.

## Delivery notes

- Slide 3 is the one to slow down on. The two diagrams do the work; you're just narrating them.
- The slides are deliberately short on text. Say the sentence, don't read the label.
- Say the dashed-outline part plainly. Volunteering what isn't built goes down better than any number on the slide.
- If someone asks who wrote the documents: the agents drafted them and we reviewed and finalised them. Wiring that into the automated pipeline is still open work. That answer holds up if they go and look at the repo.

## Questions you'll probably get

**Doesn't ingestion do the ETIM keying?**

> No. Ingestion cleans the data up and keeps the supplier's own values. All the matching happens in ML — attributes first, then ETIM. It can't sit in normalization, because an ETIM assignment has a confidence attached and might need a person to confirm it, and normalization has neither. Ingestion does load the dictionary, because it already handles file parsing and migrations, but it doesn't use it. Our spec did read the other way for about a week, and version 1.3 fixes it.

**Why not keep up with new ETIM releases?**

> Because doing it properly is real work. You'd need to diff the new release against the old one, re-match every product that's affected, and review everything that came out different. None of that gets exercised before we finish, and nobody's decided who signs off on an upgrade anyway. So we wrote it into the spec as a constraint rather than leaving it vague. We did keep the release ID on every row, so any published value still says which version of ETIM it was matched against.

**Is it Prometheus or Datadog?**

> Both, on purpose. Datadog is the production target and that's what the ADR says. Prometheus and OpenTelemetry are what the local development environment runs. Our own assessment document read the code without knowing the deployment intent and flagged it as a contradiction, so the current diagram labels both.
