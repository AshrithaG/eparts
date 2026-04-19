"""
Decision Readiness Detector — fires alerts when enough evidence has
accumulated to close an open ML decision.

Thresholds:
  ≥200 labeled examples  → threshold calibration ready (ADR-1-threshold)
  ≥100 correction pairs  → alpha calibration ready (ADR-1-alpha)
  ≥50 reviewed records   → per-attribute correlation analysis ready (ADR-2-routing)

Triggered by: poc_result event (after evidence_accumulator runs)
Outputs: Slack alerts when a decision is ready to close
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent
from agents.ml_decision.decision_log import DecisionLogAgent, init_db

logger = logging.getLogger("agent.readiness_detector")

READINESS_THRESHOLDS = {
    "ADR-1-threshold": {
        "evidence_type": "labeled_count",
        "threshold": int(os.getenv("CONFIDENCE_THRESHOLD_READINESS", "200")),
        "message": "Enough labeled data to calibrate confidence threshold — run precision-recall sweep now.",
    },
    "ADR-1-alpha": {
        "evidence_type": "correction_pairs",
        "threshold": int(os.getenv("ALPHA_CALIBRATION_READINESS", "100")),
        "message": "Enough correction pairs to calibrate alpha weighting — run alpha sweep 0.3-0.9 now.",
    },
    "ADR-2-routing": {
        "evidence_type": "reviewed_records",
        "threshold": 50,
        "message": "Enough reviewed records for per-attribute correlation analysis — run pairwise mutual information now.",
    },
}


class ReadinessDetectorAgent(BaseAgent):
    """
    Checks accumulated evidence against readiness thresholds and fires
    Slack alerts when a decision has enough data to be closed.
    """

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="readiness_detector", mcp_clients=mcp_clients)
        self._decision_log = DecisionLogAgent(mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        ready_decisions = self.check_all_readiness()
        outputs = []

        for decision_id, info in ready_decisions.items():
            decision = self._decision_log.get_decision(decision_id)
            if not decision:
                continue

            alert_text = (
                f"*ML Decision Ready to Close*\n\n"
                f"*{decision['name']}* ({decision_id})\n"
                f"Current value: {decision['current_value']} (basis: {decision['basis']})\n\n"
                f"{info['message']}\n\n"
                f"Evidence: {info['current_value']} / {info['threshold']} "
                f"({info['evidence_type']})\n"
                f"Source ADR: {decision['source_adr']}"
            )

            slack = self.mcp.get("slack")
            if slack:
                slack.send_alert(alert_text)
                outputs.append(AgentOutput(
                    output_type="message_sent",
                    description=f"Readiness alert: {decision['name']} ready to close",
                    reference=decision_id,
                ))

            self._decision_log.update_decision(
                decision_id, status="ready_to_close"
            )
            outputs.append(AgentOutput(
                output_type="decision_updated",
                description=f"{decision_id} status → ready_to_close",
                reference=decision_id,
            ))

        if not ready_decisions:
            outputs.append(AgentOutput(
                output_type="readiness_check",
                description="No decisions ready to close yet",
            ))

        return AgentResult(agent=self.name, success=True, outputs=outputs)

    def check_all_readiness(self) -> dict[str, dict]:
        """
        Check all open decisions against their readiness thresholds.
        Returns a dict of decision_id -> threshold info for decisions that are ready.
        """
        ready = {}

        for decision_id, config in READINESS_THRESHOLDS.items():
            decision = self._decision_log.get_decision(decision_id)
            if not decision or decision["status"] not in ("open",):
                continue

            current_value = self._get_max_evidence_value(
                decision_id, config["evidence_type"]
            )

            if current_value >= config["threshold"]:
                ready[decision_id] = {
                    "evidence_type": config["evidence_type"],
                    "threshold": config["threshold"],
                    "current_value": current_value,
                    "message": config["message"],
                }

        return ready

    def _get_max_evidence_value(self, decision_id: str, evidence_type: str) -> float:
        """
        Get the maximum numeric value for a specific evidence type
        across all evidence entries for a decision.
        """
        evidence_list = self._decision_log.get_evidence(decision_id)
        max_val = 0

        for e in evidence_list:
            desc = e.get("description", "")
            if evidence_type not in desc:
                continue

            try:
                val_data = json.loads(e["value"]) if isinstance(e["value"], str) else e["value"]
                if isinstance(val_data, dict) and "value" in val_data:
                    numeric = float(val_data["value"])
                elif isinstance(val_data, (int, float)):
                    numeric = float(val_data)
                else:
                    continue
                max_val = max(max_val, numeric)
            except (json.JSONDecodeError, ValueError, TypeError):
                continue

        return max_val

    def get_readiness_summary(self) -> str:
        """Format readiness state for briefings."""
        lines = ["### ML Decision Readiness"]

        for decision_id, config in READINESS_THRESHOLDS.items():
            decision = self._decision_log.get_decision(decision_id)
            if not decision:
                continue

            current = self._get_max_evidence_value(decision_id, config["evidence_type"])
            threshold = config["threshold"]
            pct = (current / threshold * 100) if threshold > 0 else 0
            status_emoji = "ready" if pct >= 100 else f"{pct:.0f}%"

            lines.append(
                f"- **{decision['name']}**: {current:.0f}/{threshold} "
                f"{config['evidence_type']} [{status_emoji}]"
            )

        return "\n".join(lines)
