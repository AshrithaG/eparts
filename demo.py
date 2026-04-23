#!/usr/bin/env python3
"""
eParts Agentic SE System — Live Demo Script

Run this during the presentation to demonstrate the full pipeline
processing a real meeting transcript end-to-end.

Usage:
    python demo.py                          # Full demo (all sections)
    python demo.py --section requirements   # Just requirements pipeline
    python demo.py --section coach          # Just coach session pipeline
    python demo.py --section search         # Just semantic search demo
    python demo.py --section briefing       # Just briefing generation
    python demo.py --section stats          # Just system stats
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# ── Pretty printing ──────────────────────────────────────────────────
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
PURPLE = "\033[95m"

def banner(text: str) -> None:
    w = 70
    print(f"\n{CYAN}{'═' * w}")
    print(f"  {BOLD}{text}{RESET}{CYAN}")
    print(f"{'═' * w}{RESET}\n")

def section(text: str) -> None:
    print(f"\n{PURPLE}{'─' * 50}")
    print(f"  {BOLD}{text}{RESET}")
    print(f"{PURPLE}{'─' * 50}{RESET}")

def ok(text: str) -> None:
    print(f"  {GREEN}✓{RESET} {text}")

def warn(text: str) -> None:
    print(f"  {YELLOW}⚠{RESET} {text}")

def info(text: str) -> None:
    print(f"  {DIM}→{RESET} {text}")

def step(n: int, text: str) -> None:
    print(f"\n  {CYAN}{BOLD}Step {n}{RESET}  {text}")

def pause(msg: str = "Press Enter to continue...") -> None:
    input(f"\n  {DIM}{msg}{RESET}")


# ── Demo sections ────────────────────────────────────────────────────

def demo_stats() -> None:
    """Show system statistics."""
    banner("SYSTEM INVENTORY")

    from mcp.vector_store import VectorStoreMCP
    from agents.coach_memory.session_memory import init_db
    from pipeline.pipelines import ALL_PIPELINES
    import os

    db = init_db()
    vs = VectorStoreMCP()

    sessions = db.execute("SELECT COUNT(*) as c FROM sessions").fetchone()["c"]
    commitments = db.execute("SELECT COUNT(*) as c FROM commitments").fetchone()["c"]
    coach_chunks = vs.count("coach_sessions")
    knowledge_chunks = vs.count("project_knowledge")

    py_files = 0
    py_lines = 0
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in {".venv", "__pycache__", ".git", "node_modules", "memory"}]
        for f in files:
            if f.endswith(".py"):
                py_files += 1
                py_lines += sum(1 for _ in open(os.path.join(root, f)))

    total_steps = sum(len(p.steps) for p in ALL_PIPELINES.values())
    unique_agents = len(set(s.agent_name for p in ALL_PIPELINES.values() for s in p.steps))

    print(f"  {BOLD}Codebase{RESET}")
    info(f"Python files:    {BOLD}{py_files}{RESET}")
    info(f"Lines of code:   {BOLD}{py_lines:,}{RESET}")
    print()
    print(f"  {BOLD}Framework{RESET}")
    info(f"Pipelines:       {BOLD}{len(ALL_PIPELINES)}{RESET}")
    info(f"Pipeline steps:  {BOLD}{total_steps}{RESET}")
    info(f"Unique agents:   {BOLD}{unique_agents}{RESET}")
    print()
    print(f"  {BOLD}Data Processed{RESET}")
    info(f"Coach sessions:  {BOLD}{sessions}{RESET}")
    info(f"Commitments:     {BOLD}{commitments}{RESET}")
    info(f"ChromaDB chunks: {BOLD}{coach_chunks + knowledge_chunks}{RESET} ({coach_chunks} sessions + {knowledge_chunks} knowledge)")


def demo_requirements() -> None:
    """Run the Requirements pipeline on a real transcript."""
    banner("REQUIREMENTS PIPELINE — Live Demo")

    from pipeline.pipelines import ALL_PIPELINES, PipelineExecutor
    from orchestrator.registry import register_all_agents
    from orchestrator.queue import TaskQueue

    vtt = "transcripts/GMT20260402-180648_Recording.transcript.vtt"
    print(f"  {BOLD}Input:{RESET} {vtt}")
    print(f"  {DIM}Apr 2 sprint review — Jaivard, Hrishik, Harsha, Ashritha{RESET}")

    step(1, "Initialize pipeline executor with all agents")
    t0 = time.perf_counter()
    tq = TaskQueue()
    agents = register_all_agents(tq)
    executor = PipelineExecutor(agents)
    ok(f"25 agents registered in {int((time.perf_counter() - t0) * 1000)}ms")

    step(2, "Execute Requirements Pipeline (7 steps)")
    print()
    t0 = time.perf_counter()
    result = executor.execute(
        ALL_PIPELINES["requirements"],
        {"trigger_type": "transcript", "source": vtt, "metadata": {"meeting_type": "client"}},
    )

    for sr in result.step_results:
        status = f"{GREEN}OK{RESET}" if sr.success else (f"{DIM}SKIP{RESET}" if sr.skipped else f"{RED}FAIL{RESET}")
        desc = sr.outputs[0]["description"][:70] if sr.outputs else "skipped"
        print(f"    {sr.step_index + 1}. [{status}] {BOLD}{sr.agent_name:22s}{RESET} {sr.duration_ms:4d}ms  {desc}")

    elapsed = int((time.perf_counter() - t0) * 1000)
    status_color = GREEN if result.success else RED
    status_text = "SUCCESS" if result.success else "FAILED"
    print(f"\n  {status_color}{BOLD}{status_text}{RESET} — {result.completed_steps}/{result.total_steps} steps, {elapsed}ms, {result.total_artifacts} artifacts")


def demo_coach() -> None:
    """Run the Coach Session pipeline on Cory Gwin's session."""
    banner("COACH SESSION MEMORY PIPELINE — Live Demo")

    from pipeline.pipelines import ALL_PIPELINES, PipelineExecutor
    from orchestrator.registry import register_all_agents
    from orchestrator.queue import TaskQueue

    vtt = "coach_meetings/GMT20260224-220446_Recording.transcript.vtt"
    print(f"  {BOLD}Input:{RESET} Cory Gwin coaching session (Feb 24)")
    print(f"  {DIM}Topics: SES, agent feedback loops, code organization, ADRs{RESET}")

    step(1, "Execute Coach Session Pipeline (6 steps)")
    print()
    tq = TaskQueue()
    agents = register_all_agents(tq)
    executor = PipelineExecutor(agents)

    t0 = time.perf_counter()
    result = executor.execute(
        ALL_PIPELINES["coach_session"],
        {"trigger_type": "coach_transcript", "source": vtt, "metadata": {"meeting_type": "coach"}},
    )

    for sr in result.step_results:
        status = f"{GREEN}OK{RESET}" if sr.success else (f"{DIM}SKIP{RESET}" if sr.skipped else f"{RED}FAIL{RESET}")
        desc = sr.outputs[0]["description"][:70] if sr.outputs else "no output"
        print(f"    {sr.step_index + 1}. [{status}] {BOLD}{sr.agent_name:22s}{RESET} {sr.duration_ms:4d}ms  {desc}")

    elapsed = int((time.perf_counter() - t0) * 1000)
    status_color = GREEN if result.success else RED
    status_text = "SUCCESS" if result.success else "FAILED"
    print(f"\n  {status_color}{BOLD}{status_text}{RESET} — {result.completed_steps}/{result.total_steps} steps, {elapsed}ms")

    step(2, "ChromaDB state after embedding")
    from mcp.vector_store import VectorStoreMCP
    vs = VectorStoreMCP()
    count = vs.count("coach_sessions")
    ok(f"{count} total chunks in coach_sessions collection")


