"""
Jira export for the Program Health dashboard — the scheduled-refresh fetcher.

Pulls every EPARTS issue from Jira Cloud via the REST API and writes
dashboard/data/jira_issues.json in the exact schema generate_program_health.py
consumes, with a provenance block recording the JQL, timestamp, and fetch
mechanism. Stdlib only (urllib), so CI needs no dependency install.

Auth (never hardcoded): environment variables
    JIRA_EMAIL       — Atlassian account email that owns the token
    JIRA_API_TOKEN   — API token from id.atlassian.com

Run:  JIRA_EMAIL=... JIRA_API_TOKEN=... python3 dashboard/fetch_jira.py
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SITE = "https://epartsmse.atlassian.net"
JQL = "project = EPARTS ORDER BY created ASC"
FIELDS = [
    "summary", "status", "issuetype", "created", "resolutiondate",
    "labels", "assignee", "priority", "customfield_10016", "parent",
]
OUT = Path(__file__).resolve().parent / "data" / "jira_issues.json"


def fetch_page(auth_header: str, next_token: str | None) -> dict:
    body = {"jql": JQL, "fields": FIELDS, "maxResults": 100}
    if next_token:
        body["nextPageToken"] = next_token
    req = urllib.request.Request(
        f"{SITE}/rest/api/3/search/jql",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def normalize(issue: dict) -> dict:
    fl = issue.get("fields", {})

    def name(obj_key: str) -> str | None:
        obj = fl.get(obj_key)
        return obj.get("name") if obj else None

    parent = fl.get("parent") or {}
    return {
        "key": issue["key"],
        "summary": fl.get("summary"),
        "type": name("issuetype"),
        "status": name("status"),
        "status_category": ((fl.get("status") or {}).get("statusCategory") or {}).get("key"),
        "created": fl.get("created"),
        "resolved": fl.get("resolutiondate"),
        "points": fl.get("customfield_10016"),
        "labels": fl.get("labels") or [],
        "assignee": (fl.get("assignee") or {}).get("displayName"),
        "priority": name("priority"),
        "parent_key": parent.get("key"),
        "parent_summary": (parent.get("fields") or {}).get("summary"),
    }


def main() -> None:
    email = os.environ.get("JIRA_EMAIL")
    token = os.environ.get("JIRA_API_TOKEN")
    if not email or not token:
        sys.exit("Set JIRA_EMAIL and JIRA_API_TOKEN environment variables.")
    auth = "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode()

    rows: dict[str, dict] = {}
    next_token: str | None = None
    pages = 0
    while True:
        page = fetch_page(auth, next_token)
        for issue in page.get("issues", []):
            rows[issue["key"]] = normalize(issue)
        pages += 1
        next_token = page.get("nextPageToken")
        if not next_token or page.get("isLast", False):
            break
        if pages > 100:
            sys.exit("Pagination runaway — aborting.")

    out = {
        "provenance": {
            "source": f"Jira Cloud ({SITE.removeprefix('https://')}), project EPARTS",
            "jql": JQL,
            "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fetched_by": f"{email} via REST API (dashboard/fetch_jira.py, scheduled workflow)",
            "issue_count": len(rows),
            "note": "Re-derive: run the JQL above in Jira; every dashboard number recomputes from this file via dashboard/generate_program_health.py",
        },
        "issues": sorted(rows.values(), key=lambda r: r["key"]),
    }
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"fetched {len(rows)} issues in {pages} page(s) -> {OUT}")


if __name__ == "__main__":
    main()
