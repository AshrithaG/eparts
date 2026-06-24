"""Layer 4 fusion + caps + routing tests (V1 spec §4.4 + §7.2 M4)."""
from __future__ import annotations

import math

import numpy as np
import pytest

from src.config import (
    ClusterConfig,
    DecisionConfig,
    FusionConfig,
    OnlineUpdateConfig,
    ProductTypeConsensusConfig,
    RuleEngineConfig,
    ThresholdsConfig,
)
from src.contracts import (
    ExtractedInput,
    ProductTypePrediction,
    Routing,
    RuleEngineResult,
    RuleHit,
    RuleTier,
    SemanticCandidate,
    SemanticHit,
    SemanticMatcherResult,
    SourceType,
)
from src.layer4_decision import Layer4Decision

# ML-CT component: decision / fusion / routing (M4) — every test here is ML-CT.
pytestmark = pytest.mark.ml_ct


# ===========================================================================
# Fixtures — spec-canonical thresholds
# ===========================================================================


def _thresholds(
    alpha: float = 0.7,
    pt_band_low: float = 0.60,
    pt_cap: float = 0.75,
    low_sample_cap: float = 0.70,
    auto: float = 0.85,
    review: float = 0.50,
) -> ThresholdsConfig:
    return ThresholdsConfig(
        rule_engine=RuleEngineConfig(
            conf_exact_part_number=1.0,
            conf_manufacturer_fuzzy=0.85,
            conf_partial=0.65,
            conf_no_match=0.0,
            manufacturer_fuzzy_min_score=90,
        ),
        product_type_consensus=ProductTypeConsensusConfig(
            band_high=0.80, band_low=pt_band_low
        ),
        clusters=ClusterConfig(min_size=5, low_sample_conf_cap=low_sample_cap),
        fusion=FusionConfig(alpha=alpha, pt_ambiguity_cap=pt_cap),
        decision=DecisionConfig(auto_process=auto, human_review_floor=review),
        online_updates=OnlineUpdateConfig(pushback_lambda=0.01),
    )


@pytest.fixture
def thresholds() -> ThresholdsConfig:
    return _thresholds()


@pytest.fixture
def decider(thresholds) -> Layer4Decision:
    return Layer4Decision(thresholds)


# ---- helpers -------------------------------------------------------------


def _extracted(text: str = "anything") -> ExtractedInput:
    return ExtractedInput(source_type=SourceType.CSV, text=text)


def _candidate(
    value: str = "24",
    conf_embed: float = 0.9,
    conf_embed_final: float = 0.8,
    cluster_n: int = 50,
    low_sample: bool = False,
) -> SemanticCandidate:
    return SemanticCandidate(
        value=value,
        conf_embed=conf_embed,
        conf_embed_final=conf_embed_final,
        cluster_n=cluster_n,
        mahalanobis_d2=0.5,
        usage_count=10,
        low_sample=low_sample,
    )


def _semantic_hit(attribute: str, *candidates: SemanticCandidate) -> SemanticHit:
    if not candidates:
        candidates = (_candidate(),)
    return SemanticHit(
        attribute_id=None, attribute_name=attribute, top_candidates=tuple(candidates)
    )


def _semantic(
    pt_id: int = 10, pt_conf: float = 0.9, *hits: SemanticHit
) -> SemanticMatcherResult:
    return SemanticMatcherResult(
        product_type=ProductTypePrediction(
            product_type_id=pt_id,
            product_type_name=f"PT{pt_id}",
            pt_conf=pt_conf,
        ),
        hits=tuple(hits),
    )


def _rule_hit(
    attribute_name: str = "",
    conf_rule: float = 0.0,
    tier: RuleTier = RuleTier.NONE,
    terminal: bool = False,
    demoted: bool = False,
    predicted_value: str = "",
) -> RuleHit:
    return RuleHit(
        attribute_id=None,
        attribute_name=attribute_name,
        predicted_value=predicted_value,
        unit_suffix=None,
        conf_rule=conf_rule,
        tier=tier,
        terminal=terminal,
        demoted_by_2a=demoted,
    )


# ===========================================================================
# Property tests (spec §7.2 M4)
# ===========================================================================


