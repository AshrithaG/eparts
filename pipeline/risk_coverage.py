"""
Measure how good the SES actually is at finding risks.

The risk practice area claims that agents propose risks and a human accepts,
edits or rejects them. That claim is only worth making if we can say how often
the human agrees. This module measures it, from the two registers that already
exist in the repo:

  * the SES-generated register, `memory/risk_register.db`, populated by
    `pipeline/risk_register.py` from the architecture report, coach-session
    memory and unresolved meeting action items;
  * the human-owned register, `docs/eParts_Risk_Register_v2.md`, owned by the
    Risk Manager, which is the authoritative document.

The mapping between them is declared below as data rather than inferred, because
matching risk statements by text similarity would be a guess dressed up as a
measurement. Every row records which human entry a machine-proposed candidate
became, and what the reviewer did to it. The mapping is the auditable part: each
row can be checked against the two registers by hand in about a minute.

What comes out is a precision figure for the risk agents, the disposition split,
and the categories of risk the agents did not find at all, which is the more
useful half. Run:

    python3 -m pipeline.risk_coverage
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "memory" / "risk_register.db"
V2 = REPO / "docs" / "eParts_Risk_Register_v2.md"
OUT_MD = REPO / "docs" / "risk_coverage.md"
OUT_JSON = REPO / "dashboard" / "data" / "risk_coverage.json"

# Disposition of every risk the SES proposed, after Risk Manager review.
#
#   accepted  — carried into the human register substantially as proposed
#   rewritten — the underlying risk was real but the reviewer restated it, so
#               the agent found the right subject and the wrong framing
#   rejected  — the reviewer judged it not a risk and it appears nowhere
#   pending   — accepted as valid but not yet merged into the human register
#
# `becomes` lists the human entry IDs. One candidate can become two entries: the
# reviewer split the scope-creep candidate into a scope risk and a stakeholder
# risk, which are mitigated differently.
DISPOSITIONS: list[dict] = [
    {"candidate": "RISK-ARCH-01", "becomes": ["R-001"], "disposition": "accepted"},
    {"candidate": "RISK-ARCH-02", "becomes": ["R-003"], "disposition": "accepted"},
    {"candidate": "RISK-ARCH-03", "becomes": ["R-004"], "disposition": "accepted"},
    {"candidate": "RISK-ARCH-04", "becomes": ["R-010"], "disposition": "accepted"},
    {"candidate": "RISK-ARCH-05", "becomes": ["R-011"], "disposition": "accepted"},
    {"candidate": "RISK-ARCH-06", "becomes": ["R-005"], "disposition": "accepted"},
    {"candidate": "RISK-ARCH-07", "becomes": ["R-006"], "disposition": "accepted"},
    {"candidate": "RISK-ARCH-08", "becomes": ["R-012"], "disposition": "accepted"},
    {
        "candidate": "RISK-ARCH-09",
        "becomes": [],
        "disposition": "pending",
        "note": "ETIM release pin. Surfaced by walking traceability links from "
                "ADR-020 back to the register and finding nothing there. A "
                "consequence the team had accepted in writing and never tracked. "
                "Queued for the human register as R-027.",
    },
    {"candidate": "RISK-COACH-01", "becomes": ["R-002"], "disposition": "accepted"},
    {
        "candidate": "RISK-COACH-02",
        "becomes": ["R-013", "R-024"],
        "disposition": "accepted",
        "note": "Split by the reviewer into the scope risk and the stakeholder "
                "risk, because the two need different mitigations.",
    },
    {"candidate": "RISK-COACH-03", "becomes": ["R-014"], "disposition": "accepted"},
    {"candidate": "RISK-COACH-04", "becomes": ["R-007"], "disposition": "accepted"},
    {"candidate": "RISK-COACH-05", "becomes": ["R-008"], "disposition": "accepted"},
    {
        "candidate": "RISK-H1",
        "becomes": ["R-019"],
        "disposition": "rewritten",
        "note": "Proposed as team burnout, which names a cause and not a "
                "consequence. Restated as a member becoming unavailable and "
                "role coverage being lost, which is the thing that can be "
                "mitigated.",
    },
    {"candidate": "RISK-H2", "becomes": ["R-020"], "disposition": "accepted"},
    {
        "candidate": "RISK-H3",
        "becomes": [],
        "disposition": "rejected",
        "note": "Communication gaps between distributed members. The reviewer "
                "judged it a topic label rather than a risk: no condition, no "
                "consequence, nothing to mitigate against.",
    },
    {"candidate": "RISK-PM-01", "becomes": ["R-015"], "disposition": "accepted"},
    {"candidate": "RISK-PM-02", "becomes": ["R-009"], "disposition": "accepted"},
    {"candidate": "RISK-PM-03", "becomes": ["R-016"], "disposition": "accepted"},
]

# Human entries with no machine candidate behind them, and why the agents missed
# them. This is the blind spot, and it is the part worth showing.
HUMAN_ORIGIN_REASONS = {
    "R-017": "Tooling access. Resolved before the extraction pipeline was "
             "processing transcripts, so no source artifact existed to find it in.",
    "R-018": "Product-schema change affecting 30-40% of data. Domain knowledge "
             "from the client relationship, never stated in a transcript.",
    "R-021": "Adopting an unproven methodology. A risk about the team's own "
             "process, which the agents do not reason about.",
    "R-022": "Switching process mid-project with no experience in the new one. "
             "Same blind spot as R-021.",
    "R-023": "Client decision-makers becoming unavailable. Requires knowing who "
             "holds which sign-off, which lives in people's heads.",
    "R-025": "Compliance. Uploading client data to unapproved AI services. The "
             "agents were not given the SOW's restriction clauses.",
    "R-026": "The register's own reliability, including the possibility that "
             "agents hallucinate entries. An agent is a poor judge of this.",
}

# Sources in the human register that are a meeting the team sat in, as opposed to
# a document. Used to report how much of the register traces back to conversation,
# which is what the transcript pipeline feeds on.
MEETING_MARKERS = (
    "meeting", "standup", "sync", "session", "review", "discussion", "comment",
)
DOCUMENT_MARKERS = ("plan", "sow timeline", "constraint", "risk doc")


def _v2_rows() -> list[dict]:
    """Parse the human register's main table into id / category / source rows."""
    rows = []
    for line in V2.read_text(encoding="utf-8").splitlines():
        if not re.match(r"^\|\s*R-\d{3}\s*\|", line):
            continue
        c = [x.strip() for x in line.split("|")]
        rows.append({"id": c[1], "statement": c[2], "category": c[3],
                     "identified": c[4], "source": c[5], "owner": c[6]})
    return rows