def demo_search() -> None:
    """Demonstrate semantic search across the knowledge base."""
    banner("SEMANTIC SEARCH — Live Demo")

    from mcp.vector_store import VectorStoreMCP

    vs = VectorStoreMCP()
    queries = [
        ("coach_sessions", "What did Cory say about agent visibility and code organization?"),
        ("coach_sessions", "Azure environment constraints and tool lock-in"),
        ("coach_sessions", "human in the loop review process design"),
        ("project_knowledge", "confidence threshold calibration for ML model"),
        ("project_knowledge", "ETVX process documentation and measurement system"),
        ("project_knowledge", "risk mitigation when blocked on client data"),
    ]

    for collection, query in queries:
        section(f"Collection: {collection}")
        print(f"  {BOLD}Query:{RESET} \"{query}\"")
        print()

        results = vs.query(collection, query, n_results=2)
        for i, r in enumerate(results):
            doc = r["document"][:150].replace("\n", " ")
            src = r["metadata"].get("source", r["metadata"].get("session_type", "?"))
            dist = r["distance"]
            color = GREEN if dist < 0.5 else YELLOW if dist < 0.7 else RED
            print(f"    {color}[{dist:.3f}]{RESET} ({src})")
            print(f"    {DIM}{doc}...{RESET}")
            print()


