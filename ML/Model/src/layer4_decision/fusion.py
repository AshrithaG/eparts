"""Layer 4 — fusion, caps, and routing.

Implements V1_Engineering_Spec §4.4.

Math (FROZEN per §6.1):

    v*(A)         = argmax_v conf_embed_final(A, v)
    conf_final(A) = α · conf_rule(A) + (1 − α) · conf_embed_final(A, v*(A))
    α = 0.7

Caps applied **after** the linear fusion:

    if PT_conf < 0.60:                    cap conf_final(A) at 0.75  for all A
    if low_sample cluster supplied v*:    cap conf_final(A) at 0.70

When both caps fire on the same attribute, the smaller cap wins (i.e.
min of the two). Both caps emit a flag on the returned
:class:`~src.contracts.AttributePrediction` so reviewers can see *why*
a score was throttled.

Routing thresholds (FROZEN per §6.1):

    conf_final ≥ 0.85    → AUTO_PROCESS
    0.50 ≤ < 0.85        → HUMAN_REVIEW
    conf_final < 0.50    → FLAG_UNCLEAR

Tier-1 terminal handling: when Layer 2 fires a part-number exact match
``terminated=True`` short-circuits the pipeline (spec §4.5). We emit a
single :class:`AttributePrediction` with ``attribute_name=""`` and the
matched part number as ``predicted_value``. This avoids changing
:class:`PipelineResult`'s schema while still surfacing the result.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import ThresholdsConfig
from ..contracts import (
    AttributePrediction,
    ExtractedInput,
    PipelineResult,
    ProductTypePrediction,
    Routing,
    RuleEngineResult,
    RuleHit,
    RuleTier,
    SemanticCandidate,
    SemanticHit,
    SemanticMatcherResult,
)


# ---------------------------------------------------------------------------
# Per-attribute fusion + cap + routing
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _AttrFusion:
    """Internal: one attribute's fused output before routing."""

    attribute_id: int | None
    attribute_name: str
    predicted_value: str
    conf_rule: float
    conf_embed_final: float
    conf_final: float
    low_sample_capped: bool
    pt_ambiguity_capped: bool


def _route(conf_final: float, thresholds: ThresholdsConfig) -> Routing:
    """Spec §4.4 routing — frozen thresholds (config-driven mirror of §6.1)."""
    if conf_final >= thresholds.decision.auto_process:
        return Routing.AUTO_PROCESS
    if conf_final >= thresholds.decision.human_review_floor:
        return Routing.HUMAN_REVIEW
    return Routing.FLAG_UNCLEAR


def _index_rule_hits_by_attribute(rules: RuleEngineResult) -> dict[str, RuleHit]:
    """Map attribute_name → highest-conf non-demoted rule hit.

    Tier-1 terminal hits don't carry a meaningful attribute (their
    ``attribute_name`` is empty) — they bypass this function entirely.
    """
    out: dict[str, RuleHit] = {}
    for hit in rules.hits:
        if hit.terminal:
            continue
        if not hit.attribute_name:
            continue
        if hit.demoted_by_2a:
            continue
        prev = out.get(hit.attribute_name)
        if prev is None or hit.conf_rule > prev.conf_rule:
            out[hit.attribute_name] = hit
    return out


def _pick_top_candidate(hit: SemanticHit) -> SemanticCandidate | None:
    """Return the top candidate by conf_embed_final, or None if empty."""
    if not hit.top_candidates:
        return None
    # SemanticScorer.score already sorts descending; we trust that contract.
    return hit.top_candidates[0]


def _fuse_one_attribute(
    semantic_hit: SemanticHit,
    rule_hits_by_attr: dict[str, RuleHit],
    thresholds: ThresholdsConfig,
    pt_conf: float,
) -> _AttrFusion | None:
    """Compute the fused score + caps for a single attribute."""
    top = _pick_top_candidate(semantic_hit)
    if top is None:
        return None

    rule_hit = rule_hits_by_attr.get(semantic_hit.attribute_name)
    conf_rule = float(rule_hit.conf_rule) if rule_hit is not None else 0.0
    # Layer 2 may have emitted a rule hit with a different predicted_value
    # than the semantic top-1. We follow §4.4: v*(A) is the semantic
    # argmax; if rule signal contradicts, the conf_rule still contributes
    # but the predicted value is the semantic top-1. The rule's
    # ``predicted_value`` is preserved only when there is no conflicting
    # semantic signal at all (handled at call site for Tier-1 terminal).
    alpha = thresholds.fusion.alpha
    conf_embed_final = float(top.conf_embed_final)
    conf_final = alpha * conf_rule + (1.0 - alpha) * conf_embed_final

    low_sample_cap = thresholds.clusters.low_sample_conf_cap
    pt_cap = thresholds.fusion.pt_ambiguity_cap
    band_low = thresholds.product_type_consensus.band_low

    pt_capped = False
    if pt_conf < band_low and conf_final > pt_cap:
        conf_final = pt_cap
        pt_capped = True

    low_sample_capped = False
    if top.low_sample and conf_final > low_sample_cap:
        conf_final = low_sample_cap
        low_sample_capped = True

    # Defensive clamp — fusion math should already keep this in [0, 1] but
    # caps + rule-engine values from non-canonical sources could drift.
    if conf_final < 0.0:
        conf_final = 0.0
    elif conf_final > 1.0:
        conf_final = 1.0

    return _AttrFusion(
        attribute_id=semantic_hit.attribute_id,
        attribute_name=semantic_hit.attribute_name,
        predicted_value=top.value,
        conf_rule=conf_rule,
        conf_embed_final=conf_embed_final,
        conf_final=conf_final,
        low_sample_capped=low_sample_capped,
        pt_ambiguity_capped=pt_capped,
    )