def _is_meeting(source: str) -> bool:
    s = source.lower()
    if any(m in s for m in MEETING_MARKERS):
        return True
    return not any(m in s for m in DOCUMENT_MARKERS)


def compute() -> dict:
    if not DB.exists():
        raise SystemExit(f"missing {DB}; run pipeline/risk_register.py first")
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    candidates = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM risks")}

    declared = {d["candidate"] for d in DISPOSITIONS}
    missing = sorted(set(candidates) - declared)
    stale = sorted(declared - set(candidates))
    if missing or stale:
        raise SystemExit(
            "DISPOSITIONS is out of sync with the generated register.\n"
            f"  candidates with no declared disposition: {missing or 'none'}\n"
            f"  declared but no longer generated:        {stale or 'none'}\n"
            "Review each against docs/eParts_Risk_Register_v2.md and update."
        )

    v2 = _v2_rows()
    v2_ids = {r["id"] for r in v2}
    claimed: set[str] = set()
    for d in DISPOSITIONS:
        for rid in d["becomes"]:
            if rid not in v2_ids:
                raise SystemExit(f"{d['candidate']} maps to {rid}, absent from the register")
            claimed.add(rid)

    human_only = sorted(v2_ids - claimed)
    undocumented = [r for r in human_only if r not in HUMAN_ORIGIN_REASONS]
    if undocumented:
        raise SystemExit(
            f"human-origin entries with no recorded reason: {undocumented}"
        )

    counts = Counter(d["disposition"] for d in DISPOSITIONS)
    survived = counts["accepted"] + counts["rewritten"] + counts["pending"]
    meeting_sourced = [r for r in v2 if _is_meeting(r["source"])]

    return {
        "generated_at": date.today().isoformat(),
        "candidates_proposed": len(DISPOSITIONS),
        "dispositions": dict(counts),
        "survived_review": survived,
        "precision_pct": round(survived / len(DISPOSITIONS) * 100),
        "accepted_as_proposed_pct": round(counts["accepted"] / len(DISPOSITIONS) * 100),
        "rejected_pct": round(counts["rejected"] / len(DISPOSITIONS) * 100),
        "register_total": len(v2),
        "register_from_agents": len(claimed),
        "register_from_agents_pct": round(len(claimed) / len(v2) * 100),
        "register_human_only": len(human_only),
        "register_human_only_pct": round(len(human_only) / len(v2) * 100),
        "human_only_ids": human_only,
        "human_only_categories": sorted(
            {r["category"] for r in v2 if r["id"] in set(human_only)}
        ),
        "meeting_sourced": len(meeting_sourced),
        "meeting_sourced_pct": round(len(meeting_sourced) / len(v2) * 100),
        "candidate_titles": {k: v["title"] for k, v in candidates.items()},
    }


