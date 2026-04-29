"""
Artifact Versioning — maintains version history for key project documents.

Final deliverables (requirements doc, architecture doc, ADRs, risk register)
need version history to show *evolution*: "these 5 meetings and 3 coach sessions
led to this final document."

Each version snapshot records:
  - version number (semantic: major.minor)
  - timestamp
  - what changed (diff summary)
  - which agent or human triggered the change
  - which meetings/sessions contributed

Storage: memory/artifact_versions.db
"""
from __future__ import annotations

import json
import logging
import sqlite3
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("pipeline.artifact_versioning")

MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"
DB_PATH = MEMORY_DIR / "artifact_versions.db"


def _init_db(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(textwrap.dedent("""\
        CREATE TABLE IF NOT EXISTS artifacts (
            artifact_name TEXT PRIMARY KEY,
            artifact_type TEXT NOT NULL,
            description TEXT DEFAULT '',
            current_version TEXT DEFAULT '0.0',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artifact_name TEXT NOT NULL,
            version TEXT NOT NULL,
            content TEXT NOT NULL,
            change_summary TEXT DEFAULT '',
            changed_by TEXT DEFAULT '',
            trigger_source TEXT DEFAULT '',
            contributing_meetings TEXT DEFAULT '[]',
            contributing_sessions TEXT DEFAULT '[]',
            metadata TEXT DEFAULT '{}',
            timestamp TEXT NOT NULL,
            FOREIGN KEY (artifact_name) REFERENCES artifacts(artifact_name),
            UNIQUE(artifact_name, version)
        );
        CREATE INDEX IF NOT EXISTS idx_ver_artifact ON versions(artifact_name);
        CREATE INDEX IF NOT EXISTS idx_ver_ts ON versions(timestamp);
    """))
    conn.commit()
    return conn


class ArtifactVersionStore:
    """Track versioned evolution of key project documents."""

    def __init__(self, db_path: Path | None = None):
        self._db = _init_db(db_path)

    def register_artifact(
        self, name: str, artifact_type: str, description: str = ""
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            "INSERT OR IGNORE INTO artifacts (artifact_name, artifact_type, description, "
            "current_version, created_at, updated_at) VALUES (?, ?, ?, '0.0', ?, ?)",
            (name, artifact_type, description, now, now),
        )
        self._db.commit()

    def add_version(
        self,
        artifact_name: str,
        content: str,
        change_summary: str = "",
        changed_by: str = "",
        trigger_source: str = "",
        contributing_meetings: list[str] | None = None,
        contributing_sessions: list[str] | None = None,
        major: bool = False,
        metadata: dict | None = None,
    ) -> str:
        """Add a new version. Returns the version string (e.g., '1.3')."""
        now = datetime.now(timezone.utc).isoformat()

        row = self._db.execute(
            "SELECT current_version FROM artifacts WHERE artifact_name = ?",
            (artifact_name,),
        ).fetchone()

        if not row:
            self.register_artifact(artifact_name, "document")
            current = "0.0"
        else:
            current = row["current_version"]

        parts = current.split(".")
        maj, minor = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        if major:
            new_version = f"{maj + 1}.0"
        else:
            new_version = f"{maj}.{minor + 1}"

        self._db.execute(
            "INSERT OR REPLACE INTO versions (artifact_name, version, content, "
            "change_summary, changed_by, trigger_source, contributing_meetings, "
            "contributing_sessions, metadata, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (artifact_name, new_version, content, change_summary, changed_by,
             trigger_source, json.dumps(contributing_meetings or []),
             json.dumps(contributing_sessions or []), json.dumps(metadata or {}), now),
        )

        self._db.execute(
            "UPDATE artifacts SET current_version = ?, updated_at = ? "
            "WHERE artifact_name = ?",
            (new_version, now, artifact_name),
        )
        self._db.commit()
        return new_version

    def get_versions(self, artifact_name: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM versions WHERE artifact_name = ? ORDER BY id ASC",
            (artifact_name,),
        ).fetchall()
        return [
            {
                **dict(r),
                "contributing_meetings": json.loads(r["contributing_meetings"]),
                "contributing_sessions": json.loads(r["contributing_sessions"]),
                "metadata": json.loads(r["metadata"]),
            }
            for r in rows
        ]

    def get_latest(self, artifact_name: str) -> dict | None:
        row = self._db.execute(
            "SELECT * FROM versions WHERE artifact_name = ? ORDER BY id DESC LIMIT 1",
            (artifact_name,),
        ).fetchone()
        if row:
            d = dict(row)
            d["contributing_meetings"] = json.loads(d["contributing_meetings"])
            d["contributing_sessions"] = json.loads(d["contributing_sessions"])
            d["metadata"] = json.loads(d["metadata"])
            return d
        return None

    def get_all_artifacts(self) -> list[dict]:
        rows = self._db.execute(
            "SELECT a.*, COUNT(v.id) as version_count "
            "FROM artifacts a LEFT JOIN versions v ON a.artifact_name = v.artifact_name "
            "GROUP BY a.artifact_name ORDER BY a.updated_at DESC",
        ).fetchall()
        return [dict(r) for r in rows]

    def get_evolution_story(self, artifact_name: str) -> str:
        """Generate a human-readable evolution narrative for a document."""
        versions = self.get_versions(artifact_name)
        if not versions:
            return f"No version history for '{artifact_name}'."

        lines = [f"# Evolution of {artifact_name}\n"]
        for v in versions:
            ts = v["timestamp"][:10]
            lines.append(f"## Version {v['version']} ({ts})")
            if v["change_summary"]:
                lines.append(f"**Change:** {v['change_summary']}")
            if v["changed_by"]:
                lines.append(f"**By:** {v['changed_by']}")
            if v["trigger_source"]:
                lines.append(f"**Triggered by:** {v['trigger_source']}")
            meetings = v["contributing_meetings"]
            sessions = v["contributing_sessions"]
            if meetings:
                lines.append(f"**Contributing meetings:** {', '.join(meetings)}")
            if sessions:
                lines.append(f"**Contributing sessions:** {', '.join(sessions)}")
            lines.append("")
        return "\n".join(lines)


