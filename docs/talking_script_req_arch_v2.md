# Talking script — Requirements & Architecture (5 minutes)

**Speaker:** Arjun · **Picks up from:** Jai (construction, quality, then risk)
**Slides:** `eParts_Section3_SoftwareSystem.pptx`, 4 slides · rebuild with [`build_section3_deck.py`](build_section3_deck.py)
**Links on the slides:** [Engineering System Artifacts](https://cmu-mse.atlassian.net/wiki/spaces/AISDLC/pages/76742657/Engineering+System+Artifacts) (slides 1, 3) — requirements document v1.3 and the v6.0 diagram · [ADR-018 on GitHub](https://github.com/AshrithaG/eparts/blob/main/docs/0018-extend-routing-to-etim-signals-with-class-review-first.md) (slide 4) — the ADR we open live; the other 20 are in the same folder, indexed in [`adr-index.md`](adr-index.md)

**786 spoken words — 5:14 at 150 wpm.** Counted from the blockquotes, not estimated. Everything in a blockquote is what you say; anything outside one is a cue. There is no slack — if you ad-lib a sentence, drop one.

The slides carry phrases because everything on them is 20 pt or larger. The sentences live here. Don't read the cards; they're the checkable version of what you're saying.

---

## Handoff — 28 sec

> Thanks Jai.
>
> So I'm covering requirements and architecture — two questions. What changed in the requirements since spring, and what changed in the architecture because of it.
>
> I'll keep coming back to ETIM because it drove both. Jai just had it as a risk; this is what it did to the system. Artifacts are linked on the slides if you'd rather read them than watch the screen.

*[Advance to slide 1]*

---

## Slide 1 — "How the requirements changed" — 58 sec

> Requirements first.
>
> Originally we predicted product attributes — voltage, material, whatever was on the datasheet. Free-form; the model could output anything.
>
> ETIM makes that classification. Every product gets an ETIM class, and every attribute maps to a controlled vocabulary — class, feature, allowed value, unit.
>
> **[the table]** Nineteen requirements at baseline, twenty-four now. Five new IDs — the ETIM classification requirement, two functional ones for matching and for the dictionary, the PIMS key, and the constraint pinning the release.
>
> **[89%]** But only two of the original nineteen got rewritten, and that's the number I'd point at — HLR-1 on ingestion channels, and HLR-2 on normalization. Everything else still stands as written in April.
>
> **[37%]** Churn is 37 percent against the baseline, which sounds like a lot until you see that five of the seven changes are additions rather than rewrites.
>
> HLR-2 is worth a word because we got it wrong first time. We wrote it as though normalization produced the ETIM-keyed rows. It doesn't — that's a matching decision with a confidence attached, so it belongs to ML. We corrected it in 1.3.

---

## Slide 2 — "How we managed the change" — 51 sec

> The point of this slide is that we handled ETIM as a change to the baseline, not a restart.
>
> The spec went 1.0 to 1.1 to 1.2 to 1.3, and each version-history entry is the change record. New requirements got new IDs and we renumbered nothing, because renumbering breaks every trace link you already have.
>
> Three revisions in a week, and two of them were us correcting ourselves. That's deliberate — none of it got quietly edited back into 1.1.
>

---

## Slide 3 — "How the architecture changed" — 88 sec

*Pause two seconds before you start. This slide carries the section.*

> That's requirements. This is what it did to the architecture — May on the left, now on the right.
>
> First, what didn't change. Pipe-and-filter, per-attribute routing, the human in the loop, the audit trail — all of it survived, which we take as a sign the April architecture was sound.
>
> Five things changed. Two matter.
>
> **[delta 2]** Matching — specifically where it sits. ML already did attribute matching; that's unchanged. ETIM adds a second phase behind it, in the same module: once you know the attribute, you match the product to a class, the attribute to a feature in that class, and the value to an allowed value and unit.
>
> It has to be that order, because the legal features are defined per class. So if the class is wrong, every feature under it is wrong, and it's wrong at high confidence — which means routing won't catch it. That's why there's a class-review step in front of attribute routing.
>
> **[delta 3]** And staging split in two. Supplier text is evidence; ETIM is an interpretation over it. One table mixes them and you lose the ability to trace a published value back to its source.
>
> Last thing — the outlines. Solid is running code, dashed is designed and not built. Reference layer, staging split and handoff record are real, in migrations 5 through 7. The matching stages aren't.

---

## Slide 4 — "Decisions, and what we chose against" — 51 sec

> Last slide — each decision beside the alternative we turned down. Every one of these is an ADR.
>
> **[row 3]** The one I'd defend hardest is the third. We didn't edit our April ADRs — we wrote new ones and left the old ones alone, plus an assessment that goes through them and says what ETIM affected in each. Editing in place would have lost the history of what we believed and when.
>
> **[row 4]** And the fourth. We're staying on ETIM 10.0 rather than building an upgrade path — a diff against each new release, a bulk re-match, a second review queue. That's a lot of work for something that won't happen inside this project, and nobody's decided who authorizes an upgrade anyway. Five client decisions are still open, and two of them gate validation.
>
> And five client decisions are still open — two of them gate validation. The biggest is that ETIM ships no required-field flag, so until the client tells us which features are mandatory we can't write a firm validation requirement.

---

## ADR walkthrough — 31 sec

Open the slide-4 link. **Scroll, don't read.** You are showing the *shape* of the artifact, not its contents.

> Let me open one so you can see the format. This is the routing ADR.
>
> Context, then the alternatives we rejected and why. Then the decision — this table, every routing signal and what it does. The rule underneath is the actual content: **validation and policy failures are not overridden by high confidence.** Then consequences, including the ones that cost us, and it traces back to the requirements at the bottom.
>
> There are 21 of these, and they all look like this.

*Then close it and hand off.*

**Why this one:** it's where the "confidently wrong" argument from slide 3 becomes a concrete design rule, so it pays off something they've already heard rather than opening a new topic at the end.

---

## If you're over time

Measured, not estimated. Drop in this order:

| Cut | Saves |
|---|---|
| The ADR walkthrough down to one sentence — *"the decision is this table, and the rule is that validation failures aren't overridden by high confidence"* | ~18 s |
| Slide 2's "three revisions in a week" paragraph — the 1.0 → 1.1 → 1.2 → 1.3 line on the slide carries it | ~14 s |
| Slide 1's HLR-2 correction | ~20 s |
| Slide 4's row-4 paragraph, keeping only *"we're pinned to ETIM 10.0 for the project"* | ~22 s |

All four gets you to roughly 3:30.

**Never cut:** the class-error argument on slide 3 ("wrong at high confidence, so routing won't catch it") and the solid-vs-dashed line. Those are what make this more than a status update. If you have to choose between the HLR-2 correction and the ADR walkthrough, keep HLR-2 — owning a requirement you got wrong is stronger evidence of change control than showing a template.

---

## Delivery notes

- Slide 3 gets the pause and the slower delivery. Two diagrams side by side does the work; you narrate.
- The cards are phrases. Say the sentence, don't read the phrase.
- Say the dashed-outline line plainly. Volunteering what isn't built lands better than any number on the slide.
- On the artifacts: agent-drafted, reviewed and finalised by us. If asked whether the pipeline generated them end to end — the agents drafted, we reviewed, and automating that step is still open. That holds up if they check the repo.

## Likely questions

**"Doesn't ingestion do the ETIM keying?"**

> No — ingestion does mechanical cleanup and keeps the supplier's own values as evidence. All matching is ML: attribute matching, then ETIM matching. It can't sit in normalization because an ETIM assignment carries a confidence and may need a human to confirm it, and normalization has no model and no route to review. Ingestion loads the dictionary because it already owns file parsing and migrations, but it doesn't use it. Our v1.1 spec did read the other way — that was wrong, and 1.3 corrects it.

**"Why not keep up with new ETIM releases?"**

> Because the upgrade path is real work — a diff against the new release, a bulk re-match of already-classified products, and a second review queue for whatever the re-match changes — and none of it gets exercised inside this project. It also isn't finishable: who authorizes an upgrade and what happens to already-published rows are client decisions nobody has made. So we wrote it into the spec as C-4 rather than leaving it unspecified. We did keep the release ID on every row, so published data still names the release it was matched against, and un-pinning would be a change request rather than a schema migration.

**"Prometheus or Datadog?"**

> Both, deliberately. Datadog is the production target — ADR-012, still stands. Prometheus, OpenTelemetry and structlog are what the local dev environment runs. Our own assessment doc read the code without the deployment intent and called it a contradiction; the v6 diagram labels both.

Fuller prep: [`studio-req+arch.md`](studio-req+arch.md#qa-prep)