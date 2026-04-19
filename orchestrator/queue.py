"""
Shared task queue for sequential agent execution.

Agents run one at a time to prevent race conditions on shared state
(git commits, Jira updates, SQLite writes). The queue accepts AgentTask
items and processes them FIFO in a background thread.

Triggered by: orchestrator/main.py enqueuing tasks
Outputs: Agent results logged to pipeline/logs/agent_runs.jsonl
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger("orchestrator.queue")


@dataclass
class AgentTask:
    agent_name: str
    trigger_type: str
    payload: dict[str, Any]
    enqueued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    task_id: str = ""

    def __post_init__(self):
        if not self.task_id:
            ts = self.enqueued_at.strftime("%Y%m%d%H%M%S%f")
            self.task_id = f"{self.agent_name}-{ts}"


class TaskQueue:
    """
    Thread-safe FIFO queue that processes agent tasks sequentially.

    Agents are resolved via a registry (dict of name -> callable that
    accepts the payload and returns a result). The queue runs in a
    background daemon thread so the FastAPI event loop is never blocked.
    """

    def __init__(self):
        self._queue: queue.Queue[AgentTask] = queue.Queue()
        self._agent_registry: dict[str, Callable] = {}
        self._running = False
        self._worker: threading.Thread | None = None
        self._results: dict[str, Any] = {}
        self._lock = threading.Lock()

    def register_agent(self, name: str, handler: Callable) -> None:
        self._agent_registry[name] = handler

    def enqueue(self, task: AgentTask) -> str:
        self._queue.put(task)
        logger.info(f"Enqueued task {task.task_id} for agent={task.agent_name}")
        return task.task_id

    def get_result(self, task_id: str) -> Any | None:
        with self._lock:
            return self._results.get(task_id)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker = threading.Thread(target=self._process_loop, daemon=True)
        self._worker.start()
        logger.info("Task queue worker started")

    def stop(self) -> None:
        self._running = False
        if self._worker:
            self._worker.join(timeout=5)
        logger.info("Task queue worker stopped")

    def _process_loop(self) -> None:
        while self._running:
            try:
                task = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            logger.info(f"Processing task {task.task_id} (agent={task.agent_name})")

            handler = self._agent_registry.get(task.agent_name)
            if not handler:
                logger.error(f"No handler registered for agent={task.agent_name}")
                with self._lock:
                    self._results[task.task_id] = {
                        "success": False,
                        "error": f"Unknown agent: {task.agent_name}",
                    }
                continue

            try:
                result = handler(task)
                with self._lock:
                    self._results[task.task_id] = result
                logger.info(f"Task {task.task_id} completed")
            except Exception as exc:
                logger.exception(f"Task {task.task_id} failed: {exc}")
                with self._lock:
                    self._results[task.task_id] = {
                        "success": False,
                        "error": str(exc),
                    }

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    @property
    def is_running(self) -> bool:
        return self._running
