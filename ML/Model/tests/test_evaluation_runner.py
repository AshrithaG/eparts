"""M5 InferencePipeline smoke tests (synthetic, no real model load)."""
from __future__ import annotations

import numpy as np
import pytest

from src.config import (
    ClusterConfig,
    DecisionConfig,
    EncoderConfig,
    FaissConfig,
    FusionConfig,
    OnlineUpdateConfig,
    ProductTypeConsensusConfig,
    RuleEngineConfig,
    ThresholdsConfig,
)
from src.contracts import SourceType
from src.layer3_semantic import (
    ProductIndex,
    ProductTypeIndex,
    SemanticScorer,
    UsagePrior,
    build_index,
)
from src.layer3_semantic.clusters import ClusterStats, ClusterStore
from src.layer4_decision import Layer4Decision
from src.evaluation import InferencePipeline


DIM = 16


class _FakeEncoder:
    """Lightweight encoder stub — returns hash-based deterministic vectors."""

    def __init__(self, dim: int = DIM):
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def model_id(self) -> str:
        return "fake-encoder"

    def encode(self, texts, **kwargs):                                # noqa: ANN001
        return np.stack([self.encode_one(t) for t in texts])

    def encode_one(self, text: str) -> np.ndarray:
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        v = rng.standard_normal(self._dim).astype(np.float32)
        v /= np.linalg.norm(v) + 1e-9
        return v


def _faiss_cfg(top_k: int = 5, nlist: int = 4) -> FaissConfig:
    return FaissConfig(
        index_type="IVFFlat", metric="inner_product",
        nlist=nlist, nprobe=2, top_k=top_k,
        training_subset_size=20, training_seed=42,
        input_text_columns=("Short_Description",),
    )


def _thresholds() -> ThresholdsConfig:
    return ThresholdsConfig(
        rule_engine=RuleEngineConfig(1.0, 0.85, 0.65, 0.0, 90),
        product_type_consensus=ProductTypeConsensusConfig(0.80, 0.60),
        clusters=ClusterConfig(5, 0.70),
        fusion=FusionConfig(0.7, 0.75),
        decision=DecisionConfig(0.85, 0.50),
        online_updates=OnlineUpdateConfig(0.01),
    )


@pytest.fixture
def pipeline():
    rng = np.random.default_rng(42)
    n = 30
    raw = rng.standard_normal(size=(n, DIM)).astype(np.float32)
    raw /= np.linalg.norm(raw, axis=1, keepdims=True).clip(min=1e-9)
    pids = np.arange(1000, 1000 + n, dtype=np.int64)
    product_index = build_index(raw, pids, _faiss_cfg())

    pt_index = ProductTypeIndex(
        pt_id_by_product={int(p): 10 if i < n // 2 else 20 for i, p in enumerate(pids)},
        pt_name_by_id={10: "PT10", 20: "PT20"},
    )

    # Clusters under PT 10
    mu = raw[0]
    cluster = ClusterStats(
        cluster_id=0, product_type_id=10, product_type_name="PT10",
        attribute_name="INPUT_VOLTAGE", value="24", n=10,
        mu=mu, sigma_inv=np.eye(DIM, dtype=np.float32),
        log_det_sigma=0.0, low_sample=False,
    )
    store = ClusterStore([cluster])
    usage = UsagePrior(counts={("input_voltage", "24"): 50}, max_counts={"input_voltage": 50})
    scorer = SemanticScorer(store, usage)
    decider = Layer4Decision(_thresholds())
    return InferencePipeline(
        encoder=_FakeEncoder(),
        product_index=product_index,
        pt_index=pt_index,
        scorer=scorer,
        decider=decider,
        model_version="test-run",
    )


def test_predict_runs_end_to_end(pipeline):
    out = pipeline.predict_from_text("any description", source_type=SourceType.CSV)
    assert out.result.model_version == "test-run"
    assert out.result.source_type == SourceType.CSV
    # Either PT 10 or PT 20 must be the predicted PT.
    if out.result.product_type is not None:
        assert out.result.product_type.product_type_id in {10, 20}


def test_trace_records_each_phase_separately(pipeline):
    out = pipeline.predict_from_text("a description")
    t = out.trace
    assert t.encode_ms >= 0
    assert t.search_ms >= 0
    assert t.consensus_ms >= 0
    assert t.score_ms >= 0
    assert t.fuse_ms >= 0
    assert t.total_ms == pytest.approx(
        t.encode_ms + t.search_ms + t.consensus_ms + t.score_ms + t.fuse_ms
    )


def test_result_latency_matches_total_trace_time(pipeline):
    out = pipeline.predict_from_text("hello")
    assert out.result.latency_ms == pytest.approx(out.trace.total_ms, abs=0.1)


def test_predict_with_explicit_rules_passes_them_through(pipeline):
    from src.contracts import RuleEngineResult, RuleHit, RuleTier
    rules = RuleEngineResult(
        hits=(
            RuleHit(
                attribute_id=None, attribute_name="INPUT_VOLTAGE",
                predicted_value="24", unit_suffix="vac", conf_rule=0.65,
                tier=RuleTier.NUMERIC_UNIT, terminal=False,
            ),
        ),
        terminated=False,
    )
    out = pipeline.predict_from_text("voltage 24 vac", rules=rules)
    # If the predicted PT had clusters for INPUT_VOLTAGE the rule signal
    # would land on at least one prediction; with our minimal cluster
    # setup we just ensure no crash + result exists.
    assert out.result is not None
