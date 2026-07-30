# Talking script — Requirements & Architecture

**Speaker:** Arjun · picks up from Jai after he covers construction, quality and risk
**Deck:** `eParts_Section3_SoftwareSystem.pptx`, 4 slides
**Length:** see the measured table at the bottom. Target is five minutes.

Blockquotes are spoken as written. Cues sit on their own lines outside the quotes.

---

## Handoff

> Thanks Jai. ETIM was our biggest risk and it's also the thing that changed the most about the system, so let me pick it up there and show you what it actually did to our requirements and our architecture.
>
> The documents are linked at the bottom of every slide if you want to open them while I talk.

---

## Slide 1 — Requirements: v1.0 → v1.4

> We baselined this document at the end of April and it's been through four revisions since. April is on the left, today is on the right, across all six classes of requirement.
>
> Everything new on that list came from ETIM. Classification became a new high-level requirement, matching split into two functional ones, and pinning ourselves to a single ETIM release became a constraint.
>
> The number I actually care about is on the right, though. Ninety-two percent of what we wrote in April survived untouched. Only two requirements had to be rewritten, and both were about ingestion — we'd said normalization would do the ETIM keying and that turned out to be wrong.
>
> The last revision is the one I'm least proud of and probably the most useful. We put ETIM into the requirements in June and never went back to our quality scenarios or our validation tests, so for a month those two sections described a system we weren't building any more. Version 1.4 is us closing that.

---

## Slide 2 — How we managed the change

> This is how we handled those revisions, and it's the part I'd point at for traceability.
>
> Every time ETIM added something we gave it a new ID instead of editing an old one, and we renumbered nothing. That sounds like bookkeeping, but it's the reason every trace link we drew in April still resolves today.

Walk the thread with your finger as you say it.

> Let me just walk one, because it's quicker than describing it. ETIM classification is HLR-6. That drives FR-9, the matching requirement. FR-9 is decided in ADR-16 and ADR-18. Those two are built as the ETIM reference tables and migration 0005. And that code is covered by eleven tests — ten unit tests, plus one integration test that loads the real release files and checks that loading twice is a no-op. So requirement, decision, code, test, and it closes at both ends.
>
> The thread that doesn't close yet is matching itself, and that's on purpose. It's specified and its validation test is written, but the test can't run until the code exists, so we didn't pretend otherwise. ETIM is also on the risk register as RISK-ARCH-09, because pinning the release means our catalog goes stale over time and somebody has to own that after we leave.

---

## Slide 3 — How the architecture changed

Let them look at both diagrams for a beat before you start.

> Left is May, right is now.
>
> What I'd notice first is how much didn't move. Still pipe-and-filter, routing still happens attribute by attribute, a person still reviews anything the system isn't sure about, and the audit trail is unchanged. ETIM was a big change and it didn't cost us a restructure, which is the one modifiability claim from April that got properly tested.
>
> Two of the five changes need explaining.

Point at change two.

> The first is matching. ML was already matching attributes and that part hasn't changed. What ETIM adds is a second pass behind it, inside the same service — once you know which attribute you're looking at, you work out the product's ETIM class, then which ETIM feature that attribute maps to, then the allowed value and unit.
>
> That order isn't arbitrary. Which features are valid depends on the class, so if we get the class wrong then everything underneath it is wrong too, and it'll be confidently wrong, so routing won't flag it. That's why a person checks the class before we route anything attribute by attribute.

Point at change three.

> The second is that we split staging into two tables. One holds what the supplier actually sent us, the other holds what we think it means in ETIM terms. Put both in the same row and you can't separate them later, and then you can't explain where a published value came from.
>
> One thing about the drawing itself. Solid boxes are running code, dashed boxes are designed but not built. The dictionary, the staging split and the handoff format are real. The matching stages aren't yet.

---

## Slide 4 — Decisions, and what we chose against

> Four decisions, and next to each one the thing we didn't do.
>
> ML does all the matching. We nearly did the ETIM lookup during normalization instead — our own spec said so for about a month. It's wrong because an ETIM assignment carries a confidence and sometimes needs a person to sign off on it, and normalization has neither of those.
>
> The supplier's raw values stay in their own table, so we can always get back to what we were actually sent.
>
> When ETIM changed a decision we wrote a new ADR instead of editing the April one, because those are the record of what we believed at the time and overwriting them loses the reasoning.
>
> And we're staying on ETIM 10.0 for the rest of the project rather than building an upgrade path. Doing that properly means diffing releases, re-matching everything affected, and reviewing whatever comes out different, and that's a lot of machinery for something that won't happen before we're finished. It's a real cost, so it's on the risk register rather than buried.

---

## Timing

Measured from the blockquotes at 150 wpm.

| Section | Words | Time |
|---|---|---|
| Handoff | 58 | 23 s |
| Slide 1 | 168 | 67 s |
| Slide 2 | 200 | 80 s |
| Slide 3 | 263 | 105 s |
| Slide 4 | 176 | 70 s |
| **Total** | **865** | **5:46** |

You are 46 seconds over. Cut in the order below; the first two get you to five minutes.

| Cut | Saves |
|---|---|
| Slide 4, the raw-values line — slide 3 already made the point | 12 s |
| Slide 3, the second half of the class-order paragraph, keeping only "get the class wrong and everything underneath it is wrong too" | 20 s |
| Slide 1, the paragraph about the June gap | 26 s |
| Slide 4, the second half of the ETIM 10.0 paragraph, keeping "that's a lot of machinery for something that won't happen before we're finished" | 20 s |

**Do not cut** the trace thread on slide 2 or the solid-versus-dashed line on slide 3. Those two carry the rubric line — traceable through architecture, implementation and validation, and honest about what isn't built.

## Delivery notes

- Slide 2's trace thread is the most valuable thirty seconds in the section. Slow down and point at each hop rather than reciting it.
- Slide 3, let the diagrams do the work. You're narrating a picture, not reading labels.
- Say the dashed-outline part plainly. Volunteering what isn't built lands better than any number on the slide.
- If asked who wrote the documents: the agents drafted them, we reviewed and finalised them. Wiring that into the automated pipeline is still open work. That answer holds up if anyone goes and looks at the repo.

## Questions you'll probably get

**Doesn't ingestion do the ETIM keying?**

> No, and our spec did say that for about a month. Ingestion cleans the data and keeps the supplier's own values. All the matching is in ML — attributes first, then ETIM. It can't sit in normalization because an ETIM assignment has a confidence attached and might need a person to confirm it, and normalization has neither. Ingestion does load the dictionary, because it already owns file parsing and migrations, but it doesn't use it. Version 1.3 fixed the wording.

**Why not keep up with new ETIM releases?**

> Because doing it properly is real work. You'd have to diff the new release against the old one, re-match every affected product, and review everything that came out different. None of that gets exercised before we finish and nobody has decided who signs off an upgrade, so we wrote it into the spec as a constraint instead of leaving it vague, and onto the risk register as RISK-ARCH-09. We did keep the release ID on every row, so any published value still says which version of ETIM it was matched against.

**How do you know the architecture is stable?**

> Two things. Ninety-two percent of the April requirements are untouched, and the biggest change we've had all summer landed without moving the pipe-and-filter structure or breaking a single trace link. That's what QAS-1 predicted would happen, and this is the first time we got to check it against something real.

**Is it Prometheus or Datadog?**

> Both, deliberately. Datadog is the production target and that's what the ADR says. Prometheus and OpenTelemetry are what the local development environment runs. Our own assessment document read the code without knowing the deployment intent and flagged it as a contradiction, which is why the current diagram labels both.
