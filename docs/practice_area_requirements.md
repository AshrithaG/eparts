# Practice Area: Requirements Engineering — End-to-End

> "For at least one Practice Area, there should be an end-to-end connection
> between the Activities in that area." — Presentation Rubric

This document shows the complete end-to-end flow for Requirements Engineering,
with each Activity documented per the meta-model: Artifacts, Processes, Resources, Measurements.

## Overview Flow

```
Meeting Recording (.vtt)
        │
        ▼
┌──────────────────────┐
│ A1: Transcript Parse  │  Resource: auton (agent) + assist (Claude optional)
│ ETVX: REQ-PARSE      │  Artifacts IN:  .vtt file
│                       │  Artifacts OUT: structured JSON (attendees, actions, decisions)
└──────────┬───────────┘
           │ parsed_minutes (data bridge)
           ▼
┌──────────────────────┐
│ A2: Priority Classify │  Resource: auton (agent) + assist (Claude optional)
│ ETVX: REQ-CLASS       │  Artifacts IN:  parsed action items
│                       │  Artifacts OUT: classified items (P0/P1/P2)
└──────────┬───────────┘
           │ classified_items (data bridge)
           ▼
┌──────────────────────┐
│ A3: Requirement       │  Resource: auton (agent)
│     Extraction        │  Artifacts IN:  classified P0/P1 items
│ ETVX: REQ-EXTRACT     │  Artifacts OUT: REQ-XXX.md files committed to repo
└──────────┬───────────┘
           │ new_requirements (data bridge)
           ▼
┌──────────────────────┐
│ A4: Ticket Creation   │  Resource: auton (agent) → Jira MCP
│ ETVX: PM-TICKET       │  Artifacts IN:  classified items + requirements
│                       │  Artifacts OUT: Jira tickets with labels
└──────────┬───────────┘
           │ action_items_extracted (event)
           ▼
┌──────────────────────┐
│ A5: Minutes Publish   │  Resource: auton (agent) → Confluence MCP
│ ETVX: KN-PUBLISH      │  Artifacts IN:  parsed minutes + classified items
│                       │  Artifacts OUT: Confluence page
└──────────┬───────────┘
           │ decision_logged (event)
           ▼
┌──────────────────────┐
│ A6: Decision Log      │  Resource: auton (agent)
│ ETVX: KN-DECISION     │  Artifacts IN:  decisions from parsed minutes
│                       │  Artifacts OUT: decision register entry
└──────────┬───────────┘
           │ wiki deposit → SharedMemory
           ▼
┌──────────────────────┐
│ A7: Architecture      │  Resource: auton (agent) + assist (Claude optional)
│     Drift Detection   │  Artifacts IN:  meeting content + canonical architecture
│ ETVX: ARCH-DRIFT      │  Artifacts OUT: drift report, drift_detected event
└──────────────────────┘
           │
           ▼ drift_detected event → Architecture Pipeline (cross-pipeline trigger)
```

## Activity Details (Meta-Model Format)

### A1: Transcript Parsing

| Element        | Detail                                                    |
|----------------|-----------------------------------------------------------|
| **Process**    | Parse raw .vtt transcript into structured JSON            |
| **Entry**      | .vtt file exists, meeting type known                      |
| **Task**       | Clean VTT formatting, extract speaker turns, identify action items/decisions/attendees |
| **Verification**| Output has attendees, action items, decisions fields      |
| **Exit**       | Structured JSON with parsed_minutes available for next step |
| **Resource**   | `auton` (agent: `transcript_parser`) — offline structural extraction via regex; `assist` (Claude) for deeper extraction when API key available |
| **Artifacts IN** | `.vtt` transcript file                                  |
| **Artifacts OUT**| Structured JSON: `{attendees, action_items, decisions, new_requirements}` |
| **Measurements**| Tokens used (if Claude), action items extracted count, decisions extracted count, duration_ms |
| **Wiki Deposit**| `meetings/{date}-{type}` — meeting summary with counts   |
| **Events Emitted**| `action_items_extracted`, `decision_logged`             |

### A2: Priority Classification

| Element        | Detail                                                    |
|----------------|-----------------------------------------------------------|
| **Process**    | Classify extracted items as P0 (critical), P1 (important), P2 (nice-to-have) |
| **Entry**      | `parsed_minutes` available from A1                        |
| **Task**       | Apply priority heuristics (keyword-based offline, or Claude-powered) |
| **Verification**| Every item has a priority label; P0 items flagged for human review |
| **Exit**       | `classified_items` with `p0_items`, `p1_items`, `p2_items` |
| **Resource**   | `auton` (agent: `priority_classifier`) — offline heuristic; `assist` (Claude) for nuanced classification |
| **Artifacts IN** | Action items from A1                                    |
| **Artifacts OUT**| Classified item list with P0/P1/P2 labels               |
| **Measurements**| Distribution of P0/P1/P2, human review rate for P0, reclassification rate |

