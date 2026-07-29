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
        CREATE TABLE IF NOT EXISTS risk_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            risk_id TEXT NOT NULL,
            reviewer TEXT NOT NULL,
            old_status TEXT NOT NULL,
            new_status TEXT NOT NULL,
            notes TEXT DEFAULT '',
            reviewed_at TEXT NOT NULL,
            FOREIGN KEY (risk_id) REFERENCES risks(id)
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

    def review_risk(
        self,
        risk_id: str,
        new_status: str,
        review_notes: str = "",
        reviewer: str = "team",
    ) -> None:
        """Update a risk's status and record a review entry."""
        row = self._db.execute(
            "SELECT status FROM risks WHERE id = ?", (risk_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Risk {risk_id} not found")
        old_status = row["status"]
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            "INSERT INTO risk_reviews (risk_id, reviewer, old_status, new_status, notes, reviewed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (risk_id, reviewer, old_status, new_status, review_notes, now),
        )
        self._db.execute(
            "UPDATE risks SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, now, risk_id),
        )
        self._db.commit()

    def get_review_history(self, risk_id: str) -> list[dict[str, Any]]:
        """Return all review entries for a given risk, oldest first."""
        rows = self._db.execute(
            "SELECT * FROM risk_reviews WHERE risk_id = ? ORDER BY reviewed_at",
            (risk_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def due_for_review(self, days: int = 14) -> list[dict[str, Any]]:
        """Return risks whose updated_at is older than *days* days."""
        cutoff = datetime.now(timezone.utc).isoformat()
        rows = self._db.execute(
            "SELECT * FROM risks "
            "WHERE julianday(?) - julianday(updated_at) > ? "
            "ORDER BY updated_at",
            (cutoff, days),
        ).fetchall()
        return [dict(r) for r in rows]


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
        description="IF the 0.85 confidence threshold is not calibrated with empirical data "
                    "THEN the review queue either overwhelms the catalog team (threshold too high) "
                    "or lets incorrect data into PIMS (threshold too low) "
                    "RESULTING IN no labor savings or data quality degradation.",
        category="technical", source="architecture_report", source_detail="Section 5.4 Risk 1",
        likelihood="high", impact="high",
        mitigation="Refinement 1: Run prototype on >=200 labeled submissions, compute precision-recall curves",
        contingency="Improve model or renegotiate accuracy target with Harsha",
        related_reqs=["QA-1", "FR-4"], related_arch=["AD-4", "routing"],
    )
    reg.add_risk(
        "RISK-ARCH-02", "Insufficient training data (<200 labeled examples)",
        description="IF fewer than 200 labeled examples are available for training "
                    "THEN the embedding layer will be undertrained and the hybrid approach "
                    "falls back to pure rules with limited coverage (~40-60%) "
                    "RESULTING IN degraded prediction accuracy and increased manual review burden.",
        category="technical", source="architecture_report", source_detail="Section 5.4 Risk 2",
        likelihood="medium", impact="high",
        mitigation="Secure labeled data from eParts; augment with synthetic examples if needed",
        contingency="Fall back to pure rule engine (ADR-1 Alt A trigger)",
        related_reqs=["FR-3"], related_arch=["ADR-1", "prediction"],
    )
    reg.add_risk(
        "RISK-ARCH-03", "PIMS staging schema incompatibility (P1-C pending)",
        description="IF Jake does not deliver the P1-C schema or staging tables use incompatible columns "
                    "THEN the writeback mechanism requires redesign "
                    "RESULTING IN schedule delays and potential data integration failures.",
        category="technical", source="architecture_report", source_detail="Section 5.4 Risk 3",
        likelihood="medium", impact="high",
        mitigation="Refinement 4: Map P1-C columns to canonical schema; integration-test 10 sample records",
        contingency="Team-owned buffer table if schema incompatible",
        related_reqs=["FR-6"], related_arch=["AD-3", "AD-5", "writeback"],
    )

    # Architecture sensitivity points
    reg.add_risk(
        "RISK-ARCH-04", "Alpha weighting sensitivity in hybrid scoring",
        description="IF small tuning errors occur in alpha weighting (currently 0.7) "
                    "THEN routing behavior changes disproportionately, suppressing the more accurate signal source "
                    "RESULTING IN misrouted items and unreliable confidence scores.",
        category="technical", source="architecture_report", source_detail="Section 5.4 Sensitivity 1",
        likelihood="medium", impact="medium",
        mitigation="Refinement 3: Sweep alpha 0.3-0.9; measure ECE, precision, coverage",
        related_reqs=["QA-1"], related_arch=["ADR-1"],
    )
    reg.add_risk(
        "RISK-ARCH-05", "Attribute correlation invalidates per-attribute routing",
        description="IF correlated attributes are reviewed independently "
                    "THEN inconsistent records are produced when cross-attribute errors exceed 30% "
                    "RESULTING IN need to switch from per-attribute to per-record routing, requiring redesign.",
        category="technical", source="architecture_report", source_detail="Section 5.4 Sensitivity 2",
        likelihood="low", impact="high",
        mitigation="Refinement 2: Pairwise mutual information analysis on labeled data",
        contingency="Switch to per-record routing (Section 4.2 Alt B)",
        related_reqs=["QA-1", "FR-4"], related_arch=["routing"],
    )
    reg.add_risk(
        "RISK-ARCH-06", "Catalog team capacity vs review volume",
        description="IF per-attribute routing still produces too many review items "
                    "THEN the 1.5 + 3 FTE catalog team cannot handle the volume "
                    "RESULTING IN no labor savings and failure of the core value proposition.",
        category="business", source="architecture_report", source_detail="Section 5.4 Sensitivity 3",
        likelihood="medium", impact="high",
        mitigation="Measure actual review volume in prototype; adjust threshold iteratively",
        contingency="Lower threshold (accepting more accuracy risk) or invest in reviewer tooling",
        related_reqs=["QA-1"], related_arch=["routing", "review"],
    )

    # Unresolved items from architecture
    reg.add_risk(
        "RISK-ARCH-07", "Drift detection metrics and baselines undefined",
        description="IF baseline metrics, alert thresholds, and feedback loops are not defined before deployment "
                    "THEN model drift will go undetected "
                    "RESULTING IN silent accuracy degradation and no trigger for retraining.",
        category="technical", source="architecture_report", source_detail="Section 5.4 Unresolved 1",
        likelihood="high", impact="medium",
        mitigation="Define baseline metrics before prototype; SES measurement system can track these",
        related_reqs=["QA-5"], related_arch=["observability"],
    )
    reg.add_risk(
        "RISK-ARCH-08", "Human review interface design not decided",
        description="IF the reviewer walkthrough reveals that tabular export is insufficient for review tasks "
                    "THEN a custom review UI must be added to scope "
                    "RESULTING IN scope expansion, additional development effort, and potential schedule delays.",
        category="ux", source="architecture_report", source_detail="Section 5.4 Unresolved 3",
        likelihood="medium", impact="medium",
        mitigation="Refinement 5: Present 30 sample items to Brian/Dewey; measure time and accuracy",
        contingency="Renegotiate custom UI scope if needed",
        related_reqs=["FR-5"], related_arch=["review"],
    )

    reg.add_risk(
        "RISK-ARCH-09", "ETIM release pin leaves the catalog progressively stale",
        description="IF the client's suppliers begin publishing against ETIM 11.0 while the platform "
                    "remains pinned to release 10.0 EI (constraint C-4) "
                    "THEN new classes, features and values are unavailable to the matcher "
                    "RESULTING IN affected products falling to ETIM Other handling or manual review, "
                    "and the catalog drifting further from the standard over time.",
        category="dependency", source="architecture_report",
        source_detail="ADR-020 Consequences: deliberately accepted, revisit before production transition",
        likelihood="medium", impact="medium",
        mitigation="Release pinned explicitly as constraint C-4 rather than left unspecified. Every ETIM "
                   "reference row, the interpretation table and the PIMS writeback key all carry "
                   "etim_release_id (ADR-013/014/017), so each published value names the release it was "
                   "matched under and provenance survives. The loader rejects an archive whose release "
                   "does not match the declared one, which is what stops an 11.0 archive being loaded "
                   "into a 10.0-pinned system by accident.",
        contingency="Un-pinning is a change request against C-4, not a gap to fill quietly. The governed "
                    "upgrade path (load releases side by side, diff, re-match affected products through a "
                    "review queue) is the shape that work would take.",
        status="mitigating",
        related_reqs=["FR-10", "HLR-6", "FR-9"],
        related_arch=["ADR-020", "ADR-013", "ADR-014", "ADR-017", "C-4"],
    )

    # === Coach Session Concerns ===
    reg.add_risk(
        "RISK-COACH-01", "Data access delay blocking ML development",
        description="IF client data is not available for model training "
                    "THEN ML development stalls and the team cannot validate the hybrid approach "
                    "RESULTING IN schedule delays and inability to meet prototype milestones.",
        category="schedule", source="coach_sessions", source_detail="Cory, Dennis, Ben sessions",
        likelihood="high", impact="high",
        mitigation="Data received ~Feb 22; team started basic model tests. Continue pressing for complete dataset.",
        status="mitigating",
        related_reqs=["REQ-DATA"],
    )
    reg.add_risk(
        "RISK-COACH-02", "Scope creep risk",
        description="IF the team expands beyond valves/actuators scope before the core pipeline is validated "
                    "THEN development effort is diluted across unvalidated categories "
                    "RESULTING IN an incomplete core pipeline and missed delivery deadlines.",
        category="scope", source="coach_sessions", source_detail="Dennis mentor session",
        likelihood="medium", impact="medium",
        mitigation="Strict phase scoping; architecture designed for category extension without structural change",
        related_reqs=["QA-3"],
    )
    reg.add_risk(
        "RISK-COACH-03", "Azure tool constraints",
        description="IF Azure platform limitations (GPU availability, service quotas) conflict with architecture needs "
                    "THEN design decisions must be reworked for the constrained environment "
                    "RESULTING IN reduced model performance or additional engineering workarounds.",
        category="technical", source="coach_sessions", source_detail="Cory SES session",
        likelihood="medium", impact="medium",
        mitigation="Single App Service deployment chosen to minimize Azure operational complexity",
        related_arch=["AD-6"],
    )
    reg.add_risk(
        "RISK-COACH-04", "Measurement validity for AI effectiveness",
        description="IF AI effectiveness is not measured with rigorous before/after comparisons "
                    "THEN the team cannot demonstrate genuine AI-driven improvement "
                    "RESULTING IN weak capstone evaluation and inability to justify the AI approach.",
        category="measurement", source="coach_sessions", source_detail="Christian AI coach session",
        likelihood="medium", impact="high",
        mitigation="SES measurement system tracks tokens, cost, latency, human review rate, correction rate per agent. "
                   "Prompt regression testing validates quality over time.",
        related_reqs=["REQ-SES"],
    )
    reg.add_risk(
        "RISK-COACH-05", "Model selection uncertainty",
        description="IF the ML model selection remains unresolved and the hybrid approach (ADR-1) is not validated "
                    "THEN the prediction pipeline lacks a stable foundation "
                    "RESULTING IN rework risk and delayed confidence in system accuracy.",
        category="technical", source="coach_sessions", source_detail="Christian, Cory sessions",
        likelihood="medium", impact="high",
        mitigation="ADR-1 hybrid approach with clear trigger conditions for switching to pure ML or pure rules",
        related_arch=["ADR-1"],
    )

    # === Project Management Risks ===
    reg.add_risk(
        "RISK-PM-01", "Capstone timeline constraint",
        description="IF the 5-person team cannot prototype within the Spring-Fall 2026 semester "
                    "THEN operational complexity exceeds team capacity "
                    "RESULTING IN incomplete deliverables and a failed capstone milestone.",
        category="schedule", source="project_constraints",
        likelihood="low", impact="high",
        mitigation="Architecture favors simplicity (single App Service, internal interfaces). "
                   "SES agents automate repetitive tasks to free team capacity.",
    )
    reg.add_risk(
        "RISK-PM-02", "Integration dependency on Jake (PIMS schema)",
        description="IF Jake does not deliver the P1-C staging table schema on time "
                    "THEN the writeback mechanism cannot be implemented against the real target "
                    "RESULTING IN critical-path schedule slip and potential redesign of the integration layer.",
        category="dependency", source="architecture_report", source_detail="Constraint table, Refinement 4",
        likelihood="high", impact="medium",
        mitigation="Refinement 4 scheduled; team-owned buffer table as fallback",
        owner="Hrishik",
        related_arch=["AD-3", "AD-5"],
    )
    reg.add_risk(
        "RISK-PM-03", "Knowledge loss from manual processes",
        description="IF meeting decisions, action items, and rationale are captured manually "
                    "THEN information is lost or inconsistently documented across artifacts "
                    "RESULTING IN duplicated effort, contradictory decisions, and knowledge gaps.",
        category="process", source="ses_design",
        likelihood="medium", impact="medium",
        mitigation="Agentic SE system auto-captures decisions, action items, and commitments from meetings. "
                   "SharedMemory wiki maintains persistent project knowledge.",
        status="mitigating",
    )

    # === Health & Team Risks ===
    reg.add_risk(
        "RISK-H1", "Team burnout from capstone + coursework overlap",
        description="IF team members are overloaded with concurrent capstone and coursework demands "
                    "THEN productivity and code quality decline as fatigue accumulates "
                    "RESULTING IN missed deadlines, increased defect rates, and potential team attrition.",
        category="health", source="team_assessment",
        likelihood="high", impact="high",
        mitigation="Establish sustainable sprint cadence; enforce work-hour limits; rotate intensive tasks across members.",
    )
    reg.add_risk(
        "RISK-H2", "Single point of failure — key person unavailable",
        description="IF a key team member becomes unavailable (illness, emergency, dropout) "
                    "THEN critical knowledge and in-progress work are inaccessible "
                    "RESULTING IN blocked deliverables and schedule delays until knowledge is reconstructed.",
        category="team", source="team_assessment",
        likelihood="high", impact="high",
        mitigation="Cross-train on all subsystems; maintain pair-programming rotation; document decisions in SharedMemory.",
    )
    reg.add_risk(
        "RISK-H3", "Communication gaps between distributed team members",
        description="IF distributed team members have infrequent or asynchronous-only communication "
                    "THEN misalignments on requirements, design, and priorities go undetected "
                    "RESULTING IN integration conflicts, rework, and divergent implementations.",
        category="team", source="team_assessment",
        likelihood="medium", impact="medium",
        mitigation="Weekly sync meetings; shared Slack channel for async updates; meeting summaries auto-generated by SES.",
    )

    return reg
