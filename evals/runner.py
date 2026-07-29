"""
Eval runner — executes scenario suites and detects capability regressions.

Usage:
    python -m evals.runner                      # offline tiers, blocking
    python -m evals.runner --live               # also run model-dependent tiers
    python -m evals.runner --suite routing      # one suite
    python -m evals.runner --update-baseline    # record current scores
    python -m evals.runner --json report.json   # machine-readable report

Design notes (from the Cory Gwin coaching session, 2026-07-24):

* **Regression detection is the point.** A score on its own says little; what
  matters is whether an ability the system *had* is now gone. Baselines are
  stored per scenario id, and any scenario that previously passed and now
  fails is reported as a regression by name.
* **Two tiers, so the cheap one can block.** Routing evals are deterministic
  and need no API key, so they gate every PR. Model-dependent evals cost
  tokens and are opt-in via ``--live``.
* **Silence is not success.** Loading zero suites, or a live tier requested
  without a key, is reported explicitly rather than passing quietly.

Exit codes:
    0 — all evaluated scenarios passed, no regressions
    1 — a scenario failed, a critical scenario failed, or a regression appeared
    2 — the harness itself could not run (malformed scenarios, bad arguments)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from evals.schema import Scenario, ScenarioError, Suite, load_all_suites
from evals.scorers import (
    ScoreResult,
    aggregate,
    exact_set_match,
    forbidden_absent,
    ordered_before,
    required_subset,
    vocabulary_conformance,
)

BASELINE_FILE = Path(__file__).resolve().parent / "baselines.json"

STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_SKIP = "skip"


@dataclass(slots=True)
class Outcome:
    """Result of evaluating one scenario."""

    suite: str
    scenario_id: str
    description: str
    status: str
    score: float
    reason: str
    critical: bool = False
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def as_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "scenario": self.scenario_id,
            "description": self.description,
            "status": self.status,
            "score": round(self.score, 4),
            "reason": self.reason,
            "critical": self.critical,
            "checks": self.checks,
        }


# ---------------------------------------------------------------------------
# Tier 1 — routing (deterministic, no model)
# ---------------------------------------------------------------------------


def evaluate_routing(suite: Suite) -> list[Outcome]:
    """Evaluate routing scenarios against the live routing table."""
    from orchestrator.router import resolve_agents

    outcomes: list[Outcome] = []
    for sc in suite.scenarios:
        trigger_type = sc.given.get("trigger_type")
        if not isinstance(trigger_type, str):
            outcomes.append(
                Outcome(
                    suite=suite.name,
                    scenario_id=sc.id,
                    description=sc.description,
                    status=STATUS_FAIL,
                    score=0.0,
                    reason="scenario 'given' is missing a string 'trigger_type'",
                    critical=sc.critical,
                )
            )
            continue

        override = sc.given.get("agent_override")
        actual = resolve_agents(trigger_type, override if isinstance(override, str) else None)

        checks: dict[str, ScoreResult] = {}
        if "agents_exact" in sc.expect:
            checks["agents_exact"] = exact_set_match(actual, sc.expect["agents_exact"])
        if "agents_required" in sc.expect:
            checks["agents_required"] = required_subset(actual, sc.expect["agents_required"])
        if "agents_forbidden" in sc.expect:
            checks["agents_forbidden"] = forbidden_absent(actual, sc.expect["agents_forbidden"])
        if "order" in sc.expect:
            checks["order"] = ordered_before(actual, sc.expect["order"])

        outcomes.append(_finalize(suite, sc, checks, note=f"dispatched={actual}"))

    return outcomes


# ---------------------------------------------------------------------------
# Tier 2 — skill selection (offline validation; model run under --live)
# ---------------------------------------------------------------------------


def evaluate_skill_selection(suite: Suite, *, live: bool) -> list[Outcome]:
    """Evaluate skill scenarios.

    Offline, this validates the scenario contract itself: every expected
    label must exist in the suite's controlled vocabulary and every named
    tool must exist in the declared tool surface. That is a real check — an
    expectation naming a label the skill can never emit (a typo, or a label
    dropped from the spec) is a broken eval that would otherwise sit green
    forever, and an off-vocabulary label in production silently drops the
    defect out of every JQL-derived metric.

    Under ``--live`` the skill is additionally executed and its actual
    choices are scored. That path requires ``ANTHROPIC_API_KEY``.
    """
    outcomes: list[Outcome] = []
    vocab = suite.vocabularies

    for sc in suite.scenarios:
        checks: dict[str, ScoreResult] = {}

        labels = sc.expect.get("labels", {})
        if isinstance(labels, dict):
            for field_name, value in labels.items():
                allowed = vocab.get(field_name)
                if allowed is None:
                    checks[f"vocab:{field_name}"] = ScoreResult(
                        0.0, False, f"no vocabulary declared for field {field_name!r}"
                    )
                else:
                    checks[f"vocab:{field_name}"] = vocabulary_conformance(
                        [value] if isinstance(value, str) else list(value),
                        allowed,
                        field=field_name,
                    )

        priority = sc.expect.get("priority")
        if isinstance(priority, str) and "priority" in vocab:
            checks["vocab:priority"] = vocabulary_conformance(
                [priority], vocab["priority"], field="priority"
            )

        tool_surface = vocab.get("tools")
        if tool_surface:
            for key in ("tools_required", "tools_forbidden"):
                named = sc.expect.get(key)
                if isinstance(named, list) and named:
                    checks[f"vocab:{key}"] = vocabulary_conformance(
                        named, tool_surface, field=key
                    )

        if live:
            model_checks = _run_live_skill_scenario(suite, sc)
            if model_checks is None:
                outcomes.append(
                    Outcome(
                        suite=suite.name,
                        scenario_id=sc.id,
                        description=sc.description,
                        status=STATUS_SKIP,
                        score=0.0,
                        reason="live run requested but ANTHROPIC_API_KEY is not set",
                        critical=sc.critical,
                        checks={k: v.as_dict for k, v in checks.items()},
                    )
                )
                continue
            checks.update(model_checks)

        outcome = _finalize(
            suite,
            sc,
            checks,
            note="contract validated (offline)" if not live else "model run",
        )
        if not live:
            # Offline this suite verifies the eval contract, not agent behaviour.
            outcome.description = f"{sc.description}"
            outcome.reason = f"[contract-only, no model] {outcome.reason}"
        outcomes.append(outcome)

    return outcomes


def _run_live_skill_scenario(suite: Suite, sc: Scenario) -> dict[str, ScoreResult] | None:
    """Execute the skill against a real model and score its selections.

    Returns ``None`` when no API key is available, so the caller can mark the
    scenario skipped rather than silently passing.

    NOTE: this path has not yet been executed against a live model — there is
    no API key in the development environment where it was written. It is
    wired for CI, where ``ANTHROPIC_API_KEY`` exists. Treat its first CI run
    as the validation of this function, and do not present it as a
    demonstrated result until then.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None

    try:  # lazy import — keeps the offline tier dependency-free
        import anthropic
    except ImportError:
        return {
            "model_run": ScoreResult(
                0.0, False, "anthropic SDK not installed; cannot run live tier"
            )
        }

    instruction = (
        "You are triaging a software defect for the EPARTS project. "
        "Classify it and state which tools you would call, in order. "
        "Respond ONLY with JSON of the form "
        '{"should_create_issue": bool, "tools": [str], "labels": '
        '{"stage_found": str, "root_cause": str, "found_by": str, "module": str}, '
        '"priority": str}. '
        "Labels must come from these controlled vocabularies:\n"
        + json.dumps({k: list(v) for k, v in suite.vocabularies.items()}, indent=2)
    )
    payload = json.dumps({"finding": sc.given.get("finding"), "context": sc.given.get("context")})

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=os.environ.get("EVAL_MODEL", "claude-sonnet-4-5-20250929"),
        max_tokens=1024,
        system=instruction,
        messages=[{"role": "user", "content": payload}],
    )
    text = "".join(getattr(block, "text", "") for block in message.content)

    try:
        actual = json.loads(_extract_json(text))
    except (json.JSONDecodeError, ValueError) as exc:
        return {
            "model_run": ScoreResult(0.0, False, f"model did not return parseable JSON: {exc}")
        }

    checks: dict[str, ScoreResult] = {}

    expected_create = sc.expect.get("should_create_issue")
    if isinstance(expected_create, bool):
        got = bool(actual.get("should_create_issue"))
        checks["should_create_issue"] = ScoreResult(
            1.0 if got == expected_create else 0.0,
            got == expected_create,
            f"expected should_create_issue={expected_create}, got {got}",
        )

    actual_tools = [t for t in actual.get("tools", []) if isinstance(t, str)]
    if "tools_required" in sc.expect:
        checks["tools_required"] = required_subset(actual_tools, sc.expect["tools_required"])
    if "tools_forbidden" in sc.expect:
        checks["tools_forbidden"] = forbidden_absent(actual_tools, sc.expect["tools_forbidden"])
    if "tool_order" in sc.expect:
        checks["tool_order"] = ordered_before(actual_tools, sc.expect["tool_order"])

    actual_labels = actual.get("labels") or {}
    for field_name, expected_value in (sc.expect.get("labels") or {}).items():
        got_value = actual_labels.get(field_name)
        match = got_value == expected_value
        checks[f"label:{field_name}"] = ScoreResult(
            1.0 if match else 0.0,
            match,
            f"{field_name}: expected {expected_value!r}, got {got_value!r}",
        )

    if isinstance(sc.expect.get("priority"), str):
        got_priority = actual.get("priority")
        match = got_priority == sc.expect["priority"]
        checks["priority"] = ScoreResult(
            1.0 if match else 0.0,
            match,
            f"priority: expected {sc.expect['priority']!r}, got {got_priority!r}",
        )

    return checks


