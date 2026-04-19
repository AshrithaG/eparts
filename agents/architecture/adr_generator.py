"""
ADR Generator — auto-drafts Architecture Decision Records when
significant technical decisions are detected in transcripts or Slack.

Committed as PR — never direct commit. Requires approval.
Specifically tracks open decisions: threshold, alpha, routing, PIMS schema.

Triggered by: transcript commit, Slack decision event
Outputs: ADR.md file committed as PR
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.adr_generator")


class ADRGeneratorAgent(BaseAgent):
    """Auto-drafts ADRs from detected decisions, submitted as PRs."""

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="adr_generator", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        decisions = trigger.metadata.get("decisions", [])
        date = trigger.metadata.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

        if not decisions:
            return AgentResult(
                agent=self.name, success=True,
                outputs=[AgentOutput(
                    output_type="adr_skipped",
                    description="No decisions to generate ADRs for",
                )],
            )

        outputs = []
        bitbucket = self.mcp.get("bitbucket")

        for decision in decisions:
            adr_content = self._generate_adr(decision, date)
            adr_id = f"ADR-{date}-{decision.get('text', 'untitled')[:30].replace(' ', '-').lower()}"
            filename = f"docs/adrs/{adr_id}.md"

            if bitbucket:
                branch_name = f"adr/{adr_id}"
                bitbucket.create_branch(branch_name)
                bitbucket.commit_file(
                    file_path=filename,
                    content=adr_content,
                    message=f"Draft ADR: {decision.get('text', '')[:60]}",
                    branch=branch_name,
                    agent_name=self.name,
                )
                pr_result = bitbucket.open_pr(
                    title=f"[ADR] {decision.get('text', '')[:80]}",
                    source_branch=branch_name,
                    description=f"Auto-drafted ADR from {date} meeting.\n\n"
                               f"Decision: {decision.get('text', '')}\n"
                               f"Context: {decision.get('context', '')}",
                )
                if pr_result.get("ok"):
                    outputs.append(AgentOutput(
                        output_type="pr_opened",
                        description=f"ADR PR opened: {decision.get('text', '')[:60]}",
                        reference=pr_result.get("pr_url", ""),
                    ))

        return AgentResult(
            agent=self.name, success=True, outputs=outputs,
            requires_human_review=True,
            review_items=[{"type": "adr_review", "count": len(decisions)}],
        )

    def _generate_adr(self, decision: dict, date: str) -> str:
        prompt = f"""Generate an Architecture Decision Record (ADR) in markdown format.

Decision: {decision.get('text', '')}
Context: {decision.get('context', '')}
Date: {date}
Project: eParts ML Product Data Ingestion Platform

Use this ADR template:
# ADR: [Title]

## Status
Proposed

## Context
[Why this decision was needed]

## Decision
[What was decided]

## Options Considered
1. [Option A] — [pros/cons]
2. [Option B] — [pros/cons]

## Consequences
- [Positive consequences]
- [Negative consequences / risks]

## Reconsideration Triggers
- [When should this decision be revisited]

Generate a thorough, specific ADR. Reference eParts context where relevant."""

        return self.call_claude(prompt)
