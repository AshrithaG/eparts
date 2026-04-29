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
        # Read items from direct metadata or from pipeline context
        items = trigger.metadata.get("items", [])
        pipeline_ctx = trigger.metadata.get("pipeline_context", {})

        if not items:
            parsed = pipeline_ctx.get("parsed_minutes", {})
            if isinstance(parsed, dict):
                items = parsed.get("action_items", []) + parsed.get("new_requirements", [])

        sprint_focus = trigger.metadata.get("sprint_focus", "ML pipeline integration and threshold calibration")

        if not items:
            return AgentResult(
                agent=self.name,
                success=True,
                outputs=[AgentOutput(
                    output_type="classification_skipped",
                    description="No items to classify (upstream produced none)",
                )],
            )

        # Online: use Claude. Offline: heuristic classification
        if self._settings.has_llm:
            classified = self._classify_items(items, sprint_focus)
        else:
            classified = self._classify_offline(items)

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
                    "message": f"P0 ticket needs approval: {item['text'][:100]}"
                }
                for item in p0_items
            ]

        return AgentResult(
            agent=self.name,
            success=True,
            outputs=outputs,
            requires_human_review=bool(p0_items),
            review_items=review_items,
            data={
                "classified_items": classified,
                "p0_items": p0_items,
                "p1_items": p1_items,
                "p2_items": p2_items,
            },
        )

    def _classify_offline(self, items: list[dict]) -> list[dict]:
        """Heuristic classification when no API key is available."""
        p0_keywords = {"deadline", "demo", "block", "urgent", "critical", "p0", "client"}
        p1_keywords = {"should", "need", "sprint", "important", "this week"}

        classified = []
        for item in items:
            text = (item.get("text", "") or str(item)).lower()
            if any(kw in text for kw in p0_keywords):
                priority = "P0"
            elif any(kw in text for kw in p1_keywords):
                priority = "P1"
            else:
                priority = "P2"
            classified.append({**item, "priority": priority})
        return classified

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

        try:
            raw_response = self.call_claude(prompt)
        except Exception as exc:
            logger.warning(f"LLM call failed, falling back to offline: {exc}")
            return self._classify_offline(items)

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
