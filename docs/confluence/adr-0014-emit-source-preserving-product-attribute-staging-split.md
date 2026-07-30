# ADR-014: Emit a Source-Preserving Product + Attribute Staging Split

> Source of truth: [`0014-emit-source-preserving-product-attribute-staging-split.md`](https://github.com/AshrithaG/eparts/blob/main/docs/0014-emit-source-preserving-product-attribute-staging-split.md) in the eparts repo. This page is a copy for reading; edit the repo, not this page.

## Status

Accepted

## Context

ETIM standardization rests on a core principle: **original supplier data is evidence; ETIM data is a standardized interpretation laid on top; confidence is how sure the system is about that interpretation.** For this to hold, ingestion must hand the matching stage data that (a) separates a *product* (the sellable SKU) from its *attributes*, and (b) preserves every original value together with where it came from — file, page, row, raw text, raw unit — so that any later ETIM mapping can be traced back to its source.

Today ingestion emits a single flat `IngestedRecord` (one row per source record, with `raw_fields` as a JSONB bag). That shape preserves source vocabulary but does not express product-vs-attribute granularity, gives attributes no individual identity, and has nowhere to carry per-attribute evidence (source page/row) or per-attribute confidence. It also forces every downstream consumer to re-derive product and attribute structure from an untyped blob.

There is also a real granularity mismatch across sources that the staging shape must absorb: a **CSV row** is naturally one product with many attribute *columns*, whereas a **datasheet PDF** is one product (a SKU) with many attribute *rows* extracted from the document. Both must land in the same canonical staging shape.

Options considered:

- **Keep the flat `IngestedRecord`** and let the matcher split product/attributes from the JSONB bag. Smallest ingestion change, but pushes structure-recovery and evidence-tracking into every consumer, and gives attributes no stable identity for per-attribute routing, confidence, or audit.
- **One wide staging row per product** with attributes as columns. Convenient for whole-product reads, but cannot carry per-attribute evidence/confidence without parallel columns, and reintroduces schema migration for every new attribute.
- **A two-table split: `staging_product` + `staging_raw_attribute`** (one product row; one evidence row per attribute). Each attribute row carries its own source evidence and confidence and has a stable identity. This matches the brief's staging model and is the natural input to per-attribute ETIM matching, routing, and audit.

## Decision

Ingestion will emit a **product + attribute split**: a `staging_product` row per sellable SKU and a `staging_raw_attribute` row per attribute, replacing the flat `IngestedRecord` as the output contract.

`staging_product` carries product identity and provenance: `supplier_id`, `supplier_sku`, `manufacturer`, `supplier_category`, `description`, `source_file_id`, `submission_id`, `processing_status`. Product identity for idempotency is `supplier_id + supplier_sku` (per source). `staging_raw_attribute` carries one row of evidence per attribute: `product_id`, `source_attribute_name`, `source_value`, `source_unit`, `source_text`, `source_page`, `source_row_number`, and `source_confidence`. Attribute identity for idempotency is `product_id + source_attribute_name`. Both tables are written with idempotent upserts, batched in one transaction per product, preserving the existing raw-bytes archival and quarantine paths unchanged.

Which source fields populate product identity versus become attribute rows is **declared per source** via `ProductMapping` on the source/parser config (`sku_field`, `manufacturer_field`, `category_field`, `description_field`, `unit_field`, `attribute_fields`, `exclude_fields`), so the CSV-column and PDF-row granularities both resolve to the same staging shape without code changes per source.

Crucially, ingestion **does not interpret** these values into ETIM. No field renaming, no ETIM class/feature/value assignment, no unit conversion happens here — those belong to the ETIM-aware matching stage, which reads staging and writes its results to its own tables (e.g. `matched_product_attribute`). ETIM must never overwrite ingestion's source-preserving output.

The legacy flat `IngestedRecord` path is retired after cutover (deprecate or dual-write during transition; tracked by EPARTS-302). Until a source declares a `ProductMapping`, it continues on the legacy flat path.

## Consequences

- Nothing from the supplier catalog is lost or flattened. Every value is individually addressable and traceable to file/page/row/raw-text, which is the evidence backbone the entire ETIM story depends on.
- Per-attribute identity makes per-attribute confidence (ADR-005/ADR-004 routing), per-attribute ETIM matching, and per-attribute audit natural — each is keyed on a real attribute row rather than reconstructed from a blob.
- The product/attribute boundary is configuration, not code. New sources and formats are onboarded by declaring a mapping; the CSV-vs-datasheet granularity difference is absorbed in config.
- Row counts grow relative to the flat shape (one row per attribute rather than one per record). For valve/actuator products with ~12–40 attributes this is a sizeable multiplier; the current Postgres stack (ADR-015) handles expected volumes, with indexes for product lookups.
- This **supersedes the staging design in ADR-007** in practice. ADR-007 specified a single tall staging table that also carried prediction/routing columns (`predicted_value`, `confidence_score`, `routing_status`). Under ETIM, ingestion's staging holds only *source evidence*; predicted values, match confidence, validation status, and review status move to a separate matching-owned table. ADR-007's "attribute-row, not wide" instinct is retained and reinforced; its column set and single-table assumption are not.
- The PIMS writeback contract shifts accordingly. The brief keys PIMS output on `product_id + etim_release_id + etim_class_id + etim_feature_id` rather than `submission_id + attribute_id`; ADR-006's idempotency mechanism needs to be revisited against this (flagged in the ADR assessment, not resolved here).
- A clean cutover is required to avoid two parallel write paths. The transition (dual-write vs deprecate) and the update to the §6.1 output contract are explicit follow-ups (EPARTS-302).
- Missing-SKU handling must be defined (quarantine vs synthesized id) — an open item feeding the source mapping config.

## Requirements Traceability

- **Source:** `ETIM_IMPLEMENTATION_BRIEF.md` (Staging Layer; Staging Tables; "Original supplier data = evidence"); `INGESTION_ETIM_TICKET_MAP.md` (ING-E4/E5/E6/E7/E9)
- **Tickets:** EPARTS-297 (ProductMapping config); EPARTS-298 (staging schema); EPARTS-299 (writer rework); EPARTS-302 (retire flat path); parent EPARTS-154
- **QASs:** QAS-1 (accuracy — evidence preserved for traceable correction); QAS-3 (new category/attribute as data + config, not schema migration)
- **Related ADRs:** ADR-007 (superseded in part — see above); ADR-013 (reference layer the staged data is matched against); ADR-015 (datastore); ADR-004/ADR-005 (per-attribute routing/threshold consume attribute identity); ADR-006 (PIMS idempotency to be re-keyed)
