#!/usr/bin/env python3
"""
LIVE DEMO — Run the full Requirements Pipeline on a meeting transcript.

Usage:
    python demo.py                          # uses the latest client meeting
    python demo.py transcripts/some.vtt     # specific file

What happens:
    1. Parses the .vtt transcript into structured data
    2. Classifies items as P0/P1/P2 (using Gemini/Claude)
    3. Extracts formal requirements → commits to GitHub
    4. Creates Jira tickets for action items
    5. Publishes meeting minutes
    6. Logs decisions → commits to GitHub
    7. Detects architecture drift via RAG

Each step prints live progress with colored output.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from glob import glob
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── colours ──────────────────────────────────────────────────────────
CYAN = "\033[96m"; GREEN = "\033[92m"; YELLOW = "\033[93m"
RED = "\033[91m"; MAGENTA = "\033[95m"; DIM = "\033[2m"
BOLD = "\033[1m"; RESET = "\033[0m"

logging.basicConfig(
    level=logging.INFO,
    format=f"{DIM}%(asctime)s{RESET} [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.WARNING)


def banner():
    print(f"""
{CYAN}{BOLD}╔══════════════════════════════════════════════════════════════════╗
║          eParts Agentic SE System — Live Pipeline Demo          ║
║          Requirements Engineering  ·  End-to-End                ║
╚══════════════════════════════════════════════════════════════════╝{RESET}
""")


def show_config(vtt_path: str):
    from agents.base import AgentSettings
    from mcp.jira import JiraMCP
    from mcp.github import GitHubMCP

    s = AgentSettings()
    jira = JiraMCP()
    gh = GitHubMCP()

    provider = s.active_provider
    model = s.gemini_model if provider == "gemini" else (
        s.claude_model if provider == "anthropic" else "n/a"
    )

    print(f"  {BOLD}Transcript{RESET}   {Path(vtt_path).name}")
    if provider == "none":
        print(f"  {BOLD}LLM{RESET}          {YELLOW}Offline (keyword heuristics){RESET}")
    else:
        print(f"  {BOLD}LLM{RESET}          {GREEN}{provider}{RESET} / {model}")
    print(f"  {BOLD}Jira{RESET}         {GREEN}Connected{RESET} ({jira._url})" if jira.is_configured
          else f"  {BOLD}Jira{RESET}         {YELLOW}Not configured{RESET}")
    print(f"  {BOLD}GitHub{RESET}       {GREEN}Connected{RESET} ({gh._repo})" if gh.is_configured
          else f"  {BOLD}GitHub{RESET}       {YELLOW}Not configured{RESET}")
    print()


def show_step(step_idx: int, total: int, agent_name: str, desc: str):
    bar = f"[{step_idx+1}/{total}]"
    print(f"\n{CYAN}{'─'*66}{RESET}")
    print(f"  {BOLD}{bar}{RESET}  {YELLOW}{agent_name}{RESET}  ·  {desc}")
    print(f"{CYAN}{'─'*66}{RESET}")


def show_step_result(sr):
    if sr.skipped:
        print(f"  Result: {DIM}SKIPPED (upstream empty){RESET}")
        return
    status = f"{GREEN}OK{RESET}" if sr.success else f"{RED}FAIL{RESET}"
    print(f"  Result:    {status}  ({sr.duration_ms:,}ms)")
    if sr.llm_calls > 0:
        print(f"  LLM:       {sr.llm_calls} call(s), ~{sr.tokens_used:,} tokens")
    for o in sr.outputs:
        print(f"  Output:    {GREEN}▸{RESET} {o['description']}")
    if sr.requires_human_review:
        print(f"  {YELLOW}⚠  Flagged for human review{RESET}")
    for e in sr.errors:
        print(f"  {RED}Error: {e[:140]}{RESET}")


def show_summary(result):
    print(f"\n{CYAN}{BOLD}{'═'*66}{RESET}")
    print(f"{BOLD}  Pipeline Complete — {result.pipeline_name}{RESET}")
    print(f"{CYAN}{'═'*66}{RESET}\n")

    c = GREEN if result.success else RED
    print(f"  Success:        {c}{result.success}{RESET}")
    print(f"  Steps:          {result.completed_steps}/{result.total_steps} ok, "
          f"{result.skipped_steps} skipped, {result.failed_steps} failed")
    print(f"  Duration:       {result.total_duration_ms:,}ms "
          f"({result.total_duration_ms/1000:.1f}s)")
    print(f"  LLM Calls:      {result.total_llm_calls}")
    print(f"  Tokens:         {result.total_tokens:,}")
    print(f"  Artifacts:      {result.total_artifacts}")
    if result.requires_human_review:
        print(f"  Human Review:   {YELLOW}Yes{RESET}")

    if result.artifacts:
        print(f"\n  {BOLD}Artifacts Produced:{RESET}")
        for a in result.artifacts:
            print(f"    {GREEN}▸{RESET} [{a['type']}] {a['description']}")

    print(f"\n{CYAN}{'═'*66}{RESET}\n")


def show_wiki_snapshot():
    """Show what's in shared memory after the pipeline ran."""
    print(f"\n{BOLD}  Shared Memory (Wiki) — latest entries:{RESET}")
    try:
        from pipeline.shared_memory import SharedMemory
        wiki = SharedMemory()
        stats = wiki.stats()
        print(f"    Namespaces: {stats.get('namespaces', 'n/a')}")
        print(f"    Total entries: {stats.get('total_entries', 'n/a')}")
    except Exception as e:
        print(f"    {DIM}(could not read: {e}){RESET}")