def demo_briefing() -> None:
    """Generate a pre-meeting briefing from all accumulated data."""
    banner("PRE-MEETING BRIEFING GENERATOR")

    from agents.coach_memory.briefing_generator import BriefingGeneratorAgent
    from agents.base import AgentTrigger

    step(1, "Gathering context from SQLite + ChromaDB + concern tracker")
    agent = BriefingGeneratorAgent(mcp_clients={"vector_store": None})
    trigger = AgentTrigger(
        trigger_type="cron_pre_meeting",
        source="manual",
        metadata={"meeting_type": "coach"},
    )

    t0 = time.perf_counter()
    result = agent.execute(trigger)
    elapsed = int((time.perf_counter() - t0) * 1000)

    ok(f"Briefing generated in {elapsed}ms")
    print()

    briefing = result.data.get("briefing", "")
    for line in briefing.split("\n")[:30]:
        if line.startswith("#"):
            print(f"  {BOLD}{CYAN}{line}{RESET}")
        elif line.startswith("-"):
            print(f"  {line}")
        else:
            print(f"  {DIM}{line}{RESET}")

    if briefing.count("\n") > 30:
        print(f"  {DIM}... ({briefing.count(chr(10)) - 30} more lines){RESET}")


def demo_all() -> None:
    """Run all demo sections in sequence."""
    banner("ePARTS AGENTIC SE SYSTEM — FULL DEMO")
    print(f"  {BOLD}Team:{RESET} Pimsie Supreme")
    print(f"  {BOLD}Program:{RESET} CMU MSE Studio 2026")
    print(f"  {BOLD}Client:{RESET} eParts Services LLC")
    print()
    print(f"  This demo shows the complete SES infrastructure processing")
    print(f"  real team data — meeting transcripts, coach sessions, and")
    print(f"  project documents — through multi-agent pipelines.")

    pause()
    demo_stats()
    pause()
    demo_requirements()
    pause()
    demo_coach()
    pause()
    demo_search()
    pause()
    demo_briefing()

    banner("DEMO COMPLETE")
    print(f"  {GREEN}{BOLD}All pipelines demonstrated with real data.{RESET}")
    print(f"  {DIM}Dashboard: open dashboard/metrics.html in browser{RESET}")
    print()


# ── Entry point ──────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="eParts SES Demo")
    parser.add_argument(
        "--section",
        choices=["requirements", "coach", "search", "briefing", "stats", "all"],
        default="all",
        help="Which demo section to run",
    )
    parser.add_argument("--no-pause", action="store_true", help="Skip pauses between sections")
    args = parser.parse_args()

    if args.no_pause:
        global pause
        pause = lambda msg="": None

    dispatch = {
        "stats": demo_stats,
        "requirements": demo_requirements,
        "coach": demo_coach,
        "search": demo_search,
        "briefing": demo_briefing,
        "all": demo_all,
    }
    dispatch[args.section]()


if __name__ == "__main__":
    main()