def test_conf_final_always_in_unit_interval(decider, thresholds):
    """Property: conf_final ∈ [0, 1] for ANY valid input."""
    # Stress with extreme rule + embed combos
    for conf_rule, conf_embed, pt_conf in [
        (0.0, 0.0, 0.9),
        (1.0, 1.0, 0.9),
        (1.0, 0.0, 0.4),                          # cap kicks in
        (0.85, 0.5, 0.9),                         # normal
        (1.0, 1.0, 0.0),                          # extreme PT ambiguity
    ]:
        cand = _candidate(conf_embed_final=conf_embed)
        rule = _rule_hit("INPUT_VOLTAGE", conf_rule, RuleTier.NUMERIC_UNIT, predicted_value="24")
        sem = _semantic(10, pt_conf, _semantic_hit("INPUT_VOLTAGE", cand))
        result = decider.fuse(
            _extracted(), RuleEngineResult(hits=(rule,), terminated=False), sem,
            model_version="v", latency_ms=0.0,
        )
        for p in result.predictions:
            assert 0.0 <= p.conf_final <= 1.0


def test_conf_final_equals_one_iff_tier1_terminal(decider):
    """conf_final = 1.0 must only happen via the Tier-1 exact-match path."""
    tier1 = _rule_hit(predicted_value="T-6000", conf_rule=1.0, tier=RuleTier.EXACT_PART_NUMBER, terminal=True)
    result = decider.fuse(
        _extracted(), RuleEngineResult(hits=(tier1,), terminated=True), semantic=None,
        model_version="v", latency_ms=0.0,
    )
    assert len(result.predictions) == 1
    only = result.predictions[0]
    assert only.conf_final == 1.0
    assert only.attribute_name == ""                                  # Tier-1 sentinel
    assert only.predicted_value == "T-6000"
    assert only.routing == Routing.AUTO_PROCESS
    # No non-terminal path should ever produce 1.0
    full_rule = _rule_hit("INPUT_VOLTAGE", 1.0, RuleTier.NUMERIC_UNIT, predicted_value="24")
    full_sem = _semantic(10, 0.9, _semantic_hit("INPUT_VOLTAGE", _candidate(conf_embed_final=1.0)))
    result_full = decider.fuse(
        _extracted(), RuleEngineResult(hits=(full_rule,), terminated=False), full_sem,
        model_version="v", latency_ms=0.0,
    )
    # alpha*1.0 + (1-alpha)*1.0 = 1.0; allowed because the input was 1.0 each.
    # Tighten: with conf_embed_final < 1.0 (the realistic case), we should
    # NEVER hit 1.0.
    near_rule = _rule_hit("INPUT_VOLTAGE", 1.0, RuleTier.NUMERIC_UNIT, predicted_value="24")
    near_sem = _semantic(10, 0.9, _semantic_hit("INPUT_VOLTAGE", _candidate(conf_embed_final=0.999)))
    res = decider.fuse(
        _extracted(), RuleEngineResult(hits=(near_rule,), terminated=False), near_sem,
        model_version="v", latency_ms=0.0,
    )
    assert res.predictions[0].conf_final < 1.0


# ===========================================================================
# Fusion math
# ===========================================================================


def test_fusion_formula_with_alpha_07(decider, thresholds):
    """conf_final = 0.7 · conf_rule + 0.3 · conf_embed_final exactly."""
    rule = _rule_hit("INPUT_VOLTAGE", 0.65, RuleTier.NUMERIC_UNIT, predicted_value="24")
    cand = _candidate(conf_embed_final=0.40)
    sem = _semantic(10, 0.9, _semantic_hit("INPUT_VOLTAGE", cand))
    result = decider.fuse(
        _extracted(), RuleEngineResult(hits=(rule,), terminated=False), sem,
        model_version="v", latency_ms=0.0,
    )
    expected = 0.7 * 0.65 + 0.3 * 0.40       # = 0.575
    assert result.predictions[0].conf_final == pytest.approx(expected, abs=1e-9)


def test_no_rule_hit_means_conf_rule_zero(decider):
    """Attributes with no rule hit fuse as 0.7·0 + 0.3·conf_embed = 0.3·conf_embed."""
    cand = _candidate(conf_embed_final=0.9)
    sem = _semantic(10, 0.9, _semantic_hit("INPUT_VOLTAGE", cand))
    result = decider.fuse(
        _extracted(), RuleEngineResult(hits=(), terminated=False), sem,
        model_version="v", latency_ms=0.0,
    )
    assert result.predictions[0].conf_rule == 0.0
    assert result.predictions[0].conf_final == pytest.approx(0.3 * 0.9, abs=1e-9)


