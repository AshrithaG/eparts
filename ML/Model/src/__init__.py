"""eParts ML Confidence Scoring System — V1 source package.

**Scope (revised 2026-05-13):** the ML team owns the *scoring and routing*
layers of the V1 pipeline. Layer 1 (text extraction) is owned by a
separate sub-team using mature LLM / NER models — see
``eparts_doc/ExtractionHandoff_Spec.md`` for the interface contract.
The deterministic Layer 1 prototype lives under ``archive/`` for reference.

Layer entry points and shared contracts:

    src.contracts          Typed inter-layer dataclasses and Protocols.
    src.config             YAML-backed settings tree.
    src.data               Raw-data loaders + stratified splits (M1).
    src.layer2_rules       Layer 2 — rule engine with 2A guardrail (M2).
    src.layer3_semantic    Layer 3 — encoder + FAISS + clusters + scoring (M3 — shipped).
    src.layer4_decision    Layer 4 — fusion + caps + routing + σ calibration (M4 — shipped; M6 pending).
    src.service            REST endpoint + Prometheus telemetry (M7 — pending).
"""

from . import contracts  # re-exported for `from src import contracts`

__all__ = ["contracts"]