def render(m: dict) -> str:
    d = m["dispositions"]
    L = ["# Risk coverage — how much of the register the SES actually found", ""]
    L.append(
        "The risk practice area claims that agents propose and a human decides. "
        "This file measures how often the human agreed, so the claim is a number "
        "rather than an assertion. It is generated by "
        "`pipeline/risk_coverage.py` from `memory/risk_register.db` and "
        "`docs/eParts_Risk_Register_v2.md`."
    )
    L += ["", "## Headline", ""]
    L.append(f"- The SES proposed **{m['candidates_proposed']} risk candidates**.")
    L.append(
        f"- **{d.get('accepted', 0)} of {m['candidates_proposed']}** "
        f"({m['accepted_as_proposed_pct']}%) went into the human register "
        "substantially as the agent wrote them."
    )
    L.append(
        f"- **{d.get('rewritten', 0)}** was restated by the reviewer, "
        f"**{d.get('pending', 0)}** is accepted and awaiting merge, and "
        f"**{d.get('rejected', 0)}** was rejected outright "
        f"({m['rejected_pct']}% of what was proposed)."
    )
    L.append(
        f"- Counting the restated and pending entries as hits, "
        f"**{m['survived_review']} of {m['candidates_proposed']}** "
        f"({m['precision_pct']}%) named a risk the Risk Manager agreed was real. "
        "The stricter figure above is the honest one to quote; this is the "
        "generous one, and the gap between them is one restatement."
    )
    L.append(
        f"- Of the **{m['register_total']} risks** in the human register, "
        f"**{m['register_from_agents']}** ({m['register_from_agents_pct']}%) trace back to "
        f"something an agent surfaced, and **{m['register_human_only']}** "
        f"({m['register_human_only_pct']}%) were added by people."
    )
    L.append(
        f"- **{m['meeting_sourced']} of {m['register_total']}** "
        f"({m['meeting_sourced_pct']}%) cite a meeting as their source: client "
        "calls, mentor sessions and internal working sessions. That is the "
        "material the transcript pipeline reads."
    )
    L += ["", "## What the agents proposed, and what the reviewer did", ""]
    L.append("| Candidate | Title | Became | Disposition | Reviewer note |")
    L.append("|---|---|---|---|---|")
    for row in DISPOSITIONS:
        title = m["candidate_titles"].get(row["candidate"], "")
        became = ", ".join(f"`{b}`" for b in row["becomes"]) or "—"
        note = " ".join(row.get("note", "").split()) or ""
        L.append(
            f"| `{row['candidate']}` | {title} | {became} | "
            f"**{row['disposition']}** | {note} |"
        )
    L += ["", "## The blind spot", ""]
    L.append(
        f"{m['register_human_only']} register entries had no machine candidate "
        "behind them. They are not scattered: they cluster in the categories an "
        "agent reading transcripts and architecture documents has no way to see."
    )
    L += ["", "| Entry | Why no agent found it |", "|---|---|"]
    for rid in m["human_only_ids"]:
        L.append(f"| `{rid}` | {' '.join(HUMAN_ORIGIN_REASONS[rid].split())} |")
    L += [
        "",
        "Categories represented: " + ", ".join(m["human_only_categories"]) + ".",
        "",
        "The pattern is consistent. The agents are reliable on technical, data "
        "and dependency risks, which is where the source material is explicit. "
        "They found nothing about the team's own process, nothing about "
        "compliance, and nothing about which humans hold which sign-off. That is "
        "the argument for the review step: not that the agents are unreliable on "
        "what they do find, because at "
        f"{m['accepted_as_proposed_pct']}% accepted as written they are not, but "
        "that they do not know what they are not looking at.",
        "",
        "---",
        f"_Generated by `pipeline/risk_coverage.py` on {m['generated_at']}. "
        "The candidate-to-entry mapping is declared in that file and is "
        "hand-auditable against both registers._",
    ]
    return "\n".join(L) + "\n"


def main() -> int:
    m = compute()
    OUT_MD.write_text(render(m), encoding="utf-8")
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT_MD.relative_to(REPO)} and {OUT_JSON.relative_to(REPO)}")
    print(
        f"  {m['candidates_proposed']} proposed · {m['survived_review']} survived "
        f"({m['precision_pct']}%) · {m['dispositions'].get('rejected', 0)} rejected"
    )
    print(
        f"  register {m['register_total']}: {m['register_from_agents']} agent-sourced "
        f"({m['register_from_agents_pct']}%), {m['register_human_only']} human-only "
        f"({m['register_human_only_pct']}%)"
    )
    print(
        f"  {m['meeting_sourced']} of {m['register_total']} cite a meeting "
        f"({m['meeting_sourced_pct']}%)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
