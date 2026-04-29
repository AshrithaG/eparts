# ADR-003: Use a Hybrid Rule Engine and Semantic Similarity for Attribute Prediction

## Status

Tentative

## Context

The Prediction Service must map raw supplier text to canonical attribute values and emit per-attribute confidence scores that the Routing Engine can compare against a threshold. Three properties matter: accuracy under data scarcity, explainability for the catalog team, and ability to handle free-text inputs that rules cannot anticipate.

The team targets approximately 200 labeled examples for the initial training set, but a calibrated pure-ML classifier typically needs around 830 examples to produce well-behaved confidence scores. eParts has stated an explainability requirement: catalog reviewers need to understand why an item was routed to review.

Three alternatives were considered:

- **Pure rules.** Deterministic and fully explainable, but estimated coverage is only 40–60% of supplier inputs because suppliers use inconsistent terminology that rules cannot enumerate.
- **Pure ML classifier.** Handles unseen text well, but with the available labeled data the confidence scores are not well-calibrated. Confidence scores are also opaque, undermining the explainability requirement.
- **Hybrid: rules first, semantic similarity (TF-IDF + cosine) for unmatched inputs.** Rules give a high-precision fallback when data is scarce; the semantic layer covers free-text inputs the rules miss. Reason codes can be attached to low-confidence items.

A weighted decision matrix scored the hybrid approach highest (2.50) against pure rules (1.85) and pure ML (1.70), with criteria weighted toward accuracy under low data, explainability, and free-text coverage.

## Decision

We will implement the Prediction Service as a hybrid pipeline. A rule engine runs first against each normalized attribute. Where rules do not match, a semantic similarity layer (TF-IDF vectorization with cosine similarity against canonical value embeddings) produces a candidate value. The final confidence is a weighted composite:

```
conf_final = α · conf_rule + (1 - α) · conf_embed
```

with an initial value of `α = 0.7`. Reason codes from the rule layer are attached to each prediction and surfaced in the Human Review Queue for low-confidence items. Both layers live inside the `prediction` package behind `PredictionServiceInterface` (ADR-002).

## Consequences

- Rules carry the prediction under data scarcity, so the system has a usable accuracy floor before sufficient labeled data accumulates.
- Reason codes from the rule layer satisfy the explainability requirement. Reviewers see why an attribute was flagged, which is expected to support adoption by Brian and Dewey on the catalog team.
- The semantic layer can be replaced or upgraded (e.g., to embeddings from a transformer) without touching the rule layer or the Routing Engine, because both layers sit behind `PredictionServiceInterface`.
- The α weighting is a sensitivity point. Wrong α suppresses the more accurate signal source and produces miscalibrated confidence, which propagates directly into routing errors. The initial value of 0.7 is a guess; it must be calibrated against prototype data (see Refinement 3 in the report).
- The decision is tentative and carries explicit reconsideration triggers. If pure rules cover ≥85% of inputs at confidence ≥0.90, the semantic layer adds complexity without value and we should switch to pure rules. If labeled data exceeds ~800 examples and a pure ML model achieves ≥85% accuracy with calibrated confidence, the hybrid approach loses its advantage and we should switch to pure ML.
- Per-attribute-type α weights may be more accurate than a single global α, since some attributes (e.g., `SUPPLY_VOLTAGE`) are inherently easier to predict than others (e.g., `DESCRIPTION`). The retraining pipeline can store learned per-type weights as configuration once Refinement 3 produces evidence.

## Requirements Traceability

- **HLRs:** HLR-3 (predict with confidence)
- **FRs:** FR-3 (per-attribute predictions with confidence scores)
- **QASs:** QAS-1 (accuracy — hybrid provides usable accuracy floor under data scarcity); QAS-5 (reason codes from rules support drift interpretation)
- **Constraints:** C-3, DC-1 (Python ML); C-4 (phase scope limits labeled data, favoring hybrid over pure ML)
- **Scenarios:** SCEN-1 (high-confidence path), SCEN-2 (low-confidence path with reason codes)
