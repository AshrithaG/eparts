"""
Pre-Meeting Briefing Generator — produces structured briefings before
every coach/mentor meeting.

Runs 1 hour before scheduled meetings. Produces:
  - What Christian flagged last session
  - What the team committed to
  - What was delivered (with evidence links)
  - What is still open
  - Recurring concerns across all sessions (pattern detection)

Triggered by: cron_pre_meeting, manual
Outputs: briefing posted to Slack (auto-published, no HITL gate)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent
from agents.coach_memory.concern_tracker import ConcernTrackerAgent
from agents.coach_memory.session_memory import SessionMemoryAgent, init_db
from mcp.vector_store import COLLECTION_SESSIONS, VectorStoreMCP

logger = logging.getLogger("agent.briefing_generator")


class BriefingGeneratorAgent(BaseAgent):
    """
    Generates a comprehensive pre-meeting briefing by combining:
    1. Last session summary (from RAG)
    2. Open commitments
    3. Delivered commitments
    4. Recurring concern patterns
    5. Open ML decisions (from ML Decision agent if available)
    """

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="briefing_generator", mcp_clients=mcp_clients)
        self._db = init_db()
        self._vector_store = (
            mcp_clients.get("vector_store") if mcp_clients else None
        ) or VectorStoreMCP()
        self._concern_tracker = ConcernTrackerAgent(mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        # 1. Gather all context
        last_session = self._get_last_session_summary()
        open_commitments = self._get_open_commitments()
        delivered_commitments = self._get_delivered_commitments()
        recurring_concerns = self._concern_tracker.get_concerns_for_briefing()

        # 2. Retrieve relevant past context via RAG
        meeting_type = trigger.metadata.get("meeting_type", "coach")
        rag_context = self._get_rag_context(meeting_type)

        # 3. Generate the briefing with Claude
        briefing = self._generate_briefing(
            last_session=last_session,
            open_commitments=open_commitments,
            delivered_commitments=delivered_commitments,
            recurring_concerns=recurring_concerns,
            rag_context=rag_context,
            meeting_type=meeting_type,
        )

        # 4. Post to Slack
        outputs = []
        slack = self.mcp.get("slack")
        if slack:
            result = slack.send_message(briefing)
            if result.get("ok"):
                slack.pin_message(
                    channel=result["channel"],
                    timestamp=result["ts"],
                )
                outputs.append(AgentOutput(
                    output_type="message_sent",
                    description="Pre-meeting briefing posted and pinned to Slack",
                    reference=result.get("ts", ""),
                ))

        outputs.append(AgentOutput(
            output_type="briefing_generated",
            description=f"Briefing for {meeting_type} meeting generated "
                       f"({len(briefing)} chars)",
        ))

        return AgentResult(agent=self.name, success=True, outputs=outputs)

    def _get_last_session_summary(self) -> str:
        row = self._db.execute(
            "SELECT * FROM sessions ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if not row:
            return "No previous sessions recorded."

        session = dict(row)
        participants = json.loads(session.get("participants", "[]"))
        return (
            f"Last session: {session['date']} ({session['session_type']})\n"
            f"Participants: {', '.join(participants) if participants else 'unknown'}"
        )

    def _get_open_commitments(self) -> str:
        rows = self._db.execute(
            "SELECT c.*, s.date as session_date FROM commitments c "
            "JOIN sessions s ON c.session_id = s.session_id "
            "WHERE c.status = 'open' ORDER BY c.deadline"
        ).fetchall()

        if not rows:
            return "No open commitments."

        lines = []
        for r in rows:
            r = dict(r)
            deadline = f" (due: {r['deadline']})" if r['deadline'] else ""
            lines.append(f"- {r['commitment_text']} — owner: {r['owner']}{deadline}")
        return "\n".join(lines)

    def _get_delivered_commitments(self) -> str:
        rows = self._db.execute(
            "SELECT c.*, s.date as session_date FROM commitments c "
            "JOIN sessions s ON c.session_id = s.session_id "
            "WHERE c.status = 'delivered' ORDER BY s.date DESC LIMIT 10"
        ).fetchall()

        if not rows:
            return "No recently delivered commitments."

        lines = []
        for r in rows:
            r = dict(r)
            evidence = f" — [{r['evidence_link']}]" if r.get('evidence_link') else ""
            lines.append(f"- ✓ {r['commitment_text']}{evidence}")
        return "\n".join(lines)

    def _get_rag_context(self, meeting_type: str) -> str:
        """Retrieve top-5 most relevant past session chunks."""
        query = f"Key topics and concerns from past {meeting_type} sessions"
        results = self._vector_store.query(
            collection_name=COLLECTION_SESSIONS,
            query_text=query,
            n_results=5,
        )

        if not results:
            return "No past session context available."

        chunks = []
        for r in results:
            meta = r.get("metadata", {})
            chunks.append(
                f"[{meta.get('date', '?')} | {meta.get('session_type', '?')}]\n"
                f"{r['document'][:400]}"
            )
        return "\n---\n".join(chunks)

    def _generate_briefing(
        self,
        last_session: str,
        open_commitments: str,
        delivered_commitments: str,
        recurring_concerns: str,
        rag_context: str,
        meeting_type: str,
    ) -> str:
        prompt = self.load_prompt(
            "briefing_generator.txt",
            meeting_type=meeting_type,
            last_session=last_session,
            open_commitments=open_commitments,
            delivered_commitments=delivered_commitments,
            recurring_concerns=recurring_concerns,
            rag_context=rag_context,
            date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        ) if (
            self._settings  # always true, but keeps prompt loading in try path
            and (AgentOutput.__module__)  # cheap truthy check to satisfy linter
            and (
                __import__("pathlib").Path(__file__).resolve().parent.parent.parent
                / "prompts" / "briefing_generator.txt"
            ).exists()
        ) else self._default_briefing_prompt(
            meeting_type, last_session, open_commitments,
            delivered_commitments, recurring_concerns, rag_context,
        )

        return self.call_claude(prompt)

    def _default_briefing_prompt(
        self,
        meeting_type: str,
        last_session: str,
        open_commitments: str,
        delivered_commitments: str,
        recurring_concerns: str,
        rag_context: str,
    ) -> str:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return f"""Generate a pre-meeting briefing for a {meeting_type} meeting on {today}.
You are preparing the Pimsie Supreme team (CMU MSE capstone) for their session.

## Last Session
{last_session}

## Open Commitments (not yet delivered)
{open_commitments}

## Recently Delivered
{delivered_commitments}

## Recurring Concerns (patterns across sessions)
{recurring_concerns}

## Relevant Past Context (from session memory)
{rag_context}

Format the briefing as clean Slack-compatible markdown with these sections:
1. **Last Session Recap** — key points from the most recent session
2. **Commitment Status** — what was promised vs delivered
3. **Open Items** — what still needs to be done
4. **Coach's Recurring Themes** — patterns to be prepared for
5. **Suggested Discussion Points** — what the team should raise

Keep it concise (under 800 words). Be specific, not generic."""
