#!/usr/bin/env python3
"""Regenerate requirements/parsed/REQ-*.md from dashboard/traceability_data.json + local elaboration text."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "dashboard" / "traceability_data.json"
OUT_DIR = ROOT / "requirements" / "parsed"

# Priority carried forward from prior human edit (classifier output)
PRIORITY = {
    "REQ-001": "P0",
    "REQ-002": "P1",
    "REQ-003": "P2",
    "REQ-004": "P1",
    "REQ-005": "P0",
    "REQ-006": "P0",
    "REQ-007": "P0",
    "REQ-008": "P0",
    "REQ-009": "P1",
    "REQ-010": "P1",
    "REQ-011": "P0",
    "REQ-012": "P0",
}

CATEGORIES = {
    "REQ-001": "Functional Requirement",
    "REQ-002": "Functional Requirement",
    "REQ-003": "Quality Attribute Requirement",
    "REQ-004": "User Goal",
    "REQ-005": "Functional Requirement",
    "REQ-006": "Constraint",
    "REQ-007": "Constraint",
    "REQ-008": "Functional Requirement",
    "REQ-009": "Milestone",
    "REQ-010": "Constraint",
    "REQ-011": "Process Requirement",
    "REQ-012": "Process Requirement",
}

ELABORATION: dict[str, dict[str, str]] = {}
# keyed sections: detailed_behavior, nf, concerns_text, deps

ELABORATION["REQ-001"] = {
    "detailed_behavior": """- Ingest CSV, `.xlsx`, and text-extractable PDF vendor sheets supplied by distributors.
- Parse tabular layouts with schema hints (headers, SKU column, specification blocks).
- Persist extracted attribute candidates with machine confidence and source document span references.
- Expose deterministic JSON contract for downstream mapping and review agents.""",
    "nf": """- **Throughput:** scalable batch pipeline (not synchronous chat per row at scale).
- **Audit:** every prediction ties back to ingestion record + model version.""",
    "concerns_text": "- Vendor variability in column naming expects canonical mapping (see REQ-002).\n- Legal sensitivity requires redaction rules for certain PDF regions (process, not this REQ).",
    "deps": "- REQ-002 (taxonomy mapping)\n- REQ-008 (multi-format coverage)\n- REQ-009 (POC scope)",
}
ELABORATION["REQ-002"] = {
    "detailed_behavior": """- Maintain canonical attribute dictionary for industrial SKUs (valves, actuators first category).
- Map vendor-local labels to industry vocabulary with confidence.
- Support multi-language labels where present in source sheets.""",
    "nf": """- **Versioning:** taxonomy versions must be bumpable without invalidating historical trace rows.""",
    "concerns_text": "- Mis-mapping propagates to catalog—requires human review below confidence (REQ-004).",
    "deps": "- REQ-001 (extraction)\n- REQ-003 (confidence scoring)",
}
ELABORATION["REQ-003"] = {
    "detailed_behavior": """- Emit per-attribute scalar or vector confidence after model forward pass.
- Feed scores into routing policy: auto-accept band, review band, reject band (thresholds ADR-governed).
- Log score distributions for calibration regression tests.""",
    "nf": """- **Observability:** aggregate calibration metrics exportable to monitoring (REQ-007).""",
    "concerns_text": "- Threshold mistakes are top risk class; mitigated by explicit risk records + ADR-001.",
    "deps": "- REQ-001 / REQ-002 upstream features\n- REQ-004 (review queue)\n- ADR-001 (threshold calibration)",
}
ELABORATION["REQ-004"] = {
    "detailed_behavior": """- Web queue lists pending predictions with source doc diff and model explanation snippet.
- Actions: accept, edit value, reject with mandatory reason codes.
- Accepted edits enqueue training-feedback dataset builder (phase 2—not blocking MVP read path).""",
    "nf": """- Target reviewer productivity ≥10 reviewed lines/min sustained (per product goals).""",
    "concerns_text": "- Human bottlenecks if routing too conservative (see risk register linkage).",
    "deps": "- REQ-003 (scores)\n- REQ-005 (staging diff UX alignment)",
}
ELABORATION["REQ-005"] = {
    "detailed_behavior": """- Persist proposed catalog rows into staging relation mirroring prod shape.
