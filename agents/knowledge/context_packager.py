"""
Context Packager — runs Mon 7am (1hr before typical mentor meeting).

Reads week's commits, open REQs, stale items, pending ADRs.
Produces 1-page briefing. Slack-pinned.

Triggered by: cron_monday_8am (runs 1hr before meetings)
Outputs: context briefing posted to Slack
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.context_packager")


class ContextPackagerAgent(BaseAgent):
    """Packages relevant project context into a concise briefing."""

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="context_packager", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        context = self._gather_context()
        briefing = self._generate_briefing(context)
        outputs = []

        slack = self.mcp.get("slack")
        if slack:
            result = slack.send_message(briefing)
            if result.get("ok"):
                slack.pin_message(channel=result["channel"], timestamp=result["ts"])
                outputs.append(AgentOutput(
                    output_type="message_sent",
                    description="Weekly context briefing posted and pinned",
                ))

        return AgentResult(agent=self.name, success=True, outputs=outputs)

    def _gather_context(self) -> dict:
        """Gather context from wiki, Jira, and event bus."""
        ctx = {
            "week_start": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "commits": [],
            "open_reqs": [],
            "stale_items": [],
            "pending_adrs": [],
            "concerns": [],
            "sprint_status": {},
        }

        # Jira board state
        jira = self.mcp.get("jira")
        if jira and getattr(jira, "is_configured", False):
            board = jira.get_board_status()
            if board.get("ok"):
                ctx["sprint_status"] = board.get("by_status", {})
                ctx["open_reqs"] = [
                    i for i in board.get("recent_issues", [])
                    if i.get("status") != "Done"
                ]

        # Wiki data
        try:
            concerns = self.wiki.list_namespace("concerns")
            ctx["concerns"] = concerns[-5:] if concerns else []

            adrs = self.wiki.list_namespace("architecture")
            ctx["pending_adrs"] = [
                a for a in (adrs or [])
                if isinstance(a, dict) and "drift" in str(a.get("key", "")).lower()
            ][-5:]
        except Exception:
            pass

        # Recent events
        try:
            events = self.events.get_pending_events(limit=15)
            ctx["recent_events"] = [
                f"{e['event_type']} from {e['source_agent']}" for e in events
            ]
        except Exception:
            pass

        return ctx

    def _generate_briefing(self, context: dict) -> str:
        prompt = f"""Generate a concise weekly context briefing for the Pimsie Supreme team.
Today: {context['week_start']}

Available context:
- Commits this week: {len(context['commits'])}
- Open requirements: {len(context['open_reqs'])}
- Stale items: {len(context['stale_items'])}
- Pending ADRs: {len(context['pending_adrs'])}

Format as a brief Slack message (under 500 words) with sections:
1. This Week's Progress
2. Open Items Needing Attention
3. Upcoming Deadlines
4. Preparation Notes for Meetings"""

        return self.call_claude(prompt)
