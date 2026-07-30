# Talking script — Requirements & Architecture

**Speaker:** Arjun · picks up from Jai after he covers construction, quality and risk
**Deck:** `eParts_Section3_SoftwareSystem.pptx`, 5 slides
**Length:** see the measured table at the bottom. Target is five minutes.

Blockquotes are spoken as written. Cues sit on their own lines outside the quotes.

---

## Handoff

> Thanks Jai. ETIM was our biggest risk, and it's also what changed the system the most. So I'll pick it up there, and go through what it did to our requirements and our architecture.
>
> The documents are linked at the bottom of every slide.

---

## Slide 1 — Requirements: v1.0 → v1.4

> We baselined this document at the end of April and it's been through four revisions since. April is on the left, today is on the right.
>
> Everything new on that list came from ETIM. Classification became a new high-level requirement. Matching split into two functional ones. And pinning to a single ETIM release is now a constraint.
>
> Eighty-nine percent of what we wrote in April is untouched. Two requirements were rewritten, both in ingestion. We'd said normalization would do the ETIM keying, and that was wrong.
>
> The fourth revision was cleanup. We put ETIM into the requirements in June and didn't go back to the quality scenarios or the validation tests. So for a month those two sections described a system we weren't building. Version 1.4 fixed that.

---

## Slide 2 — How we managed the change

> This is how we handled those revisions, and what happened to traceability.
>
> Every time ETIM added something we gave it a new ID instead of editing an old one, and we renumbered nothing. That's why every trace link we drew in April still resolves today.

Walk the thread with your finger as you say it. Pause at each hop.

> I'll walk one. ETIM classification is HLR-6. That drives FR-9, the matching requirement. FR-9 is decided in ADR-16 and ADR-18. Those two exist in the code as the ETIM reference tables. That code is covered by ten unit tests, all passing. There's also an integration test that loads the real ETIM archive end to end, and checks that loading it twice is a no-op. That one only runs where the archive is present. The archive isn't in the repo, so it skips on a clean checkout. Requirement, decision, code, test, and it closes at both ends.
>
> Matching is the thread that doesn't close yet. It's specified and its validation test is written, but the test can't run until the code exists, so it's recorded as not run.
>
> ETIM is also on the risk register, as RISK-ARCH-09. Pinning the release means our catalog goes stale over time, and somebody has to own that after we leave.

---

## Slide 3 — How the architecture changed

Let them look at both diagrams for a beat before you start.

> Left is May, right is now. Side by side they're almost the same drawing.
>
> One box is new. Everything else is where it was. Same pipe-and-filter structure, same audit trail. Routing still works attribute by attribute, and a person still reviews anything the system isn't sure about.
>
> ETIM was a large change and it didn't force a restructure. That's the modifiability claim we made in April, and this is the first change big enough to test it.
>
> Five things changed, and only the first one shows up on the drawing. The other four are inside components. The dictionary we load, the split that keeps the supplier's raw values separate in staging, the handoff format to ML, and the PIMS key.

Point at the new box on the right-hand diagram.

> The new box is ETIM matching. It sits behind attribute matching, inside the same interface. That's the next slide.

---

## Slide 4 — Inside the new box

> This is what's inside that box, drawn large enough to read.
>
> ML was already matching attributes and that part hasn't changed. That's the box at the top. ETIM adds a second pass behind it, inside the same service. That's the five stages below: the product's ETIM class, then which ETIM feature the attribute maps to, then the allowed value and unit, then two validation checks.
>
> The order matters. In ETIM the features belong to the class, so the class decides which features a product can have at all. If we call a ball valve a butterfly valve, we match its attributes against the wrong feature list. The torque number is right, the feature it's attached to is wrong, and that's true for every attribute on the product.
>
> And each of those matches scores high, because it was the best match in the list we gave it. So routing sees confidence and auto-accepts. A wrong class doesn't produce anything routing can catch, so a person confirms the class first.
>
> Every box on that row is dashed. The dictionary it reads and the tables it writes are built, but the five stages are designed and not written.

---

## Slide 5 — Decisions, and what we chose against

