"""
WBS Updater — maintains /sprint/wbs.md (work breakdown structure)
synced to Jira state.

When tickets close → WBS updates. When new tickets created → appear
under correct epic.

Triggered by: Jira webhook (ticket state change), cron
Outputs: updated wbs.md committed to repo
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.wbs_updater")


class WBSUpdaterAgent(BaseAgent):
    """Keeps the work breakdown structure in sync with Jira."""

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="wbs_updater", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        jira = self.mcp.get("jira")
        if not jira:
            return AgentResult(
                agent=self.name, success=True,
                outputs=[AgentOutput(
                    output_type="wbs_skipped",
                    description="Jira not configured",
                )],
            )

        sprint_state = jira.get_sprint_state()
        if not sprint_state.get("ok"):
            return AgentResult(
                agent=self.name, success=False,
                errors=[sprint_state.get("error", "Failed to fetch sprint")],
            )

        wbs_content = self._build_wbs(sprint_state.get("issues", []))

        outputs = []
        bitbucket = self.mcp.get("bitbucket")
        if bitbucket:
            bitbucket.commit_file(
                file_path="sprint/wbs.md",
                content=wbs_content,
                message=f"Update WBS ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})",
                agent_name=self.name,
            )
            outputs.append(AgentOutput(
                output_type="file_committed",
                description="WBS updated from Jira sprint state",
                reference="sprint/wbs.md",
            ))

        return AgentResult(agent=self.name, success=True, outputs=outputs)

    def _build_wbs(self, issues: list[dict]) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"# Work Breakdown Structure\n",
            f"_Last synced: {now}_\n",
        ]

        by_status: dict[str, list] = {}
        for issue in issues:
            status = issue.get("status", "Unknown")
            by_status.setdefault(status, []).append(issue)

        for status in ["To Do", "In Progress", "In Review", "Done"]:
            items = by_status.get(status, [])
            lines.append(f"\n## {status} ({len(items)})\n")
            for item in items:
                assignee = item.get("assignee", "unassigned")
                lines.append(
                    f"- [{item.get('key', '?')}] {item.get('summary', '?')} "
                    f"({item.get('priority', '?')}) — {assignee}"
                )

        return "\n".join(lines)
