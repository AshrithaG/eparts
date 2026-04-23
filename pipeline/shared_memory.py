"""
Shared Memory — the persistent "project wiki" all agents read and write.

This is the Karpathy wiki pattern: instead of agents producing isolated outputs,
every agent enriches a shared, structured knowledge store. Over time this store
becomes the team's accumulated intelligence.

Namespaces:
  requirements/  — extracted requirements, priorities, staleness
  architecture/  — ADRs, drift reports, canonical component list
  decisions/     — all logged decisions with context and status
  risks/         — known risks, current status, mitigation evidence
  commitments/   — coach/mentor commitments with delivery tracking
  concerns/      — recurring themes from coach sessions
  ml_decisions/  — ML model evaluations, evidence, readiness state
  meetings/      — meeting summaries, action items, cross-meeting analysis
  metrics/       — aggregate SES performance indicators

Each entry has: namespace, key, value (JSON), source_agent, source_pipeline,
timestamp, and optional tags for cross-referencing.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("pipeline.shared_memory")

MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"
DB_PATH = MEMORY_DIR / "shared_memory.db"


def _init_db(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(textwrap.dedent("""\
        CREATE TABLE IF NOT EXISTS wiki (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            namespace TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            source_agent TEXT DEFAULT '',
            source_pipeline TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(namespace, key)
        );
        CREATE INDEX IF NOT EXISTS idx_wiki_ns ON wiki(namespace);
        CREATE INDEX IF NOT EXISTS idx_wiki_ns_key ON wiki(namespace, key);

        CREATE TABLE IF NOT EXISTS wiki_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            namespace TEXT NOT NULL,
            key TEXT NOT NULL,
            action TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            agent TEXT DEFAULT '',
            pipeline TEXT DEFAULT '',
            timestamp TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_log_ns ON wiki_log(namespace);
    """))
    conn.commit()
    return conn


class SharedMemory:
    """
    The project wiki — a namespaced key-value store where agents
    deposit and query structured knowledge.

    Every write is logged, creating an audit trail of how the
    project's knowledge evolved over time.
    """

    def __init__(self, db_path: Path | None = None):
        self._db = _init_db(db_path)

    def put(
        self,
        namespace: str,
        key: str,
        value: Any,
        agent: str = "",
        pipeline: str = "",
        tags: list[str] | None = None,
    ) -> None:
        """Write or update a wiki entry. Logs the change."""
        now = datetime.now(timezone.utc).isoformat()
        val_json = json.dumps(value, default=str)
        tags_json = json.dumps(tags or [])

        existing = self._db.execute(
            "SELECT value FROM wiki WHERE namespace = ? AND key = ?",
            (namespace, key),
        ).fetchone()

        if existing:
            old_val = existing["value"]
            self._db.execute(
                "UPDATE wiki SET value = ?, source_agent = ?, source_pipeline = ?, "
                "tags = ?, updated_at = ? WHERE namespace = ? AND key = ?",
                (val_json, agent, pipeline, tags_json, now, namespace, key),
            )
            self._log(namespace, key, "update", old_val, val_json, agent, pipeline)
        else:
            self._db.execute(
                "INSERT INTO wiki (namespace, key, value, source_agent, source_pipeline, "
                "tags, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (namespace, key, val_json, agent, pipeline, tags_json, now, now),
            )
            self._log(namespace, key, "create", None, val_json, agent, pipeline)

        self._db.commit()

    def get(self, namespace: str, key: str, default: Any = None) -> Any:
        """Read a single wiki entry."""
        row = self._db.execute(
            "SELECT value FROM wiki WHERE namespace = ? AND key = ?",
            (namespace, key),
        ).fetchone()
        if row:
            return json.loads(row["value"])
        return default

    def list_keys(self, namespace: str) -> list[str]:
        """List all keys in a namespace."""
        rows = self._db.execute(
            "SELECT key FROM wiki WHERE namespace = ? ORDER BY key",
            (namespace,),
        ).fetchall()
        return [r["key"] for r in rows]

    def list_namespace(self, namespace: str) -> list[dict[str, Any]]:
        """Return all entries in a namespace with metadata."""
        rows = self._db.execute(
            "SELECT key, value, source_agent, source_pipeline, tags, updated_at "
            "FROM wiki WHERE namespace = ? ORDER BY updated_at DESC",
            (namespace,),
        ).fetchall()
        return [
            {
                "key": r["key"],
                "value": json.loads(r["value"]),
                "source_agent": r["source_agent"],
                "source_pipeline": r["source_pipeline"],
                "tags": json.loads(r["tags"]),
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]

    def search(self, query: str, namespace: str | None = None) -> list[dict[str, Any]]:
        """Full-text search across wiki entries."""
        if namespace:
            rows = self._db.execute(
                "SELECT namespace, key, value, source_agent, updated_at FROM wiki "
                "WHERE namespace = ? AND (key LIKE ? OR value LIKE ?) "
                "ORDER BY updated_at DESC",
                (namespace, f"%{query}%", f"%{query}%"),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT namespace, key, value, source_agent, updated_at FROM wiki "
                "WHERE key LIKE ? OR value LIKE ? ORDER BY updated_at DESC",
                (f"%{query}%", f"%{query}%"),
            ).fetchall()

        return [
            {
                "namespace": r["namespace"],
                "key": r["key"],
                "value": json.loads(r["value"]),
                "source_agent": r["source_agent"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]

    def find_by_tags(self, tags: list[str]) -> list[dict[str, Any]]:
        """Find wiki entries that have any of the given tags."""
        results = []
        for tag in tags:
            rows = self._db.execute(
                "SELECT namespace, key, value, tags, source_agent, updated_at FROM wiki "
                "WHERE tags LIKE ?",
                (f'%"{tag}"%',),
            ).fetchall()
            for r in rows:
                results.append({
                    "namespace": r["namespace"],
                    "key": r["key"],
                    "value": json.loads(r["value"]),
                    "tags": json.loads(r["tags"]),
                    "source_agent": r["source_agent"],
                    "updated_at": r["updated_at"],
                })
        return results

    def delete(self, namespace: str, key: str, agent: str = "") -> bool:
        old = self._db.execute(
            "SELECT value FROM wiki WHERE namespace = ? AND key = ?",
            (namespace, key),
        ).fetchone()
        if not old:
            return False
        self._db.execute(
            "DELETE FROM wiki WHERE namespace = ? AND key = ?",
            (namespace, key),
        )
        self._log(namespace, key, "delete", old["value"], None, agent, "")
        self._db.commit()
        return True

    def get_history(self, namespace: str, key: str, limit: int = 20) -> list[dict]:
        """Get the change log for a specific entry."""
        rows = self._db.execute(
            "SELECT * FROM wiki_log WHERE namespace = ? AND key = ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (namespace, key, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        """Aggregate stats across all namespaces."""
        rows = self._db.execute(
            "SELECT namespace, COUNT(*) as entries FROM wiki GROUP BY namespace ORDER BY namespace"
        ).fetchall()
        ns_stats = {r["namespace"]: r["entries"] for r in rows}
        total = sum(ns_stats.values())
        log_count = self._db.execute("SELECT COUNT(*) as c FROM wiki_log").fetchone()["c"]
        return {
            "total_entries": total,
            "total_changes": log_count,
            "namespaces": ns_stats,
        }

    def _log(
        self, namespace: str, key: str, action: str,
        old_value: str | None, new_value: str | None,
        agent: str, pipeline: str,
    ) -> None:
        self._db.execute(
            "INSERT INTO wiki_log (namespace, key, action, old_value, new_value, "
            "agent, pipeline, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (namespace, key, action, old_value, new_value, agent, pipeline,
             datetime.now(timezone.utc).isoformat()),
        )
