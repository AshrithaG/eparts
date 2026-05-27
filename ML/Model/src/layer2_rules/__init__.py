"""Layer 2 — rule engine.

Implements V1_Engineering_Spec §4.2: part-number exact match (Tier 1,
terminal), manufacturer fuzzy match (Tier 2), numeric + unit match
(Tier 3), and the 2A valid-value guardrail.
"""

from .engine import (
    MANUFACTURER_ATTRIBUTE_NAME,
    RuleEngine,
    RuleEngineComponents,
    build_rule_engine,
    build_rule_engine_components,
)
from .guardrail import ValidValueGuardrail, build_from_2a as build_guardrail_from_2a
from .manufacturers import ManufacturerIndex, ManufacturerMatch
from .numeric_match import NumericHit, NumericMatcher
from .part_numbers import PartNumberIndex, PartNumberMatch

__all__ = [
    "MANUFACTURER_ATTRIBUTE_NAME",
    "ManufacturerIndex",
    "ManufacturerMatch",
    "NumericHit",
    "NumericMatcher",
    "PartNumberIndex",
    "PartNumberMatch",
    "RuleEngine",
    "RuleEngineComponents",
    "ValidValueGuardrail",
    "build_guardrail_from_2a",
    "build_rule_engine",
    "build_rule_engine_components",
]
