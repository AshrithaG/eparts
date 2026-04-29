#!/usr/bin/env python3
"""
LIVE DEMO — Run the full Requirements Pipeline on a meeting transcript.

Usage:
    python demo.py                          # uses the latest client meeting
    python demo.py transcripts/some.vtt   # specific file
    python demo.py --auto                 # skip all "press ENTER" prompts
    python demo.py --step                 # press ENTER after each agent (live presentation)
    python demo.py examples/x.vtt --step  # transcript + step-through

    SES_DEMO_AUTO=1 python demo.py        # same as --auto
    SES_DEMO_STEP=1 python demo.py        # same as --step (Enter after each step)

What happens:
    1. Parses the .vtt transcript into structured data
    2. Classifies items as P0/P1/P2 (using Gemini/Claude)
    3. Extracts formal requirements → commits to GitHub
    4. Creates Jira tickets for action items
    5. Publishes meeting minutes
    6. Logs decisions → commits to GitHub
    7. Detects architecture drift via RAG

Each step prints a live DAG-style runner view, coloured progress, then a
specific “Presenter — what to show now” cue (URLs, clicks, narration).
"""
from __future__ import annotations

import json
import logging
import os
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

# Deep links referenced in presenter cues (match DEMO_PLAYBOOK / .env URLs)
GH_REPO = os.environ.get(
    "DEMO_PRESENT_GITHUB_URL",
    "https://github.com/AshrithaG/eparts",
).rstrip("/")
JIRA_PROJECT_URL = os.environ.get(
    "DEMO_PRESENT_JIRA_URL",
    "https://epartsmse.atlassian.net/jira/software/projects/EPARTS/board",
).rstrip("/")

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


def show_pipeline_execution_view(pipe, *, running_index: int) -> None:
    """ASCII view of REQUIREMENTS_PIPELINE while a step executes."""
    steps = getattr(pipe, "steps", ()) or ()
    total = len(steps)
    if total == 0:
        return
    pct = round(24 * running_index / max(total, 1))
    prog = "[" + "#" * pct + "-" * (24 - pct) + "]"
    label = f"{running_index + 1}/{total}"
    print(f"\n  {BOLD}Pipeline in execution{RESET}  {DIM}{prog}{RESET}  {CYAN}{label}{RESET}")
    print(f"  {DIM}{pipe.name} · {getattr(pipe, 'practice_area', '')}{RESET}")
    for i, s in enumerate(steps):
        name = s.agent_name
        if i < running_index:
            mark = f"{GREEN}✓{RESET}"
            state = f"{DIM}done{RESET}"
        elif i == running_index:
            mark = f"{YELLOW}▶{RESET}"
            state = f"{YELLOW}RUNNING{RESET}"
        else:
            mark = f"{DIM}·{RESET}"
            state = f"{DIM}pending{RESET}"
        etvx = getattr(s, "etvx_id", "") or ""
        etvx_s = f" {DIM}({etvx}){RESET}" if etvx else ""
        print(f"    {mark}  {BOLD}{name}{RESET}{etvx_s}  {state}")
    print(f"  {CYAN}{'─'*62}{RESET}")


def show_presenter_cue(agent_name: str, sr, *, dash_mode: bool) -> None:
    """What to flash in browser / narration after this REQUIREMENTS_PIPELINE step."""

    lines = _presenter_cue_lines(agent_name, sr)
    if not lines:
        return
    print(f"\n  {MAGENTA}{BOLD}▸ Presenter — what to show now{RESET}")
    for line in lines:
        print(f"     {line}")
    if dash_mode:
        print(f"  {DIM}— use --step to pause before the next agent after this narration —{RESET}")


