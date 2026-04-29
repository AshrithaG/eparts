# ADR-004: Per-Attribute ML Routing

**Status:** Accepted  
**Date:** 2026-03-19  
**Deciders:** Data/ML Lead, Architecture Lead  
**Traced from:** REQ-008 (Multi-Vendor Format Support), ARCH-003, Risk 3 (ML Uncertainty)  
**Contributing meetings:** Meeting 2026-02-19, Meeting 2026-03-05, Meeting 2026-03-19  
**Contributing sessions:** Jim 2026-03-15

---

## Context

The eParts catalog contains diverse attribute types with fundamentally different characteristics:
product names are semi-structured free text, category codes come from a controlled vocabulary,
technical specifications involve numeric values with units from PDF tables, and unit of measure
is a constrained enumeration.

POC experiments (Meeting 4, Mar 05) confirmed that a single model trained on all attribute types
produces mediocre results. The BERT-based model achieved 0.91 F1 on category codes but only 0.68
on technical specifications. The all-MiniLM semantic matcher scored 0.89 on product names but
failed on numeric specs where semantic similarity is meaningless.

The team has three candidate models (BERT, all-MiniLM, fine-tuned LLM extractor) with different
strengths. Risk 3 identifies this model selection uncertainty as a key risk. Rather than forcing
a single-model decision, the architecture should let each attribute type use its best model.

## Decision

We implement **per-attribute routing** where each attribute type flows through its own model
and threshold configuration, managed via a YAML routing table.

**Routing Configuration** is maintained in `config/attribute_routing.yaml`. Each attribute entry
specifies: primary model, calibrated threshold (per ADR-001), alpha weight for hybrid scoring,
and a fallback strategy when confidence drops below the 0.50 safety floor. Current mappings:
`product_name` → all-MiniLM (α=0.6, threshold 0.88), `category_code` → BERT classifier
(α=0.2, threshold 0.82), `technical_spec` → LLM extractor (α=0.3, threshold 0.75),
`unit_of_measure` → enum-matcher (α=0.1, threshold 0.90).

**Pipeline Flow:** Ingestion parses vendor documents and identifies attribute fields → each
attribute dispatches to its configured model → hybrid scoring (ADR-001) computes calibrated
confidence → predictions write to staging (ADR-002) and route through review (ADR-003).

**Model Lifecycle.** Each attribute's model is independently versioned, trained, and evaluated.
A category code model upgrade does not require revalidating product name. New attribute types
are onboarded by adding a routing entry and deploying a model — no pipeline code changes.

## Consequences

**Positive:**
- Each attribute uses the architecture best suited to its data, maximizing per-attribute
  accuracy over single-model average-case optimization.
- Independent versioning enables targeted retraining on the worst-performing attribute without
  disrupting well-performing ones.
- The routing table is a single, auditable configuration surface for the entire ML pipeline.
- New attributes are a config change, supporting the client's goal of expanding coverage.

**Negative:**
- Multiple models to train, evaluate, and maintain. With 4 attributes and 3 candidates, the
  experimentation matrix is 12 combinations.
- Pipeline complexity increases — the dispatcher must handle model failures, timeouts, and
  version mismatches independently per attribute.
- Cross-attribute consistency is not guaranteed. A SKU may have high-confidence name but
  low-confidence category, creating a fragmented review experience.

## Alternatives Considered

**Single Model for All Attributes.** One fine-tuned LLM extracts everything in a single pass.
Rejected — POC showed a 23-point F1 spread across attribute types with every unified model
tested. A single model optimizes for average performance, underserving hard attributes while
wasting capacity on easy ones, and creates a single point of failure.

**Manual Rules for Some + ML for Others.** Deterministic rules (regex, lookup tables) for
structured attributes, ML for unstructured. Rejected as permanent architecture because rules
require manual updates when categories or units change. The `enum-matcher` for unit of measure
borrows from this idea while staying within the ML routing framework.