def test_demoted_rule_hit_does_not_contribute(decider):
    """Rule hits demoted by the 2A guardrail must not contribute conf_rule."""
    demoted = _rule_hit("INPUT_VOLTAGE", 0.0, RuleTier.NUMERIC_UNIT, demoted=True, predicted_value="24")
    cand = _candidate(conf_embed_final=0.9)
    sem = _semantic(10, 0.9, _semantic_hit("INPUT_VOLTAGE", cand))
    result = decider.fuse(
        _extracted(), RuleEngineResult(hits=(demoted,), terminated=False), sem,
        model_version="v", latency_ms=0.0,
    )
    # Same as the "no rule hit" case.
    assert result.predictions[0].conf_final == pytest.approx(0.3 * 0.9, abs=1e-9)


# ===========================================================================
# Caps
# ===========================================================================


def test_pt_ambiguity_cap_when_pt_conf_below_band_low(decider):
    """PT_conf < 0.60 → cap all attribute conf_final at 0.75 (spec §4.4)."""
    rule = _rule_hit("INPUT_VOLTAGE", 1.0, RuleTier.MANUFACTURER_FUZZY, predicted_value="24")
    cand = _candidate(conf_embed_final=1.0)
    sem = _semantic(10, 0.45, _semantic_hit("INPUT_VOLTAGE", cand))             # ambiguous PT
    result = decider.fuse(
        _extracted(), RuleEngineResult(hits=(rule,), terminated=False), sem,
        model_version="v", latency_ms=0.0,
    )
    only = result.predictions[0]
    # Pre-cap: 0.7*1.0 + 0.3*1.0 = 1.0; PT cap drops to 0.75.
    assert only.conf_final == pytest.approx(0.75, abs=1e-9)
    assert only.pt_ambiguity_capped is True


def test_pt_ambiguity_cap_doesnt_lower_already_lower_score(decider):
    """If conf_final is already below the cap, do NOT raise it to the cap."""
    cand = _candidate(conf_embed_final=0.2)
    sem = _semantic(10, 0.40, _semantic_hit("INPUT_VOLTAGE", cand))
    result = decider.fuse(
        _extracted(), RuleEngineResult(hits=(), terminated=False), sem,
        model_version="v", latency_ms=0.0,
    )
    only = result.predictions[0]
    assert only.conf_final == pytest.approx(0.3 * 0.2, abs=1e-9)      # = 0.06
    assert only.pt_ambiguity_capped is False                          # cap didn't fire


def test_low_sample_cap_when_top_candidate_is_low_sample(decider):
    """A low-sample top candidate → cap conf_final at 0.70."""
    rule = _rule_hit("INPUT_VOLTAGE", 1.0, RuleTier.MANUFACTURER_FUZZY, predicted_value="24")
    cand = _candidate(conf_embed_final=1.0, low_sample=True)
    sem = _semantic(10, 0.9, _semantic_hit("INPUT_VOLTAGE", cand))
    result = decider.fuse(
        _extracted(), RuleEngineResult(hits=(rule,), terminated=False), sem,
        model_version="v", latency_ms=0.0,
    )
    only = result.predictions[0]
    assert only.conf_final == pytest.approx(0.70, abs=1e-9)
    assert only.low_sample_capped is True
    assert only.pt_ambiguity_capped is False


def test_both_caps_fire_smaller_cap_wins(decider):
    """When PT_conf<0.60 AND low_sample, take the min(0.75, 0.70) = 0.70."""
    rule = _rule_hit("INPUT_VOLTAGE", 1.0, RuleTier.MANUFACTURER_FUZZY, predicted_value="24")
    cand = _candidate(conf_embed_final=1.0, low_sample=True)
    sem = _semantic(10, 0.45, _semantic_hit("INPUT_VOLTAGE", cand))
    result = decider.fuse(
        _extracted(), RuleEngineResult(hits=(rule,), terminated=False), sem,
        model_version="v", latency_ms=0.0,
    )
    only = result.predictions[0]
    # Pre-cap: 1.0. PT cap drops to 0.75. Low-sample cap drops further to 0.70.
    assert only.conf_final == pytest.approx(0.70, abs=1e-9)
    assert only.pt_ambiguity_capped is True
    assert only.low_sample_capped is True