- Generate row-level Git-style diffs vs prior approved snapshot per SKU.
- Support batch approve / batch rollback.""",
    "nf": "",
    "concerns_text": "- Schema churn from PIMS must be isolated—see ARCH-level mitigations.",
    "deps": "- REQ-004 (review UX)\n- Azure data plane (REQ-006/007)",
}
ELABORATION["REQ-006"] = {
    "detailed_behavior": """- Provision application, data, secrets, CI slots via checked-in IaC definitions.
- Enforce repeatable environment promotion paths (sandbox → staging → prod).""",
    "nf": "**Compliance:** infra changes reviewable via PR with policy-as-code scanners enabled.",
    "concerns_text": "",
    "deps": "- REQ-007 (telemetry plane)\n- Bicep module library from architecture slice",
}
ELABORATION["REQ-007"] = {
    "detailed_behavior": """- Structured logs shipped to centralized sink with correlation identifiers per ingestion job.
- Dashboards track latency, OCR failures, routing counts, reviewer throughput.""",
    "nf": "",
    "concerns_text": "",
    "deps": "- REQ-006 (Azure tenancy)\n- OpenTelemetry exporters where applicable",
}
ELABORATION["REQ-008"] = {
    "detailed_behavior": """- Dispatcher selects parser module by MIME + content sniff (PDF text vs OCR path later).
- Reject malformed zips outright with actionable error payloads.""",
    "nf": "",
    "concerns_text": "",
    "deps": "- REQ-001 ingestion contract",
}
ELABORATION["REQ-009"] = {
    "detailed_behavior": """- Scripted golden-path demo ingest → predict → queue → staged publish within latency budget.
- Success criteria enumerated in Sprint review rubric—not production cutover.""",
    "nf": "",
    "concerns_text": "",
    "deps": "- REQ-001, REQ-002, REQ-003 core loop",
}
ELABORATION["REQ-010"] = {
    "detailed_behavior": """- Executable SoW milestones mapped to EPARTS backlog with explicit sign-off checkpoints.
- Document client feedback loop SLA for redlines.""",
    "nf": "",
    "concerns_text": "",
    "deps": "- PM artifacts + legal review checklist",
}
ELABORATION["REQ-011"] = {
    "detailed_behavior": """- Covers model usage tiers, forbidden data classes, escalation for suspected secrets in prompts.
- Must be adopted by Studio + client engineering touchpoints.""",
    "nf": "",
    "concerns_text": "",
    "deps": "- REQ-010 governance threads",
}
ELABORATION["REQ-012"] = {
    "detailed_behavior": """- Each materially significant architectural choice produces ADR Markdown with status, consequences, rollback.
