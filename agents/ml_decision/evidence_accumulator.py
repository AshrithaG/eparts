"""
Evidence Accumulator — parses POC results and labeled data commits to
update the ML decision log with new empirical evidence.

When POC scripts run or new labeled data is committed, this agent
automatically updates the relevant decision entries with new results.
Tracks: labeled count, precision@threshold, recall@threshold,
per-attribute variance, correction rate, alpha sweep results.

Triggered by: poc_result event, labeled data commit
Outputs: updated evidence entries in SQLite
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent
from agents.ml_decision.decision_log import DecisionLogAgent, init_db

logger = logging.getLogger("agent.evidence_accumulator")

# Maps evidence fields to relevant decisions
EVIDENCE_DECISION_MAP = {
    "precision_at_threshold": "ADR-1-threshold",
    "recall_at_threshold": "ADR-1-threshold",
    "auto_accept_rate": "ADR-1-threshold",
    "labeled_count": "ADR-1-threshold",
    "per_attribute_variance": "ADR-1-threshold",
    "alpha_sweep": "ADR-1-alpha",
    "correction_pairs": "ADR-1-alpha",
    "ece_scores": "ADR-1-alpha",
    "cross_attribute_correlation": "ADR-2-routing",
    "reviewed_records": "ADR-2-routing",
    "pims_schema_mapping": "ADR-3-schema",
    "integration_test_results": "ADR-3-schema",
    "confidence_distribution": "ADR-4-drift",
    "correction_rate_baseline": "ADR-4-drift",
}


class EvidenceAccumulatorAgent(BaseAgent):
    """
    Parses structured output from POC scripts and updates the ML decision
    log with new empirical evidence.
    """

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="evidence_accumulator", mcp_clients=mcp_clients)
        self._decision_log = DecisionLogAgent(mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        source = trigger.source
        outputs = []

        if trigger.trigger_type == "poc_result":
            results = self._parse_poc_results(source)
            evidence_count = self._ingest_evidence(results)
            outputs.append(AgentOutput(
                output_type="evidence_ingested",
                description=f"Ingested {evidence_count} evidence items from POC results",
                reference=source,
            ))
        elif trigger.trigger_type == "manual":
            data = trigger.metadata.get("evidence", {})
            evidence_count = self._ingest_evidence(data)
            outputs.append(AgentOutput(
                output_type="evidence_ingested",
                description=f"Manually ingested {evidence_count} evidence items",
            ))

        return AgentResult(agent=self.name, success=True, outputs=outputs)

    def _parse_poc_results(self, source: str) -> dict[str, Any]:
        """Parse a POC results JSON file into evidence fields."""
        path = Path(source)
        if not path.exists():
            logger.warning(f"POC results file not found: {source}")
            return {}

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.error(f"Failed to parse POC results: {exc}")
            return {}

        evidence: dict[str, Any] = {}

        if "auto_accept_rate" in raw:
            evidence["auto_accept_rate"] = raw["auto_accept_rate"]
        if "precision" in raw:
            evidence["precision_at_threshold"] = raw["precision"]
        if "recall" in raw:
            evidence["recall_at_threshold"] = raw["recall"]
        if "top_1_accuracy" in raw:
            evidence["precision_at_threshold"] = raw["top_1_accuracy"]
        if "labeled_count" in raw or "total_attributes_tested" in raw:
            evidence["labeled_count"] = raw.get("labeled_count", raw.get("total_attributes_tested"))
        if "per_attribute_results" in raw:
            results = raw["per_attribute_results"]
            if isinstance(results, list) and results:
                accuracies = [r.get("accuracy", 0) for r in results if "accuracy" in r]
                if accuracies:
                    import statistics
                    evidence["per_attribute_variance"] = statistics.variance(accuracies) if len(accuracies) > 1 else 0
        if "alpha_sweep" in raw:
            evidence["alpha_sweep"] = raw["alpha_sweep"]
        if "correction_pairs" in raw:
            evidence["correction_pairs"] = raw["correction_pairs"]
        if "reviewed_records" in raw:
            evidence["reviewed_records"] = raw["reviewed_records"]
        if "threshold" in raw:
            evidence["threshold_used"] = raw["threshold"]

        return evidence

    def _ingest_evidence(self, evidence: dict[str, Any]) -> int:
        """Map evidence fields to decisions and store them."""
        count = 0
        for field, value in evidence.items():
            decision_id = EVIDENCE_DECISION_MAP.get(field)
            if not decision_id:
                logger.info(f"No decision mapping for evidence field: {field}")
                continue

            self._decision_log.add_evidence(
                decision_id=decision_id,
                evidence_type="poc_result",
                description=f"Auto-ingested: {field}",
                value=value if isinstance(value, (dict, list)) else {"value": value},
            )
            count += 1
            logger.info(f"Evidence added: {field} → {decision_id}")

        return count

    def ingest_poc_file(self, filepath: str) -> int:
        """Convenience: parse a POC results file and ingest all evidence."""
        results = self._parse_poc_results(filepath)
        return self._ingest_evidence(results)
