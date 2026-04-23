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
        # Get meeting content from pipeline context or direct metadata
        pipeline_ctx = trigger.metadata.get("pipeline_context", {})
        minutes_content = (
            trigger.metadata.get("minutes", "")
            or pipeline_ctx.get("transcript_cleaned", "")
            or pipeline_ctx.get("minutes", "")
        )
        date = trigger.metadata.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

        if not minutes_content:
            return AgentResult(
                agent=self.name, success=True,
                outputs=[AgentOutput(
                    output_type="drift_check_skipped",
                    description="No meeting content to analyze for drift",
                )],
            )

        # Load architecture from ChromaDB (real canonical architecture)
        arch_context = self._get_architecture_context(minutes_content)

        # Load architecture from wiki (structured data)
        wiki_arch = self._get_wiki_architecture()

        drift_report = self._detect_drift_offline(minutes_content, arch_context, wiki_arch, date)
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

            # Emit cross-pipeline event
            self.emit("drift_detected", {
                "date": date,
                "drift_count": len(drift_report["drifts"]),
                "drifts": drift_report["drifts"][:5],
            })

            # Deposit to wiki
            self.wiki.put("architecture", f"drift-{date}", {
                "date": date,
                "drifts": drift_report["drifts"],
                "confidence": drift_report.get("no_drift_confidence", 0),
            }, agent=self.name, tags=["drift", date])
        else:
            outputs.append(AgentOutput(
                output_type="drift_check_clean",
                description=f"No architectural drift detected (checked against {len(arch_context)} architecture chunks)",
            ))

        return AgentResult(
            agent=self.name, success=True, outputs=outputs,
            data={"drift_report": drift_report},
        )

    def _get_architecture_context(self, query: str) -> list[str]:
        """Retrieve relevant architecture chunks from ChromaDB."""
        try:
            from mcp.vector_store import VectorStoreMCP
            vs = VectorStoreMCP()
            col = vs.get_or_create_collection("architecture")
            if col.count() == 0:
                return []
            results = col.query(query_texts=[query[:1000]], n_results=5)
            return results.get("documents", [[]])[0]
        except Exception as exc:
            logger.debug(f"ChromaDB architecture query failed: {exc}")
            return []

    def _get_wiki_architecture(self) -> dict:
        """Get structured architecture data from SharedMemory wiki."""
        try:
            return {
                "style": self.wiki.get("architecture", "style", {}),
                "components": self.wiki.get("architecture", "components", {}),
                "quality_attributes": self.wiki.get("architecture", "quality_attributes", {}),
                "constraints": self.wiki.get("architecture", "constraints", {}),
                "decisions": self.wiki.get("architecture", "decisions", {}),
            }
        except Exception:
            return {}

    def _detect_drift_offline(self, minutes: str, arch_chunks: list[str], wiki_arch: dict, date: str) -> dict:
        """
        Detect drift using keyword matching against the canonical architecture.
        Works without Claude API key.
        """
        drifts = []
        text = minutes.lower()

        # Architecture components from wiki
        components = wiki_arch.get("components", {})
        constraints = wiki_arch.get("constraints", {})
        decisions = wiki_arch.get("decisions", {})

        # Check for mentions of alternative approaches that contradict decisions
        contradiction_patterns = {
            "microservice": ("AD-6", "Single App Service chosen over microservices"),
            "kubernetes": ("AD-6", "Single App Service — no container orchestration"),
            "message queue": ("ADR-1", "Internal interface chosen over message queue"),
            "rest api.*prediction": ("AD-2", "Internal interface chosen over REST for prediction"),
            "gcp": ("azure_deployment", "Azure is a fixed constraint"),
            "aws": ("azure_deployment", "Azure is a fixed constraint"),
            "per.record.*rout": ("routing", "Per-attribute routing chosen over per-record"),
            "direct.*prod.*write": ("no_direct_prod_writes", "All writes go to staging first"),
            "pricing.*ml": ("no_pricing", "Pricing excluded from ML pipeline"),
        }

        for pattern, (decision_id, desc) in contradiction_patterns.items():
            if re.search(pattern, text):
                evidence_match = re.search(f".{{0,100}}{pattern}.{{0,100}}", text)
                evidence = evidence_match.group(0).strip() if evidence_match else ""
                drifts.append({
                    "type": "contradiction",
                    "description": f"Discussion may contradict {decision_id}: {desc}",
                    "evidence": evidence[:200],
                    "severity": "medium",
                    "suggested_action": f"Review {decision_id} — verify if decision needs updating",
                    "architecture_ref": decision_id,
                })

        # Check for new components or technologies not in architecture
        new_tech_patterns = {
            "redis": "caching layer not in architecture",
            "kafka": "event streaming not in architecture",
            "mongodb": "document store not in current architecture",
            "graphql": "query layer not in current API design",
            "grpc": "RPC protocol not in current interface design",
            "terraform": "IaC tool not in deployment view",
            "docker compose": "local orchestration not specified",
        }

        for tech, desc in new_tech_patterns.items():
            if tech in text:
                drifts.append({
                    "type": "new_component",
                    "description": f"New technology mentioned: {tech} — {desc}",
                    "evidence": f"'{tech}' mentioned in meeting discussion",
                    "severity": "low",
                    "suggested_action": "Evaluate if this should be added to the architecture",
                })

        # Check if any architecture chunks from ChromaDB are relevant
        for chunk in arch_chunks[:3]:
            chunk_lower = chunk.lower()
            if "risk" in chunk_lower or "unresolved" in chunk_lower:
                # Extract key terms from the chunk to cross-reference
                if "threshold" in text and "threshold" in chunk_lower:
                    drifts.append({
                        "type": "sensitivity_point",
                        "description": "Threshold discussion detected — this is a known sensitivity point",
                        "evidence": "Meeting discusses confidence thresholds",
                        "severity": "low",
                        "suggested_action": "Record any threshold decisions in ADR-4",
                        "architecture_ref": "AD-4",
                    })

        confidence = 1.0 - (len(drifts) * 0.15)
        return {
            "drifts": drifts,
            "no_drift_confidence": max(0.0, confidence),
            "architecture_chunks_checked": len(arch_chunks),
            "wiki_data_available": bool(wiki_arch.get("components")),
        }

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
