# Defect Management — eParts / Pimsie Supreme

**Status:** Adopted 2026-07-20 · **Owner:** QA practice (Jai) · **Board:** Jira `EPARTS`
**Companion docs:** Quality Plan (Draft 7), `docs/etvx_manifest.yaml`, `Metamodel_framework.md`

The Quality Plan defines *what must be true* (QA-1…QA-7) and *which tests prove
it* (T-x.y). This document defines what happens when something is **found
broken anyway**: one managed loop from discovery to closure, with metrics that
tell us whether quality is improving — instead of ad-hoc Slack messages and
memory.

Design constraints: zero new tools (Jira only), low ceremony (labels over
custom fields), and every number derivable from a JQL query so the metrics
have provenance.

---

## 1. The defect record

Every defect is a Jira **Bug** in `EPARTS`, classified on four axes at triage:

| Axis | Where it lives | Values |
|---|---|---|
| **Severity** | Jira Priority field | see §2 |
| **Stage found** | label | `found-spec` · `found-build` · `found-review` · `found-ci` · `found-integrated` · `found-client` |
| **Root cause** | label | `rc-logic` · `rc-data` · `rc-interface` · `rc-config` · `rc-requirements` · `rc-env` · `rc-prompt` |
| **Found by** | label | `by-test` · `by-ci` · `by-human-review` · `by-ai-review` · `by-client` |

Plus: **component/module** (the Quality Plan §3 module it belongs to, as a
label, e.g. `mod-prediction`, `mod-routing`), and a **link** to the
requirement or QA goal it threatens (Jira "relates to" REQ ticket, or
`qa-goal-N` label).

`rc-prompt` is the AI-era root-cause class the classic taxonomies (IEEE
1044-style) don't have: the code was fine, the model was fine — the *prompt or
context* produced the wrong artifact. Tracking it separately tells us whether
our prompt regression suite (golden tests) is earning its keep.

**Bug description template:**

```
**Observed:** what happened (paste CI log / review finding / screenshot)
**Expected:** what should have happened
**Repro:** steps or failing test name; "not reproduced" is allowed at intake
**Threatens:** QA-goal / requirement / module
**Source:** link to CI run, PR comment, or meeting where it surfaced
```

## 2. Severity scale

| Priority | Meaning | Response norm |
|---|---|---|
| **S1 · Highest** | Wrong data could reach staging/PIMS, or main is broken (red CI on main) | Drop current work; fix or revert same day |
| **S2 · High** | A QA goal (QA-1…7) is violated but contained; a milestone is blocked | Fix within the current 7-day tick |
| **S3 · Medium** | Functional defect with a workaround; quality-plan test failing on a branch | Schedule into next tick |
| **S4 · Low** | Cosmetic, docs, style, non-blocking tooling | Backlog; batch up |

## 3. Intake rules — when a Bug MUST be created

1. **Red CI on `main`/`master`** → S1 Bug, `found-ci`, `by-ci`, same day.
   (Red CI on a PR branch is normal work, not a defect — unless it reveals a
   pre-existing problem, then file it `found-build`.)
2. **A PR review finding that is real but not fixed in that PR** → Bug at
   triage severity, `found-review`, `by-human-review` or `by-ai-review`.
   Findings fixed inside the same PR are *not* ticketed (the PR record is the
   audit trail) — no ceremony for things already handled.
3. **A quality-plan test (T-x.y) that fails after previously passing** → Bug,
   linked to the module and QA goal, `found-integrated` if on main.
4. **Client- or mentor-reported problem** → Bug, `found-client`, `by-client`,
   linked to the meeting minutes where it was raised.
5. **A generated SES artifact rejected at human review** (e.g. minutes PR
   needed correction) → *not* a Bug by default; it's a correction counted by
   the artifact-quality measurement. File a Bug only when the cause is
   systematic (`rc-prompt` — the prompt/pipeline needs a fix, not the output).

## 4. Lifecycle

`Open → Triaged → In Progress → In Review → Done` (Jira board columns), with
two rules: an S1/S2 may not sit in `Open` past its next standup, and `Done`
requires the fix merged **and** a regression guard where feasible (test added
or golden case extended) — the G2 pattern: every escaped defect leaves a
tripwire behind.

Triage happens at standup (5 min): confirm severity, add the four labels,
link the requirement, assign. The `/defect-triage` skill (see
`skills/defect-triage/SKILL.md`) drafts all of this from a pasted CI log or
review finding; the human confirms — T2 review tier applied to our own
process.

## 5. Measurements (all JQL-derivable — provenance built in)

| Metric | Definition | Question it answers (GQM) |
|---|---|---|
| **Escape rate** | % of defects `found-integrated` or `found-client` vs. all defects | Are our gates catching problems early? (goal: trend ↓) |
| **MTTR by severity** | mean (resolved − created) per priority | Do we respond proportionally to risk? |
| **Found-by mix** | share of `by-ci` / `by-test` / `by-ai-review` / `by-human-review` / `by-client` | Which detection resources earn their cost? |
| **Root-cause Pareto** | count by `rc-*` label per month | Where should prevention effort go next? (input to tick retro) |
| **Defect density by module** | open+closed Bugs per `mod-*` label | Does testing effort match the Quality Plan §5 HARA ranking? |
| **Reopen rate** | % of Done Bugs reopened | Are fixes real? |

Leading indicators: found-by mix and stage-found distribution (early-stage
finds predict fewer escapes). Lagging: escape rate, reopen rate. Reviewed at
every tick retro; a rising escape rate or a root-cause class exceeding 40% of
a month's defects triggers a process change, not just more fixing.

## 6. Metamodel mapping

- **Process:** defect triage (ETVX: *Entry* — intake rule fires; *Task* —
  classify on four axes + link; *Verification* — human confirms AI-drafted
  triage; *eXit* — labeled Bug on board).
- **Artifact:** the Bug ticket, schema in §1 — a defined, measurable artifact.
- **Resources:** CI (deterministic detector), test suites, AI reviewer +
  `/defect-triage` skill (assist), humans (judgment + approval).
- **Measurements:** §5 — measuring the *process* (MTTR, escape rate), the
  *artifacts* (density, reopen), and the *resources* (found-by mix).

## 7. Bootstrap plan

1. Create the label set + Bug template in Jira (15 min, one person).
2. Backfill the defects we already know about (the ML-repo bugs found and
   fixed this summer — e.g. the G2 online-feedback wiring defect, the CI
   coverage-gate failure) so the board reflects reality, honestly dated.
3. Install `/defect-triage` for all five team members.
4. First metrics read-out at the next tick retro; expect small numbers — the
   point is the loop existing, not big-company volume.
