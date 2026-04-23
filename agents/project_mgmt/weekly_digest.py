"""
Weekly Digest Agent — runs every Friday 6pm.

Reads all commits that week and produces a digest:
  - Decisions made this week
  - Requirements changes (added/modified)
  - Sprint health (open/closed tickets, velocity)
  - Architecture (drift detected/resolved)
  - Next week preview

Published to Confluence + Slack.

Triggered by: cron_friday_6pm
Outputs: digest posted to Slack and Confluence
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.weekly_digest")


class WeeklyDigestAgent(BaseAgent):
    """Generates and publishes the weekly project digest."""

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="weekly_digest", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        week_data = self._gather_week_data()
        digest = self._generate_digest(week_data)
        outputs = []

        slack = self.mcp.get("slack")
        if slack:
            slack.send_message(digest)
            outputs.append(AgentOutput(
                output_type="message_sent",
                description="Weekly digest posted to Slack",
            ))

        confluence = self.mcp.get("confluence")
        if confluence:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            confluence.create_page(
                title=f"Weekly Digest — {date}",
                body=digest,
            )
            outputs.append(AgentOutput(
                output_type="page_published",
                description="Weekly digest published to Confluence",
            ))

        return AgentResult(agent=self.name, success=True, outputs=outputs)

    def _gather_week_data(self) -> dict:
        """Gather data from wiki, Jira, and event bus."""
        data = {
            "week_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "commits": [],
            "decisions": [],
            "req_changes": [],
            "sprint_state": {},
            "drift_reports": [],
            "concerns": [],
            "events_this_week": [],
        }

        # Pull from Jira
        jira = self.mcp.get("jira")
        if jira and getattr(jira, "is_configured", False):
            board = jira.get_board_status()
            if board.get("ok"):
                data["sprint_state"] = board.get("by_status", {})
                data["total_issues"] = board.get("total_issues", 0)

        # Pull from SharedMemory wiki
        try:
            decisions = self.wiki.list_namespace("decisions")
            data["decisions"] = decisions[-10:] if decisions else []

            concerns = self.wiki.list_namespace("concerns")
            data["concerns"] = concerns[-5:] if concerns else []

            reqs = self.wiki.list_namespace("requirements_engineering")
            data["req_changes"] = reqs[-5:] if reqs else []
        except Exception:
            pass

        # Pull recent events
        try:
            data["events_this_week"] = [
                {"type": e["event_type"], "agent": e["source_agent"]}
                for e in self.events.get_pending_events(limit=20)
            ]
            data["drift_reports"] = [
                e for e in data["events_this_week"] if e["type"] == "drift_detected"
            ]
        except Exception:
            pass

        return data

    def _generate_digest(self, data: dict) -> str:
        prompt = f"""Generate a weekly project digest for the Pimsie Supreme team.
Week of: {data['week_of']}

Data available:
- Commits: {len(data['commits'])}
- Decisions logged: {len(data['decisions'])}
- Requirement changes: {len(data['req_changes'])}
- Drift reports: {len(data['drift_reports'])}

Format:
## Week of {data['week_of']} — Project Digest
### Decisions Made This Week
### Requirements Changes (added/modified)
### Sprint Health (open/closed tickets, velocity)
### Architecture (drift detected/resolved)
### Next Week Preview

Be concise and actionable. If no data is available for a section, say so briefly."""

        return self.call_claude(prompt)
