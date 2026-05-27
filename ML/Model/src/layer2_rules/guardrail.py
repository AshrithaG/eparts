"""Layer 2 — 2A valid-value guardrail.

Implements V1_Engineering_Spec §4.2 "Guardrail — 2A valid-value check":

    Every rule-produced (Attribute, Value) pair must validate against 2A.
    If it does not, the rule prediction is demoted and Layer 3 adjudicates.
    This prevents the rule engine from emitting values absent from the
    database.

Demotion does not raise — Layer 4 still needs to see *something* per
attribute so it can fall through to Layer 3. We rewrite the offending
:class:`~src.contracts.RuleHit` with ``conf_rule = 0`` and
``demoted_by_2a = True``. Caller is responsible for ignoring the value
content of demoted hits.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

import pandas as pd

from ..contracts import RuleHit


class ValidValueGuardrail:
    """Set-based ``(Attribute_Name, Value)`` validity check.

    Names and values are case-folded and whitespace-collapsed before storage
    and lookup, so reasonable normalization variants still pass.
    """

    def __init__(
        self,
        valid_pairs: Iterable[tuple[str, str]],
        exempt_attribute_names: Iterable[str] = (),
    ) -> None:
        """Build the guardrail.

        Args:
            valid_pairs: The closed set of legal ``(Attribute_Name, Value)``
                pairs, normally drawn from ``2A_Values_Per_Attribute``.
            exempt_attribute_names: Attribute names that bypass the 2A check.
                Useful for product metadata that is *not* stored in 2A but is
                still emitted as a rule hit (e.g. ``"Manufacturer"`` —
                the canonical-name closure for manufacturers is enforced
                upstream by the fuzzy index). Names are case-folded for the
                comparison.
        """
        self._pairs: frozenset[tuple[str, str]] = frozenset(
            (self._normalize(a), self._normalize(v)) for a, v in valid_pairs
        )
        self._exempt: frozenset[str] = frozenset(
            self._normalize(n) for n in exempt_attribute_names
        )

    @staticmethod
    def _normalize(s: str) -> str:
        return " ".join(str(s or "").strip().lower().split())

    @property
    def size(self) -> int:
        return len(self._pairs)

    def is_valid(self, attribute_name: str, value: str) -> bool:
        return (self._normalize(attribute_name), self._normalize(value)) in self._pairs

    def validate(self, hit: RuleHit) -> RuleHit:
        """Return a copy of ``hit`` with ``demoted_by_2a`` set when invalid.

        Tier 1 (exact part-number) is never demoted — it carries no
        ``(attribute, value)`` claim. Hits with empty attribute names pass
        through unchanged.
        """
        if hit.terminal:
            return hit
        if not hit.attribute_name:
            return hit
        if self._normalize(hit.attribute_name) in self._exempt:
            return hit
        if self.is_valid(hit.attribute_name, hit.predicted_value):
            return hit
        return replace(hit, conf_rule=0.0, demoted_by_2a=True)

    def validate_all(self, hits: Iterable[RuleHit]) -> tuple[RuleHit, ...]:
        return tuple(self.validate(h) for h in hits)


# ---------------------------------------------------------------------------
# Production factory
# ---------------------------------------------------------------------------


def build_from_2a(
    values_df: pd.DataFrame | None = None,
    exempt_attribute_names: Iterable[str] = (),
) -> ValidValueGuardrail:
    """Build :class:`ValidValueGuardrail` from 2A_Values_Per_Attribute.

    Args:
        values_df: Pre-loaded 2A DataFrame. When ``None``, loads via
            :func:`src.data.load_values_per_attribute`.
        exempt_attribute_names: Attribute names that bypass the 2A check
            (e.g. ``"Manufacturer"`` — see class docstring).

    Returns:
        A guardrail covering every ``(Attribute_Name, Value)`` pair in 2A,
        plus the given exemptions.
    """
    if values_df is None:
        from ..data import load_values_per_attribute
        values_df = load_values_per_attribute()

    required = {"Attribute_Name", "Value"}
    missing = required - set(values_df.columns)
    if missing:
        raise ValueError(f"2A frame is missing required columns: {missing}")

    pairs = (
        (str(a), str(v))
        for a, v in values_df[["Attribute_Name", "Value"]]
        .dropna(subset=["Attribute_Name", "Value"])
        .itertuples(index=False, name=None)
    )
    return ValidValueGuardrail(pairs, exempt_attribute_names=exempt_attribute_names)
