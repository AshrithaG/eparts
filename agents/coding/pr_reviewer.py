"""
PR Reviewer — auto-comments on every PR with style, test coverage,
REQ traceability, and API surface documentation checks.

Comment only — human decides on merge. No auto-merge ever.

Triggered by: PR open event
Outputs: PR comment with review feedback
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.pr_reviewer")


class PRReviewerAgent(BaseAgent):
    """Auto-reviews PRs for style, tests, and traceability."""

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="pr_reviewer", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        pr_id = trigger.metadata.get("pr_id")
        diff = trigger.metadata.get("diff", "")
        pr_title = trigger.metadata.get("title", "")
        pr_description = trigger.metadata.get("description", "")

        if not pr_id or not diff:
            return AgentResult(
                agent=self.name, success=True,
                outputs=[AgentOutput(
                    output_type="review_skipped",
                    description="No PR diff available",
                )],
            )

        review = self._generate_review(diff, pr_title, pr_description)

        outputs = []
        bitbucket = self.mcp.get("bitbucket")
        if bitbucket:
            bitbucket.add_pr_comment(pr_id, review)
            outputs.append(AgentOutput(
                output_type="pr_comment",
                description="Auto-review posted to PR",
                reference=str(pr_id),
            ))

        return AgentResult(agent=self.name, success=True, outputs=outputs)

    def _generate_review(self, diff: str, title: str, description: str) -> str:
        prompt = f"""Review this pull request. Check for:

1. **Code style**: Python conventions, type hints, docstrings
2. **Test coverage**: are there tests for new functionality?
3. **REQ traceability**: does the PR reference a REQ-XXX ID?
4. **Jira link**: does it reference a Jira ticket?
5. **API surface**: if API endpoints changed, are docs updated?
6. **Security**: any hardcoded secrets, credentials, or tokens?

PR Title: {title}
PR Description: {description}

DIFF:
{diff[:8000]}

Format as a PR review comment in markdown. Be constructive and specific.
Start with a brief summary, then itemized feedback."""

        return self.call_claude(prompt)
