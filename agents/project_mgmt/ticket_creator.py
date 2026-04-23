"""
Jira Ticket Creator — creates tickets from classified P0/P1 items.

From P0/P1 items → creates tickets with description, assignee suggestion
based on domain, priority label, link to source REQ file.
P0 tickets are held in a review queue for 1-click approval.

Triggered by: priority_classifier output, manual
Outputs: Jira tickets created, P0 items queued for approval
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.ticket_creator")

DOMAIN_ASSIGNEES = {
    "ml": "Arjun",
    "pipeline": "Arjun",
    "threshold": "Arjun",
    "alpha": "Arjun",
    "frontend": "Zheliang",
    "ui": "Zheliang",
    "review queue": "Zheliang",
    "pims": "Hrishikesh",
    "database": "Hrishikesh",
    "schema": "Hrishikesh",
    "integration": "Hrishikesh",
    "architecture": "Jaivardhan",
    "monitoring": "Jaivardhan",
    "observability": "Jaivardhan",
    "datadog": "Jaivardhan",
    "ingestion": "Ashritha",
    "agents": "Ashritha",
    "orchestrator": "Ashritha",
}


class TicketCreatorAgent(BaseAgent):
    """Creates Jira tickets from prioritized items."""

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="ticket_creator", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        pipeline_ctx = trigger.metadata.get("pipeline_context", {})
        items = (
            trigger.metadata.get("classified_items", [])
            or pipeline_ctx.get("classified_items", [])
        )
        outputs = []
        review_items = []

        jira = self.mcp.get("jira")
        if not jira:
            return AgentResult(
                agent=self.name,
                success=False,
                errors=["Jira MCP not configured"],
            )

        for item in items:
            priority = item.get("priority", "P2")

            if priority == "P0":
                review_items.append({
                    "type": "p0_ticket_approval",
                    "item": item,
                    "suggested_assignee": self._suggest_assignee(item.get("text", "")),
                    "message": f"P0 ticket needs approval: {item['text']}",
                })
                continue

            # P1 and P2 are auto-created
            assignee = self._suggest_assignee(item.get("text", ""))
            jira_priority = "High" if priority == "P1" else "Medium"

            result = jira.create_issue(
                summary=item.get("text", "Untitled"),
                description=self._build_description(item),
                issue_type="Task",
                labels=[priority, "auto-created"],
                agent_name=self.name,
                priority=jira_priority,
            )

            if result.get("ok"):
                outputs.append(AgentOutput(
                    output_type="ticket_created",
                    description=f"{priority} ticket: {result['key']} — {item.get('text', '')[:60]}",
                    reference=result.get("url", result.get("key", "")),
                ))

        return AgentResult(
            agent=self.name,
            success=True,
            outputs=outputs,
            requires_human_review=bool(review_items),
            review_items=review_items,
        )

    def _suggest_assignee(self, text: str) -> str | None:
        """Suggest an assignee based on domain keywords in the item text."""
        text_lower = text.lower()
        for keyword, assignee in DOMAIN_ASSIGNEES.items():
            if keyword in text_lower:
                return assignee
        return None

    def _build_description(self, item: dict) -> str:
        parts = [
            f"**Auto-created from meeting transcript**\n",
            f"**Item:** {item.get('text', '')}",
            f"**Priority:** {item.get('priority', '?')}",
            f"**Owner:** {item.get('owner', 'unassigned')}",
        ]
        if item.get("rationale"):
            parts.append(f"**Rationale:** {item['rationale']}")
        if item.get("deadline"):
            parts.append(f"**Deadline:** {item['deadline']}")
        if item.get("source_req"):
            parts.append(f"**Source REQ:** {item['source_req']}")
        return "\n".join(parts)
