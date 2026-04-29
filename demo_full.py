#!/usr/bin/env python3
"""
FULL SES DEMO — Walks through every component of the eParts Agentic SE System.

Usage:
    python demo_full.py                     # interactive (pauses between sections)
    python demo_full.py --auto              # auto-advance (no pauses, for recording)

Sections:
    1. System Overview (28 agents, 7 pipelines, 8 MCP, 9 DBs)
    2. Requirements Pipeline — LIVE (transcript → Jira + GitHub)
    3. Coach Session Pipeline — LIVE (coach VTT → memory + commitments)
    4. Shared Memory (Wiki) — live query
    5. Event Bus — cross-pipeline triggers
    6. Traceability Store — full lifecycle chains
    7. Risk Register — auto-populated
    8. Prompt Registry — governance
    9. Artifact Versioning — document evolution
   10. Metrics — agent performance dashboard
   11. Open Dashboards
"""
from __future__ import annotations

import json
import sys
import time
from glob import glob
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── colours ──────────────────────────────────────────────────────────
C = "\033[96m"; G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"
M = "\033[95m"; D = "\033[2m"; B = "\033[1m"; X = "\033[0m"

AUTO = "--auto" in sys.argv

import logging
logging.basicConfig(level=logging.WARNING, format=f"{D}%(message)s{X}")
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("chromadb").setLevel(logging.ERROR)


def pause(msg="Press ENTER to continue"):
    if AUTO:
        return
    input(f"  {M}{msg} ▸{X} ")


def section(num, title, subtitle=""):
    print(f"\n\n{C}{B}{'═'*70}")
    print(f"  {num}. {title}")
    if subtitle:
        print(f"     {D}{subtitle}{B}")
    print(f"{'═'*70}{X}\n")


def kv(key, val, indent=4):
    print(f"{' '*indent}{B}{key:.<30}{X} {val}")


def bullet(text, indent=4):
    print(f"{' '*indent}{G}▸{X} {text}")


def warn(text, indent=4):
    print(f"{' '*indent}{Y}⚠ {text}{X}")


def table_row(cols, widths):
    parts = []
    for c, w in zip(cols, widths):
        parts.append(str(c)[:w].ljust(w))
    print(f"    {'  '.join(parts)}")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 0: BANNER
# ═══════════════════════════════════════════════════════════════════════
def show_banner():
    print(f"""
{C}{B}╔═══════════════════════════════════════════════════════════════════════╗
║                                                                       ║
║     eParts — Agentic Software Engineering System                      ║
║     Full System Demo                                                  ║
║                                                                       ║
║     Team Pimsie Supreme · CMU MSE Capstone · 2026                     ║
║                                                                       ║
╚═══════════════════════════════════════════════════════════════════════╝{X}
""")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 1: SYSTEM OVERVIEW
# ═══════════════════════════════════════════════════════════════════════
def show_overview():
    section("1", "System Overview", "What did we build?")

    from agents.base import AgentSettings
    from mcp.jira import JiraMCP
    from mcp.github import GitHubMCP
    s = AgentSettings()
    jira = JiraMCP()
    gh = GitHubMCP()

    provider = s.active_provider
    model = s.gemini_model if provider == "gemini" else s.claude_model if provider == "anthropic" else "offline"

    print(f"    {B}Architecture:{X}")
    print(f"    Triggers → Central Orchestrator → Domain Agents → MCP Servers → Outputs\n")

    kv("Agents", "28 specialized agents")
    kv("Pipelines", "7 end-to-end pipelines")
    kv("MCP Servers", "8 (Jira, GitHub, Confluence, Slack, Drive, ChromaDB, Bitbucket, Vector Store)")
    kv("SQLite Databases", "9 persistent stores")
    kv("ChromaDB Collections", "RAG vector store (ONNX MiniLM-L6 embeddings)")
    kv("LLM Provider", f"{provider} / {model}")
    kv("Jira", f"{'Connected' if jira.is_configured else 'Not configured'}")
    kv("GitHub", f"{'Connected' if gh.is_configured else 'Not configured'}")

    print(f"\n    {B}The 7 Pipelines:{X}")
    from pipeline.pipelines import ALL_PIPELINES
    for name, pipe in ALL_PIPELINES.items():
        agents = [s.agent_name for s in pipe.steps]
        print(f"    {G}▸{X} {B}{name}{X} ({pipe.practice_area}) — {len(agents)} agents")
        print(f"      {D}{' → '.join(agents)}{X}")

    print(f"\n    {B}The 9 SQLite Stores:{X}")
    stores = [
        ("shared_memory.db", "Project Wiki — all agent knowledge"),
        ("events.db", "Event Bus — cross-pipeline triggers"),
        ("traceability.db", "Unified Traceability — artifact lifecycle"),
        ("risk_register.db", "Risk Register — 16 tracked risks"),
        ("prompt_registry.db", "Prompt Registry — version-controlled prompts"),
        ("coach_sessions.db", "Coach Session Memory — indexed sessions"),
        ("ml_decisions.db", "ML Decision Log — evidence & readiness"),
        ("artifact_versions.db", "Artifact Versioning — document evolution"),
        ("metrics.db", "Agent Metrics — performance tracking (inside MetricsCollector)"),
    ]
    for db, desc in stores:
        bullet(f"{B}{db}{X} — {desc}")

    pause()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 2: LIVE REQUIREMENTS PIPELINE
