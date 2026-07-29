"""
Deterministic scoring primitives for the eval harness.

Every function here is pure and model-free: same inputs, same score. That is
deliberate. Per the Cory Gwin coaching session (2026-07-24), a great deal of
quality assurance is deterministic and consumes no tokens — so the scoring
layer is fully testable offline and only the *behaviour under test* needs a
model.

Each scorer returns a :class:`ScoreResult` carrying the 0.0–1.0 score plus a
human-readable reason, because an eval that says "0.6" without saying what
was missing cannot be acted on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """Outcome of one scorer."""

    score: float
    passed: bool
    reason: str

    @property
    def as_dict(self) -> dict[str, object]:
        return {"score": round(self.score, 4), "passed": self.passed, "reason": self.reason}


def _norm(items: Iterable[str]) -> list[str]:
    """Normalize to trimmed, non-empty strings, preserving order."""
    return [s.strip() for s in items if isinstance(s, str) and s.strip()]


def exact_set_match(actual: Sequence[str], expected: Sequence[str]) -> ScoreResult:
    """Score 1.0 only when ``actual`` and ``expected`` hold the same members.

    Order-insensitive, duplicate-insensitive. Use when the full dispatch set
    is the contract and any extra or missing member is a defect.
    """
    a, e = set(_norm(actual)), set(_norm(expected))
    if a == e:
        return ScoreResult(1.0, True, f"exact match ({len(e)} expected)")

    missing, extra = sorted(e - a), sorted(a - e)
    union = len(a | e) or 1
    score = len(a & e) / union  # Jaccard: penalizes both directions
    parts = []
    if missing:
        parts.append(f"missing {missing}")
    if extra:
        parts.append(f"unexpected {extra}")
    return ScoreResult(score, False, "; ".join(parts))


def required_subset(actual: Sequence[str], required: Sequence[str]) -> ScoreResult:
    """Fraction of ``required`` members present in ``actual``.

    This is the capability check that drives regression detection: it answers
    "can the system still do X?" while tolerating additions. Extras are fine
    — new abilities are not regressions.
    """
    a, r = set(_norm(actual)), _norm(required)
    if not r:
        return ScoreResult(1.0, True, "no requirements declared")

    present = [x for x in r if x in a]
    missing = sorted(set(r) - a)
    score = len(present) / len(r)
    if not missing:
        return ScoreResult(1.0, True, f"all {len(r)} required present")
    return ScoreResult(score, False, f"lost capability: missing {missing}")


def forbidden_absent(actual: Sequence[str], forbidden: Sequence[str]) -> ScoreResult:
    """Score 1.0 when none of ``forbidden`` appear in ``actual``."""
    a, f = set(_norm(actual)), _norm(forbidden)
    if not f:
        return ScoreResult(1.0, True, "no exclusions declared")

    present = sorted(a & set(f))
    if not present:
        return ScoreResult(1.0, True, f"none of {len(f)} forbidden present")
    return ScoreResult(0.0, False, f"forbidden present: {present}")


def ordered_before(actual: Sequence[str], pairs: Sequence[Sequence[str]]) -> ScoreResult:
    """Score the fraction of ``(first, second)`` pairs appearing in order.

    Pipeline correctness often depends on sequence, not just membership: a
    transcript must be parsed before requirements can be extracted from it.
    A pair whose members are not both present counts as a failure — the
    ordering claim cannot hold if a stage is missing.
    """
    a = _norm(actual)
    index = {name: i for i, name in enumerate(a)}
    if not pairs:
        return ScoreResult(1.0, True, "no ordering constraints declared")

    violations: list[str] = []
    for pair in pairs:
        if len(pair) != 2:
            violations.append(f"malformed pair {list(pair)!r}")
            continue
        first, second = pair[0].strip(), pair[1].strip()
        if first not in index or second not in index:
            violations.append(f"{first} -> {second} (member absent)")
        elif index[first] >= index[second]:
            violations.append(f"{first} -> {second} (out of order)")

    score = (len(pairs) - len(violations)) / len(pairs)
    if not violations:
        return ScoreResult(1.0, True, f"all {len(pairs)} ordering constraints hold")
    return ScoreResult(max(score, 0.0), False, "ordering violated: " + "; ".join(violations))


def vocabulary_conformance(
    values: Sequence[str],
    allowed: Sequence[str],
    *,
    field: str = "value",
) -> ScoreResult:
    """Fraction of ``values`` drawn from the ``allowed`` vocabulary.

    Controlled vocabularies are how a skill's output stays machine-queryable.
    The defect-management spec, for example, derives every metric from a JQL
    query over fixed labels — an invented label silently drops the defect out
    of those metrics, so an off-vocabulary value is a real defect, not a
    stylistic quibble.
    """
    v, permitted = _norm(values), set(_norm(allowed))
    if not v:
        return ScoreResult(0.0, False, f"no {field} values produced")

    invalid = sorted({x for x in v if x not in permitted})
    score = (len(v) - len([x for x in v if x in invalid])) / len(v)
    if not invalid:
        return ScoreResult(1.0, True, f"all {len(v)} {field} value(s) in vocabulary")
    return ScoreResult(score, False, f"off-vocabulary {field}: {invalid}")


def aggregate(results: Sequence[ScoreResult]) -> ScoreResult:
    """Combine scorer results into one: mean score, passing only if all pass."""
    if not results:
        return ScoreResult(1.0, True, "no checks run")
    mean = sum(r.score for r in results) / len(results)
    failures = [r.reason for r in results if not r.passed]
    if not failures:
        return ScoreResult(mean, True, f"{len(results)} check(s) passed")
    return ScoreResult(mean, False, "; ".join(failures))
