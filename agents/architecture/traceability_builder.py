"""
Traceability Builder — maintains the living traceability matrix.

Maintains /docs/traceability.md — a living matrix:
  REQ ID | Description | Jira ticket | PR | Test status | Last updated
Updated on every relevant commit.

Triggered by: commit event, Jira webhook, PR event
Outputs: updated traceability.md
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.traceability_builder")


class TraceabilityBuilderAgent(BaseAgent):
    """Maintains the REQ → Jira → PR → Test traceability matrix."""

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="traceability_builder", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # In production: read current traceability.md from Bitbucket,
        # scan for new REQs, Jira tickets, PRs, and test results,
        # then rebuild the matrix
        matrix = self._build_matrix(trigger)

        outputs = []
        bitbucket = self.mcp.get("bitbucket")
        if bitbucket and matrix:
            bitbucket.commit_file(
                file_path="docs/traceability.md",
                content=matrix,
                message=f"Update traceability matrix ({date})",
                agent_name=self.name,
            )
            outputs.append(AgentOutput(
                output_type="file_committed",
                description="Traceability matrix updated",
                reference="docs/traceability.md",
            ))

        return AgentResult(agent=self.name, success=True, outputs=outputs)

    def _build_matrix(self, trigger: AgentTrigger) -> str:
        """
        Build the traceability matrix markdown table.
        In production: queries Bitbucket for REQs, Jira for tickets,
        and test results for coverage.
        """
        header = (
            "# Traceability Matrix\n\n"
            f"_Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_\n\n"
            "| REQ ID | Description | Jira Ticket | PR | Test Status | Last Updated |\n"
            "|--------|-------------|-------------|-----|-------------|-------------|\n"
        )
        # Placeholder rows would be populated from actual data
        return header