# ═══════════════════════════════════════════════════════════════════════
def run_requirements_pipeline():
    section("2", "LIVE: Requirements Pipeline",
            "Upload a meeting transcript → 7 agents fire in sequence")

    vtts = sorted(glob(str(PROJECT_ROOT / "transcripts" / "*.transcript.vtt")))
    vtt = vtts[-1] if vtts else None
    if not vtt:
        warn("No .vtt files found in transcripts/")
        return

    print(f"    Transcript: {B}{Path(vtt).name}{X}")
    print(f"    Pipeline:   transcript_parser → priority_classifier → req_extractor →")
    print(f"                ticket_creator → minutes_publisher → decision_logger → drift_detector\n")

    pause("Press ENTER to run the Requirements Pipeline LIVE")

    from orchestrator.registry import register_all_agents
    from orchestrator.queue import TaskQueue
    from pipeline.pipelines import REQUIREMENTS_PIPELINE, PipelineExecutor

    print(f"\n{D}    Registering 28 agents...{X}")
    tq = TaskQueue()
    agents = register_all_agents(tq)
    print(f"    {G}✓ {len(agents)} agents ready{X}\n")

    executor = PipelineExecutor(agents)

    logging.getLogger("agent").setLevel(logging.INFO)
    logging.getLogger("mcp").setLevel(logging.INFO)

    t0 = time.perf_counter()
    result = executor.execute(REQUIREMENTS_PIPELINE, {
        "trigger_type": "transcript",
        "source": vtt,
    })
    elapsed = time.perf_counter() - t0

    logging.getLogger("agent").setLevel(logging.WARNING)
    logging.getLogger("mcp").setLevel(logging.WARNING)

    print(f"\n    {B}Pipeline Result:{X}")
    c = G if result.success else R
    kv("Success", f"{c}{result.success}{X}")
    kv("Steps", f"{result.completed_steps}/{result.total_steps} ok, "
       f"{result.skipped_steps} skipped, {result.failed_steps} failed")
    kv("Duration", f"{elapsed:.1f}s")
    kv("LLM Calls", str(result.total_llm_calls))
    kv("Tokens Used", f"{result.total_tokens:,}")
    kv("Artifacts", str(result.total_artifacts))

    if result.artifacts:
        print(f"\n    {B}Artifacts Produced:{X}")
        for a in result.artifacts:
            bullet(f"[{a['type']}] {a['description'][:80]}")

    pause()
    return agents


