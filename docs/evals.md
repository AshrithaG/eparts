# Agent Evals

**Status:** Adopted 2026-07-27 · **Owner:** Ashritha (Engineering System) · **Harness:** [`evals/`](../evals)
**Companion docs:** [`Metamodel_framework.md`](../Metamodel_framework.md), [`defect_management.md`](defect_management.md), [`ses_product_repo_integration.md`](ses_product_repo_integration.md)

---

## 1. Why

Deterministic tooling — types, linters, coverage, security scanning — covers
deterministic failure. Agents are not deterministic: the same prompt can produce
different output tomorrow, and an agent can quietly *lose* an ability it used to
have when a prompt, a model, or a routing table changes.

Evals close that gap. The practice and its priority come from the AI-tools
coaching session with **Cory Gwin** (Senior Software Engineer, GitHub Copilot),
2026-07-24, where it was his single strongest recommendation. His framing:

> For a given skill, define scenarios and validate that the agent calls the
> correct tools and skills under each. Agents are non-deterministic, so evals
> establish whether behaviour holds under known conditions. **The key benefit is
> regression detection — knowing whether an agent has lost an ability it
> previously had.**

This also closes a gap we had already identified in our own measurement system:
every metric we tracked was a *process* metric (time saved, handoff time, rework
rate). None of them measured whether the output was actually any good.

## 2. What existed before, honestly

`agents/knowledge/prompt_regression.py` already had the *mechanism*: golden
cases, a scoring function, baselines, and a rule to block a PR when quality drops
more than 10%. But it never called a model — it scored the golden *input* against
the expected structure as a proxy (see its `_run_regression_tests`, "use input as
a proxy to validate the framework works"), and no baseline file had ever been
written. So it validated that golden data was self-consistent; it did not
evaluate agent behaviour.

We had the machinery and not the practice. The harness in `evals/` is the
practice.

## 3. Two tiers, so the cheap one can block

| Tier | Evaluates | Needs a model? | Runs |
|---|---|---|---|
| **`routing`** | Which agents the orchestrator dispatches for a trigger — membership, ordering, and isolation of manual overrides | No | Every PR, blocking |
| **`skill_selection`** | Whether a skill picks the correct tools and emits labels from its controlled vocabulary | Yes, for the full check | On demand (`--live`) |

The routing tier executes the real `orchestrator.router.resolve_agents` against
declared expectations, using nothing but the standard library — so it is cheap
enough to gate every push. The skill tier validates its own contract offline
(every expected label must exist in the vocabulary; every named tool must exist
in the tool surface) and additionally runs the model under `--live`.

**Scenarios marked `critical` encode required capabilities.** A critical failure
fails the run regardless of the aggregate score, and the report names the missing
ability rather than just reporting a lower number.

## 4. Running it

```bash
python3 -m evals.runner                    # offline tiers (blocking gate)
python3 -m evals.runner --live             # also run the model tier (needs ANTHROPIC_API_KEY)
python3 -m evals.runner --suite routing    # one suite
python3 -m evals.runner --update-baseline  # record current scores
python3 -m evals.runner --json report.json # machine-readable report
```

Exit codes: `0` all passed · `1` failure or regression · `2` the harness itself
could not run (malformed scenarios). A run that loads zero suites is an error,
not a pass — silence must not read as success.

CI: [`.github/workflows/quality-gates.yml`](../.github/workflows/quality-gates.yml),
job `evals`. The offline tier gates every PR; the live tier is opt-in via
`workflow_dispatch` because it costs tokens.

## 5. Verified behaviour

Recorded 2026-07-27, on 20 scenarios across 2 suites:

- Clean run: **20/20 pass, exit 0**, in under a second, with no API key.
- Regression detection, deliberately induced: removing `prompt_regression` from
  the `pr_event` route caused
  `FAIL [CRITICAL] pr_event.review_and_regression_capability — lost capability: missing ['prompt_regression']`
  and exit 1. Restoring the route returned the run to 20/20.

**Not yet demonstrated:** the `--live` model tier has never executed — there was
no API key in the environment where it was written. It is wired to CI, where the
secret exists. Its first CI run is its validation, and it should not be presented
as a demonstrated result before then.

## 6. Measurements

| Measurement | Source | Question it answers |
|---|---|---|
| Scenarios passing / total | runner report | Does behaviour hold under known conditions? |
| Regressions per run | baseline comparison | Have we lost an ability we had? |
| Critical-scenario failures | runner report | Is a required capability missing right now? |
| Scenario coverage per skill | suite files | Which skills have no eval at all? |
| Live-tier score vs. offline contract | `--live` report | Does the model actually choose what we expect? |

## 7. Metamodel mapping

- **Process:** eval gate (ETVX — *Entry:* a PR or dispatch; *Task:* run scenarios
  and score; *Verification:* a human reads the named failure and decides whether
  it is a real regression or an intended change; *eXit:* green gate, or a
  baseline deliberately updated).
- **Artifacts:** scenario suites (`evals/scenarios/*.json`), the baseline file,
  and the run report — each defined and inspectable.
- **Resources:** the harness, the routing table under test, CI, and (for the live
  tier) the model plus an API key.
- **Measurements:** §6.
- **Context management:** scenarios are the encoded, versioned statement of what
  each agent is *supposed* to do — the reference an eval judges against.

## 8. Extending it

Add a `*.json` suite under `evals/scenarios/`. Give every scenario a stable `id`
(it is the baseline key, so renaming one reads as "old capability gone, new one
added" — rename deliberately). Mark a scenario `critical` only when its failure
genuinely means a lost capability; overusing it makes the signal useless.
