"""
GitHub MCP server — all GitHub repository interactions go through this module.

Tools exposed:
  commit_file()    — commit a file to a branch
  open_pr()        — open a pull request
  add_pr_comment() — add a review comment on a PR
  get_repo_info()  — get repository metadata
  create_branch()  — create a new branch

Commit messages follow convention: [agent:name] description
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any

import requests

logger = logging.getLogger("mcp.github")

GITHUB_API = "https://api.github.com"


class GitHubMCP:
    def __init__(
        self,
        repo: str | None = None,
        token: str | None = None,
    ):
        self._repo = repo or os.getenv("GITHUB_REPO", "")
        self._token = token or os.getenv("GITHUB_TOKEN", "")
        self._session = requests.Session()
        if self._token:
            self._session.headers["Authorization"] = f"Bearer {self._token}"
            self._session.headers["Accept"] = "application/vnd.github.v3+json"
            self._session.headers["X-GitHub-Api-Version"] = "2022-11-28"

        if self._repo and self._token:
            logger.info(f"GitHub MCP initialized for repo={self._repo}")
        else:
            logger.warning("GitHub MCP initialized without credentials — offline mode")

    @property
    def _repo_url(self) -> str:
        return f"{GITHUB_API}/repos/{self._repo}"

    @property
    def is_configured(self) -> bool:
        return bool(self._repo and self._token)

    def get_repo_info(self) -> dict[str, Any]:
        if not self.is_configured:
            return {"ok": False, "error": "Not configured"}
        resp = self._session.get(self._repo_url)
        if resp.ok:
            d = resp.json()
            return {
                "ok": True,
                "name": d["full_name"],
                "default_branch": d["default_branch"],
                "private": d["private"],
                "url": d["html_url"],
            }
        return {"ok": False, "status_code": resp.status_code, "error": resp.text[:300]}

    def commit_file(
        self,
        file_path: str,
        content: str,
        message: str,
        branch: str = "main",
        agent_name: str = "system",
    ) -> dict[str, Any]:
        """Commit a single file using the GitHub Contents API."""
        if not self.is_configured:
            logger.warning(f"Commit skipped (offline): {file_path}")
            return {"ok": False, "error": "Not configured"}

        prefixed_msg = f"[agent:{agent_name}] {message}"
        url = f"{self._repo_url}/contents/{file_path}"

        # Check if file exists (need SHA for updates)
        sha = None
        check = self._session.get(url, params={"ref": branch})
        if check.ok:
            sha = check.json().get("sha")

        payload: dict[str, Any] = {
            "message": prefixed_msg,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        resp = self._session.put(url, json=payload)

        if resp.ok:
            commit_sha = resp.json().get("commit", {}).get("sha", "")[:8]
            logger.info(f"Committed {file_path} to {branch}: {prefixed_msg} ({commit_sha})")
            return {
                "ok": True,
                "file": file_path,
                "branch": branch,
                "message": prefixed_msg,
                "commit_sha": commit_sha,
            }
        else:
            logger.error(f"Commit failed ({resp.status_code}): {resp.text[:300]}")
            return {"ok": False, "status_code": resp.status_code, "error": resp.text[:300]}

    def create_branch(self, branch_name: str, from_branch: str = "main") -> dict[str, Any]:
        """Create a new branch from an existing branch."""
        if not self.is_configured:
            return {"ok": False, "error": "Not configured"}

        # Get the SHA of the source branch
        ref_resp = self._session.get(f"{self._repo_url}/git/ref/heads/{from_branch}")
        if not ref_resp.ok:
            return {"ok": False, "error": f"Source branch '{from_branch}' not found"}

        sha = ref_resp.json()["object"]["sha"]

        # Create the new branch
        resp = self._session.post(
            f"{self._repo_url}/git/refs",
            json={"ref": f"refs/heads/{branch_name}", "sha": sha},
        )

        if resp.ok:
            logger.info(f"Branch created: {branch_name} from {from_branch}")
            return {"ok": True, "branch": branch_name, "sha": sha[:8]}
        elif resp.status_code == 422:
            logger.info(f"Branch already exists: {branch_name}")
            return {"ok": True, "branch": branch_name, "already_exists": True}
        else:
            logger.error(f"Branch creation failed: {resp.text[:300]}")
            return {"ok": False, "error": resp.text[:300]}

    def open_pr(
        self,
        title: str,
        source_branch: str,
        description: str = "",
        destination_branch: str = "main",
    ) -> dict[str, Any]:
        if not self.is_configured:
            return {"ok": False, "error": "Not configured"}

        resp = self._session.post(
            f"{self._repo_url}/pulls",
            json={
                "title": title,
                "head": source_branch,
                "base": destination_branch,
                "body": description,
            },
        )

        if resp.ok:
            d = resp.json()
            logger.info(f"PR opened: #{d['number']} — {title}")
            return {"ok": True, "pr_number": d["number"], "pr_url": d["html_url"]}
        else:
            logger.error(f"PR creation failed: {resp.text[:300]}")
            return {"ok": False, "error": resp.text[:300]}

    def add_pr_comment(self, pr_number: int, content: str) -> dict[str, Any]:
        if not self.is_configured:
            return {"ok": False, "error": "Not configured"}

        resp = self._session.post(
            f"{self._repo_url}/issues/{pr_number}/comments",
            json={"body": content},
        )

        if resp.ok:
            return {"ok": True, "comment_id": resp.json()["id"]}
        return {"ok": False, "error": resp.text[:300]}
