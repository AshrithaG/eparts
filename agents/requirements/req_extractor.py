"""
REQ Extractor — synthesizes formal, categorized requirements from
parsed meeting data.

Takes raw action items, decisions, and discussion points from the
transcript parser and produces proper requirements with categories:
  FUNCTIONAL, NON_FUNCTIONAL, USER_GOAL, SOFT_GOAL, CONSTRAINT

Uses LLM when available for intelligent synthesis; falls back to
domain-aware extraction for eParts using keyword patterns.

Triggered by: transcript_parser + priority_classifier output
Outputs: REQ-XXX.md files committed to GitHub
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.req_extractor")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Domain knowledge for offline extraction
EPARTS_REQUIREMENT_PATTERNS: list[dict[str, Any]] = [
    {
        "keywords": ["extract", "attribute", "spec sheet", "pdf", "catalog", "parse", "ingestion"],
        "id": "REQ-001",
        "title": "Automated product attribute extraction",
        "statement": "The system shall automatically extract product attributes (name, description, specifications, category) from vendor spec sheets in PDF, CSV, and Excel formats.",
        "category": "FUNCTIONAL",
        "rationale": "Core project objective — eParts receives catalogs from 50+ vendors in inconsistent formats.",
        "acceptance_criteria": "Given a vendor spec sheet, the system extracts at least 5 key attributes with >80% accuracy.",
    },
    {
        "keywords": ["confidence", "score", "threshold", "accuracy", "precision"],
        "id": "REQ-002",
        "title": "ML confidence scoring",
        "statement": "The system shall assign a confidence score (0.0-1.0) to every ML-predicted attribute value.",
        "category": "NON_FUNCTIONAL",
        "rationale": "Client emphasized need for transparency — operators must know which predictions to trust vs review.",
        "acceptance_criteria": "Every extracted attribute includes a confidence score; scores correlate with actual accuracy (calibration within 10%).",
    },
    {
        "keywords": ["review", "human", "correct", "approve", "manual", "operator", "queue"],
        "id": "REQ-003",
        "title": "Human-in-the-loop review workflow",
        "statement": "The system shall route low-confidence predictions (below configurable threshold) to a human review queue where operators can approve, correct, or reject values.",
        "category": "USER_GOAL",
        "rationale": "Client requires human oversight for business-critical data — cannot auto-publish uncertain predictions.",
        "acceptance_criteria": "Predictions below threshold appear in review queue; operator can approve/edit/reject; corrections feed back to model.",
    },
    {
        "keywords": ["format", "vendor", "inconsistent", "variation", "standard", "normalize"],
        "id": "REQ-004",
        "title": "Multi-format vendor data support",
        "statement": "The system shall support ingestion of vendor catalogs in at least 3 formats: PDF, CSV, and Excel, normalizing data into a unified schema.",
        "category": "FUNCTIONAL",
        "rationale": "Vendors submit data in different formats — the system must handle this variation without manual conversion.",
        "acceptance_criteria": "System successfully ingests and normalizes test files in PDF, CSV, and XLSX formats.",
    },
    {
        "keywords": ["azure", "cloud", "deploy", "infrastructure", "hosting"],
        "id": "REQ-005",
        "title": "Azure cloud deployment",
        "statement": "The system shall be deployable on Microsoft Azure cloud infrastructure using Azure App Service.",
        "category": "CONSTRAINT",
        "rationale": "eParts' existing infrastructure runs on Azure — non-negotiable deployment target.",
        "acceptance_criteria": "System runs successfully on Azure App Service with all endpoints accessible.",
    },
    {
        "keywords": ["staging", "table", "validation", "before", "production", "write"],
        "id": "REQ-006",
        "title": "Staging tables for data validation",
        "statement": "The system shall write all ML-extracted data to staging tables first, never directly to production, allowing validation before promotion.",
        "category": "FUNCTIONAL",
        "rationale": "Architecture decision to prevent bad ML predictions from corrupting production catalog data.",
        "acceptance_criteria": "No pipeline path writes directly to production tables; all data passes through staging with validation.",
    },
    {
        "keywords": ["metric", "dashboard", "monitor", "report", "track", "performance"],
        "id": "REQ-007",
        "title": "Pipeline performance monitoring",
        "statement": "The system should provide a monitoring dashboard showing pipeline throughput, ML accuracy metrics, and error rates.",
        "category": "NON_FUNCTIONAL",
        "rationale": "Client wants visibility into system health and ML model performance over time.",
        "acceptance_criteria": "Dashboard displays: records processed/day, accuracy by attribute type, error count, and trend charts.",
    },
    {
        "keywords": ["manual", "effort", "automate", "reduce", "time", "efficiency", "save"],
        "id": "REQ-008",
        "title": "Reduce manual data entry effort",
        "statement": "The system should reduce manual product data entry effort by at least 60% compared to the current fully manual process.",
        "category": "SOFT_GOAL",
        "rationale": "Primary business value proposition — eParts currently has staff manually keying in vendor data.",
        "acceptance_criteria": "Measured time-to-catalog for 100 products: AI-assisted < 40% of manual baseline.",
    },
    {
        "keywords": ["per.attribute", "routing", "classification", "category", "predict"],
        "id": "REQ-009",
        "title": "Per-attribute ML routing",
        "statement": "The system shall apply ML classification at the individual attribute level (not per-record), allowing different models/thresholds per attribute type.",
        "category": "FUNCTIONAL",
        "rationale": "Architecture decision — different attributes (description vs. specs vs. category) need different ML approaches.",
        "acceptance_criteria": "Each attribute type can have independent model and threshold configuration.",
    },
    {
        "keywords": ["training", "data", "label", "sample", "200", "dataset"],
        "id": "REQ-010",
        "title": "Training data requirements",
        "statement": "The ML models shall be trainable on a minimum of 200 labeled product examples provided by eParts.",
        "category": "CONSTRAINT",
        "rationale": "Client committed to providing labeled training data; team needs minimum viable dataset for model training.",
        "acceptance_criteria": "Models train and evaluate successfully on provided labeled dataset of >=200 examples.",
    },
    {
        "keywords": ["pricing", "sensitive", "exclude", "not", "price"],
        "id": "REQ-011",
        "title": "Exclude pricing from ML pipeline",
        "statement": "The system shall not include pricing data in the ML extraction pipeline — pricing remains a manual process.",
        "category": "CONSTRAINT",
        "rationale": "Client explicitly stated pricing is too sensitive for automated extraction; business risk too high.",
        "acceptance_criteria": "No pricing fields appear in ML pipeline output; pricing columns remain untouched.",
    },
    {
        "keywords": ["feedback", "loop", "retrain", "improve", "learn", "correction"],
        "id": "REQ-012",
        "title": "Feedback loop for model improvement",
        "statement": "The system should incorporate human corrections back into model retraining to improve accuracy over time.",
        "category": "USER_GOAL",
        "rationale": "Operators correcting predictions should make the system smarter — not just fix individual records.",
        "acceptance_criteria": "After 50+ corrections on an attribute type, retraining measurably improves accuracy on that type.",
    },
]

CATEGORY_LABELS = {
    "FUNCTIONAL": "Functional Requirement",
    "NON_FUNCTIONAL": "Non-Functional Requirement (Quality Attribute)",
    "USER_GOAL": "User Goal",
    "SOFT_GOAL": "Soft Goal",
    "CONSTRAINT": "Constraint",
}


class ReqExtractorAgent(BaseAgent):
    """Synthesizes formal, categorized requirements from parsed meeting data."""

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="req_extractor", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        pipeline_ctx = trigger.metadata.get("pipeline_context", {})
        parsed_minutes = pipeline_ctx.get("parsed_minutes", {})
        classified_items = pipeline_ctx.get("classified_items", [])

        date = (
            trigger.metadata.get("date")
            or pipeline_ctx.get("meeting_date")
            or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        )
        meeting_type = pipeline_ctx.get("meeting_type", "client")

        meeting_data = self._build_meeting_summary(parsed_minutes, classified_items)

        if not meeting_data.strip():
            return AgentResult(
                agent=self.name, success=True,
                outputs=[AgentOutput(
                    output_type="extraction_skipped",
                    description="No meeting data to extract requirements from",
                )],
            )

        existing_reqs = self._get_existing_reqs()

        requirements = None
        if self._settings.has_llm:
            requirements = self._extract_with_llm(meeting_data, existing_reqs, date)

        if not requirements:
            requirements = self._extract_offline(parsed_minutes, classified_items, existing_reqs)

        if not requirements:
            return AgentResult(
                agent=self.name, success=True,
                outputs=[AgentOutput(
                    output_type="extraction_skipped",
                    description="No new requirements identified from this meeting",
                )],
            )

        outputs = []
        repo = self.mcp.get("github") or self.mcp.get("bitbucket")

        for req in requirements:
            req_id = req.get("id", f"REQ-{hash(req.get('title',''))%1000:03d}")
            content = self._format_req_file(req, date, meeting_type)
            filename = f"requirements/parsed/{req_id}.md"

            self.wiki.put("requirements", req_id, {
                "title": req.get("title", ""),
                "statement": req.get("statement", ""),
                "category": req.get("category", "FUNCTIONAL"),
                "priority": req.get("priority", "P1"),
                "date": date,
                "meeting_type": meeting_type,
            }, agent=self.name, pipeline="requirements")

            if repo:
                result = repo.commit_file(
                    file_path=filename,
                    content=content,
                    message=f"Add {req.get('category', 'REQ')} {req_id}: {req.get('title', '')[:50]}",
                    agent_name=self.name,
                )
                if result.get("ok"):
                    outputs.append(AgentOutput(
                        output_type="file_committed",
                        description=f"{req_id} [{req.get('category', '?')}] {req.get('title', '')}",
                        reference=filename,
                    ))
                else:
                    outputs.append(AgentOutput(
                        output_type="req_extracted",
                        description=f"{req_id} [{req.get('category', '?')}] {req.get('title', '')}",
                        reference=req_id,
                    ))
            else:
                outputs.append(AgentOutput(
                    output_type="req_extracted",
                    description=f"{req_id} [{req.get('category', '?')}] {req.get('title', '')}",
                    reference=req_id,
                ))

        categories = {}
        for r in requirements:
            cat = r.get("category", "UNKNOWN")
            categories[cat] = categories.get(cat, 0) + 1
        cat_summary = ", ".join(f"{c}: {n}" for c, n in sorted(categories.items()))

        self.emit("requirements_extracted", {
            "count": len(requirements),
            "categories": categories,
            "date": date,
        })

        return AgentResult(
            agent=self.name, success=True, outputs=outputs,
            data={
                "requirements": requirements,
                "requirements_count": len(requirements),
                "categories": categories,
            },
        )

    def _build_meeting_summary(self, parsed_minutes: dict, classified_items: list) -> str:
        """Build a text summary of meeting data for the LLM."""
        parts = []
        if isinstance(parsed_minutes, dict):
            for key in ["decisions", "action_items", "open_questions",
                        "new_requirements", "key_discussion_points"]:
                items = parsed_minutes.get(key, [])
                if items:
                    parts.append(f"\n{key.upper()}:")
                    for item in items:
                        if isinstance(item, dict):
                            parts.append(f"  - {item.get('text', str(item))}")
                        else:
                            parts.append(f"  - {item}")

        if classified_items:
            parts.append("\nCLASSIFIED ITEMS:")
            for item in classified_items:
                if isinstance(item, dict):
                    parts.append(f"  - [{item.get('priority', '?')}] {item.get('text', str(item))}")

        return "\n".join(parts)

    def _get_existing_reqs(self) -> str:
        """Get already-extracted requirements to avoid duplicates."""
        try:
            entries = self.wiki.list_namespace("requirements")
            if entries:
                lines = []
                for e in entries[:20]:
                    val = e.get("value", {})
                    if isinstance(val, dict):
                        lines.append(f"- {e.get('key', '?')}: {val.get('title', val.get('text', ''))[:80]}")
                return "\n".join(lines)
        except Exception:
            pass
        return "(none yet)"

    def _extract_with_llm(self, meeting_data: str, existing_reqs: str, date: str) -> list[dict] | None:
        """Use LLM to synthesize proper requirements from meeting data."""
        prompt = self.load_prompt(
            "req_extractor.txt",
            meeting_data=meeting_data[:6000],
            existing_reqs=existing_reqs[:1000],
        )

        try:
            raw = self.call_claude(prompt)
        except Exception as exc:
            logger.warning(f"LLM call failed, falling back to offline: {exc}")
            return None

        try:
            reqs = json.loads(raw)
            if isinstance(reqs, list):
                return reqs
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        logger.warning("Failed to parse LLM response for requirements")
        return None

    def _extract_offline(self, parsed_minutes: dict, classified_items: list,
                         existing_reqs: str) -> list[dict]:
        """
        Domain-aware offline extraction using eParts knowledge.

        Matches meeting discussion keywords against known requirement patterns.
        Also pulls context from ALL previous meeting JSONs in minutes/ so even
        a thin transcript produces meaningful requirements.
        """
        all_text = ""
        if isinstance(parsed_minutes, dict):
            for key in ["decisions", "action_items", "open_questions",
                        "new_requirements", "key_discussion_points"]:
                for item in parsed_minutes.get(key, []):
                    if isinstance(item, dict):
                        all_text += " " + item.get("text", "")
                    else:
                        all_text += " " + str(item)

        for item in classified_items:
            if isinstance(item, dict):
                all_text += " " + item.get("text", "")

        # Pull context from all previous meeting JSONs for richer matching
        all_text += " " + self._load_all_meeting_context()

        all_text = all_text.lower()

        already_extracted = set()
        for line in existing_reqs.split("\n"):
            match = re.search(r"(REQ-\d+)", line)
            if match:
                already_extracted.add(match.group(1))

        matched = []
        for pattern in EPARTS_REQUIREMENT_PATTERNS:
            if pattern["id"] in already_extracted:
                continue

            score = sum(1 for kw in pattern["keywords"] if re.search(kw, all_text))
            if score >= 1:
                matched.append((score, pattern))

        matched.sort(key=lambda x: -x[0])
        requirements = []
        for score, pattern in matched[:8]:
            req = {
                "id": pattern["id"],
                "title": pattern["title"],
                "statement": pattern["statement"],
                "category": pattern["category"],
                "priority": "P0" if score >= 3 else "P1" if score >= 2 else "P2",
                "rationale": pattern["rationale"],
                "source_speaker": "team discussion",
                "acceptance_criteria": pattern["acceptance_criteria"],
                "related_concerns": [],
            }
            requirements.append(req)

        return requirements

    def _load_all_meeting_context(self) -> str:
        """Load text from all meeting JSONs for comprehensive keyword matching."""
        minutes_dir = PROJECT_ROOT / "minutes"
        if not minutes_dir.exists():
            return ""
        texts = []
        for jf in sorted(minutes_dir.glob("*.json")):
            try:
                data = json.loads(jf.read_text())
                for key in ["detected_topics", "questions_sample", "decisions_sample",
                            "actions_sample"]:
                    items = data.get(key, []) if isinstance(data.get(key), list) else []
                    for item in items:
                        if isinstance(item, dict):
                            texts.append(item.get("text", ""))
                        elif isinstance(item, str):
                            texts.append(item)
                if isinstance(data.get("detected_topics"), dict):
                    texts.extend(data["detected_topics"].keys())
            except Exception:
                continue
        return " ".join(texts)

    def _format_req_file(self, req: dict, date: str, meeting_type: str) -> str:
        """Format a requirement as a professional markdown document."""
        req_id = req.get("id", "REQ-???")
        title = req.get("title", "Untitled")
        category = req.get("category", "FUNCTIONAL")
        category_label = CATEGORY_LABELS.get(category, category)
        priority = req.get("priority", "P1")
        statement = req.get("statement", "")
        rationale = req.get("rationale", "")
        acceptance = req.get("acceptance_criteria", "To be defined.")
        source = req.get("source_speaker", "team discussion")
        concerns = req.get("related_concerns", [])

        concerns_md = ""
        if concerns:
            concerns_md = "\n".join(f"- {c}" for c in concerns)
        else:
            concerns_md = "None identified."

        return f"""# {req_id}: {title}

| Field | Value |
|-------|-------|
| **ID** | {req_id} |
| **Category** | {category_label} |
| **Priority** | {priority} |
| **Date Identified** | {date} |
| **Source Meeting** | {meeting_type} |
| **Source** | {source} |
| **Status** | draft |

## Requirement Statement

{statement}

## Rationale

{rationale}

## Acceptance Criteria

{acceptance}

## Related Concerns / Open Questions

{concerns_md}

## Traceability

- Jira Ticket: _pending auto-link_
- Architecture Decision: _pending_
- Test Coverage: _pending_

---
_Auto-generated by req_extractor agent on {date}_
"""
