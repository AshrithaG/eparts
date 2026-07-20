---
name: defect-triage
description: Turn a CI failure log, PR review finding, or bug report into a fully-triaged EPARTS Jira Bug — severity, stage-found, root-cause, found-by labels, module tag, and requirement link — following docs/defect_management.md. Use whenever something broken is found and needs tracking. Assumes the caller is authenticated to epartsmse.atlassian.net via the claude.ai Atlassian connector.
user-invokable: true
args:
  - name: finding
    description: "The raw material: paste a CI log excerpt, PR review comment, failing test output, or a plain-English bug description. If omitted, the skill asks."
    required: false
---

# Defect triage — EPARTS

Create one correctly-classified Bug in the EPARTS Jira project from whatever
evidence the caller pastes. The classification scheme is defined in
`docs/defect_management.md` (the defect management spec) — this skill is its
assist-tier automation: **AI drafts the triage, the human confirms, then the
ticket is created.** Never create the ticket without explicit confirmation.

## Constants (do not ask the user for these)

```
cloudId          = 1b3fa01d-9ef5-428f-93b5-429405fe9466
projectKey       = EPARTS
site             = https://epartsmse.atlassian.net
issueTypeName    = "Bug"
```

Label vocabularies (exactly these — never invent new label values):

- stage found: `found-spec` `found-build` `found-review` `found-ci` `found-integrated` `found-client`
- root cause:  `rc-logic` `rc-data` `rc-interface` `rc-config` `rc-requirements` `rc-env` `rc-prompt`
- found by:    `by-test` `by-ci` `by-human-review` `by-ai-review` `by-client`
- module:      `mod-ingestion` `mod-normalization` `mod-prediction` `mod-routing` `mod-review-queue` `mod-writeback` `mod-publish` `mod-audit` `mod-retraining` `mod-monitoring` `mod-ses` (team tooling/CI itself)

Severity → Jira priority: S1 → `Highest`, S2 → `High`, S3 → `Medium`, S4 → `Low`.

## Steps

### 1. Preflight — auth
Call `mcp__claude_ai_Atlassian__atlassianUserInfo`.
- If it errors → STOP and tell the caller: "Not connected. Run `/mcp`, select
  **claude.ai Atlassian**, authorize, then re-run `/defect-triage`."
- Keep `account_id` — the Bug is assigned to the caller (they own shepherding
  it through triage, not necessarily the fix).

### 2. Gather the finding
Use the `finding` arg, or ask for it. Accept anything: CI log, stack trace,
review comment, one-line description. If the finding is vague, ask at most
TWO clarifying questions (typically: "where was this found?" and "what did
you expect instead?") — then proceed with stated assumptions rather than
interrogating.

### 3. Draft the triage
From the finding, draft ALL of:

- **summary** — imperative, specific, ≤ 90 chars ("Routing accepts NaN
  confidence as auto-accept" not "bug in routing")
- **severity** — per docs/defect_management.md §2. Default S3 when honestly
  unsure; S1 ONLY for red main-branch CI or wrong-data-toward-staging.
- **stage found / root cause / found by** — one label each from the
  vocabularies. `rc-prompt` when a prompt/context produced a wrong artifact
  though code and model behaved.
- **module** — one `mod-*` label (Quality Plan §3 modules; `mod-ses` for
  team-tooling defects).
- **threatened QA goal** — `qa-goal-1` … `qa-goal-7` label when it maps to a
  Quality Plan §2 goal; omit when none fits.
- **description** — use the template from docs/defect_management.md §1
  (Observed / Expected / Repro / Threatens / Source). Quote the pasted
  evidence in the Observed block; include links the caller provided.

### 4. Duplicate check
`searchJiraIssuesUsingJql` with
`project = EPARTS AND issuetype = Bug AND statusCategory != Done AND text ~ "<2-3 keywords>"`.
If a likely duplicate exists, show it and ask: comment on the existing Bug
instead, or proceed with a new one?

### 5. Confirm with the caller
Present the full draft (summary, severity, all labels, description) in one
block. Proceed ONLY on explicit yes. Apply any corrections they give —
their judgment overrides the draft (that is the point of the human tier).

### 6. Create
`mcp__claude_ai_Atlassian__createJiraIssue` with:

```
cloudId             = constant above
projectKey          = "EPARTS"
issueTypeName       = "Bug"
summary             = <summary>
description         = <template-formatted description>
contentFormat       = "markdown"
assignee_account_id = <account_id from step 1>
additional_fields   = {
  "priority": { "name": <"Highest"|"High"|"Medium"|"Low"> },
  "labels":   [<stage>, <root-cause>, <found-by>, <module>, <qa-goal if any>, "defect"]
}
```

Do not set sprint or due date. If a `priority` field error comes back
(team-managed projects sometimes hide it), retry once without the priority
field and put `S1`/`S2`/`S3`/`S4` at the start of the summary instead.

### 7. Report
Print: key, summary, severity, the four labels, and the browse link
(`https://epartsmse.atlassian.net/browse/EPARTS-xxx`). Remind the caller of
the response norm for the severity (S1: today; S2: this tick; S3: next tick;
S4: backlog).

## Rules

- Never create without step-5 confirmation; never invent label values.
- One finding = one Bug. If the paste contains several distinct defects, say
  so and triage them one at a time.
- Findings already fixed in the same PR do not get tickets (intake rule §3.2
  of the spec) — tell the caller if their paste looks like one.
- If the caller disputes the drafted severity, take theirs — record, don't argue.

## Example invocation

`/defect-triage the coverage gate failed on master: Required test coverage of 85.0% not reached. Total coverage: 84.86%`

→ drafts: S1 `found-ci` `by-ci` `rc-config` `mod-ses` "CI coverage gate fails on master: 84.86% < 85% floor", confirms, creates, reports the key.
