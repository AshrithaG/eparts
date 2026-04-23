"""
REQ Extractor — formats new requirements as REQ-XXX.md files and
commits them to /requirements/parsed/ in the repo.

Each file contains: requirement statement, source meeting, date,
priority, open questions.

Triggered by: transcript_parser output with new_requirements
Outputs: REQ-XXX.md files committed to Bitbucket
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.req_extractor")


class ReqExtractorAgent(BaseAgent):
    """Formats and commits requirement documents from parsed transcript data."""

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="req_extractor", mcp_clients=mcp_clients)
        self._next_req_id = 1

    def run(self, trigger: AgentTrigger) -> AgentResult:
        pipeline_ctx = trigger.metadata.get("pipeline_context", {})
        requirements = (
            trigger.metadata.get("requirements", [])
            or pipeline_ctx.get("new_requirements", [])
            or pipeline_ctx.get("classified_items", [])
        )
        date = (
            trigger.metadata.get("date")
            or pipeline_ctx.get("meeting_date")
            or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        )
        meeting_type = trigger.metadata.get("meeting_type", pipeline_ctx.get("meeting_type", "client"))

        if not requirements:
            return AgentResult(
                agent=self.name,
                success=True,
                outputs=[AgentOutput(
                    output_type="extraction_skipped",
                    description="No new requirements to extract",
                )],
            )

        outputs = []
        repo = self.mcp.get("github") or self.mcp.get("bitbucket")

        for req in requirements:
            req_id = self._generate_req_id()
            text = req.get("text", req.get("description", str(req)))[:200]
            content = self._format_req_file(req, req_id, date, meeting_type)
            filename = f"requirements/parsed/{req_id}.md"

            self.wiki.put("requirements", req_id, {
                "text": text,
                "date": date,
                "meeting_type": meeting_type,
                "priority": req.get("priority", "unclassified"),
            }, agent=self.name, pipeline="requirements")

            if repo:
                result = repo.commit_file(
                    file_path=filename,
                    content=content,
                    message=f"Add requirement {req_id}: {text[:60]}",
                    agent_name=self.name,
                )
                if result.get("ok"):
                    outputs.append(AgentOutput(
                        output_type="file_committed",
                        description=f"Requirement {req_id} committed",
                        reference=filename,
                    ))
            else:
                outputs.append(AgentOutput(
                    output_type="req_extracted",
                    description=f"Requirement {req_id} formatted (no repo configured)",
                    reference=req_id,
                ))

        return AgentResult(agent=self.name, success=True, outputs=outputs)

    def _generate_req_id(self) -> str:
        req_id = f"REQ-{self._next_req_id:03d}"
        self._next_req_id += 1
        return req_id

    def _format_req_file(self, req: dict, req_id: str, date: str, meeting_type: str) -> str:
        priority = req.get("priority", req.get("priority_hint", "unclassified"))
        return f"""# {req_id}: {req.get('text', 'Untitled requirement')}

**ID:** {req_id}
**Date Identified:** {date}
**Source Meeting:** {meeting_type}
**Source Person:** {req.get('source', 'unknown')}
**Priority:** {priority}
**Status:** draft

## Requirement Statement

{req.get('text', '')}

## Context

Identified during {meeting_type} meeting on {date}.
{req.get('context', '')}

## Open Questions

{req.get('open_questions', 'None identified.')}

## Linked Artifacts

- Jira Ticket: _pending_
- Architecture ADR: _pending_
- PR: _pending_
- Test Coverage: _pending_
"""