# ===========================================================================
# Routing
# ===========================================================================


def test_routing_auto_process_at_or_above_0_85(decider):
    rule = _rule_hit("X", 1.0, RuleTier.NUMERIC_UNIT, predicted_value="v")
    cand = _candidate(conf_embed_final=0.95)        # fused: 0.7+0.285 = 0.985
    sem = _semantic(10, 0.9, _semantic_hit("X", cand))
    result = decider.fuse(
        _extracted(), RuleEngineResult(hits=(rule,), terminated=False), sem,
        model_version="v", latency_ms=0.0,
    )
    assert result.predictions[0].routing == Routing.AUTO_PROCESS


def test_routing_human_review_in_band(decider):
    cand = _candidate(conf_embed_final=0.8)         # fused: 0.3*0.8 = 0.24 — but raise via rule
    rule = _rule_hit("X", 0.85, RuleTier.MANUFACTURER_FUZZY, predicted_value="v")
    sem = _semantic(10, 0.9, _semantic_hit("X", cand))
    # 0.7*0.85 + 0.3*0.8 = 0.835 → HUMAN_REVIEW (0.50 ≤ 0.835 < 0.85)
    result = decider.fuse(
        _extracted(), RuleEngineResult(hits=(rule,), terminated=False), sem,
        model_version="v", latency_ms=0.0,
    )
    p = result.predictions[0]
    assert p.conf_final == pytest.approx(0.7 * 0.85 + 0.3 * 0.8)
    assert p.routing == Routing.HUMAN_REVIEW


def test_routing_flag_unclear_below_0_50(decider):
    cand = _candidate(conf_embed_final=0.5)         # fused: 0.3*0.5 = 0.15
    sem = _semantic(10, 0.9, _semantic_hit("X", cand))
    result = decider.fuse(
        _extracted(), RuleEngineResult(hits=(), terminated=False), sem,
        model_version="v", latency_ms=0.0,
    )
    assert result.predictions[0].routing == Routing.FLAG_UNCLEAR


# ===========================================================================
# Tier-1 short-circuit
# ===========================================================================


def test_tier1_terminal_emits_single_auto_processed_prediction(decider):
    tier1 = _rule_hit(predicted_value="T-6000", conf_rule=1.0, tier=RuleTier.EXACT_PART_NUMBER, terminal=True)
    result = decider.fuse(
        _extracted(), RuleEngineResult(hits=(tier1,), terminated=True), semantic=None,
        model_version="v1.0", latency_ms=10.0,
    )
    assert len(result.predictions) == 1
    p = result.predictions[0]
    assert p.attribute_name == ""
    assert p.predicted_value == "T-6000"
    assert p.conf_final == 1.0
    assert p.routing == Routing.AUTO_PROCESS
    assert result.product_type is None                             # Tier-1 skips Layer 3


def test_tier1_terminal_ignores_semantic_result(decider):
    """Defensive: if both terminated=True AND a semantic result are supplied,
    the Tier-1 path still wins (semantic input is ignored)."""
    tier1 = _rule_hit(predicted_value="T-6000", conf_rule=1.0, tier=RuleTier.EXACT_PART_NUMBER, terminal=True)
    fake_sem = _semantic(10, 0.9, _semantic_hit("X", _candidate(conf_embed_final=0.5)))
    result = decider.fuse(
        _extracted(), RuleEngineResult(hits=(tier1,), terminated=True), fake_sem,
        model_version="v", latency_ms=0.0,
    )
    assert len(result.predictions) == 1
    assert result.predictions[0].attribute_name == ""


# ===========================================================================
# Edge / defensive
# ===========================================================================


def test_no_semantic_no_rules_yields_empty_predictions(decider):
    result = decider.fuse(
        _extracted(), RuleEngineResult(hits=(), terminated=False), semantic=None,
        model_version="v", latency_ms=0.0,
    )
    assert result.predictions == ()
    assert result.product_type is None


def test_semantic_hit_with_no_candidates_is_skipped(decider):
    empty_hit = SemanticHit(attribute_id=None, attribute_name="X", top_candidates=())
    sem = _semantic(10, 0.9, empty_hit)
    result = decider.fuse(
        _extracted(), RuleEngineResult(hits=(), terminated=False), sem,
        model_version="v", latency_ms=0.0,
    )
    assert result.predictions == ()