### A3: Requirement Extraction

| Element        | Detail                                                    |
|----------------|-----------------------------------------------------------|
| **Process**    | Generate formal REQ-XXX.md requirement documents from classified items |
| **Entry**      | `classified_items` available, at least one P0 or P1 item  |
| **Task**       | Template-fill requirement document with rationale, acceptance criteria, traceability |
| **Verification**| Each REQ has title, rationale, acceptance criteria, priority |
| **Exit**       | REQ-XXX.md files committed to repo                        |
| **Resource**   | `auton` (agent: `req_extractor`) → Bitbucket MCP for commit |
| **Artifacts IN** | P0/P1 classified items                                  |
| **Artifacts OUT**| `requirements/REQ-XXX.md` files in repository            |
| **Measurements**| Requirements generated count, commit success rate         |

### A4: Ticket Creation

| Element        | Detail                                                    |
|----------------|-----------------------------------------------------------|
| **Process**    | Create Jira tickets from extracted action items            |
| **Entry**      | `classified_items` available                               |
| **Task**       | Map action items to Jira tickets with priority, labels, assignee |
| **Verification**| Ticket created in correct project with `ai-generated` label |
| **Exit**       | Jira tickets created, task IDs recorded                    |
| **Resource**   | `auton` (agent: `ticket_creator`) → Jira MCP              |
| **Artifacts IN** | Classified action items                                  |
| **Artifacts OUT**| Jira tickets                                              |
| **Measurements**| Tickets created count, ticket accuracy (human review rate) |

### A5: Minutes Publication

| Element        | Detail                                                    |
|----------------|-----------------------------------------------------------|
| **Process**    | Publish formatted meeting minutes to Confluence            |
| **Entry**      | `parsed_minutes` and `classified_items` available          |
| **Task**       | Format markdown minutes with action items, decisions, attendees |
| **Verification**| Published page has all sections populated                  |
| **Exit**       | Confluence page published and linked                       |
| **Resource**   | `auton` (agent: `minutes_publisher`) → Confluence MCP      |
| **Artifacts IN** | Parsed minutes + classified items                        |
| **Artifacts OUT**| Confluence page                                           |
| **Measurements**| Publication success rate, page completeness                |

### A6: Decision Logging

| Element        | Detail                                                    |
|----------------|-----------------------------------------------------------|
| **Process**    | Extract and log decisions from meeting to persistent register |
| **Entry**      | `decisions` available from A1                              |
| **Task**       | Record each decision with context, rationale, participants  |
| **Verification**| Decision has context, at least one participant              |
| **Exit**       | Decision register updated in wiki                          |
| **Resource**   | `auton` (agent: `decision_logger`)                         |
| **Artifacts IN** | Decisions from parsed minutes                            |
| **Artifacts OUT**| Wiki entry in `decisions/` namespace                      |
| **Measurements**| Decisions logged count, decisions with full context rate    |
| **Events Emitted**| `decision_logged` → Knowledge pipeline                   |

### A7: Architecture Drift Detection

| Element        | Detail                                                    |
|----------------|-----------------------------------------------------------|
| **Process**    | Compare meeting discussion against canonical architecture for contradictions |
| **Entry**      | Meeting content available AND architecture doc in ChromaDB  |
| **Task**       | Semantic search for architecture-related discussion; compare against ADRs and constraints |
| **Verification**| Drift items have specific reference to contradicted architecture element |
| **Exit**       | Drift report generated; `drift_detected` event emitted if found |
| **Resource**   | `auton` (agent: `drift_detector`) + ChromaDB (architecture collection) |
| **Artifacts IN** | Meeting content + canonical architecture (31 chunks in ChromaDB) |
| **Artifacts OUT**| Drift report; triggers Architecture pipeline if drift found |
| **Measurements**| Drift items detected, false positive rate (human verified)  |
| **Events Emitted**| `drift_detected` → Architecture pipeline (cross-pipeline) |

## End-to-End Connection

The seven activities form a complete pipeline:
1. **Input**: Raw `.vtt` recording from a client meeting
2. **Processing**: Each activity consumes the previous activity's output via the `PipelineContext` data bridge
3. **Output**: Requirements docs, Jira tickets, Confluence pages, decision register, drift reports
4. **Cross-Pipeline**: Events emitted (`action_items_extracted`, `decision_logged`, `drift_detected`) trigger other practice areas
5. **Persistent Knowledge**: Every activity deposits structured data into SharedMemory wiki
6. **Measurement**: Every step is metered (tokens, duration, success rate) via MetricsCollector

This is the "end-to-end connection between Activities" the rubric requires:
a single meeting recording flows through all seven activities, producing
artifacts at each step, with data bridging between steps, events triggering
other pipelines, and measurements captured throughout.
