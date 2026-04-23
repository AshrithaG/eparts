"""
Transcript Parser — extracts structured data from meeting transcripts.

Sends .vtt/.txt transcripts to Claude. Extracts: meeting date, attendees,
decisions, action items with owners, open questions, new requirements.
Output: structured JSON committed as markdown.

Triggered by: transcript upload (Google Drive poll or manual)
Outputs: parsed meeting minutes committed to /minutes/
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.transcript_parser")


class TranscriptParserAgent(BaseAgent):
    """
    Parses meeting transcripts into structured data using Claude.
    Produces meeting minutes in markdown format.
    """

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="transcript_parser", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        source = trigger.source
        metadata = trigger.metadata

        # Support both direct source path and pipeline context
        pipeline_ctx = metadata.get("pipeline_context", {})
        source_path = pipeline_ctx.get("source", source)

        transcript_path = Path(source_path)
        if not transcript_path.exists():
            return AgentResult(
                agent=self.name,
                success=False,
                errors=[f"Transcript not found: {source_path}"],
            )

        raw_text = transcript_path.read_text(encoding="utf-8")
        date = metadata.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        meeting_type = metadata.get("meeting_type", "client")

        # Clean VTT formatting if present
        cleaned = self._clean_vtt(raw_text)

        # Try Claude-powered extraction (online) or fall back to structural (offline)
        parsed = None
        if self._settings.anthropic_api_key:
            parsed = self._parse_with_claude(cleaned, date, meeting_type)

        if not parsed:
            parsed = self._parse_offline(raw_text, date, transcript_path.name)

        if not parsed:
            return AgentResult(
                agent=self.name,
                success=False,
                errors=["Failed to parse transcript"],
            )

        # Format as markdown
        minutes_md = self._format_minutes(parsed, date, meeting_type)

        # Commit to repo
        outputs = []
        bitbucket = self.mcp.get("bitbucket")
        if bitbucket:
            filename = f"minutes/{date}-{meeting_type}.md"
            result = bitbucket.commit_file(
                file_path=filename,
                content=minutes_md,
                message=f"Parsed minutes from {meeting_type} on {date}",
                agent_name=self.name,
            )
            if result.get("ok"):
                outputs.append(AgentOutput(
                    output_type="file_committed",
                    description=f"Meeting minutes committed: {filename}",
                    reference=filename,
                ))

        action_count = len(parsed.get("action_items", []))
        decision_count = len(parsed.get("decisions", []))
        req_count = len(parsed.get("new_requirements", []))
        mode = "online (Claude)" if self._settings.anthropic_api_key else "offline (structural)"

        outputs.append(AgentOutput(
            output_type="transcript_parsed",
            description=f"[{mode}] Extracted {action_count} action items, "
                       f"{decision_count} decisions, {req_count} new requirements",
            reference=str(transcript_path),
        ))

        # Deposit to shared wiki and emit cross-pipeline events
        if action_count > 0:
            self.emit("action_items_extracted", {
                "count": action_count,
                "meeting_date": date,
                "meeting_type": meeting_type,
                "source": str(transcript_path),
                "items": parsed.get("action_items", [])[:10],
            })
        if decision_count > 0:
            self.emit("decision_logged", {
                "count": decision_count,
                "meeting_date": date,
                "decisions": parsed.get("decisions", [])[:10],
            })
        self.wiki.put("meetings", f"{date}-{meeting_type}", {
            "date": date,
            "type": meeting_type,
            "source": str(transcript_path),
            "action_items": action_count,
            "decisions": decision_count,
            "new_requirements": req_count,
            "participants": parsed.get("attendees", []),
        }, agent=self.name, tags=[meeting_type, date])

        return AgentResult(
            agent=self.name,
            success=True,
            outputs=outputs,
            requires_human_review=False,
            data={
                "parsed_minutes": parsed,
                "transcript_cleaned": cleaned[:5000],
                "meeting_date": date,
                "meeting_type": meeting_type,
                "source_file": str(transcript_path),
            },
        )

    def _parse_offline(self, transcript: str, date: str, filename: str) -> dict | None:
        """Structural extraction without LLM — used when no API key is set."""
        from pipeline.vtt_processor import parse_vtt, generate_offline_summary
        meeting = parse_vtt(transcript, filename)
        summary = generate_offline_summary(meeting)

        decisions = [
            {"text": d["text"][:200], "context": f"said by {d['speaker']}"}
            for d in summary.get("decisions_sample", [])
        ]
        action_items = [
            {"text": a["text"][:200], "owner": a["speaker"], "deadline": ""}
            for a in summary.get("actions_sample", [])
        ]
        questions = [
            {"text": q["text"], "context": "", "assigned_to": q["speaker"]}
            for q in summary.get("questions_sample", [])
        ]

        return {
            "meeting_date": date,
            "meeting_type": "client",
            "attendees": summary.get("participants", []),
            "decisions": decisions,
            "action_items": action_items,
            "open_questions": questions,
            "new_requirements": [],
            "key_discussion_points": [
                f"Topics discussed: {', '.join(summary.get('detected_topics', {}).keys())}",
                f"Duration: {summary.get('duration_minutes', 0)} minutes",
                f"Total words: {summary.get('total_words', 0)} across {summary.get('total_turns', 0)} turns",
            ],
            "_analysis_mode": "offline",
            "_speaker_stats": summary.get("speaker_stats", {}),
        }

    def _clean_vtt(self, text: str) -> str:
        """Strip WebVTT timestamps and metadata, keeping only speech content."""
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("WEBVTT") or line.startswith("NOTE"):
                continue
            if re.match(r"^\d+$", line):
                continue
            if re.match(r"\d{2}:\d{2}:\d{2}\.\d{3}\s*-->", line):
                continue
            cleaned.append(line)
        return "\n".join(cleaned)

    def _parse_with_claude(self, transcript: str, date: str, meeting_type: str) -> dict | None:
        """Send transcript to Claude for structured extraction."""
        prompt = self.load_prompt(
            "transcript_parser.txt",
            transcript=transcript[:12000],
            date=date,
            meeting_type=meeting_type,
        )

        raw_response = self.call_claude(prompt)

        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            logger.error("Failed to parse Claude response as JSON")
            return None

    def _format_minutes(self, parsed: dict, date: str, meeting_type: str) -> str:
        """Format parsed transcript data as markdown minutes."""
        lines = [
            f"# Meeting Minutes — {date}",
            f"**Type:** {meeting_type}",
            f"**Attendees:** {', '.join(parsed.get('attendees', ['unknown']))}",
            "",
        ]

        if parsed.get("key_discussion_points"):
            lines.append("## Key Discussion Points")
            for point in parsed["key_discussion_points"]:
                lines.append(f"- {point}")
            lines.append("")

        if parsed.get("decisions"):
            lines.append("## Decisions")
            for d in parsed["decisions"]:
                lines.append(f"- **{d['text']}**")
                if d.get("context"):
                    lines.append(f"  - Context: {d['context']}")
            lines.append("")

        if parsed.get("action_items"):
            lines.append("## Action Items")
            for a in parsed["action_items"]:
                deadline = f" (due: {a['deadline']})" if a.get("deadline") else ""
                lines.append(f"- [ ] {a['text']} — **{a.get('owner', 'unassigned')}**{deadline}")
            lines.append("")

        if parsed.get("open_questions"):
            lines.append("## Open Questions")
            for q in parsed["open_questions"]:
                assigned = f" → {q['assigned_to']}" if q.get("assigned_to") else ""
                lines.append(f"- {q['text']}{assigned}")
            lines.append("")

        if parsed.get("new_requirements"):
            lines.append("## New Requirements Identified")
            for r in parsed["new_requirements"]:
                lines.append(f"- {r['text']} (source: {r.get('source', 'unknown')})")
            lines.append("")

        return "\n".join(lines)
