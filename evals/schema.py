"""
Eval scenario schema — the declarative contract for agent-behaviour evals.

A *scenario* states a known condition and the behaviour we expect from the
system under it. A *suite* is a named collection of scenarios evaluated by
one evaluator kind.

Why this exists (Cory Gwin coaching session, 2026-07-24): agents are
non-deterministic, so evals establish whether behaviour holds under known
conditions. The recommended entry point was, for a given skill, to "define
scenarios and validate that the agent calls the correct tools and skills
under each," with **regression detection** — knowing whether an agent has
lost an ability it previously had — as the primary payoff.

Two evaluator kinds are supported today:

``routing``
    Deterministic. Asserts which agents the orchestrator dispatches for a
    trigger type (``orchestrator.router.resolve_agents``). Needs no model
    and no API key, so it runs on every PR as a blocking gate.

``skill_selection``
    Asserts that a skill/agent selects the correct tools and emits labels
    drawn from a controlled vocabulary. Offline it validates the scenario
    and its vocabulary; live (with an API key) it also runs the model.

Scenarios are JSON — stdlib only, no PyYAML — so the harness runs the same
way locally and in CI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"

EvaluatorKind = Literal["routing", "skill_selection"]

_VALID_KINDS: frozenset[str] = frozenset({"routing", "skill_selection"})


class ScenarioError(ValueError):
    """A scenario or suite is malformed."""


@dataclass(frozen=True, slots=True)
class Scenario:
    """One known condition and the behaviour expected under it.

    Attributes:
        id: Stable identifier. Used as the baseline key, so renaming an id
            reads as "old capability gone, new capability added" — rename
            deliberately.
        description: Why this scenario matters, in one line.
        given: The input condition (evaluator-specific keys).
        expect: The expected behaviour (evaluator-specific keys).
        critical: When true, a failure here is a lost capability and fails
            the run outright regardless of aggregate score.
    """

    id: str
    description: str
    given: dict[str, Any]
    expect: dict[str, Any]
    critical: bool = False

    @staticmethod
    def from_dict(raw: dict[str, Any], *, suite: str) -> Scenario:
        missing = [k for k in ("id", "description", "given", "expect") if k not in raw]
        if missing:
            raise ScenarioError(f"suite {suite!r}: scenario missing keys {missing}: {raw!r}")
        if not isinstance(raw["given"], dict) or not isinstance(raw["expect"], dict):
            raise ScenarioError(f"suite {suite!r}: scenario {raw['id']!r}: given/expect must be objects")
        return Scenario(
            id=str(raw["id"]),
            description=str(raw["description"]),
            given=dict(raw["given"]),
            expect=dict(raw["expect"]),
            critical=bool(raw.get("critical", False)),
        )


@dataclass(frozen=True, slots=True)
class Suite:
    """A named set of scenarios sharing one evaluator kind."""

    name: str
    kind: EvaluatorKind
    description: str
    scenarios: tuple[Scenario, ...] = field(default_factory=tuple)
    # Controlled vocabularies for skill_selection suites: field -> allowed values.
    vocabularies: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def requires_model(self) -> bool:
        """True when fully evaluating this suite needs a live model call."""
        return self.kind == "skill_selection"

    @staticmethod
    def from_dict(raw: dict[str, Any], *, source: str) -> Suite:
        for key in ("name", "kind", "description", "scenarios"):
            if key not in raw:
                raise ScenarioError(f"{source}: suite missing required key {key!r}")

        kind = str(raw["kind"])
        if kind not in _VALID_KINDS:
            raise ScenarioError(
                f"{source}: unknown evaluator kind {kind!r} (valid: {sorted(_VALID_KINDS)})"
            )

        raw_scenarios = raw["scenarios"]
        if not isinstance(raw_scenarios, list) or not raw_scenarios:
            raise ScenarioError(f"{source}: 'scenarios' must be a non-empty list")

        name = str(raw["name"])
        scenarios = tuple(Scenario.from_dict(s, suite=name) for s in raw_scenarios)

        ids = [s.id for s in scenarios]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ScenarioError(f"{source}: duplicate scenario ids {duplicates}")

        vocabularies = {
            str(k): tuple(str(v) for v in vals)
            for k, vals in (raw.get("vocabularies") or {}).items()
        }

        return Suite(
            name=name,
            kind=kind,  # type: ignore[arg-type]
            description=str(raw["description"]),
            scenarios=scenarios,
            vocabularies=vocabularies,
        )


def load_suite(path: Path) -> Suite:
    """Load and validate one suite file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScenarioError(f"{path}: invalid JSON: {exc}") from exc
    return Suite.from_dict(raw, source=str(path))


def load_all_suites(directory: Path | None = None) -> list[Suite]:
    """Load every ``*.json`` suite in ``directory``, sorted by filename.

    Raises:
        ScenarioError: if the directory is missing or holds no suites — an
            eval run that silently evaluates nothing is worse than a
            failure, because it reports success.
    """
    target = directory or SCENARIOS_DIR
    if not target.is_dir():
        raise ScenarioError(f"scenario directory not found: {target}")

    paths = sorted(target.glob("*.json"))
    if not paths:
        raise ScenarioError(f"no scenario suites found in {target}")

    return [load_suite(p) for p in paths]
