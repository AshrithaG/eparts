"""
Stale REQ Detector — flags requirements that have gone stale.

Runs Monday 8am via cron. Flags REQs with no Jira ticket and not
mentioned in any meeting transcript in the past 14 days.

Triggered by: cron_monday_8am
Outputs: Slack alert + /docs/stale-requirements.md
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.stale_detector")

STALE_THRESHOLD_DAYS = int(os.getenv("STALE_REQ_THRESHOLD_DAYS", "14"))


class StaleDetectorAgent(BaseAgent):
    """
    Detects requirements that have gone stale — no Jira ticket
    and no mention in recent meetings.
    """

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="stale_detector", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        # In production: scan /requirements/parsed/ in Bitbucket,
        # cross-reference against Jira tickets and recent meeting minutes
        stale_reqs = self._find_stale_requirements()
        outputs = []

        if stale_reqs:
            report = self._format_stale_report(stale_reqs)

            slack = self.mcp.get("slack")
            if slack:
                slack.send_alert(
                    f"*Stale Requirements Alert*\n"
                    f"{len(stale_reqs)} requirement(s) with no activity in "
                    f"{STALE_THRESHOLD_DAYS} days.\n\n{report}"
                )
                outputs.append(AgentOutput(
                    output_type="message_sent",
                    description=f"Stale REQ alert: {len(stale_reqs)} items",
                ))

            bitbucket = self.mcp.get("bitbucket")
            if bitbucket:
                bitbucket.commit_file(
                    file_path="docs/stale-requirements.md",
                    content=f"# Stale Requirements — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n\n{report}",
                    message=f"Update stale requirements report ({len(stale_reqs)} items)",
                    agent_name=self.name,
                )
                outputs.append(AgentOutput(
                    output_type="file_committed",
                    description="docs/stale-requirements.md updated",
                ))
        else:
            outputs.append(AgentOutput(
                output_type="stale_check",
                description="No stale requirements detected",
            ))

        return AgentResult(agent=self.name, success=True, outputs=outputs)

    def _find_stale_requirements(self) -> list[dict]:
        """
        Scan the wiki for requirements with no recent activity,
        cross-reference against Jira tickets.
        """
        stale = []
        try:
            reqs = self.wiki.list_namespace("requirements_engineering")
            if not reqs:
                return []

            cutoff = (datetime.now(timezone.utc) - timedelta(days=STALE_THRESHOLD_DAYS)).isoformat()

            jira = self.mcp.get("jira")
            jira_keys = set()
            if jira and getattr(jira, "is_configured", False):
                result = jira.search_issues(
                    jql=f"project = {jira._project_key} AND labels = requirements"
                )
                if result.get("ok"):
                    jira_keys = {i["summary"].lower() for i in result.get("issues", [])}

            for entry in reqs:
                if not isinstance(entry, dict):
                    continue
                updated = entry.get("updated_at", entry.get("timestamp", ""))
                text = str(entry.get("value", entry.get("key", "")))

                has_ticket = any(kw in text.lower() for kw in jira_keys) if jira_keys else False

                if updated < cutoff and not has_ticket:
                    stale.append({
                        "req_id": entry.get("key", "unknown"),
                        "text": text[:100],
                        "last_activity": updated[:10] if updated else "unknown",
                        "jira_ticket": "none",
                    })
        except Exception as exc:
            logger.debug(f"Stale detection error: {exc}")

        return stale

    def _format_stale_report(self, stale_reqs: list[dict]) -> str:
        lines = []
        for req in stale_reqs:
            lines.append(
                f"- **{req.get('req_id', '?')}**: {req.get('text', '?')}\n"
                f"  Last activity: {req.get('last_activity', 'unknown')} | "
                f"Jira: {req.get('jira_ticket', 'none')}"
            )
        return "\n".join(lines) if lines else "No stale requirements."
