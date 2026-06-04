"""eParts LLM-Based Layer 3 — POC.

Public surface for the POC. The library is intentionally small so it can
be reviewed end-to-end by two people (per the QA plan):

    schemas       — Pydantic models for grounding pack, prediction, provenance.
    llm_client    — Abstract LLMClient + OllamaClient / MockLLMClient.
    prompt        — System prompt and user-prompt rendering.
    grounding     — Retrieval stub + grounding-pack builder.
    extract       — End-to-end extract() entry point.
"""

from .extract import extract
from .grounding import build_grounding_pack, load_fixtures, retrieve_top_k_stub
from .llm_client import LLMClient, MockLLMClient, OllamaClient, build_client
from .schemas import (
    AttributePrediction,
    AttributeSpec,
    ExtractionResult,
    GroundingPack,
    LLMPrediction,
    NeighborDigest,
    Provenance,
)

__all__ = [
    "extract",
    "build_grounding_pack",
    "load_fixtures",
    "retrieve_top_k_stub",
    "LLMClient",
    "OllamaClient",
    "MockLLMClient",
    "build_client",
    "GroundingPack",
    "NeighborDigest",
    "AttributeSpec",
    "AttributePrediction",
    "LLMPrediction",
    "ExtractionResult",
    "Provenance",
]
