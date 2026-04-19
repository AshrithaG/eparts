"""
Priority Classifier — assigns P0/P1/P2 to action items and requirements.

P0 = blocks delivery or client commitment with hard deadline
P1 = important for current sprint, ticket immediately
P2 = future sprint

P0 ticket creation requires human approval gate.

Triggered by: transcript_parser output
Outputs: classified items, P0 items flagged for human review
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.priority_classifier")


class PriorityClassifierAgent(BaseAgent):
    """
    Classifies extracted items by priority using Claude with eParts context.
    P0 items are held for human approval before Jira ticket creation.
    """

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="priority_classifier", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        items = trigger.metadata.get("items", [])
        sprint_focus = trigger.metadata.get("sprint_focus", "ML pipeline integration and threshold calibration")

        if not items:
            return AgentResult(
                agent=self.name,
                success=True,
                outputs=[AgentOutput(
                    output_type="classification_skipped",
                    description="No items to classify",
                )],
            )

        classified = self._classify_items(items, sprint_focus)

        p0_items = [i for i in classified if i.get("priority") == "P0"]
        p1_items = [i for i in classified if i.get("priority") == "P1"]
        p2_items = [i for i in classified if i.get("priority") == "P2"]

        outputs = [
            AgentOutput(
                output_type="items_classified",
                description=f"Classified {len(classified)} items: "
                           f"{len(p0_items)} P0, {len(p1_items)} P1, {len(p2_items)} P2",
            )
        ]

        review_items = []
        if p0_items:
            review_items = [
                {
                    "type": "p0_ticket_approval",
                    "item": item,
                    "message": f"P0 ticket needs approval: {item['text']}"
                }
                for item in p0_items
            ]

        return AgentResult(
            agent=self.name,
            success=True,
            outputs=outputs,
            requires_human_review=bool(p0_items),
            review_items=review_items,
        )

    def _classify_items(self, items: list[dict], sprint_focus: str) -> list[dict]:
        """Send items to Claude for priority classification."""
        items_text = "\n".join(
            f"- {i.get('text', i)} (owner: {i.get('owner', 'unassigned')})"
            for i in items
        )

        prompt = self.load_prompt(
            "priority_classifier.txt",
            items=items_text,
            sprint_focus=sprint_focus,
        )

        raw_response = self.call_claude(prompt)

        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            json_match = re.search(r"\[.*\]", raw_response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            logger.error("Failed to parse priority classification response")
            return items
