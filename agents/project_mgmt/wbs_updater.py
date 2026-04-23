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

        board = jira.get_board_status()
        if not board.get("ok"):
            return AgentResult(
                agent=self.name, success=False,
                errors=[board.get("error", "Failed to fetch board")],
            )

        wbs_content = self._build_wbs(board.get("recent_issues", []))

        outputs = []

        # Deposit WBS to wiki for cross-pipeline access
        self.wiki.put("project_mgmt", "wbs_latest", {
            "content": wbs_content,
            "total_issues": board.get("total_issues", 0),
            "by_status": board.get("by_status", {}),
        }, agent=self.name, pipeline="project_mgmt")

        # Commit to repo (prefer GitHub, fall back to Bitbucket)
        repo = self.mcp.get("github") or self.mcp.get("bitbucket")
        if repo:
            repo.commit_file(
                file_path="sprint/wbs.md",
                content=wbs_content,
                message=f"Update WBS ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})",
                agent_name=self.name,
            )
            outputs.append(AgentOutput(
                output_type="file_committed",
                description=f"WBS updated — {board.get('total_issues', 0)} issues tracked",
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
