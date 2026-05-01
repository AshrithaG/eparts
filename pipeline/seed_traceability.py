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
              "commitments": 0, "risks": 0, "jira_tickets": 0, "architecture": 0,
              "requirements": 0, "links": 0}

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
    # 6. REQUIREMENTS — derived from architecture report and meeting decisions
    # =========================================================================
    requirements = [
        {"id": "REQ-001", "title": "Extract product attributes from vendor spec sheets",
         "description": "System must parse PDF/CSV vendor documents and extract structured attributes (dimensions, material, voltage, etc.)",
         "meeting": "2026-01-22", "priority": "P0", "arch": ["ARCH-002", "ARCH-003"]},
        {"id": "REQ-002", "title": "Map extracted attributes to industry-standard taxonomy",
         "description": "Use general industry standards instead of ALPS-specific naming. Decided based on Harsha's recommendation (April 2 meeting).",
         "meeting": "2026-04-02", "priority": "P0", "arch": ["ARCH-002"]},
        {"id": "REQ-003", "title": "ML confidence scoring on every predicted attribute",
         "description": "Each predicted attribute value must carry a confidence score. Low-confidence items routed to human review queue.",
         "meeting": "2026-01-22", "priority": "P0", "arch": ["ARCH-003", "ARCH-005"]},
        {"id": "REQ-004", "title": "Human review queue for AI-generated catalog data",
         "description": "All AI predictions must pass through human review before entering production. No fully automated path to production catalog.",
         "meeting": "2026-01-22", "priority": "P0", "arch": ["ARCH-005", "ARCH-004"]},
        {"id": "REQ-005", "title": "Staging table diff model for catalog review workflow",
         "description": "ML pipeline outputs to staging tables. Catalog team reviews diffs (like Git) and approves to production.",
         "meeting": "2026-01-22", "priority": "P0", "arch": ["ARCH-004"]},
        {"id": "REQ-006", "title": "Azure infrastructure with Bicep IaC",
         "description": "Deploy on Azure. Use Bicep (not Terraform) for infrastructure-as-code based on team familiarity.",
         "meeting": "2026-02-12", "priority": "P0", "arch": ["ARCH-001"]},
        {"id": "REQ-007", "title": "Azure Log Analytics for monitoring and observability",
         "description": "Use Azure Log Analytics for system monitoring. Track ML model performance, API latency, data ingestion metrics.",
         "meeting": "2026-02-12", "priority": "P1", "arch": ["ARCH-001"]},
        {"id": "REQ-008", "title": "Support multiple vendor document formats",
         "description": "Handle PDFs, CSVs, and other formats from different vendors. OCR capability for scanned documents.",
         "meeting": "2026-02-26", "priority": "P0", "arch": ["ARCH-002", "ARCH-003"]},
        {"id": "REQ-009", "title": "POC demonstrating end-to-end attribute extraction",
         "description": "Build proof-of-concept showing: vendor doc → extraction → confidence scoring → human review → catalog update.",
         "meeting": "2026-04-02", "priority": "P0", "arch": ["ARCH-003", "ARCH-004", "ARCH-005"]},
        {"id": "REQ-010", "title": "Statement of Work signed by end of April",
         "description": "Finalize and sign SoW with client feedback on deliverables and timeline.",
         "meeting": "2026-04-02", "priority": "P0", "arch": []},
        {"id": "REQ-011", "title": "Team AI usage policy and best practices guide",
         "description": "Implement Claude token usage policy. Create shared best practices guide for consistent AI use across team.",
         "meeting": "2026-04-16", "priority": "P1", "arch": ["ARCH-006"]},
        {"id": "REQ-012", "title": "Formal ADRs for all architecture decisions",
         "description": "Document architecture decisions as formal ADRs. Coach feedback emphasized this for traceability.",
         "meeting": "coach", "priority": "P1", "arch": ["ARCH-001", "ARCH-002", "ARCH-003", "ARCH-004", "ARCH-005"]},
    ]

    for req in requirements:
        rid = store.add_artifact(
            artifact_type="requirement",
            title=req["title"],
            description=req["description"],
            status="open",
            source_meeting=req["meeting"],
            priority=req["priority"],
            artifact_id=req["id"],
        )
        if req["meeting"] not in ("coach", "internal"):
            store.link(rid, f"MTG-{req['meeting']}", "RAISED_IN", f"Derived from {req['meeting']} meeting")
            counts["links"] += 1
        for arch_id in req.get("arch", []):
            store.link(rid, arch_id, "DECIDED_BY", f"Requirement shaped by {arch_id}")
            counts["links"] += 1
        counts["requirements"] = counts.get("requirements", 0) + 1

    # =========================================================================
    # 7. CROSS-LINKS — connect concerns → decisions → requirements → jira → risks
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
    """
    Build real cross-links between artifacts using three strategies:
      1. LABEL-BASED — Jira ticket labels map to domains/architecture decisions
      2. EXPLICIT CURATED — known relationships from project knowledge
      3. THEMATIC — domain keyword groups for fuzzy matching
    """
    concerns = store.get_by_type("concern")
    decisions = store.get_by_type("decision")
    action_items = store.get_by_type("action_item")
    arch_items = store.get_by_type("architecture")
    risks = store.get_by_type("risk")
    jira_tickets = store.get_by_type("jira_ticket")
    commitments = store.get_by_type("commitment")
    requirements = store.get_by_type("requirement")

    # Domain keyword groups — shared across all linking strategies
    DOMAIN_KEYWORDS = {
        "ml_data": {"ml", "model", "confidence", "training", "predict", "attribute",
                     "extraction", "vendor", "catalog", "data", "schema", "accuracy",
                     "llm", "ai", "ocr", "classification"},
        "architecture": {"architecture", "adr", "decision", "bicep", "terraform",
                         "diagram", "tradeoff", "analysis", "design", "pattern"},
        "infrastructure": {"azure", "deploy", "monitor", "log", "analytics",
                           "infrastructure", "pipeline", "bicep", "iac"},
        "requirements": {"requirement", "specification", "sow", "scope", "deliverable",
                         "finalize", "document", "timeline"},
        "process": {"sprint", "agile", "sdlc", "process", "risk", "management",
                    "project", "board", "presentation", "critique"},
        "review": {"review", "approval", "staging", "human", "loop", "queue",
                   "diff", "catalog"},
    }

    def _get_domains(text: str, labels: list | None = None) -> set[str]:
        """Classify text into domain groups."""
        text_lower = text.lower()
        words = set(text_lower.split())
        matched = set()
        for domain, keywords in DOMAIN_KEYWORDS.items():
            if words & keywords:
                matched.add(domain)
        if labels:
            label_set = {l.lower() for l in labels}
            if label_set & {"architecture", "decision"}:
                matched.add("architecture")
            if label_set & {"ml", "research"}:
                matched.add("ml_data")
            if label_set & {"infrastructure", "milestone"}:
                matched.add("infrastructure")
            if label_set & {"requirements"}:
                matched.add("requirements")
            if label_set & {"ai-tooling", "best-practices"}:
                matched.add("process")
            if label_set & {"measurement"}:
                matched.add("ml_data")
                matched.add("review")
            if label_set & {"coach-feedback"}:
                matched.add("process")
                matched.add("architecture")
        return matched

    # Map architecture decisions to domains
    arch_domain_map = {
        "ARCH-001": {"infrastructure"},
        "ARCH-002": {"ml_data", "requirements"},
        "ARCH-003": {"ml_data", "review"},
        "ARCH-004": {"review", "ml_data"},
        "ARCH-005": {"review", "ml_data"},
        "ARCH-006": {"process"},
    }

    # Map requirements to domains
    req_domain_map = {
        "REQ-001": {"ml_data"},
        "REQ-002": {"ml_data", "requirements"},
        "REQ-003": {"ml_data", "review"},
        "REQ-004": {"review"},
        "REQ-005": {"review", "ml_data"},
        "REQ-006": {"infrastructure"},
        "REQ-007": {"infrastructure"},
        "REQ-008": {"ml_data"},
        "REQ-009": {"ml_data", "review"},
        "REQ-010": {"requirements", "process"},
        "REQ-011": {"process"},
        "REQ-012": {"architecture"},
    }

    # =====================================================================
    # 1. CONCERNS → ARCHITECTURE (ADDRESSES)
    # =====================================================================
    for concern in concerns:
        c_domains = _get_domains(concern["title"] + " " + concern.get("description", ""))
        for arch in arch_items:
            a_domains = arch_domain_map.get(arch["id"], set())
            if c_domains & a_domains:
                store.link(arch["id"], concern["id"], "ADDRESSES",
                           f"Architecture decision addresses concern (shared domains: {c_domains & a_domains})")
                counts["links"] += 1

    # =====================================================================
    # 2. CONCERNS → DECISIONS (BECAME) — same meeting
    # =====================================================================
    for concern in concerns:
        c_meeting = concern.get("source_meeting", "")
        if not c_meeting:
            continue
        c_domains = _get_domains(concern["title"])
        for decision in decisions:
            if decision.get("source_meeting") != c_meeting:
                continue
            d_domains = _get_domains(decision["title"])
            if c_domains & d_domains:
                store.link(concern["id"], decision["id"], "BECAME",
                           "Concern led to this decision in the same meeting")
                counts["links"] += 1

    # =====================================================================
    # 3. CONCERNS → REQUIREMENTS (BECAME)
    # =====================================================================
    for concern in concerns:
        c_domains = _get_domains(concern["title"] + " " + concern.get("description", ""))
        for req in requirements:
            r_domains = req_domain_map.get(req["id"], set())
            if c_domains & r_domains:
                store.link(concern["id"], req["id"], "BECAME",
                           "Concern shaped this requirement")
                counts["links"] += 1

    # =====================================================================
    # 4. DECISIONS → ARCHITECTURE (DECIDED_BY)
    # =====================================================================
    for decision in decisions:
        d_domains = _get_domains(decision["title"] + " " + decision.get("description", ""))
        for arch in arch_items:
            a_domains = arch_domain_map.get(arch["id"], set())
            if d_domains & a_domains:
                store.link(decision["id"], arch["id"], "DECIDED_BY",
                           "Decision influenced by architecture choice")
                counts["links"] += 1

    # =====================================================================
    # 5. DECISIONS → ACTION ITEMS (TRIGGERED) — same meeting
    # =====================================================================
    for decision in decisions:
        d_meeting = decision.get("source_meeting", "")
        if not d_meeting:
            continue
        d_domains = _get_domains(decision["title"])
        for ai in action_items:
            if ai.get("source_meeting") != d_meeting:
                continue
            ai_domains = _get_domains(ai["title"])
            if d_domains & ai_domains:
                store.link(ai["id"], decision["id"], "TRIGGERED",
                           "Action item triggered by this decision")
                counts["links"] += 1

    # =====================================================================
    # 6. REQUIREMENTS → RISKS (requirement failure creates risk)
    # =====================================================================
    for req in requirements:
        r_domains = req_domain_map.get(req["id"], set())
        req_blob = (req["title"] + " " + req.get("description", "")).lower()
        for risk in risks:
            risk_blob = (risk["title"] + " " + risk.get("description", "")).lower()
            risk_domains = _get_domains(risk_blob)
            if r_domains & risk_domains:
                store.link(req["id"], risk["id"], "MITIGATES",
                           "Fulfilling this requirement mitigates the risk")
                counts["links"] += 1

    # =====================================================================
    # 7. JIRA TICKETS — label-based and domain-based linking
    # =====================================================================

    # Explicit Jira → Architecture decision mapping from labels
    label_to_arch = {
        "architecture": ["ARCH-001", "ARCH-002", "ARCH-003", "ARCH-004", "ARCH-005"],
        "decision": ["ARCH-002", "ARCH-003"],
        "ML": ["ARCH-003"],
        "infrastructure": ["ARCH-001"],
        "measurement": ["ARCH-003"],
        "AI-tooling": ["ARCH-006"],
        "best-practices": ["ARCH-006"],
    }

    # Explicit Jira → Requirement mapping from labels
    label_to_req = {
        "architecture": ["REQ-012"],
        "requirements": ["REQ-001", "REQ-002"],
        "ML": ["REQ-001", "REQ-003", "REQ-008"],
        "infrastructure": ["REQ-006", "REQ-007"],
        "measurement": ["REQ-003", "REQ-009"],
        "AI-tooling": ["REQ-011"],
        "best-practices": ["REQ-011"],
        "coach-feedback": ["REQ-012"],
        "SES": ["REQ-011", "REQ-012"],
        "project-management": ["REQ-010"],
        "milestone": ["REQ-009", "REQ-010"],
        "onboarding": [],
        "research": ["REQ-001", "REQ-008"],
    }

    # Explicit Jira key → architecture mapping for manually created tickets
    manual_ticket_map = {
        "EPARTS-14": {"arch": ["ARCH-001", "ARCH-002"], "req": ["REQ-009"], "desc": "Context diagram"},
        "EPARTS-15": {"arch": ["ARCH-006"], "req": ["REQ-010"], "desc": "PM principles"},
        "EPARTS-33": {"arch": ["ARCH-006"], "req": [], "desc": "Jira automation"},
        "EPARTS-34": {"arch": [], "req": ["REQ-010"], "desc": "Risk management", "risks": True},
        "EPARTS-35": {"arch": ["ARCH-006"], "req": ["REQ-011"], "desc": "SES overhaul"},
        "EPARTS-36": {"arch": [], "req": ["REQ-001", "REQ-002"], "desc": "Requirements doc"},
        "EPARTS-37": {"arch": [], "req": [], "desc": "Presentation plan"},
        "EPARTS-38": {"arch": [], "req": [], "desc": "Slides context"},
        "EPARTS-39": {"arch": [], "req": ["REQ-001", "REQ-002", "REQ-003"], "desc": "Requirements gathering"},
        "EPARTS-40": {"arch": ["ARCH-001", "ARCH-002", "ARCH-003"], "req": ["REQ-012"], "desc": "Architecture slides"},
        "EPARTS-41": {"arch": ["ARCH-004", "ARCH-005"], "req": ["REQ-012"], "desc": "Architecture slides"},
        "EPARTS-42": {"arch": [], "req": ["REQ-010"], "desc": "Risk & PM slides", "risks": True},
        "EPARTS-43": {"arch": [], "req": [], "desc": "Presentation plan"},
        "EPARTS-44": {"arch": ["ARCH-006"], "req": [], "desc": "Process: internal rehearsal"},
        "EPARTS-45": {"arch": ["ARCH-006"], "req": [], "desc": "Process: final rehearsal"},
        "EPARTS-46": {"arch": [], "req": [], "desc": "Mentor meeting"},
        "EPARTS-47": {"arch": [], "req": [], "desc": "Mentor meeting"},
        "EPARTS-48": {"arch": ["ARCH-006"], "req": ["REQ-010"], "desc": "Semester roadmap"},
        "EPARTS-49": {"arch": ["ARCH-001"], "req": ["REQ-012"], "desc": "Diagram review"},
        "EPARTS-50": {"arch": [], "req": ["REQ-010"], "desc": "Timeline"},
        "EPARTS-51": {"arch": ["ARCH-006"], "req": ["REQ-011"], "desc": "Automation processes"},
        "EPARTS-52": {"arch": [], "req": [], "desc": "Board update"},
        "EPARTS-53": {"arch": ["ARCH-006"], "req": ["REQ-011"], "desc": "Tool access for AI workflow"},
        "EPARTS-54": {"arch": ["ARCH-006"], "req": ["REQ-011"], "desc": "Tool access for AI workflow"},
        "EPARTS-55": {"arch": ["ARCH-001", "ARCH-002", "ARCH-003", "ARCH-004", "ARCH-005"], "req": ["REQ-012"], "desc": "Architecture design"},
        "EPARTS-56": {"arch": ["ARCH-006"], "req": [], "desc": "Process: meeting preparation"},
        "EPARTS-57": {"arch": ["ARCH-006"], "req": ["REQ-011"], "desc": "Agentic system tasks"},
        "EPARTS-58": {"arch": [], "req": ["REQ-001", "REQ-002"], "desc": "Requirements review"},
        "EPARTS-59": {"arch": [], "req": ["REQ-010"], "desc": "Timeline update"},
        "EPARTS-60": {"arch": ["ARCH-003"], "req": ["REQ-003", "REQ-009"], "desc": "ML check-in"},
        "EPARTS-61": {"arch": ["ARCH-006"], "req": [], "desc": "Process: critique preparation"},
        "EPARTS-62": {"arch": ["ARCH-001", "ARCH-002", "ARCH-003"], "req": ["REQ-012"], "desc": "Architecture diagram"},
        "EPARTS-63": {"arch": ["ARCH-001", "ARCH-002", "ARCH-003", "ARCH-004", "ARCH-005"], "req": ["REQ-012"], "desc": "Architecture tradeoffs"},
        "EPARTS-64": {"arch": ["ARCH-001", "ARCH-002", "ARCH-003", "ARCH-004", "ARCH-005"], "req": ["REQ-012"], "desc": "Writing ADRs"},
    }

    for ticket in jira_tickets:
        t_blob = (ticket["title"] + " " + ticket.get("description", "")).lower()
        labels = (ticket.get("metadata") or {}).get("labels", [])
        jira_key = ticket.get("jira_key", "")
        t_domains = _get_domains(t_blob, labels)

        linked_arch = set()
        linked_req = set()

        # Strategy A: manual ticket map for known tickets
        if jira_key in manual_ticket_map:
            mapping = manual_ticket_map[jira_key]
            for arch_id in mapping.get("arch", []):
                if arch_id not in linked_arch:
                    store.link(ticket["id"], arch_id, "IMPLEMENTS",
                               f"{jira_key} implements {arch_id}")
                    counts["links"] += 1
                    linked_arch.add(arch_id)
            for req_id in mapping.get("req", []):
                if req_id not in linked_req:
                    store.link(ticket["id"], req_id, "IMPLEMENTS",
                               f"{jira_key} implements {req_id}")
                    counts["links"] += 1
                    linked_req.add(req_id)
            if mapping.get("risks"):
                for risk in risks:
                    store.link(ticket["id"], risk["id"], "MITIGATES",
                               f"{jira_key} risk management work mitigates risks")
                    counts["links"] += 1

        # Strategy B: label-based linking for AI-generated tickets
        for label in labels:
            for arch_id in label_to_arch.get(label, []):
                if arch_id not in linked_arch:
                    store.link(ticket["id"], arch_id, "IMPLEMENTS",
                               f"Label '{label}' maps to {arch_id}")
                    counts["links"] += 1
                    linked_arch.add(arch_id)
            for req_id in label_to_req.get(label, []):
                if req_id not in linked_req:
                    store.link(ticket["id"], req_id, "IMPLEMENTS",
                               f"Label '{label}' maps to {req_id}")
                    counts["links"] += 1
                    linked_req.add(req_id)

        # Strategy C: domain-based linking (fallback for unlinked tickets)
        if not linked_arch:
            for arch in arch_items:
                a_domains = arch_domain_map.get(arch["id"], set())
                if t_domains & a_domains and arch["id"] not in linked_arch:
                    store.link(ticket["id"], arch["id"], "IMPLEMENTS",
                               f"Domain match: {t_domains & a_domains}")
                    counts["links"] += 1
                    linked_arch.add(arch["id"])

        if not linked_req:
            for req in requirements:
                r_domains = req_domain_map.get(req["id"], set())
                if t_domains & r_domains and req["id"] not in linked_req:
                    store.link(ticket["id"], req["id"], "IMPLEMENTS",
                               f"Domain match: {t_domains & r_domains}")
                    counts["links"] += 1
                    linked_req.add(req["id"])

        # Link tickets to risks they mitigate
        for risk in risks:
            risk_blob = (risk["title"] + " " + risk.get("description", "")).lower()
            risk_domains = _get_domains(risk_blob)
            if t_domains & risk_domains:
                store.link(ticket["id"], risk["id"], "MITIGATES",
                           f"Ticket addresses risk domain: {t_domains & risk_domains}")
                counts["links"] += 1

        # Link tickets to commitments
        for commitment in commitments:
            cm_blob = (commitment["title"] + " " + commitment.get("description", "")).lower()
            cm_words = {w for w in cm_blob.split() if len(w) > 3}
            t_words = {w for w in t_blob.split() if len(w) > 3}
            if len(cm_words & t_words) >= 3:
                store.link(ticket["id"], commitment["id"], "IMPLEMENTS",
                           "Ticket fulfills this commitment")
                counts["links"] += 1

        # Link tickets to action items from same meeting (via meeting label)
        ticket_meetings = {l.replace("meeting-", "") for l in labels if l.startswith("meeting-")}
        if ticket_meetings:
            for ai in action_items:
                if ai.get("source_meeting") in ticket_meetings:
                    ai_domains = _get_domains(ai["title"])
                    if t_domains & ai_domains:
                        store.link(ticket["id"], ai["id"], "IMPLEMENTS",
                                   f"Same meeting + shared domain")
                        counts["links"] += 1

    # =====================================================================
    # 8. RISK → ARCHITECTURE mitigations
    # =====================================================================
    for risk in risks:
        r_blob = (risk["title"] + " " + risk.get("description", "")).lower()
        mitigation = ((risk.get("metadata") or {}).get("mitigation", "")).lower()
        r_domains = _get_domains(r_blob + " " + mitigation)

        for arch in arch_items:
            a_domains = arch_domain_map.get(arch["id"], set())
            if r_domains & a_domains:
                store.link(arch["id"], risk["id"], "MITIGATES",
                           f"Architecture mitigates risk (domains: {r_domains & a_domains})")
                counts["links"] += 1

    # =====================================================================
    # 9. COMMITMENTS → ARCHITECTURE + REQUIREMENTS
    # =====================================================================
    for commitment in commitments:
        cm_domains = _get_domains(commitment["title"] + " " + commitment.get("description", ""))
        for arch in arch_items:
            a_domains = arch_domain_map.get(arch["id"], set())
            if cm_domains & a_domains:
                store.link(arch["id"], commitment["id"], "IMPLEMENTS",
                           "Architecture fulfills commitment")
                counts["links"] += 1
        for req in requirements:
            r_domains = req_domain_map.get(req["id"], set())
            if cm_domains & r_domains:
                store.link(commitment["id"], req["id"], "BECAME",
                           "Commitment shaped this requirement")
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