- ADRs referenced from SES trace graph and PR templates.""",
    "nf": "",
    "concerns_text": "",
    "deps": "- Architecture pipeline + GitHub MCP\n- Companion docs under `docs/adr/` where overlapping",
}


def mtg_dates_from_id(mid: str) -> str | None:
    if not mid.startswith("MTG-"):
        return None
    m = re.match(r"^MTG-(\d{4})-(\d{2})-(\d{2})$", mid)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def load_bundle():
    raw = json.loads(DATA.read_text())
    nodes = {n["id"]: n for n in raw["nodes"]}
    edges = raw["edges"]
    return nodes, edges


def gather_links(rid: str, nodes: dict, edges: list) -> dict[str, object]:
    ins = defaultdict(list)
    outs = defaultdict(list)
    for e in edges:
        if e["target"] == rid:
            ins[e["type"]].append(e)
        if e["source"] == rid:
            outs[e["type"]].append(e)

    mtgs_o = sorted({e["target"] for e in outs.get("RAISED_IN", []) if e["target_type"] == "meeting"})
    arch_o = sorted({e["target"] for e in outs.get("DECIDED_BY", []) if e["target_type"] == "architecture"})
    risks_o = sorted({e["target"] for e in outs.get("MITIGATES", []) if e["target_type"] == "risk"})
    jira_i = sorted({e["source"] for e in ins.get("IMPLEMENTS", []) if e["source_type"] == "jira_ticket"})
    concerns_i = sorted({e["source"] for e in ins.get("BECAME", []) if e["source_type"] == "concern"})
    commits_i = sorted({e["source"] for e in ins.get("BECAME", []) if e["source_type"] == "commitment"})

    mtg_dates: list[str] = []
    display_mtgs: list[tuple[str, str, str]] = []

    def add_meeting(mid: str) -> None:
        d = nodes.get(mid, {}).get("meeting") or mtg_dates_from_id(mid)
        if not d:
            return
        mtg_dates.append(d)
        title = nodes.get(mid, {}).get("title") or mid
        display_mtgs.append((mid, d, title))

    for mid in mtgs_o:
        add_meeting(mid)

    # Architecture-derived meetings (e.g. REQ linked only via ARCH → RAISED_IN → meeting).
    for aid in arch_o:
        for e in edges:
            if e["source"] != aid:
                continue
            if e["type"] != "RAISED_IN" or e["target_type"] != "meeting":
                continue
            add_meeting(e["target"])

    by_mid = {mid: (mid, d, title) for mid, d, title in display_mtgs}
    display_mtgs = sorted(by_mid.values(), key=lambda x: x[1])
    earliest = min(mtg_dates) if mtg_dates else None

    # decisions via concerns
    decisions: list[tuple[str, str]] = []
    for cid in concerns_i:
        for e in edges:
            if e["source"] == cid and e["target_type"] == "decision" and e["type"] == "BECAME":
                did = e["target"]
                title = nodes.get(did, {}).get("title", "").strip()
                decisions.append((did, title[:120] + ("…" if len(title) > 120 else "")))

    decisions = sorted(set(decisions))

    return {
        "meetings": display_mtgs,
        "meeting_dates": mtg_dates,
        "date_identified": earliest,
        "architectures": arch_o,
        "risks": risks_o,
        "jira": jira_i,
        "concerns": concerns_i,
        "commitments": commits_i,
        "decisions": decisions,
        "concern_titles": [(c, nodes.get(c, {}).get("title", c)) for c in concerns_i],
        "risk_titles": [(r, nodes.get(r, {}).get("title", r)) for r in risks_o],
        "arch_titles": [(a, nodes.get(a, {}).get("title", a)) for a in arch_o],
    }


def fmt_list_md(label: str, rows: list[tuple[str, str]], maxn: int = 12) -> str:
    if not rows:
        return f"- _None in trace store for this slice._"
    lines = []
    for k, v in rows[:maxn]:
        if v and v != k:
            lines.append(f"- **`{k}`** — {v}")
        else:
            lines.append(f"- **`{k}`**")
    if len(rows) > maxn:
        lines.append(f"- _… {len(rows) - maxn} additional record(s) in trace export (`traceability_data.json`)._")
    return "\n".join(lines)


def fmt_meetings(rows: list[tuple[str, str, str]]) -> str:
    if not rows:
        return "- _No `RAISED_IN` meeting edge; see architecture-derived meetings if listed._"
    out = []
    for mid, d, title in rows:
        out.append(f"- **`{mid}`** ({d}) — _{title}_")
    return "\n".join(out)


def fmt_jira(ids: list[str]) -> str:
    if not ids:
        return "- _No `IMPLEMENTS` Jira rows ingested for this requirement._"
    return ", ".join(f"`{j}`" for j in ids)


def build_markdown(rid: str, title: str, nodes: dict, edges: list) -> str:
    el = ELABORATION.get(rid, {})
    g = gather_links(rid, nodes, edges)
    date = g["date_identified"] or "TBD"
    priority = PRIORITY[rid]
    category = CATEGORIES[rid]

    primary_mtg = g["meetings"][0] if g["meetings"] else None
    source_meeting = primary_mtg[0] if primary_mtg else "TBD"

    ac = {
        "REQ-001": "Given a labeled evaluation set drawn from supplier sheets covering ≥3 vendors, extractor F1-meets agreed threshold vs human labels.",
        "REQ-002": "Given heterogeneous vendor schemas, mapper assigns ≥target coverage of canonical attributes without manual remap per SKU.",
        "REQ-003": "Given batched SKU rows, every attribute prediction ships with numeric confidence usable by routing policy.",
        "REQ-004": "Given routed low-confidence SKU fields, reviewer can accept/modify/reject with audit trace and queue drains without silent loss.",
        "REQ-005": "Given sequential catalog revisions, diff engine surfaces row-level deltas with checksum-stable ordering.",
        "REQ-006": "Given infra PR, IaC yields reproducible sandbox deploy with secret separation and smoke tests wired in CI.",
        "REQ-007": "Given running services, ingestion + pipeline SLIs observable in shared dashboard within one hop from alert rule.",
        "REQ-008": "Given enumerated MIME envelopes, ingestion rejects unsupported classes with deterministic error envelopes.",
        "REQ-009": "Given scripted fixture corpus, POC path completes ingestion→prediction→staging handoff ≤ agreed wall-clock SLA.",
        "REQ-010": "Given legal template, executable SoW exists with annotated signatures milestones before April close-out window.",
        "REQ-011": "Given onboarding checklist, engineers acknowledge AI governance doc + violation reporting path quarterly.",
        "REQ-012": "Given ARCH decision events, numbered ADRs exist linked from SES trace graph.",
    }.get(rid, "Detailed acceptance scripted in QA matrix.")

    rationale = (
        "| REQ | Rationale (summary) |\n|-----|----------------------|\n"
        + f"| **{rid}** | Derived from SES ingest + stakeholder dialogue; prioritized **{priority}** for backlog ordering. |\n"
    )

    nf_block = "### Non-functional / ops\n" + (el["nf"] if el.get("nf") else "_None beyond global platform NFRs._")

    deps_block = "### Dependencies\n" + (el["deps"] if el.get("deps") else "_See trace graph for upstream artifacts._")

    md = f"""# {rid}: {title}

