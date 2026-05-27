"""Layer 2 — rule engine entry point.

Implements V1_Engineering_Spec §4.2 by orchestrating Tier 1 (part-number
exact match), Tier 2 (manufacturer fuzzy), and Tier 3 (numeric + unit)
against an :class:`~src.contracts.ExtractedInput`, applying the 2A valid-
value guardrail, and returning a :class:`~src.contracts.RuleEngineResult`.

Termination policy (spec §4.2 Tier 1 & §4.5): when Tier 1 fires anywhere
(structured ``part_number`` field or free-text match), the engine emits
a single ``EXACT_PART_NUMBER`` hit with ``terminal=True`` and skips Tier 2
and Tier 3. Downstream Layer 3 / Layer 4 honor the termination flag.

Construction is dependency-injected so tests can swap in tiny indexes:

    engine = RuleEngine(
        part_number_index=...,
        manufacturer_index=...,
        numeric_matcher=...,
        guardrail=...,
        config=settings.thresholds.rule_engine,
    )
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import RuleEngineConfig, load_settings
from ..contracts import ExtractedInput, RuleEngineResult, RuleHit, RuleTier
from .guardrail import ValidValueGuardrail, build_from_2a as build_guardrail_from_2a
from .manufacturers import ManufacturerIndex, build_from_1b as build_manufacturers_from_1b
from .numeric_match import (
    NumericMatcher,
    build_from_2a as build_numeric_from_2a,
    collect_value_unit_pairs,
)
from .part_numbers import PartNumberIndex, build_from_1b as build_part_numbers_from_1b


# A name reserved in 2A for manufacturer-as-attribute. eParts's schema uses
# the attribute "Manufacturer" — kept as a constant so a schema rename only
# needs touching one place.
MANUFACTURER_ATTRIBUTE_NAME = "Manufacturer"


@dataclass(frozen=True, slots=True)
class RuleEngineComponents:
    """Bundle of the four indexes the rule engine needs.

    Useful when callers want to build the components once (slow — reads 1B
    and 2A from disk) and instantiate engines multiple times (fast).
    """

    part_numbers: PartNumberIndex
    manufacturers: ManufacturerIndex
    numeric: NumericMatcher
    guardrail: ValidValueGuardrail


class RuleEngine:
    """Production wiring of all three rule tiers plus the 2A guardrail."""

    def __init__(
        self,
        part_numbers: PartNumberIndex,
        manufacturers: ManufacturerIndex,
        numeric: NumericMatcher,
        guardrail: ValidValueGuardrail,
        config: RuleEngineConfig,
    ) -> None:
        self._pn = part_numbers
        self._mfg = manufacturers
        self._num = numeric
        self._guardrail = guardrail
        self._cfg = config

    # ------------------------------------------------------------------
    # Tier wrappers — each returns RuleHit(s) and never raises.
    # ------------------------------------------------------------------

    def _tier1_part_number(self, x: ExtractedInput) -> RuleHit | None:
        # Structured part-number wins over free-text scan (more reliable).
        structured_pn = x.structured_fields.get("part_number")
        if structured_pn and self._pn.is_exact(structured_pn):
            return RuleHit(
                attribute_id=None,
                attribute_name="",
                predicted_value=structured_pn.strip(),
                unit_suffix=None,
                conf_rule=self._cfg.conf_exact_part_number,
                tier=RuleTier.EXACT_PART_NUMBER,
                terminal=True,
            )
        match = self._pn.find(x.text)
        if match is not None:
            return RuleHit(
                attribute_id=None,
                attribute_name="",
                predicted_value=match.part_number,
                unit_suffix=None,
                conf_rule=self._cfg.conf_exact_part_number,
                tier=RuleTier.EXACT_PART_NUMBER,
                terminal=True,
            )
        return None

    def _tier2_manufacturer(self, x: ExtractedInput) -> RuleHit | None:
        candidate = x.structured_fields.get("manufacturer_name")
        if not candidate:
            return None
        match = self._mfg.best_match(
            candidate,
            min_score=self._cfg.manufacturer_fuzzy_min_score,
        )
        if match is None:
            return None
        return RuleHit(
            attribute_id=None,
            attribute_name=MANUFACTURER_ATTRIBUTE_NAME,
            predicted_value=match.canonical_name,
            unit_suffix=None,
            conf_rule=self._cfg.conf_manufacturer_fuzzy,
            tier=RuleTier.MANUFACTURER_FUZZY,
            terminal=False,
        )

    def _tier3_numeric(self, x: ExtractedInput) -> tuple[RuleHit, ...]:
        hits: list[RuleHit] = []
        for value, unit in collect_value_unit_pairs(x.normalized_units):
            candidates = self._num.match_by_value_unit(value, unit)
            for cand in candidates:
                # Conservative emission: only emit unambiguous hits at
                # conf_partial. Ambiguous (>1) hits would create noise
                # downstream because the rule engine cannot disambiguate
                # which attribute the customer meant. Layer 3 will adjudicate.
                if cand.ambiguity > 1:
                    continue
                hits.append(
                    RuleHit(
                        attribute_id=None,
                        attribute_name=cand.attribute_name,
                        predicted_value=cand.value,
                        unit_suffix=cand.unit,
                        conf_rule=self._cfg.conf_partial,
                        tier=RuleTier.NUMERIC_UNIT,
                        terminal=False,
                    )
                )
        return tuple(hits)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply(self, x: ExtractedInput) -> RuleEngineResult:
        """Run all three tiers, apply the 2A guardrail, return result.

        Tier-1 termination short-circuits the remaining tiers per spec §4.2.
        """
        tier1 = self._tier1_part_number(x)
        if tier1 is not None:
            # Tier 1 is terminal; guardrail is a no-op for it.
            return RuleEngineResult(hits=(tier1,), terminated=True)

        hits: list[RuleHit] = []
        tier2 = self._tier2_manufacturer(x)
        if tier2 is not None:
            hits.append(tier2)
        hits.extend(self._tier3_numeric(x))

        validated = self._guardrail.validate_all(hits)
        return RuleEngineResult(hits=tuple(validated), terminated=False)


# ---------------------------------------------------------------------------
# Convenience factories
# ---------------------------------------------------------------------------


def build_rule_engine_components() -> RuleEngineComponents:
    """Build all four components from disk (1B and 2A).

    Slow — reads ~100 MB of 1B + 0.4 MB of 2A. Call once at service startup.

    ``Manufacturer`` is exempt from the 2A guardrail: it's product metadata
    in 1B, not a value-per-attribute entry. Closure on canonical manufacturer
    names is enforced upstream by the fuzzy index.
    """
    return RuleEngineComponents(
        part_numbers=build_part_numbers_from_1b(),
        manufacturers=build_manufacturers_from_1b(),
        numeric=build_numeric_from_2a(),
        guardrail=build_guardrail_from_2a(
            exempt_attribute_names=(MANUFACTURER_ATTRIBUTE_NAME,)
        ),
    )


def build_rule_engine(
    components: RuleEngineComponents | None = None,
    config: RuleEngineConfig | None = None,
) -> RuleEngine:
    """Assemble a :class:`RuleEngine` with configurable parts.

    Args:
        components: Pre-built components. When ``None``, builds from disk
            (1B + 2A reads).
        config: Rule-engine threshold config. When ``None``, reads
            ``config/thresholds.yaml`` via :func:`load_settings`.
    """
    if components is None:
        components = build_rule_engine_components()
    if config is None:
        config = load_settings().thresholds.rule_engine
    return RuleEngine(
        part_numbers=components.part_numbers,
        manufacturers=components.manufacturers,
        numeric=components.numeric,
        guardrail=components.guardrail,
        config=config,
    )
