"""End-to-end inference wiring for M5 evaluation.

Composes M3a (encoder + FAISS), M3b (PT consensus + clusters), M3c
(per-attribute scoring), and M4 (fusion + caps + routing) into a single
``predict`` call that satisfies the
:class:`src.contracts.Layer3SemanticMatcher` + Layer 4 cycle without
ever leaving Python.

Used by ``scripts/m5_evaluate.py`` to score the test split, and
re-usable as the inference backbone for M7's REST endpoint.

Per-phase wall time is recorded on every :class:`InferenceTrace` so M5
can produce the spec §5.5 latency histogram.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ..contracts import (
    ExtractedInput,
    PipelineResult,
    RuleEngineResult,
    SemanticMatcherResult,
    SourceType,
)
from ..layer3_semantic import (
    Encoder,
    ProductIndex,
    ProductTypeIndex,
    SemanticScorer,
    compute_pt_consensus,
)
from ..layer4_decision import Layer4Decision


@dataclass(frozen=True, slots=True)
class InferenceTrace:
    """Per-phase wall times for a single query (in milliseconds)."""

    encode_ms: float
    search_ms: float
    consensus_ms: float
    score_ms: float
    fuse_ms: float

    @property
    def total_ms(self) -> float:
        return (
            self.encode_ms
            + self.search_ms
            + self.consensus_ms
            + self.score_ms
            + self.fuse_ms
        )


@dataclass(frozen=True, slots=True)
class InferenceOutput:
    """Bundle of pipeline result + phase trace + raw intermediates.

    ``semantic`` is preserved so M5 evaluation can read full top-3
    candidate lists per attribute without re-encoding and re-scoring.
    """

    result: PipelineResult
    trace: InferenceTrace
    semantic: SemanticMatcherResult | None = None
    query_vector: np.ndarray | None = None


class InferencePipeline:
    """Encoder + FAISS + consensus + scorer + decider — one call."""

    def __init__(
        self,
        encoder: Encoder,
        product_index: ProductIndex,
        pt_index: ProductTypeIndex,
        scorer: SemanticScorer,
        decider: Layer4Decision,
        model_version: str,
    ) -> None:
        self._encoder = encoder
        self._product_index = product_index
        self._pt_index = pt_index
        self._scorer = scorer
        self._decider = decider
        self._model_version = model_version

    @property
    def model_version(self) -> str:
        return self._model_version

    # ---- public API ----------------------------------------------------

    def predict_from_text(
        self,
        text: str,
        *,
        source_type: SourceType = SourceType.CSV,
        source_ref: str | None = None,
        rules: RuleEngineResult | None = None,
    ) -> InferenceOutput:
        """Run M3+M4 end-to-end on a single text query.

        Args:
            text: Customer-facing or self-test product description.
            source_type: Carried into the :class:`PipelineResult` for
                downstream stratification (default ``CSV``).
            source_ref: Opaque trace identifier; defaults to ``None``.
            rules: Optional :class:`RuleEngineResult`. ``None`` →
                construct an empty ``(hits=(), terminated=False)``.

        Returns:
            :class:`InferenceOutput` bundling the pipeline result + a
            per-phase :class:`InferenceTrace`.
        """
        x = ExtractedInput(source_type=source_type, text=text, source_ref=source_ref)

        if rules is None:
            rules = RuleEngineResult(hits=(), terminated=False)

        # Encode --------------------------------------------------------
        t0 = time.perf_counter()
        q_vec = self._encoder.encode_one(text)
        encode_ms = (time.perf_counter() - t0) * 1000.0

        # FAISS search --------------------------------------------------
        t0 = time.perf_counter()
        [hits] = self._product_index.search(q_vec)
        search_ms = (time.perf_counter() - t0) * 1000.0

        # PT consensus --------------------------------------------------
        t0 = time.perf_counter()
        pt_pred = compute_pt_consensus(hits, self._pt_index)
        consensus_ms = (time.perf_counter() - t0) * 1000.0

        # Semantic scoring (or skip if no PT) ---------------------------
        score_ms = 0.0
        semantic_result = None
        if pt_pred is not None:
            t0 = time.perf_counter()
            semantic_result = self._scorer.score(q_vec, pt_pred)
            score_ms = (time.perf_counter() - t0) * 1000.0

        # Layer 4 fusion -----------------------------------------------
        t0 = time.perf_counter()
        result = self._decider.fuse(
            x,
            rules,
            semantic_result,
            model_version=self._model_version,
            latency_ms=encode_ms + search_ms + consensus_ms + score_ms,
        )
        fuse_ms = (time.perf_counter() - t0) * 1000.0

        # Total latency on the result reflects the full chain.
        # Rebuild only if needed to update latency_ms; PipelineResult is frozen.
        from dataclasses import replace
        result = replace(result, latency_ms=encode_ms + search_ms + consensus_ms + score_ms + fuse_ms)

        return InferenceOutput(
            result=result,
            trace=InferenceTrace(
                encode_ms=encode_ms,
                search_ms=search_ms,
                consensus_ms=consensus_ms,
                score_ms=score_ms,
                fuse_ms=fuse_ms,
            ),
            semantic=semantic_result,
            query_vector=q_vec,
        )
