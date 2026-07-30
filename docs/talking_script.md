# Talking script — Requirements & Architecture

**Speaker:** Arjun · picks up from Jai after he covers construction, quality and risk
**Deck:** `eParts_Summer.pptx`, slides 16–20
**Length:** see the measured table at the bottom. Target is five minutes.

Blockquotes are spoken as written. Cues sit on their own lines outside the quotes.

> ⚠️ **Two label edits needed on slide 17 before this script is true.** The chain currently
> reads `HLR-6 → FR-9 → ADR-18 → REF TABLES → TESTS`. FR-9 is *matching*, which isn't built;
> the reference tables and those ten tests implement **FR-10**, the dictionary, decided in
> **ADR-13**. Change `FR-9` to `FR-10` and `ADR-18` to `ADR-13` and the chain closes for
> real. Everything below assumes that edit.

---

## Handoff · 18 s

> Thanks Jai. ETIM was our biggest risk, and it's also what changed the system the most. So I'll pick it up there, and go through what it did to our requirements and our architecture.
>
> The documents are linked at the bottom of every slide.

---

## Slide 16 — Requirements: v1.0 → v1.4 · 85 s

> We baselined this document at the end of April and it's been through four revisions since. April is on the left, today is on the right.
>
> Five IDs were added, and all five came from ETIM.

Point down the table as you name each one.

> HLR-6 is the high-level one: classify each product against ETIM, and tag its attributes with ETIM identifiers — class, feature, value and unit — while keeping the supplier's own values as evidence.
>
> Then two functional requirements. FR-9 is matching: the ML service maps each attribute onto an ETIM class, an ETIM feature, and a controlled value and unit, with a confidence on every assignment. FR-10 is the reference data: load and maintain the ETIM dictionary itself.
>
> DR-4 follows from HLR-6: anything we publish to PIMS is keyed by those identifiers. And C-4 is the constraint — we target release 10.0 and don't adopt later ones.
>
> Eighty-nine percent of what we wrote in April is untouched. Two requirements were rewritten, both in ingestion. We'd said normalization would do the ETIM keying, and that was wrong.
>
> The fourth revision was cleanup. We put ETIM into the requirements in June and didn't go back to the quality scenarios or the validation tests. So for a month those two sections described a system we weren't building. Version 1.4 fixed that.

---

## Slide 17 — How we managed the change · 62 s

> Every time ETIM added something we gave it a new ID instead of editing an old one. We renumbered nothing, so every trace link from April still resolves.

Walk the chain with your hand. One box per beat. Do not rush this.

> Here's one, end to end. Classification, HLR-6. It drives FR-10, load and maintain the ETIM dictionary. That's decided in ADR-13, where we made the dictionary release-versioned reference data owned by ingestion. It's implemented as the ten ETIM tables in the database. And it's validated by ten unit tests on the loader, all passing.
>
> Requirement, requirement, decision, code, test. It closes at both ends.
>
> The one that doesn't close yet is matching itself, FR-9. It's decided in ADR-16, its test is written, and the test can't run until the code exists. So it's recorded as not run rather than quietly left out.
>
> ETIM is on the risk register as RISK-ARCH-09. Pinning the release means the catalog goes stale, and somebody has to own that after we leave.

---

## Slide 18 — How the architecture changed · 55 s

Let them look at both diagrams for a beat before you start.

> Left is May, right is now. Side by side they're almost the same drawing.
>
> One box is new. Everything else is where it was — same pipe-and-filter structure, same audit trail. Routing still works attribute by attribute, and a person still reviews anything the system isn't sure about.
>
> ETIM was a large change and it didn't force a restructure. That's QAS-1, our modifiability scenario, and this is the first change big enough to test it.
>
> Five things changed, and only one of them shows up on the drawing. The other four are inside components. The dictionary we load, the split that keeps the supplier's raw values separate in staging, the handoff format to ML, and the PIMS key.

Point at the new box on the right-hand diagram.

> The new box is ETIM matching. It sits behind attribute matching, inside the same interface. That's the next slide.

---

## Slide 19 — Inside the new box · 78 s

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

## Slide 20 — Decisions, and what we chose against · 68 s

> Four decisions, and next to each one the alternative we rejected. The ADR is in the left column.
>
> ML does all the matching — that's ADR-16. The alternative was doing the ETIM lookup during normalization, which is what our spec said until version 1.3. It doesn't work, because an ETIM assignment carries a confidence and sometimes needs a person to approve it, and normalization has neither.
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
| Slide 16 | 212 | 85 s |
| Slide 17 | 154 | 62 s |
| Slide 18 | 137 | 55 s |
| Slide 19 | 195 | 78 s |
| Slide 20 | 170 | 68 s |
| **Total** | **912** | **6:04** |

**Read as written this runs 6:04, so the cuts below are not optional.** Spelling the five
requirements out costs about 50 seconds and it's what the panel asked for, so the time comes
from elsewhere. All four cuts land you at 5:05; drop the loader detail on slide 17 as well and
you're at 5:00.