# ---------------------------------------------------------------------------
# Public Layer 4 entry point
# ---------------------------------------------------------------------------


class Layer4Decision:
    """Fuse rule + semantic outputs, apply caps, emit a routed prediction.

    Satisfies the :class:`src.contracts.Layer4Decision` Protocol.
    """

    def __init__(self, thresholds: ThresholdsConfig) -> None:
        self._thresholds = thresholds

    # ---- public surface ------------------------------------------------

    def fuse(
        self,
        x: ExtractedInput,
        rules: RuleEngineResult,
        semantic: SemanticMatcherResult | None,
        *,
        model_version: str,
        latency_ms: float,
    ) -> PipelineResult:
        """Return a :class:`PipelineResult` for one customer request."""
        # ---- Tier-1 terminal short-circuit (spec §4.2 / §4.5) ----------
        if rules.terminated:
            return self._build_tier1_terminal(x, rules, model_version, latency_ms)

        # ---- Normal path -----------------------------------------------
        if semantic is None:
            # Tier 2/3 rule hits with no semantic signal at all → emit
            # one prediction per non-terminal rule hit using conf_rule
            # only (rare path; mostly defensive).
            predictions = self._predictions_from_rule_hits_only(rules)
            return PipelineResult(
                input_ref=x.source_ref,
                source_type=x.source_type,
                product_type=None,
                predictions=predictions,
                latency_ms=latency_ms,
                model_version=model_version,
            )

        rule_hits_by_attr = _index_rule_hits_by_attribute(rules)
        pt_conf = float(semantic.product_type.pt_conf)

        predictions: list[AttributePrediction] = []
        for hit in semantic.hits:
            fused = _fuse_one_attribute(
                hit, rule_hits_by_attr, self._thresholds, pt_conf
            )
            if fused is None:
                continue
            predictions.append(
                AttributePrediction(
                    attribute_id=fused.attribute_id,
                    attribute_name=fused.attribute_name,
                    predicted_value=fused.predicted_value,
                    conf_rule=fused.conf_rule,
                    conf_embed_final=fused.conf_embed_final,
                    conf_final=fused.conf_final,
                    routing=_route(fused.conf_final, self._thresholds),
                    low_sample_capped=fused.low_sample_capped,
                    pt_ambiguity_capped=fused.pt_ambiguity_capped,
                )
            )

        return PipelineResult(
            input_ref=x.source_ref,
            source_type=x.source_type,
            product_type=semantic.product_type,
            predictions=tuple(predictions),
            latency_ms=latency_ms,
            model_version=model_version,
        )

    # ---- internals -----------------------------------------------------

    def _build_tier1_terminal(
        self,
        x: ExtractedInput,
        rules: RuleEngineResult,
        model_version: str,
        latency_ms: float,
    ) -> PipelineResult:
        terminal_hit = next(
            (h for h in rules.hits if h.terminal and h.tier == RuleTier.EXACT_PART_NUMBER),
            None,
        )
        if terminal_hit is None:                                # defensive
            return PipelineResult(
                input_ref=x.source_ref,
                source_type=x.source_type,
                product_type=None,
                predictions=(),
                latency_ms=latency_ms,
                model_version=model_version,
            )
        prediction = AttributePrediction(
            attribute_id=None,
            attribute_name="",                                  # marks Tier-1 terminal
            predicted_value=terminal_hit.predicted_value,
            conf_rule=float(terminal_hit.conf_rule),
            conf_embed_final=0.0,
            conf_final=float(terminal_hit.conf_rule),           # = 1.0 per §6.1
            routing=Routing.AUTO_PROCESS,
            low_sample_capped=False,
            pt_ambiguity_capped=False,
        )
        return PipelineResult(
            input_ref=x.source_ref,
            source_type=x.source_type,
            product_type=None,
            predictions=(prediction,),
            latency_ms=latency_ms,
            model_version=model_version,
        )

    def _predictions_from_rule_hits_only(
        self, rules: RuleEngineResult
    ) -> tuple[AttributePrediction, ...]:
        alpha = self._thresholds.fusion.alpha
        out: list[AttributePrediction] = []
        for hit in rules.hits:
            if hit.terminal:
                continue
            if hit.demoted_by_2a or not hit.attribute_name:
                continue
            # No semantic signal → conf_embed_final = 0; fusion reduces
            # to alpha * conf_rule.
            conf_final = max(0.0, min(1.0, alpha * float(hit.conf_rule)))
            out.append(
                AttributePrediction(
                    attribute_id=hit.attribute_id,
                    attribute_name=hit.attribute_name,
                    predicted_value=hit.predicted_value,
                    conf_rule=float(hit.conf_rule),
                    conf_embed_final=0.0,
                    conf_final=conf_final,
                    routing=_route(conf_final, self._thresholds),
                    low_sample_capped=False,
                    pt_ambiguity_capped=False,
                )
            )
        return tuple(out)
