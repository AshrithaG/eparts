"""
Doc Generator — auto-updates API docs when endpoints change in a PR.

Triggered by: PR event with API endpoint changes
Outputs: doc updates added to same PR
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.doc_generator")


class DocGeneratorAgent(BaseAgent):
    """Auto-updates API documentation when endpoints change."""

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="doc_generator", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        diff = trigger.metadata.get("diff", "")
        pr_id = trigger.metadata.get("pr_id")

        has_api_changes = any(
            indicator in diff
            for indicator in ["@app.get", "@app.post", "@app.put", "@app.delete", "router."]
        )

        if not has_api_changes:
            return AgentResult(
                agent=self.name, success=True,
                outputs=[AgentOutput(
                    output_type="doc_gen_skipped",
                    description="No API endpoint changes detected",
                )],
            )

        docs = self._generate_api_docs(diff)
        outputs = [AgentOutput(
            output_type="docs_generated",
            description="API documentation updated",
        )]

        bitbucket = self.mcp.get("bitbucket")
        if bitbucket and pr_id:
            bitbucket.add_pr_comment(
                pr_id,
                f"**API Documentation Update**\n\n{docs}"
            )

        return AgentResult(agent=self.name, success=True, outputs=outputs)

    def _generate_api_docs(self, diff: str) -> str:
        prompt = f"""Analyze this code diff and generate API documentation for any new or changed endpoints.

DIFF:
{diff[:6000]}

Format as markdown with: endpoint, method, description, request body, response format, example."""

        return self.call_claude(prompt)
