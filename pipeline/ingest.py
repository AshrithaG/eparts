"""
Batch Ingestion Pipeline — processes all VTT transcripts into structured outputs.

This is the entry point for the full transcript processing pipeline:
  1. VTT cleaning and speaker extraction
  2. Structural analysis (offline) or Claude-powered analysis (online)
  3. Meeting minutes generation (markdown)
  4. Metrics recording
  5. Output storage (minutes/ directory)

Run:  python -m pipeline.ingest [--transcripts-dir PATH] [--output-dir PATH]
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

from pipeline.vtt_processor import batch_process, MeetingData


def generate_minutes_md(meeting: MeetingData, summary: dict) -> str:
    """Generate markdown meeting minutes from processed data."""
    lines = [
        f"# Meeting Minutes — {summary['meeting_date']}",
        "",
        f"**Date:** {summary['meeting_date']}",
        f"**Duration:** {summary['duration_minutes']} minutes",
        f"**Participants:** {', '.join(summary['participants'])}",
        f"**Source:** `{meeting.filename}`",
        f"**Processed:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
        "## Participation",
        "",
        "| Speaker | Turns | Words | Share |",
        "|---------|-------|-------|-------|",
    ]
    for speaker, stats in summary["speaker_stats"].items():
        lines.append(f"| {speaker} | {stats['turns']} | {stats['words']} | {stats['pct_words']}% |")

    if summary["detected_topics"]:
        lines.extend(["", "## Topics Discussed", ""])
        for topic, relevance in summary["detected_topics"].items():
            bar = "█" * min(relevance, 10)
            lines.append(f"- **{topic}** {bar} (relevance: {relevance})")

    if summary["decisions_sample"]:
        lines.extend(["", "## Potential Decisions", ""])
        for i, d in enumerate(summary["decisions_sample"], 1):
            text = d["text"][:300].replace("\n", " ")
            lines.append(f"{i}. **[{d['speaker']}]** {text}")

    if summary["actions_sample"]:
        lines.extend(["", "## Potential Action Items", ""])
        for i, a in enumerate(summary["actions_sample"], 1):
            text = a["text"][:300].replace("\n", " ")
            lines.append(f"{i}. **[{a['speaker']}]** {text}")

    if summary["questions_sample"]:
        lines.extend(["", "## Questions Raised", ""])
        for q in summary["questions_sample"]:
            lines.append(f"- **[{q['speaker']}]** {q['text']}")

    lines.extend([
        "",
        "---",
        "",
        f"*Analysis mode: {summary['analysis_mode']}*",
        f"*Total: {summary['total_words']} words across {summary['total_turns']} speaker turns*",
    ])

    return "\n".join(lines)


def generate_cross_meeting_report(all_summaries: list[dict]) -> str:
    """Generate a cross-meeting analysis report."""
    lines = [
        "# eParts Client Meetings — Cross-Meeting Analysis",
        "",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Meetings analyzed:** {len(all_summaries)}",
        "",
        "---",
        "",
        "## Meeting Overview",
        "",
        "| Date | Duration | Participants | Words | Topics |",
        "|------|----------|-------------|-------|--------|",
    ]
    for s in all_summaries:
        topics = ", ".join(list(s["detected_topics"].keys())[:3])
        lines.append(
            f"| {s['meeting_date']} | {s['duration_minutes']}min | "
            f"{s['participant_count']} | {s['total_words']} | {topics} |"
        )

    # Aggregate stats
    total_words = sum(s["total_words"] for s in all_summaries)
    total_minutes = sum(s["duration_minutes"] for s in all_summaries)
    total_turns = sum(s["total_turns"] for s in all_summaries)
    all_speakers = set()
    for s in all_summaries:
        all_speakers.update(s["participants"])

    lines.extend([
        "",
        "## Aggregate Statistics",
        "",
        f"- **Total meeting time:** {total_minutes} minutes ({total_minutes / 60:.1f} hours)",
        f"- **Total words transcribed:** {total_words:,}",
        f"- **Total speaker turns:** {total_turns}",
        f"- **Unique participants:** {len(all_speakers)} ({', '.join(sorted(all_speakers))})",
        f"- **Average meeting length:** {total_minutes // len(all_summaries)} minutes",
        f"- **Average words per meeting:** {total_words // len(all_summaries):,}",
    ])

    # Topic frequency across meetings
    topic_freq: dict[str, int] = {}
    for s in all_summaries:
        for topic in s["detected_topics"]:
            topic_freq[topic] = topic_freq.get(topic, 0) + 1

    lines.extend(["", "## Topic Frequency Across Meetings", ""])
    for topic, freq in sorted(topic_freq.items(), key=lambda x: -x[1]):
        pct = freq / len(all_summaries) * 100
        bar = "█" * freq
        lines.append(f"- **{topic}**: {bar} ({freq}/{len(all_summaries)} meetings, {pct:.0f}%)")

    # Speaker participation across meetings
    speaker_meetings: dict[str, int] = {}
    speaker_total_words: dict[str, int] = {}
    for s in all_summaries:
        for speaker, stats in s["speaker_stats"].items():
            speaker_meetings[speaker] = speaker_meetings.get(speaker, 0) + 1
            speaker_total_words[speaker] = speaker_total_words.get(speaker, 0) + stats["words"]

    lines.extend([
        "",
        "## Speaker Participation",
        "",
        "| Speaker | Meetings | Total Words | Avg Words/Meeting |",
        "|---------|----------|-------------|-------------------|",
    ])
    for speaker in sorted(speaker_total_words, key=lambda x: -speaker_total_words[x]):
        meetings = speaker_meetings[speaker]
        words = speaker_total_words[speaker]
        avg = words // meetings
        lines.append(f"| {speaker} | {meetings} | {words:,} | {avg:,} |")

    lines.extend([
        "",
        "---",
        "",
        "*Generated by eParts Agentic SE System — offline structural analysis*",
    ])

    return "\n".join(lines)


def run(
    transcripts_dir: Path | None = None,
    output_dir: Path | None = None,
) -> dict:
    """Run the full ingestion pipeline."""
    t_dir = transcripts_dir or PROJECT_ROOT / "transcripts"
    o_dir = output_dir or PROJECT_ROOT / "minutes"
    o_dir.mkdir(parents=True, exist_ok=True)

    results = batch_process(t_dir)
    if not results:
        print("No .transcript.vtt files found")
        return {"meetings": 0}

    all_summaries = []

    for meeting, summary in results:
        # Save meeting minutes
        md = generate_minutes_md(meeting, summary)
        md_path = o_dir / f"{summary['meeting_date']}-client.md"
        md_path.write_text(md, encoding="utf-8")

        # Save raw summary JSON
        json_path = o_dir / f"{summary['meeting_date']}-client.json"
        json_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

        # Save cleaned transcript
        clean_path = o_dir / f"{summary['meeting_date']}-cleaned.md"
        clean_path.write_text(
            f"# Cleaned Transcript — {summary['meeting_date']}\n\n{meeting.cleaned_text}",
            encoding="utf-8",
        )

        all_summaries.append(summary)
        print(f"  Processed: {meeting.filename} → {md_path.name}")

    # Generate cross-meeting report
    report = generate_cross_meeting_report(all_summaries)
    report_path = o_dir / "cross-meeting-analysis.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"  Cross-meeting report: {report_path.name}")

    print(f"\nDone: {len(results)} meetings → {o_dir}/")
    return {
        "meetings": len(results),
        "output_dir": str(o_dir),
        "files_created": len(results) * 3 + 1,
    }


if __name__ == "__main__":
    transcripts = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    run(transcripts, output)
