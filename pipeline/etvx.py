"""
ETVX Process Model — machine-readable meta-model compliance layer.

Loads the ETVX manifest (docs/etvx_manifest.yaml) and provides:
  - Programmatic access to process definitions
  - Validation that all agents have ETVX coverage
  - Summary statistics for presentation
  - Markdown rendering for documentation

Maps to the CMU AASE/LASE meta-model: every process has Entry criteria,
Task definition, Verification checks, and eXit criteria, with explicit
resource allocation (auton/assist/human) and measurement points.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ETVX_PATH = PROJECT_ROOT / "docs" / "etvx_manifest.yaml"


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    p = path or ETVX_PATH
    with open(p) as f:
        return yaml.safe_load(f)


def get_processes(manifest: dict | None = None) -> list[dict]:
    m = manifest or load_manifest()
    return m.get("processes", [])


def get_process_by_agent(agent_name: str, manifest: dict | None = None) -> dict | None:
    for p in get_processes(manifest):
        if p.get("agent") == agent_name:
            return p
    return None


def validate_coverage(registered_agents: list[str], manifest: dict | None = None) -> dict:
    """Check that every registered agent has an ETVX process definition."""
    processes = get_processes(manifest)
    documented_agents = {p["agent"] for p in processes}
    system_agents = {
        "N/A (built into BaseAgent)",
        "Central Orchestrator (FastAPI)",
        "N/A (human process)",
    }

    covered = set()
    missing = set()
    for agent in registered_agents:
        if agent in documented_agents:
            covered.add(agent)
        else:
            missing.add(agent)

    return {
        "total_agents": len(registered_agents),
        "covered": len(covered),
        "missing": sorted(missing),
        "coverage_pct": len(covered) / max(len(registered_agents), 1) * 100,
        "total_processes": len(processes),
    }


def summary_stats(manifest: dict | None = None) -> dict:
    """Aggregate statistics for the presentation."""
    procs = get_processes(manifest)
    resource_counts = {"auton": 0, "assist": 0, "human": 0}
    domain_counts: dict[str, int] = {}
    total_measurements = 0

    for p in procs:
        rt = p.get("resource_type", "unknown")
        resource_counts[rt] = resource_counts.get(rt, 0) + 1
        domain = p.get("domain", "unknown")
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        total_measurements += len(p.get("measurements", []))

    return {
        "total_processes": len(procs),
        "resource_allocation": resource_counts,
        "domain_distribution": domain_counts,
        "total_measurement_points": total_measurements,
        "avg_measurements_per_process": round(total_measurements / max(len(procs), 1), 1),
    }


def render_markdown(manifest: dict | None = None) -> str:
    """Render the full ETVX manifest as presentation-ready markdown."""
    m = manifest or load_manifest()
    procs = m.get("processes", [])
    meta = m.get("meta", {})
    stats = summary_stats(m)

    lines = [
        f"# {meta.get('project', 'SES')} — ETVX Process Model",
        "",
        f"**Team:** {meta.get('team', '')}",
        f"**Framework:** {meta.get('framework', '')}",
        f"**SDLC Pattern:** {meta.get('sdlc_pattern', '')}",
        "",
        "## Summary",
        "",
        f"- **{stats['total_processes']} processes** documented",
        f"- **{stats['resource_allocation'].get('auton', 0)} autonomous**, "
        f"**{stats['resource_allocation'].get('assist', 0)} AI-assisted**, "
        f"**{stats['resource_allocation'].get('human', 0)} human**",
        f"- **{stats['total_measurement_points']} measurement points** across all processes",
        f"- **{stats['avg_measurements_per_process']} avg measurements** per process",
        "",
        "## Domains",
        "",
    ]

    for domain, count in sorted(stats["domain_distribution"].items()):
        lines.append(f"- **{domain}**: {count} processes")

    lines.extend(["", "---", ""])

    current_domain = ""
    for p in procs:
        domain = p.get("domain", "")
        if domain != current_domain:
            current_domain = domain
            lines.extend([f"## {domain.replace('_', ' ').title()} Domain", ""])

        rt_badge = {"auton": "autonomous", "assist": "AI-assisted", "human": "human"}
        badge = rt_badge.get(p.get("resource_type", ""), p.get("resource_type", ""))

        lines.extend([
            f"### {p['id']}: {p['name']} [{badge}]",
            "",
            f"*Agent:* `{p.get('agent', 'N/A')}`",
            "",
            f"> {p.get('description', '')}",
            "",
            "**Entry Criteria:**",
        ])
        for item in p.get("entry", []):
            lines.append(f"- {item}")

        lines.extend(["", "**Task:**"])
        for item in p.get("task", []):
            lines.append(f"1. {item}")

        lines.extend(["", "**Verification:**"])
        for item in p.get("verification", []):
            lines.append(f"- {item}")

        lines.extend(["", "**Exit Criteria:**"])
        for item in p.get("exit", []):
            lines.append(f"- {item}")

        if p.get("artifacts_produced"):
            lines.extend(["", "**Artifacts Produced:**"])
            for a in p["artifacts_produced"]:
                lines.append(f"- `{a}`")

        if p.get("measurements"):
            lines.extend(["", "**Measurements:**"])
            for m_item in p["measurements"]:
                lines.append(f"- {m_item}")

        lines.extend(["", "---", ""])

    return "\n".join(lines)
