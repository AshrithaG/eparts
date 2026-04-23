"""
Pipeline Executor — the connective tissue of the SES framework.

A Pipeline is an ordered chain of agents where each step's output feeds
the next step's input. This is what makes the system a *framework* rather
than a bag of scripts.

Key concepts:
  - PipelineStep: one agent invocation with input/output mapping
  - PipelineContext: accumulated state flowing through the chain
  - PipelineResult: end-to-end outcome with per-step metrics
  - Pipeline: named, ordered sequence of steps with practice area metadata

The pipeline executor:
  1. Initializes a context from the trigger payload
  2. Runs each step in order, passing accumulated context
  3. Each step's outputs are merged back into the context
  4. Steps can be conditional (skip if required context key is empty)
  5. Records per-step AND end-to-end metrics

This directly implements the meta-model requirement:
  "For at least one Practice Area, there should be an end-to-end
   connection between the Activities in that area."
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.base import AgentTrigger, AgentResult, AgentOutput

logger = logging.getLogger("pipeline.executor")

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class PipelineStep:
    """One step in a pipeline chain."""
    agent_name: str
    description: str
    input_keys: list[str] = field(default_factory=list)   # context keys this step reads
    output_key: str = ""                                    # context key this step writes to
    required: bool = True                                   # fail pipeline if this step fails
    skip_if_empty: str = ""                                 # skip if this context key is empty/missing
    etvx_id: str = ""                                       # link to ETVX process definition


@dataclass
class PipelineContext:
    """Accumulated state flowing through the pipeline."""
    pipeline_id: str
    pipeline_name: str
    trigger_type: str
    source: str
    data: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, str]] = field(default_factory=list)
    step_results: list[dict[str, Any]] = field(default_factory=list)
    started_at: str = ""
    current_step: int = 0

    def __post_init__(self):
        if not self.started_at:
            self.started_at = datetime.now(timezone.utc).isoformat()

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def add_artifact(self, artifact_type: str, description: str, reference: str = "") -> None:
        self.artifacts.append({
            "type": artifact_type,
            "description": description,
            "reference": reference,
            "step": self.current_step,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


@dataclass
class StepResult:
    step_index: int
    agent_name: str
    description: str
    success: bool
    skipped: bool
    duration_ms: int
    outputs: list[dict]
    errors: list[str]
    llm_calls: int
    tokens_used: int
    artifacts_produced: int
    requires_human_review: bool


@dataclass
class PipelineResult:
    pipeline_id: str
    pipeline_name: str
    practice_area: str
    trigger_source: str
    success: bool
    total_steps: int
    completed_steps: int
    skipped_steps: int
    failed_steps: int
    total_duration_ms: int
    total_llm_calls: int
    total_tokens: int
    total_artifacts: int
    requires_human_review: bool
    step_results: list[StepResult]
    artifacts: list[dict]
    context_snapshot: dict[str, Any]
    started_at: str
    completed_at: str


@dataclass
class Pipeline:
    """A named, ordered chain of agent steps for a practice area."""
    name: str
    practice_area: str
    description: str
    trigger_types: list[str]
    steps: list[PipelineStep]
    metadata: dict[str, Any] = field(default_factory=dict)


class PipelineExecutor:
    """
    Executes pipelines by running agent steps in sequence,
    threading context from one step to the next.
    """

    def __init__(self, agent_registry: dict[str, Any]):
        self._agents = agent_registry

    def execute(self, pipeline: Pipeline, trigger_payload: dict[str, Any]) -> PipelineResult:
        pipeline_id = f"pipe-{pipeline.name}-{uuid.uuid4().hex[:8]}"
        ctx = PipelineContext(
            pipeline_id=pipeline_id,
            pipeline_name=pipeline.name,
            trigger_type=trigger_payload.get("trigger_type", "manual"),
            source=trigger_payload.get("source", "unknown"),
            data=dict(trigger_payload),
        )

        logger.info(
            f"Pipeline '{pipeline.name}' started: id={pipeline_id} "
            f"steps={len(pipeline.steps)} source={ctx.source}"
        )

        step_results: list[StepResult] = []
        pipeline_success = True
        pipeline_t0 = time.perf_counter()
        total_llm = 0
        total_tokens = 0
        human_review_needed = False

        for i, step in enumerate(pipeline.steps):
            ctx.current_step = i

            # Check skip condition
            if step.skip_if_empty:
                val = ctx.get(step.skip_if_empty)
                if not val:
                    logger.info(
                        f"  Step {i}/{len(pipeline.steps)} [{step.agent_name}] "
                        f"SKIPPED ('{step.skip_if_empty}' is empty)"
                    )
                    step_results.append(StepResult(
                        step_index=i, agent_name=step.agent_name,
                        description=step.description, success=True, skipped=True,
                        duration_ms=0, outputs=[], errors=[], llm_calls=0,
                        tokens_used=0, artifacts_produced=0, requires_human_review=False,
                    ))
                    continue

            # Resolve agent
            agent = self._agents.get(step.agent_name)
            if not agent:
                logger.error(f"  Step {i} [{step.agent_name}] — agent not found")
                sr = StepResult(
                    step_index=i, agent_name=step.agent_name,
                    description=step.description, success=False, skipped=False,
                    duration_ms=0, outputs=[], errors=[f"Agent '{step.agent_name}' not registered"],
                    llm_calls=0, tokens_used=0, artifacts_produced=0, requires_human_review=False,
                )
                step_results.append(sr)
                if step.required:
                    pipeline_success = False
                    break
                continue

            # Build trigger with accumulated context
            trigger = AgentTrigger(
                trigger_type=ctx.trigger_type,
                source=ctx.source,
                metadata={
                    "pipeline_id": pipeline_id,
                    "pipeline_step": i,
                    "pipeline_context": ctx.data,
                },
            )

            logger.info(
                f"  Step {i}/{len(pipeline.steps)} [{step.agent_name}] "
                f"{step.description}..."
            )

            step_t0 = time.perf_counter()
            try:
                result: AgentResult = agent.execute(trigger)
                step_ms = int((time.perf_counter() - step_t0) * 1000)

                # Extract metrics from the agent
                step_llm = getattr(agent, '_run_llm_calls', 0)
                step_tokens = getattr(agent, '_run_total_tokens', 0)
                total_llm += step_llm
                total_tokens += step_tokens

                # Merge structured data into context (pipeline data bridge)
                if step.output_key:
                    if result.data:
                        ctx.set(step.output_key, result.data)
                    elif result.outputs:
                        ctx.set(step.output_key, [asdict(o) for o in result.outputs])

                # Also merge all result.data keys directly into context
                for key, val in result.data.items():
                    ctx.set(key, val)

                # Deposit structured data into shared memory (the wiki)
                self._deposit_to_wiki(pipeline, step, result)

                # Track artifacts
                for o in result.outputs:
                    ctx.add_artifact(o.output_type, o.description, o.reference)

                if result.requires_human_review:
                    human_review_needed = True

                sr = StepResult(
                    step_index=i, agent_name=step.agent_name,
                    description=step.description,
                    success=result.success, skipped=False,
                    duration_ms=step_ms,
                    outputs=[asdict(o) for o in result.outputs],
                    errors=result.errors,
                    llm_calls=step_llm, tokens_used=step_tokens,
                    artifacts_produced=len(result.outputs),
                    requires_human_review=result.requires_human_review,
                )
                step_results.append(sr)

                status = "OK" if result.success else "FAIL"
                logger.info(
                    f"  Step {i} [{step.agent_name}] → {status} "
                    f"({step_ms}ms, {step_llm} LLM calls, "
                    f"{len(result.outputs)} outputs)"
                )

                if not result.success and step.required:
                    pipeline_success = False
                    logger.error(
                        f"  Pipeline STOPPED: required step {step.agent_name} failed"
                    )
                    break

            except Exception as exc:
                step_ms = int((time.perf_counter() - step_t0) * 1000)
                logger.exception(f"  Step {i} [{step.agent_name}] EXCEPTION: {exc}")
                sr = StepResult(
                    step_index=i, agent_name=step.agent_name,
                    description=step.description,
                    success=False, skipped=False,
                    duration_ms=step_ms, outputs=[],
                    errors=[f"{type(exc).__name__}: {exc}"],
                    llm_calls=0, tokens_used=0, artifacts_produced=0,
                    requires_human_review=False,
                )
                step_results.append(sr)
                if step.required:
                    pipeline_success = False
                    break

        total_ms = int((time.perf_counter() - pipeline_t0) * 1000)
        completed = sum(1 for sr in step_results if not sr.skipped and sr.success)
        skipped = sum(1 for sr in step_results if sr.skipped)
        failed = sum(1 for sr in step_results if not sr.skipped and not sr.success)

        pipe_result = PipelineResult(
            pipeline_id=pipeline_id,
            pipeline_name=pipeline.name,
            practice_area=pipeline.practice_area,
            trigger_source=ctx.source,
            success=pipeline_success,
            total_steps=len(pipeline.steps),
            completed_steps=completed,
            skipped_steps=skipped,
            failed_steps=failed,
            total_duration_ms=total_ms,
            total_llm_calls=total_llm,
            total_tokens=total_tokens,
            total_artifacts=len(ctx.artifacts),
            requires_human_review=human_review_needed,
            step_results=step_results,
            artifacts=ctx.artifacts,
            context_snapshot={k: type(v).__name__ for k, v in ctx.data.items()},
            started_at=ctx.started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

        # Record pipeline-level metrics
        self._record_pipeline_metrics(pipe_result)

        status = "COMPLETED" if pipeline_success else "FAILED"
        logger.info(
            f"Pipeline '{pipeline.name}' {status}: "
            f"{completed}/{len(pipeline.steps)} steps, "
            f"{total_ms}ms, {total_llm} LLM calls, "
            f"{len(ctx.artifacts)} artifacts"
        )

        return pipe_result

    def _deposit_to_wiki(self, pipeline: Pipeline, step: PipelineStep, result: AgentResult) -> None:
        """Deposit agent results into the shared wiki so other pipelines can access them."""
        try:
            from pipeline.shared_memory import SharedMemory
            wiki = SharedMemory()

            if not result.data and not result.outputs:
                return

            # Namespace is the practice area, key is agent:timestamp
            ns = pipeline.practice_area.lower().replace(" ", "_")
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            key = f"{step.agent_name}:{ts}"

            entry = {
                "agent": step.agent_name,
                "pipeline": pipeline.name,
                "step_description": step.description,
                "etvx_id": step.etvx_id,
                "outputs": [asdict(o) for o in result.outputs] if result.outputs else [],
                "data_keys": list(result.data.keys()) if result.data else [],
                "success": result.success,
                "requires_human_review": result.requires_human_review,
            }

            # Store significant data fields directly for cross-pipeline access
            if result.data:
                for data_key, data_val in result.data.items():
                    if isinstance(data_val, (str, int, float, bool, list)):
                        entry[data_key] = data_val
                    elif isinstance(data_val, dict) and len(str(data_val)) < 5000:
                        entry[data_key] = data_val

            tags = [pipeline.name, step.agent_name]
            if step.etvx_id:
                tags.append(step.etvx_id)
            if result.requires_human_review:
                tags.append("human_review")

            wiki.put(ns, key, entry, agent=step.agent_name, pipeline=pipeline.name, tags=tags)

            # Also store latest run per agent for quick lookup
            wiki.put(
                "latest_runs", step.agent_name, entry,
                agent=step.agent_name, pipeline=pipeline.name,
            )

        except Exception as exc:
            logger.debug(f"Wiki deposit failed (non-critical): {exc}")

    def _record_pipeline_metrics(self, result: PipelineResult) -> None:
        try:
            from pipeline.metrics import MetricsCollector, AgentRunMetric
            mc = MetricsCollector()
            mc.record_agent_run(AgentRunMetric(
                run_id=result.pipeline_id,
                agent=f"pipeline:{result.pipeline_name}",
                trigger_type="pipeline",
                trigger_source=result.trigger_source,
                success=result.success,
                duration_ms=result.total_duration_ms,
                llm_calls=result.total_llm_calls,
                total_input_tokens=0,
                total_output_tokens=result.total_tokens,
                estimated_cost_usd=0,
                outputs_count=result.total_artifacts,
                requires_human_review=result.requires_human_review,
                errors=[],
            ))
        except Exception:
            pass


# ============================================================================
# PIPELINE DEFINITIONS — The Framework
# ============================================================================

REQUIREMENTS_PIPELINE = Pipeline(
    name="requirements",
    practice_area="Requirements Engineering",
    description=(
        "End-to-end requirements flow: VTT transcript → structured minutes → "
        "priority classification → REQ documents → Jira tickets → "
        "Confluence publication → decision log → architecture drift check"
    ),
    trigger_types=["transcript"],
    steps=[
        PipelineStep(
            agent_name="transcript_parser",
            description="Parse raw transcript into structured minutes",
            input_keys=["source"],
            output_key="parsed_minutes",
            etvx_id="REQ-PARSE",
        ),
        PipelineStep(
            agent_name="priority_classifier",
            description="Classify extracted items as P0/P1/P2",
            input_keys=["parsed_minutes"],
            output_key="classified_items",
            skip_if_empty="parsed_minutes",
            etvx_id="REQ-CLASSIFY",
        ),
        PipelineStep(
            agent_name="req_extractor",
            description="Generate REQ-XXX.md files from classified items",
            input_keys=["classified_items"],
            output_key="requirements",
            skip_if_empty="classified_items",
            etvx_id="REQ-EXTRACT",
        ),
        PipelineStep(
            agent_name="ticket_creator",
            description="Create Jira tickets (P0 → human review queue)",
            input_keys=["classified_items"],
            output_key="jira_tickets",
            skip_if_empty="classified_items",
            required=False,
            etvx_id="PM-TICKET",
        ),
        PipelineStep(
            agent_name="minutes_publisher",
            description="Publish minutes to Confluence",
            input_keys=["parsed_minutes"],
            output_key="confluence_page",
            skip_if_empty="parsed_minutes",
            required=False,
            etvx_id="KN-PUBLISH",
        ),
        PipelineStep(
            agent_name="decision_logger",
            description="Extract and log decisions",
            input_keys=["parsed_minutes"],
            output_key="decisions",
            skip_if_empty="parsed_minutes",
            required=False,
            etvx_id="KN-DECISION",
        ),
        PipelineStep(
            agent_name="drift_detector",
            description="Check for architectural drift",
            input_keys=["parsed_minutes", "decisions"],
            output_key="drift_report",
            skip_if_empty="parsed_minutes",
            required=False,
            etvx_id="ARCH-DRIFT",
        ),
    ],
)

COACH_SESSION_PIPELINE = Pipeline(
    name="coach_session",
    practice_area="Coach Session Memory",
    description=(
        "Coach/mentor transcript → session embedding → commitment extraction → "
        "concern detection → ML decision linking → pre-meeting briefing"
    ),
    trigger_types=["coach_transcript"],
    steps=[
        PipelineStep(
            agent_name="transcript_parser",
            description="Parse coach session transcript",
            input_keys=["source"],
            output_key="parsed_session",
            etvx_id="REQ-PARSE",
        ),
        PipelineStep(
            agent_name="session_memory",
            description="Chunk and embed into ChromaDB for RAG",
            input_keys=["source"],
            output_key="session_embedded",
            etvx_id="COACH-INGEST",
        ),
        PipelineStep(
            agent_name="commitment_tracker",
            description="Extract commitments with owners and deadlines",
            input_keys=["parsed_session"],
            output_key="commitments",
            skip_if_empty="parsed_session",
            etvx_id="COACH-COMMIT",
        ),
        PipelineStep(
            agent_name="concern_tracker",
            description="Detect recurring themes and concerns",
            input_keys=["parsed_session"],
            output_key="concerns",
            etvx_id="COACH-CONCERN",
        ),
        PipelineStep(
            agent_name="coach_linker",
            description="Link session content to open ML decisions",
            input_keys=["session_embedded"],
            output_key="ml_links",
            required=False,
            etvx_id="ML-LINK",
        ),
        PipelineStep(
            agent_name="decision_logger",
            description="Log any decisions from the session",
            input_keys=["parsed_session"],
            output_key="decisions",
            skip_if_empty="parsed_session",
            required=False,
            etvx_id="KN-DECISION",
        ),
    ],
)

ARCHITECTURE_PIPELINE = Pipeline(
    name="architecture",
    practice_area="Architecture",
    description=(
        "Architecture practice: drift detection → ADR generation → "
        "diagram update → traceability matrix"
    ),
    trigger_types=["transcript", "pr_event"],
    steps=[
        PipelineStep(
            agent_name="drift_detector",
            description="Compare discussion against canonical architecture",
            input_keys=["source"],
            output_key="drift_report",
            etvx_id="ARCH-DRIFT",
        ),
        PipelineStep(
            agent_name="adr_generator",
            description="Draft ADR if significant decision detected",
            input_keys=["drift_report"],
            output_key="adr_draft",
            skip_if_empty="drift_report",
            required=False,
            etvx_id="ARCH-ADR",
        ),
        PipelineStep(
            agent_name="diagram_updater",
            description="Propose diagram updates via PR",
            input_keys=["drift_report"],
            output_key="diagram_pr",
            skip_if_empty="drift_report",
            required=False,
            etvx_id="ARCH-DIAGRAM",
        ),
        PipelineStep(
            agent_name="traceability_builder",
            description="Update traceability matrix",
            input_keys=["adr_draft"],
            output_key="traceability",
            required=False,
            etvx_id="ARCH-TRACE",
        ),
    ],
)

CODING_PIPELINE = Pipeline(
    name="coding",
    practice_area="Coding",
    description=(
        "Code practice: PR review → test generation → "
        "doc update → boilerplate scaffolding"
    ),
    trigger_types=["pr_event"],
    steps=[
        PipelineStep(
            agent_name="pr_reviewer",
            description="Automated PR review (style, tests, traceability)",
            input_keys=["source"],
            output_key="review_comments",
            etvx_id="CODE-REVIEW",
        ),
        PipelineStep(
            agent_name="test_generator",
            description="Generate test stubs for new functions",
            input_keys=["source"],
            output_key="test_stubs",
            required=False,
            etvx_id="CODE-TEST",
        ),
        PipelineStep(
            agent_name="doc_generator",
            description="Update API documentation",
            input_keys=["source"],
            output_key="doc_updates",
            required=False,
            etvx_id="CODE-DOC",
        ),
        PipelineStep(
            agent_name="prompt_regression",
            description="Test prompt changes against golden dataset",
            input_keys=["source"],
            output_key="regression_results",
            required=False,
            etvx_id="KN-PROMPT-REG",
        ),
    ],
)

ML_DECISION_PIPELINE = Pipeline(
    name="ml_decision",
    practice_area="ML Decision Memory",
    description=(
        "ML decision flow: evidence accumulation → readiness detection → "
        "coach linking → briefing generation"
    ),
    trigger_types=["poc_result"],
    steps=[
        PipelineStep(
            agent_name="evidence_accumulator",
            description="Parse POC results and log evidence",
            input_keys=["source"],
            output_key="evidence",
            etvx_id="ML-EVIDENCE",
        ),
        PipelineStep(
            agent_name="readiness_detector",
            description="Check if decisions are ready to close",
            input_keys=["evidence"],
            output_key="readiness_alerts",
            etvx_id="ML-READINESS",
        ),
        PipelineStep(
            agent_name="coach_linker",
            description="Link evidence to coach session context",
            input_keys=["evidence"],
            output_key="coach_links",
            required=False,
            etvx_id="ML-LINK",
        ),
    ],
)

PROJECT_MGMT_PIPELINE = Pipeline(
    name="project_mgmt",
    practice_area="Project Management",
    description=(
        "PM practice: ticket creation → WBS update → "
        "weekly digest → health alerting"
    ),
    trigger_types=["cron_friday_6pm"],
    steps=[
        PipelineStep(
            agent_name="wbs_updater",
            description="Sync WBS with Jira sprint state",
            input_keys=[],
            output_key="wbs_state",
            required=False,
            etvx_id="PM-WBS",
        ),
        PipelineStep(
            agent_name="weekly_digest",
            description="Generate weekly progress digest",
            input_keys=["wbs_state"],
            output_key="digest",
            etvx_id="PM-DIGEST",
        ),
        PipelineStep(
            agent_name="alert_agent",
            description="Check project health and fire alerts",
            input_keys=["wbs_state"],
            output_key="alerts",
            required=False,
            etvx_id="PM-ALERT",
        ),
    ],
)

KNOWLEDGE_PIPELINE = Pipeline(
    name="knowledge",
    practice_area="Knowledge Management",
    description=(
        "Knowledge practice: context packaging → "
        "briefing generation (pre-meeting preparation)"
    ),
    trigger_types=["cron_pre_meeting"],
    steps=[
        PipelineStep(
            agent_name="context_packager",
            description="Package project context for meeting",
            input_keys=[],
            output_key="context_package",
            etvx_id="KN-CONTEXT",
        ),
        PipelineStep(
            agent_name="briefing_generator",
            description="Generate pre-meeting briefing",
            input_keys=["context_package"],
            output_key="briefing",
            etvx_id="COACH-BRIEF",
        ),
    ],
)

# All pipelines indexed by name
ALL_PIPELINES: dict[str, Pipeline] = {
    p.name: p for p in [
        REQUIREMENTS_PIPELINE,
        COACH_SESSION_PIPELINE,
        ARCHITECTURE_PIPELINE,
        CODING_PIPELINE,
        ML_DECISION_PIPELINE,
        PROJECT_MGMT_PIPELINE,
        KNOWLEDGE_PIPELINE,
    ]
}

# Trigger → pipeline mapping (which pipeline handles which trigger)
TRIGGER_PIPELINES: dict[str, list[str]] = {}
for pipe in ALL_PIPELINES.values():
    for tt in pipe.trigger_types:
        TRIGGER_PIPELINES.setdefault(tt, []).append(pipe.name)


def get_framework_summary() -> dict[str, Any]:
    """Summary of the complete framework for presentation."""
    total_steps = sum(len(p.steps) for p in ALL_PIPELINES.values())
    practice_areas = list({p.practice_area for p in ALL_PIPELINES.values()})

    connections = []
    for pipe in ALL_PIPELINES.values():
        for i, step in enumerate(pipe.steps):
            if i > 0:
                prev = pipe.steps[i - 1]
                connections.append({
                    "from": prev.agent_name,
                    "to": step.agent_name,
                    "pipeline": pipe.name,
                    "data_key": step.skip_if_empty or prev.output_key,
                })

    return {
        "framework_name": "eParts Agentic SE System",
        "total_pipelines": len(ALL_PIPELINES),
        "total_pipeline_steps": total_steps,
        "practice_areas": sorted(practice_areas),
        "pipelines": {
            name: {
                "practice_area": p.practice_area,
                "description": p.description,
                "steps": len(p.steps),
                "trigger_types": p.trigger_types,
                "agents": [s.agent_name for s in p.steps],
                "etvx_ids": [s.etvx_id for s in p.steps if s.etvx_id],
            }
            for name, p in ALL_PIPELINES.items()
        },
        "connections": connections,
        "trigger_coverage": TRIGGER_PIPELINES,
    }
