# Talking script — Requirements & Architecture

**Speaker:** Arjun · picks up from Jai after he covers construction, quality and risk
**Deck:** `eParts_Section3_SoftwareSystem.pptx`, 5 slides
**Length:** 866 words, 5:46 measured. Two cuts from the table at the bottom get you to five.

Blockquotes are spoken as written. Cues sit on their own lines outside the quotes.

---

## Handoff

> Thanks Jai. ETIM was our biggest risk, and it's also what changed the most about the system, so let me pick it up there and show you what it actually did to our requirements and our architecture. The documents are linked at the bottom of every slide.

---

## Slide 1 — Requirements: v1.0 → v1.4

> We baselined this at the end of April and it's been through four revisions since. April on the left, today on the right.
>
> Everything new came from ETIM. Classification became a new high-level requirement, matching split into two functional ones, and pinning ourselves to one ETIM release became a constraint.
>
> The number I care about is on the right, though. Eighty-nine percent of what we wrote in April survived untouched, and only two requirements had to be rewritten. Both were about ingestion — we'd said normalization would do the ETIM keying, and that was wrong.
>
> The fourth revision was us catching ourselves. We added ETIM to the requirements in June and never went back to our quality scenarios or our validation tests, so for a month those two sections described a system we weren't building any more.

---

## Slide 2 — How we managed the change

> This is how we handled those revisions, and it's the part I'd point at for traceability.
>
> Every time ETIM added something we gave it a new ID instead of editing an old one, and we renumbered nothing. That sounds like bookkeeping, but it's the reason every trace link we drew in April still resolves today.

Walk the thread with your finger as you say it.

> Let me walk one, because it's quicker than describing it. ETIM classification is HLR-6. That drives FR-9, the matching requirement. FR-9 is decided in ADR-16 and ADR-18. Those two decisions exist in the code as the ten ETIM reference tables, and that code is covered by ten unit tests, all passing. So requirement, decision, code, test — and it closes at both ends.
>
> The thread that doesn't close yet is matching itself, and that's deliberate. Its test is written but it can't run until the code exists, so we didn't pretend otherwise. ETIM is also on our risk register as RISK-ARCH-09, because pinning the release means our catalog goes stale over time and somebody has to own that after we leave.

---

## Slide 3 — How the architecture changed

Let them look at both diagrams for a beat before you start.

> Left is May, right is now. You can't read either of those and you're not meant to — the full drawing is linked at the bottom. What I want you to see is the outline.
>
> Almost none of it moved. Still pipe-and-filter, routing still happens attribute by attribute, a person still reviews anything the system isn't sure about, and the audit trail is unchanged. ETIM was the biggest change we've had all summer and it didn't cost us a restructure, which is the one modifiability claim from April we've now actually tested.
>
> Five things did change. Two of them are worth explaining.

Point at change three in the list.

> The quick one is that we split staging into two tables. One holds what the supplier actually sent us, the other holds what we think it means in ETIM terms. Put both in the same row and you can't separate them afterwards, and then you can't explain where a published value came from.
>
> The other one I want to show you properly.

---

## Slide 4 — Change 2, up close

> This is change two, drawn big enough to read.
>
> ML was already matching attributes and that part hasn't changed — that's the box at the top. What ETIM adds is a second pass behind it, inside the same service. Once you know which attribute you're looking at, you work out the product's ETIM class, then which ETIM feature that attribute maps to, then the allowed value and its unit, and then two validation steps.
>
> The order isn't arbitrary, and this is the part I'd want you to take away. Which features are even valid depends on the class. Get the class wrong and everything underneath it is wrong too — and wrong with high confidence, which means routing won't flag it. A low-confidence answer is safe, because it goes to a person. A confidently wrong one isn't. That's why someone confirms the class before we route anything attribute by attribute.
>
> Every box on that row is dashed, and none of it is built yet. The dictionary it reads from is built and the tables it writes into are built. The five stages are designed and not written.

---

## Slide 5 — Decisions, and what we chose against