> Four decisions, and next to each one the alternative we rejected.
>
> ML does all the matching. The alternative was doing the ETIM lookup during normalization, which is what our spec said until version 1.3. It doesn't work, because an ETIM assignment carries a confidence and sometimes needs a person to approve it, and normalization has neither.
>
> The supplier's raw values stay in their own table, so we can always get back to what we were sent.
>
> When ETIM changed a decision we wrote a new ADR instead of editing the April one. Those are the record of what we believed at the time, and overwriting them loses the reasoning.
>
> And we're staying on ETIM 10.0 for the rest of the project rather than building an upgrade path. Doing that properly means diffing releases, re-matching everything affected, and reviewing what comes out different. None of that gets exercised before we finish. It's a real cost, so it's on the risk register.

---

## Timing

Measured from the blockquotes at 150 wpm.

| Section | Words | Time |
|---|---|---|
| Handoff | 44 | 18 s |
| Slide 1 | 128 | 51 s |
| Slide 2 | 200 | 80 s |
| Slide 3 | 139 | 56 s |
| Slide 4 | 195 | 78 s |
| Slide 5 | 160 | 64 s |
| **Total** | **866** | **5:46** |

You are 47 seconds over. The first four cuts land you at 5:02; all five put you at 4:56.
Slide 4 is the longest section and it should stay that way. It is the only place you
explain a decision rather than report one.

| Cut | Saves |
|---|---|
| Slide 5, the raw-values line — slide 3's list already names it | 8 s |
| Slide 1, the paragraph about the June gap | 17 s |
| Slide 3, the list of the other four changes, keeping "only the first one shows up on the drawing" | 12 s |
| Slide 2, the two sentences about the archive skipping — keep it for the Q&A instead | 9 s |
| Slide 5, the first half of the ETIM 10.0 paragraph, keeping "none of that gets exercised before we finish" | 6 s |

**Do not cut** the trace thread on slide 2, the valve example on slide 4, or the dashed-boxes line. Those carry the rubric line — traceable through architecture, implementation and validation, and honest about what isn't built.

## Delivery notes

- Slide 2's trace thread is the most valuable thirty seconds in the section. Slow down and point at each hop rather than reciting it. The IDs are the one place you're allowed to sound like you're reading, because you're reading them off the slide.
- Slide 3, the two thumbnails are a silhouette comparison, nothing more. v6 is v5 with one box added, so they should look near-identical. Don't invite anyone to read them, and don't tell them what to conclude from it — the near-identical outline is doing that on its own. Slide 4 is where the detail lands.
- Slide 4 is the one slide where you're explaining a design decision rather than reporting one. Slow down on the valve example. Name the two valves clearly and let the panel picture it before you land the consequence.
- Say the dashed part plainly and move on. State it once, don't sell it.
- Every paragraph break in the script is a breath. If you run two together you'll start to sound like you're reciting, regardless of the wording.
- The ten unit tests were run on 29 July and all passed, in about 3m40s (`pytest tests/unit/test_etim_loader.py` in `e2e-ocr-ing`). The integration test skips unless `.tmp_etim_csv` is present, and it is gitignored — so if anyone runs the suite in front of you, expect `10 passed, 1 skipped`. Say the skip before they ask.
- If asked who wrote the documents: the agents drafted them, we reviewed and finalised them. Wiring that into the automated pipeline is still open work. That answer holds up if anyone goes and looks at the repo.

## Questions you'll probably get

**Doesn't ingestion do the ETIM keying?**

> No. Our spec did say that until version 1.3. Ingestion cleans the data and keeps the supplier's own values. All the matching is in ML, attributes first, then ETIM. It can't sit in normalization because an ETIM assignment has a confidence attached and might need a person to confirm it, and normalization has neither. Ingestion does load the dictionary, because it already owns file parsing and migrations, but it doesn't use it.

**Why not keep up with new ETIM releases?**

> Because doing it properly is real work. You'd have to diff the new release against the old one, re-match every affected product, and review everything that came out different. None of that gets exercised before we finish, and nobody has decided who signs off an upgrade. So we wrote it into the spec as a constraint, and onto the risk register as RISK-ARCH-09. We did keep the release ID on every row, so any published value still says which version of ETIM it was matched against.

**How do you know the architecture is stable?**

> Two things. Eighty-nine percent of the April requirements are untouched, and the biggest change we've had all summer landed without moving the pipe-and-filter structure or breaking a trace link. That's what QAS-1 predicted, and this is the first time we could check it against something real.

**Is it Prometheus or Datadog?**

> Both, deliberately. Datadog is the production target and that's what the ADR says. Prometheus and OpenTelemetry are what the local development environment runs. Our own assessment document read the code without knowing the deployment intent and flagged it as a contradiction, which is why the current diagram labels both.
