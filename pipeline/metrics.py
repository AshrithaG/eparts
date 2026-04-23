"""
Metrics Collector — the evidence engine for the SES.

Captures every measurable signal from agent operations:
  - Per-LLM-call: model, tokens in/out, latency, prompt file, temperature
  - Per-agent-run: duration, success/fail, outputs, human review needed
  - Per-prompt: version hash, effectiveness score, correction count
  - Aggregates: token costs, re-prompt rates, time saved, velocity

SQLite-backed for queryability. Every metric maps to the meta-model:
  Resource (which agent/model) implements Process (which activity),
  generating Artifacts (outputs), measured by these metrics.

This is what Christian wants to see: evidence-based AI effectiveness.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import textwrap
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
METRICS_DB = PROJECT_ROOT / "pipeline" / "metrics.db"

# Approximate costs per 1M tokens (USD) — for cost tracking
TOKEN_COSTS = {
    "claude-sonnet-4-5-20250514": {"input": 3.00, "output": 15.00},
    "claude-opus-4-5": {"input": 15.00, "output": 75.00},
}


@dataclass
class LLMCallMetric:
    agent: str
    run_id: str
    model: str
    prompt_file: str  # which prompt template was used (or "inline")
    input_tokens: int
    output_tokens: int
    latency_ms: int
    temperature: float
    attempt: int  # which retry attempt succeeded
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        rates = TOKEN_COSTS.get(self.model, {"input": 3.0, "output": 15.0})
        return (
            self.input_tokens / 1_000_000 * rates["input"]
            + self.output_tokens / 1_000_000 * rates["output"]
        )


@dataclass
class AgentRunMetric:
    run_id: str
    agent: str
    trigger_type: str
    trigger_source: str
    success: bool
    duration_ms: int
    llm_calls: int
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float
    outputs_count: int
    requires_human_review: bool
    errors: list[str] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class PromptMetric:
    prompt_file: str
    content_hash: str  # SHA-256 of prompt content for version tracking
    times_used: int = 0
    avg_output_tokens: float = 0.0
    avg_latency_ms: float = 0.0
    correction_count: int = 0  # times human corrected the output


def init_metrics_db(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or METRICS_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(textwrap.dedent("""\
        CREATE TABLE IF NOT EXISTS llm_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            agent TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_file TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            total_tokens INTEGER,
            latency_ms INTEGER,
            temperature REAL,
            attempt INTEGER,
            estimated_cost_usd REAL,
            timestamp TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agent_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT UNIQUE NOT NULL,
            agent TEXT NOT NULL,
            trigger_type TEXT,
            trigger_source TEXT,
            success INTEGER,
            duration_ms INTEGER,
            llm_calls INTEGER,
            total_input_tokens INTEGER,
            total_output_tokens INTEGER,
            estimated_cost_usd REAL,
            outputs_count INTEGER,
            requires_human_review INTEGER,
            errors TEXT,
            timestamp TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS prompt_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_file TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            first_seen TEXT NOT NULL,
            UNIQUE(prompt_file, content_hash)
        );

        CREATE TABLE IF NOT EXISTS human_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            agent TEXT,
            correction_type TEXT,
            description TEXT,
            timestamp TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_llm_calls_agent ON llm_calls(agent);
        CREATE INDEX IF NOT EXISTS idx_llm_calls_run ON llm_calls(run_id);
        CREATE INDEX IF NOT EXISTS idx_agent_runs_agent ON agent_runs(agent);
        CREATE INDEX IF NOT EXISTS idx_agent_runs_ts ON agent_runs(timestamp);
    """))
    conn.commit()
    return conn


class MetricsCollector:
    """
    Collects and stores all metrics from agent operations.
    Thread-safe via SQLite's built-in locking.
    """

    def __init__(self, db_path: Path | None = None):
        self._db = init_metrics_db(db_path)

    def record_llm_call(self, metric: LLMCallMetric) -> None:
        self._db.execute(
            "INSERT INTO llm_calls "
            "(run_id, agent, model, prompt_file, input_tokens, output_tokens, "
            "total_tokens, latency_ms, temperature, attempt, estimated_cost_usd, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                metric.run_id, metric.agent, metric.model, metric.prompt_file,
                metric.input_tokens, metric.output_tokens, metric.total_tokens,
                metric.latency_ms, metric.temperature, metric.attempt,
                metric.estimated_cost_usd, metric.timestamp,
            ),
        )
        self._db.commit()

    def record_agent_run(self, metric: AgentRunMetric) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO agent_runs "
            "(run_id, agent, trigger_type, trigger_source, success, duration_ms, "
            "llm_calls, total_input_tokens, total_output_tokens, estimated_cost_usd, "
            "outputs_count, requires_human_review, errors, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                metric.run_id, metric.agent, metric.trigger_type,
                metric.trigger_source, int(metric.success), metric.duration_ms,
                metric.llm_calls, metric.total_input_tokens, metric.total_output_tokens,
                metric.estimated_cost_usd, metric.outputs_count,
                int(metric.requires_human_review), json.dumps(metric.errors),
                metric.timestamp,
            ),
        )
        self._db.commit()

    def track_prompt_version(self, prompt_file: str, content: str) -> str:
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            "INSERT OR IGNORE INTO prompt_versions (prompt_file, content_hash, first_seen) "
            "VALUES (?, ?, ?)",
            (prompt_file, content_hash, now),
        )
        self._db.commit()
        return content_hash

    def record_human_correction(
        self, run_id: str, agent: str, correction_type: str, description: str
    ) -> None:
        self._db.execute(
            "INSERT INTO human_corrections (run_id, agent, correction_type, description, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, agent, correction_type, description,
             datetime.now(timezone.utc).isoformat()),
        )
        self._db.commit()

    # ------ Query methods for dashboard ------

    def summary(self) -> dict[str, Any]:
        """High-level metrics summary across all agents."""
        runs = self._db.execute(
            "SELECT COUNT(*) as total, SUM(success) as succeeded, "
            "SUM(duration_ms) as total_duration, SUM(llm_calls) as total_llm_calls, "
            "SUM(total_input_tokens) as total_input, SUM(total_output_tokens) as total_output, "
            "SUM(estimated_cost_usd) as total_cost, "
            "SUM(requires_human_review) as needed_review "
            "FROM agent_runs"
        ).fetchone()

        corrections = self._db.execute(
            "SELECT COUNT(*) as total FROM human_corrections"
        ).fetchone()

        return {
            "total_runs": runs["total"] or 0,
            "successful_runs": runs["succeeded"] or 0,
            "failure_rate": 1 - (runs["succeeded"] or 0) / max(runs["total"] or 1, 1),
            "total_duration_ms": runs["total_duration"] or 0,
            "total_llm_calls": runs["total_llm_calls"] or 0,
            "total_input_tokens": runs["total_input"] or 0,
            "total_output_tokens": runs["total_output"] or 0,
            "total_tokens": (runs["total_input"] or 0) + (runs["total_output"] or 0),
            "estimated_cost_usd": round(runs["total_cost"] or 0, 4),
            "runs_needing_review": runs["needed_review"] or 0,
            "human_corrections": corrections["total"] or 0,
            "review_rate": (runs["needed_review"] or 0) / max(runs["total"] or 1, 1),
        }

    def per_agent_summary(self) -> list[dict[str, Any]]:
        """Metrics broken down by agent."""
        rows = self._db.execute(
            "SELECT agent, COUNT(*) as runs, SUM(success) as succeeded, "
            "AVG(duration_ms) as avg_duration, SUM(llm_calls) as total_llm_calls, "
            "SUM(total_input_tokens + total_output_tokens) as total_tokens, "
            "SUM(estimated_cost_usd) as total_cost, "
            "SUM(requires_human_review) as needed_review "
            "FROM agent_runs GROUP BY agent ORDER BY runs DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def per_prompt_summary(self) -> list[dict[str, Any]]:
        """Metrics broken down by prompt template."""
        rows = self._db.execute(
            "SELECT prompt_file, COUNT(*) as uses, "
            "AVG(output_tokens) as avg_output_tokens, "
            "AVG(latency_ms) as avg_latency_ms, "
            "SUM(estimated_cost_usd) as total_cost "
            "FROM llm_calls WHERE prompt_file != 'inline' "
            "GROUP BY prompt_file ORDER BY uses DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def token_usage_timeseries(self, days: int = 30) -> list[dict[str, Any]]:
        """Daily token usage for time-series charts."""
        rows = self._db.execute(
            "SELECT DATE(timestamp) as date, "
            "SUM(input_tokens) as input_tokens, "
            "SUM(output_tokens) as output_tokens, "
            "SUM(estimated_cost_usd) as cost, "
            "COUNT(*) as calls "
            "FROM llm_calls "
            "GROUP BY DATE(timestamp) ORDER BY date DESC LIMIT ?",
            (days,),
        ).fetchall()
        return [dict(r) for r in rows]

    def recent_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        """Most recent agent runs for the activity feed."""
        rows = self._db.execute(
            "SELECT * FROM agent_runs ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def prompt_version_history(self) -> list[dict[str, Any]]:
        """Track which prompt versions have been used."""
        rows = self._db.execute(
            "SELECT * FROM prompt_versions ORDER BY first_seen DESC"
        ).fetchall()
        return [dict(r) for r in rows]