| Cut | Saves |
|---|---|
| Slide 16, the paragraph about the June gap | 17 s |
| Slide 16, DR-4 and C-4 — name them instead of reading them: "plus a derived requirement for the PIMS key, and a constraint pinning us to release 10.0" | 22 s |
| Slide 18, the list of the other four changes, keeping "only one of them shows up on the drawing" | 12 s |
| Slide 20, the raw-values line — slide 18's list already names it | 8 s |

**Don't cut** HLR-6, FR-9 or FR-10 on slide 16, the trace walk on slide 17, the valve example
on slide 19, or the dashed-boxes line. The first three are what the panel asked to hear; the
last two carry the rubric language.

## Delivery notes

- **Slide 16 is now the glossary.** Say the ID, then immediately what it means — "HLR-6 is the new high-level requirement: classify each product against ETIM." Never say a bare ID and move on; that's the thing they called out.
- Slide 17 works *because* slide 16 defined the IDs first. By the time you walk the chain you can say "HLR-6" and "FR-10" as shorthand, because the room already knows them. Don't re-define them here.
- Slide 17 is the rubric slide. Hand moves, name the box, hand moves again. The pauses come from your hand, which is what stops it sounding recited.
- Slide 18, the two thumbnails are a silhouette comparison. Don't invite anyone to read them, and don't tell them what to conclude — the near-identical outline does that on its own. The full diagram is the backup slide at the end if anyone asks.
- Slide 19 is the one slide where you're explaining a design decision rather than reporting one. Slow down on the valve example. Name the two valves clearly and let the panel picture it before you land the consequence.
- Say the dashed part on 19 plainly and move on. It's on 19 and again on 20, so once out loud is enough.
- Every paragraph break in the script is a breath. If you run two together you'll start to sound like you're reciting, regardless of the wording.
- The ten unit tests were run on 29 July and all passed, in about 3m40s (`pytest tests/unit/test_etim_loader.py` in `e2e-ocr-ing`). The integration test skips unless `.tmp_etim_csv` is present, and it is gitignored — so if anyone runs the suite in front of you, expect `10 passed, 1 skipped`. Say the skip before they ask.
- If asked who wrote the documents: the agents drafted them, we reviewed and finalised them. Wiring that into the automated pipeline is still open work. That answer holds up if anyone goes and looks at the repo.

## Questions you'll probably get

**What's the difference between FR-9 and FR-10?**

> FR-10 is the vocabulary — load and maintain the ETIM dictionary, 5,640 classes and 17,377 features, for the release we're pinned to. FR-9 is using it: taking a supplier attribute and matching it onto a class, a feature and a controlled value, with a confidence. FR-10 is built and tested. FR-9 is designed and not built.

**Your chain shows ADR-13, but the decisions table says 16 for matching.**

> Different requirements. The chain walks FR-10, the dictionary, and ADR-13 is the decision that made it release-versioned reference data owned by ingestion. ADR-16 is matching — that's the row in the decisions table, and it's the thread that isn't built yet. ADR-18 is a third one: it extends routing to ETIM signals and adds the class-review-first path you saw on the previous slide.

**Slide 17 lists FR-9 in the new IDs, but the chain doesn't walk it.**

> Deliberately. FR-9 is matching, and it isn't built, so walking it would break at the implementation step. FR-10 closes all the way to a passing test, so that's the one I walked. FR-9's validation test is written and recorded as not run.

**Ten tests? Slide 12 said 106 and slide 14 said 638.**

> Different scopes. Ten is the unit suite on the ETIM loader specifically, which is the code at the end of that trace. The larger numbers are the full suite across the repo.

**Doesn't ingestion do the ETIM keying?**

> No. Our spec did say that until version 1.3. Ingestion cleans the data and keeps the supplier's own values. All the matching is in ML, attributes first, then ETIM. It can't sit in normalization because an ETIM assignment has a confidence attached and might need a person to confirm it, and normalization has neither. Ingestion does load the dictionary, because it already owns file parsing and migrations, but it doesn't use it.

**Why not keep up with new ETIM releases?**

> Because doing it properly is real work. You'd have to diff the new release against the old one, re-match every affected product, and review everything that came out different. None of that gets exercised before we finish, and nobody has decided who signs off an upgrade. So we wrote it into the spec as a constraint, and onto the risk register as RISK-ARCH-09. We did keep the release ID on every row, so any published value still says which version of ETIM it was matched against.

**How do you know the architecture is stable?**

> Two things. Eighty-nine percent of the April requirements are untouched, and the biggest change we've had all summer landed without moving the pipe-and-filter structure or breaking a trace link. That's what QAS-1 predicted, and this is the first time we could check it against something real.

**Is it Prometheus or Datadog?**

> Both, deliberately. Datadog is the production target and that's what the ADR says. Prometheus and OpenTelemetry are what the local development environment runs. Our own assessment document read the code without knowing the deployment intent and flagged it as a contradiction, which is why the current diagram labels both.
