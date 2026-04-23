"""
Jira MCP server — all Jira interactions go through this module.

Tools exposed:
  create_issue()    — create a ticket (Story, Task, Bug, Sub-task)
  get_issue()       — fetch issue details
  transition()      — move an issue through workflow states
  add_comment()     — add a comment to an issue
  search_issues()   — JQL search
  get_board_status() — summary of project board

Commit messages / comments follow convention: [agent:name] description
"""
from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger("mcp.jira")


class JiraMCP:
    def __init__(
        self,
        url: str | None = None,
        project_key: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
    ):
        self._url = (url or os.getenv("JIRA_URL", "")).rstrip("/")
        self._project_key = project_key or os.getenv("JIRA_PROJECT_KEY", "")
        self._email = email or os.getenv("JIRA_EMAIL", "")
        self._api_token = api_token or os.getenv("JIRA_API_TOKEN", "")

        self._session = requests.Session()
        if self._email and self._api_token:
            self._session.auth = (self._email, self._api_token)
        self._session.headers["Accept"] = "application/json"
        self._session.headers["Content-Type"] = "application/json"

        if self.is_configured:
            logger.info(f"Jira MCP initialized: {self._url} project={self._project_key}")
        else:
            logger.warning("Jira MCP initialized without credentials — offline mode")

    @property
    def is_configured(self) -> bool:
        return bool(self._url and self._project_key and self._email and self._api_token
                     and "yourteam" not in self._url and "your@" not in self._email)

    @property
    def _api(self) -> str:
        return f"{self._url}/rest/api/3"

    def create_issue(
        self,
        summary: str,
        description: str = "",
        issue_type: str = "Task",
        labels: list[str] | None = None,
        agent_name: str = "system",
        priority: str = "Medium",
    ) -> dict[str, Any]:
        """Create a Jira issue. Auto-labels with 'AI-generated'."""
        if not self.is_configured:
            logger.warning(f"Jira issue skipped (offline): {summary}")
            return {"ok": False, "error": "Not configured"}

        all_labels = list(set((labels or []) + ["AI-generated", f"agent-{agent_name}"]))

        # Atlassian Document Format for description
        adf_body = {
            "version": 1,
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": description or summary}],
                }
            ],
        }

        payload = {
            "fields": {
                "project": {"key": self._project_key},
                "summary": f"[{agent_name}] {summary}",
                "description": adf_body,
                "issuetype": {"name": issue_type},
                "labels": all_labels,
            }
        }

        resp = self._session.post(f"{self._api}/issue", json=payload)

        if resp.ok:
            data = resp.json()
            key = data["key"]
            logger.info(f"Created {key}: {summary}")
            return {
                "ok": True,
                "key": key,
                "id": data["id"],
                "url": f"{self._url}/browse/{key}",
                "summary": summary,
            }
        else:
            logger.error(f"Jira create failed ({resp.status_code}): {resp.text[:300]}")
            return {"ok": False, "status_code": resp.status_code, "error": resp.text[:300]}

    def get_issue(self, issue_key: str) -> dict[str, Any]:
        if not self.is_configured:
            return {"ok": False, "error": "Not configured"}

        resp = self._session.get(f"{self._api}/issue/{issue_key}")

        if resp.ok:
            d = resp.json()
            fields = d["fields"]
            return {
                "ok": True,
                "key": d["key"],
                "summary": fields.get("summary"),
                "status": fields.get("status", {}).get("name"),
                "assignee": (fields.get("assignee") or {}).get("displayName"),
                "labels": fields.get("labels", []),
                "priority": fields.get("priority", {}).get("name"),
            }
        return {"ok": False, "error": resp.text[:300]}

    def add_comment(self, issue_key: str, body: str, agent_name: str = "system") -> dict[str, Any]:
        if not self.is_configured:
            return {"ok": False, "error": "Not configured"}

        adf_body = {
            "version": 1,
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": f"[agent:{agent_name}] {body}"}],
                }
            ],
        }

        resp = self._session.post(
            f"{self._api}/issue/{issue_key}/comment",
            json={"body": adf_body},
        )

        if resp.ok:
            return {"ok": True, "comment_id": resp.json()["id"]}
        return {"ok": False, "error": resp.text[:300]}

    def transition(self, issue_key: str, target_status: str) -> dict[str, Any]:
        """Move issue to a target status (e.g., 'In Progress', 'Done')."""
        if not self.is_configured:
            return {"ok": False, "error": "Not configured"}

        # First, get available transitions
        resp = self._session.get(f"{self._api}/issue/{issue_key}/transitions")
        if not resp.ok:
            return {"ok": False, "error": resp.text[:300]}

        transitions = resp.json().get("transitions", [])
        match = next((t for t in transitions if t["name"].lower() == target_status.lower()), None)

        if not match:
            available = [t["name"] for t in transitions]
            return {"ok": False, "error": f"No transition to '{target_status}'. Available: {available}"}

        resp = self._session.post(
            f"{self._api}/issue/{issue_key}/transitions",
            json={"transition": {"id": match["id"]}},
        )

        if resp.status_code == 204:
            logger.info(f"Transitioned {issue_key} to {target_status}")
            return {"ok": True, "key": issue_key, "new_status": target_status}
        return {"ok": False, "error": resp.text[:300]}

    def search_issues(self, jql: str | None = None, max_results: int = 50) -> dict[str, Any]:
        """Search issues using JQL. Defaults to all project issues."""
        if not self.is_configured:
            return {"ok": False, "error": "Not configured"}

        query = jql or f"project = {self._project_key} ORDER BY created DESC"
        resp = self._session.post(
            f"{self._api}/search/jql",
            json={"jql": query, "maxResults": max_results, "fields": ["summary", "status", "assignee", "labels", "priority"]},
        )

        if resp.ok:
            data = resp.json()
            issues = []
            for iss in data.get("issues", []):
                f = iss["fields"]
                issues.append({
                    "key": iss["key"],
                    "summary": f.get("summary"),
                    "status": f.get("status", {}).get("name"),
                    "assignee": (f.get("assignee") or {}).get("displayName"),
                    "labels": f.get("labels", []),
                })
            return {"ok": True, "total": data.get("total", 0), "issues": issues}
        return {"ok": False, "error": resp.text[:300]}

    def get_board_status(self) -> dict[str, Any]:
        """Get a summary of the project board."""
        result = self.search_issues()
        if not result["ok"]:
            return result

        status_counts: dict[str, int] = {}
        for iss in result["issues"]:
            st = iss.get("status", "Unknown")
            status_counts[st] = status_counts.get(st, 0) + 1

        return {
            "ok": True,
            "project": self._project_key,
            "total_issues": result["total"],
            "by_status": status_counts,
            "recent_issues": result["issues"][:10],
        }
