"""
Unified Traceability Store — the single source of truth for product lifecycle.

Every artifact that matters for shipping the product gets an entry here.
Each entry can link to other entries, forming chains:

  Client concern → Requirement → Decision → Architecture → Jira → PR → Test → Risk mitigated

This is what lets you pick any client concern and trace it all the way
to code — or pick any risk and see what's mitigating it.

Schema:
  artifacts     — every traceable item (concern, decision, requirement, risk, etc.)
  links         — directed edges between artifacts (concern BECAME requirement, etc.)

Link types:
  BECAME        — concern became a requirement
  DECIDED_BY    — requirement decided by a decision
  IMPLEMENTS    — Jira ticket implements a requirement
  MITIGATES     — action mitigates a risk
  ADDRESSES     — decision addresses a concern
  RAISED_IN     — artifact was raised in a meeting/session
  ASSIGNED_TO   — artifact assigned to a person
  TRIGGERED     — one artifact triggered creation of another
  VERIFIED_BY   — artifact verified by test/review
"""
from __future__ import annotations

import json
import logging
import sqlite3
import textwrap
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("pipeline.traceability")

MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"
DB_PATH = MEMORY_DIR / "traceability.db"

ARTIFACT_TYPES = [
    "concern",
    "decision",
    "requirement",
    "risk",
    "action_item",
    "commitment",
    "architecture",
    "jira_ticket",
    "pull_request",
    "test",
    "meeting",
    "coach_session",
    "adr",
]

LINK_TYPES = [
    "BECAME",
    "DECIDED_BY",
    "IMPLEMENTS",
    "MITIGATES",
    "ADDRESSES",
    "RAISED_IN",
    "ASSIGNED_TO",
    "TRIGGERED",
    "VERIFIED_BY",
    "SUPERSEDES",
    "DEPENDS_ON",
    "RELATES_TO",
]

STATUS_VALUES = ["open", "in_progress", "done", "superseded", "wont_fix"]