def _presenter_cue_lines(agent_name: str, sr) -> list[str]:
    """Renderable lines with terminal-friendly emphasis."""

    skipped = getattr(sr, "skipped", False)
    failed = getattr(sr, "success", True) is False and not skipped

    if skipped:
        return [
            f"{YELLOW}{BOLD}Skipped.{RESET} No downstream writes for this beat — upstream was empty.",
            f"{DIM}Stay on the terminal; skip Jira/GitHub until a later cue.{RESET}",
        ]
    if failed:
        errs = getattr(sr, "errors", []) or []
        first = errs[0][:120] if errs else "(see errors above)"
        return [
            f"{RED}{BOLD}This step failed.{RESET} Gesture at stderr above and describe "
            "retry vs heuristic/offline continuation.",
            f"{RED}Hint:{RESET} {first}",
        ]

    reqs_tree = f"{GH_REPO}/tree/main/requirements/parsed"
    reqs_commits = f"{GH_REPO}/commits/main"
    decisions_blob = f"{GH_REPO}/blob/main/minutes/decisions.log.md"

    cues: dict[str, list[str]] = {
        "transcript_parser": [
            f"{BOLD}Terminal:{RESET} Point at stdout — parsed action items / decisions "
            "that downstream agents reuse.",
            f"{DIM}Narrative: “Structured minutes from upload — GitHub/Jira stay cold until REQ + tickets.”{RESET}",
            f"{DIM}(Optional:{RESET} bounce to the `{CYAN}.vtt{DIM}` file on disk — source-of-truth for the ingest.)",
        ],
        "priority_classifier": [
            f"{BOLD}Terminal:{RESET} Walk P0/P1/P2 tagging (risk posture vs schedule wins).",
            f"{YELLOW}Important:{RESET} P0 items stall for humans — cite the yellow ⚠ cue after "
            "ticket_creator runs.",
            f"{DIM}Do not open Jira yet — wait for `ticket_creator` so “Created” sort shows today’s work.{RESET}",
        ],
        "req_extractor": [
            f"{BOLD}GitHub → requirements/parsed:{RESET}",
            reqs_tree,
            f"{BOLD}Show:{RESET} the `REQ-***.md` file named by the Output ▸ lines (commit `[agent:req_extractor]`).",
            f"{BOLD}Commits:{RESET} {reqs_commits} newest entry on `main`.",
        ],
        "ticket_creator": [
            f"{BOLD}Jira backlog / board:{RESET}",
            JIRA_PROJECT_URL,
            f"{BOLD}Filter/sort:{RESET} sort by {BOLD}Created (desc){RESET} → fresh rows from this run.",
            f"{BOLD}Look for labels:{RESET} `AI-generated`, priority tag `P1`/`P2`, `agent-ticket_creator`.",
            f"{YELLOW}If P0s exist,{RESET} the terminal ⚠ warns — emphasize review queue behaviour "
            "(not auto-filed tickets).",
        ],
        "minutes_publisher": [
            f"{BOLD}If Confluence is live:{RESET} Space ▸ Client Meetings ▸ page "
            "`Client — YYYY‑MM‑DD`.",
            f"{YELLOW}Offline / skipped:{RESET} highlight Output ▸ publish_skipped (expected without secrets).",
            f"{BOLD}Fallback mirror:{RESET} {GH_REPO}/tree/main/minutes whenever minutes files commit.",
        ],
        "decision_logger": [
            f"{BOLD}GitHub file:{RESET}",
            decisions_blob,
            f"{BOLD}Show:{RESET} last rows appended to `{BOLD}minutes/decisions.log.md{RESET}` (markdown table footer).",
        ],
        "drift_detector": [
            f"{BOLD}Terminal:{RESET} summarise drift deltas vs canon architecture excerpt.",
            f"{BOLD}Local dashboards:{RESET} `{CYAN}{PROJECT_ROOT / 'dashboard' / 'intelligence.html'}{RESET} "
            f"& `{CYAN}{PROJECT_ROOT / 'dashboard' / 'interactive_architecture.html'}{RESET}`.",
            f"{DIM}Call out REQ-DRIFT-CHECK ({BOLD}ETVX{RESET}{DIM}) vs deep ARCH drift later.{RESET}",
        ],
    }

    raw = cues.get(agent_name)
    if not raw:
        return [
            f"{BOLD}Terminal:{RESET} Re-read Outputs above.",
            f"{DIM}See DEMO_PLAYBOOK.md § Section 2 (Live Requirements Pipeline).{RESET}",
        ]
    return raw


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
    print(f"    {GREEN}▸{RESET} Jira board:     {JIRA_PROJECT_URL}")
    print(f"    {GREEN}▸{RESET} GitHub repo:     {GH_REPO}")
    print(f"    {GREEN}▸{RESET} Dashboard:       open dashboard/interactive_architecture.html")
    print(f"    {GREEN}▸{RESET} Intelligence:    open dashboard/intelligence.html")
    print()


def parse_demo_cli():
    """Return (vtt_path|None, auto: bool, step_through: bool)."""
    argv = sys.argv[1:]
    auto = "--auto" in argv or os.environ.get("SES_DEMO_AUTO", "").lower() in ("1", "true", "yes")
    step_through = "--step" in argv or os.environ.get("SES_DEMO_STEP", "").lower() in ("1", "true", "yes")
    filtered = [a for a in argv if a not in ("--auto", "--step")]
    vtt = None
    for a in filtered:
        if ".vtt" in a.lower() or Path(a).suffix.lower() in (".vtt",):
            vtt = a
            break
    return vtt, auto, step_through


# ── monkeypatch PipelineExecutor to show live step progress ──────────
def _patch_executor(executor, pipeline, *, step_through: bool = False, auto: bool = False):
    """Wrap the real executor so we see each step live."""
    original = executor.execute

    def pause_after_step(step_index: int):
        if not step_through or auto:
            return
        if step_index >= len(pipeline.steps) - 1:
            return
        input(f"  {MAGENTA}Press ENTER for the next agent ▸{RESET} ")

    dash_present = step_through and not auto

    def finish_step(agent_name: str, sr, idx: int):
        show_step_result(sr)
        show_presenter_cue(agent_name, sr, dash_mode=dash_present)
        pause_after_step(idx)

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
            show_pipeline_execution_view(pipe, running_index=i)
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
                    finish_step(step.agent_name, sr, i)
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
                finish_step(step.agent_name, sr, i)
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
                finish_step(step.agent_name, sr, i)
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
                finish_step(step.agent_name, sr, i)
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
    vtt_arg, auto, step_through = parse_demo_cli()

    # ── resolve transcript ──────────────────────────────────────────
    if vtt_arg is None:
        vtts = sorted(glob(str(PROJECT_ROOT / "transcripts" / "*.transcript.vtt")))
        if not vtts:
            print(f"{RED}No .vtt files found in transcripts/{RESET}")
            sys.exit(1)
        vtt = vtts[-1]
    else:
        vtt = str(Path(vtt_arg).expanduser().resolve())
        if not Path(vtt).is_file():
            print(f"{RED}Transcript not found: {vtt}{RESET}")
            sys.exit(1)

    banner()
    show_config(vtt)

    if not auto:
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
    _patch_executor(
        executor, REQUIREMENTS_PIPELINE, step_through=step_through, auto=auto
    )

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
