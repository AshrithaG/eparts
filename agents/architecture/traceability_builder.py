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
        """Build the traceability matrix from wiki data and Jira."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        header = (
            "# Traceability Matrix\n\n"
            f"_Last updated: {now}_\n\n"
            "| REQ ID | Description | Jira Ticket | Test Status | Last Updated |\n"
            "|--------|-------------|-------------|-------------|-------------|\n"
        )

        rows = []
        try:
            reqs = self.wiki.list_namespace("requirements")
            jira = self.mcp.get("jira")
            jira_issues = {}

            if jira and getattr(jira, "is_configured", False):
                result = jira.search_issues(
                    jql=f"project = {jira._project_key} AND labels = requirements"
                )
                if result.get("ok"):
                    for iss in result.get("issues", []):
                        jira_issues[iss["summary"].lower()] = iss["key"]

            for entry in reqs if reqs else []:
                if not isinstance(entry, dict):
                    continue
                val = entry.get("value", {})
                if isinstance(val, str):
                    continue
                req_id = entry.get("key", "?")
                text = str(val.get("text", ""))[:60]
                updated = entry.get("updated_at", "")[:10]

                ticket = "—"
                for k, v in jira_issues.items():
                    if req_id.lower() in k or text[:20].lower() in k:
                        ticket = v
                        break

                rows.append(f"| {req_id} | {text} | {ticket} | pending | {updated} |")
        except Exception as exc:
            rows.append(f"| — | Error building matrix: {exc} | — | — | — |")

        if not rows:
            rows.append("| — | No requirements tracked yet | — | — | — |")

        return header + "\n".join(rows) + "\n"