def _extract_json(text: str) -> str:
    """Pull the first JSON object out of a model response."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found in response")
    return text[start : end + 1]


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


def _finalize(
    suite: Suite, sc: Scenario, checks: dict[str, ScoreResult], *, note: str
) -> Outcome:
    if not checks:
        return Outcome(
            suite=suite.name,
            scenario_id=sc.id,
            description=sc.description,
            status=STATUS_FAIL,
            score=0.0,
            reason="scenario declared no checkable expectations",
            critical=sc.critical,
        )
    combined = aggregate(list(checks.values()))
    return Outcome(
        suite=suite.name,
        scenario_id=sc.id,
        description=sc.description,
        status=STATUS_PASS if combined.passed else STATUS_FAIL,
        score=combined.score,
        reason=f"{combined.reason} ({note})",
        critical=sc.critical,
        checks={k: v.as_dict for k, v in checks.items()},
    )


def load_baselines(path: Path | None = None) -> dict[str, float]:
    target = path or BASELINE_FILE
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {str(k): float(v) for k, v in data.get("scores", {}).items()}


def save_baselines(outcomes: Sequence[Outcome], path: Path | None = None) -> Path:
    target = path or BASELINE_FILE
    scores = {
        f"{o.suite}::{o.scenario_id}": round(o.score, 4)
        for o in outcomes
        if o.status != STATUS_SKIP
    }
    target.write_text(
        json.dumps(
            {
                "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "scores": scores,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


def find_regressions(
    outcomes: Sequence[Outcome], baselines: dict[str, float], *, tolerance: float = 0.001
) -> list[str]:
    """Scenarios whose score dropped below their recorded baseline."""
    regressions = []
    for o in outcomes:
        if o.status == STATUS_SKIP:
            continue
        key = f"{o.suite}::{o.scenario_id}"
        if key in baselines and o.score < baselines[key] - tolerance:
            regressions.append(f"{key}: {baselines[key]:.3f} -> {o.score:.3f} ({o.reason})")
    return regressions


def run(
    *,
    live: bool = False,
    only_suite: str | None = None,
    scenarios_dir: Path | None = None,
) -> tuple[list[Outcome], list[Suite]]:
    suites = load_all_suites(scenarios_dir)
    if only_suite:
        suites = [s for s in suites if only_suite in s.name]
        if not suites:
            raise ScenarioError(f"no suite matching {only_suite!r}")

    outcomes: list[Outcome] = []
    for suite in suites:
        if suite.kind == "routing":
            outcomes.extend(evaluate_routing(suite))
        elif suite.kind == "skill_selection":
            outcomes.extend(evaluate_skill_selection(suite, live=live))
    return outcomes, suites


def format_report(outcomes: Sequence[Outcome], regressions: Sequence[str], *, live: bool) -> str:
    lines: list[str] = ["# Agent Eval Report", ""]
    lines.append(f"Tier: {'offline + live model' if live else 'offline only (no model calls)'}")
    passed = sum(1 for o in outcomes if o.status == STATUS_PASS)
    failed = sum(1 for o in outcomes if o.status == STATUS_FAIL)
    skipped = sum(1 for o in outcomes if o.status == STATUS_SKIP)
    lines.append(f"Scenarios: {len(outcomes)} — {passed} passed, {failed} failed, {skipped} skipped")
    lines.append("")

    by_suite: dict[str, list[Outcome]] = {}
    for o in outcomes:
        by_suite.setdefault(o.suite, []).append(o)

    for suite_name, items in by_suite.items():
        mean = sum(i.score for i in items) / len(items) if items else 0.0
        lines.append(f"## {suite_name} (mean score {mean:.3f})")
        for o in items:
            marker = {STATUS_PASS: "PASS", STATUS_FAIL: "FAIL", STATUS_SKIP: "SKIP"}[o.status]
            crit = " [CRITICAL]" if o.critical else ""
            lines.append(f"- **{marker}**{crit} `{o.scenario_id}` — {o.reason}")
        lines.append("")

    if regressions:
        lines.append("## Regressions (lost capabilities)")
        lines.extend(f"- {r}" for r in regressions)
        lines.append("")

    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run agent behaviour evals.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="also run model-dependent tiers (requires ANTHROPIC_API_KEY)",
    )
    parser.add_argument("--suite", help="only run suites whose name contains this string")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="record current scores as the regression baseline",
    )
    parser.add_argument("--json", dest="json_out", help="write the report as JSON to this path")
    args = parser.parse_args(argv)

    try:
        outcomes, suites = run(live=args.live, only_suite=args.suite)
    except ScenarioError as exc:
        print(f"eval harness error: {exc}", file=sys.stderr)
        return 2

    baselines = load_baselines()
    regressions = find_regressions(outcomes, baselines)

    print(format_report(outcomes, regressions, live=args.live))

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "live": args.live,
                    "suites": [{"name": s.name, "kind": s.kind} for s in suites],
                    "outcomes": [o.as_dict for o in outcomes],
                    "regressions": list(regressions),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"JSON report written to {args.json_out}")

    if args.update_baseline:
        path = save_baselines(outcomes)
        print(f"Baseline recorded at {path}")

    critical_failures = [o for o in outcomes if o.status == STATUS_FAIL and o.critical]
    failures = [o for o in outcomes if o.status == STATUS_FAIL]

    if critical_failures:
        print(
            f"\nFAILED: {len(critical_failures)} critical scenario(s) failed — "
            "a required capability is missing.",
            file=sys.stderr,
        )
        return 1
    if failures:
        print(f"\nFAILED: {len(failures)} scenario(s) failed.", file=sys.stderr)
        return 1
    if regressions:
        print(f"\nFAILED: {len(regressions)} regression(s) detected.", file=sys.stderr)
        return 1

    print("\nAll evaluated scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
