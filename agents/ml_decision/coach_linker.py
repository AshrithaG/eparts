"""
Coach Session Linker — cross-references open ML decisions against
coach session transcripts.

When Christian asks about threshold calibration, this agent surfaces:
what decision is open, what evidence exists, what is still needed,
and links to the relevant ADR. Feeds into Coach Memory Agent briefings.

Triggered by: coach_transcript event (after session_memory)
Outputs: linked ML decision context for briefings
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent
from agents.ml_decision.decision_log import DecisionLogAgent
from agents.ml_decision.readiness_detector import ReadinessDetectorAgent
from mcp.vector_store import COLLECTION_SESSIONS, VectorStoreMCP

logger = logging.getLogger("agent.coach_linker")

ML_KEYWORDS = [
    "threshold", "confidence", "calibration", "alpha", "weighting",
    "per-attribute", "per-record", "routing", "drift", "baseline",
    "precision", "recall", "accuracy", "PIMS", "schema", "P1-C",
]


class CoachLinkerAgent(BaseAgent):
    """
    Bridges the Coach Memory and ML Decision agents by detecting when
    coach sessions touch ML decision topics and enriching the context.
    """

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="coach_linker", mcp_clients=mcp_clients)
        self._decision_log = DecisionLogAgent(mcp_clients=mcp_clients)
        self._readiness = ReadinessDetectorAgent(mcp_clients=mcp_clients)
        self._vector_store = (
            mcp_clients.get("vector_store") if mcp_clients else None
        ) or VectorStoreMCP()

    def run(self, trigger: AgentTrigger) -> AgentResult:
        outputs = []

        # Search past sessions for ML-related discussions
        ml_mentions = self._find_ml_mentions_in_sessions()

        # Build linked context
        linked_context = self._build_linked_context(ml_mentions)

        if linked_context:
            outputs.append(AgentOutput(
                output_type="context_linked",
                description=f"Linked {len(ml_mentions)} ML discussion(s) "
                           f"to open decisions",
            ))

        return AgentResult(agent=self.name, success=True, outputs=outputs)

    def _find_ml_mentions_in_sessions(self) -> list[dict]:
        """Query the session vector store for ML-related content."""
        mentions = []
        for keyword in ["threshold calibration", "alpha weighting", "drift detection"]:
            results = self._vector_store.query(
                collection_name=COLLECTION_SESSIONS,
                query_text=keyword,
                n_results=3,
            )
            for r in results:
                if r.get("distance", 1.0) < 0.5:
                    mentions.append({
                        "query": keyword,
                        "document": r["document"],
                        "metadata": r["metadata"],
                        "distance": r["distance"],
                    })
        return mentions

    def _build_linked_context(self, ml_mentions: list[dict]) -> str:
        """Build a formatted context string linking sessions to decisions."""
        open_decisions = self._decision_log.get_open_decisions()
        if not open_decisions:
            return ""

        lines = ["### ML Decisions Referenced in Coach Sessions\n"]

        for decision in open_decisions:
            related = [
                m for m in ml_mentions
                if any(kw in m["document"].lower()
                       for kw in decision["name"].lower().split())
            ]
            if related:
                evidence = self._decision_log.get_evidence(decision["decision_id"])
                lines.append(
                    f"**{decision['name']}** ({decision['decision_id']})\n"
                    f"  Current: {decision['current_value']} | Basis: {decision['basis']}\n"
                    f"  Evidence collected: {len(evidence)} items\n"
                    f"  Still needs: {decision['evidence_needed'][:120]}\n"
                    f"  Referenced in {len(related)} session(s)"
                )

        return "\n".join(lines) if len(lines) > 1 else ""

    def get_ml_context_for_briefing(self) -> str:
        """
        Produce a combined ML decision + readiness summary for
        inclusion in pre-meeting briefings.
        """
        decision_summary = self._decision_log.get_decisions_summary_for_briefing()
        readiness_summary = self._readiness.get_readiness_summary()
        return f"{decision_summary}\n\n{readiness_summary}"
