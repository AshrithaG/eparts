"""
Minutes Publisher — pushes meeting minutes to Confluence under the
correct parent page (client meeting / mentor meeting / standup).

Bitbucket = permanent record, Confluence = human-readable mirror.

Triggered by: commit to /minutes/
Outputs: Confluence page created or updated
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.minutes_publisher")

PARENT_PAGES = {
    "client": "Client Meetings",
    "coach": "Coach Sessions",
    "mentor": "Mentor Meetings",
    "standup": "Standups",
}


class MinutesPublisherAgent(BaseAgent):
    """Publishes meeting minutes to Confluence."""

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="minutes_publisher", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        minutes_content = trigger.metadata.get("content", "")
        meeting_type = trigger.metadata.get("meeting_type", "standup")
        date = trigger.metadata.get("date", "")
        title = f"{meeting_type.title()} — {date}"

        confluence = self.mcp.get("confluence")
        if not confluence:
            return AgentResult(
                agent=self.name, success=True,
                outputs=[AgentOutput(
                    output_type="publish_skipped",
                    description="Confluence not configured",
                )],
            )

        parent_title = PARENT_PAGES.get(meeting_type, "Meetings")
        parent = confluence.get_page(title=parent_title)
        parent_id = parent.get("page_id") if parent.get("ok") else None

        result = confluence.create_page(
            title=title,
            body=self._markdown_to_confluence(minutes_content),
            parent_id=parent_id,
        )

        outputs = []
        if result.get("ok"):
            outputs.append(AgentOutput(
                output_type="page_published",
                description=f"Minutes published: {title}",
                reference=result.get("page_id", ""),
            ))

        return AgentResult(agent=self.name, success=True, outputs=outputs)

    def _markdown_to_confluence(self, md: str) -> str:
        """Basic markdown to Confluence storage format conversion."""
        html = md.replace("# ", "<h1>").replace("\n## ", "</h1>\n<h2>")
        html = html.replace("- [ ]", "<li>☐").replace("- ", "<li>")
        html = html.replace("**", "<strong>", 1).replace("**", "</strong>", 1)
        return f"<div>{html}</div>"
