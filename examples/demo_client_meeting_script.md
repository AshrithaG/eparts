# Synthetic client meeting — demo script (paired with SES sample transcript)

Use this alongside `examples/demo_client_review.transcript.vtt` when you rehearse or present live. Dialogue is abbreviated in the transcript file; extend with your own names if recording a fresh Zoom.

---

## Logistics

| | |
|--|--|
| **Duration target** | 12–13 minutes (recording) / read transcript as-is for pipeline demo |
| **Cast** | PM (`JaiVardhan`), catalog ops (`Dave`), PIMS backend (`Laura`, `Jake`), ML/data (`Harsh`, `Sophie`), DevOps (`Raj`), stakeholder PM (`Chris`) |

---

## Beats (what “good content” demonstrates)

1. **Context** — Ingestion for valves/actuators slice; sponsor governance on scope creep.  
2. **Non-functional anchors** — PIMS correctness over completeness; SLA on E2E latency and reviewer throughput.  
3. **Explicit decisions** — Per-attribute thresholds, diff-based review UI, single App Service sandbox.  
4. **Architecture alignment** — Staging DDL + canonical mapping; hybrid ML + rules; Datadog telemetry.  
5. **Traceability language** — HLR / FR / DR / QA scenario phrasing auditors expect.  
6. **Risk & escalation** — Staging delays, labelled data volume, backlog if queue spikes.  
7. **Action items with owners/dates** — Jake Thursday DDL, Sophie Friday metrics, Raj Wednesday dashboards.

---

## Read-through lines (speaker script)

Deliver naturally; numbering matches transcript cues.

### Opening — JaiVardhan
> Good morning everyone. Goal for this sixty-minute architectural review block is alignment on ingestion scope for Spring, confirm our confidence thresholds, and capture action items before we freeze ADR drafts for Critique Demo.

### Dave — business priority  
> Wrong data in PIMS is worse than missing data. Keep auto-accept at high confidence only. Valves/actuators scope first — reviewer throughput around ten reviewed items per minute still stands.

### Laura — blocker / ask  
> We need definitive staging-column mapping before idempotent upsert validation — Jake can we get DDL handshake end of sprint?

### Jake — commitment  
> Deliverable is mapping spreadsheet staging → canonical SKU key + attribute hash; DDL diff by Thursday; escalate leadership if slips.

### Harsh — ML rationale  
> all-MiniLM beats DistilBERT for short fields — propose ~90% auto-accept on brand/name, ~75% routing on technical specs; per-attribute thresholds in ADRs.

### Sophie — QA / measurement  
> Per-attribute thresholds protect precision/recall — regression harness tracks uplift weekly.

### Raj — infra  
> Sandbox stays single Azure App Service; Datadog for ingestion rate and E2E latency under SLA.

### Chris — stakeholder  
> Escalate scope beyond valves before allocating more SKUs — backlog scrub first.

### JaiVardhan — decision summary  
> Decision 1 — per-attribute thresholds before pilot. Decision 2 — diff-based reviewer UI. Decision 3 — single sandbox App Service until summer hardening.

*(Continue through action items and closing as in transcript.)*

---

## Run SES on this transcript

Always use the `.transcript.vtt` file so `demo.py` picks it explicitly:

```bash
python3 demo.py examples/demo_client_review.transcript.vtt --auto
```

Or use `./scripts/show_ses_demo.sh` (prefers this file when present).

---

## Disclaimer

Synthetic scenario for education and SES demonstration only—not a record of any real sponsor conversation.
