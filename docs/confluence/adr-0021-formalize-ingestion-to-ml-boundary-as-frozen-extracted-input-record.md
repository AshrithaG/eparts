# ADR-021: Formalize the Ingestion → ML Boundary as a Frozen `ExtractedInput` Record

> Source of truth: [`0021-formalize-ingestion-to-ml-boundary-as-frozen-extracted-input-record.md`](https://github.com/AshrithaG/eparts/blob/main/docs/0021-formalize-ingestion-to-ml-boundary-as-frozen-extracted-input-record.md) in the eparts repo. This page is a copy for reading; edit the repo, not this page.

## Status

Accepted

## Context

ADR-001 established pipe-and-filter as the platform's style, with filters communicating through typed data channels. In practice the ingestion→matching channel was the weakest of them: ingestion parsed a supplier file into a `RawRecord` and the matching stream read whatever fields happened to be there. Adequate while both sides were one team and one process; untenable now.

Three pressures forced the boundary to become explicit.

**It is a cross-team contract.** Ingestion (EPARTS-154) and ML matching (EPARTS-156) are separate streams with separate backlogs. The ETIM requirements-change record names this contract as one of two places where our traceability deliberately stops — we own the requirement, another stream owns the implementation. A trace boundary that is not a schema boundary is not a boundary at all.

**Ingestion must not leak interpretation.** ADR-014 established the principle that supplier data is *evidence* and ETIM is a *standardized interpretation* over it. If ingestion hands the matcher a confidence score or a ranked list of candidate attribute names, it has already begun interpreting, and the evidence/interpretation split becomes a convention rather than a property of the system. The temptation is real: the OCR path (Azure Document Intelligence plus an LLM extraction) *has* per-field confidences available, and passing them along would be a one-line change.

**Source provenance differs by channel and matters downstream.** A value read from a CSV cell, a value read from a text-native PDF, and a value read from OCR over a scanned page carry different reliability, and the matcher and the reviewer both need to know which they are looking at. A generic dictionary of fields loses that.

Alternatives considered:

- **Keep passing `RawRecord`.** Zero work, and it makes every ingestion-side refactor a potential silent break for the ML stream, because nothing declares what the ML stream is entitled to rely on.
- **Put the boundary behind an HTTP service now.** Genuinely the right long-term shape, and premature: it adds deployment, retry and tracing surface for a boundary that currently runs in one process. ADR-008's single-deployable-unit decision still holds; what this ADR fixes is the *contract*, not the *topology*.
- **Document the contract in prose only.** The 460-line handoff specification already exists. Documentation that is not enforced drifts, and this contract's whole value is that it cannot drift.

## Decision

The ingestion→ML boundary is a **single, versioned, schema-frozen record type**, `ExtractedInput`, specified in `docs/extraction_handoff_spec.md` and enforced in code:

| Field | Meaning |
|---|---|
| `source_type` | one of `csv`, `email`, `pdf_text`, `pdf_ocr`, `image` — the channel, so the consumer knows what kind of evidence this is |
| `text` | the extracted text; required, and an empty string is valid |
| `structured_fields` | the parsed field/value pairs as the supplier wrote them |
| `normalized_units` | mechanical unit normalization only, as `(value, unit)` pairs |
| `source_ref` | pointer back to the archived raw artefact |

Two properties do the real work.

**The schema forbids interpretation by construction.** The Pydantic model is declared `extra="forbid"` and `frozen=True`. Confidence scores, ranked alternates, predicted ETIM classes — anything that constitutes an interpretation — *cannot be represented*, so they cannot cross the boundary by accident. The evidence/interpretation split of ADR-014 is enforced by the type system rather than by reviewer vigilance.

**The record is persisted, not just passed.** `extracted_inputs` (Alembic `0007`) stores each handoff record, which turns the boundary into a durable checkpoint: the matching stream can be down, restarted, or re-run against the same inputs without re-doing OCR, and a matching bug can be diagnosed against exactly the input that produced it.

Cleaning (spec §3) and unit normalization (spec §4) are injectable seams on the ingestion side of the boundary. This keeps mechanical tidying — whitespace, encoding, unit spelling — with the party that knows the source format, while leaving anything requiring domain judgement to the matcher.

**Implementation status: built and merged.** `handoff/spec_model.py`, `handoff/builder.py`, `models/extracted_input.py` and migration `0007` are on the main line (EPARTS-357, EPARTS-358). The cleaning and unit implementations (EPARTS-359, EPARTS-362) and the provenance split between `pdf_text` and `pdf_ocr` (EPARTS-361) are on open branches; on the main line those seams are pass-throughs. Wiring the builder into the orchestrator is EPARTS-363 and is not yet done, so the record type exists and is validated but is not yet produced on every run.

## Consequences

- The two streams can move independently. Ingestion can change parsers, add a channel, or swap the OCR engine without coordinating, so long as the record still validates. The ML stream has a written, enforced statement of what it may rely on.
- **`extra="forbid"` will reject rather than ignore** an ingestion-side addition. That is the intended behaviour — it makes contract changes loud — but it means adding a field is a deliberate, two-team, spec-versioning act, not a convenience. Expect this to feel obstructive at least once; that is the cost being paid on purpose.
- Persisting the record makes matching **replayable**. Re-running the matcher over stored `extracted_inputs` costs nothing in Azure Document Intelligence or LLM calls, which materially changes the economics of iterating on the matching stages of ADR-016.
- This turns ADR-001's in-process function call into an explicit asynchronous seam, and it is consequently **the leading candidate for extraction into a service** if the deployment topology of ADR-008 is ever revisited. Nothing about the contract assumes co-location.
- The boundary is a queue-shaped thing without a queue. Delivery today is a table plus a poll; the transactional outbox and circuit breaker planned under EPARTS-301 are not built. Until they are, there is no delivery guarantee beyond "the row is committed" — adequate, because the row *is* the durable state, but not the same as at-least-once delivery to a live consumer.
- The record carries no confidence, which means the matcher cannot preferentially trust a high-confidence OCR field over a low-confidence one. This is a deliberate loss of information: OCR confidence measures character recognition, not semantic correctness, and treating it as the latter is the mistake the split exists to prevent. If the matcher later needs a reliability signal, it should come from `source_type` and from measured per-channel accuracy, not from the OCR engine's self-report.
- Because the builder is not yet wired into the orchestrator, the contract is currently **enforced but unexercised in production flow**. The unit tests validate the shape; no end-to-end run has yet produced a record. This should not be described as a working boundary until EPARTS-363 lands.

## Requirements Traceability

- **Spec:** Product Specification v1.4 (29 July 2026)
- **HLRs:** HLR-2 (normalize into a standardized intermediate structure preserving original supplier values as evidence); HLR-1 (ingest from diverse supplier sources — `source_type` enumerates the channels); HLR-3 (the ML service that consumes this record)
- **FRs:** FR-1 (ingestion record with supplier, timestamp, source channel); FR-2 (validation before processing — an invalid handoff record is a validation failure, not a silent pass); FR-9 (matching consumes this record)
- **DRs:** DR-1 (raw file archived as evidence — `source_ref` is the pointer to it)
- **QASs:** QAS-1 Modifiability — a new supplier format is a new `source_type` and a new parser; the boundary and everything downstream of it are unchanged
- **Constraints:** DC-1 (Python backend); DC-3 (raw files preserved for re-processing and traceability — replayability depends on this)
- **Scenarios:** SCEN-1 step 3 and SCEN-2 step 1 (both scenarios cross this boundary; SCEN-2's OCR path is `pdf_ocr`)
- **Source:** `docs/extraction_handoff_spec.md` (§1 channels, §2 record shape, §3 cleaning, §4 unit normalization, §5 structured fields, §6 per-channel examples)
- **Tickets:** EPARTS-357 (schema + migration `0007` — Done), EPARTS-358 (builder + spec model — Done), EPARTS-359 (units), EPARTS-361 (pdf_text/pdf_ocr provenance), EPARTS-362 (text cleaning), EPARTS-363 (orchestrator wiring — **not done**), EPARTS-301 (transactional outbox — not built); contract boundary between EPARTS-154 (Ingestion) and EPARTS-156 (ML)
- **Related ADRs:** makes explicit the filter boundary of ADR-001; enforces the evidence/interpretation split of ADR-014; feeds the matching stages of ADR-016; does not alter the single-deployable-unit topology of ADR-008, but is the natural extraction point if that is revisited
