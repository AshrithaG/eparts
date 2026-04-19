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
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from orchestrator.queue import AgentTask, TaskQueue
from orchestrator.router import resolve_agents

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("orchestrator")

task_queue = TaskQueue()


# ---------------------------------------------------------------------------
# Lifespan — start/stop the task queue worker
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    task_queue.start()
    logger.info("Orchestrator started")
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
