"""Layer 3 [3a] encoder tests (V1 spec §4.3 [3a]).

The encoder loads ~130 MB of model weights on first use; we share one
instance across the whole module via a session-scoped fixture.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.config import EncoderConfig
from src.layer3_semantic import Encoder

# ML-CT component: product search (M3a, encoder) — every test here is ML-CT.
pytestmark = pytest.mark.ml_ct


@pytest.fixture(scope="module")
def encoder(settings) -> Encoder:
    return Encoder(settings.encoder)


def test_encoder_advertises_configured_dimension(settings):
    """Construction must not touch the model — dimension comes from config."""
    enc = Encoder(settings.encoder)
    assert enc.dimension == 384
    assert enc.model_id == "BAAI/bge-small-en-v1.5"


def test_encode_returns_float32_with_correct_shape(encoder):
    texts = ["Temperature sensor 24 VAC", "Damper actuator 0-10 VDC"]
    vectors = encoder.encode(texts)
    assert vectors.dtype == np.float32
    assert vectors.shape == (2, 384)


def test_encoded_vectors_are_l2_normalized(encoder):
    texts = ["thermistor probe", "differential pressure sensor", "actuator"]
    vectors = encoder.encode(texts)
    norms = np.linalg.norm(vectors, axis=1)
    # Frozen normalize='l2' in config → every row should be unit norm.
    np.testing.assert_allclose(norms, 1.0, atol=1e-5)


def test_encode_one_returns_1d_vector(encoder):
    v = encoder.encode_one("strap-on thermistor")
    assert v.shape == (384,)
    assert np.isclose(np.linalg.norm(v), 1.0, atol=1e-5)


def test_semantically_similar_strings_score_higher(encoder):
    """Sanity check the model: synonyms should be closer than disjoint topics."""
    anchor = encoder.encode_one("temperature sensor")
    similar = encoder.encode_one("thermistor probe")
    different = encoder.encode_one("damper actuator with spring return")
    sim_same = float(anchor @ similar)
    sim_diff = float(anchor @ different)
    assert sim_same > sim_diff, f"expected synonyms closer, got {sim_same=} {sim_diff=}"


def test_config_dimension_mismatch_raises(settings):
    """If encoder.yaml lies about the dimension we should fail loudly."""
    bad = EncoderConfig(
        model_id=settings.encoder.model_id,
        dimension=999,                                       # WRONG on purpose
        normalize=settings.encoder.normalize,
        batch_size=settings.encoder.batch_size,
        device=settings.encoder.device,
    )
    enc = Encoder(bad)
    with pytest.raises(ValueError, match="declares dimension=999"):
        enc.encode(["anything"])


# ===========================================================================
# ML-CT P1 boundary test (search) — see eparts_doc/ML_CT_Test_Plan.md Part D
# ===========================================================================


def test_empty_string_encodes_to_valid_vector(encoder):
    """Spec §4.1 allows empty `text`. The encoder must return a well-formed
    384-d vector (no crash, no NaN/Inf), so an empty description flows
    through Layer 3 instead of blowing up. The vector is still L2-normalized
    (the model emits a non-degenerate embedding for the empty/CLS input)."""
    v = encoder.encode_one("")
    assert v.shape == (384,)
    assert v.dtype == np.float32
    assert np.isfinite(v).all()                 # no NaN / Inf
    # L2-normalized like every other output (norm 1, or 0 only if degenerate).
    norm = float(np.linalg.norm(v))
    assert np.isclose(norm, 1.0, atol=1e-5)