# ═══════════════════════════════════════════════════════════════════════
# SECTION 3: LIVE COACH SESSION PIPELINE
# ═══════════════════════════════════════════════════════════════════════
def run_coach_pipeline(agents):
    section("3", "LIVE: Coach Session Pipeline",
            "Process a coach meeting → memory + commitments + concerns")

    coach_vtts = sorted(glob(str(PROJECT_ROOT / "coach_meetings" / "*.vtt")))
    if not coach_vtts:
        coach_vtts = sorted(glob(str(PROJECT_ROOT / "coach_meetings" / "**" / "*.vtt")))
    if not coach_vtts:
        warn("No coach meeting .vtt files found")
        return

    vtt = coach_vtts[-1]
    print(f"    Transcript: {B}{Path(vtt).name}{X}")
    print(f"    Pipeline:   transcript_parser → session_memory → commitment_tracker →")
    print(f"                concern_tracker → coach_linker → decision_logger\n")

    pause("Press ENTER to run the Coach Session Pipeline LIVE")

    from pipeline.pipelines import COACH_SESSION_PIPELINE, PipelineExecutor
    if not agents:
        from orchestrator.registry import register_all_agents
        from orchestrator.queue import TaskQueue
        tq = TaskQueue()
        agents = register_all_agents(tq)

    executor = PipelineExecutor(agents)

    logging.getLogger("agent").setLevel(logging.INFO)
    logging.getLogger("mcp").setLevel(logging.INFO)

    t0 = time.perf_counter()
    result = executor.execute(COACH_SESSION_PIPELINE, {
        "trigger_type": "coach_transcript",
        "source": vtt,
    })
    elapsed = time.perf_counter() - t0

    logging.getLogger("agent").setLevel(logging.WARNING)
    logging.getLogger("mcp").setLevel(logging.WARNING)

    print(f"\n    {B}Pipeline Result:{X}")
    c = G if result.success else R
    kv("Success", f"{c}{result.success}{X}")
    kv("Steps", f"{result.completed_steps}/{result.total_steps} ok, "
       f"{result.skipped_steps} skipped, {result.failed_steps} failed")
    kv("Duration", f"{elapsed:.1f}s")
    kv("Artifacts", str(result.total_artifacts))

    if result.artifacts:
        print(f"\n    {B}Artifacts:{X}")
        for a in result.artifacts:
            bullet(f"[{a['type']}] {a['description'][:80]}")

    pause()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 4: SHARED MEMORY (Wiki)
# ═══════════════════════════════════════════════════════════════════════
def show_wiki():
    section("4", "Shared Memory — The Project Wiki",
            "Every agent reads from and writes to a shared SQLite knowledge base")

    from pipeline.shared_memory import SharedMemory
    wiki = SharedMemory()
    stats = wiki.stats()

    kv("Total Entries", stats["total_entries"])
    kv("Total Changes (audit)", stats["total_changes"])

    print(f"\n    {B}Namespaces:{X}")
    for ns, count in stats.get("namespaces", {}).items():
        bullet(f"{B}{ns}{X} — {count} entries")

    print(f"\n    {B}Sample entry (latest meeting):{X}")
    latest = wiki.get("latest_runs", "transcript_parser")
    if latest:
        for k, v in latest.items():
            if k in ("agent", "pipeline", "success", "data_keys"):
                kv(k, str(v)[:60], indent=6)

    print(f"\n    {D}Every agent deposits results here. Other pipelines query it.")
    print(f"    This is the 'Karpathy wiki pattern' — accumulating intelligence.{X}")
    pause()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 5: EVENT BUS
# ═══════════════════════════════════════════════════════════════════════
def show_eventbus():
    section("5", "Event Bus — Cross-Pipeline Communication",
            "Publish-subscribe system: one pipeline's output triggers another")

    from pipeline.event_bus import EventBus
    bus = EventBus()
    stats = bus.stats()

    kv("Total Events Emitted", stats["total_events"])
    kv("Active Subscriptions", stats["active_subscriptions"])

    print(f"\n    {B}Events by Type:{X}")
    for etype, count in stats.get("events_by_type", {}).items():
        bullet(f"{B}{etype}{X} — {count} events")

    print(f"\n    {B}Cross-Pipeline Trigger Examples:{X}")
    triggers = [
        ("action_items_extracted", "Requirements → Project Management", "Auto-creates Jira tickets"),
        ("decision_logged", "Requirements → Architecture", "Triggers drift detection"),
        ("new_session_embedded", "Coach Memory → Knowledge", "Updates briefing context"),
        ("recurring_concern", "Coach Memory → Risk", "Flags repeated issues as risks"),
        ("drift_detected", "Architecture → Requirements", "Re-checks requirements alignment"),
    ]
    for event, flow, desc in triggers:
        print(f"      {Y}{event}{X}")
        print(f"        {flow}: {D}{desc}{X}")

    pause()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 6: TRACEABILITY
