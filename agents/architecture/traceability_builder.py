"""
Traceability Builder — maintains the living traceability matrix
AND the unified traceability store.

Every time a new artifact is created (requirement, Jira ticket, PR, decision),
this agent updates the traceability store with new links.

Also generates /docs/traceability.md from the store.

Triggered by: commit event, Jira webhook, PR event, pipeline completion
Outputs: updated traceability.md + traceability store links
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.traceability_builder")


class TraceabilityBuilderAgent(BaseAgent):
    """Maintains the REQ → Jira → PR → Test traceability matrix and unified store."""

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="traceability_builder", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        from pipeline.traceability import TraceabilityStore
        from pipeline.seed_traceability import seed

        seed()
        store = TraceabilityStore()
        coverage = store.get_coverage()

        matrix = self._build_matrix_from_store(store)
        outputs = []

        repo = self.mcp.get("github") or self.mcp.get("bitbucket")
        if repo and matrix:
            repo.commit_file(
                file_path="docs/traceability.md",
                content=matrix,
                message=f"Update traceability matrix ({coverage['total_artifacts']} artifacts, {coverage['coverage_pct']}% coverage)",
                agent_name=self.name,
            )
            outputs.append(AgentOutput(
                output_type="file_committed",
                description=f"Traceability matrix: {coverage['total_artifacts']} artifacts, {coverage['total_links']} links, {coverage['coverage_pct']}% coverage",
                reference="docs/traceability.md",
            ))

        # Report gaps
        gap_count = coverage["concerns_without_action"] + coverage["risks_without_mitigation"]
        if gap_count > 0:
            self.emit("human_review_needed", data={
                "type": "traceability_gaps",
                "unaddressed_concerns": coverage["concerns_without_action"],
                "unmitigated_risks": coverage["risks_without_mitigation"],
            }, pipeline="architecture")

        return AgentResult(
            agent=self.name, success=True, outputs=outputs,
            data={
                "coverage": coverage,
                "gap_count": gap_count,
            },
        )

    def _build_matrix_from_store(self, store) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        coverage = store.get_coverage()

        lines = [
            "# Traceability Matrix",
            f"\n_Last updated: {now}_",
            f"\n**{coverage['total_artifacts']}** artifacts | **{coverage['total_links']}** links | **{coverage['coverage_pct']}%** coverage",
            "",
            "## Coverage Summary",
            "",
            "| Artifact Type | Count |",
            "|--------------|-------|",
        ]
        for atype, count in coverage["by_type"].items():
            lines.append(f"| {atype} | {count} |")

        lines.extend([
            "",
            "| Link Type | Count |",
            "|-----------|-------|",
        ])
        for ltype, count in coverage["by_link_type"].items():
            lines.append(f"| {ltype} | {count} |")

        # Architecture decisions → what they connect to
        lines.extend(["", "## Architecture Decision Chains", ""])
        for arch in store.get_by_type("architecture"):
            chain = store.get_chain(arch["id"], direction="forward")
            lines.append(f"### {arch['id']}: {arch['title']}")
            lines.append(f"- **Source:** {arch.get('source_meeting', '?')} ({arch.get('source_speaker', '?')})")
            lines.append(f"- **Status:** {arch.get('status', '?')}")
            for node in chain:
                if node["artifact"]["id"] == arch["id"]:
                    continue
                a = node["artifact"]
                indent = "  " * node["depth"]
                lines.append(f"{indent}- [{a['artifact_type']}] **{a.get('jira_key') or a['id']}**: {a['title'][:80]}")
            lines.append("")

        # Risks and mitigation status
        lines.extend(["## Risk Mitigation Status", ""])
        lines.append("| Risk | Severity | Mitigated By | Status |")
        lines.append("|------|----------|-------------|--------|")
        for risk in store.get_by_type("risk"):
            chain = store.get_chain(risk["id"], direction="backward")
            mitigators = []
            for node in chain:
                for link in node.get("links", []):
                    if link["link_type"] == "MITIGATES":
                        src = store.get_artifact(link["source_id"])
                        if src:
                            mitigators.append(src.get("jira_key") or src["id"])
            sev = (risk.get("metadata") or {}).get("severity", "?")
            mit_str = ", ".join(mitigators[:3]) if mitigators else "**UNMITIGATED**"
            status = "Mitigated" if mitigators else "Open"
            lines.append(f"| {risk['title'][:50]} | {sev} | {mit_str} | {status} |")

        # Concerns traceability
        lines.extend(["", "## Concern Traceability", ""])
        lines.append("| Concern | Meeting | Speaker | Addressed By |")
        lines.append("|---------|---------|---------|-------------|")
        for c in store.get_by_type("concern"):
            chain = store.get_chain(c["id"], direction="backward")
            addressors = []
            for node in chain:
                for link in node.get("links", []):
                    if link["link_type"] == "ADDRESSES":
                        src = store.get_artifact(link["source_id"])
                        if src:
                            addressors.append(src["id"])
            addr_str = ", ".join(addressors) if addressors else "—"
            lines.append(f"| {c['title'][:50]} | {c.get('source_meeting', '?')} | {c.get('source_speaker', '?')} | {addr_str} |")

        # Gaps
        lines.extend(["", "## Traceability Gaps", ""])
        if coverage["concerns_without_action"] > 0:
            lines.append(f"- **{coverage['concerns_without_action']}** concerns without any linked action")
        if coverage["risks_without_mitigation"] > 0:
            lines.append(f"- **{coverage['risks_without_mitigation']}** risks without mitigation")
        if coverage["concerns_without_action"] == 0 and coverage["risks_without_mitigation"] == 0:
            lines.append("No critical gaps detected.")

        return "\n".join(lines) + "\n"