def show_event_snapshot():
    """Show events emitted during the pipeline run."""
    print(f"\n{BOLD}  Event Bus — recent events:{RESET}")
    try:
        from pipeline.event_bus import EventBus
        bus = EventBus()
        stats = bus.stats()
        print(f"    Total events: {stats.get('total_events', 'n/a')}")
        print(f"    Event types: {', '.join(stats.get('event_types', []))}")
    except Exception as e:
        print(f"    {DIM}(could not read: {e}){RESET}")


def show_next_steps():
    print(f"\n{BOLD}  Where to see the results:{RESET}")
    print(f"    {GREEN}▸{RESET} Jira board:     https://epartsmse.atlassian.net/jira/software/projects/EPARTS/board")
    print(f"    {GREEN}▸{RESET} GitHub repo:     https://github.com/AshrithaG/eparts")
    print(f"    {GREEN}▸{RESET} Dashboard:       open dashboard/interactive_architecture.html")
    print(f"    {GREEN}▸{RESET} Intelligence:    open dashboard/intelligence.html")
    print()


# ── monkeypatch PipelineExecutor to show live step progress ──────────
def _patch_executor(executor, pipeline):
    """Wrap the real executor so we see each step live."""
    original = executor.execute

    def wrapped(pipe, trigger_payload):
        import uuid as _uuid
        from pipeline.pipelines import (
            PipelineContext, StepResult, PipelineResult
        )
        from agents.base import AgentTrigger
        from dataclasses import asdict

        pid = f"pipe-{pipe.name}-{_uuid.uuid4().hex[:8]}"
        ctx = PipelineContext(
            pipeline_id=pid, pipeline_name=pipe.name,
            trigger_type=trigger_payload.get("trigger_type", "manual"),
            source=trigger_payload.get("source", "unknown"),
            data=dict(trigger_payload),
        )
        results = []
        ok = True
        t0 = time.perf_counter()
        tot_llm = tot_tok = 0
        needs_review = False

        for i, step in enumerate(pipe.steps):
            ctx.current_step = i
            show_step(i, len(pipe.steps), step.agent_name, step.description)

            if step.skip_if_empty:
                val = ctx.get(step.skip_if_empty)
                if not val:
                    sr = StepResult(
                        step_index=i, agent_name=step.agent_name,
                        description=step.description, success=True,
                        skipped=True, duration_ms=0, outputs=[], errors=[],
                        llm_calls=0, tokens_used=0, artifacts_produced=0,
                        requires_human_review=False,
                    )
                    results.append(sr)
                    show_step_result(sr)
                    continue

            agent = executor._agents.get(step.agent_name)
            if not agent:
                sr = StepResult(
                    step_index=i, agent_name=step.agent_name,
                    description=step.description, success=False,
                    skipped=False, duration_ms=0, outputs=[],
                    errors=[f"Agent not found: {step.agent_name}"],
                    llm_calls=0, tokens_used=0, artifacts_produced=0,
                    requires_human_review=False,
                )
                results.append(sr)
                show_step_result(sr)
                if step.required:
                    ok = False; break
                continue

            trigger = AgentTrigger(
                trigger_type=ctx.trigger_type,
                source=ctx.source,
                metadata={
                    "pipeline_id": pid,
                    "pipeline_step": i,
                    "pipeline_context": ctx.data,
                },
            )

            st = time.perf_counter()
            try:
                res = agent.execute(trigger)
                ms = int((time.perf_counter() - st) * 1000)
                s_llm = getattr(agent, '_run_llm_calls', 0)
                s_tok = getattr(agent, '_run_total_tokens', 0)
                tot_llm += s_llm; tot_tok += s_tok

                if step.output_key:
                    if res.data:
                        ctx.set(step.output_key, res.data)
                    elif res.outputs:
                        ctx.set(step.output_key, [asdict(o) for o in res.outputs])
                for k, v in res.data.items():
                    ctx.set(k, v)

                executor._deposit_to_wiki(pipe, step, res)

                for o in res.outputs:
                    ctx.add_artifact(o.output_type, o.description, o.reference)
                if res.requires_human_review:
                    needs_review = True

                sr = StepResult(
                    step_index=i, agent_name=step.agent_name,
                    description=step.description, success=res.success,
                    skipped=False, duration_ms=ms,
                    outputs=[asdict(o) for o in res.outputs],
                    errors=res.errors,
                    llm_calls=s_llm, tokens_used=s_tok,
                    artifacts_produced=len(res.outputs),
                    requires_human_review=res.requires_human_review,
                )
                results.append(sr)
                show_step_result(sr)
                if not res.success and step.required:
                    ok = False; break

            except Exception as exc:
                ms = int((time.perf_counter() - st) * 1000)
                sr = StepResult(
                    step_index=i, agent_name=step.agent_name,
                    description=step.description, success=False,
                    skipped=False, duration_ms=ms, outputs=[],
                    errors=[f"{type(exc).__name__}: {exc}"],
                    llm_calls=0, tokens_used=0, artifacts_produced=0,
                    requires_human_review=False,
                )
                results.append(sr)
                show_step_result(sr)
                if step.required:
                    ok = False; break

        total_ms = int((time.perf_counter() - t0) * 1000)
        from datetime import datetime, timezone
        comp = sum(1 for s in results if not s.skipped and s.success)
        skip = sum(1 for s in results if s.skipped)
        fail = sum(1 for s in results if not s.skipped and not s.success)

        return PipelineResult(
            pipeline_id=pid, pipeline_name=pipe.name,
            practice_area=pipe.practice_area,
            trigger_source=ctx.source, success=ok,
            total_steps=len(pipe.steps), completed_steps=comp,
            skipped_steps=skip, failed_steps=fail,
            total_duration_ms=total_ms, total_llm_calls=tot_llm,
            total_tokens=tot_tok, total_artifacts=len(ctx.artifacts),
            requires_human_review=needs_review, step_results=results,
            artifacts=ctx.artifacts,
            context_snapshot={k: type(v).__name__ for k, v in ctx.data.items()},
            started_at=ctx.started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    executor.execute = wrapped


def main():
    # ── resolve transcript ──────────────────────────────────────────
    if len(sys.argv) > 1:
        vtt = sys.argv[1]
    else:
        vtts = sorted(glob(str(PROJECT_ROOT / "transcripts" / "*.transcript.vtt")))
        if not vtts:
            print(f"{RED}No .vtt files found in transcripts/{RESET}")
            sys.exit(1)
        vtt = vtts[-1]

    banner()
    show_config(vtt)

    input(f"  {MAGENTA}Press ENTER to start the pipeline ▸{RESET} ")

    # ── register agents ─────────────────────────────────────────────
    print(f"\n{DIM}  Registering agents...{RESET}")
    from orchestrator.registry import register_all_agents
    from orchestrator.queue import TaskQueue
    from pipeline.pipelines import REQUIREMENTS_PIPELINE, PipelineExecutor

    tq = TaskQueue()
    agents = register_all_agents(tq)
    print(f"  {GREEN}✓ {len(agents)} agents registered{RESET}")

    print(f"\n  {BOLD}Pipeline:{RESET} {REQUIREMENTS_PIPELINE.name}")
    print(f"  {BOLD}Practice Area:{RESET} {REQUIREMENTS_PIPELINE.practice_area}")
    print(f"  {BOLD}Steps:{RESET} {len(REQUIREMENTS_PIPELINE.steps)}")
    print(f"  {BOLD}Trigger:{RESET} transcript → {vtt}")

    # ── run pipeline with live output ───────────────────────────────
    executor = PipelineExecutor(agents)
    _patch_executor(executor, REQUIREMENTS_PIPELINE)

    result = executor.execute(REQUIREMENTS_PIPELINE, {
        "trigger_type": "transcript",
        "source": vtt,
    })

    # ── summary ─────────────────────────────────────────────────────
    show_summary(result)
    show_wiki_snapshot()
    show_event_snapshot()
    show_next_steps()


if __name__ == "__main__":
    main()