# ═══════════════════════════════════════════════════════════════════════
def show_traceability():
    section("6", "Unified Traceability Store",
            "Every artifact linked to its origin — concerns → decisions → requirements → Jira → PRs")

    from pipeline.traceability import TraceabilityStore
    ts = TraceabilityStore()
    stats = ts.stats()

    kv("Total Artifacts", stats["total_artifacts"])
    kv("Total Links", stats["total_links"])
    kv("Coverage", f"{stats.get('coverage_pct', 0):.0f}% of artifacts have links")
    kv("Orphaned Concerns", f"{stats.get('concerns_without_action', 0)}/{stats['total_concerns']}")
    kv("Unmitigated Risks", f"{stats.get('risks_without_mitigation', 0)}/{stats['total_risks']}")

    print(f"\n    {B}Artifacts by Type:{X}")
    for atype, count in sorted(stats.get("by_type", {}).items(), key=lambda x: -x[1]):
        bar = "█" * min(count, 40)
        print(f"      {atype:.<20} {count:3d} {G}{bar}{X}")

    print(f"\n    {B}Links by Type:{X}")
    for ltype, count in sorted(stats.get("by_link_type", {}).items(), key=lambda x: -x[1]):
        bar = "█" * min(count // 5, 40)
        print(f"      {ltype:.<20} {count:3d} {C}{bar}{X}")

    print(f"\n    {B}Example Chain — Meeting to Jira Ticket:{X}")
    print(f"      {D}[MEETING] 2026-01-22 Client Call{X}")
    print(f"        {Y}↓ RAISED_IN{X}")
    print(f"      {D}[CONCERN] Vendor spec sheet formats vary widely{X}")
    print(f"        {Y}↓ BECAME{X}")
    print(f"      {D}[REQUIREMENT] REQ-008: Support multiple document formats{X}")
    print(f"        {Y}↓ IMPLEMENTS{X}")
    print(f"      {D}[JIRA] EPARTS-42: Implement multi-format parser{X}")

    print(f"\n    {D}All links built via domain-aware keyword matching — zero LLM tokens.{X}")
    pause()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 7: RISK REGISTER
# ═══════════════════════════════════════════════════════════════════════
def show_risks():
    section("7", "Risk Register", "Auto-populated from architecture, coach sessions, and meetings")

    from pipeline.risk_register import RiskRegister
    rr = RiskRegister()
    stats = rr.stats()

    kv("Total Risks", stats["total"])

    print(f"\n    {B}By Severity:{X}")
    for sev, count in stats.get("by_severity", {}).items():
        color = R if sev == "critical" else Y if sev == "high" else D
        bullet(f"{color}{sev}{X}: {count}")

    print(f"\n    {B}By Category:{X}")
    for cat, count in stats.get("by_category", {}).items():
        bullet(f"{cat}: {count}")

    print(f"\n    {B}Sample risks (top 3):{X}")
    all_risks = rr.get_all()
    for risk in all_risks[:3]:
        sev = risk.get("severity", "?")
        color = R if sev == "critical" else Y if sev == "high" else X
        print(f"      {color}[{sev.upper()}]{X} {risk.get('title', '?')[:65]}")
        print(f"        {D}Mitigation: {risk.get('mitigation', '?')[:65]}{X}")

    pause()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 8: PROMPT REGISTRY
# ═══════════════════════════════════════════════════════════════════════
def show_prompts():
    section("8", "Prompt Registry — Governance",
            "Version-controlled prompts with review workflow and A/B testing")

    from pipeline.prompt_registry import PromptRegistry
    pr = PromptRegistry()
    stats = pr.stats()

    kv("Total Prompts", stats["total_prompts"])
    kv("Total Versions", stats["total_versions"])
    kv("Reviews", stats["total_reviews"])
    kv("A/B Tests", stats["total_ab_tests"])

    print(f"\n    {B}Why this matters:{X}")
    bullet("Without this: 5 team members use 5 different prompts for the same task")
    bullet("With this: one canonical prompt per agent, peer-reviewed, version-pinned")
    bullet("Rollback: if a new prompt version regresses quality, revert to previous")

    print(f"\n    {B}Registered prompts:{X}")
    for p in pr.get_all_prompts():
        bullet(f"{B}{p.get('prompt_name','?')}{X} v{p.get('active_version', '?')} — "
               f"by {p.get('author', '?')}, status: {p.get('status', '?')}")

    pause()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 9: ARTIFACT VERSIONING
# ═══════════════════════════════════════════════════════════════════════
def show_versioning():
    section("9", "Artifact Versioning — Document Evolution",
            "Track how requirements, architecture, risks, and ADRs evolved")

    from pipeline.artifact_versioning import ArtifactVersionStore
    avs = ArtifactVersionStore()
    artifacts = avs.get_all_artifacts()

    kv("Tracked Artifacts", len(artifacts))

    print(f"\n    {B}Artifacts and their versions:{X}")
    for a in artifacts:
        v_count = a.get("version_count", 0)
        print(f"      {G}▸{X} {B}{a['artifact_name']}{X} ({a['artifact_type']})")
        print(f"        Current: v{a['current_version']}  |  {v_count} version(s) recorded")

        if v_count > 0:
            versions = avs.get_versions(a["artifact_name"])
            for v in versions[:2]:
                print(f"        {D}  v{v.get('version', '?')}: {v.get('change_summary', '?')[:55]}{X}")

    print(f"\n    {D}Each version records: who changed it, what triggered the change,")
    print(f"    which meetings/sessions contributed, and a diff summary.{X}")
    pause()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 10: METRICS
# ═══════════════════════════════════════════════════════════════════════
def show_metrics():
    section("10", "Agent Metrics — Performance Dashboard",
            "Every agent run is metered: duration, LLM calls, tokens, cost, errors")

    from pipeline.metrics import MetricsCollector
    mc = MetricsCollector()
    summary = mc.summary()

    kv("Total Agent Runs", summary["total_runs"])
    kv("Successful", summary["successful_runs"])
    kv("Failure Rate", f"{summary['failure_rate']*100:.1f}%")
    kv("Total LLM Calls", summary["total_llm_calls"])
    kv("Total Tokens", f"{summary['total_tokens']:,}")
    kv("Estimated Cost", f"${summary['estimated_cost_usd']:.4f}")
    kv("Human Review Rate", f"{summary['review_rate']*100:.1f}%")

    print(f"\n    {B}Recent runs:{X}")
    for run in mc.recent_runs(5):
        status = f"{G}OK{X}" if run["success"] else f"{R}FAIL{X}"
        print(f"      {status}  {run['agent']:<25} {run['duration_ms']:>6}ms  "
              f"{D}{run['timestamp'][:19]}{X}")

    print(f"\n    {D}This powers the metrics dashboard (dashboard/metrics.html)")
    print(f"    and provides the data for counterfactual analysis.{X}")
    pause()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 11: DASHBOARDS
# ═══════════════════════════════════════════════════════════════════════
def show_dashboards():
    section("11", "Interactive Dashboards",
            "Visual exploration of the entire system")

    dashboards = [
        ("dashboard/interactive_architecture.html",
         "Clickable architecture — expand any pipeline to see agents, SE activities, meta-model"),
        ("dashboard/intelligence.html",
         "Knowledge Graph, Goal Model, WBS, Agent Flow, Traceability Explorer"),
        ("dashboard/architecture.html",
         "Static architecture overview — all 28 agents, 7 pipelines, storage layer"),
        ("dashboard/metrics.html",
         "Agent performance metrics — runs, tokens, cost, errors"),
    ]

    for path, desc in dashboards:
        print(f"    {G}▸{X} {B}{path}{X}")
        print(f"      {desc}\n")

    print(f"    {B}Key Documents:{X}")
    docs = [
        ("docs/ses_explained.md", "Complete SES explanation with diagrams"),
        ("docs/practice_area_requirements.md", "Requirements practice area (ETVX)"),
        ("docs/why_everything.md", "Justification for every component"),
        ("docs/sdlc_choice.md", "SDLC design and rationale"),
        ("docs/ses_assessment.md", "Self-assessment against rubric"),
        ("docs/traceability.md", "Living traceability matrix"),
    ]
    for path, desc in docs:
        bullet(f"{B}{path}{X} — {desc}")

    print()
    pause("Press ENTER to open the dashboards in Chrome")

    import subprocess
    for path, _ in dashboards:
        full = PROJECT_ROOT / path
        if full.exists():
            subprocess.Popen(["open", str(full)])
            time.sleep(0.5)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 12: EXTERNAL INTEGRATIONS (live proof)
# ═══════════════════════════════════════════════════════════════════════
def show_integrations():
    section("12", "Live External Integrations",
            "Show the audience the Jira board and GitHub repo")

    print(f"    {B}Open these in your browser:{X}\n")
    bullet(f"Jira Board:  {B}https://epartsmse.atlassian.net/jira/software/projects/EPARTS/board{X}")
    bullet(f"GitHub Repo: {B}https://github.com/AshrithaG/eparts{X}")
    print(f"\n    {B}What to point out:{X}")
    bullet("Jira tickets created automatically by the ticket_creator agent")
    bullet("P0 items are held for human review (not auto-created)")
    bullet("Each ticket has priority, description, and AI-generated label")
    bullet("GitHub has REQ-XXX.md files committed by the req_extractor agent")
    bullet("Decision logs committed by the decision_logger agent")
    bullet("Every commit message shows [agent:name] for traceability")

    pause()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 13: CLOSING
# ═══════════════════════════════════════════════════════════════════════
def closing():
    section("13", "Summary — Why This Matters")

    print(f"    {B}What we demonstrated:{X}")
    bullet("End-to-end pipeline: .vtt transcript → parsed data → classified → GitHub + Jira")
    bullet("28 agents working as a connected framework, not isolated scripts")
    bullet("Cross-pipeline triggers via Event Bus (e.g., drift detected → architecture)")
    bullet("Shared Memory wiki: agents accumulate knowledge across runs")
    bullet("Full artifact traceability: 184 artifacts, 760 links, zero orphans")
    bullet("Risk register auto-populated from multiple sources")
    bullet("Prompt governance: version-controlled, peer-reviewed prompts")
    bullet("Document evolution tracked across versions")
    bullet("All metrics logged: 160 runs, cost tracking, failure rates")
    bullet("Graceful degradation: works with or without LLM (offline fallback)")

    print(f"\n    {B}Counterfactual — Without AI:{X}")
    bullet("Transcript parsing: ~45 min of manual note-taking vs 30s automated")
    bullet("Priority classification: subjective team debate vs consistent criteria")
    bullet("Jira ticket creation: manual copy-paste vs auto-created with traceability")
    bullet("Drift detection: forgotten until too late vs checked every meeting")
    bullet("Traceability: maintained manually (often abandoned) vs auto-linked")

    print(f"\n{C}{B}{'═'*70}")
    print(f"  Demo Complete")
    print(f"{'═'*70}{X}\n")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════
def main():
    show_banner()
    pause("Press ENTER to begin the demo")

    show_overview()
    agents = run_requirements_pipeline()
    run_coach_pipeline(agents)
    show_wiki()
    show_eventbus()
    show_traceability()
    show_risks()
    show_prompts()
    show_versioning()
    show_metrics()
    show_integrations()
    show_dashboards()
    closing()


if __name__ == "__main__":
    main()
