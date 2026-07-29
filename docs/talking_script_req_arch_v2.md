# Talking script — Requirements & Architecture (5 minutes)

**Speaker:** Arjun · **Picks up from:** Jai (construction, quality, then risk)
**Slides:** `eParts_Section3_SoftwareSystem.pptx`, 4 slides · rebuild with [`build_section3_deck.py`](build_section3_deck.py)
**Links on the slides:** [Engineering System Artifacts](https://cmu-mse.atlassian.net/wiki/spaces/AISDLC/pages/76742657/Engineering+System+Artifacts) (slides 1, 3) — requirements document v1.2 and the v6.0 diagram · [ADR index on GitHub](https://github.com/AshrithaG/eparts/blob/main/docs/adr-index.md) (slide 4) — all 21 ADRs

~620 words, lands around 4:30–5:00. Lines marked **[CUT IF LONG]** can go.

The slides are phrase-level because everything on them is 20 pt or larger, so the sentences live here. Don't read the cards — they're the checkable version of what you're saying.

---

## Handoff — 20 sec

> Thanks Jai.
>
> So I'm going to cover our requirements and our architecture, and where both of them ended up. Two questions really: what changed in the requirements since spring, and what changed in the architecture because of that.
>
> The reason I'm going to keep coming back to ETIM is that it was by far the biggest change we had this summer, and it's what drove both. Jai just had it as one of our top risks — this is the other half of that, which is what it actually did to the system.
>
> I'll show you the artifacts as I go. These were drafted by our agents and then reviewed and finalised by us. Links are on the slides — the requirements document, the architecture diagram, and all 21 ADRs on GitHub — so if you want to look at any of them properly rather than on the screen, you can pull them up.

*[Advance to slide 1]*

---

## Slide 1 — "How the requirements changed" — 70 sec

> So, requirements first.
>
> Originally we were predicting product attributes. Voltage, material, whatever was on the datasheet. It was free-form, the model could output anything.
>
> With ETIM that becomes classification instead. Each product has to get assigned an ETIM class, and then each attribute has to map to a controlled vocabulary, so a class, a feature, an allowed value, and a unit.
>
> **[gesture at the left card]** So the objective picked up industry-standard classification, the function went from prediction to constrained matching, and accuracy is now measured against that vocabulary rather than against free text. We also picked up a requirement type we hadn't had before, FR-10, which is loading and maintaining the ETIM dictionary as reference data.
>
> **[gesture at the right card]** And on the other side, three of our original requirements didn't hold anymore. HLR-2 just said normalize into a standardized structure, which was too vague, so that's ETIM-keyed now. FR-3 said predict attributes, and that's constrained matching, so what we hand the ML team changed. And the flat ingestion record couldn't represent any of this, so we split it into two tables.
>
> The last line there is C-4, which is new as of this week. We're pinning to ETIM 10.0 and we're not going to chase later releases. **[CUT IF LONG]** I'll come back to why on the last slide.
>
> And at the bottom, that's the ETIM 10.0 data we've actually loaded and verified — about 5,600 classes.

---

## Slide 2 — "How we managed the change" — 65 sec

> The main thing here is that we handled ETIM as a change to the existing baseline rather than starting the spec over.
>
> **[gesture at the left card]** So the spec went 1.0 to 1.1 to 1.2, and each version-history entry in the document is the change record. Where we added requirements we gave them new IDs — HLR-6, FR-9, FR-10, DR-4, and then C-4 — and we didn't renumber anything that already existed. That was on purpose, because renumbering would have broken the trace links we already had.
>
> And we used the same process twice. 1.1 was integrating ETIM. 1.2 was pinning the release, which we could have just edited into 1.1 quietly, but that's exactly the thing we're saying we don't do.
>
> **[gesture at the right card]** Two items are blocked on the client and they're worth calling out. ETIM doesn't give you a required-field flag — the file that maps features to classes has no column saying which ones are mandatory. Until the client defines that, we can't write a firm validation requirement for what blocks publishing.
>
> **[CUT IF LONG]** The trace along the bottom runs from HLR-6 through FR-9 and 10 to the tickets and the golden test set. It stops at the ML and OCR contracts on purpose, because we own those requirements but another stream builds them.

---

## Slide 3 — "How the architecture changed" — 95 sec

*Give them a couple of seconds to look before you start.*

> So that's the requirements side. This is what it did to the architecture — before and after. May on the left, current on the right.
>
> The first thing worth pointing out is what stayed the same. The pipe-and-filter structure, per-attribute routing, the human-in-the-loop step, the audit trail. Those all held up through the change, which we take as a decent sign that the original architecture was reasonable.
>
> Five things did change and I'll go through two of them.
>
> **[point at delta 2]** The first is matching. We used to have a single component that did ML attribute matching. That doesn't work under ETIM, because you can't match an attribute until you know the class. The set of legal features is defined per class. So if the class is wrong, every feature under it is wrong too, and it's wrong at high confidence, which means routing won't catch it. That's why matching is now five stages, and why routing has a class-review step before the attribute-level routing.
>
> **[point at delta 3]** The second is that we split staging into two tables. The supplier's original text is evidence, and the ETIM mapping is an interpretation on top of it. Keeping both in one table mixes them up, and then you can't trace a published value back to where it came from.
>
> One more thing on this slide. The outlines mean something. Solid is code that's running, dashed is designed but not built yet. So the reference layer, the staging split and the handoff record are real and they're in migrations 5 through 7. The matching stages aren't built.

---

## Slide 4 — "Decisions, and what we chose against" — 60 sec

> Last slide, the decisions and the alternatives we didn't take. Each of these is an ADR, and rather than walk you through them the link up there goes to all 21 on GitHub.
>
> **[point at row 3]** The one I'd point at first is the third. We didn't go back and edit our April ADRs. They record what we decided in April, so instead we superseded them forward with new ones, and we wrote an assessment document that goes through the old ADRs one by one and says what ETIM affected in each. If we'd edited them in place we'd have lost that history.
>
> **[point at row 4]** And the fourth is the newest one. We're pinning to ETIM 10.0 for the whole project. The alternative was building an upgrade path — a diff against the new release, a bulk re-match, a second review queue — and that's a lot of work for something that won't happen inside this project. On top of that, nobody's decided who authorizes an upgrade, so we couldn't have finished it anyway. We'd rather state the limit than half-build the thing. We do accept that the catalog goes stale relative to ETIM, and that's the trade.
>
> **[CUT IF LONG]** We kept the release ID on every row though, so a published value still says which ETIM release it was matched under. Un-pinning later would be a scope change, not a migration.
>
> And on what's still open, five client decisions, two of which gate validation.
>
> So to close the loop on the two questions — the requirements changed from prediction to constrained classification against a standard, and that's in the spec as version 1.2. The architecture changed in five places, and the spine didn't move. Both of those are linked from the slides.

*[Hand off]*

---

## If you're running out of time

Drop in this order:

1. The three **[CUT IF LONG]** lines — about 40 seconds.
2. Slide 2's version-history-used-twice paragraph. The 1.0 → 1.1 → 1.2 line on the slide carries it.
3. Slide 1's FR-10 sentence. Slide 4's row 4 covers the same territory.

Keep the class-error explanation on slide 3 and the solid-vs-dashed line. Those two are what make it more than a status update.

---

## Delivery notes

- Slide 3 is the one to slow down on. Two diagrams side by side does the work; you're just narrating.
- The cards are phrases, not sentences — say the sentence, don't read the phrase. If you catch yourself reading a card, move on to the next point.
- Say the dashed-outline thing plainly. Volunteering what isn't built lands better than any number on the slide, and the rubric is asking for coherence and traceability at this stage, not completeness.
- On the artifacts: they were agent-drafted and we reviewed and finalised them. If someone asks whether the pipeline generated them end to end, the answer is that the agents drafted them, we reviewed them, and automating that step is still open work. That holds up if they go look at the repo.

## Likely questions

**"Why not keep up with new ETIM releases?"**

> Because the upgrade path is real work — you need a diff against the new release, a bulk re-match of already-classified products, and a second review queue for anything the re-match changes — and none of that gets exercised inside this project. It also isn't finishable: who authorizes an upgrade and what happens to already-published rows are client decisions nobody has made. So we wrote it into the spec as C-4 rather than leaving it unspecified, which means it reads as scope rather than an omission. We did keep the release ID on every reference row and in the PIMS key, so published data still names the release it was matched against, and un-pinning would be a change request against C-4 rather than a schema migration.

**"Your assessment says the stack is Prometheus and OpenTelemetry, but ADR-012 says Datadog. Which is it?"**

> Both, and it's deliberate. Datadog is the production target, which is what ADR-012 says and that still stands. Prometheus, OpenTelemetry and structlog are what the local dev environment runs. The assessment was written from the code without the deployment intent, so it read that as a contradiction and recommended superseding ADR-012. We didn't, and the v6 diagram labels both so it's visible.

Fuller Q&A prep: [`studio-req+arch.md`](studio-req+arch.md#qa-prep).
