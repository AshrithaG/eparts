"""
Seed the traceability store from all existing data sources.

Pulls from:
  1. Client meeting JSONs (concerns, decisions, action items, participants)
  2. Coach session DB (commitments, concerns)
  3. Jira (live tickets)
  4. Risk register
  5. Architecture report (key decisions)
  6. EventBus (logged events)

Run: python -m pipeline.seed_traceability
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from glob import glob
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def seed(force: bool = False) -> dict:
    from pipeline.traceability import TraceabilityStore

    store = TraceabilityStore()

    if not force:
        existing = store.stats()
        if existing["total_artifacts"] > 20:
            logger.info(f"Traceability already seeded ({existing['total_artifacts']} artifacts). Use force=True to reseed.")
            return existing

    counts = {"meetings": 0, "concerns": 0, "decisions": 0, "action_items": 0,
              "commitments": 0, "risks": 0, "jira_tickets": 0, "architecture": 0, "links": 0}

    # =========================================================================
    # 1. CLIENT MEETINGS — meetings, concerns, decisions, action items
    # =========================================================================
    for f in sorted(glob(str(PROJECT_ROOT / "minutes" / "*-client.json"))):
        with open(f) as fh:
            data = json.load(fh)

        meeting_date = data.get("meeting_date", "unknown")
        participants = data.get("participants", [])

        # Create meeting artifact
        meeting_id = store.add_artifact(
            artifact_type="meeting",
            title=f"Client Meeting {meeting_date}",
            description=f"{data.get('duration_minutes', 0)} min, {data.get('total_words', 0)} words, {data.get('participant_count', 0)} participants",
            status="done",
            source_meeting=meeting_date,
            artifact_id=f"MTG-{meeting_date}",
            metadata={"participants": participants, "topics": data.get("detected_topics", {})},
        )
        counts["meetings"] += 1

        # Extract concerns from detected topics and questions
        for q in data.get("questions_sample", []):
            speaker = q.get("speaker", "unknown")
            text = q.get("text", "")[:200]
            if not text:
                continue
            cid = store.add_artifact(
                artifact_type="concern",
                title=text[:100],
                description=text,
                source_meeting=meeting_date,
                source_speaker=speaker,
                source_quote=text[:300],
                owner=speaker,
            )
            store.link(cid, meeting_id, "RAISED_IN", f"Raised by {speaker} in {meeting_date} meeting")
            counts["concerns"] += 1
            counts["links"] += 1

        # Extract decisions
        for d in data.get("decisions_sample", []):
            speaker = d.get("speaker", "unknown")
            text = d.get("text", "")[:200]
            if not text:
                continue
            did = store.add_artifact(
                artifact_type="decision",
                title=text[:100],
                description=text,
                status="done",
                source_meeting=meeting_date,
                source_speaker=speaker,
                source_quote=text[:300],
            )
            store.link(did, meeting_id, "RAISED_IN", f"Decided in {meeting_date} meeting")
            counts["decisions"] += 1
            counts["links"] += 1

        # Extract action items
        for a in data.get("actions_sample", []):
            speaker = a.get("speaker", "unknown")
            text = a.get("text", "")[:200]
            if not text or len(text) < 20:
                continue
            aid = store.add_artifact(
                artifact_type="action_item",
                title=text[:100],
                description=text,
                source_meeting=meeting_date,
                source_speaker=speaker,
                source_quote=text[:300],
                owner=speaker,
            )
            store.link(aid, meeting_id, "RAISED_IN", f"Action from {meeting_date} meeting")
            counts["action_items"] += 1
            counts["links"] += 1

    # =========================================================================
    # 2. COACH SESSIONS — commitments and concerns
    # =========================================================================
    coach_db_path = PROJECT_ROOT / "memory" / "coach_sessions.db"
    if coach_db_path.exists():
        cdb = sqlite3.connect(str(coach_db_path))
        cdb.row_factory = sqlite3.Row

        # Sessions
        for sess in cdb.execute("SELECT * FROM sessions").fetchall():
            sess = dict(sess)
            sid = store.add_artifact(
                artifact_type="coach_session",
                title=f"Coach Session {sess['date']} ({sess['session_type']})",
                description=f"Participants: {sess['participants']}",
                status="done",
                source_meeting=sess["date"],
                artifact_id=f"COACH-{sess['session_id'][:8]}",
                metadata={"session_id": sess["session_id"], "type": sess["session_type"]},
            )
            counts["meetings"] += 1

        # Commitments
        for c in cdb.execute(
            "SELECT c.*, s.date FROM commitments c JOIN sessions s ON c.session_id = s.session_id"
        ).fetchall():
            c = dict(c)
            text = c.get("commitment_text", "")
            if not text:
                continue
            cid = store.add_artifact(
                artifact_type="commitment",
                title=text[:100],
                description=text,
                status=c.get("status", "open"),
                source_meeting=c.get("date", ""),
                owner=c.get("owner", "Team"),
                metadata={"deadline": c.get("deadline", ""), "evidence": c.get("evidence_link", "")},
            )
            session_aid = f"COACH-{c['session_id'][:8]}"
            store.link(cid, session_aid, "RAISED_IN", f"Commitment from coach session {c.get('date', '')}")
            counts["commitments"] += 1
            counts["links"] += 1

        # Concerns from coach
        for con in cdb.execute("SELECT co.*, s.date FROM concerns co JOIN sessions s ON co.session_id = s.session_id").fetchall():
            con = dict(con)
            text = con.get("concern_text", "")
            if not text:
                continue
            coid = store.add_artifact(
                artifact_type="concern",
                title=text[:100],
                description=text,
                source_meeting=con.get("date", ""),
                source_speaker=con.get("raised_by", "coach"),
                metadata={"theme": con.get("theme", ""), "times_raised": con.get("times_raised", 1)},
            )
            session_aid = f"COACH-{con['session_id'][:8]}"
            store.link(coid, session_aid, "RAISED_IN", f"Coach concern from {con.get('date', '')}")
            counts["concerns"] += 1
            counts["links"] += 1

        cdb.close()

    # =========================================================================
    # 3. JIRA TICKETS
    # =========================================================================
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
    except Exception:
        pass

    try:
        from mcp.jira import JiraMCP
        jira = JiraMCP()
        if jira.is_configured:
            result = jira.search_issues(max_results=50)
            if result.get("ok"):
                for iss in result.get("issues", []):
                    labels = iss.get("labels", [])
                    jid = store.add_artifact(
                        artifact_type="jira_ticket",
                        title=iss.get("summary", ""),
                        status=_map_jira_status(iss.get("status", "")),
                        owner=iss.get("assignee", ""),
                        jira_key=iss.get("key", ""),
                        priority=iss.get("priority", ""),
                        artifact_id=iss.get("key", ""),
                        metadata={"labels": labels},
                    )
                    counts["jira_tickets"] += 1

                    # Link AI-generated tickets to their source meetings
                    for label in labels:
                        if label.startswith("meeting-"):
                            meeting_date = label.replace("meeting-", "")
                            meeting_aid = f"MTG-{meeting_date}"
                            store.link(jid, meeting_aid, "RAISED_IN", f"Created from {meeting_date} meeting")
                            counts["links"] += 1
    except Exception as e:
        logger.warning(f"Jira seeding skipped: {e}")

    # =========================================================================
    # 4. RISK REGISTER
    # =========================================================================
    try:
        from pipeline.risk_register import RiskRegister, seed_risk_register
        reg = seed_risk_register()
        for risk in reg.get_all():
            rid = store.add_artifact(
                artifact_type="risk",
                title=risk.get("title", ""),
                description=risk.get("description", ""),
                status="open" if risk.get("status", "open") == "open" else "done",
                priority=f"L{risk.get('likelihood', '?')}/I{risk.get('impact', '?')}",
                artifact_id=risk.get("risk_id", ""),
                metadata={
                    "category": risk.get("category", ""),
                    "mitigation": risk.get("mitigation", ""),
                    "severity": risk.get("severity", 0),
                    "source": risk.get("source", ""),
                },
            )
            counts["risks"] += 1
    except Exception as e:
        logger.warning(f"Risk register seeding skipped: {e}")

    # =========================================================================
    # 5. KEY ARCHITECTURE DECISIONS (manually curated from meeting data)
    # =========================================================================
    arch_decisions = [
        {
            "id": "ARCH-001", "title": "Use Bicep over Terraform for Azure IaC",
            "description": "David recommended Bicep due to team familiarity. Terraform considered but rejected.",
            "meeting": "2026-02-12", "speaker": "Client Lead", "status": "done",
        },
        {
            "id": "ARCH-002", "title": "Map to industry standards instead of ALPS-specific attributes",
            "description": "Harsha recommended general industry standards over ALPS naming for product attributes. Simplifies extraction from vendor spec sheets.",
            "meeting": "2026-04-02", "speaker": "Harsha (eParts)", "status": "done",
        },
        {
            "id": "ARCH-003", "title": "ML confidence scoring for attribute prediction",
            "description": "Use ML confidence scores for predicted product attributes. Low-confidence items go to human review queue.",
            "meeting": "2026-01-22", "speaker": "Hrishik", "status": "open",
        },
        {
            "id": "ARCH-004", "title": "Staging tables as Git-diff model for data review",
            "description": "eParts uses staging tables as a diff view for catalog team to review. ML pipeline outputs to staging, humans approve to production.",
            "meeting": "2026-01-22", "speaker": "Client Lead", "status": "done",
        },
        {
            "id": "ARCH-005", "title": "Human-in-the-loop for all AI-generated data",
            "description": "All AI-predicted attributes must pass through human review before entering production catalog. No fully automated path to production.",
            "meeting": "2026-01-22", "speaker": "Dennis Grinberg", "status": "done",
        },
        {
            "id": "ARCH-006", "title": "Agent-Augmented Iterative SDLC (bespoke)",
            "description": "Custom SDLC instead of Scrum/RUP. Practice areas map to agent pipelines. AI handles repeatable 80%, humans own judgment 20%.",
            "meeting": "internal", "speaker": "Team", "status": "done",
        },
    ]

    for ad in arch_decisions:
        aid = store.add_artifact(
            artifact_type="architecture",
            title=ad["title"],
            description=ad["description"],
            status=ad["status"],
            source_meeting=ad["meeting"],
            source_speaker=ad["speaker"],
            artifact_id=ad["id"],
        )
        if ad["meeting"] != "internal":
            store.link(aid, f"MTG-{ad['meeting']}", "RAISED_IN", f"Architecture decision from {ad['meeting']}")
            counts["links"] += 1
        counts["architecture"] += 1

    # =========================================================================
    # 6. CROSS-LINKS — connect concerns → decisions → requirements → jira → risks
    # =========================================================================
    _build_cross_links(store, counts)

    logger.info(f"\n=== Traceability Seeded ===")
    for k, v in counts.items():
        logger.info(f"  {k}: {v}")

    final = store.stats()
    logger.info(f"\n  Total artifacts: {final['total_artifacts']}")
    logger.info(f"  Total links: {final['total_links']}")
    logger.info(f"  Coverage: {final['coverage_pct']}%")

    return final


def _build_cross_links(store, counts: dict) -> None:
    """Build semantic cross-links between related artifacts."""

    # Link architecture decisions to concerns they address
    concern_decision_pairs = [
        ("vendor data", "ARCH-002"),     # vendor data quality → industry standards
        ("confidence", "ARCH-003"),      # confidence → ML confidence scoring
        ("human", "ARCH-005"),           # human review → human-in-the-loop
        ("staging", "ARCH-004"),         # staging → staging tables
        ("Bicep", "ARCH-001"),           # infrastructure → Bicep
        ("Terraform", "ARCH-001"),
    ]
    concerns = store.get_by_type("concern")
    for concern in concerns:
        title_lower = concern["title"].lower() + " " + concern.get("description", "").lower()
        for keyword, arch_id in concern_decision_pairs:
            if keyword.lower() in title_lower:
                store.link(arch_id, concern["id"], "ADDRESSES", f"Architecture decision addresses this concern")
                counts["links"] += 1
                break

    # Link Jira tickets to architecture decisions and action items
    jira_tickets = store.get_by_type("jira_ticket")
    action_items = store.get_by_type("action_item")
    arch_items = store.get_by_type("architecture")

    for ticket in jira_tickets:
        t_lower = ticket["title"].lower()

        # Link to architecture decisions
        for arch in arch_items:
            a_lower = arch["title"].lower()
            shared_words = set(a_lower.split()) & set(t_lower.split())
            significant = {w for w in shared_words if len(w) > 4}
            if len(significant) >= 2:
                store.link(ticket["id"], arch["id"], "IMPLEMENTS", "Ticket implements architecture decision")
                counts["links"] += 1

        # Link to action items from same meeting
        for ai in action_items:
            if ticket.get("source_meeting") and ai.get("source_meeting") == ticket.get("source_meeting"):
                ai_lower = ai["title"].lower()
                shared_words = set(ai_lower.split()) & set(t_lower.split())
                significant = {w for w in shared_words if len(w) > 4}
                if len(significant) >= 2:
                    store.link(ticket["id"], ai["id"], "IMPLEMENTS", "Ticket tracks this action item")
                    counts["links"] += 1

    # Link risks to architecture decisions that mitigate them
    risks = store.get_by_type("risk")
    for risk in risks:
        r_lower = risk["title"].lower() + " " + risk.get("description", "").lower()
        mitigation = (risk.get("metadata") or {}).get("mitigation", "").lower()

        for arch in arch_items:
            a_lower = arch["title"].lower() + " " + arch.get("description", "").lower()
            shared_words = set(a_lower.split()) & set(r_lower.split())
            significant = {w for w in shared_words if len(w) > 4}
            if len(significant) >= 2 or any(kw in a_lower for kw in mitigation.split() if len(kw) > 4):
                store.link(arch["id"], risk["id"], "MITIGATES", "Architecture decision mitigates this risk")
                counts["links"] += 1

        # Link Jira tickets to risks they mitigate
        for ticket in jira_tickets:
            t_lower = ticket["title"].lower()
            shared_words = set(t_lower.split()) & set(r_lower.split())
            significant = {w for w in shared_words if len(w) > 4}
            if len(significant) >= 2:
                store.link(ticket["id"], risk["id"], "MITIGATES", "Ticket mitigates this risk")
                counts["links"] += 1

    # Link commitments to Jira tickets
    commitments = store.get_by_type("commitment")
    for c in commitments:
        c_lower = c["title"].lower()
        for ticket in jira_tickets:
            t_lower = ticket["title"].lower()
            shared_words = set(c_lower.split()) & set(t_lower.split())
            significant = {w for w in shared_words if len(w) > 4}
            if len(significant) >= 2:
                store.link(ticket["id"], c["id"], "IMPLEMENTS", "Ticket fulfills this commitment")
                counts["links"] += 1


def _map_jira_status(status: str) -> str:
    s = status.lower()
    if s == "done":
        return "done"
    elif s in ("in progress", "in review"):
        return "in_progress"
    return "open"


if __name__ == "__main__":
    seed(force=True)
