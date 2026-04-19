"""
Persistent Session Memory — RAG over all past coach/mentor sessions.

Embeds session transcripts into ChromaDB. On each new session, retrieves
semantically relevant past context before generating any outputs.

Triggered by: coach_transcript event (new transcript uploaded)
Outputs: session record in SQLite, chunks embedded in vector store

This is eParts-specific: requires the CMU coached capstone structure
with recurring sessions with Christian Kastner and mentors.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent
from mcp.vector_store import COLLECTION_SESSIONS, VectorStoreMCP

logger = logging.getLogger("agent.session_memory")

MEMORY_DIR = Path(__file__).resolve().parent.parent.parent / "memory"
DB_PATH = MEMORY_DIR / "coach_sessions.db"

CHUNK_SIZE = 800  # characters per chunk
CHUNK_OVERLAP = 100


def init_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Create the coach sessions SQLite schema if it doesn't exist."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(textwrap.dedent("""\
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            date TEXT,
            session_type TEXT,
            participants TEXT,
            raw_transcript_path TEXT,
            processed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS commitments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            commitment_text TEXT,
            owner TEXT,
            deadline TEXT,
            status TEXT DEFAULT 'open',
            evidence_link TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        );

        CREATE TABLE IF NOT EXISTS concerns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            concern_text TEXT,
            raised_by TEXT,
            theme TEXT,
            times_raised INTEGER DEFAULT 1,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        );
    """))
    conn.commit()
    return conn


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks for embedding."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap

    return chunks


class SessionMemoryAgent(BaseAgent):
    """
    Ingests coach/mentor session transcripts into the persistent memory store.

    Flow:
    1. Parse the transcript to extract metadata (date, participants, type)
    2. Chunk the transcript text
    3. Embed and store chunks in ChromaDB
    4. Store session record in SQLite
    5. Use Claude to extract structured data (decisions, commitments, concerns)
    """

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="session_memory", mcp_clients=mcp_clients)
        self._db = init_db()
        self._vector_store: VectorStoreMCP = (
            mcp_clients.get("vector_store") if mcp_clients else None
        ) or VectorStoreMCP()

    def run(self, trigger: AgentTrigger) -> AgentResult:
        source = trigger.source
        metadata = trigger.metadata

        transcript_path = Path(source)
        if not transcript_path.exists():
            return AgentResult(
                agent=self.name,
                success=False,
                errors=[f"Transcript file not found: {source}"],
            )

        raw_text = transcript_path.read_text(encoding="utf-8")

        session_id = metadata.get(
            "session_id",
            f"session-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        )
        session_type = metadata.get("session_type", "coach")
        date = metadata.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        participants = metadata.get("participants", [])

        # 1. Store session metadata in SQLite
        self._db.execute(
            "INSERT OR REPLACE INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
            (
                session_id,
                date,
                session_type,
                json.dumps(participants),
                str(transcript_path),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._db.commit()

        # 2. Chunk and embed the transcript
        chunks = chunk_text(raw_text)
        chunk_ids = [f"{session_id}-chunk-{i}" for i in range(len(chunks))]
        chunk_metadatas = [
            {
                "session_id": session_id,
                "session_type": session_type,
                "date": date,
                "chunk_index": i,
            }
            for i in range(len(chunks))
        ]

        stored = self._vector_store.embed_and_store(
            collection_name=COLLECTION_SESSIONS,
            documents=chunks,
            metadatas=chunk_metadatas,
            ids=chunk_ids,
        )

        # 3. Use Claude to extract structured data from the transcript
        extraction = self._extract_session_data(raw_text, session_id, date)

        outputs = [
            AgentOutput(
                output_type="session_stored",
                description=f"Session {session_id}: {stored} chunks embedded, "
                           f"{len(extraction.get('commitments', []))} commitments, "
                           f"{len(extraction.get('concerns', []))} concerns extracted",
                reference=session_id,
            )
        ]

        return AgentResult(
            agent=self.name,
            success=True,
            outputs=outputs,
        )

    def _extract_session_data(self, transcript: str, session_id: str, date: str) -> dict:
        """
        Use Claude to extract commitments, concerns, and decisions from a
        session transcript. Stores results in SQLite.
        """
        prompt = self.load_prompt(
            "session_extraction.txt",
            transcript=transcript[:8000],
            date=date,
        ) if Path(
            Path(__file__).resolve().parent.parent.parent / "prompts" / "session_extraction.txt"
        ).exists() else self._default_extraction_prompt(transcript[:8000], date)

        raw_response = self.call_claude(prompt)

        try:
            data = json.loads(raw_response)
        except json.JSONDecodeError:
            json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                logger.warning("Could not parse Claude extraction as JSON")
                data = {"commitments": [], "concerns": [], "decisions": []}

        for c in data.get("commitments", []):
            self._db.execute(
                "INSERT INTO commitments (session_id, commitment_text, owner, deadline) VALUES (?, ?, ?, ?)",
                (session_id, c.get("text", ""), c.get("owner", ""), c.get("deadline", "")),
            )

        for c in data.get("concerns", []):
            theme = c.get("theme", "general")
            existing = self._db.execute(
                "SELECT id, times_raised FROM concerns WHERE theme = ? AND raised_by = ?",
                (theme, c.get("raised_by", "")),
            ).fetchone()

            if existing:
                self._db.execute(
                    "UPDATE concerns SET times_raised = times_raised + 1 WHERE id = ?",
                    (existing["id"],),
                )
            else:
                self._db.execute(
                    "INSERT INTO concerns (session_id, concern_text, raised_by, theme) VALUES (?, ?, ?, ?)",
                    (session_id, c.get("text", ""), c.get("raised_by", ""), theme),
                )

        self._db.commit()
        return data

    def _default_extraction_prompt(self, transcript: str, date: str) -> str:
        return f"""Analyze this coach/mentor session transcript from {date}.

Extract the following as a JSON object:
{{
  "commitments": [
    {{"text": "what was committed", "owner": "who owns it", "deadline": "when"}}
  ],
  "concerns": [
    {{"text": "the concern", "raised_by": "who raised it", "theme": "one-word theme"}}
  ],
  "decisions": [
    {{"text": "what was decided", "context": "why"}}
  ]
}}

Return ONLY valid JSON, no other text.

TRANSCRIPT:
{transcript}"""

    def query_sessions(self, query: str, n_results: int = 5) -> list[dict]:
        """Semantic search over all past session transcripts."""
        return self._vector_store.query(
            collection_name=COLLECTION_SESSIONS,
            query_text=query,
            n_results=n_results,
        )

    def get_all_concerns(self) -> list[dict]:
        """Return all tracked concerns, sorted by times_raised descending."""
        rows = self._db.execute(
            "SELECT * FROM concerns ORDER BY times_raised DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_open_commitments(self) -> list[dict]:
        """Return all commitments with status='open'."""
        rows = self._db.execute(
            "SELECT c.*, s.date as session_date FROM commitments c "
            "JOIN sessions s ON c.session_id = s.session_id "
            "WHERE c.status = 'open' ORDER BY s.date DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_session_history(self) -> list[dict]:
        """Return all sessions ordered by date."""
        rows = self._db.execute(
            "SELECT * FROM sessions ORDER BY date DESC"
        ).fetchall()
        return [dict(r) for r in rows]
