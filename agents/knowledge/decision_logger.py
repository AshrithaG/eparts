"""
Decision Logger — extracts decisions from all sources and maintains
a running log at /minutes/decisions.log.md.

Each entry: decision, source, date, people present.

Triggered by: transcript commit, Slack decision event
Outputs: updated decisions.log.md
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.decision_logger")


class DecisionLoggerAgent(BaseAgent):
    """Maintains a running log of all decisions from all sources."""

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="decision_logger", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        pipeline_ctx = trigger.metadata.get("pipeline_context", {})
        decisions = (
            trigger.metadata.get("decisions", [])
            or pipeline_ctx.get("decisions", [])
            or pipeline_ctx.get("potential_decisions", [])
        )
        date = (
            trigger.metadata.get("date")
            or pipeline_ctx.get("meeting_date")
            or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        )
        source = trigger.source or pipeline_ctx.get("source", "unknown")
        participants = (
            trigger.metadata.get("participants", [])
            or pipeline_ctx.get("participants", [])
        )

        if not decisions:
            return AgentResult(
                agent=self.name, success=True,
                outputs=[AgentOutput(
                    output_type="no_decisions",
                    description="No decisions to log",
                )],
            )

        new_entries = []
        for d in decisions:
            entry = (
                f"| {date} | {d.get('text', '')} | {source} | "
                f"{', '.join(participants) if participants else 'unknown'} |"
            )
            new_entries.append(entry)

        repo = self.mcp.get("github") or self.mcp.get("bitbucket")
        outputs = []

        # Deposit each decision to wiki
        for i, d in enumerate(decisions):
            text = d.get("text", d) if isinstance(d, dict) else str(d)
            self.wiki.put("decisions", f"{date}:{i}", {
                "text": text[:300],
                "source": source,
                "date": date,
                "participants": participants,
            }, agent=self.name, pipeline="knowledge")

        if repo:
            log_content = self._build_log_update(new_entries, date)
            repo.commit_file(
                file_path="minutes/decisions.log.md",
                content=log_content,
                message=f"Log {len(decisions)} decision(s) from {date}",
                agent_name=self.name,
            )
            outputs.append(AgentOutput(
                output_type="file_committed",
                description=f"Logged {len(decisions)} decision(s)",
                reference="minutes/decisions.log.md",
            ))

        return AgentResult(agent=self.name, success=True, outputs=outputs)

    def _build_log_update(self, new_entries: list[str], date: str) -> str:
        header = (
            "# Decision Log\n\n"
            "| Date | Decision | Source | People Present |\n"
            "|------|----------|--------|----------------|\n"
        )
        return header + "\n".join(new_entries) + "\n"
