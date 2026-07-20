"""
VTT Processor — cleans Zoom auto-transcripts into structured meeting data.

Handles the real-world messiness of Zoom VTT files:
  - Speaker identification from email addresses
  - Timestamp stripping and turn merging
  - Filler removal and text cleaning
  - Speaker turn consolidation (adjacent lines from same speaker)
  - Meeting metadata extraction (date, duration, participants)

Two output modes:
  - Offline: structural extraction without LLM (speaker stats, turn counts, topics)
  - Online: full Claude-powered extraction (decisions, action items, requirements)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Known team member mapping (CMU email → display name)
SPEAKER_MAP = {
    "hrishikb@andrew.cmu.edu": "Hrishik",
    "jaivards@andrew.cmu.edu": "Jaivard",
    "arjunnai@andrew.cmu.edu": "Arjun",
    "zhelianl@andrew.cmu.edu": "Liu",
    "JakeMonroe": "Jake (eParts)",
    "Clifford Huff": "Cliff (Mentor)",
    "Ashritha": "Ashritha",
    "Harsha Tummala": "Harsha (eParts)",
    "Cory Gwin": "Cory (Coach)",
    "Dennis Grinberg": "Dennis (Mentor)",
    "David Mine": "David (eParts)",
    "Ben": "Ben (UX Coach)",
    "Christian Kästner": "Christian (AI Coach)",
    "Christian Kaestner": "Christian (AI Coach)",
}

# Maps filenames → session metadata for sessions where Zoom couldn't distinguish speakers
SESSION_METADATA = {
    "GMT20260220-180425": {"coach": "Dennis (Mentor)", "type": "mentor", "topic": "Risk & Project Management"},
    "GMT20260220-222907": {"coach": "Christian (AI Coach)", "type": "ai_coach", "topic": "Measurement Theory, ML Model Selection, AI in SE"},
    "GMT20260224-190023": {"coach": "Ben (UX Coach)", "type": "ux_coach", "topic": "UX Integration & HITL Design"},
    "GMT20260224-220446": {"coach": "Cory (Coach)", "type": "ses_coach", "topic": "SES, Agent Feedback Loops, Code Organization"},
}

# Filler patterns to clean
FILLER_PATTERNS = [
    r"\b(um|uh|hmm|hm|yeah,?\s*yeah|like,?\s*you know)\b",
]


@dataclass
class SpeakerTurn:
    speaker: str
    speaker_raw: str
    start_time: str
    end_time: str
    text: str


@dataclass
class MeetingData:
    filename: str
    date: str
    duration_seconds: int
    speakers: list[str]
    speaker_stats: dict[str, dict[str, Any]]
    turns: list[SpeakerTurn]
    total_words: int
    cleaned_text: str
    meeting_type: str  # "client" or "coach"


def _parse_timestamp(ts: str) -> float:
    parts = ts.strip().split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return 0.0


def _resolve_speaker(raw: str) -> str:
    raw = raw.strip()
    if raw in SPEAKER_MAP:
        return SPEAKER_MAP[raw]
    # Try email prefix
    if "@" in raw:
        prefix = raw.split("@")[0]
        for email, name in SPEAKER_MAP.items():
            if prefix in email:
                return name
        return prefix.title()
    return raw


def _extract_date_from_filename(filename: str) -> str:
    match = re.search(r"GMT(\d{8})", filename)
    if match:
        d = match.group(1)
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return "unknown"


def parse_vtt(content: str, filename: str = "") -> MeetingData:
    """Parse a VTT file into structured MeetingData."""
    lines = content.strip().split("\n")

    turns: list[SpeakerTurn] = []
    current_speaker_raw = ""
    current_speaker = ""
    current_start = ""
    current_end = ""
    current_text_parts: list[str] = []

    i = 0
    # Skip WEBVTT header
    while i < len(lines) and not re.match(r"\d+\s*$", lines[i].strip()):
        i += 1

    while i < len(lines):
        line = lines[i].strip()

        # Sequence number
        if re.match(r"^\d+$", line):
            i += 1
            continue

        # Timestamp line
        ts_match = re.match(r"(\d[\d:,.]+)\s*-->\s*(\d[\d:,.]+)", line)
        if ts_match:
            start = ts_match.group(1).replace(",", ".")
            end = ts_match.group(2).replace(",", ".")
            i += 1

            # Text line(s) follow
            text_parts = []
            speaker_raw = ""
            while i < len(lines) and lines[i].strip() and not re.match(r"^\d+$", lines[i].strip()):
                text_line = lines[i].strip()
                # Check for speaker label
                speaker_match = re.match(r"^(.+?):\s*(.*)$", text_line)
                if speaker_match and not text_line.startswith("http"):
                    potential_speaker = speaker_match.group(1)
                    if "@" in potential_speaker or len(potential_speaker.split()) <= 3:
                        speaker_raw = potential_speaker
                        text_parts.append(speaker_match.group(2))
                    else:
                        text_parts.append(text_line)
                else:
                    text_parts.append(text_line)
                i += 1

            text = " ".join(text_parts).strip()
            if not text:
                continue

            resolved = _resolve_speaker(speaker_raw) if speaker_raw else current_speaker

            # Merge with previous turn if same speaker
            if resolved == current_speaker and current_text_parts:
                current_text_parts.append(text)
                current_end = end
            else:
                # Flush previous turn
                if current_text_parts and current_speaker:
                    turns.append(SpeakerTurn(
                        speaker=current_speaker,
                        speaker_raw=current_speaker_raw,
                        start_time=current_start,
                        end_time=current_end,
                        text=" ".join(current_text_parts),
                    ))
                current_speaker = resolved
                current_speaker_raw = speaker_raw
                current_start = start
                current_end = end
                current_text_parts = [text]

            continue

        i += 1

    # Flush last turn
    if current_text_parts and current_speaker:
        turns.append(SpeakerTurn(
            speaker=current_speaker,
            speaker_raw=current_speaker_raw,
            start_time=current_start,
            end_time=current_end,
            text=" ".join(current_text_parts),
        ))

    # Compute stats
    speakers = list(dict.fromkeys(t.speaker for t in turns))
    speaker_stats: dict[str, dict[str, Any]] = {}
    for speaker in speakers:
        speaker_turns = [t for t in turns if t.speaker == speaker]
        word_count = sum(len(t.text.split()) for t in speaker_turns)
        speaker_stats[speaker] = {
            "turns": len(speaker_turns),
            "words": word_count,
            "pct_words": 0,
        }
    total_words = sum(s["words"] for s in speaker_stats.values())
    for s in speaker_stats.values():
        s["pct_words"] = round(s["words"] / max(total_words, 1) * 100, 1)

    # Duration
    if turns:
        start_sec = _parse_timestamp(turns[0].start_time)
        end_sec = _parse_timestamp(turns[-1].end_time)
        duration = int(end_sec - start_sec)
    else:
        duration = 0

    # Build cleaned text
    cleaned_lines = []
    for t in turns:
        cleaned_lines.append(f"**{t.speaker}**: {t.text}")
    cleaned_text = "\n\n".join(cleaned_lines)

    return MeetingData(
        filename=filename,
        date=_extract_date_from_filename(filename),
        duration_seconds=duration,
        speakers=speakers,
        speaker_stats=speaker_stats,
        turns=turns,
        total_words=total_words,
        cleaned_text=cleaned_text,
        meeting_type="client",
    )


def generate_offline_summary(meeting: MeetingData) -> dict[str, Any]:
    """
    Generate a structural summary without LLM calls.
    Extracts what we can from text patterns alone.
    """
    all_text = " ".join(t.text for t in meeting.turns).lower()

    # Topic detection via keyword groups
    topic_keywords = {
        "ML/Model": ["ml", "model", "training", "bert", "semantic", "confidence", "threshold", "prediction"],
        "Architecture": ["architecture", "schema", "api", "endpoint", "database", "azure", "docker", "terraform"],
        "Data": ["data", "dataset", "label", "attributes", "pim", "staging", "categories"],
        "Project Mgmt": ["timeline", "sprint", "deadline", "sow", "milestone", "deliverable"],
        "Infrastructure": ["deployment", "cloud", "token", "chromadb", "vector", "infrastructure"],
        "Onboarding": ["onboarding", "access", "documentation", "teams", "communication"],
    }
    detected_topics = {}
    for topic, keywords in topic_keywords.items():
        hits = sum(1 for kw in keywords if kw in all_text)
        if hits >= 2:
            detected_topics[topic] = hits

    # Question detection
    questions = []
    for t in meeting.turns:
        sentences = re.split(r'[.!?]+', t.text)
        for s in sentences:
            s = s.strip()
            if s.endswith("?") or s.lower().startswith(("should we", "can we", "how do", "what if", "why don", "is there")):
                if len(s.split()) >= 4:
                    questions.append({"speaker": t.speaker, "text": s.strip()})

    # Decision-like patterns
    decision_patterns = [
        r"(?:we decided|let's go with|we'll use|decision is|agreed to|we're going with)",
        r"(?:I think we should|the plan is|we need to)",
    ]
    potential_decisions = []
    for t in meeting.turns:
        for pat in decision_patterns:
            if re.search(pat, t.text, re.IGNORECASE):
                potential_decisions.append({
                    "speaker": t.speaker,
                    "text": t.text[:200],
                })
                break

    # Action item patterns
    action_patterns = [
        r"(?:I'll|we'll|I will|we will|let me|going to|need to|should|can you|please)",
    ]
    potential_actions = []
    for t in meeting.turns:
        for pat in action_patterns:
            if re.search(pat, t.text, re.IGNORECASE) and len(t.text.split()) >= 5:
                potential_actions.append({
                    "speaker": t.speaker,
                    "text": t.text[:200],
                })
                break

    duration_min = meeting.duration_seconds // 60

    return {
        "meeting_date": meeting.date,
        "duration_minutes": duration_min,
        "participants": meeting.speakers,
        "participant_count": len(meeting.speakers),
        "total_words": meeting.total_words,
        "total_turns": len(meeting.turns),
        "speaker_stats": meeting.speaker_stats,
        "detected_topics": dict(sorted(detected_topics.items(), key=lambda x: -x[1])),
        "questions_found": len(questions),
        "questions_sample": questions[:10],
        "potential_decisions": len(potential_decisions),
        "decisions_sample": potential_decisions[:10],
        "potential_action_items": len(potential_actions),
        "actions_sample": potential_actions[:10],
        "analysis_mode": "offline (no LLM — structural extraction only)",
    }


def process_vtt_file(path: Path) -> tuple[MeetingData, dict]:
    """Process a single VTT file and return meeting data + summary."""
    content = path.read_text(encoding="utf-8")
    meeting = parse_vtt(content, path.name)
    summary = generate_offline_summary(meeting)
    return meeting, summary


def batch_process(
    directory: Path,
    pattern: str = "*.transcript.vtt",
) -> list[tuple[MeetingData, dict]]:
    """Process all VTT files in a directory."""
    results = []
    for vtt_file in sorted(directory.glob(pattern)):
        meeting, summary = process_vtt_file(vtt_file)
        results.append((meeting, summary))
    return results
