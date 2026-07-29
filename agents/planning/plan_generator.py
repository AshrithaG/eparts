"""
Plan Generator — the Planning Agent. Translates a spec / definition of work
into a reviewable implementation plan *before* any code is written.

Two phases, both driven by prompts/plan_generator.txt:

  1. GRILL — the agent asks every question it needs answered up front (the
     "Grill Me" pattern). If any question is *blocking* — a wrong guess would
     change which files change, the class breakdown, or the test set — the
     agent returns the questions instead of guessing, and no plan is produced.
  2. PLAN — with no blocking ambiguity left, it produces a plan following
     docs/plan_template.md: files to change and how, supporting code
     structures, class breakdown, required tests and what each proves,
     sequencing, out-of-scope, risks, and explicit stop conditions for the
     implementing agent.

Both outcomes are written as markdown artifacts under docs/plans/ so a human
can accept or reject the proposed organization while change is still cheap
(process: docs/spec_to_plan_process.md). Model tiering: this agent is meant to
run on a frontier model; cheaper models implement against the approved plan.

Requires an LLM provider — planning is the one step we do not want a keyword
fallback for, so with no API key configured the agent fails loudly with a
review item rather than emitting a plausible-looking plan.

Triggered by: new spec / story ready for refinement (manual, jira_webhook)
Outputs: docs/plans/PLAN-<date>-<slug>.md (plan awaiting human review), or
         docs/plans/PLAN-<date>-<slug>-questions.md when the spec is too
         ambiguous to plan
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.plan_generator")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PLANS_DIR = PROJECT_ROOT / "docs" / "plans"
PLAN_TEMPLATE_PATH = PROJECT_ROOT / "docs" / "plan_template.md"

CHANGE_TYPE_LABELS = {
    "new": "new file",
    "modify": "modify",
    "delete": "delete",
}


class PlanGeneratorAgent(BaseAgent):
    """
    Reads a spec and produces either a reviewable implementation plan or the
    clarifying questions that must be answered before one can be written.

    The plan artifact — not the code — is the reviewable unit: a human accepts
    or rejects the proposed file set, class breakdown, and test set before
    implementation starts.
    """

    # Source dirs used to build the repository inventory handed to the planner,
    # so the plan names real paths instead of invented ones.
    CONTEXT_DIRS = ("agents", "pipeline", "mcp", "orchestrator", "tests", "prompts")
    CONTEXT_SUFFIXES = (".py", ".txt", ".yaml", ".yml")
    MAX_CONTEXT_LINES = 200

    MAX_SPEC_CHARS = 12000
    MAX_TEMPLATE_CHARS = 6000
    MAX_ANSWER_CHARS = 4000

    GRILL_MAX_TOKENS = 2048
    PLAN_MAX_TOKENS = 8192

    # A single blocking question is enough to stop planning. Callers may raise
    # the tolerance explicitly via metadata["max_blocking_questions"].
    MAX_BLOCKING_QUESTIONS = 0

    # Sections the plan must actually populate to be worth reviewing.
    REQUIRED_PLAN_SECTIONS = (
        "files_to_change",
        "code_structures",
        "class_breakdown",
        "tests_required",
        "stop_conditions",
    )

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="plan_generator", mcp_clients=mcp_clients)

    # ------------------------------------------------------------------
    # main entry point
    # ------------------------------------------------------------------

    def run(self, trigger: AgentTrigger) -> AgentResult:
        metadata = trigger.metadata or {}
        pipeline_ctx = metadata.get("pipeline_context", {}) or {}

        spec_text, spec_ref = self._resolve_spec(trigger, pipeline_ctx)
        if not spec_text.strip():
            return AgentResult(
                agent=self.name,
                success=False,
                errors=[
                    "No spec provided. Pass metadata['spec'] (text) or "
                    "metadata['spec_path'] (file), or set trigger.source to a spec file."
                ],
            )

        if not self._settings.has_llm:
            return AgentResult(
                agent=self.name,
                success=False,
                errors=[
                    "No LLM provider configured — plan generation requires a "
                    "frontier-tier model and has no offline fallback by design. "
                    "Set GEMINI_API_KEY or ANTHROPIC_API_KEY in .env (see .env.example)."
                ],
                outputs=[AgentOutput(
                    output_type="plan_skipped",
                    description="Planning skipped: no LLM provider configured",
                    reference=spec_ref,
                )],
                requires_human_review=True,
                review_items=[{
                    "type": "plan_blocked",
                    "reason": "no_llm_provider",
                    "spec": spec_ref,
                }],
            )

        date = metadata.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        repo_context = metadata.get("repo_context") or self._collect_repo_context()
        plan_template = self._load_plan_template()
        answers_md = self._format_answers(metadata.get("answers") or pipeline_ctx.get("answers"))

        # ---- phase 1: Grill Me ----
        grill = self._llm_json(
            "GRILL",
            spec=spec_text,
            repo_context=repo_context,
            plan_template=plan_template,
            answers=answers_md,
            max_tokens=self.GRILL_MAX_TOKENS,
        )
        if grill is None:
            return AgentResult(
                agent=self.name,
                success=False,
                errors=[
                    "GRILL phase failed: no parseable JSON returned by "
                    f"{self._settings.active_provider}. Plan not generated."
                ],
                requires_human_review=True,
                review_items=[{
                    "type": "plan_blocked",
                    "reason": "grill_unparseable",
                    "spec": spec_ref,
                }],
            )

        questions = [q for q in self._as_list(grill.get("clarifying_questions")) if isinstance(q, dict)]
        blocking = [q for q in questions if self._is_blocking(q)]
        title = str(grill.get("spec_title") or metadata.get("title") or "untitled work item")
        summary = str(grill.get("spec_summary") or "")
        plan_id = f"PLAN-{date}-{self._slug(title)}"

        try:
            max_blocking = int(metadata.get("max_blocking_questions", self.MAX_BLOCKING_QUESTIONS))
        except (TypeError, ValueError):
            max_blocking = self.MAX_BLOCKING_QUESTIONS

        declared_ready = bool(grill.get("ready_to_plan", not blocking))
        ready = declared_ready and len(blocking) <= max_blocking
        forced = bool(metadata.get("force_plan", False))

        logger.info(
            f"grill complete: plan_id={plan_id} questions={len(questions)} "
            f"blocking={len(blocking)} ready={ready} forced={forced}"
        )

        if not ready and not forced:
            return self._questions_result(
                plan_id=plan_id, date=date, title=title, summary=summary,
                spec_ref=spec_ref, questions=questions, blocking=blocking,
            )

        # ---- phase 2: the plan ----
        plan = self._llm_json(
            "PLAN",
            spec=spec_text,
            repo_context=repo_context,
            plan_template=plan_template,
            answers=self._merge_answers(answers_md, questions) if forced else answers_md,
            max_tokens=self.PLAN_MAX_TOKENS,
        )
        if plan is None:
            return AgentResult(
                agent=self.name,
                success=False,
                errors=[
                    "PLAN phase failed: no parseable JSON returned by "
                    f"{self._settings.active_provider}. No plan artifact written."
                ],
                requires_human_review=True,
                review_items=[{
                    "type": "plan_blocked",
                    "reason": "plan_unparseable",
                    "spec": spec_ref,
                }],
            )

        gaps = self._validate_plan(plan)
        content = self._render_plan_markdown(
            plan_id=plan_id, date=date, title=title, spec_ref=spec_ref,
            plan=plan, questions=questions, gaps=gaps, forced=forced,
        )
        rel_path = f"docs/plans/{plan_id}.md"
        written_path = self._write_artifact(rel_path, content)

        outputs: list[AgentOutput] = [AgentOutput(
            output_type="plan_drafted",
            description=(
                f"{plan_id}: {title} — "
                f"{len(self._as_list(plan.get('files_to_change')))} files, "
                f"{len(self._as_list(plan.get('class_breakdown')))} classes, "
                f"{len(self._as_list(plan.get('tests_required')))} tests, "
                f"{len(questions)} questions asked ({len(blocking)} blocking)"
            ),
            reference=written_path or rel_path,
        )]
        outputs.extend(self._commit(rel_path, content, f"Add implementation plan {plan_id}: {title[:50]}"))

        measurements = {
            "plan_id": plan_id,
            "clarifying_questions": len(questions),
            "blocking_questions": len(blocking),
            "files_to_change": len(self._as_list(plan.get("files_to_change"))),
            "code_structures": len(self._as_list(plan.get("code_structures"))),
            "classes": len(self._as_list(plan.get("class_breakdown"))),
            "tests_required": len(self._as_list(plan.get("tests_required"))),
            "stop_conditions": len(self._as_list(plan.get("stop_conditions"))),
            "planned_paths": [
                str(f.get("path", "")) for f in self._as_list(plan.get("files_to_change"))
                if isinstance(f, dict) and f.get("path")
            ],
            "implementation_tier": str(plan.get("implementation_tier") or "cheap"),
            "planning_model": self._planning_model(),
            "template_gaps": gaps,
            "planned_without_answers": forced,
        }

        self.wiki.put("plans", plan_id, {
            "title": title,
            "status": "awaiting_review",
            "spec": spec_ref,
            "date": date,
            "artifact": rel_path,
            **{k: measurements[k] for k in (
                "clarifying_questions", "blocking_questions", "files_to_change",
                "tests_required", "implementation_tier", "planned_paths",
            )},
        }, agent=self.name, pipeline="planning", tags=["plan", date])

        self.emit("plan_drafted", {
            "plan_id": plan_id,
            "spec": spec_ref,
            "artifact": rel_path,
            **{k: measurements[k] for k in (
                "clarifying_questions", "blocking_questions",
                "files_to_change", "tests_required", "implementation_tier",
            )},
        }, pipeline="planning")

        review_items = [{
            "type": "plan_review",
            "plan_id": plan_id,
            "artifact": rel_path,
            "decision": "accept_or_reject",
            "gate": "no implementation may start before this plan is accepted",
        }]
        if gaps:
            review_items.append({
                "type": "plan_incomplete",
                "plan_id": plan_id,
                "missing_sections": gaps,
            })

        return AgentResult(
            agent=self.name,
            success=True,
            outputs=outputs,
            requires_human_review=True,
            review_items=review_items,
            data={
                "plan_id": plan_id,
                "plan": plan,
                "clarifying_questions": questions,
                "artifact_path": rel_path,
                "plan_markdown": content,
                "status": "awaiting_review",
                "measurements": measurements,
            },
        )

    # ------------------------------------------------------------------
    # grill-me outcome
    # ------------------------------------------------------------------

    def _questions_result(
        self, *, plan_id: str, date: str, title: str, summary: str,
        spec_ref: str, questions: list[dict], blocking: list[dict],
    ) -> AgentResult:
        """
        Material ambiguity found: return the questions instead of a plan.

        This is the deliberate stop condition of the planning process — the
        agent hands back to a human rather than guessing at the design.
        """
        content = self._render_questions_markdown(
            plan_id=plan_id, date=date, title=title, summary=summary,
            spec_ref=spec_ref, questions=questions,
        )
        rel_path = f"docs/plans/{plan_id}-questions.md"
        written_path = self._write_artifact(rel_path, content)

        outputs: list[AgentOutput] = [AgentOutput(
            output_type="clarifications_requested",
            description=(
                f"{plan_id}: spec too ambiguous to plan — {len(blocking)} blocking "
                f"of {len(questions)} questions must be answered first"
            ),
            reference=written_path or rel_path,
        )]
        outputs.extend(self._commit(
            rel_path, content, f"Clarifying questions for {plan_id}: {title[:50]}"
        ))

        self.wiki.put("plans", plan_id, {
            "title": title,
            "status": "awaiting_answers",
            "spec": spec_ref,
            "date": date,
            "artifact": rel_path,
            "clarifying_questions": len(questions),
            "blocking_questions": len(blocking),
        }, agent=self.name, pipeline="planning", tags=["plan", "blocked", date])

        self.emit("plan_clarifications_requested", {
            "plan_id": plan_id,
            "spec": spec_ref,
            "artifact": rel_path,
            "clarifying_questions": len(questions),
            "blocking_questions": len(blocking),
            "questions": [str(q.get("question", "")) for q in blocking][:10],
        }, pipeline="planning")

        return AgentResult(
            agent=self.name,
            success=True,
            outputs=outputs,
            requires_human_review=True,
            review_items=[{
                "type": "spec_clarification",
                "plan_id": plan_id,
                "artifact": rel_path,
                "blocking_questions": [str(q.get("question", "")) for q in blocking],
                "gate": "answer the blocking questions, then re-run with metadata['answers']",
            }],
            data={
                "plan_id": plan_id,
                "plan": None,
                "clarifying_questions": questions,
                "artifact_path": rel_path,
                "status": "awaiting_answers",
                "measurements": {
                    "plan_id": plan_id,
                    "clarifying_questions": len(questions),
                    "blocking_questions": len(blocking),
                    "planning_model": self._planning_model(),
                },
            },
        )

    # ------------------------------------------------------------------
    # inputs
    # ------------------------------------------------------------------

    def _resolve_spec(self, trigger: AgentTrigger, pipeline_ctx: dict) -> tuple[str, str]:
        """
        Find the definition of work. Accepts inline text or a file path, from
        trigger metadata, upstream pipeline context, or trigger.source.

        Returns (spec_text, human-readable reference).
        """
        metadata = trigger.metadata or {}

        for key in ("spec_text", "spec", "work_definition"):
            value = metadata.get(key) or pipeline_ctx.get(key)
            if isinstance(value, str) and value.strip():
                ref = str(metadata.get("spec_ref") or metadata.get("ticket") or trigger.source or key)
                return value, ref
            if isinstance(value, dict):
                ref = str(value.get("id") or value.get("key") or trigger.source or key)
                return json.dumps(value, indent=2, default=str), ref

        for key in ("spec_path", "source"):
            candidate = metadata.get(key) or pipeline_ctx.get(key)
            if not isinstance(candidate, str) or not candidate.strip():
                continue
            path = Path(candidate)
            if not path.is_absolute():
                path = PROJECT_ROOT / path
            if path.is_file():
                try:
                    return path.read_text(encoding="utf-8"), candidate
                except OSError as exc:
                    logger.warning(f"Could not read spec file {path}: {exc}")

        if trigger.source:
            path = Path(trigger.source)
            if not path.is_absolute():
                path = PROJECT_ROOT / path
            if path.is_file():
                try:
                    return path.read_text(encoding="utf-8"), trigger.source
                except OSError as exc:
                    logger.warning(f"Could not read spec file {path}: {exc}")

        return "", str(trigger.source or "unknown")

    def _collect_repo_context(self) -> str:
        """List real source paths so the planner cannot invent file names."""
        lines: list[str] = []
        for dirname in self.CONTEXT_DIRS:
            base = PROJECT_ROOT / dirname
            if not base.is_dir():
                continue
            files = sorted(
                p for p in base.rglob("*")
                if p.is_file()
                and p.suffix in self.CONTEXT_SUFFIXES
                and "__pycache__" not in p.parts
            )
            if not files:
                continue
            lines.append(f"{dirname}/")
            lines.extend(f"  {p.relative_to(PROJECT_ROOT).as_posix()}" for p in files)

        if not lines:
            return "(repository inventory unavailable)"
        if len(lines) > self.MAX_CONTEXT_LINES:
            omitted = len(lines) - self.MAX_CONTEXT_LINES
            lines = lines[: self.MAX_CONTEXT_LINES]
            lines.append(f"  ... ({omitted} more paths omitted)")
        return "\n".join(lines)

    def _load_plan_template(self) -> str:
        """The plan template is the single source of truth for plan shape."""
        if PLAN_TEMPLATE_PATH.is_file():
            try:
                return PLAN_TEMPLATE_PATH.read_text(encoding="utf-8")[: self.MAX_TEMPLATE_CHARS]
            except OSError as exc:
                logger.warning(f"Could not read {PLAN_TEMPLATE_PATH}: {exc}")
        logger.warning("docs/plan_template.md missing — planning with the inline fallback template")
        return (
            "Sections required: work summary; clarifying questions; files to change "
            "and how; supporting code structures; class breakdown; required tests and "
            "what each proves; implementation sequence; out of scope; risks; stop "
            "conditions; review gate."
        )

    def _format_answers(self, answers: Any) -> str:
        """Render answers to previously asked questions for the PLAN phase."""
        if not answers:
            return "(none provided — this is the first pass over this spec)"

        lines: list[str] = []
        if isinstance(answers, dict):
            for question, answer in answers.items():
                lines.append(f"- Q: {question}\n  A: {answer}")
        elif isinstance(answers, list):
            for item in answers:
                if isinstance(item, dict):
                    question = item.get("question", "(unlabelled question)")
                    answer = item.get("answer", item.get("response", ""))
                    lines.append(f"- Q: {question}\n  A: {answer}")
                else:
                    lines.append(f"- {item}")
        else:
            lines.append(str(answers))

        return "\n".join(lines)[: self.MAX_ANSWER_CHARS] or "(none provided)"

    def _merge_answers(self, answers_md: str, questions: list[dict]) -> str:
        """
        Planning was forced past unanswered blocking questions. Hand the
        planner its own fallback assumptions so they land in the plan's
        assumptions section, where a reviewer will see them.
        """
        lines = [answers_md, "", "UNANSWERED — proceeding on the planner's own assumptions:"]
        for q in questions:
            if not self._is_blocking(q):
                continue
            lines.append(
                f"- Q: {q.get('question', '')}\n"
                f"  ASSUMED: {q.get('assumption_if_unanswered', 'no assumption stated')}"
            )
        return "\n".join(lines)[: self.MAX_ANSWER_CHARS]

    # ------------------------------------------------------------------
    # LLM
    # ------------------------------------------------------------------

    def _llm_json(
        self, phase: str, *, spec: str, repo_context: str, plan_template: str,
        answers: str, max_tokens: int,
    ) -> dict | None:
        """Run one phase of prompts/plan_generator.txt. Returns None on failure."""
        prompt = self.load_prompt(
            "plan_generator.txt",
            phase=phase,
            spec=spec[: self.MAX_SPEC_CHARS],
            repo_context=repo_context,
            plan_template=plan_template,
            answers=answers,
        )
        try:
            raw = self.call_claude(prompt, max_tokens=max_tokens)
        except Exception as exc:
            logger.warning(f"LLM call failed during {phase} phase: {exc}")
            return None
        parsed = self._parse_json_object(raw)
        if parsed is None:
            logger.error(f"Could not parse {phase} response as a JSON object")
        return parsed

    @staticmethod
    def _parse_json_object(raw: str) -> dict | None:
        """Parse a JSON object, tolerating code fences and surrounding prose."""
        if not raw:
            return None
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
            text = re.sub(r"```\s*$", "", text).strip()
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
        return None

    def _planning_model(self) -> str:
        provider = self._settings.active_provider
        if provider == "anthropic":
            return f"anthropic:{self._settings.claude_model}"
        if provider == "gemini":
            return f"gemini:{self._settings.gemini_model}"
        return provider

    # ------------------------------------------------------------------
    # validation
    # ------------------------------------------------------------------

    def _validate_plan(self, plan: dict) -> list[str]:
        """
        Verification step: which required template sections came back empty,
        plus files that no test covers. Reported to the reviewer, not hidden.
        """
        gaps = [
            section for section in self.REQUIRED_PLAN_SECTIONS
            if not self._as_list(plan.get(section))
        ]

        tests_blob = json.dumps(self._as_list(plan.get("tests_required")), default=str).lower()
        untested = [
            str(entry.get("path", ""))
            for entry in self._as_list(plan.get("files_to_change"))
            if isinstance(entry, dict)
            and entry.get("path")
            and str(entry.get("change_type", "")).lower() != "delete"
            and Path(str(entry["path"])).stem.lower() not in tests_blob
        ]
        if untested:
            gaps.append("no test traced to: " + ", ".join(untested[:6]))
        return gaps

    # ------------------------------------------------------------------
    # artifact rendering
    # ------------------------------------------------------------------

    def _render_questions_markdown(
        self, *, plan_id: str, date: str, title: str, summary: str,
        spec_ref: str, questions: list[dict],
    ) -> str:
        lines = [
            f"# {plan_id} — Clarifying Questions (no plan yet)",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| **Plan ID** | `{plan_id}` |",
            f"| **Work item** | {title} |",
            f"| **Spec** | `{spec_ref}` |",
            f"| **Date** | {date} |",
            f"| **Planning model** | `{self._planning_model()}` |",
            "| **Status** | `awaiting answers` — planning stopped, no code may start |",
            "",
            "This spec contains ambiguity that would change the implementation plan.",
            "Per `docs/spec_to_plan_process.md`, the planning agent surfaces the",
            "questions rather than guessing. Answer the blocking questions below and",
            "re-run the agent with `metadata['answers']`.",
            "",
        ]
        if summary:
            lines += ["## Understood as", "", summary, ""]

        lines += [
            "## Questions",
            "",
            "| # | Question | Blocking? | Why it matters | Assumption if unanswered | Ask |",
            "|---|---|---|---|---|---|",
        ]
        for i, q in enumerate(questions, start=1):
            lines.append(
                f"| {i} | {self._cell(q.get('question'))} "
                f"| {'**yes**' if self._is_blocking(q) else 'no'} "
                f"| {self._cell(q.get('why_it_matters'))} "
                f"| {self._cell(q.get('assumption_if_unanswered'))} "
                f"| {self._cell(q.get('ask'))} |"
            )

        blocking_count = sum(1 for q in questions if self._is_blocking(q))
        lines += [
            "",
            "## Answers",
            "",
            "Record answers here (or in the Jira ticket) and re-run the planning agent.",
            "",
            f"- Questions asked: **{len(questions)}** ({blocking_count} blocking)",
            "- [ ] All blocking questions answered — planning may resume",
            "",
            "---",
            f"_Generated by the plan_generator agent on {date} "
            f"(model `{self._planning_model()}`). Process: `docs/spec_to_plan_process.md`._",
        ]
        return "\n".join(lines) + "\n"

    def _render_plan_markdown(
        self, *, plan_id: str, date: str, title: str, spec_ref: str,
        plan: dict, questions: list[dict], gaps: list[str], forced: bool,
    ) -> str:
        tier = str(plan.get("implementation_tier") or "cheap")
        lines = [
            f"# {plan_id} — Implementation Plan",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| **Plan ID** | `{plan_id}` |",
            f"| **Work item** | {plan.get('spec_title') or title} |",
            f"| **Spec** | `{spec_ref}` |",
            f"| **Date** | {date} |",
            f"| **Planning model** | `{self._planning_model()}` (frontier tier) |",
            f"| **Implementation tier** | `{tier}` |",
            f"| **Estimated effort** | {self._cell(plan.get('estimated_effort')) or 'not estimated'} |",
            "| **Status** | `awaiting review` — no code may start until accepted |",
            "",
            "> Review the plan, not just the code. Accepting or rejecting the file set,",
            "> class breakdown, and test set here is far cheaper than reworking an",
            "> implementation. Process: `docs/spec_to_plan_process.md`.",
            "",
            "## 1. Work summary",
            "",
            str(plan.get("spec_summary") or "_not provided by the planner_"),
            "",
        ]

        if forced:
            lines += [
                "> **Warning:** this plan was generated with `force_plan` while blocking",
                "> questions were unanswered. The assumptions in §2 are unvalidated.",
                "",
            ]

        # §2 questions / assumptions
        lines += ["## 2. Clarifying questions asked (Grill Me)", ""]
        if questions:
            lines += [
                "| # | Question | Blocking? | Why it matters | Answer / assumption |",
                "|---|---|---|---|---|",
            ]
            for i, q in enumerate(questions, start=1):
                lines.append(
                    f"| {i} | {self._cell(q.get('question'))} "
                    f"| {'yes' if self._is_blocking(q) else 'no'} "
                    f"| {self._cell(q.get('why_it_matters'))} "
                    f"| {self._cell(q.get('answer') or q.get('assumption_if_unanswered'))} |"
                )
        else:
            lines.append("None — the planner reported no ambiguity in this spec.")
        lines.append("")

        assumptions = self._as_list(plan.get("assumptions"))
        if assumptions:
            lines += ["**Assumptions this plan rests on:**", ""]
            lines += [f"- {self._flat(a)}" for a in assumptions]
            lines.append("")

        # §3 files
        lines += [
            "## 3. Files to change — and how",
            "",
            "| File | Change | What changes | Why |",
            "|---|---|---|---|",
        ]
        files = self._as_list(plan.get("files_to_change"))
        if files:
            for entry in files:
                if not isinstance(entry, dict):
                    lines.append(f"| {self._cell(entry)} | ? | | |")
                    continue
                change = str(entry.get("change_type", "modify")).lower()
                lines.append(
                    f"| `{self._cell(entry.get('path'))}` "
                    f"| {CHANGE_TYPE_LABELS.get(change, change)} "
                    f"| {self._cell(entry.get('what_changes'))} "
                    f"| {self._cell(entry.get('why'))} |"
                )
        else:
            lines.append("| _none listed_ | | | |")
        lines.append("")

        # §4 structures
        lines += ["## 4. Code structures supporting the feature", ""]
        structures = self._as_list(plan.get("code_structures"))
        if structures:
            lines += ["| Structure | Kind | Location | Purpose |", "|---|---|---|---|"]
            for s in structures:
                if isinstance(s, dict):
                    lines.append(
                        f"| `{self._cell(s.get('name'))}` "
                        f"| {self._cell(s.get('kind'))} "
                        f"| `{self._cell(s.get('location'))}` "
                        f"| {self._cell(s.get('purpose'))} |"
                    )
                else:
                    lines.append(f"| {self._cell(s)} | | | |")
        else:
            lines.append("_none listed_")
        lines.append("")

        # §5 classes
        lines += ["## 5. Class / module breakdown", ""]
        classes = self._as_list(plan.get("class_breakdown"))
        if classes:
            for c in classes:
                if not isinstance(c, dict):
                    lines += [f"- {self._flat(c)}", ""]
                    continue
                module = self._cell(c.get("module"))
                header = f"### `{self._cell(c.get('class_name'))}`"
                if module:
                    header += f" — `{module}`"
                lines += [header, "", f"**Responsibility:** {self._cell(c.get('responsibility'))}", ""]
                methods = self._as_list(c.get("key_methods"))
                if methods:
                    lines += ["| Method | Signature | Does |", "|---|---|---|"]
                    for m in methods:
                        if isinstance(m, dict):
                            lines.append(
                                f"| `{self._cell(m.get('name'))}` "
                                f"| `{self._cell(m.get('signature'))}` "
                                f"| {self._cell(m.get('does'))} |"
                            )
                        else:
                            lines.append(f"| `{self._cell(m)}` | | |")
                    lines.append("")
                collaborators = self._as_list(c.get("collaborators"))
                if collaborators:
                    lines += [
                        "**Collaborators:** " + ", ".join(f"`{self._flat(x)}`" for x in collaborators),
                        "",
                    ]
        else:
            lines += ["_none listed_", ""]

        # §6 tests
        lines += [
            "## 6. Required tests — and what each one proves",
            "",
            "| Test | File | Level | What it tests | Fails when |",
            "|---|---|---|---|---|",
        ]
        tests = self._as_list(plan.get("tests_required"))
        if tests:
            for t in tests:
                if isinstance(t, dict):
                    lines.append(
                        f"| `{self._cell(t.get('name'))}` "
                        f"| `{self._cell(t.get('file'))}` "
                        f"| {self._cell(t.get('level'))} "
                        f"| {self._cell(t.get('what_it_tests'))} "
                        f"| {self._cell(t.get('fails_when'))} |"
                    )
                else:
                    lines.append(f"| {self._cell(t)} | | | | |")
        else:
            lines.append("| _none listed_ | | | | |")
        lines.append("")

        # §7-9
        lines += self._numbered_bullets("7. Implementation sequence", plan.get("implementation_sequence"), ordered=True)
        lines += self._numbered_bullets("8. Out of scope", plan.get("out_of_scope"))

        lines += ["## 9. Risks", ""]
        risks = self._as_list(plan.get("risks"))
        if risks:
            lines += ["| Risk | Mitigation |", "|---|---|"]
            for r in risks:
                if isinstance(r, dict):
                    lines.append(f"| {self._cell(r.get('risk'))} | {self._cell(r.get('mitigation'))} |")
                else:
                    lines.append(f"| {self._cell(r)} | |")
        else:
            lines.append("_none listed_")
        lines.append("")

        # §10 stop conditions
        lines += [
            "## 10. Stop conditions",
            "",
            "When the implementing agent stops and hands off instead of trying again.",
            "",
            "| Condition | Action |",
            "|---|---|",
        ]
        stops = self._as_list(plan.get("stop_conditions"))
        if stops:
            for s in stops:
                if isinstance(s, dict):
                    lines.append(
                        f"| {self._cell(s.get('condition'))} "
                        f"| {self._cell(s.get('action')) or 'hand off to human'} |"
                    )
                else:
                    lines.append(f"| {self._cell(s)} | hand off to human |")
        else:
            lines.append("| _none listed — reject this plan_ | |")
        lines.append("")

        # §11 gate
        lines += [
            "## 11. Review gate",
            "",
            "- [ ] **Accepted** — file set, class breakdown, and test set are right; "
            f"implementation may start on the `{tier}` tier",
            "- [ ] **Rejected** — reason: `organization` | `missing-tests` | `wrong-files` "
            "| `scope` | `unanswered-ambiguity`",
            "",
            "Reviewer: ______ · Date: ______ · Time spent: ____ min",
            "",
        ]
        if gaps:
            lines += [
                "**Automated completeness check flagged:**",
                "",
            ]
            lines += [f"- {g}" for g in gaps]
            lines.append("")

        lines += [
            "---",
            f"_Generated by the plan_generator agent on {date} "
            f"(model `{self._planning_model()}`). Template: `docs/plan_template.md`. "
            "Process: `docs/spec_to_plan_process.md`._",
        ]
        return "\n".join(lines) + "\n"

    def _numbered_bullets(self, heading: str, value: Any, *, ordered: bool = False) -> list[str]:
        lines = [f"## {heading}", ""]
        items = self._as_list(value)
        if not items:
            lines += ["_none listed_", ""]
            return lines
        for i, item in enumerate(items, start=1):
            prefix = f"{i}." if ordered else "-"
            lines.append(f"{prefix} {self._flat(item)}")
        lines.append("")
        return lines

    # ------------------------------------------------------------------
    # output plumbing
    # ------------------------------------------------------------------

    def _write_artifact(self, rel_path: str, content: str) -> str:
        """Write the reviewable markdown artifact into the working tree."""
        path = PROJECT_ROOT / rel_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            logger.info(f"plan artifact written: {rel_path}")
            return str(path)
        except OSError as exc:
            logger.warning(f"Could not write plan artifact {rel_path}: {exc}")
            return ""

    def _commit(self, rel_path: str, content: str, message: str) -> list[AgentOutput]:
        """Commit the artifact through whichever repo MCP client is wired up."""
        repo = self.mcp.get("github") or self.mcp.get("bitbucket")
        if not repo:
            return []
        try:
            result = repo.commit_file(
                file_path=rel_path,
                content=content,
                message=message,
                agent_name=self.name,
            )
        except Exception as exc:
            logger.warning(f"Commit of {rel_path} failed: {exc}")
            return []
        if isinstance(result, dict) and result.get("ok"):
            return [AgentOutput(
                output_type="file_committed",
                description=message,
                reference=rel_path,
            )]
        return []

    # ------------------------------------------------------------------
    # small helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _as_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return [v for v in value if v not in ("", None)]
        if isinstance(value, dict):
            return [value]
        if isinstance(value, str):
            return [value] if value.strip() else []
        return [value]

    @staticmethod
    def _is_blocking(question: dict) -> bool:
        value = question.get("blocking")
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"true", "yes", "y", "blocking", "1"}

    @classmethod
    def _flat(cls, value: Any) -> str:
        """Flatten a value to a single markdown-safe line."""
        if isinstance(value, dict):
            value = " · ".join(f"{k}: {v}" for k, v in value.items())
        elif isinstance(value, (list, tuple)):
            value = "; ".join(str(v) for v in value)
        return re.sub(r"\s+", " ", str(value)).strip()

    @classmethod
    def _cell(cls, value: Any) -> str:
        """Flatten a value for use inside a markdown table cell."""
        return cls._flat("" if value is None else value).replace("|", "\\|")

    @staticmethod
    def _slug(text: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
        return (slug[:48].rstrip("-")) or "work-item"
