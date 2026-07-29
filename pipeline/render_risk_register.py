"""
Render docs/risk_register.md from the risk register database.

The register file previously carried the footer "Auto-generated from
risk_register.db" while nothing in the repo actually generated it, so the
markdown and the database could drift apart silently. This module closes that
gap: the file is now produced from the database, and every count in the header
is computed rather than typed.

Exit condition of the risk practice area (see the meta-model mapping in
docs/defect_management.md for the house style) is that a risk has both an owner
and a mitigation. This renderer reports any risk failing that condition rather
than quietly publishing it, so the register cannot claim completeness it does
not have.

Run:  python3 -m pipeline.render_risk_register
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from pipeline.risk_register import RiskRegister

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "risk_register.md"

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _cell(text: str, limit: int = 200) -> str:
    """Collapse to one line and keep pipes from breaking the table."""
    one = " ".join((text or "").split()).replace("|", "\\|")
    return one if len(one) <= limit else one[: limit - 1].rstrip() + "…"


def render(reg: RiskRegister | None = None) -> str:
    reg = reg or RiskRegister()
    risks = sorted(
        reg.get_all(),
        key=lambda r: (SEVERITY_ORDER.get(r["severity"], 9), r["id"]),
    )
    stats = reg.stats()
    sev = stats["by_severity"]
    status = stats["by_status"]

    lines: list[str] = ["# eParts Risk Register", ""]
    lines.append(f"**Total Risks:** {stats['total']}  ")
    lines.append(
        f"**Critical:** {sev.get('critical', 0)} | "
        f"**High:** {sev.get('high', 0)} | "
        f"**Medium:** {sev.get('medium', 0)}"
        + (f" | **Low:** {sev['low']}" if sev.get("low") else "")
    )
    lines.append("")
    lines.append(
        "  ".join(f"**{k.title()}:** {v}" for k, v in sorted(status.items()))
        + "  "
    )
    lines.append("")

    lines.append(
        "| # | Severity | Category | Title | Risk Statement | Mitigation | Status | Owner |"
    )
    lines.append("|---|----------|----------|-------|----------------|------------|--------|-------|")
    for n, r in enumerate(risks, 1):
        lines.append(
            f"| {n} | **{r['severity']}** | {r['category']} | {_cell(r['title'], 70)} "
            f"| {_cell(r['description'])} | {_cell(r['mitigation'])} "
            f"| {r['status']} | {r['owner']} |"
        )
    lines.append("")

    # Traceability: which requirements and architecture artifacts each risk threatens.
    traced = [r for r in risks if r["related_reqs"] or r["related_arch"]]
    lines.append("## Traceability")
    lines.append("")
    lines.append(
        f"{len(traced)} of {len(risks)} risks are linked to the requirements or "
        "architecture artifacts they threaten."
    )
    lines.append("")
    lines.append("| Risk | Title | Threatens (requirements) | Threatens (architecture) |")
    lines.append("|------|-------|--------------------------|--------------------------|")
    for r in traced:
        lines.append(
            f"| `{r['id']}` | {_cell(r['title'], 60)} "
            f"| {', '.join(r['related_reqs']) or '—'} "
            f"| {', '.join(r['related_arch']) or '—'} |"
        )
    lines.append("")

    # Exit-condition check. A risk without an owner or a mitigation has not
    # cleared the practice area's exit gate and is called out here.
    incomplete = [r for r in risks if not r["mitigation"].strip() or not r["owner"].strip()]
    lines.append("## Exit-condition check")
    lines.append("")
    if incomplete:
        lines.append(
            f"{len(incomplete)} risk(s) have not cleared the exit gate "
            "(a risk requires both an owner and a mitigation):"
        )
        lines.append("")
        for r in incomplete:
            missing = []
            if not r["mitigation"].strip():
                missing.append("mitigation")
            if not r["owner"].strip():
                missing.append("owner")
            lines.append(f"- `{r['id']}` {r['title']} — missing {' and '.join(missing)}")
    else:
        lines.append(
            "All risks have both an owner and a mitigation, so every entry has "
            "cleared the exit gate."
        )
    lines.append("")
    lines.append("---")
    lines.append(
        f"_Generated from `memory/risk_register.db` by "
        f"`pipeline/render_risk_register.py` on {date.today().isoformat()}. "
        "Do not edit by hand: change the source in `pipeline/risk_register.py` "
        "and re-run._"
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    text = render()
    OUT.write_text(text, encoding="utf-8")
    reg = RiskRegister()
    stats = reg.stats()
    print(f"wrote {OUT.relative_to(REPO)}")
    print(f"  {stats['total']} risks · {stats['by_severity']}")
    print(f"  status: {stats['by_status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
