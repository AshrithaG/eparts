"""
Drift Detector — compares meeting transcripts against the canonical
architecture diagram to detect structural changes.

After every meeting, reads architecture.mmd + meeting minutes. Detects:
new ingestion sources, routing changes, new downstream consumers,
layer splits/renames, decisions contradicting existing diagram.

Triggered by: transcript commit, PR event
Outputs: drift report committed to /docs/drift/YYYY-MM-DD.md
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.drift_detector")


class DriftDetectorAgent(BaseAgent):
    """Detects architectural drift between meeting decisions and the canonical diagram."""

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="drift_detector", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        minutes_content = trigger.metadata.get("minutes", "")
        date = trigger.metadata.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

        if not minutes_content:
            return AgentResult(
                agent=self.name, success=True,
                outputs=[AgentOutput(
                    output_type="drift_check_skipped",
                    description="No meeting content to analyze for drift",
                )],
            )

        # Load current architecture (from Bitbucket in production)
        arch_content = trigger.metadata.get("architecture_mmd", "")

        drift_report = self._detect_drift(minutes_content, arch_content, date)
        outputs = []

        if drift_report.get("drifts"):
            report_md = self._format_drift_report(drift_report, date)
            bitbucket = self.mcp.get("bitbucket")
            if bitbucket:
                filename = f"docs/drift/{date}.md"
                bitbucket.commit_file(
                    file_path=filename,
                    content=report_md,
                    message=f"Drift report for {date}: {len(drift_report['drifts'])} item(s)",
                    agent_name=self.name,
                )
                outputs.append(AgentOutput(
                    output_type="file_committed",
                    description=f"Drift report: {len(drift_report['drifts'])} items detected",
                    reference=filename,
                ))

            slack = self.mcp.get("slack")
            if slack:
                slack.send_alert(
                    f"*Architecture Drift Detected* ({date})\n"
                    f"{len(drift_report['drifts'])} potential change(s) found.\n"
                    f"Review: docs/drift/{date}.md"
                )
        else:
            outputs.append(AgentOutput(
                output_type="drift_check_clean",
                description="No architectural drift detected",
            ))

        return AgentResult(agent=self.name, success=True, outputs=outputs)

    def _detect_drift(self, minutes: str, architecture: str, date: str) -> dict:
        prompt = f"""Compare this meeting content against the current architecture diagram.
Identify ANY structural changes discussed, decided, or implied:

MEETING CONTENT:
{minutes[:6000]}

CURRENT ARCHITECTURE (Mermaid):
{architecture[:3000] if architecture else "(not provided)"}

Return a JSON object:
{{
  "drifts": [
    {{
      "type": "new_source|routing_change|layer_change|new_consumer|contradiction|new_component",
      "description": "what changed",
      "evidence": "quote from the meeting",
      "severity": "high|medium|low",
      "suggested_action": "what should be updated in the diagram"
    }}
  ],
  "no_drift_confidence": 0.0-1.0
}}

Return ONLY valid JSON."""

        raw = self.call_claude(prompt)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            return {"drifts": [], "no_drift_confidence": 0.5}

    def _format_drift_report(self, report: dict, date: str) -> str:
        lines = [f"# Architecture Drift Report — {date}\n"]
        for i, drift in enumerate(report.get("drifts", []), 1):
            lines.append(f"## Drift #{i}: {drift.get('type', 'unknown')}")
            lines.append(f"**Severity:** {drift.get('severity', '?')}")
            lines.append(f"**Description:** {drift.get('description', '?')}")
            lines.append(f"**Evidence:** _{drift.get('evidence', '?')}_")
            lines.append(f"**Suggested Action:** {drift.get('suggested_action', '?')}")
            lines.append("")
        return "\n".join(lines)
