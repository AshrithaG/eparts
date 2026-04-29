# ADR-007: Use an Attribute-Row Canonical Schema for the Staging Table

## Status

Accepted

## Context

The Normalization stage transforms heterogeneous supplier formats (CSV, PDF, email-extracted key-value pairs) into a canonical structure that the Prediction Service, Routing Engine, and Writeback Service can consume uniformly. The shape of this canonical schema is an architecturally significant decision because it determines how much work it takes to add a new product category, how easily attributes can be routed individually, and how the staging tables grow over time.

The current scope is valves and actuators, but the client (Harsha) has stated that category expansion is expected after the pilot. Quality attribute QA-3 (Modifiability — new category) is rated Medium/Medium and explicitly requires that adding a category not force a structural change to routing or writeback.

Two structural options were considered:

- **Wide schema (one row per record).** Each record is a single row with one column per attribute (`voltage`, `port_size`, `connection_type`, etc.). Adding a new category requires schema migration: new columns, ALTER TABLE statements, and coordination with any system that reads the staging table. Querying a single record is trivial. Per-attribute routing is awkward because attribute-level state (confidence score, routing decision) would need parallel columns for every attribute.
- **Tall schema (one row per attribute).** Each row is `(record_id, attribute_id, raw_value, predicted_value, confidence, routing_status)`. Adding a new attribute is a data change (a new entry in the attribute reference table), not a schema change. Per-attribute routing is direct: routing status is a column on the row.

## Decision

The canonical staging schema is attribute-row: each row represents one attribute of one record. The columns include `submission_id`, `record_id`, `attribute_id`, `supplier_raw_value`, `predicted_value`, `confidence_score`, `routing_status`, and audit metadata. Attribute definitions (name, type, allowed values, category) live in a separate reference table joined as needed. New product categories are added by inserting attribute definitions into the reference table, not by altering the staging schema.

## Consequences

- Adding a new product category does not require a schema migration against the staging tables. The Normalization stage gains new mapping entries; the Prediction Service is retrained on the expanded label set; nothing in the Routing Engine, Review Queue, or Writeback Service changes structurally.
- Per-attribute routing (ADR-004) becomes natural. Each row carries its own routing state, so the Routing Engine reads and updates one row at a time without joining against a wide record schema.
- Per-attribute audit is also natural. The audit trail can reference a single attribute row by its primary key.
- Querying a complete record requires a join or aggregation across multiple rows. This is a small loss in query convenience and is acceptable because the platform's hot-path queries are per-attribute (routing, scoring, review), not per-record.
- The staging tables grow faster than they would under a wide schema (one row per attribute rather than one row per record). For valves and actuators with roughly a dozen attributes, this is a 12× row-count multiplier. Azure SQL Database is sized to handle this comfortably at expected ingestion volumes.
- This schema decision is independent of the PIMS staging schema. ADR-006 covers the writeback contract with PIMS, which may use either a wide or tall structure. If PIMS is wide, the Writeback Service performs an aggregation transform from the platform's tall canonical schema into the wide PIMS schema; this is documented as an open dependency on Refinement 4.
- If Refinement 4 reveals that PIMS staging is rigidly wide and the team-owned mapping is too costly to maintain, the platform may keep its internal canonical schema tall while presenting a wide interface to PIMS through the Publish/Sync Job. The architecture supports this.

## Requirements Traceability

- **HLRs:** HLR-2 (normalize to standardized structure)
- **FRs:** FR-2 (canonical schema before prediction); FR-11 (attribute-level natural key requires attribute-row schema)
- **QASs:** QAS-3 (new category as data change, not schema migration)
- **Constraints:** C-4 (phase scope expansion); C-6 (pricing excluded from canonical schema)
- **Scenarios:** SCEN-1 (Step 3 — canonical normalization)
