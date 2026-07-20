"""
Inbox processor — the CI entry point for the transcript pipeline.

Closes the "system on one laptop" operations gap: anyone on the team drops a
Zoom ``*.transcript.vtt`` into ``transcripts/inbox/`` (git push or GitHub web
upload) and CI does the rest — no orchestrator server, no local SQLite, no
manual trigger.

What it does:
  1. Canonicalize inbox filenames (strip Zoom's " (1)" download suffixes).
  2. Run the ingestion pipeline (pipeline.ingest) on the inbox files only,
     writing per-meeting minutes/JSON/cleaned-transcript into ``minutes/``.
  3. Move the processed VTTs from ``transcripts/inbox/`` into ``transcripts/``.
  4. Rebuild ``minutes/cross-meeting-analysis.md`` across ALL meetings to date.
  5. Write a run summary (markdown) for the pull-request body.

The GitHub Actions workflow (.github/workflows/transcript-pipeline.yml) then
opens a pull request with the generated artifacts. The PR review IS the human
gate: generated minutes are drafts until a person approves the merge.

Run:  python -m pipeline.process_inbox [--summary-file PATH]
Exit code 0 with "processed: 0" when the inbox is empty (safe no-op).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = PROJECT_ROOT / "transcripts" / "inbox"
TRANSCRIPTS_DIR = PROJECT_ROOT / "transcripts"
MINUTES_DIR = PROJECT_ROOT / "minutes"

from pipeline.ingest import generate_cross_meeting_report, run as run_ingest


def canonicalize(name: str) -> str:
    """Strip browser-download suffixes: 'X.transcript (1).vtt' -> 'X.transcript.vtt'."""
    return re.sub(r"\.transcript(?: \(\d+\))?\.vtt$", ".transcript.vtt", name)


def rebuild_cross_meeting_report() -> int:
    """Regenerate the cross-meeting analysis over every processed meeting."""
    summaries = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(MINUTES_DIR.glob("*-client.json"))
    ]
    if summaries:
        report = generate_cross_meeting_report(summaries)
        (MINUTES_DIR / "cross-meeting-analysis.md").write_text(report, encoding="utf-8")
    return len(summaries)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary-file",
        type=Path,
        default=None,
        help="Where to write the markdown run summary (for the PR body).",
    )
    args = parser.parse_args()

    inbox_files = sorted(INBOX_DIR.glob("*.vtt")) if INBOX_DIR.exists() else []
    transcript_files = [f for f in inbox_files if ".transcript" in f.name]
    other_files = [f for f in inbox_files if ".transcript" not in f.name]

    summary_lines = ["## Transcript pipeline run", ""]

    if not transcript_files:
        print("processed: 0 (inbox empty)")
        summary_lines.append("Inbox empty — nothing to process.")
        if args.summary_file:
            args.summary_file.write_text("\n".join(summary_lines), encoding="utf-8")
        return

    # Stage inbox files under canonical names so batch_process's
    # "*.transcript.vtt" glob matches regardless of download suffixes.
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        for f in transcript_files:
            shutil.copy2(f, stage / canonicalize(f.name))

        result = run_ingest(stage, MINUTES_DIR)

    # Archive processed VTTs out of the inbox into transcripts/.
    for f in transcript_files:
        target = TRANSCRIPTS_DIR / canonicalize(f.name)
        shutil.move(str(f), target)
    # Non-transcript VTTs (e.g. .cc.vtt) are archived alongside, unprocessed.
    for f in other_files:
        shutil.move(str(f), TRANSCRIPTS_DIR / f.name)

    total = rebuild_cross_meeting_report()

    summary_lines += [
        f"Processed **{result['meetings']}** transcript(s) from `transcripts/inbox/`:",
        "",
    ]
    summary_lines += [f"- `{canonicalize(f.name)}`" for f in transcript_files]
    summary_lines += [
        "",
        f"Artifacts written to `minutes/` (minutes + JSON + cleaned transcript per meeting).",
        f"Cross-meeting analysis rebuilt over **{total}** meetings to date.",
        "",
        "**These are agent-generated drafts.** Review the minutes for speaker",
        "attribution errors, missed decisions, and misclassified action items",
        "before merging — merging this PR is the human approval step.",
    ]

    if args.summary_file:
        args.summary_file.write_text("\n".join(summary_lines), encoding="utf-8")
    print(f"processed: {result['meetings']}, cross-meeting total: {total}")


if __name__ == "__main__":
    main()
