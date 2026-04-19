"""
Diagram Updater — proposes Mermaid diagram changes as PRs.

Proposes Mermaid diff against architecture.mmd. PR description quotes
the meeting excerpt that triggered each change. Requires 2 team
approvals to merge. Never direct commit.

Triggered by: drift_detector output
Outputs: PR with updated architecture.mmd
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.diagram_updater")


class DiagramUpdaterAgent(BaseAgent):
    """Proposes Mermaid diagram updates as PRs based on detected drift."""

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="diagram_updater", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        drifts = trigger.metadata.get("drifts", [])
        current_diagram = trigger.metadata.get("architecture_mmd", "")
        date = trigger.metadata.get("date", "")

        if not drifts:
            return AgentResult(
                agent=self.name, success=True,
                outputs=[AgentOutput(
                    output_type="diagram_no_update",
                    description="No drift items to update diagram for",
                )],
            )

        drift_descriptions = "\n".join(
            f"- {d.get('description', '')} (evidence: {d.get('evidence', '')})"
            for d in drifts
        )

        updated_diagram = self._propose_update(current_diagram, drift_descriptions)

        outputs = []
        bitbucket = self.mcp.get("bitbucket")
        if bitbucket and updated_diagram:
            branch = f"arch/diagram-update-{date}"
            bitbucket.create_branch(branch)
            bitbucket.commit_file(
                file_path="docs/architecture.mmd",
                content=updated_diagram,
                message=f"Update architecture diagram based on {date} meeting",
                branch=branch,
                agent_name=self.name,
            )
            pr_result = bitbucket.open_pr(
                title=f"[Arch] Diagram update from {date} meeting",
                source_branch=branch,
                description=f"Proposed diagram changes based on detected drift:\n\n{drift_descriptions}",
            )
            if pr_result.get("ok"):
                outputs.append(AgentOutput(
                    output_type="pr_opened",
                    description="Architecture diagram update PR opened",
                    reference=pr_result.get("pr_url", ""),
                ))

        return AgentResult(
            agent=self.name, success=True, outputs=outputs,
            requires_human_review=True,
        )

    def _propose_update(self, current_diagram: str, drift_descriptions: str) -> str:
        prompt = f"""You are updating a Mermaid architecture diagram based on detected changes.

CURRENT DIAGRAM:
{current_diagram if current_diagram else "(no existing diagram)"}

CHANGES DETECTED:
{drift_descriptions}

Generate an updated Mermaid diagram that incorporates these changes.
If no current diagram exists, create a new one based on the changes.
Return ONLY the Mermaid diagram code, no other text."""

        return self.call_claude(prompt)
