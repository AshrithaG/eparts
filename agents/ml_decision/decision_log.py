"""
Open ML Decision Log — SQLite-backed store for unresolved ML architectural decisions.

Maintains a living log of every open ML decision with:
  decision_id, name, current_value, basis (guess/empirical/validated),
  evidence_needed, evidence_so_far, status, source_adr

Pre-populated with ADR-1 through ADR-5 from SW.pdf on first run.

Triggered by: system init (seed), manual
Outputs: decision records in SQLite
"""

from __future__ import annotations

import json
import logging
import sqlite3
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.decision_log")

MEMORY_DIR = Path(__file__).resolve().parent.parent.parent / "memory"
DB_PATH = MEMORY_DIR / "ml_decisions.db"

SEED_DECISIONS = [
    {
        "decision_id": "ADR-1-threshold",
        "name": "Confidence threshold value",
        "current_value": "0.85",
        "basis": "guess",
        "evidence_needed": "Precision-recall curves from ≥200 labeled submissions. Per-attribute accuracy variance.",
        "status": "open",
        "source_adr": "ADR-4",
    },
    {
        "decision_id": "ADR-1-alpha",
        "name": "Hybrid model alpha weighting",
        "current_value": "0.7",
        "basis": "guess",
        "evidence_needed": "Alpha sweep 0.3-0.9 across correction data. ECE, precision, coverage at each value.",
        "status": "open",
        "source_adr": "ADR-1",
    },
    {
        "decision_id": "ADR-2-routing",
        "name": "Per-attribute vs per-record routing",
        "current_value": "per-attribute",
        "basis": "empirical (partial)",
        "evidence_needed": "Pairwise mutual information on labeled data. ≥50 reviewed records inspected for cross-attribute inconsistency.",
        "status": "open",
        "source_adr": "ADR-2",
    },
    {
        "decision_id": "ADR-3-schema",
        "name": "PIMS staging schema compatibility",
        "current_value": "assumed compatible",
        "basis": "unvalidated",
        "evidence_needed": "Jake delivers P1-C schema. Map P1-C columns to canonical schema. Integration test 10 sample records.",
        "status": "blocked",
        "source_adr": "ADR-5",
    },
    {
        "decision_id": "ADR-4-drift",
        "name": "Drift detection baselines and alert thresholds",
        "current_value": "undefined",
        "basis": "guess",
        "evidence_needed": "Baseline confidence distribution from first 2 weeks of production data. Correction rate baseline.",
        "status": "open",
        "source_adr": "ADR-5",
    },
]


def init_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Create the ML decisions SQLite schema and seed if empty."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(textwrap.dedent("""\
        CREATE TABLE IF NOT EXISTS ml_decisions (
            decision_id TEXT PRIMARY KEY,
            name TEXT,
            current_value TEXT,
            basis TEXT,
            evidence_needed TEXT,
            status TEXT,
            source_adr TEXT,
            last_updated TEXT
        );

        CREATE TABLE IF NOT EXISTS evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id TEXT,
            evidence_type TEXT,
            description TEXT,
            value TEXT,
            collected_at TEXT,
            FOREIGN KEY (decision_id) REFERENCES ml_decisions(decision_id)
        );
    """))
    conn.commit()

    existing = conn.execute("SELECT COUNT(*) as cnt FROM ml_decisions").fetchone()
    if existing["cnt"] == 0:
        now = datetime.now(timezone.utc).isoformat()
        for d in SEED_DECISIONS:
            conn.execute(
                "INSERT INTO ml_decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    d["decision_id"], d["name"], d["current_value"],
                    d["basis"], d["evidence_needed"], d["status"],
                    d["source_adr"], now,
                ),
            )
        conn.commit()
        logger.info(f"Seeded {len(SEED_DECISIONS)} ML decisions")

    return conn


class DecisionLogAgent(BaseAgent):
    """
    Maintains the living log of open ML architectural decisions.
    Provides query methods for other agents to check decision state.
    """

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="decision_log", mcp_clients=mcp_clients)
        self._db = init_db()

    def run(self, trigger: AgentTrigger) -> AgentResult:
        """Report current state of all ML decisions."""
        decisions = self.get_all_decisions()
        open_count = sum(1 for d in decisions if d["status"] == "open")
        blocked_count = sum(1 for d in decisions if d["status"] == "blocked")

        return AgentResult(
            agent=self.name,
            success=True,
            outputs=[AgentOutput(
                output_type="decision_status",
                description=f"{len(decisions)} decisions tracked: "
                           f"{open_count} open, {blocked_count} blocked",
            )],
        )

    def get_all_decisions(self) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM ml_decisions ORDER BY decision_id"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_open_decisions(self) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM ml_decisions WHERE status IN ('open', 'blocked') "
            "ORDER BY decision_id"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_decision(self, decision_id: str) -> dict | None:
        row = self._db.execute(
            "SELECT * FROM ml_decisions WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_evidence(self, decision_id: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM evidence WHERE decision_id = ? ORDER BY collected_at DESC",
            (decision_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def add_evidence(
        self,
        decision_id: str,
        evidence_type: str,
        description: str,
        value: dict | str,
    ) -> int:
        """Add a new evidence entry for a decision. Returns the evidence ID."""
        now = datetime.now(timezone.utc).isoformat()
        val = json.dumps(value) if isinstance(value, dict) else value
        cursor = self._db.execute(
            "INSERT INTO evidence (decision_id, evidence_type, description, value, collected_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (decision_id, evidence_type, description, val, now),
        )
        self._db.execute(
            "UPDATE ml_decisions SET last_updated = ? WHERE decision_id = ?",
            (now, decision_id),
        )
        self._db.commit()
        return cursor.lastrowid

    def update_decision(
        self,
        decision_id: str,
        current_value: str | None = None,
        basis: str | None = None,
        status: str | None = None,
    ) -> bool:
        """Update fields on a decision."""
        updates = []
        params = []
        if current_value is not None:
            updates.append("current_value = ?")
            params.append(current_value)
        if basis is not None:
            updates.append("basis = ?")
            params.append(basis)
        if status is not None:
            updates.append("status = ?")
            params.append(status)

        if not updates:
            return False

        updates.append("last_updated = ?")
        params.append(datetime.now(timezone.utc).isoformat())
        params.append(decision_id)

        self._db.execute(
            f"UPDATE ml_decisions SET {', '.join(updates)} WHERE decision_id = ?",
            params,
        )
        self._db.commit()
        return True

    def get_decisions_summary_for_briefing(self) -> str:
        """Format open decisions for inclusion in coach briefings."""
        decisions = self.get_open_decisions()
        if not decisions:
            return "No open ML decisions."

        lines = ["### Open ML Decisions"]
        for d in decisions:
            evidence = self.get_evidence(d["decision_id"])
            lines.append(
                f"- **{d['name']}** (current: {d['current_value']}, basis: {d['basis']})\n"
                f"  Status: {d['status']} | Evidence items: {len(evidence)}\n"
                f"  Needs: {d['evidence_needed'][:100]}"
            )
        return "\n".join(lines)
