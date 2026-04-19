"""
Jira MCP server — all Jira interactions go through this module.

Tools exposed:
  create_ticket()     — create a new issue
  update_ticket()     — update fields on an existing issue
  get_sprint_state()  — get current sprint board state
  add_comment()       — add a comment to an issue

No agent should import atlassian-python-api directly. Use this wrapper.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from atlassian import Jira

logger = logging.getLogger("mcp.jira")


class JiraMCP:
    def __init__(
        self,
        server: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
    ):
        self._server = server or os.getenv("JIRA_SERVER", "")
        self._email = email or os.getenv("JIRA_EMAIL", "")
        self._token = api_token or os.getenv("JIRA_API_TOKEN", "")
        self._project_key = os.getenv("JIRA_PROJECT_KEY", "EPARTS")

        if self._server and self._email and self._token:
            self._client = Jira(
                url=self._server,
                username=self._email,
                password=self._token,
                cloud=True,
            )
        else:
            self._client = None
            logger.warning("Jira MCP initialized without credentials — offline mode")

    def create_ticket(
        self,
        summary: str,
        description: str,
        issue_type: str = "Task",
        priority: str = "Medium",
        assignee: str | None = None,
        labels: list[str] | None = None,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        """Create a new Jira issue. Returns the issue key and URL."""
        if not self._client:
            logger.warning("Jira offline — ticket not created")
            return {"ok": False, "error": "Jira not configured"}

        project = project_key or self._project_key
        fields: dict[str, Any] = {
            "project": {"key": project},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type},
            "priority": {"name": priority},
        }
        if assignee:
            fields["assignee"] = {"name": assignee}
        if labels:
            fields["labels"] = labels

        try:
            result = self._client.create_issue(fields=fields)
            issue_key = result.get("key", "")
            logger.info(f"Ticket created: {issue_key} — {summary}")
            return {
                "ok": True,
                "key": issue_key,
                "url": f"{self._server}browse/{issue_key}",
                "summary": summary,
            }
        except Exception as exc:
            logger.error(f"Jira create_ticket failed: {exc}")
            return {"ok": False, "error": str(exc)}

    def update_ticket(
        self,
        issue_key: str,
        fields: dict[str, Any] | None = None,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """Update fields or add a comment on an existing issue."""
        if not self._client:
            return {"ok": False, "error": "Jira not configured"}

        try:
            if fields:
                self._client.update_issue(issue_key, fields=fields)
            if comment:
                self._client.add_comment(issue_key, comment)
            logger.info(f"Ticket updated: {issue_key}")
            return {"ok": True, "key": issue_key}
        except Exception as exc:
            logger.error(f"Jira update_ticket failed: {exc}")
            return {"ok": False, "error": str(exc)}

    def get_sprint_state(self, board_id: int | None = None) -> dict[str, Any]:
        """Get the current sprint's issues and their statuses."""
        if not self._client:
            return {"ok": False, "error": "Jira not configured"}

        try:
            jql = f"project = {self._project_key} AND sprint in openSprints()"
            issues = self._client.jql(jql, limit=100)
            parsed = []
            for issue in issues.get("issues", []):
                parsed.append({
                    "key": issue["key"],
                    "summary": issue["fields"]["summary"],
                    "status": issue["fields"]["status"]["name"],
                    "assignee": (issue["fields"].get("assignee") or {}).get("displayName", "unassigned"),
                    "priority": issue["fields"]["priority"]["name"],
                })
            logger.info(f"Sprint state: {len(parsed)} issues")
            return {
                "ok": True,
                "issue_count": len(parsed),
                "issues": parsed,
            }
        except Exception as exc:
            logger.error(f"Jira get_sprint_state failed: {exc}")
            return {"ok": False, "error": str(exc)}

    def add_comment(self, issue_key: str, body: str) -> dict[str, Any]:
        """Add a comment to an issue."""
        if not self._client:
            return {"ok": False, "error": "Jira not configured"}

        try:
            self._client.add_comment(issue_key, body)
            logger.info(f"Comment added to {issue_key}")
            return {"ok": True, "key": issue_key}
        except Exception as exc:
            logger.error(f"Jira add_comment failed: {exc}")
            return {"ok": False, "error": str(exc)}