def seed_artifact_versions(db_path: Path | None = None) -> ArtifactVersionStore:
    """Seed version history for key project documents from existing data."""
    store = ArtifactVersionStore(db_path)

    store.register_artifact(
        "requirements_document", "requirements",
        "Consolidated requirements specification for eParts ML catalog system"
    )
    store.register_artifact(
        "architecture_document", "architecture",
        "Software architecture document for eParts data pipeline"
    )
    store.register_artifact(
        "risk_register", "risk",
        "Project risk register with severity, likelihood, and mitigations"
    )
    store.register_artifact(
        "adr_threshold_calibration", "adr",
        "ADR: ML confidence threshold calibration approach"
    )
    store.register_artifact(
        "adr_staging_tables", "adr",
        "ADR: Staging tables for vendor data ingestion"
    )
    store.register_artifact(
        "adr_human_in_loop", "adr",
        "ADR: Human-in-the-loop review workflow design"
    )

    # Requirements Document evolution
    store.add_version(
        "requirements_document",
        content="Initial scope: ML extraction from vendor spec sheets. Key needs identified: accuracy, scalability, vendor format variation.",
        change_summary="Initial scope from project kickoff meeting. Client described the problem: manual attribute extraction is slow and error-prone.",
        changed_by="transcript_parser",
        trigger_source="Client Meeting 1 (Jan 22)",
        contributing_meetings=["Meeting 2026-01-22"],
    )
    store.add_version(
        "requirements_document",
        content="Added: confidence scoring requirement (REQ-003), human-in-the-loop for low-confidence (REQ-005). Clarified: primary approach is LLM, not OCR.",
        change_summary="Client emphasized need for confidence scores on every prediction. Team decided LLM extraction over OCR approach.",
        changed_by="req_extractor",
        trigger_source="Client Meeting 2 (Feb 05)",
        contributing_meetings=["Meeting 2026-02-05"],
    )
    store.add_version(
        "requirements_document",
        content="Added: multi-vendor format support (REQ-008), PIMS integration requirement (REQ-010). Refined priority: confidence thresholds are P0.",
        change_summary="Deep-dive with catalog team revealed vendor format variation is a major risk. PIMS writeback is a hard requirement.",
        changed_by="req_extractor",
        trigger_source="Client Meeting 3 (Feb 19)",
        contributing_meetings=["Meeting 2026-02-19"],
    )
    store.add_version(
        "requirements_document",
        content="Added: batch processing requirement (REQ-011), monitoring/alerting (REQ-012). Coach flagged: need measurable acceptance criteria for each REQ.",
        change_summary="Coach Christian emphasized measurability. Added explicit acceptance criteria to REQ-001 through REQ-008.",
        changed_by="req_extractor",
        trigger_source="Coach Session (Christian Feb 20) + Client Meeting 4",
        contributing_meetings=["Meeting 2026-03-05"],
        contributing_sessions=["Christian 2026-02-20"],
    )
    store.add_version(
        "requirements_document",
        content="Consolidated 12 formal requirements (REQ-001 to REQ-012) with traceability to source meetings, architecture decisions, and Jira tickets.",
        change_summary="Final consolidation. All 12 requirements now traced: meeting → concern → decision → requirement → Jira ticket.",
        changed_by="traceability_builder",
        trigger_source="Traceability Store seeding + Client Meeting 5",
        contributing_meetings=["Meeting 2026-01-22", "Meeting 2026-02-05", "Meeting 2026-02-19", "Meeting 2026-03-05", "Meeting 2026-03-19"],
        contributing_sessions=["Christian 2026-02-20", "Ben 2026-03-10"],
        major=True,
    )

    # Architecture Document evolution
    store.add_version(
        "architecture_document",
        content="Initial architecture: ingest → predict → route → writeback pipeline. Key decision: LLM-first extraction, PIMS integration via API.",
        change_summary="Initial architecture sketched after Meeting 1. Core pipeline structure defined.",
        changed_by="adr_generator",
        trigger_source="Client Meeting 1 (Jan 22)",
        contributing_meetings=["Meeting 2026-01-22"],
    )
    store.add_version(
        "architecture_document",
        content="Added: staging tables for vendor data (ARCH-004), confidence threshold calibration component (ARCH-003).",
        change_summary="Vendor data variation requires staging tables before ML processing. Confidence scoring needs dedicated calibration component.",
        changed_by="adr_generator",
        trigger_source="Client Meeting 2 (Feb 05) + drift_detector flag",
        contributing_meetings=["Meeting 2026-02-05"],
    )
    store.add_version(
        "architecture_document",
        content="Added: human-in-the-loop review workflow (ARCH-005), map to industry standards not ALPS (ARCH-002).",
        change_summary="Client explicitly said: map to industry standards, not ALPS codes. Added review workflow for low-confidence predictions.",
        changed_by="adr_generator",
        trigger_source="Client Meeting 3 (Feb 19)",
        contributing_meetings=["Meeting 2026-02-19"],
    )
    store.add_version(
        "architecture_document",
        content="Final architecture: 6 architecture decisions (ARCH-001 to ARCH-006), all with ADRs. Canonical architecture report ingested into ChromaDB for drift detection.",
        change_summary="Architecture report finalized and indexed. All future meeting decisions will be compared against this canonical version.",
        changed_by="drift_detector",
        trigger_source="Architecture Report finalization",
        contributing_meetings=["Meeting 2026-01-22", "Meeting 2026-02-05", "Meeting 2026-02-19", "Meeting 2026-03-05"],
        contributing_sessions=["Jim 2026-03-15"],
        major=True,
    )

    # Risk Register evolution
    store.add_version(
        "risk_register",
        content="Initial risks: data quality, vendor format variation, team capacity (5 people).",
        change_summary="Initial risk identification from project overview and first meeting.",
        changed_by="seed_risk_register",
        trigger_source="Project kickoff",
        contributing_meetings=["Meeting 2026-01-22"],
    )
    store.add_version(
        "risk_register",
        content="Added: confidence threshold miscalibration (from coach Dennis), PIMS schema changes (from client meeting).",
        change_summary="Dennis coaching session flagged ML-specific risks. Client revealed PIMS schema may change.",
        changed_by="seed_risk_register",
        trigger_source="Coach Session (Dennis) + Client Meeting 3",
        contributing_meetings=["Meeting 2026-02-19"],
        contributing_sessions=["Dennis 2026-03-20"],
    )
    store.add_version(
        "risk_register",
        content="16 risks identified. All have mitigations linked to requirements. Risk-to-requirement mapping in traceability store.",
        change_summary="Full risk register seeded from architecture report, coach sessions, and meeting analysis. All risks linked to mitigating requirements.",
        changed_by="traceability_builder",
        trigger_source="Traceability Store seeding",
        contributing_meetings=["Meeting 2026-01-22", "Meeting 2026-02-05", "Meeting 2026-02-19", "Meeting 2026-03-05", "Meeting 2026-03-19"],
        contributing_sessions=["Dennis 2026-03-20", "Ben 2026-03-10"],
        major=True,
    )

    # ADR: Threshold calibration
    store.add_version(
        "adr_threshold_calibration",
        content="Problem: How to set confidence thresholds for ML predictions? Status: OPEN.",
        change_summary="Decision opened after client emphasized accuracy concerns in Meeting 2.",
        changed_by="adr_generator",
        trigger_source="Client Meeting 2 (Feb 05)",
        contributing_meetings=["Meeting 2026-02-05"],
    )
    store.add_version(
        "adr_threshold_calibration",
        content="Decision: Per-attribute thresholds calibrated on holdout set. Not a single global threshold. Status: DECIDED.",
        change_summary="After POC results showed wide variance across attribute types, team decided per-attribute calibration.",
        changed_by="adr_generator",
        trigger_source="POC results + Client Meeting 4",
        contributing_meetings=["Meeting 2026-03-05"],
        contributing_sessions=["Christian 2026-02-20"],
        major=True,
    )

    logger.info(
        f"Seeded artifact versions: {len(store.get_all_artifacts())} artifacts"
    )
    return store
