"""
Base Agent class for the eParts agentic system.

All domain agents inherit from BaseAgent. Provides:
- Abstract run() method that every agent implements
- call_claude() for all LLM calls via Anthropic SDK
- load_prompt() for loading versioned prompt templates from /prompts/
- Structured JSON logging for every agent invocation
- Retry with exponential backoff on rate limits

Triggered by: N/A (base class)
Outputs: N/A (base class)
"""

from __future__ import annotations

import json
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from string import Template
from typing import Any

import anthropic
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = PROJECT_ROOT / "prompts"
LOG_DIR = PROJECT_ROOT / "pipeline" / "logs"
LOG_FILE = LOG_DIR / "agent_runs.jsonl"


class AgentSettings(BaseSettings):
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-5-20250514"
    model_config = {"env_file": ".env", "extra": "ignore"}


# ---------------------------------------------------------------------------
# Data schemas
# ---------------------------------------------------------------------------

@dataclass
class AgentTrigger:
    trigger_type: str  # transcript | jira_webhook | slack | pr | cron | manual | poc_result
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AgentOutput:
    output_type: str  # file_committed | ticket_created | message_sent | pr_opened | page_published
    description: str
    reference: str = ""  # URL, file path, ticket key, etc.


@dataclass
class AgentResult:
    agent: str
    success: bool
    outputs: list[AgentOutput] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    requires_human_review: bool = False
    review_items: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Structured logger
# ---------------------------------------------------------------------------

class StructuredLogger:
    """JSON-structured logger that writes to both stderr and the JSONL audit file."""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self._logger = logging.getLogger(f"agent.{agent_name}")
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter("%(asctime)s [%(name)s] %(levelname)s %(message)s")
            )
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.INFO)

    def _write_jsonl(self, record: dict[str, Any]) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def log_run(
        self,
        trigger: AgentTrigger,
        result: AgentResult,
        duration_ms: int,
        llm_calls: int = 0,
        total_tokens: int = 0,
    ) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": self.agent_name,
            "trigger_type": trigger.trigger_type,
            "trigger_source": trigger.source,
            "success": result.success,
            "duration_ms": duration_ms,
            "llm_calls": llm_calls,
            "total_tokens": total_tokens,
            "outputs": [asdict(o) for o in result.outputs],
            "errors": result.errors,
            "requires_human_review": result.requires_human_review,
        }
        self._write_jsonl(record)
        level = logging.INFO if result.success else logging.ERROR
        self._logger.log(level, json.dumps(record, default=str))

    def info(self, msg: str, **kwargs: Any) -> None:
        self._logger.info(msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._logger.warning(msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._logger.error(msg, **kwargs)


# ---------------------------------------------------------------------------
# Base Agent
# ---------------------------------------------------------------------------

class BaseAgent(ABC):
    """
    Abstract base class for all eParts agentic system agents.

    Subclasses must implement `run(trigger) -> AgentResult`.
    All LLM calls go through `call_claude()`. All prompts are loaded from
    /prompts/ via `load_prompt()`. Every invocation is logged to the JSONL
    audit trail.
    """

    MAX_RETRIES = 3
    INITIAL_BACKOFF_S = 1.0

    def __init__(self, name: str, mcp_clients: dict[str, Any] | None = None):
        self.name = name
        self.mcp = mcp_clients or {}
        self.logger = StructuredLogger(agent_name=name)
        self._settings = AgentSettings()
        self._client = anthropic.Anthropic(api_key=self._settings.anthropic_api_key)
        self._run_llm_calls = 0
        self._run_total_tokens = 0

    # ------ abstract interface ------

    @abstractmethod
    def run(self, trigger: AgentTrigger) -> AgentResult:
        """Execute the agent's task. Every agent implements this."""
        ...

    # ------ LLM helpers ------

    def call_claude(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str:
        """
        Call the Anthropic API. If `prompt` matches a filename in /prompts/,
        loads the file contents instead.

        Retries up to MAX_RETRIES times with exponential backoff on rate-limit
        or transient server errors.
        """
        if PROMPTS_DIR.joinpath(prompt).exists():
            prompt = self.load_prompt(prompt)

        model = model or self._settings.claude_model
        messages = [{"role": "user", "content": prompt}]

        system_param = [{"type": "text", "text": system}] if system else anthropic.NOT_GIVEN

        backoff = self.INITIAL_BACKOFF_S
        last_error: Exception | None = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            t0 = time.perf_counter()
            try:
                response = self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_param,
                    messages=messages,
                )
                elapsed_ms = int((time.perf_counter() - t0) * 1000)

                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                self._run_llm_calls += 1
                self._run_total_tokens += input_tokens + output_tokens

                self.logger.info(
                    f"LLM call completed: model={model} "
                    f"input_tokens={input_tokens} output_tokens={output_tokens} "
                    f"latency_ms={elapsed_ms} attempt={attempt}"
                )

                return response.content[0].text

            except anthropic.RateLimitError as exc:
                last_error = exc
                self.logger.warning(
                    f"Rate limited (attempt {attempt}/{self.MAX_RETRIES}), "
                    f"backing off {backoff:.1f}s"
                )
                time.sleep(backoff)
                backoff *= 2

            except anthropic.APIStatusError as exc:
                if exc.status_code >= 500:
                    last_error = exc
                    self.logger.warning(
                        f"Server error {exc.status_code} (attempt {attempt}/{self.MAX_RETRIES}), "
                        f"backing off {backoff:.1f}s"
                    )
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    raise

        raise RuntimeError(
            f"call_claude failed after {self.MAX_RETRIES} retries: {last_error}"
        ) from last_error

    def load_prompt(self, filename: str, **kwargs: Any) -> str:
        """
        Load a prompt template from /prompts/{filename} and substitute
        template variables using Python's string.Template ($var syntax).
        """
        path = PROMPTS_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {path}")

        template_str = path.read_text(encoding="utf-8")
        if kwargs:
            return Template(template_str).safe_substitute(**kwargs)
        return template_str

    # ------ execution wrapper ------

    def execute(self, trigger: AgentTrigger) -> AgentResult:
        """
        Wraps run() with timing, token tracking, and structured logging.
        Call this instead of run() directly.
        """
        self._run_llm_calls = 0
        self._run_total_tokens = 0
        t0 = time.perf_counter()

        try:
            result = self.run(trigger)
        except Exception as exc:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            result = AgentResult(
                agent=self.name,
                success=False,
                errors=[f"{type(exc).__name__}: {exc}"],
            )
            self.logger.log_run(
                trigger, result, duration_ms,
                llm_calls=self._run_llm_calls,
                total_tokens=self._run_total_tokens,
            )
            return result

        duration_ms = int((time.perf_counter() - t0) * 1000)
        self.logger.log_run(
            trigger, result, duration_ms,
            llm_calls=self._run_llm_calls,
            total_tokens=self._run_total_tokens,
        )
        return result
