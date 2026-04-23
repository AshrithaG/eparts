"""
Event Bus — cross-pipeline communication backbone.

When one pipeline produces a significant output, it publishes an event.
Other pipelines (or individual agents) subscribe to event types and
auto-trigger when relevant events fire.

This is what makes the system a connected framework rather than
isolated scripts. Examples:

  requirements pipeline → drift_detected event → architecture pipeline
  coach session pipeline → recurring_concern event → PM alert pipeline
  ML decision pipeline → decision_ready event → coach briefing
  any pipeline → action_items_extracted → PM ticket creation

Events are persistent (SQLite-backed) so we have a full audit trail
of system-level communication.
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
from typing import Any, Callable

logger = logging.getLogger("pipeline.event_bus")

MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"
DB_PATH = MEMORY_DIR / "events.db"


@dataclass
class Event:
    """A cross-pipeline event."""
    event_type: str
    source_agent: str
    source_pipeline: str
    data: dict[str, Any] = field(default_factory=dict)
    event_id: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.event_id:
            self.event_id = f"evt-{uuid.uuid4().hex[:8]}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


# Well-known event types — the contract between pipelines
EVENT_TYPES = {
    # Requirements → Architecture
    "drift_detected": "Requirements discussion contradicts canonical architecture",
    "new_requirements": "New requirements extracted from meeting",
    "priority_changed": "Item priority was reclassified",

    # Coach → PM / Knowledge
    "recurring_concern": "A coach/mentor concern has recurred across multiple sessions",
    "commitment_overdue": "A commitment from a coach session is past deadline",
    "new_session_embedded": "A new coach/mentor session was embedded into ChromaDB",

    # ML Decision → Coach / Architecture
    "decision_ready": "Enough evidence accumulated to close an ML decision",
    "poc_evidence_logged": "New POC result evidence was logged",

    # Any → PM
    "action_items_extracted": "Action items were extracted from a meeting",
    "human_review_needed": "An agent output needs human review before proceeding",

    # Any → Knowledge
    "decision_logged": "A decision was captured and logged",
    "artifact_produced": "A significant artifact was generated",
}


def _init_db(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(textwrap.dedent("""\
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE NOT NULL,
            event_type TEXT NOT NULL,
            source_agent TEXT NOT NULL,
            source_pipeline TEXT DEFAULT '',
            data TEXT DEFAULT '{}',
            timestamp TEXT NOT NULL,
            consumed_by TEXT DEFAULT '[]'
        );
        CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
        CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);

        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            target_pipeline TEXT NOT NULL,
            target_agent TEXT DEFAULT '',
            description TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            UNIQUE(event_type, target_pipeline)
        );
    """))
    conn.commit()
    return conn


class EventBus:
    """
    Publish-subscribe event bus for cross-pipeline communication.

    Agents publish events. The orchestrator (or pipeline executor)
    checks for pending events and triggers the subscribed pipelines.

    In-process handlers fire synchronously for demo purposes.
    In production, this would be async via a message queue.
    """

    def __init__(self, db_path: Path | None = None):
        self._db = _init_db(db_path)
        self._handlers: dict[str, list[Callable[[Event], None]]] = {}
        self._setup_default_subscriptions()

    def _setup_default_subscriptions(self) -> None:
        """Register the cross-pipeline subscription table."""
        defaults = [
            ("drift_detected", "architecture", "", "Drift in requirements triggers architecture review"),
            ("new_requirements", "architecture", "drift_detector", "New reqs trigger drift check"),
            ("recurring_concern", "project_mgmt", "alert_agent", "Recurring concerns trigger PM alerts"),
            ("commitment_overdue", "project_mgmt", "alert_agent", "Overdue commitments trigger PM alerts"),
            ("new_session_embedded", "knowledge", "briefing_generator", "New sessions trigger briefing refresh"),
            ("decision_ready", "coach_session", "coach_linker", "Ready decisions link to coach context"),
            ("action_items_extracted", "project_mgmt", "ticket_creator", "Action items trigger ticket creation"),
            ("human_review_needed", "project_mgmt", "alert_agent", "Human review requests trigger alerts"),
            ("poc_evidence_logged", "ml_decision", "readiness_detector", "New evidence triggers readiness check"),
            ("decision_logged", "knowledge", "decision_logger", "Decisions get logged to knowledge base"),
        ]
        for event_type, pipeline, agent, desc in defaults:
            self._db.execute(
                "INSERT OR IGNORE INTO subscriptions (event_type, target_pipeline, target_agent, description) "
                "VALUES (?, ?, ?, ?)",
                (event_type, pipeline, agent, desc),
            )
        self._db.commit()

    def publish(self, event: Event) -> list[dict[str, str]]:
        """
        Publish an event and return the list of triggered subscriptions.
        Also fires any in-process handlers.
        """
        self._db.execute(
            "INSERT OR IGNORE INTO events (event_id, event_type, source_agent, "
            "source_pipeline, data, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (event.event_id, event.event_type, event.source_agent,
             event.source_pipeline, json.dumps(event.data, default=str),
             event.timestamp),
        )
        self._db.commit()

        triggered = self._get_subscriptions(event.event_type)

        logger.info(
            f"Event published: {event.event_type} from {event.source_agent} "
            f"→ triggers {len(triggered)} subscription(s)"
        )

        # Fire in-process handlers
        for handler in self._handlers.get(event.event_type, []):
            try:
                handler(event)
            except Exception as exc:
                logger.error(f"Handler error for {event.event_type}: {exc}")

        return triggered

    def subscribe_handler(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """Register an in-process handler for an event type."""
        self._handlers.setdefault(event_type, []).append(handler)

    def _get_subscriptions(self, event_type: str) -> list[dict[str, str]]:
        rows = self._db.execute(
            "SELECT target_pipeline, target_agent, description FROM subscriptions "
            "WHERE event_type = ? AND active = 1",
            (event_type,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_pending_events(
        self, event_type: str | None = None, since: str | None = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get recent events, optionally filtered by type."""
        if event_type:
            rows = self._db.execute(
                "SELECT * FROM events WHERE event_type = ? ORDER BY timestamp DESC LIMIT ?",
                (event_type, limit),
            ).fetchall()
        elif since:
            rows = self._db.execute(
                "SELECT * FROM events WHERE timestamp > ? ORDER BY timestamp DESC LIMIT ?",
                (since, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [
            {**dict(r), "data": json.loads(r["data"]), "consumed_by": json.loads(r["consumed_by"])}
            for r in rows
        ]

    def mark_consumed(self, event_id: str, consumer: str) -> None:
        """Mark an event as consumed by a pipeline/agent."""
        row = self._db.execute(
            "SELECT consumed_by FROM events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if row:
            consumers = json.loads(row["consumed_by"])
            if consumer not in consumers:
                consumers.append(consumer)
                self._db.execute(
                    "UPDATE events SET consumed_by = ? WHERE event_id = ?",
                    (json.dumps(consumers), event_id),
                )
                self._db.commit()

    def get_subscriptions(self) -> list[dict[str, Any]]:
        """Return all active subscriptions (the wiring diagram)."""
        rows = self._db.execute(
            "SELECT event_type, target_pipeline, target_agent, description "
            "FROM subscriptions WHERE active = 1 ORDER BY event_type"
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        """Event bus statistics."""
        total = self._db.execute("SELECT COUNT(*) as c FROM events").fetchone()["c"]
        by_type = self._db.execute(
            "SELECT event_type, COUNT(*) as c FROM events GROUP BY event_type ORDER BY c DESC"
        ).fetchall()
        subs = self._db.execute(
            "SELECT COUNT(*) as c FROM subscriptions WHERE active = 1"
        ).fetchone()["c"]
        return {
            "total_events": total,
            "active_subscriptions": subs,
            "events_by_type": {r["event_type"]: r["c"] for r in by_type},
        }
