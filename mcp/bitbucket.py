"""
Bitbucket MCP server — all repository interactions go through this module.

Tools exposed:
  commit_file()    — commit a file to a branch
  open_pr()        — open a pull request
  add_pr_comment() — add a review comment on a PR
  get_pr_status()  — check PR state (open/merged/declined)

No agent should make direct HTTP calls to Bitbucket. Use this wrapper.
Commit messages follow convention: [agent:name] description
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

import requests

logger = logging.getLogger("mcp.bitbucket")

BITBUCKET_API = "https://api.bitbucket.org/2.0"


class BitbucketMCP:
    def __init__(
        self,
        workspace: str | None = None,
        repo_slug: str | None = None,
        token: str | None = None,
    ):
        self._workspace = workspace or os.getenv("BITBUCKET_WORKSPACE", "")
        self._repo = repo_slug or os.getenv("BITBUCKET_REPO", "")
        self._token = token or os.getenv("BITBUCKET_TOKEN", "")
        self._session = requests.Session()
        if self._token:
            self._session.headers["Authorization"] = f"Bearer {self._token}"
        self._session.headers["Content-Type"] = "application/json"

    @property
    def _repo_url(self) -> str:
        return f"{BITBUCKET_API}/repositories/{self._workspace}/{self._repo}"

    def commit_file(
        self,
        file_path: str,
        content: str,
        message: str,
        branch: str = "main",
        agent_name: str = "system",
    ) -> dict[str, Any]:
        """
        Commit a single file to a branch using the Bitbucket source endpoint.
        Commit message is auto-prefixed with [agent:name].
        """
        url = f"{self._repo_url}/src"
        prefixed_msg = f"[agent:{agent_name}] {message}"

        # Bitbucket src endpoint uses multipart form data
        response = self._session.post(
            url,
            headers={"Content-Type": None},  # let requests set multipart boundary
            data={
                "message": prefixed_msg,
                "branch": branch,
            },
            files={
                file_path: (file_path, content.encode("utf-8")),
            },
        )

        if response.ok:
            logger.info(f"Committed {file_path} to {branch}: {prefixed_msg}")
            return {
                "ok": True,
                "file": file_path,
                "branch": branch,
                "message": prefixed_msg,
            }
        else:
            logger.error(
                f"Commit failed ({response.status_code}): {response.text[:300]}"
            )
            return {
                "ok": False,
                "status_code": response.status_code,
                "error": response.text[:500],
            }

    def open_pr(
        self,
        title: str,
        source_branch: str,
        description: str = "",
        destination_branch: str = "main",
        reviewers: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Open a pull request from source_branch to destination_branch.
        Returns the PR URL and ID.
        """
        url = f"{self._repo_url}/pullrequests"

        payload: dict[str, Any] = {
            "title": title,
            "source": {"branch": {"name": source_branch}},
            "destination": {"branch": {"name": destination_branch}},
            "description": description,
            "close_source_branch": True,
        }

        if reviewers:
            payload["reviewers"] = [{"username": r} for r in reviewers]

        response = self._session.post(url, json=payload)

        if response.ok:
            data = response.json()
            pr_id = data.get("id")
            pr_url = data.get("links", {}).get("html", {}).get("href", "")
            logger.info(f"PR opened: #{pr_id} — {title} ({source_branch} → {destination_branch})")
            return {
                "ok": True,
                "pr_id": pr_id,
                "pr_url": pr_url,
                "title": title,
                "source_branch": source_branch,
            }
        else:
            logger.error(
                f"PR creation failed ({response.status_code}): {response.text[:300]}"
            )
            return {
                "ok": False,
                "status_code": response.status_code,
                "error": response.text[:500],
            }

    def add_pr_comment(
        self,
        pr_id: int,
        content: str,
        inline: dict | None = None,
    ) -> dict[str, Any]:
        """
        Add a comment to a pull request.
        For inline comments, pass inline={"to": line_num, "path": "file.py"}.
        """
        url = f"{self._repo_url}/pullrequests/{pr_id}/comments"

        payload: dict[str, Any] = {
            "content": {"raw": content},
        }
        if inline:
            payload["inline"] = inline

        response = self._session.post(url, json=payload)

        if response.ok:
            comment_id = response.json().get("id")
            logger.info(f"Comment added to PR #{pr_id}: id={comment_id}")
            return {"ok": True, "comment_id": comment_id, "pr_id": pr_id}
        else:
            logger.error(
                f"PR comment failed ({response.status_code}): {response.text[:300]}"
            )
            return {"ok": False, "error": response.text[:500]}

    def get_pr_status(self, pr_id: int) -> dict[str, Any]:
        """Check the state of a pull request (OPEN, MERGED, DECLINED)."""
        url = f"{self._repo_url}/pullrequests/{pr_id}"

        response = self._session.get(url)

        if response.ok:
            data = response.json()
            return {
                "ok": True,
                "pr_id": pr_id,
                "state": data.get("state"),
                "title": data.get("title"),
                "author": data.get("author", {}).get("display_name"),
                "merge_commit": data.get("merge_commit", {}).get("hash"),
            }
        else:
            return {
                "ok": False,
                "status_code": response.status_code,
                "error": response.text[:500],
            }

    def create_branch(self, branch_name: str, from_branch: str = "main") -> dict[str, Any]:
        """Create a new branch from an existing branch."""
        url = f"{self._repo_url}/refs/branches"
        payload = {
            "name": branch_name,
            "target": {"hash": from_branch},
        }

        response = self._session.post(url, json=payload)

        if response.ok:
            logger.info(f"Branch created: {branch_name} from {from_branch}")
            return {"ok": True, "branch": branch_name}
        else:
            logger.error(
                f"Branch creation failed ({response.status_code}): {response.text[:300]}"
            )
            return {"ok": False, "error": response.text[:500]}
