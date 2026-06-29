# ADR-015: Target PostgreSQL Now; Defer the Azure SQL Conversion

## Status

Accepted

## Context

The ETIM implementation brief specifies its schemas in **SQL Server / Azure SQL dialect** (`DATETIME2`, `NVARCHAR(MAX)`, `BIT`), consistent with the original platform design (ADR-008), which placed all internal pipeline state in **Azure SQL Database** and deployed the platform as a single Azure App Service. Several earlier ADRs assume this Azure SQL substrate (ADR-006 PIMS writeback, ADR-007 staging, ADR-008 deployment, ADR-009 review queue, ADR-010 audit trail).

The ingestion service as actually built does not run on Azure SQL. It runs on **PostgreSQL** with SQLAlchemy 2.x + Alembic migrations, uses **JSONB** for semi-structured fields, archives raw bytes to **S3/MinIO**, and is packaged with Docker/`docker-compose` (Postgres + MinIO) rather than App Service. The existing migrations (`0001`–`0005`, including the ETIM reference tables) are all Postgres.

The ETIM schema tickets (reference tables, staging split) were therefore blocked on a datastore question (ING-E0): author the new ETIM and staging tables for Azure SQL to match the brief, or for Postgres to match the running service? Authoring for Azure SQL now would mean building against a database the platform does not yet use, maintaining a dialect the rest of the codebase does not use, and carrying that divergence indefinitely. Authoring for Postgres now keeps the entire ingestion service on one coherent stack and translates the brief's SQL Server DDL to Postgres equivalents.

A migration to Azure SQL is a real future possibility — it is the original target and ties to the broader platform-on-Azure direction (EPARTS-64) — but it is a separate, platform-level effort that is not in flight today.

## Decision

All new ETIM reference tables and staging tables target **PostgreSQL (the current stack) for now**, using Alembic migrations and JSONB where useful, matching the existing ingestion service. The brief's SQL Server DDL is translated to Postgres equivalents: `DATETIME2 → timestamptz`, `NVARCHAR(MAX) → text`, `BIT → boolean`, with JSONB used where a flexible column is warranted.

A later conversion to **Azure SQL is explicitly deferred** to the future move of the wider platform onto Azure, and is treated as a separate effort rather than a constraint on current ETIM work. This decision **unblocks the ETIM schema tickets** (ING-E0 is resolved). It does not retract ADR-008's eventual Azure direction; it records that the *current* substrate is Postgres and that ETIM work builds on Postgres rather than waiting for, or pre-building against, Azure SQL.

## Consequences

- The ingestion service stays on a single coherent persistence stack (Postgres + Alembic + JSONB + S3). New ETIM and staging migrations sit in the same migration chain as everything else, with one dialect to test and operate.
- The ETIM schema and staging tickets are unblocked and can proceed immediately, which is the critical path for the rest of the ETIM matching work.
- A divergence is now on record between several existing ADRs (which name Azure SQL / SQL Server) and the running system (Postgres). ADR-008 in particular is now partially stale on the datastore and deployment topology; this is captured in the ADR assessment for whole-platform follow-up rather than silently ignored.
- A future Azure SQL port is a known, bounded piece of work. It would touch: column-type translation back to the SQL Server dialect, JSONB usage (which has no exact Azure SQL analogue and would need `nvarchar(max)`/JSON functions), Postgres-specific features in use (advisory locks for run-level exclusivity, `ON CONFLICT` upserts), and the migration tooling. Keeping Postgres-specific features behind the storage layer limits the blast radius of that future port.
- Because the decision is "now vs later" rather than "never," teams should avoid leaning on Postgres-only behavior in business logic above the storage layer, so the deferred port stays a storage-layer concern.
- PIMS itself remains external and may stay on SQL Server regardless; this ADR governs the platform's *own* internal stores, not the PIMS target (see ADR-006).

## Requirements Traceability

- **Source:** `INGESTION_ETIM_TICKET_MAP.md` (ING-E0 — RESOLVED: "PostgreSQL now; Azure SQL conversion deferred"); `ETIM_IMPLEMENTATION_BRIEF.md` (Data Model — SQL Server DDL, here translated)
- **Tickets:** EPARTS-285 (built on Postgres migration 0005); EPARTS-298 (staging schema, Postgres); EPARTS-64 (future platform-on-Azure)
- **Constraints:** C-1 (Azure managed services — eventual direction, deferred); C-7 (capstone operational simplicity — one stack)
- **Related ADRs:** ADR-008 (revisits its Azure App Service + Azure SQL topology — now partially superseded on substrate); ADR-013 and ADR-014 (the reference and staging tables this decision places on Postgres); ADR-006 (PIMS target datastore, separate)
