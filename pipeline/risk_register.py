"""
Risk Register — auto-populated from architecture report, coach sessions, and meetings.

Risks are pulled from three sources:
  1. Architecture report (Section 5.4) — technical risks and sensitivity points
  2. Coach session memory — recurring concerns tracked across sessions
  3. Meeting action items — unresolved items that become risks over time

Each risk has: ID, title, category, source, likelihood, impact, severity,
mitigation strategy, status, owner, and links to related artifacts.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("pipeline.risk_register")

MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"
DB_PATH = MEMORY_DIR / "risk_register.db"


def _init_db(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(textwrap.dedent("""\
        CREATE TABLE IF NOT EXISTS risks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            category TEXT DEFAULT '',
            source TEXT DEFAULT '',
            source_detail TEXT DEFAULT '',
            likelihood TEXT DEFAULT 'medium',
            impact TEXT DEFAULT 'medium',
            severity TEXT DEFAULT 'medium',
            mitigation TEXT DEFAULT '',
            contingency TEXT DEFAULT '',
            status TEXT DEFAULT 'open',
            owner TEXT DEFAULT 'team',
            related_reqs TEXT DEFAULT '[]',
            related_arch TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """))
    conn.commit()
    return conn


SEVERITY_MATRIX = {
    ("high", "high"): "critical",
    ("high", "medium"): "high",
    ("medium", "high"): "high",
    ("high", "low"): "medium",
    ("low", "high"): "medium",
    ("medium", "medium"): "medium",
    ("medium", "low"): "low",
    ("low", "medium"): "low",
    ("low", "low"): "low",
}


class RiskRegister:
    def __init__(self, db_path: Path | None = None):
        self._db = _init_db(db_path)

    def add_risk(
        self,
        risk_id: str,
        title: str,
        description: str = "",
        category: str = "",
        source: str = "",
        source_detail: str = "",
        likelihood: str = "medium",
        impact: str = "medium",
        mitigation: str = "",
        contingency: str = "",
        status: str = "open",
        owner: str = "team",
        related_reqs: list[str] | None = None,
        related_arch: list[str] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        severity = SEVERITY_MATRIX.get((likelihood, impact), "medium")
        self._db.execute(
            "INSERT OR REPLACE INTO risks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (risk_id, title, description, category, source, source_detail,
             likelihood, impact, severity, mitigation, contingency, status, owner,
             json.dumps(related_reqs or []), json.dumps(related_arch or []),
             now, now),
        )
        self._db.commit()

    def get_all(self) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM risks ORDER BY "
            "CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, id"
        ).fetchall()
        return [
            {**dict(r), "related_reqs": json.loads(r["related_reqs"]),
             "related_arch": json.loads(r["related_arch"])}
            for r in rows
        ]

    def get_by_category(self, category: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM risks WHERE category = ? ORDER BY severity", (category,)
        ).fetchall()
        return [dict(r) for r in rows]

    def update_status(self, risk_id: str, status: str) -> None:
        self._db.execute(
            "UPDATE risks SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now(timezone.utc).isoformat(), risk_id),
        )
        self._db.commit()

    def stats(self) -> dict[str, Any]:
        total = self._db.execute("SELECT COUNT(*) as c FROM risks").fetchone()["c"]
        by_severity = self._db.execute(
            "SELECT severity, COUNT(*) as c FROM risks GROUP BY severity"
        ).fetchall()
        by_status = self._db.execute(
            "SELECT status, COUNT(*) as c FROM risks GROUP BY status"
        ).fetchall()
        by_category = self._db.execute(
            "SELECT category, COUNT(*) as c FROM risks GROUP BY category"
        ).fetchall()
        return {
            "total": total,
            "by_severity": {r["severity"]: r["c"] for r in by_severity},
            "by_status": {r["status"]: r["c"] for r in by_status},
            "by_category": {r["category"]: r["c"] for r in by_category},
        }


def seed_risk_register(reg: RiskRegister | None = None) -> RiskRegister:
    """
    Seed the risk register from all known sources:
    architecture report, coach sessions, project management doc.
    """
    if reg is None:
        reg = RiskRegister()

    # === Architecture Report Risks (Section 5.4) ===
    reg.add_risk(
        "RISK-ARCH-01", "Confidence threshold miscalibration",
        description="0.85 threshold is unsupported by empirical data. If too high, review queue "
                    "overwhelms catalog team (no labor savings). If too low, incorrect data enters PIMS.",
        category="technical", source="architecture_report", source_detail="Section 5.4 Risk 1",
        likelihood="high", impact="high",
        mitigation="Refinement 1: Run prototype on >=200 labeled submissions, compute precision-recall curves",
        contingency="Improve model or renegotiate accuracy target with Harsha",
        related_reqs=["QA-1", "FR-4"], related_arch=["AD-4", "routing"],
    )
    reg.add_risk(
        "RISK-ARCH-02", "Insufficient training data (<200 labeled examples)",
        description="Embedding layer will be undertrained; hybrid approach falls back to pure rules "
                    "with limited coverage (~40-60%).",
        category="technical", source="architecture_report", source_detail="Section 5.4 Risk 2",
        likelihood="medium", impact="high",
        mitigation="Secure labeled data from eParts; augment with synthetic examples if needed",
        contingency="Fall back to pure rule engine (ADR-1 Alt A trigger)",
        related_reqs=["FR-3"], related_arch=["ADR-1", "prediction"],
    )
    reg.add_risk(
        "RISK-ARCH-03", "PIMS staging schema incompatibility (P1-C pending)",
        description="Jake has not delivered the P1-C schema. If staging tables use wide columns or "
                    "lack key columns, the writeback mechanism needs redesign.",
        category="technical", source="architecture_report", source_detail="Section 5.4 Risk 3",
        likelihood="medium", impact="high",
        mitigation="Refinement 4: Map P1-C columns to canonical schema; integration-test 10 sample records",
        contingency="Team-owned buffer table if schema incompatible",
        related_reqs=["FR-6"], related_arch=["AD-3", "AD-5", "writeback"],
    )

    # Architecture sensitivity points
    reg.add_risk(
        "RISK-ARCH-04", "Alpha weighting sensitivity in hybrid scoring",
        description="Small tuning errors in alpha (currently 0.7) have outsized effects on routing behavior. "
                    "Wrong alpha suppresses the more accurate signal source.",
        category="technical", source="architecture_report", source_detail="Section 5.4 Sensitivity 1",
        likelihood="medium", impact="medium",
        mitigation="Refinement 3: Sweep alpha 0.3-0.9; measure ECE, precision, coverage",
        related_reqs=["QA-1"], related_arch=["ADR-1"],
    )
    reg.add_risk(
        "RISK-ARCH-05", "Attribute correlation invalidates per-attribute routing",
        description="Correlated attributes reviewed independently could produce inconsistent records. "
                    "If >30% of corrections involve cross-attribute errors, need to switch to per-record.",
        category="technical", source="architecture_report", source_detail="Section 5.4 Sensitivity 2",
        likelihood="low", impact="high",
        mitigation="Refinement 2: Pairwise mutual information analysis on labeled data",
        contingency="Switch to per-record routing (Section 4.2 Alt B)",
        related_reqs=["QA-1", "FR-4"], related_arch=["routing"],
    )
    reg.add_risk(
        "RISK-ARCH-06", "Catalog team capacity vs review volume",
        description="Entire value proposition depends on review volume being manageable by 1.5 + 3 FTEs. "
                    "If per-attribute routing still produces too many items, no labor savings.",
        category="business", source="architecture_report", source_detail="Section 5.4 Sensitivity 3",
        likelihood="medium", impact="high",
        mitigation="Measure actual review volume in prototype; adjust threshold iteratively",
        contingency="Lower threshold (accepting more accuracy risk) or invest in reviewer tooling",
        related_reqs=["QA-1"], related_arch=["routing", "review"],
    )

    # Unresolved items from architecture
    reg.add_risk(
        "RISK-ARCH-07", "Drift detection metrics and baselines undefined",
        description="Monitorability scaffolding exists (telemetry from 4 pipeline stages, audit trail) "
                    "but operational content is empty — no baseline metrics, alert thresholds, or "
                    "correction-to-retraining feedback loop.",
        category="technical", source="architecture_report", source_detail="Section 5.4 Unresolved 1",
        likelihood="high", impact="medium",
        mitigation="Define baseline metrics before prototype; SES measurement system can track these",
        related_reqs=["QA-5"], related_arch=["observability"],
    )
    reg.add_risk(
        "RISK-ARCH-08", "Human review interface design not decided",
        description="No custom review UI is in scope for current phase, but reviewer walkthrough "
                    "(Refinement 5) may reveal that tabular export is insufficient.",
        category="ux", source="architecture_report", source_detail="Section 5.4 Unresolved 3",
        likelihood="medium", impact="medium",
        mitigation="Refinement 5: Present 30 sample items to Brian/Dewey; measure time and accuracy",
        contingency="Renegotiate custom UI scope if needed",
        related_reqs=["FR-5"], related_arch=["review"],
    )

    # === Coach Session Concerns ===
    reg.add_risk(
        "RISK-COACH-01", "Data access delay blocking ML development",
        description="Recurring concern across 3 coach sessions (Cory, Dennis, Ben). "
                    "Development cannot proceed without client data for model training.",
        category="schedule", source="coach_sessions", source_detail="Cory, Dennis, Ben sessions",
        likelihood="high", impact="high",
        mitigation="Data received ~Feb 22; team started basic model tests. Continue pressing for complete dataset.",
        status="mitigating",
        related_reqs=["REQ-DATA"],
    )
    reg.add_risk(
        "RISK-COACH-02", "Scope creep risk",
        description="Raised by Dennis (mentor). Risk of expanding beyond valves/actuators "
                    "scope before core pipeline is validated.",
        category="scope", source="coach_sessions", source_detail="Dennis mentor session",
        likelihood="medium", impact="medium",
        mitigation="Strict phase scoping; architecture designed for category extension without structural change",
        related_reqs=["QA-3"],
    )
    reg.add_risk(
        "RISK-COACH-03", "Azure tool constraints",
        description="Client mandates Azure deployment. Some tools/services have limitations "
                    "that may affect architecture decisions (GPU availability, service quotas).",
        category="technical", source="coach_sessions", source_detail="Cory SES session",
        likelihood="medium", impact="medium",
        mitigation="Single App Service deployment chosen to minimize Azure operational complexity",
        related_arch=["AD-6"],
    )
    reg.add_risk(
        "RISK-COACH-04", "Measurement validity for AI effectiveness",
        description="Christian (AI coach) raised: How do you measure whether AI actually helps? "
                    "Need rigorous before/after comparison, not just 'we used AI'.",
        category="measurement", source="coach_sessions", source_detail="Christian AI coach session",
        likelihood="medium", impact="high",
        mitigation="SES measurement system tracks tokens, cost, latency, human review rate, correction rate per agent. "
                   "Prompt regression testing validates quality over time.",
        related_reqs=["REQ-SES"],
    )
    reg.add_risk(
        "RISK-COACH-05", "Model selection uncertainty",
        description="Raised across multiple sessions. ML model selection is the second open "
                    "question after threshold. Hybrid approach is tentative (ADR-1 status: Tentative).",
        category="technical", source="coach_sessions", source_detail="Christian, Cory sessions",
        likelihood="medium", impact="high",
        mitigation="ADR-1 hybrid approach with clear trigger conditions for switching to pure ML or pure rules",
        related_arch=["ADR-1"],
    )

    # === Project Management Risks ===
    reg.add_risk(
        "RISK-PM-01", "Capstone timeline constraint",
        description="5-person team, Spring-Fall 2026. Must be prototypable within semester. "
                    "Operational complexity must stay within team capacity.",
        category="schedule", source="project_constraints",
        likelihood="low", impact="high",
        mitigation="Architecture favors simplicity (single App Service, internal interfaces). "
                   "SES agents automate repetitive tasks to free team capacity.",
    )
    reg.add_risk(
        "RISK-PM-02", "Integration dependency on Jake (PIMS schema)",
        description="Writeback design assumes staging table schema that Jake hasn't delivered. "
                    "P1-C contract is a critical path dependency.",
        category="dependency", source="architecture_report", source_detail="Constraint table, Refinement 4",
        likelihood="high", impact="medium",
        mitigation="Refinement 4 scheduled; team-owned buffer table as fallback",
        owner="Hrishik",
        related_arch=["AD-3", "AD-5"],
    )
    reg.add_risk(
        "RISK-PM-03", "Knowledge loss from manual processes",
        description="Meeting decisions, action items, and architectural rationale get lost "
                    "when captured manually. Risk of inconsistent documentation.",
        category="process", source="ses_design",
        likelihood="medium", impact="medium",
        mitigation="Agentic SE system auto-captures decisions, action items, and commitments from meetings. "
                   "SharedMemory wiki maintains persistent project knowledge.",
        status="mitigating",
    )

    return reg
