"""
Prompt Registry — version-controlled prompt governance for team consistency.

Solves the core problem: 5 people using LLMs probabilistically will produce
chaos unless prompts are treated as shared, reviewed, versioned artifacts.

Three layers of consistency:
  1. Prompt Pinning — every prompt has a hash; agents use the pinned version
  2. Prompt Review — changes require peer review (like code review)
  3. Output Validation — golden tests catch regressions from prompt changes

The registry tracks:
  - Every prompt version with hash, author, reviewer, approval status
  - Performance metrics per version (score, correction rate, tokens)
  - Review comments and approval history
  - A/B test results when two versions run side-by-side
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("pipeline.prompt_registry")

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"
DB_PATH = MEMORY_DIR / "prompt_registry.db"


def _init_db(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(textwrap.dedent("""\
        CREATE TABLE IF NOT EXISTS prompt_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_name TEXT NOT NULL,
            version_hash TEXT NOT NULL,
            content TEXT NOT NULL,
            author TEXT DEFAULT 'unknown',
            created_at TEXT NOT NULL,
            status TEXT DEFAULT 'draft',
            reviewer TEXT DEFAULT '',
            review_comment TEXT DEFAULT '',
            reviewed_at TEXT DEFAULT '',
            is_active INTEGER DEFAULT 0,
            UNIQUE(prompt_name, version_hash)
        );
        CREATE INDEX IF NOT EXISTS idx_pv_name ON prompt_versions(prompt_name);
        CREATE INDEX IF NOT EXISTS idx_pv_active ON prompt_versions(is_active);

        CREATE TABLE IF NOT EXISTS prompt_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_name TEXT NOT NULL,
            version_hash TEXT NOT NULL,
            run_count INTEGER DEFAULT 0,
            avg_tokens INTEGER DEFAULT 0,
            avg_score REAL DEFAULT 0.0,
            correction_rate REAL DEFAULT 0.0,
            last_used TEXT DEFAULT '',
            UNIQUE(prompt_name, version_hash)
        );

        CREATE TABLE IF NOT EXISTS prompt_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_name TEXT NOT NULL,
            version_hash TEXT NOT NULL,
            reviewer TEXT NOT NULL,
            action TEXT NOT NULL,
            comment TEXT DEFAULT '',
            timestamp TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ab_tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_name TEXT NOT NULL,
            version_a TEXT NOT NULL,
            version_b TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            score_a REAL DEFAULT 0.0,
            score_b REAL DEFAULT 0.0,
            winner TEXT DEFAULT '',
            timestamp TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS team_conventions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            convention TEXT NOT NULL,
            category TEXT DEFAULT '',
            rationale TEXT DEFAULT '',
            enforced_by TEXT DEFAULT 'manual',
            created_at TEXT NOT NULL
        );
    """))
    conn.commit()
    return conn


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


class PromptRegistry:
    """
    Centralized prompt management for team consistency.

    Every prompt used by any agent goes through this registry.
    This ensures:
    - All team members use the same prompt version
    - Changes are reviewed before activation
    - Performance is tracked per version
    - A/B tests compare versions with evidence
    """

    def __init__(self, db_path: Path | None = None):
        self._db = _init_db(db_path)
        self._scan_prompts_dir()

    def _scan_prompts_dir(self) -> None:
        """Auto-register any prompts in the prompts/ directory."""
        if not PROMPTS_DIR.exists():
            return
        for f in PROMPTS_DIR.glob("*.txt"):
            content = f.read_text()
            h = _hash_content(content)
            existing = self._db.execute(
                "SELECT id FROM prompt_versions WHERE prompt_name = ? AND version_hash = ?",
                (f.stem, h),
            ).fetchone()
            if not existing:
                now = datetime.now(timezone.utc).isoformat()
                self._db.execute(
                    "INSERT INTO prompt_versions (prompt_name, version_hash, content, "
                    "author, created_at, status, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (f.stem, h, content, "auto-scan", now, "active", 1),
                )
        self._db.commit()

    def register_version(
        self, prompt_name: str, content: str, author: str,
    ) -> dict[str, str]:
        """Register a new prompt version. Returns hash and status."""
        h = _hash_content(content)
        now = datetime.now(timezone.utc).isoformat()

        existing = self._db.execute(
            "SELECT id, status FROM prompt_versions WHERE prompt_name = ? AND version_hash = ?",
            (prompt_name, h),
        ).fetchone()

        if existing:
            return {"hash": h, "status": existing["status"], "action": "already_exists"}

        self._db.execute(
            "INSERT INTO prompt_versions (prompt_name, version_hash, content, "
            "author, created_at, status, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (prompt_name, h, content, author, now, "pending_review", 0),
        )
        self._db.commit()
        return {"hash": h, "status": "pending_review", "action": "registered"}

    def review_prompt(
        self, prompt_name: str, version_hash: str,
        reviewer: str, action: str, comment: str = "",
    ) -> dict[str, str]:
        """
        Review a prompt version. Actions: approve, reject, request_changes.
        Only approved prompts can be activated.
        """
        now = datetime.now(timezone.utc).isoformat()

        if action not in ("approve", "reject", "request_changes"):
            return {"error": f"Invalid action: {action}"}

        # Record the review
        self._db.execute(
            "INSERT INTO prompt_reviews (prompt_name, version_hash, reviewer, "
            "action, comment, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (prompt_name, version_hash, reviewer, action, comment, now),
        )

        # Update prompt status
        new_status = {
            "approve": "approved",
            "reject": "rejected",
            "request_changes": "changes_requested",
        }[action]

        self._db.execute(
            "UPDATE prompt_versions SET status = ?, reviewer = ?, review_comment = ?, "
            "reviewed_at = ? WHERE prompt_name = ? AND version_hash = ?",
            (new_status, reviewer, comment, now, prompt_name, version_hash),
        )
        self._db.commit()

        return {"status": new_status, "reviewer": reviewer}

    def activate_version(self, prompt_name: str, version_hash: str) -> dict[str, str]:
        """
        Activate a prompt version (must be approved first).
        Deactivates the previously active version.
        """
        row = self._db.execute(
            "SELECT status FROM prompt_versions WHERE prompt_name = ? AND version_hash = ?",
            (prompt_name, version_hash),
        ).fetchone()

        if not row:
            return {"error": "Version not found"}
        if row["status"] not in ("approved", "active"):
            return {"error": f"Cannot activate — status is '{row['status']}'. Must be approved first."}

        # Deactivate all other versions
        self._db.execute(
            "UPDATE prompt_versions SET is_active = 0 WHERE prompt_name = ?",
            (prompt_name,),
        )
        # Activate this one
        self._db.execute(
            "UPDATE prompt_versions SET is_active = 1, status = 'active' "
            "WHERE prompt_name = ? AND version_hash = ?",
            (prompt_name, version_hash),
        )
        self._db.commit()

        # Also write to the prompts/ directory
        PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
        content = self._db.execute(
            "SELECT content FROM prompt_versions WHERE prompt_name = ? AND version_hash = ?",
            (prompt_name, version_hash),
        ).fetchone()["content"]
        (PROMPTS_DIR / f"{prompt_name}.txt").write_text(content)

        return {"status": "active", "hash": version_hash}

    def get_active_prompt(self, prompt_name: str) -> dict[str, Any] | None:
        """Get the currently active (pinned) prompt version."""
        row = self._db.execute(
            "SELECT * FROM prompt_versions WHERE prompt_name = ? AND is_active = 1",
            (prompt_name,),
        ).fetchone()
        return dict(row) if row else None

    def get_version_history(self, prompt_name: str) -> list[dict]:
        """Full version history for a prompt."""
        rows = self._db.execute(
            "SELECT prompt_name, version_hash, author, status, reviewer, "
            "review_comment, created_at, reviewed_at, is_active "
            "FROM prompt_versions WHERE prompt_name = ? ORDER BY created_at DESC",
            (prompt_name,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_reviews(self, prompt_name: str, version_hash: str = "") -> list[dict]:
        """Get review history for a prompt."""
        if version_hash:
            rows = self._db.execute(
                "SELECT * FROM prompt_reviews WHERE prompt_name = ? AND version_hash = ? "
                "ORDER BY timestamp DESC",
                (prompt_name, version_hash),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM prompt_reviews WHERE prompt_name = ? ORDER BY timestamp DESC",
                (prompt_name,),
            ).fetchall()
        return [dict(r) for r in rows]

    def record_ab_test(
        self, prompt_name: str, version_a: str, version_b: str,
        input_hash: str, score_a: float, score_b: float,
    ) -> dict:
        """Record an A/B test result between two prompt versions."""
        winner = "a" if score_a > score_b else "b" if score_b > score_a else "tie"
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            "INSERT INTO ab_tests (prompt_name, version_a, version_b, "
            "input_hash, score_a, score_b, winner, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (prompt_name, version_a, version_b, input_hash, score_a, score_b, winner, now),
        )
        self._db.commit()
        return {"winner": winner, "score_a": score_a, "score_b": score_b}

    def get_ab_results(self, prompt_name: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM ab_tests WHERE prompt_name = ? ORDER BY timestamp DESC",
            (prompt_name,),
        ).fetchall()
        return [dict(r) for r in rows]

    def record_metrics(
        self, prompt_name: str, version_hash: str,
        tokens: int = 0, score: float = 0.0, corrected: bool = False,
    ) -> None:
        """Record usage metrics for a prompt version."""
        existing = self._db.execute(
            "SELECT run_count, avg_tokens, avg_score, correction_rate "
            "FROM prompt_metrics WHERE prompt_name = ? AND version_hash = ?",
            (prompt_name, version_hash),
        ).fetchone()

        now = datetime.now(timezone.utc).isoformat()

        if existing:
            n = existing["run_count"]
            new_avg_tokens = int((existing["avg_tokens"] * n + tokens) / (n + 1))
            new_avg_score = (existing["avg_score"] * n + score) / (n + 1)
            corrections = existing["correction_rate"] * n + (1 if corrected else 0)
            new_correction_rate = corrections / (n + 1)
            self._db.execute(
                "UPDATE prompt_metrics SET run_count = ?, avg_tokens = ?, avg_score = ?, "
                "correction_rate = ?, last_used = ? WHERE prompt_name = ? AND version_hash = ?",
                (n + 1, new_avg_tokens, round(new_avg_score, 4),
                 round(new_correction_rate, 4), now, prompt_name, version_hash),
            )
        else:
            self._db.execute(
                "INSERT INTO prompt_metrics (prompt_name, version_hash, run_count, "
                "avg_tokens, avg_score, correction_rate, last_used) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (prompt_name, version_hash, 1, tokens, round(score, 4),
                 1.0 if corrected else 0.0, now),
            )
        self._db.commit()

    def get_all_prompts(self) -> list[dict]:
        """Summary of all registered prompts with their active versions."""
        rows = self._db.execute(
            "SELECT prompt_name, version_hash, author, status, reviewer, "
            "created_at, reviewed_at, is_active FROM prompt_versions "
            "ORDER BY prompt_name, created_at DESC"
        ).fetchall()

        prompts: dict[str, list] = {}
        for r in rows:
            prompts.setdefault(r["prompt_name"], []).append(dict(r))

        result = []
        for name, versions in prompts.items():
            active = next((v for v in versions if v["is_active"]), None)
            metrics_row = self._db.execute(
                "SELECT * FROM prompt_metrics WHERE prompt_name = ? AND version_hash = ?",
                (name, active["version_hash"] if active else ""),
            ).fetchone()

            result.append({
                "prompt_name": name,
                "active_version": active["version_hash"] if active else None,
                "active_author": active["author"] if active else None,
                "total_versions": len(versions),
                "status": active["status"] if active else versions[0]["status"],
                "metrics": dict(metrics_row) if metrics_row else None,
            })
        return result

    def stats(self) -> dict[str, Any]:
        total_prompts = self._db.execute(
            "SELECT COUNT(DISTINCT prompt_name) as c FROM prompt_versions"
        ).fetchone()["c"]
        total_versions = self._db.execute(
            "SELECT COUNT(*) as c FROM prompt_versions"
        ).fetchone()["c"]
        total_reviews = self._db.execute(
            "SELECT COUNT(*) as c FROM prompt_reviews"
        ).fetchone()["c"]
        total_ab = self._db.execute(
            "SELECT COUNT(*) as c FROM ab_tests"
        ).fetchone()["c"]
        by_status = self._db.execute(
            "SELECT status, COUNT(*) as c FROM prompt_versions GROUP BY status"
        ).fetchall()
        return {
            "total_prompts": total_prompts,
            "total_versions": total_versions,
            "total_reviews": total_reviews,
            "total_ab_tests": total_ab,
            "by_status": {r["status"]: r["c"] for r in by_status},
        }


def seed_team_conventions(db_path: Path | None = None) -> None:
    """
    Seed the team conventions that enforce systematic operation.
    These are the rules all team members follow.
    """
    conn = _init_db(db_path)
    now = datetime.now(timezone.utc).isoformat()

    conventions = [
        (
            "All prompts must be stored in /prompts/ as .txt files, never inline in code",
            "prompt_management",
            "Inline prompts are invisible to the team. Centralized storage enables review, versioning, and regression testing.",
            "prompt_registry scan",
        ),
        (
            "Every prompt change requires peer review before activation",
            "prompt_management",
            "LLMs are probabilistic — a 'small' prompt tweak can drastically change output quality. Review catches regressions the author didn't test for.",
            "prompt_registry review workflow",
        ),
        (
            "Use temperature=0 for all deterministic tasks (parsing, classification, extraction)",
            "reproducibility",
            "Temperature >0 means different outputs on the same input. For engineering artifacts, we need consistency across team members and runs.",
            "BaseAgent call_claude() default",
        ),
        (
            "Every LLM-generated artifact must have provenance metadata (agent, prompt version, timestamp, model)",
            "traceability",
            "If an artifact is wrong, we need to know which prompt version produced it so we can fix the root cause, not just the symptom.",
            "MetricsCollector automatic tracking",
        ),
        (
            "Human-in-the-loop required for all P0 items and architectural decisions",
            "quality_gate",
            "AI draft → human approve. Never auto-ship P0 requirements or ADRs. The cost of a wrong P0 decision exceeds the time saved by automation.",
            "pipeline step configuration",
        ),
        (
            "Golden test cases required for every prompt in /prompts/",
            "regression",
            "Without golden tests, prompt changes are untested. Golden tests are the unit tests of prompt engineering.",
            "prompt_regression agent on PR",
        ),
        (
            "All agents run offline-first, Claude-powered as an upgrade",
            "resilience",
            "System must work without API key (demo resilience, cost control). Offline results establish a baseline for measuring Claude's improvement.",
            "BaseAgent offline fallback pattern",
        ),
        (
            "Meeting outputs are deposited to SharedMemory wiki, not just logged to files",
            "knowledge_management",
            "Files are dead. The wiki is alive — queryable, cross-referenceable, and grows smarter with every meeting.",
            "BaseAgent.wiki integration",
        ),
        (
            "Cross-pipeline events for significant outputs, not direct function calls",
            "architecture",
            "Direct coupling between pipelines creates a maintenance nightmare. Events decouple producers from consumers.",
            "EventBus subscription model",
        ),
        (
            "Weekly review of measurement dashboard by SES team (Jai, Hrishik, Ashritha)",
            "process_improvement",
            "The meta-model says 'process improvement is reliant on improving AI components/systems.' Can't improve what you don't inspect.",
            "manual team practice",
        ),
    ]

    for conv, cat, rationale, enforced in conventions:
        conn.execute(
            "INSERT OR IGNORE INTO team_conventions (convention, category, rationale, enforced_by, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (conv, cat, rationale, enforced, now),
        )
    conn.commit()