| Field | Value |
|-------|-------|
| **ID** | {rid} |
| **Category** | {category} |
| **Priority** | {priority} |
| **Date Identified** | **{date}** (from client meeting ingest / `SharedMemory`-aligned `RAISED_IN` edges; **not** file commit stamp) |
| **Source Meeting (primary)** | `{source_meeting}` |
| **Evidence** | `dashboard/traceability_data.json` |
| **Status** | draft |

## Requirement statement

**{title}** — binds engineering + ML teams to measurable delivery for the eParts catalog program.

## Expanded description

### Behavior

{el.get('detailed_behavior') or '(See requirement statement.)'}

### Context

{rationale.strip()}

{nf_block}

{deps_block}

## Acceptance criteria

1. **Traceability completeness:** Requirement row participates in SES graph with enumerated meetings, architectures, risks, tickets below.
2. **Delivery:** Implementation satisfies scripted acceptance `{ac}` scoped to POC unless noted otherwise.

## Open questions / concerns

{el.get('concerns_text') or '_None surfaced in ingest for this REQ._'}

## Traceability (populated from SES trace ingest)

_Link types follow SES naming (`RAISED_IN`, `BECAME`, `DECIDED_BY`, `MITIGATES`, `IMPLEMENTS`)._

### Meetings (`RAISED_IN` from `{rid}` → meeting)

{fmt_meetings(g['meetings'])}

### Concerns linking here (`concern --BECAME--> {rid}`)

{fmt_list_md('', g['concern_titles'])}

### Commitments (`commitment --BECAME--> {rid}`)

{fmt_list_md('', [(c, nodes.get(c, {}).get('title','')) for c in g['commitments']]) if g['commitments'] else '- _None in current slice._'}

### Architecture canon (`{rid}` --DECIDED_BY--> architecture)

{fmt_list_md('', g['arch_titles'])}

### Decisions surfaced via bridging concerns (`concern --BECAME--> decision`)

{(chr(10).join(f'- **`{did}`:** {tit if tit else "_(see trace store)_"}' for did, tit in g['decisions']) if g['decisions'] else '- _None resolved through concern bridges in ingest._')}

### Risks `{rid}` participates in mitigating (`{rid}` --MITIGATES--> risk)

{fmt_list_md('', g['risk_titles'])}

### Jira implementation coverage (`jira_ticket --IMPLEMENTS--> {rid}`)

{fmt_jira(g['jira'])}

### Cross-links

| Destination | Repo / dashboard pointer |
|------------|--------------------------|
| Trace graph explorer | [`dashboard/intelligence.html`](../../dashboard/intelligence.html) (Traceability tab) |
| Traceability storyboard | [`dashboard/traceability_story.html`](../../dashboard/traceability_story.html) |
| ADR corpus (partial overlap) | [`docs/adr/`](../../docs/adr/) |

---

_Requirement body enriched for Studio documentation. Traceability bullets generated from **`dashboard/traceability_data.json`**; regenerate via `python3 requirements/parsed/sync_req_docs.py`. Meeting dates prefer node `meeting` field._
"""
    return md


def main():
    nodes, edges = load_bundle()
    reqs = [(n["id"], n["title"]) for n in nodes.values() if n["type"] == "requirement"]
    reqs.sort()
    for rid, title in reqs:
        md = build_markdown(rid, title, nodes, edges)
        out = OUT_DIR / f"{rid}.md"
        out.write_text(md, encoding="utf-8")
        print(out)


if __name__ == "__main__":
    main()
