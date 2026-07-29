# SES ↔ Product Repo Integration

**Status:** Proposed (team decision pending) · **Owner:** Ashritha (Engineering System) · **Date:** 2026-07-27
**Companion docs:** [`Metamodel_framework.md`](../Metamodel_framework.md), [`agentic-augmented-scrum.md`](../agentic-augmented-scrum.md), [`defect_management.md`](defect_management.md), [`evals.md`](evals.md)

---

## 1. The principle: the harness is not the product

The engineering system is a **harness that operates on the product repo from the
outside**. It is versioned, tested, and deployed as its own system; the product
repo stays clean and shippable.

| | Repo | Hosts | CI |
|---|---|---|---|
| **Harness (this repo)** | `AshrithaG/eparts` | agents, prompts, orchestrator, evals, linters, QA interfaces, dashboards | GitHub Actions |
| **Product** | `epartsservices/intelligent-attribute-prediction` | the ML attribute-prediction system delivered to eParts | Bitbucket Pipelines |

This separation is the reason the harness can be changed aggressively — new
agents, new prompts, new gates — without any of that churn touching client
deliverables.

## 2. Decision: integrate by configuration, not migration

**Decision.** Keep the SES in its own repo and have it act on the product repo
through the Bitbucket API client (`mcp/bitbucket.py`).

**Alternatives considered and rejected:**

| Option | Rejected because |
|---|---|
| **Migrate the SES into the product repo** | Puts team-process tooling — coach-session memory, meeting-transcript pipelines, program-health dashboards — inside the client's deliverable, degrading handover. The client bought an attribute-prediction system, not our project management. |
| **Duplicate the SES into both repos** | Two copies of every agent and prompt diverge immediately; the prompt registry's whole purpose is one reviewed version per prompt. |
| **Rebuild the SES natively on Bitbucket Pipelines** | Throws away working GitHub Actions workflows and couples the harness to one CI vendor. The harness should be portable across product repos, because the *next* project will have a different one. |
| **Keep them fully disconnected (status quo)** | The engineering system then governs only its own artifacts, and cannot see or act on the code it is supposed to govern. This is the gap being closed. |

**Consequence being accepted:** two CI platforms to understand. Mitigated by
keeping the boundary narrow — the harness talks to the product repo over one
documented API client, not through shared build config.

## 3. What crosses the boundary

`mcp/bitbucket.py` is the single crossing point. It exposes `get_pr_status`,
`add_pr_comment`, `open_pr`, `create_branch`, and `commit_file`, configured by
three environment variables (see `.env.example`):

```
BITBUCKET_WORKSPACE=epartsservices
BITBUCKET_REPO=intelligent-attribute-prediction
BITBUCKET_TOKEN=<PR read + comment scope>
```

Agents that act on the product repo once configured:

| Agent | Acts on the product repo by | Human gate |
|---|---|---|
| `pr_reviewer` | Commenting on every product PR (style, test coverage, REQ traceability, API surface) | Comment-only; never merges |
| `drift_detector` | Flagging product changes that diverge from the documented architecture | Raises for review |
| `traceability_builder` | Linking product PRs to requirements and decisions in the traceability graph | Read-only |
| `test_review_agent` | Reviewing whether product tests cover sad paths and whether coverage is meaningful | Comment-only |

Everything else in the harness (transcripts, coach memory, requirements
extraction, program health) operates on project artifacts and Jira, and never
touches product code.

## 4. Staged rollout, gated on safety

Integration is deliberately staged, because the product repo is shared team
property and agent write access to it is not reversible by a single person.

| Stage | Grants | Precondition |
|---|---|---|
| **1. Observe** | PR read | none — safe today |
| **2. Advise** | PR read + comment | team agreement that agent comments are welcome on their PRs |
| **3. Propose** | branch create + commit to a **feature branch**, PR opened for human review | **SES005 fixed** (below) |
| **4. — (not planned)** | direct commit to `main` | never; violates the human-approval rule |

**SES005 is a hard precondition for stage 3.** `commit_file()` defaults to
`branch="main"` (`mcp/bitbucket.py:52`, `mcp/github.py:74`), and seven agents
call it without naming a branch. A write-scoped token today would let an agent
commit directly to the team's `main` with no PR and no human approval — which
contradicts this system's core rule. The custom linter
(`python3 tools/lint_ses.py --strict`) reports every affected call site, and this
finding is exactly the kind of implementation-drift-from-stated-policy that
deterministic tooling is supposed to catch.

## 5. Process definition (ETVX)

**Process:** *Product-change governance* — the harness observing and advising on
a product-repo change.

- **Entry:** a PR is opened in `epartsservices/intelligent-attribute-prediction`.
- **Task:** `pr_reviewer` posts a structured review; `traceability_builder` links
  the PR to the requirement or decision it implements; `drift_detector` compares
  the change against the documented architecture; `test_review_agent` assesses
  test meaningfulness.
- **Verification:** a human reviewer reads the agent output alongside the diff.
  Agent output is advice, never authority — the tier policy in
  `agentic-augmented-scrum.md` (T1/T2/T3) sets how much human review the change
  requires, indexed to its risk.
- **eXit:** the PR is merged by a human, with the traceability link recorded and
  any agent-raised concern either addressed or explicitly dismissed.

## 6. Measurements

All derivable without new instrumentation:

| Measurement | Source | Question it answers |
|---|---|---|
| Product PRs receiving agent review | Bitbucket PR comments by the agent account | Is the harness actually reaching the product? |
| Agent comments that led to a code change | PR comment → subsequent commit in the same PR | Is the review useful, or noise? |
| Product PRs linked to a requirement | traceability graph vs. total merged PRs | Can we still trace code to intent? |
| Drift findings per tick | `drift_detector` output | Is the implementation diverging from the architecture? |
| Stage-3 blockers outstanding | `tools/lint_ses.py --strict` violation count | Are we safe to grant write access yet? |

## 7. Metamodel mapping

- **Process:** product-change governance (§5), as ETVX, with the human
  verification step explicit.
- **Artifacts:** the product PR, the agent review comment, the traceability link,
  the drift finding. Each is a defined, inspectable artifact.
- **Resources:** the Bitbucket MCP client, the four agents above, CI on both
  sides, and human reviewers holding the tier-appropriate authority.
- **Measurements:** §6 — measuring reach (is it connected), usefulness (does
  advice change outcomes), and safety (are write preconditions met).
- **Context management:** the harness supplies agents with the requirement,
  decision, and architecture context a product PR relates to — which is what
  makes the review specific to *this* system rather than generic.

## 8. Provenance

The harness/product separation and the staged-trust rollout follow the AI-tools
coaching session with **Cory Gwin** (Senior Software Engineer, GitHub Copilot),
2026-07-24 — specifically his framing that trust should be a function of risk,
that loop tightness is the control, and that a building harness is a distinct
artifact whose quality is measured by what it lets you ship correctly the first
time.
