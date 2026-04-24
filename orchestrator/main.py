"""
Central Orchestrator — FastAPI server for the eParts agentic system.

Three entry points:
  POST /webhook       — receives external events (Jira, Slack, GitHub, Drive)
  POST /trigger       — manual API trigger for any agent
  GET  /health        — health check + queue status

Pure routing and queue management. Does NOT make LLM calls.
All agent execution is dispatched through the shared TaskQueue.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from orchestrator.queue import AgentTask, TaskQueue
from orchestrator.router import resolve_agents

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("orchestrator")

task_queue = TaskQueue()
_agent_instances: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Lifespan — start/stop the task queue worker
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent_instances
    from orchestrator.registry import register_all_agents
    _agent_instances = register_all_agents(task_queue)
    task_queue.start()
    logger.info("Orchestrator started — all agents registered")
    yield
    task_queue.stop()
    logger.info("Orchestrator shut down")


app = FastAPI(
    title="eParts Agentic Orchestrator",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class WebhookPayload(BaseModel):
    trigger_type: str = Field(
        ...,
        description="One of: transcript, coach_transcript, jira_webhook, "
                    "pr_event, slack_event, poc_result",
    )
    source: str = Field(..., description="File path, URL, or event identifier")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ManualTriggerPayload(BaseModel):
    agent: str = Field(..., description="Agent name to invoke directly")
    payload: dict[str, Any] = Field(default_factory=dict)


class TaskResponse(BaseModel):
    task_ids: list[str]
    agents: list[str]
    message: str


class TaskStatusResponse(BaseModel):
    task_id: str
    result: Any | None
    found: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "queue_running": task_queue.is_running,
        "queue_pending": task_queue.pending_count,
        "agents_registered": len(task_queue._agent_registry),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/agents")
async def list_agents():
    """List all registered agents and their route mappings."""
    from orchestrator.router import TRIGGER_ROUTES
    return {
        "registered": sorted(task_queue._agent_registry.keys()),
        "routes": TRIGGER_ROUTES,
    }


@app.post("/webhook", response_model=TaskResponse)
async def webhook(payload: WebhookPayload):
    """
    Receive an external event and route it to the appropriate agent(s).
    Returns task IDs for tracking.
    """
    agents = resolve_agents(payload.trigger_type)
    if not agents:
        raise HTTPException(
            status_code=400,
            detail=f"No agents registered for trigger_type={payload.trigger_type}",
        )

    task_ids = []
    for agent_name in agents:
        task = AgentTask(
            agent_name=agent_name,
            trigger_type=payload.trigger_type,
            payload={
                "source": payload.source,
                "metadata": payload.metadata,
            },
        )
        task_id = task_queue.enqueue(task)
        task_ids.append(task_id)

    logger.info(
        f"Webhook received: type={payload.trigger_type} "
        f"source={payload.source} → dispatched {len(agents)} agent(s)"
    )

    return TaskResponse(
        task_ids=task_ids,
        agents=agents,
        message=f"Dispatched {len(agents)} agent(s) for {payload.trigger_type}",
    )


@app.post("/trigger", response_model=TaskResponse)
async def manual_trigger(payload: ManualTriggerPayload):
    """
    Manually trigger a specific agent by name.
    Bypasses the routing table.
    """
    task = AgentTask(
        agent_name=payload.agent,
        trigger_type="manual",
        payload=payload.payload,
    )
    task_id = task_queue.enqueue(task)

    logger.info(f"Manual trigger: agent={payload.agent} → task_id={task_id}")

    return TaskResponse(
        task_ids=[task_id],
        agents=[payload.agent],
        message=f"Manually triggered {payload.agent}",
    )


@app.get("/task/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """Check the result of a previously enqueued task."""
    result = task_queue.get_result(task_id)
    return TaskStatusResponse(
        task_id=task_id,
        result=result,
        found=result is not None,
    )


# ---------------------------------------------------------------------------
# Metrics endpoints — SES measurement system
# ---------------------------------------------------------------------------

@app.get("/metrics")
async def metrics_summary():
    """
    SES measurement dashboard data. Returns aggregate metrics
    across all agent operations: token usage, costs, success rates,
    human review rates, correction counts.
    """
    from pipeline.metrics import MetricsCollector
    mc = MetricsCollector()
    return {
        "summary": mc.summary(),
        "per_agent": mc.per_agent_summary(),
        "per_prompt": mc.per_prompt_summary(),
        "token_timeseries": mc.token_usage_timeseries(),
    }


@app.get("/metrics/runs")
async def metrics_recent_runs(limit: int = 20):
    """Recent agent run activity feed."""
    from pipeline.metrics import MetricsCollector
    mc = MetricsCollector()
    return {"runs": mc.recent_runs(limit)}


@app.get("/metrics/prompts")
async def metrics_prompt_versions():
    """Prompt version history for regression tracking."""
    from pipeline.metrics import MetricsCollector
    mc = MetricsCollector()
    return {
        "versions": mc.prompt_version_history(),
        "usage": mc.per_prompt_summary(),
    }


@app.post("/metrics/correction")
async def record_correction(
    run_id: str,
    agent: str,
    correction_type: str,
    description: str = "",
):
    """Record a human correction to an agent output (for re-prompt rate tracking)."""
    from pipeline.metrics import MetricsCollector
    mc = MetricsCollector()
    mc.record_human_correction(run_id, agent, correction_type, description)
    return {"ok": True, "message": f"Correction recorded for {agent} run {run_id}"}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/dashboard")
async def dashboard():
    """Serve the SES metrics dashboard."""
    return FileResponse(DASHBOARD_DIR / "metrics.html")


@app.post("/ingest")
async def ingest_transcripts():
    """Run the batch VTT ingestion pipeline on all transcripts."""
    from pipeline.ingest import run as ingest_run
    result = ingest_run()
    return result


# ---------------------------------------------------------------------------
# Pipeline endpoints — the framework in action
# ---------------------------------------------------------------------------

@app.get("/pipelines")
async def list_pipelines():
    """List all defined pipelines and the full framework summary."""
    from pipeline.pipelines import get_framework_summary
    return get_framework_summary()


@app.post("/pipeline/{pipeline_name}")
async def run_pipeline(pipeline_name: str, payload: WebhookPayload):
    """
    Execute a named pipeline end-to-end.
    Each step's output feeds the next step's input.
    """
    from pipeline.pipelines import ALL_PIPELINES, PipelineExecutor
    from dataclasses import asdict

    pipe = ALL_PIPELINES.get(pipeline_name)
    if not pipe:
        raise HTTPException(
            status_code=404,
            detail=f"Pipeline '{pipeline_name}' not found. "
                   f"Available: {list(ALL_PIPELINES.keys())}",
        )

    executor = PipelineExecutor(_agent_instances)
    result = executor.execute(pipe, {
        "trigger_type": payload.trigger_type,
        "source": payload.source,
        "metadata": payload.metadata,
    })

    return {
        "pipeline_id": result.pipeline_id,
        "pipeline": result.pipeline_name,
        "practice_area": result.practice_area,
        "success": result.success,
        "steps": f"{result.completed_steps}/{result.total_steps} completed, "
                 f"{result.skipped_steps} skipped, {result.failed_steps} failed",
        "duration_ms": result.total_duration_ms,
        "llm_calls": result.total_llm_calls,
        "tokens": result.total_tokens,
        "artifacts": result.total_artifacts,
        "requires_human_review": result.requires_human_review,
        "step_details": [
            {
                "agent": sr.agent_name,
                "description": sr.description,
                "status": "SKIP" if sr.skipped else ("OK" if sr.success else "FAIL"),
                "duration_ms": sr.duration_ms,
                "outputs": sr.artifacts_produced,
                "human_review": sr.requires_human_review,
            }
            for sr in result.step_results
        ],
    }


# ---------------------------------------------------------------------------
# ETVX Process Model endpoints
# ---------------------------------------------------------------------------

@app.get("/etvx")
async def etvx_summary():
    """ETVX process model summary — meta-model compliance."""
    from pipeline.etvx import summary_stats, validate_coverage
    stats = summary_stats()
    coverage = validate_coverage(sorted(task_queue._agent_registry.keys()))
    return {"stats": stats, "coverage": coverage}


@app.get("/etvx/processes")
async def etvx_processes():
    """Full ETVX process definitions."""
    from pipeline.etvx import get_processes
    return {"processes": get_processes()}


@app.get("/etvx/markdown")
async def etvx_markdown():
    """Render ETVX manifest as presentation-ready markdown."""
    from pipeline.etvx import render_markdown
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(render_markdown(), media_type="text/markdown")


@app.get("/prompts")
async def prompt_registry():
    """Prompt registry — version-controlled prompt governance."""
    from pipeline.prompt_registry import PromptRegistry
    reg = PromptRegistry()
    return {
        "prompts": reg.get_all_prompts(),
        "stats": reg.stats(),
    }


@app.get("/conventions")
async def team_conventions():
    """Team conventions for systematic operation."""
    from pipeline.prompt_registry import PromptRegistry, seed_team_conventions
    seed_team_conventions()
    reg = PromptRegistry()
    rows = reg._db.execute(
        "SELECT convention, category, rationale, enforced_by FROM team_conventions ORDER BY category"
    ).fetchall()
    return {"conventions": [dict(r) for r in rows]}


@app.get("/risks")
async def risk_register():
    """Risk register — auto-populated from architecture, coach sessions, meetings."""
    from pipeline.risk_register import RiskRegister, seed_risk_register
    reg = seed_risk_register()
    return {"risks": reg.get_all(), "stats": reg.stats()}


@app.get("/wiki")
async def wiki_contents():
    """SharedMemory wiki — the project knowledge graph."""
    from pipeline.shared_memory import SharedMemory
    wiki = SharedMemory()
    stats = wiki.stats()
    contents = {}
    for ns in stats["namespaces"]:
        contents[ns] = wiki.list_namespace(ns)
    return {"stats": stats, "contents": contents}


@app.get("/events")
async def event_log():
    """Event bus — cross-pipeline communication log."""
    from pipeline.event_bus import EventBus
    bus = EventBus()
    return {
        "stats": bus.stats(),
        "subscriptions": bus.get_subscriptions(),
        "recent_events": bus.get_pending_events(limit=50),
    }


@app.get("/framework")
async def framework_overview():
    """
    The complete SES framework: pipelines, agents, connections, measurements.
    This is the 'one diagram' view for the presentation.
    """
    from pipeline.pipelines import get_framework_summary
    from pipeline.etvx import summary_stats, validate_coverage

    framework = get_framework_summary()
    etvx = summary_stats()
    coverage = validate_coverage(sorted(task_queue._agent_registry.keys()))

    return {
        "framework": framework,
        "etvx": etvx,
        "agent_coverage": coverage,
        "system": {
            "agents_registered": len(task_queue._agent_registry),
            "queue_running": task_queue.is_running,
        },
    }


# ---------------------------------------------------------------------------
# External Integration endpoints — GitHub + Jira live connections
# ---------------------------------------------------------------------------

@app.get("/github/status")
async def github_status():
    """Test GitHub connection and return repo info."""
    from mcp.github import GitHubMCP
    gh = GitHubMCP()
    if not gh.is_configured:
        return {"ok": False, "error": "GitHub not configured — check .env"}
    return gh.get_repo_info()


@app.get("/jira/status")
async def jira_status():
    """Test Jira connection and return board status."""
    from mcp.jira import JiraMCP
    jira = JiraMCP()
    if not jira.is_configured:
        return {"ok": False, "error": "Jira not configured — check .env (URL still has placeholder)"}
    return jira.get_board_status()


@app.post("/github/commit")
async def github_commit(file_path: str, content: str, message: str, branch: str = "main", agent: str = "system"):
    """Commit a file to GitHub via the Contents API."""
    from mcp.github import GitHubMCP
    gh = GitHubMCP()
    return gh.commit_file(file_path, content, message, branch, agent)


@app.post("/jira/create")
async def jira_create_issue(summary: str, description: str = "", issue_type: str = "Task", agent: str = "system"):
    """Create a Jira issue."""
    from mcp.jira import JiraMCP
    jira = JiraMCP()
    return jira.create_issue(summary, description, issue_type, agent_name=agent)


@app.get("/jira/issues")
async def jira_issues(jql: str | None = None):
    """Search Jira issues."""
    from mcp.jira import JiraMCP
    jira = JiraMCP()
    return jira.search_issues(jql)


@app.get("/traceability")
async def traceability_overview():
    """Unified traceability — every artifact and its chain."""
    from pipeline.traceability import TraceabilityStore
    from pipeline.seed_traceability import seed
    seed()
    store = TraceabilityStore()
    return {
        "coverage": store.get_coverage(),
        "concerns": store.get_by_type("concern"),
        "decisions": store.get_by_type("decision"),
        "architecture": store.get_by_type("architecture"),
        "risks": store.get_by_type("risk"),
        "commitments": store.get_by_type("commitment"),
    }


@app.get("/traceability/{artifact_id}")
async def trace_artifact(artifact_id: str, direction: str = "forward"):
    """Follow a single artifact's traceability chain."""
    from pipeline.traceability import TraceabilityStore
    store = TraceabilityStore()
    artifact = store.get_artifact(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_id}' not found")
    chain = store.get_chain(artifact_id, direction=direction)
    return {"artifact": artifact, "chain": chain, "chain_length": len(chain)}


@app.get("/traceability/gaps/concerns")
async def unaddressed_concerns():
    """Concerns with no action taken — traceability gaps."""
    from pipeline.traceability import TraceabilityStore
    store = TraceabilityStore()
    return {"unlinked_concerns": store.get_unlinked("concern")}


@app.get("/traceability/gaps/risks")
async def unmitigated_risks():
    """Risks without mitigation — traceability gaps."""
    from pipeline.traceability import TraceabilityStore
    store = TraceabilityStore()
    return {"unmitigated_risks": store.get_unlinked("risk")}


@app.get("/traceability/chains/{artifact_type}")
async def all_chains(artifact_type: str):
    """Get all forward chains for a given artifact type."""
    from pipeline.traceability import TraceabilityStore
    store = TraceabilityStore()
    return {"chains": store.get_all_chains_from_type(artifact_type)}


@app.get("/integrations")
async def integration_status():
    """Status of all external integrations."""
    from mcp.github import GitHubMCP
    from mcp.jira import JiraMCP
    gh = GitHubMCP()
    jira = JiraMCP()
    return {
        "github": {"configured": gh.is_configured, "repo": gh._repo},
        "jira": {"configured": jira.is_configured, "url": jira._url, "project": jira._project_key},
    }
