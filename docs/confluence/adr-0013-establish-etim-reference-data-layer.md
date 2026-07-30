# ADR-013: Establish a Release-Versioned ETIM Reference Data Layer Owned by Ingestion

> Source of truth: [`0013-establish-etim-reference-data-layer.md`](https://github.com/AshrithaG/eparts/blob/main/docs/0013-establish-etim-reference-data-layer.md) in the eparts repo. This page is a copy for reading; edit the repo, not this page.

## Status

Accepted

## Context

The platform is adopting ETIM as the classification standard for catalog standardization (valves and actuators in phase one). ETIM is a controlled technical dictionary: product groups (EG), product classes (EC), features (EF), feature groups (EFG), units (EU), and controlled values (EV), plus the mappings that say which features belong to a class and which values are allowed for a class-feature. ETIM is not supplier data — it provides no SKUs, prices, or product documents. Before the platform can match any supplier product to ETIM (class matching, feature matching, value matching, validation), it needs the ETIM dictionary loaded, queryable, and under version control.

The supplied ETIM data has awkward physical characteristics that make it a poor fit for ad-hoc loading: the production archive is a set of CSV files encoded **UTF-16 little-endian, semicolon-delimited**, for a specific release (10.0) and language (EI, English International). ETIM publishes new releases over time, and class/feature/value definitions change between releases, so a single un-versioned copy would silently conflate releases and make historical mappings unauditable.

A key question was **ownership**: the reference loader could sit in the ML/matching component (the primary consumer) or in ingestion (which already owns file parsing, encoding handling, idempotent batch loads, and Alembic migrations). Two further options for storage shape were considered:

- **Denormalized blob / JSON document per class.** Fast to load and to read a whole class, but cannot enforce referential integrity, makes cross-class queries (e.g. "all classes using feature EF000513") expensive, and couples readers to a single release's shape.
- **Normalized relational tables mirroring the ETIM model**, scoped by release ID. Enforces FKs and composite keys, supports multi-release coexistence, and lets the matcher query class→feature→value relationships directly.

## Decision

We will model ETIM as a **normalized relational reference layer of ten tables**, every row scoped by a release identifier, and we will make the **ingestion team the owner** of both the schema and the import job.

The tables are `etim_release`, `etim_group`, `etim_class`, `etim_class_synonym`, `etim_feature_group`, `etim_feature`, `etim_unit`, `etim_value`, `etim_class_feature`, and `etim_class_feature_value`, with composite primary keys on `(etim_release_id, …)` so that multiple ETIM releases can coexist without collision. The release identifier is a stable, human-readable string of the form `ETIM-{version}-{language}` (e.g. `ETIM-10.0-EI`).

A dedicated **ETIM Reference Loader** import job reads the UTF-16 LE, semicolon-delimited CSV archive, validates that the expected columns are present per file, rejects incomplete or release-mismatched archives, and loads the rows into the reference tables. It records the release version, language, source name, an import timestamp, and a **SHA-256 checksum over the archive**. Re-importing the same release is **idempotent** (no-op when the checksum matches; controlled replace only with an explicit `--force`). The job is exposed as a CLI entry point (`eparts etim import …`) mirroring the existing Typer CLI, and is delivered as Alembic migration `0005_create_etim_reference` plus `etim/loader.py`, `models/etim.py`, and `cli/etim.py`.

This decision is implemented and verified against the real ETIM 10.0 EI archive (EPARTS-285).

## Consequences

- The matcher (ETIM class/feature/value matching) can treat ETIM as a stable, queryable dependency. Loading the dictionary is no longer entangled with matching logic, so the two can evolve independently.
- Release versioning is first-class. Because every row is keyed by `etim_release_id`, a future ETIM 11.0 can be loaded alongside 10.0, and any product's mapping can name the exact release it was matched against. This is a prerequisite for governed ETIM upgrades (an open client decision in the brief).
- Idempotent, checksummed import makes the load safe to re-run in CI and across environments without producing duplicates or partial state. A mismatched or truncated archive is rejected with a clear error rather than loaded silently.
- Placing ownership in ingestion reuses existing strengths (encoding handling, batch idempotency, Alembic, the Typer CLI) and keeps the file-handling concerns in the team that already does file handling. The cost is a coordination point: the matching team consumes a schema that ingestion owns, so reference-table changes require a published contract.
- The reference layer is read-mostly and modest in size (~160 groups, ~5,600 classes, ~17,000 features, ~16,000 values, ~200,000 class-feature-value links for 10.0 EI). Normalized storage on the current Postgres stack handles this comfortably.
- ETIM does not supply a client-ready "required field" flag. The reference layer deliberately stores ETIM as published and leaves required/recommended/optional policy to a separate client policy overlay (`catalog_feature_policy`, owned downstream). This ADR does not cover that overlay.
- The loader currently targets the CSV archive only. The Excel workbook (useful for analyst review and metric/imperial crosswalks) is intentionally out of scope for production import.

## Requirements Traceability

- **Source:** `ETIM_IMPLEMENTATION_BRIEF.md` (ETIM Reference Loader, ETIM Reference Tables, Acceptance Criteria 1)
- **Tickets:** EPARTS-285 (Create ETIM reference schema and import job — Done); EPARTS-275 (ETIM research); parent EPARTS-154 (Ingestion)
- **Implements:** ETIM reference schema, release tracking, idempotent import, golden row-count validation
- **Related ADRs:** ADR-014 (staging split consumes the reference layer for matching); ADR-015 (Postgres-now datastore the tables are built on); ADR-007 (the prior canonical-schema decision this complements)