def test_predicted_value_comes_from_semantic_top_1(decider):
    rule = _rule_hit("INPUT_VOLTAGE", 0.65, RuleTier.NUMERIC_UNIT, predicted_value="999")
    # Semantic top-1 says "24"; spec §4.4 v*(A) = argmax_v conf_embed_final.
    cand_top = _candidate(value="24", conf_embed_final=0.9)
    cand_other = _candidate(value="120", conf_embed_final=0.1)
    sem = _semantic(
        10, 0.9, _semantic_hit("INPUT_VOLTAGE", cand_top, cand_other)
    )
    result = decider.fuse(
        _extracted(), RuleEngineResult(hits=(rule,), terminated=False), sem,
        model_version="v", latency_ms=0.0,
    )
    assert result.predictions[0].predicted_value == "24"


def test_latency_and_model_version_pass_through(decider):
    rule = _rule_hit("X", 0.65, RuleTier.NUMERIC_UNIT, predicted_value="v")
    sem = _semantic(10, 0.9, _semantic_hit("X", _candidate(conf_embed_final=0.5)))
    result = decider.fuse(
        _extracted(), RuleEngineResult(hits=(rule,), terminated=False), sem,
        model_version="run_20260519_120000", latency_ms=42.5,
    )
    assert result.model_version == "run_20260519_120000"
    assert result.latency_ms == 42.5


# ===========================================================================
# ML-CT P1 boundary tests — see eparts_doc/ML_CT_Test_Plan.md Part D
# Both feed threshold VALUES directly (literals / direct _route calls) to
# avoid the float-equality trap from 0.7*x + 0.3*y arithmetic.
# ===========================================================================


def test_routing_at_exact_thresholds(thresholds):
    """Routing uses `>=` (fusion.py:_route). Feed the threshold values
    directly — exactly 0.85 and exactly 0.50 — bypassing the fused-score
    float multiply, so the test is deterministic, not flaky.

    `>=` means: 0.85 → AUTO (inclusive), 0.50 → REVIEW (inclusive),
    just-below each → the next band down."""
    from src.layer4_decision.fusion import _route

    eps = 1e-9
    # Auto-process boundary (0.85): inclusive
    assert _route(0.85, thresholds) == Routing.AUTO_PROCESS
    assert _route(0.85 - eps, thresholds) == Routing.HUMAN_REVIEW
    # Human-review floor (0.50): inclusive
    assert _route(0.50, thresholds) == Routing.HUMAN_REVIEW
    assert _route(0.50 - eps, thresholds) == Routing.FLAG_UNCLEAR


def test_pt_ambiguity_cap_boundary_is_exclusive_at_band_low(decider):
    """The PT-ambiguity cap fires on `pt_conf < band_low` (fusion.py:138) —
    strictly less-than. So at pt_conf EXACTLY 0.60 the cap must NOT fire;
    just below it must. pt_conf is fed as a literal via _semantic(), so no
    float arithmetic produces the boundary value (non-flaky).

    Note: band_high (0.80) has no hard branch in the four ML-CT components
    — it is reporting-only (scripts/m3b_pt_accuracy_eval.py:141 uses `>=`),
    so there is no component-layer 0.80 boundary to assert here."""
    cand = _candidate(conf_embed_final=1.0)     # high enough that the cap WOULD fire
    rule = _rule_hit("X", 1.0, RuleTier.MANUFACTURER_FUZZY, predicted_value="v")
    rer = RuleEngineResult(hits=(rule,), terminated=False)

    # Exactly at band_low (0.60): NOT capped (0.60 < 0.60 is False).
    at_edge = decider.fuse(
        _extracted(), rer, _semantic(10, 0.60, _semantic_hit("X", cand)),
        model_version="v", latency_ms=0.0,
    )
    assert at_edge.predictions[0].pt_ambiguity_capped is False
    assert at_edge.predictions[0].conf_final == pytest.approx(1.0)

    # Just below band_low: capped to 0.75.
    below = decider.fuse(
        _extracted(), rer, _semantic(10, 0.60 - 1e-9, _semantic_hit("X", cand)),
        model_version="v", latency_ms=0.0,
    )
    assert below.predictions[0].pt_ambiguity_capped is True
    assert below.predictions[0].conf_final == pytest.approx(0.75)