> Four decisions, and next to each one the thing we didn't do.
>
> ML does all the matching. We nearly did the ETIM lookup during normalization instead — our own spec said so for about a month. It's wrong because an ETIM assignment carries a confidence and sometimes needs a person to sign off on it, and normalization has neither of those.
>
> When ETIM changed a decision we wrote a new ADR instead of editing the April one, because those are the record of what we believed at the time and overwriting them loses the reasoning.
>
> And we're staying on ETIM 10.0 for the rest of the project rather than building an upgrade path. Doing that properly means diffing releases, re-matching everything affected, and reviewing whatever comes out different, and that's a lot of machinery for something that won't happen before we're finished. It's a real cost, so it's on the risk register rather than buried.

---

## Timing

Measured from the blockquotes at 150 wpm.

| Section | Words | Time |
|---|---|---|
| Handoff | 47 | 19 s |
| Slide 1 | 137 | 55 s |
| Slide 2 | 176 | 70 s |
| Slide 3 | 164 | 66 s |
| Slide 4 | 187 | 75 s |
| Slide 5 | 155 | 62 s |
| **Total** | **866** | **5:46** |

Forty-six seconds over. The first two cuts get you to 5:00 exactly.

| Cut | Saves |
|---|---|
| Slide 1, the fourth-revision paragraph | 22 s |
| Slide 5, the second half of the ETIM 10.0 paragraph, keeping "that's a lot of machinery for something that won't happen before we're finished" | 20 s |
| Slide 3, the staging-split paragraph — slide 5 names it again as a decision | 20 s |
| Slide 4, "A low-confidence answer is safe… A confidently wrong one isn't" | 10 s |

**Don't cut** the trace thread on slide 2, or the dashed-boxes paragraph on slide 4. Those two carry the rubric line — traceable through architecture, implementation and validation, and honest about what isn't built.

## Delivery notes

- Slide 2's trace thread is the most valuable thirty seconds in the section. Point at each hop rather than reciting it.
- Slide 3, say the "you can't read these" line without apologising for it. Admitting the thumbnails are a silhouette comparison is stronger than pretending anyone can read them, and slide 4 is the payoff.
- On slide 4, slow right down on the confidently-wrong argument. It's the one place you're explaining a design decision rather than reporting one.
- **On the tests:** ten unit tests pass, in about 3m40s (`pytest tests/unit/test_etim_loader.py` in `e2e-ocr-ing`). There's also an integration test against the real ETIM archive, but it skips unless `.tmp_etim_csv` is present and that isn't committed — so a clean checkout shows `10 passed, 1 skipped`. Only bring the skip up if someone runs the suite or asks; don't spend slide-2 time on it.
- If asked who wrote the documents: the agents drafted them, we reviewed and finalised them. Wiring that into the automated pipeline is still open work. That answer holds up if anyone goes and looks at the repo.

## Questions you'll probably get

**Doesn't ingestion do the ETIM keying?**

> No, and our spec did say that for about a month. Ingestion cleans the data and keeps the supplier's own values. All the matching is in ML — attributes first, then ETIM. It can't sit in normalization because an ETIM assignment has a confidence attached and might need a person to confirm it, and normalization has neither. Ingestion does load the dictionary, because it already owns file parsing and migrations, but it doesn't use it. Version 1.3 fixed the wording.

**Why not keep up with new ETIM releases?**

> Because doing it properly is real work. You'd have to diff the new release against the old one, re-match every affected product, and review everything that came out different. None of that gets exercised before we finish and nobody has decided who signs off an upgrade, so we wrote it into the spec as a constraint instead of leaving it vague, and onto the risk register as RISK-ARCH-09. We did keep the release ID on every row, so any published value still says which version of ETIM it was matched against.

**How do you know the architecture is stable?**

> Two things. Eighty-nine percent of the April requirements are untouched, and the biggest change we've had all summer landed without moving the pipe-and-filter structure or breaking a single trace link. That's what QAS-1 predicted would happen, and this is the first time we got to check it against something real.

**Is it Prometheus or Datadog?**

> Both, deliberately. Datadog is the production target and that's what the ADR says. Prometheus and OpenTelemetry are what the local development environment runs. Our own assessment document read the code without knowing the deployment intent and flagged it as a contradiction, which is why the current diagram labels both.