def _init_db(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(textwrap.dedent("""\
        CREATE TABLE IF NOT EXISTS artifacts (
            id TEXT PRIMARY KEY,
            artifact_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'open',
            source_meeting TEXT DEFAULT '',
            source_speaker TEXT DEFAULT '',
            source_timestamp TEXT DEFAULT '',
            source_quote TEXT DEFAULT '',
            owner TEXT DEFAULT '',
            jira_key TEXT DEFAULT '',
            pr_number TEXT DEFAULT '',
            priority TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata TEXT DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_art_type ON artifacts(artifact_type);
        CREATE INDEX IF NOT EXISTS idx_art_status ON artifacts(status);
        CREATE INDEX IF NOT EXISTS idx_art_jira ON artifacts(jira_key);
        CREATE INDEX IF NOT EXISTS idx_art_meeting ON artifacts(source_meeting);

        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            link_type TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (source_id) REFERENCES artifacts(id),
            FOREIGN KEY (target_id) REFERENCES artifacts(id),
            UNIQUE(source_id, target_id, link_type)
        );
        CREATE INDEX IF NOT EXISTS idx_link_source ON links(source_id);
        CREATE INDEX IF NOT EXISTS idx_link_target ON links(target_id);
        CREATE INDEX IF NOT EXISTS idx_link_type ON links(link_type);
    """))
    conn.commit()
    return conn


class TraceabilityStore:
    def __init__(self, db_path: Path | None = None):
        self._db = _init_db(db_path)

    def add_artifact(
        self,
        artifact_type: str,
        title: str,
        description: str = "",
        status: str = "open",
        source_meeting: str = "",
        source_speaker: str = "",
        source_timestamp: str = "",
        source_quote: str = "",
        owner: str = "",
        jira_key: str = "",
        pr_number: str = "",
        priority: str = "",
        artifact_id: str = "",
        metadata: dict | None = None,
    ) -> str:
        prefix = artifact_type[:3].upper()
        aid = artifact_id or f"{prefix}-{uuid.uuid4().hex[:6]}"
        now = datetime.now(timezone.utc).isoformat()

        self._db.execute(
            "INSERT OR REPLACE INTO artifacts "
            "(id, artifact_type, title, description, status, source_meeting, "
            "source_speaker, source_timestamp, source_quote, owner, jira_key, "
            "pr_number, priority, created_at, updated_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "COALESCE((SELECT created_at FROM artifacts WHERE id = ?), ?), ?, ?)",
            (aid, artifact_type, title, description, status, source_meeting,
             source_speaker, source_timestamp, source_quote, owner, jira_key,
             pr_number, priority, aid, now, now, json.dumps(metadata or {})),
        )
        self._db.commit()
        return aid

    def link(
        self,
        source_id: str,
        target_id: str,
        link_type: str,
        description: str = "",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            "INSERT OR IGNORE INTO links (source_id, target_id, link_type, description, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (source_id, target_id, link_type, description, now),
        )
        self._db.commit()

    def get_artifact(self, artifact_id: str) -> dict | None:
        row = self._db.execute(
            "SELECT * FROM artifacts WHERE id = ?", (artifact_id,)
        ).fetchone()
        if row:
            d = dict(row)
            d["metadata"] = json.loads(d["metadata"])
            return d
        return None

    def get_by_type(self, artifact_type: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM artifacts WHERE artifact_type = ? ORDER BY created_at",
            (artifact_type,),
        ).fetchall()
        return [{**dict(r), "metadata": json.loads(r["metadata"])} for r in rows]

    def get_chain(self, artifact_id: str, direction: str = "forward") -> list[dict]:
        """
        Follow the traceability chain from an artifact.
        direction='forward': follow outgoing links (concern → what it became)
        direction='backward': follow incoming links (jira ticket → where it came from)
        """
        visited = set()
        chain = []
        self._walk_chain(artifact_id, direction, visited, chain, depth=0)
        return chain

    def _walk_chain(
        self, artifact_id: str, direction: str,
        visited: set, chain: list, depth: int,
    ) -> None:
        if artifact_id in visited or depth > 10:
            return
        visited.add(artifact_id)

        artifact = self.get_artifact(artifact_id)
        if not artifact:
            return

        if direction == "forward":
            links = self._db.execute(
                "SELECT * FROM links WHERE source_id = ?", (artifact_id,)
            ).fetchall()
        else:
            links = self._db.execute(
                "SELECT * FROM links WHERE target_id = ?", (artifact_id,)
            ).fetchall()

        link_list = [dict(l) for l in links]

        chain.append({
            "depth": depth,
            "artifact": artifact,
            "links": link_list,
        })

        for link in links:
            next_id = link["target_id"] if direction == "forward" else link["source_id"]
            self._walk_chain(next_id, direction, visited, chain, depth + 1)

    def get_unlinked(self, artifact_type: str | None = None) -> list[dict]:
        """Find artifacts with no outgoing links — potential gaps in traceability."""
        query = """
            SELECT a.* FROM artifacts a
            LEFT JOIN links l ON a.id = l.source_id
            WHERE l.id IS NULL
        """
        if artifact_type:
            query += " AND a.artifact_type = ?"
            rows = self._db.execute(query, (artifact_type,)).fetchall()
        else:
            rows = self._db.execute(query).fetchall()
        return [{**dict(r), "metadata": json.loads(r["metadata"])} for r in rows]

    def get_coverage(self) -> dict[str, Any]:
        """Traceability coverage report — what percentage of artifacts are linked."""
        total = self._db.execute("SELECT COUNT(*) as c FROM artifacts").fetchone()["c"]
        by_type = self._db.execute(
            "SELECT artifact_type, COUNT(*) as c FROM artifacts GROUP BY artifact_type ORDER BY c DESC"
        ).fetchall()
        linked = self._db.execute(
            "SELECT COUNT(DISTINCT source_id) + COUNT(DISTINCT target_id) as c FROM links"
        ).fetchone()["c"]
        by_link_type = self._db.execute(
            "SELECT link_type, COUNT(*) as c FROM links GROUP BY link_type ORDER BY c DESC"
        ).fetchall()
        by_status = self._db.execute(
            "SELECT status, COUNT(*) as c FROM artifacts GROUP BY status ORDER BY c DESC"
        ).fetchall()

        unlinked_concerns = self._db.execute(
            "SELECT COUNT(*) as c FROM artifacts a "
            "LEFT JOIN links l ON a.id = l.source_id "
            "WHERE a.artifact_type = 'concern' AND l.id IS NULL"
        ).fetchone()["c"]
        total_concerns = self._db.execute(
            "SELECT COUNT(*) as c FROM artifacts WHERE artifact_type = 'concern'"
        ).fetchone()["c"]

        unlinked_risks = self._db.execute(
            "SELECT COUNT(*) as c FROM artifacts a "
            "LEFT JOIN links l ON a.id = l.target_id AND l.link_type = 'MITIGATES' "
            "WHERE a.artifact_type = 'risk' AND l.id IS NULL"
        ).fetchone()["c"]
        total_risks = self._db.execute(
            "SELECT COUNT(*) as c FROM artifacts WHERE artifact_type = 'risk'"
        ).fetchone()["c"]

        return {
            "total_artifacts": total,
            "by_type": {r["artifact_type"]: r["c"] for r in by_type},
            "total_links": self._db.execute("SELECT COUNT(*) as c FROM links").fetchone()["c"],
            "by_link_type": {r["link_type"]: r["c"] for r in by_link_type},
            "by_status": {r["status"]: r["c"] for r in by_status},
            "linked_artifacts": linked,
            "coverage_pct": round(linked / total * 100, 1) if total > 0 else 0,
            "concerns_without_action": unlinked_concerns,
            "total_concerns": total_concerns,
            "risks_without_mitigation": unlinked_risks,
            "total_risks": total_risks,
        }

    def get_all_chains_from_type(self, artifact_type: str) -> list[dict]:
        """Get full forward chains for all artifacts of a given type."""
        artifacts = self.get_by_type(artifact_type)
        results = []
        for a in artifacts:
            chain = self.get_chain(a["id"], direction="forward")
            results.append({
                "root": a,
                "chain": chain,
                "chain_length": len(chain),
            })
        return results

    def stats(self) -> dict[str, Any]:
        return self.get_coverage()
