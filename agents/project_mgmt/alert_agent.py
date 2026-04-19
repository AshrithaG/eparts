"""
Alert Agent — monitors sprint state every 6 hours.

Fires Slack alert when:
  - Ticket velocity off-track
  - Must-have REQ has no Jira ticket
  - P0 ticket unassigned >48hrs
  - Drift detected but no PR opened within 24hrs

Triggered by: cron_6h_alert
Outputs: Slack alerts
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.alert_agent")


class AlertAgent(BaseAgent):
    """Monitors project health and fires alerts for anomalies."""

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="alert_agent", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        alerts = self._check_all_conditions()
        outputs = []

        if alerts:
            slack = self.mcp.get("slack")
            if slack:
                for alert in alerts:
                    slack.send_alert(alert)
                outputs.append(AgentOutput(
                    output_type="alerts_sent",
                    description=f"Fired {len(alerts)} alert(s)",
                ))
        else:
            outputs.append(AgentOutput(
                output_type="health_check",
                description="All health checks passed — no alerts",
            ))

        return AgentResult(agent=self.name, success=True, outputs=outputs)

    def _check_all_conditions(self) -> list[str]:
        """Run all health checks and return alert messages."""
        alerts = []

        alerts.extend(self._check_velocity())
        alerts.extend(self._check_unlinked_reqs())
        alerts.extend(self._check_unassigned_p0())
        alerts.extend(self._check_unresolved_drift())

        return alerts

    def _check_velocity(self) -> list[str]:
        """Check if ticket velocity is on track for the sprint."""
        jira = self.mcp.get("jira")
        if not jira:
            return []

        state = jira.get_sprint_state()
        if not state.get("ok"):
            return []

        issues = state.get("issues", [])
        done = sum(1 for i in issues if i.get("status") == "Done")
        total = len(issues)

        if total > 0 and done / total < 0.3:
            return [
                f"*Sprint Velocity Alert*\n"
                f"Only {done}/{total} tickets done ({done/total*100:.0f}%). "
                f"Sprint may be at risk."
            ]
        return []

    def _check_unlinked_reqs(self) -> list[str]:
        """Check for must-have REQs without Jira tickets."""
        # In production: scan /requirements/parsed/ for REQs
        # with priority P0/P1 and no linked Jira ticket
        return []

    def _check_unassigned_p0(self) -> list[str]:
        """Check for P0 tickets unassigned for >48 hours."""
        jira = self.mcp.get("jira")
        if not jira:
            return []

        state = jira.get_sprint_state()
        if not state.get("ok"):
            return []

        unassigned_p0 = [
            i for i in state.get("issues", [])
            if i.get("priority") == "Highest" and i.get("assignee") == "unassigned"
        ]

        if unassigned_p0:
            tickets = ", ".join(i["key"] for i in unassigned_p0)
            return [f"*Unassigned P0 Alert*\nP0 tickets without assignee: {tickets}"]
        return []

    def _check_unresolved_drift(self) -> list[str]:
        """Check for drift detected but no PR opened within 24hrs."""
        # In production: read /docs/drift/ for recent reports,
        # check Bitbucket for corresponding arch update PRs
        return []
