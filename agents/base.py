"""
Base Agent class for the eParts agentic system.

All domain agents inherit from BaseAgent. Provides:
- Abstract run() method that every agent implements
- call_llm() / call_claude() for LLM calls (supports Anthropic Claude + Google Gemini)
- load_prompt() for loading versioned prompt templates from /prompts/
- Structured JSON logging for every agent invocation
- Retry with exponential backoff on rate limits

LLM Provider selection (auto-detected from .env):
  GEMINI_API_KEY  → Google Gemini (gemini-2.0-flash)
  ANTHROPIC_API_KEY → Anthropic Claude (claude-sonnet)
  Both set → uses LLM_PROVIDER env var to pick, defaults to gemini
  Neither → offline mode (agents use keyword/regex fallbacks)

Triggered by: N/A (base class)
Outputs: N/A (base class)
"""

from __future__ import annotations

import json
import time
import logging
import uuid
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
    gemini_api_key: str = ""
    llm_provider: str = ""  # "gemini", "anthropic", or "" (auto-detect)
    claude_model: str = "claude-sonnet-4-5-20250514"
    gemini_model: str = "gemini-2.5-flash"
    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def active_provider(self) -> str:
        """Which LLM provider to use. Auto-detects from available keys."""
        if self.llm_provider:
            return self.llm_provider.lower()
        if self.gemini_api_key:
            return "gemini"
        if self.anthropic_api_key:
            return "anthropic"
        return "none"

    @property
    def has_llm(self) -> bool:
        return self.active_provider != "none"


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
    # Pipeline data: structured output for downstream agents to consume
    data: dict[str, Any] = field(default_factory=dict)


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
    audit trail. Every call is metered into the metrics DB for the SES
    measurement system (tokens, latency, cost, prompt version).
    """

    MAX_RETRIES = 3
    INITIAL_BACKOFF_S = 1.0

    def __init__(self, name: str, mcp_clients: dict[str, Any] | None = None):
        self.name = name
        self.mcp = mcp_clients or {}
        self.logger = StructuredLogger(agent_name=name)
        self._settings = AgentSettings()

        # LLM client setup — supports Anthropic Claude and Google Gemini
        self._llm_provider = self._settings.active_provider
        self._anthropic_client = None
        self._gemini_model = None

        if self._llm_provider == "anthropic":
            self._anthropic_client = anthropic.Anthropic(
                api_key=self._settings.anthropic_api_key
            )
        elif self._llm_provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=self._settings.gemini_api_key)
            self._gemini_model = genai.GenerativeModel(self._settings.gemini_model)

        self._run_llm_calls = 0
        self._run_total_tokens = 0
        self._run_input_tokens = 0
        self._run_output_tokens = 0
        self._run_cost_usd = 0.0
        self._run_id = ""

        # Lazy-loaded shared infrastructure
        self._metrics = None
        self._wiki = None
        self._event_bus = None

    def _get_metrics(self):
        if self._metrics is None:
            from pipeline.metrics import MetricsCollector
            self._metrics = MetricsCollector()
        return self._metrics

    @property
    def wiki(self):
        """Shared Memory — the project wiki all agents read/write."""
        if self._wiki is None:
            from pipeline.shared_memory import SharedMemory
            self._wiki = SharedMemory()
        return self._wiki

    @property
    def events(self):
        """Event Bus — publish events to trigger cross-pipeline actions."""
        if self._event_bus is None:
            from pipeline.event_bus import EventBus
            self._event_bus = EventBus()
        return self._event_bus

    def emit(self, event_type: str, data: dict[str, Any] | None = None, pipeline: str = "") -> None:
        """Convenience: publish an event from this agent."""
        from pipeline.event_bus import Event
        self.events.publish(Event(
            event_type=event_type,
            source_agent=self.name,
            source_pipeline=pipeline,
            data=data or {},
        ))

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
        Call the active LLM provider (Gemini or Anthropic).

        Auto-resolves prompt files from /prompts/ directory.
        Retries with exponential backoff on transient errors.
        All calls are metered into the metrics DB.

        Despite the name 'call_claude', this routes to whichever
        provider is configured via .env (GEMINI_API_KEY or ANTHROPIC_API_KEY).
        """
        prompt_file = "inline"
        if len(prompt) < 256 and "\n" not in prompt:
            try:
                if PROMPTS_DIR.joinpath(prompt).exists():
                    prompt_file = prompt
                    prompt = self.load_prompt(prompt)
            except (OSError, ValueError):
                pass

        if self._llm_provider == "gemini":
            return self._call_gemini(prompt, system=system, prompt_file=prompt_file,
                                     max_tokens=max_tokens, temperature=temperature)
        elif self._llm_provider == "anthropic":
            return self._call_anthropic(prompt, system=system, model=model,
                                        prompt_file=prompt_file, max_tokens=max_tokens,
                                        temperature=temperature)
        else:
            raise RuntimeError(
                "No LLM provider configured. Set GEMINI_API_KEY or ANTHROPIC_API_KEY in .env"
            )

    def _call_gemini(
        self, prompt: str, *, system: str | None = None,
        prompt_file: str = "inline", max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str:
        """Call Google Gemini API."""
        model_name = self._settings.gemini_model
        full_prompt = f"{system}\n\n{prompt}" if system else prompt

        backoff = self.INITIAL_BACKOFF_S
        last_error: Exception | None = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            t0 = time.perf_counter()
            try:
                response = self._gemini_model.generate_content(
                    full_prompt,
                    generation_config={
                        "max_output_tokens": max_tokens,
                        "temperature": temperature,
                    },
                )
                elapsed_ms = int((time.perf_counter() - t0) * 1000)

                text = response.text
                input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0
                self._run_llm_calls += 1
                self._run_total_tokens += input_tokens + output_tokens
                self._run_input_tokens += input_tokens
                self._run_output_tokens += output_tokens

                try:
                    from pipeline.metrics import LLMCallMetric
                    call_metric = LLMCallMetric(
                        agent=self.name,
                        run_id=self._run_id,
                        model=model_name,
                        prompt_file=prompt_file,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        latency_ms=elapsed_ms,
                        temperature=temperature,
                        attempt=attempt,
                    )
                    self._run_cost_usd += call_metric.estimated_cost_usd
                    self._get_metrics().record_llm_call(call_metric)
                    if prompt_file != "inline":
                        self._get_metrics().track_prompt_version(prompt_file, prompt)
                except Exception:
                    pass

                self.logger.info(
                    f"LLM call completed: provider=gemini model={model_name} "
                    f"prompt={prompt_file} "
                    f"input_tokens={input_tokens} output_tokens={output_tokens} "
                    f"latency_ms={elapsed_ms} attempt={attempt}"
                )
                return text

            except Exception as exc:
                last_error = exc
                self.logger.warning(
                    f"Gemini error (attempt {attempt}/{self.MAX_RETRIES}): {exc}, "
                    f"backing off {backoff:.1f}s"
                )
                time.sleep(backoff)
                backoff *= 2

        raise RuntimeError(
            f"call_gemini failed after {self.MAX_RETRIES} retries: {last_error}"
        ) from last_error

    def _call_anthropic(
        self, prompt: str, *, system: str | None = None,
        model: str | None = None, prompt_file: str = "inline",
        max_tokens: int = 4096, temperature: float = 0.0,
    ) -> str:
        """Call Anthropic Claude API."""
        model = model or self._settings.claude_model
        messages = [{"role": "user", "content": prompt}]
        system_param = [{"type": "text", "text": system}] if system else anthropic.NOT_GIVEN

        backoff = self.INITIAL_BACKOFF_S
        last_error: Exception | None = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            t0 = time.perf_counter()
            try:
                response = self._anthropic_client.messages.create(
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
                self._run_input_tokens += input_tokens
                self._run_output_tokens += output_tokens

                try:
                    from pipeline.metrics import LLMCallMetric
                    call_metric = LLMCallMetric(
                        agent=self.name,
                        run_id=self._run_id,
                        model=model,
                        prompt_file=prompt_file,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        latency_ms=elapsed_ms,
                        temperature=temperature,
                        attempt=attempt,
                    )
                    self._run_cost_usd += call_metric.estimated_cost_usd
                    self._get_metrics().record_llm_call(call_metric)
                    if prompt_file != "inline":
                        self._get_metrics().track_prompt_version(prompt_file, prompt)
                except Exception:
                    pass

                self.logger.info(
                    f"LLM call completed: provider=anthropic model={model} "
                    f"prompt={prompt_file} "
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
            f"call_anthropic failed after {self.MAX_RETRIES} retries: {last_error}"
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
        Wraps run() with timing, token tracking, structured logging, and
        metrics collection. Call this instead of run() directly.
        """
        self._run_id = f"{self.name}-{uuid.uuid4().hex[:12]}"
        self._run_llm_calls = 0
        self._run_total_tokens = 0
        self._run_input_tokens = 0
        self._run_output_tokens = 0
        self._run_cost_usd = 0.0
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
            self._record_run_metrics(trigger, result, duration_ms)
            self.logger.log_run(
                trigger, result, duration_ms,
                llm_calls=self._run_llm_calls,
                total_tokens=self._run_total_tokens,
            )
            return result

        duration_ms = int((time.perf_counter() - t0) * 1000)
        self._record_run_metrics(trigger, result, duration_ms)
        self.logger.log_run(
            trigger, result, duration_ms,
            llm_calls=self._run_llm_calls,
            total_tokens=self._run_total_tokens,
        )
        return result

    def _record_run_metrics(
        self, trigger: AgentTrigger, result: AgentResult, duration_ms: int
    ) -> None:
        try:
            from pipeline.metrics import AgentRunMetric
            self._get_metrics().record_agent_run(AgentRunMetric(
                run_id=self._run_id,
                agent=self.name,
                trigger_type=trigger.trigger_type,
                trigger_source=trigger.source,
                success=result.success,
                duration_ms=duration_ms,
                llm_calls=self._run_llm_calls,
                total_input_tokens=self._run_input_tokens,
                total_output_tokens=self._run_output_tokens,
                estimated_cost_usd=self._run_cost_usd,
                outputs_count=len(result.outputs),
                requires_human_review=result.requires_human_review,
                errors=result.errors,
            ))
        except Exception:
            pass  # metrics should never break agent execution
