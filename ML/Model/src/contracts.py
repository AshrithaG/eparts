"""Typed inter-layer contracts for the V1 confidence-scoring pipeline.

Implements the layer boundaries of V1_Engineering_Spec §1.1 as immutable
dataclasses and structural Protocols. Concrete implementations (encoders,
index types, scoring strategies) are swappable without touching downstream
consumers as long as they satisfy these contracts.

Naming follows the spec's vocabulary verbatim (``conf_rule``, ``conf_embed``,
``conf_final``, ``PT_conf``, ``Mahalanobis``). Do not introduce synonyms.

Layer outputs:
    Layer 1  → :class:`ExtractedInput`
    Layer 2  → :class:`RuleEngineResult`            (sequence of :class:`RuleHit`)
    Layer 3  → :class:`SemanticMatcherResult`       (one :class:`ProductTypePrediction`
                                                     + sequence of :class:`SemanticHit`)
    Layer 4  → :class:`PipelineResult`              (sequence of :class:`AttributePrediction`)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Source-type tag (Layer 1 input classification)
# ---------------------------------------------------------------------------


class SourceType(str, Enum):
    """Origin of the customer request that Layer 1 consumed.

    The tag flows downstream so calibration and evaluation can stratify
    metrics by intake channel (CSV submissions are clean; OCR'd PDFs are
    noisy). See §5.3 secondary-calibration caveat.
    """

    CSV = "csv"
    PDF_TEXT = "pdf_text"
    PDF_OCR = "pdf_ocr"
    EMAIL = "email"
    IMAGE = "image"           # standalone JPG/PNG inputs; same OCR pipeline as
                              # PDF_OCR but tagged separately for downstream
                              # calibration stratification (added 2026-05-19 per
                              # ExtractionHandoff_Spec.md v0.2)


# ---------------------------------------------------------------------------
# Layer 1 — extraction output
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExtractedInput:
    """Normalized output of Layer 1.

    Args:
        source_type: Which intake channel produced this input.
        text: Canonical free-text string fed to the Layer 3 encoder. For CSV
            inputs this is typically the concatenation of description columns;
            for emails / PDFs it is the cleaned body.
        structured_fields: Key/value pairs Layer 2 can match deterministically
            (e.g. ``{"part_number": "T-6000", "manufacturer_name":
            "Johnson Controls"}``). Empty when only free text is available.
        normalized_units: Attribute name → ``(value, canonical_unit)`` pairs
            extracted from text via the unit-alias map. Layer 2 uses these
            directly without re-extracting from text.
        source_ref: Optional opaque identifier (file path, message-id,
            row index) preserved for audit logging in M6.
    """

    source_type: SourceType
    text: str
    structured_fields: Mapping[str, str] = field(default_factory=dict)
    normalized_units: Mapping[str, tuple[str, str]] = field(default_factory=dict)
    source_ref: str | None = None


# ---------------------------------------------------------------------------
# Layer 2 — rule engine output
# ---------------------------------------------------------------------------


class RuleTier(str, Enum):
    """Which rule tier fired for a given attribute (V1 spec §4.2)."""

    EXACT_PART_NUMBER = "exact_part_number"  # Tier 1, terminal
    MANUFACTURER_FUZZY = "manufacturer_fuzzy"  # Tier 2
    NUMERIC_UNIT = "numeric_unit"  # Tier 3
    NONE = "none"


@dataclass(frozen=True, slots=True)
class RuleHit:
    """One attribute prediction from the rule engine.

    ``conf_rule`` carries the spec-fixed values (1.0 terminal, 0.85 fuzzy,
    0.65 partial, 0.0 no-match). The 2A valid-value guardrail demotes
    any hit whose ``(attribute_name, predicted_value)`` is absent from
    ``2A_Values_Per_Attribute.csv`` — demoted hits surface with
    ``demoted_by_2a=True`` and ``conf_rule=0.0`` so Layer 3 adjudicates.
    """

    attribute_id: int | None
    attribute_name: str
    predicted_value: str
    unit_suffix: str | None
    conf_rule: float
    tier: RuleTier
    terminal: bool                  # True iff Tier 1 (exact part-number)
    demoted_by_2a: bool = False     # True iff 2A guardrail demoted the hit


@dataclass(frozen=True, slots=True)
class RuleEngineResult:
    """Aggregated output of Layer 2 for a single :class:`ExtractedInput`.

    ``terminated`` short-circuits the pipeline per spec §4.2 / §4.5: when a
    part-number exact match fires, Layer 3 is skipped entirely.
    """

    hits: tuple[RuleHit, ...]
    terminated: bool


# ---------------------------------------------------------------------------
# Layer 3 — semantic matcher output
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProductTypePrediction:
    """Voted ProductType from the FAISS top-K consensus.

    ``pt_conf`` follows §4.3 [3c]: ``vote[PT] / Σ vote[*]`` over the
    similarity-weighted ProductType ballots cast by the top-K neighbors.
    The three bands (>= 0.80, [0.60, 0.80), < 0.60) drive the spec's
    ambiguity cap in Layer 4.
    """

    product_type_id: int
    product_type_name: str
    pt_conf: float


@dataclass(frozen=True, slots=True)
class SemanticCandidate:
    """One candidate value for one attribute, with confidence math.

    Args:
        value: Candidate attribute value (already valid in 2A; clusters with
            < min_size members are still included but flagged via
            ``low_sample``).
        conf_embed: Raw Gaussian decay ``exp(-D² / 2σ²)`` from the per-cluster
            Mahalanobis distance.
        conf_embed_final: ``conf_embed * usage_prior`` per §4.3 [3d].
        cluster_n: Size of the cluster that produced ``μ, Σ``.
        mahalanobis_d2: Squared Mahalanobis distance (kept for diagnostics).
        usage_count: 2A Usage_Count value used by the log prior.
        low_sample: True iff ``cluster_n < clusters.min_size``; Layer 4 will
            cap ``conf_final`` at ``clusters.low_sample_conf_cap``.
    """

    value: str
    conf_embed: float
    conf_embed_final: float
    cluster_n: int
    mahalanobis_d2: float
    usage_count: int
    low_sample: bool


@dataclass(frozen=True, slots=True)
class SemanticHit:
    """Top-3 candidate values for a single attribute under PT_predicted."""

    attribute_id: int
    attribute_name: str
    top_candidates: tuple[SemanticCandidate, ...]   # length 1..3


@dataclass(frozen=True, slots=True)
class SemanticMatcherResult:
    """Full Layer 3 output for one :class:`ExtractedInput`.

    Returned for every input that reaches Layer 3, i.e. when Layer 2 did
    not terminate with a Tier-1 hit.
    """

    product_type: ProductTypePrediction
    hits: tuple[SemanticHit, ...]


# ---------------------------------------------------------------------------
# Layer 4 — decision output
# ---------------------------------------------------------------------------


class Routing(str, Enum):
    """Final routing decision per §4.4."""

    AUTO_PROCESS = "auto_process"      # conf_final >= 0.85
    HUMAN_REVIEW = "human_review"      # 0.50 <= conf_final < 0.85
    FLAG_UNCLEAR = "flag_unclear"      # conf_final < 0.50


@dataclass(frozen=True, slots=True)
class AttributePrediction:
    """Fused prediction for one attribute, ready for downstream consumption.

    ``conf_final`` is the fused score after the §4.4 caps:
        * PT ambiguity cap (PT_conf < 0.60 → cap 0.75)
        * Low-sample cluster cap (n < min_size → cap 0.7)
    Flags expose *why* a cap was applied so reviewers can interpret the score.
    """

    attribute_id: int | None
    attribute_name: str
    predicted_value: str
    conf_rule: float
    conf_embed_final: float
    conf_final: float
    routing: Routing
    low_sample_capped: bool
    pt_ambiguity_capped: bool


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """End-to-end pipeline result for a single customer request.

    Args:
        input_ref: Echo of ``ExtractedInput.source_ref`` for tracing.
        source_type: Intake channel (carried through for metrics stratification).
        product_type: ``None`` only when Tier-1 part-number match terminated
            the pipeline before Layer 3 ran.
        predictions: One :class:`AttributePrediction` per applicable
            attribute (~ProductType-attribute count, avg 4.2 per §3.2).
        latency_ms: End-to-end wall time (encode + retrieve + score + fuse).
        model_version: Run-directory timestamp under ``artifacts/v1/`` that
            produced the artifacts used for this prediction. CAP-ML-03
            requires this to be reported on every response.
    """

    input_ref: str | None
    source_type: SourceType
    product_type: ProductTypePrediction | None
    predictions: tuple[AttributePrediction, ...]
    latency_ms: float
    model_version: str


# ---------------------------------------------------------------------------
# Structural protocols — what each layer must implement.
# Concrete classes do not need to inherit; duck-typing is enforced by mypy.
# ---------------------------------------------------------------------------


@runtime_checkable
class Layer1Extractor(Protocol):
    """Layer 1 (§4.1): produce one :class:`ExtractedInput` per request."""

    def extract(self, payload: bytes | str, source_type: SourceType) -> ExtractedInput:
        ...


@runtime_checkable
class Layer2RuleEngine(Protocol):
    """Layer 2 (§4.2): produce rule hits + termination flag for one input."""

    def apply(self, x: ExtractedInput) -> RuleEngineResult:
        ...


@runtime_checkable
class Layer3SemanticMatcher(Protocol):
    """Layer 3 (§4.3): encode → FAISS → consensus → per-cluster scoring.

    ``allowed_attributes`` restricts which attributes are scored; ``None``
    means "use the spec default" (= ProductTypeAttributes[PT_predicted]).
    """

    def match(
        self,
        x: ExtractedInput,
        allowed_attributes: Iterable[int] | None = None,
    ) -> SemanticMatcherResult:
        ...


@runtime_checkable
class Layer4Decision(Protocol):
    """Layer 4 (§4.4): fuse, apply caps, route, and emit :class:`PipelineResult`."""

    def fuse(
        self,
        x: ExtractedInput,
        rules: RuleEngineResult,
        semantic: SemanticMatcherResult | None,
        *,
        model_version: str,
        latency_ms: float,
    ) -> PipelineResult:
        ...
