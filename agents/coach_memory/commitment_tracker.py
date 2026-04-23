"""
Commitment Tracker — extracts and tracks commitments from coach sessions.

Cross-checks commitments against Bitbucket commits and Jira closures to
verify delivery status. Maintains: commitment → deadline → status → evidence.

Triggered by: coach_transcript event (after session_memory processes)
Outputs: updated commitment records in SQLite, Slack alerts for overdue items
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent
from agents.coach_memory.session_memory import DB_PATH, init_db

logger = logging.getLogger("agent.commitment_tracker")


class CommitmentTrackerAgent(BaseAgent):
    """
    Tracks commitments made in coach/mentor sessions and cross-references
    them against actual deliverables in Bitbucket and Jira.
    """

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="commitment_tracker", mcp_clients=mcp_clients)
        self._db = init_db()

    def run(self, trigger: AgentTrigger) -> AgentResult:
        outputs = []

        # Check for overdue commitments
        overdue = self._find_overdue_commitments()
        if overdue:
            alert_text = self._format_overdue_alert(overdue)
            slack = self.mcp.get("slack")
            if slack:
                slack.send_alert(alert_text)
                outputs.append(AgentOutput(
                    output_type="message_sent",
                    description=f"Overdue commitment alert: {len(overdue)} items",
                ))

        # If this was triggered by a transcript, extract new commitments
        if trigger.trigger_type in ("coach_transcript", "transcript"):
            pipeline_ctx = trigger.metadata.get("pipeline_context", {})
            session_id = (
                trigger.metadata.get("session_id")
                or pipeline_ctx.get("session_id")
            )
            if session_id:
                new_count = self._count_commitments_for_session(session_id)
                outputs.append(AgentOutput(
                    output_type="commitments_tracked",
                    description=f"Session {session_id}: {new_count} commitments tracked",
                    reference=session_id,
                ))
            else:
                total = self._db.execute("SELECT COUNT(*) as cnt FROM commitments").fetchone()["cnt"]
                outputs.append(AgentOutput(
                    output_type="commitments_tracked",
                    description=f"Total commitments tracked: {total}",
                ))

        # Cross-check delivered commitments
        verified = self._verify_deliveries()
        if verified:
            outputs.append(AgentOutput(
                output_type="commitments_verified",
                description=f"{len(verified)} commitments verified as delivered",
            ))

        return AgentResult(
            agent=self.name,
            success=True,
            outputs=outputs,
        )

    def _find_overdue_commitments(self) -> list[dict]:
        """Find open commitments past their deadline."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = self._db.execute(
            "SELECT c.*, s.date as session_date FROM commitments c "
            "JOIN sessions s ON c.session_id = s.session_id "
            "WHERE c.status = 'open' AND c.deadline != '' AND c.deadline < ? "
            "ORDER BY c.deadline",
            (today,),
        ).fetchall()
        return [dict(r) for r in rows]

    def _count_commitments_for_session(self, session_id: str) -> int:
        row = self._db.execute(
            "SELECT COUNT(*) as cnt FROM commitments WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    def _verify_deliveries(self) -> list[dict]:
        """
        Cross-check open commitments against Bitbucket and Jira.
        Marks commitments as 'delivered' when evidence is found.
        """
        verified = []
        bitbucket = self.mcp.get("bitbucket")
        if not bitbucket:
            return verified

        open_commitments = self._db.execute(
            "SELECT * FROM commitments WHERE status = 'open'"
        ).fetchall()

        for commitment in open_commitments:
            commitment = dict(commitment)
            evidence = self._search_for_evidence(commitment, bitbucket)
            if evidence:
                self._db.execute(
                    "UPDATE commitments SET status = 'delivered', evidence_link = ? WHERE id = ?",
                    (evidence, commitment["id"]),
                )
                self._db.commit()
                verified.append(commitment)

        return verified

    def _search_for_evidence(self, commitment: dict, bitbucket: Any) -> str | None:
        """
        Search for evidence that a commitment was delivered.
        Returns an evidence link if found, None otherwise.
        Placeholder: in production, this searches Bitbucket commits
        and Jira tickets for keywords from the commitment text.
        """
        # TODO: implement Bitbucket commit search and Jira ticket search
        # For now, return None (no auto-verification)
        return None

    def mark_delivered(self, commitment_id: int, evidence_link: str) -> bool:
        """Manually mark a commitment as delivered with evidence."""
        self._db.execute(
            "UPDATE commitments SET status = 'delivered', evidence_link = ? WHERE id = ?",
            (evidence_link, commitment_id),
        )
        self._db.commit()
        return True

    def mark_missed(self, commitment_id: int) -> bool:
        """Mark a commitment as missed."""
        self._db.execute(
            "UPDATE commitments SET status = 'missed' WHERE id = ?",
            (commitment_id,),
        )
        self._db.commit()
        return True

    def _format_overdue_alert(self, overdue: list[dict]) -> str:
        lines = ["*Overdue Commitments Alert*\n"]
        for c in overdue:
            lines.append(
                f"• *{c['commitment_text']}*\n"
                f"  Owner: {c['owner']} | Deadline: {c['deadline']} | "
                f"From session: {c['session_date']}"
            )
        return "\n".join(lines)
