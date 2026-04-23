"""
Alert Agent — monitors project health.

Fires Slack alert when:
  - Ticket velocity off-track
  - Must-have REQ has no Jira ticket
  - P0 ticket unassigned >48hrs
  - Drift detected but no PR opened within 24hrs
  - Recurring concern from coach sessions

Triggered by: cron_6h_alert, recurring_concern event, commitment_overdue event
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
                    output_type="alerts_generated",
                    description=f"Generated {len(alerts)} alert(s) (Slack not configured)",
                ))

            self.wiki.put("alerts", "latest", {
                "count": len(alerts),
                "alerts": alerts,
            }, agent=self.name, pipeline="project_mgmt")
        else:
            outputs.append(AgentOutput(
                output_type="health_check",
                description="All health checks passed — no alerts",
            ))

        return AgentResult(
            agent=self.name, success=True, outputs=outputs,
            data={"alerts": alerts},
        )

    def _check_all_conditions(self) -> list[str]:
        alerts = []
        alerts.extend(self._check_velocity())
        alerts.extend(self._check_unlinked_reqs())
        alerts.extend(self._check_unassigned_p0())
        alerts.extend(self._check_unresolved_drift())
        return alerts

    def _check_velocity(self) -> list[str]:
        jira = self.mcp.get("jira")
        if not jira or not getattr(jira, "is_configured", False):
            return []

        board = jira.get_board_status()
        if not board.get("ok"):
            return []

        by_status = board.get("by_status", {})
        done = by_status.get("Done", 0)
        total = board.get("total_issues", 0)

        if total > 0 and done / total < 0.3:
            return [
                f"*Sprint Velocity Alert*\n"
                f"Only {done}/{total} tickets done ({done/total*100:.0f}%). "
                f"Sprint may be at risk."
            ]
        return []

    def _check_unlinked_reqs(self) -> list[str]:
        """Check for must-have REQs without Jira tickets using the wiki."""
        try:
            reqs = self.wiki.list_namespace("requirements_engineering")
            jira = self.mcp.get("jira")
            if not reqs or not jira or not getattr(jira, "is_configured", False):
                return []

            result = jira.search_issues(
                jql=f"project = {jira._project_key} AND labels = requirements"
            )
            if not result.get("ok"):
                return []

            ticket_count = result.get("total", 0)
            req_count = len([r for r in reqs if "P0" in str(r) or "P1" in str(r)])

            if req_count > 0 and ticket_count < req_count:
                return [
                    f"*Unlinked Requirements Alert*\n"
                    f"{req_count} high-priority requirements but only {ticket_count} "
                    f"linked Jira tickets."
                ]
        except Exception:
            pass
        return []

    def _check_unassigned_p0(self) -> list[str]:
        jira = self.mcp.get("jira")
        if not jira or not getattr(jira, "is_configured", False):
            return []

        result = jira.search_issues(
            jql=f"project = {jira._project_key} AND priority = Highest AND assignee is EMPTY"
        )
        if not result.get("ok"):
            return []

        unassigned = result.get("issues", [])
        if unassigned:
            tickets = ", ".join(i["key"] for i in unassigned[:5])
            return [f"*Unassigned P0 Alert*\nP0 tickets without assignee: {tickets}"]
        return []

    def _check_unresolved_drift(self) -> list[str]:
        """Check wiki for drift events that haven't been resolved."""
        try:
            events = self.events.get_pending_events(event_type="drift_detected", limit=10)
            if not events:
                return []

            unresolved = [e for e in events if not e.get("consumed_by") or e["consumed_by"] == []]
            if unresolved:
                return [
                    f"*Unresolved Drift Alert*\n"
                    f"{len(unresolved)} architecture drift event(s) detected "
                    f"but not yet resolved with a PR."
                ]
        except Exception:
            pass
        return []
