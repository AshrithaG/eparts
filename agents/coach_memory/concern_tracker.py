"""
Evolving Concern Tracker — tracks Christian's recurring themes across sessions.

Detects patterns like "Christian has flagged monitorability in 3 of 4 sessions"
and surfaces them in briefings and Slack alerts.

Triggered by: coach_transcript event (after session_memory)
Outputs: updated concern frequency data, pattern alerts
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent
from agents.coach_memory.session_memory import DB_PATH, init_db

logger = logging.getLogger("agent.concern_tracker")

KNOWN_THEMES = [
    "monitorability",
    "hitl",
    "evidence",
    "threshold",
    "architecture",
    "process",
    "testing",
    "deployment",
    "scope",
]

RECURRING_THRESHOLD = 2  # flag when a theme appears this many times


class ConcernTrackerAgent(BaseAgent):
    """
    Tracks recurring concerns from coach/mentor sessions and surfaces
    patterns to the team.
    """

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="concern_tracker", mcp_clients=mcp_clients)
        self._db = init_db()

    def run(self, trigger: AgentTrigger) -> AgentResult:
        patterns = self.detect_patterns()
        outputs = []

        recurring = [p for p in patterns if p["times_raised"] >= RECURRING_THRESHOLD]

        if recurring:
            alert = self._format_pattern_alert(recurring)
            slack = self.mcp.get("slack")
            if slack:
                slack.send_message(alert)
                outputs.append(AgentOutput(
                    output_type="message_sent",
                    description=f"Recurring concern patterns: {len(recurring)} themes flagged",
                ))

        outputs.append(AgentOutput(
            output_type="concerns_analyzed",
            description=f"Tracked {len(patterns)} concern themes, "
                       f"{len(recurring)} recurring (≥{RECURRING_THRESHOLD} sessions)",
        ))

        return AgentResult(agent=self.name, success=True, outputs=outputs)

    def detect_patterns(self) -> list[dict]:
        """
        Aggregate concerns by theme, counting how many times each has
        been raised across all sessions.
        """
        rows = self._db.execute(
            "SELECT theme, raised_by, SUM(times_raised) as total_raised, "
            "COUNT(DISTINCT session_id) as session_count, "
            "GROUP_CONCAT(concern_text, ' | ') as all_concerns "
            "FROM concerns "
            "GROUP BY theme, raised_by "
            "ORDER BY total_raised DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_concerns_for_briefing(self) -> str:
        """
        Format recurring concerns for inclusion in pre-meeting briefings.
        Returns a markdown-formatted string.
        """
        patterns = self.detect_patterns()
        if not patterns:
            return "No recurring concerns tracked yet."

        lines = []
        for p in patterns:
            if p["total_raised"] >= RECURRING_THRESHOLD:
                lines.append(
                    f"- **{p['theme']}** — raised {p['total_raised']}x "
                    f"across {p['session_count']} session(s) by {p['raised_by']}"
                )

        if not lines:
            return "No themes have recurred enough to flag (threshold: {RECURRING_THRESHOLD})."

        return "### Recurring Coach Concerns\n" + "\n".join(lines)

    def _format_pattern_alert(self, recurring: list[dict]) -> str:
        lines = ["*Recurring Coach Concern Patterns*\n"]
        for p in recurring:
            lines.append(
                f"• *{p['theme']}* — raised {p['total_raised']}x "
                f"across {p['session_count']} session(s)\n"
                f"  Latest: {p['all_concerns'][:200]}"
            )
        return "\n".join(lines)
