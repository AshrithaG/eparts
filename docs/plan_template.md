# Implementation Plan Template

**Status:** Adopted 2026-07-24 · **Process:** `docs/spec_to_plan_process.md`
**Produced by:** `agents/planning/plan_generator.py` (prompt: `prompts/plan_generator.txt`)

Every spec gets a plan before any code is written. The plan answers *how this
is built in this codebase* — not *what the feature is*. It is reviewed and
accepted or rejected by a human while changing the design is still cheap.

Keep it to one page-ish. If a section genuinely does not apply, write
"none — <reason>"; do not delete the heading.

---

## 0. Header

| Field | Value |
|---|---|
| **Plan ID** | `PLAN-YYYY-MM-DD-<slug>` |
| **Spec / work item** | link or path (Jira key, `requirements/…`, spec file) |
| **Planning model** | model that produced this plan (frontier tier) |
| **Implementation tier** | `cheap` \| `frontier` — which tier may implement it |
| **Status** | `draft` → `awaiting review` → `approved` \| `rejected` |

## 1. Work summary

2–4 sentences: what the work is, and what "done" looks like. Restated in the
planner's words — a summary that just echoes the spec is a signal the spec was
not understood.

## 2. Clarifying questions (the "Grill Me" step)

Every question the planner needed answered *before* planning, each marked
**blocking** (a wrong guess changes the design) or **non-blocking**.

| # | Question | Blocking? | Why it matters | Answer / assumption |
|---|---|---|---|---|

A plan may not be written while a blocking question is unanswered. Assumptions
recorded here are the ones a reviewer must check hardest.

## 3. Files to change — and how

| File | Change | What changes | Why |
|---|---|---|---|
| `path/to/file.py` | new / modify / delete | the specific edit, not "update logic" | which part of §1 it serves |

Real paths only. A path the planner invented is a rejection reason.

## 4. Code structures supporting the feature

What has to exist for the feature to be expressible: data schemas, dataclasses,
config keys, prompt files, DB tables/migrations, interfaces, events, CLI entry
points. For each: name, kind, where it lives, and its purpose.

## 5. Class / module breakdown

For each class or module introduced or materially changed:

- **Name + module** — where it lives
- **Responsibility** — one sentence; if it needs "and", consider splitting
- **Key methods** — name, signature, what it does
- **Collaborators** — what it calls / what calls it (existing code included)

## 6. Required tests — and what each one proves

| Test | File | Level | What it tests | Fails when |
|---|---|---|---|---|
| `test_…` | `tests/…` | unit / integration / regression | the behaviour it pins down | the concrete break it catches |

Rules: every item in §3 traces to at least one test here; every test states the
failure it catches ("tests the happy path" is not an entry); tests named here
are the definition of done for the implementation step.

## 7. Implementation sequence

Ordered steps a cheaper model can follow without re-deriving the design.
Each step should be independently verifiable (compiles / test passes).

## 8. Out of scope

What this plan deliberately does not do, so the implementer does not drift into
it and the reviewer does not expect it.

## 9. Risks

| Risk | Mitigation |
|---|---|

## 10. Stop conditions

When the implementing agent must stop and hand off to a human instead of
trying again. Be specific — these are the conditions the team kept getting
wrong when work was under-specified.

| Condition | Action |
|---|---|
| e.g. a planned test cannot be made to pass without changing a file not in §3 | stop; return to plan review |
| e.g. two consecutive failed attempts on the same step | stop; escalate with the failing output |

## 11. Review gate

- [ ] **Accepted** — organization, class breakdown, and test set are right; implementation may start (at the tier in §0)
- [ ] **Rejected** — reason: `organization` \| `missing-tests` \| `wrong-files` \| `scope` \| `unanswered-ambiguity`

Reviewer: ______ · Date: ______ · Time spent: ____ min

Rejection is cheap and expected — it is the point of the gate. Record the
reason; the reasons are a measured input to prompt and process improvement
(see `docs/spec_to_plan_process.md` §7).
