#!/usr/bin/env python3
"""
Throwaway QA interface for pipeline/vtt_processor.py

A tiny stdlib-only local web app that lets a human drive ONE module in isolation:
paste or load a VTT transcript on the left, see exactly what
`parse_vtt()` + `generate_offline_summary()` produce on the right.

Practice adopted from the AI-tools coaching session with Cory Gwin
(Senior Software Engineer, GitHub / Copilot), 2026-07-24:
"Build throwaway QA interfaces ... small purpose-built interfaces solely for QA
— tools that let a human interact with one module in isolation and confirm it
behaves as expected, rather than only reading code." (User interfaces, not agents.)

Run:
    python3 qa/vtt_qa_server.py            # serve UI on http://127.0.0.1:8777
    python3 qa/vtt_qa_server.py --check    # headless: parse every fixture + real files

No third-party dependencies. Read-only: this tool never writes to the repo.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.vtt_processor import (  # noqa: E402
    SPEAKER_MAP,
    parse_vtt,
    generate_offline_summary,
)

# Directories the UI is allowed to read sample transcripts from.
SAMPLE_DIRS = ["transcripts", "coach_meetings"]

DEFAULT_PORT = 8777


# --------------------------------------------------------------------------
# Synthetic edge-case fixtures — the point of the tool is that a human can
# click each of these and confirm the module degrades gracefully.
# --------------------------------------------------------------------------

FIXTURES: dict[str, dict[str, str]] = {
    "empty": {
        "label": "Empty input",
        "note": "Nothing at all. Expect 0 turns, no exception, duration 0.",
        "filename": "empty.vtt",
        "text": "",
    },
    "whitespace": {
        "label": "Whitespace only",
        "note": "Blank lines and spaces. Expect 0 turns, no exception.",
        "filename": "whitespace.vtt",
        "text": "   \n\n\t\n   \n",
    },
    "garbage": {
        "label": "Not a VTT file at all",
        "note": "Plain prose. Expect 0 turns rather than a crash or garbled turns.",
        "filename": "notes.txt",
        "text": "These are just my handwritten notes.\nNo timestamps, no cues.\nAshritha: said something.\n",
    },
    "happy_two_speakers": {
        "label": "Happy path — 2 speakers, 3 cues",
        "note": "Baseline. Expect 3 turns (no merge), correct name mapping, 6s duration.",
        "filename": "GMT20260724-190000_Recording.transcript.vtt",
        "text": (
            "WEBVTT\n\n"
            "1\n00:00:01.000 --> 00:00:03.000\nCory Gwin: Build throwaway QA interfaces.\n\n"
            "2\n00:00:03.500 --> 00:00:05.000\nAshritha: Interfaces, not agents. Got it.\n\n"
            "3\n00:00:05.500 --> 00:00:07.000\nCory Gwin: Right, a human should poke the module.\n"
        ),
    },
    "adjacent_merge": {
        "label": "Adjacent same-speaker cues (turn merging)",
        "note": "4 cues, same speaker throughout. Expect ONE merged turn spanning 00:00:01 -> 00:00:09.",
        "filename": "merge.transcript.vtt",
        "text": (
            "WEBVTT\n\n"
            "1\n00:00:01.000 --> 00:00:03.000\nAshritha: First fragment,\n\n"
            "2\n00:00:03.000 --> 00:00:05.000\nAshritha: second fragment,\n\n"
            "3\n00:00:05.000 --> 00:00:07.000\nAshritha: third fragment,\n\n"
            "4\n00:00:07.000 --> 00:00:09.000\nAshritha: and the last one.\n"
        ),
    },
    "no_cue_numbers": {
        "label": "Zoom .cc.vtt style — no cue numbers, no speaker labels",
        "note": (
            "This is the real shape of the four *.cc.vtt files in transcripts/. "
            "Watch the turn count carefully."
        ),
        "filename": "GMT20260724-190000_Recording.cc.vtt",
        "text": (
            "WEBVTT\n\n"
            "00:00:07.000 --> 00:00:09.000\nYeah, start it.\n\n"
            "00:00:09.000 --> 00:00:16.000\nSo I think we should use the offline path.\n\n"
            "00:00:16.000 --> 00:00:28.000\nAgreed to ship that this tick.\n"
        ),
    },
    "no_speaker_labels": {
        "label": "Cue numbers present, speaker labels missing",
        "note": "Expect: no speaker can be resolved, so turns are dropped. Confirm words == 0.",
        "filename": "unlabelled.transcript.vtt",
        "text": (
            "WEBVTT\n\n"
            "1\n00:00:01.000 --> 00:00:03.000\nSomeone says a thing.\n\n"
            "2\n00:00:03.000 --> 00:00:05.000\nSomeone else replies.\n"
        ),
    },
    "unknown_email": {
        "label": "Unknown speaker email (fuzzy name mapping)",
        "note": (
            "Speakers 'n@n.com' and 'a@x.com' are strangers. Check whether they are "
            "mapped onto real teammates."
        ),
        "filename": "strangers.transcript.vtt",
        "text": (
            "WEBVTT\n\n"
            "1\n00:00:01.000 --> 00:00:03.000\nn@n.com: Who am I supposed to be?\n\n"
            "2\n00:00:03.000 --> 00:00:05.000\na@x.com: And who am I?\n\n"
            "3\n00:00:05.000 --> 00:00:07.000\nsomebody.new@example.org: I am definitely not on the team.\n"
        ),
    },
    "questions_stock_phrases": {
        "label": "Questions starting with stock phrases",
        "note": (
            "All three open with a phrase the module explicitly looks for "
            "(\"should we\" / \"how do\" / \"can we\"). Expect questions_found == 3."
        ),
        "filename": "questions_stock.transcript.vtt",
        "text": (
            "WEBVTT\n\n"
            "1\n00:00:01.000 --> 00:00:03.000\nAshritha: Should we go with the offline extraction path?\n\n"
            "2\n00:00:03.000 --> 00:00:05.000\nCory Gwin: How do you plan to QA the parser itself?\n\n"
            "3\n00:00:05.000 --> 00:00:07.000\nAshritha: Can we just build a tiny interface for it?\n"
        ),
    },
    "questions_plain": {
        "label": "Ordinary questions ending in '?'",
        "note": (
            "Three unmistakable questions, none starting with a stock phrase. Compare "
            "questions_found against the three question marks you can see on the left."
        ),
        "filename": "questions_plain.transcript.vtt",
        "text": (
            "WEBVTT\n\n"
            "1\n00:00:01.000 --> 00:00:03.000\nAshritha: So Jay, do you want to go first?\n\n"
            "2\n00:00:03.000 --> 00:00:05.000\nCory Gwin: Where is the ingestion pipeline breaking today?\n\n"
            "3\n00:00:05.000 --> 00:00:07.000\nAshritha: Who owns the ETIM normalization work now?\n"
        ),
    },
    "decisions_actions": {
        "label": "Decisions and action items",
        "note": "Contains 'we decided', \"let's go with\", \"I'll\". Expect both counters non-zero.",
        "filename": "decisions.transcript.vtt",
        "text": (
            "WEBVTT\n\n"
            "1\n00:00:01.000 --> 00:00:04.000\nAshritha: We decided to keep the offline path as the default for CI.\n\n"
            "2\n00:00:04.000 --> 00:00:08.000\nCory Gwin: Let's go with a throwaway interface, and I'll review it next session.\n\n"
            "3\n00:00:08.000 --> 00:00:12.000\nAshritha: I will wire the QA page into the dashboard directory this week.\n"
        ),
    },
    "malformed_timestamps": {
        "label": "Malformed / mixed timestamps",
        "note": (
            "Cue 1 uses mm:ss, cue 2 uses comma decimals (SRT style), cue 3's arrow is broken. "
            "Expect no crash; check which cues survive and whether duration is sane."
        ),
        "filename": "malformed.transcript.vtt",
        "text": (
            "WEBVTT\n\n"
            "1\n01:02.500 --> 01:05.500\nAshritha: Two-part timestamp.\n\n"
            "2\n00:01:06,000 --> 00:01:09,000\nCory Gwin: Comma decimals.\n\n"
            "3\n00:01:10.000 -> 00:01:12.000\nAshritha: Single-arrow, not valid VTT.\n"
        ),
    },
    "reversed_time": {
        "label": "Out-of-order timestamps (negative duration)",
        "note": "Last cue ends BEFORE the first begins. Expect a negative or nonsense duration.",
        "filename": "reversed.transcript.vtt",
        "text": (
            "WEBVTT\n\n"
            "1\n00:10:00.000 --> 00:10:05.000\nAshritha: I was recorded late.\n\n"
            "2\n00:00:01.000 --> 00:00:02.000\nCory Gwin: I was recorded early.\n"
        ),
    },
    "colon_in_text": {
        "label": "Colons inside speech (false speaker labels)",
        "note": (
            "Lines contain colons that are NOT speaker labels (a URL, a ratio, a short phrase). "
            "Check whether phantom speakers appear."
        ),
        "filename": "colons.transcript.vtt",
        "text": (
            "WEBVTT\n\n"
            "1\n00:00:01.000 --> 00:00:03.000\nAshritha: The split is 80:20 for train and test.\n\n"
            "2\n00:00:03.000 --> 00:00:05.000\nhttps://example.com/docs: see the appendix.\n\n"
            "3\n00:00:05.000 --> 00:00:07.000\nNote to self: revisit this later.\n"
        ),
    },
    "crlf": {
        "label": "Windows line endings (CRLF)",
        "note": "Same as the happy path but with \\r\\n. Output should be identical, with no stray \\r.",
        "filename": "crlf.transcript.vtt",
        "text": (
            "WEBVTT\r\n\r\n"
            "1\r\n00:00:01.000 --> 00:00:03.000\r\nCory Gwin: Build throwaway QA interfaces.\r\n\r\n"
            "2\r\n00:00:03.500 --> 00:00:05.000\r\nAshritha: Interfaces, not agents. Got it.\r\n"
        ),
    },
    "no_gmt_filename": {
        "label": "Filename without a GMT date stamp",
        "note": "Date is derived from the filename only. Expect date == 'unknown'.",
        "filename": "team-sync.vtt",
        "text": (
            "WEBVTT\n\n"
            "1\n00:00:01.000 --> 00:00:03.000\nAshritha: Where does the meeting date come from?\n"
        ),
    },
    "single_cue": {
        "label": "Single cue",
        "note": "Smallest non-empty input. Expect 1 turn and a 2s duration.",
        "filename": "GMT20260724-190000_Recording.transcript.vtt",
        "text": "WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\nAshritha: Just the one line.\n",
    },
}


# --------------------------------------------------------------------------
# Core: run the module and package the result for the UI
# --------------------------------------------------------------------------

def list_samples() -> list[dict[str, Any]]:
    """Real VTT files in the repo that the UI can load."""
    out = []
    for d in SAMPLE_DIRS:
        base = REPO_ROOT / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.vtt")):
            rel = p.relative_to(REPO_ROOT).as_posix()
            try:
                size = p.stat().st_size
            except OSError:
                continue
            out.append({"id": rel, "label": rel, "bytes": size})
    return out


def read_sample(rel: str) -> str:
    """Read a sample file, refusing anything outside the allowed directories."""
    target = (REPO_ROOT / rel).resolve()
    allowed = [(REPO_ROOT / d).resolve() for d in SAMPLE_DIRS]
    if not any(str(target).startswith(str(a) + "/") for a in allowed):
        raise ValueError(f"path not allowed: {rel}")
    if target.suffix != ".vtt":
        raise ValueError(f"only .vtt files may be loaded: {rel}")
    return target.read_text(encoding="utf-8", errors="replace")


def _email_keys_for(name: str) -> list[str]:
    return [k for k, v in SPEAKER_MAP.items() if v == name]


def qa_flags(text: str, meeting, summary: dict) -> list[dict[str, str]]:
    """
    Heuristic observations produced by THIS HARNESS (not by the module) to draw
    a human's eye to output that looks wrong. Every flag is a prompt to go look
    at the input pane and judge for yourself — none of them is a verdict.
    """
    flags: list[dict[str, str]] = []
    cue_count = text.count("-->")
    stripped = text.strip()

    if stripped and not meeting.turns:
        flags.append({
            "level": "warn",
            "msg": f"Input is non-empty ({len(stripped)} chars, {cue_count} cue arrows) "
                   f"but 0 turns were produced. Silent total data loss?",
        })
    if cue_count and meeting.turns and len(meeting.turns) < cue_count:
        flags.append({
            "level": "info",
            "msg": f"{cue_count} cues collapsed into {len(meeting.turns)} turns. Expected when "
                   f"adjacent cues share a speaker — suspicious when they clearly do not.",
        })
    if "?" in text and summary.get("questions_found") == 0:
        flags.append({
            "level": "warn",
            "msg": "Input contains '?' but summary.questions_found == 0.",
        })
    if meeting.turns and meeting.duration_seconds <= 0:
        flags.append({
            "level": "warn",
            "msg": f"duration_seconds == {meeting.duration_seconds} with "
                   f"{len(meeting.turns)} turns.",
        })
    if meeting.turns and not meeting.total_words:
        flags.append({"level": "warn", "msg": "Turns exist but total_words == 0."})

    # Fuzzy email→name mapping: raw label is an email not in SPEAKER_MAP, yet it
    # resolved to a mapped teammate whose own address does not start with that prefix.
    seen = set()
    for t in meeting.turns:
        raw = (t.speaker_raw or "").strip()
        if not raw or "@" not in raw or raw in SPEAKER_MAP or raw in seen:
            continue
        seen.add(raw)
        prefix = raw.split("@")[0]
        if t.speaker in SPEAKER_MAP.values():
            keys = _email_keys_for(t.speaker)
            if not any(k.startswith(prefix) for k in keys):
                flags.append({
                    "level": "warn",
                    "msg": f"Unknown address '{raw}' was mapped to a known teammate "
                           f"'{t.speaker}' (substring match against {keys}).",
                })

    pct_total = round(sum(s["pct_words"] for s in meeting.speaker_stats.values()), 1)
    if meeting.speaker_stats and not (98.0 <= pct_total <= 102.0):
        flags.append({
            "level": "info",
            "msg": f"pct_words sums to {pct_total} (rounding, or a real accounting bug).",
        })
    if not flags:
        flags.append({"level": "ok", "msg": "No harness heuristics tripped. Still read the panes."})
    return flags


def run_module(text: str, filename: str) -> dict:
    """Call the module under test and capture everything, including failures."""
    t0 = time.perf_counter()
    try:
        meeting = parse_vtt(text, filename)
        summary = generate_offline_summary(meeting)
    except Exception:
        return {
            "ok": False,
            "error": traceback.format_exc(),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
    elapsed = round((time.perf_counter() - t0) * 1000, 2)

    return {
        "ok": True,
        "elapsed_ms": elapsed,
        "input_stats": {
            "chars": len(text),
            "lines": len(text.splitlines()),
            "cues": text.count("-->"),
        },
        "meeting": {
            "filename": meeting.filename,
            "date": meeting.date,
            "duration_seconds": meeting.duration_seconds,
            "speakers": meeting.speakers,
            "speaker_stats": meeting.speaker_stats,
            "total_words": meeting.total_words,
            "meeting_type": meeting.meeting_type,
            "turns": [
                {
                    "speaker": t.speaker,
                    "speaker_raw": t.speaker_raw,
                    "start_time": t.start_time,
                    "end_time": t.end_time,
                    "text": t.text,
                }
                for t in meeting.turns
            ],
            "cleaned_text": meeting.cleaned_text,
        },
        "summary": summary,
        "flags": qa_flags(text, meeting, summary),
    }


# --------------------------------------------------------------------------
# HTML (single page, embedded; matches the repo's dashboard house style)
# --------------------------------------------------------------------------

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QA — pipeline/vtt_processor.py</title>
<style>
  body { margin:0; background:#fcfcfb; color:#0b0b0b; font:16px/1.5 -apple-system,"Segoe UI",Roboto,sans-serif; }
  .wrap { max-width:1500px; margin:0 auto; padding:24px 20px 60px; }
  h1 { font-size:27px; margin:0 0 4px; }
  h2 { font-size:17px; margin:26px 0 6px; }
  h3 { font-size:14px; text-transform:uppercase; letter-spacing:.5px; color:#52514e; margin:20px 0 6px; }
  .sub { color:#52514e; font-size:14px; margin-bottom:10px; }
  code { background:#e7e6e1; padding:1px 5px; border-radius:4px; font-size:.9em; }
  .prov { background:#f1f0ec; border-radius:10px; padding:12px 16px; font-size:13px; color:#52514e; margin:14px 0; }
  .bar { display:flex; flex-wrap:wrap; gap:10px; align-items:center; background:#fff;
         border:1px solid #e5e4e0; border-radius:12px; padding:12px 14px; margin:14px 0; }
  .bar label { font-size:13px; color:#52514e; font-weight:600; }
  select, button { font:14px inherit; border-radius:8px; border:1px solid #d8d7d2; background:#fff;
                   padding:7px 10px; color:#0b0b0b; }
  select { max-width:340px; }
  button { cursor:pointer; }
  button.primary { background:#2a78d6; border-color:#2a78d6; color:#fff; font-weight:650; }
  button.primary:hover { background:#2168bd; }
  .cols { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:18px; align-items:start; }
  @media (max-width:1050px){ .cols { grid-template-columns:minmax(0,1fr); } }
  .panel { background:#fff; border:1px solid #e5e4e0; border-radius:12px; padding:14px 16px; }
  .panel > h2:first-child { margin-top:0; }
  textarea { width:100%; box-sizing:border-box; min-height:520px; resize:vertical;
             font:12.5px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;
             border:1px solid #e5e4e0; border-radius:8px; padding:10px; background:#fdfdfc; color:#0b0b0b; }
  .meta { font-size:12.5px; color:#52514e; margin:6px 0 0; }
  .tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(96px,1fr)); gap:8px; margin:4px 0 12px; }
  .tile { background:#f7f6f3; border:1px solid #e5e4e0; border-radius:10px; padding:9px 11px; }
  .tile .v { font-size:23px; font-weight:750; letter-spacing:-.5px; overflow-wrap:anywhere; }
  .tile .l { font-size:11.5px; color:#52514e; line-height:1.3; }
  table { border-collapse:collapse; width:100%; font-size:13px; }
  th,td { text-align:left; padding:5px 8px; border-bottom:1px solid #e5e4e0; vertical-align:top; }
  th { color:#52514e; font-weight:600; }
  td.num { text-align:right; font-variant-numeric:tabular-nums; }
  .pbar { background:#e5e4e0; border-radius:5px; height:9px; min-width:70px; }
  .pbar div { background:#2a78d6; height:9px; border-radius:5px; }
  .flag { font-size:13px; border-radius:0 8px 8px 0; padding:8px 12px; margin:6px 0; background:#f7f6f3;
          border-left:3px solid #e5e4e0; }
  .flag.warn { background:#fdf6e6; border-left-color:#eda100; }
  .flag.ok   { background:#f0f7ef; border-left-color:#008300; }
  .note { font-size:13px; color:#52514e; background:#f7f6f3; border-left:3px solid #e5e4e0;
          padding:9px 13px; border-radius:0 8px 8px 0; margin:8px 0; }
  .turns { max-height:340px; overflow:auto; border:1px solid #e5e4e0; border-radius:8px; }
  .turns table { font-size:12.5px; }
  .turns th { position:sticky; top:0; background:#f7f6f3; }
  .mono { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; white-space:nowrap; color:#52514e; }
  .empty { color:#8a8984; font-style:italic; font-size:13px; }
  pre { background:#f7f6f3; border:1px solid #e5e4e0; border-radius:8px; padding:10px;
        overflow:auto; max-height:340px; font-size:11.5px; margin:6px 0 0; }
  pre.err { background:#fdeeee; border-color:#e8bcbc; color:#8a1f1f; max-height:none; }
  details summary { cursor:pointer; font-size:13px; color:#2a78d6; font-weight:600; }
  ul.checks { font-size:13.5px; color:#52514e; padding-left:20px; margin:6px 0; }
  ul.checks li { margin:3px 0; }
</style></head><body><div class="wrap">

<h1>QA harness — <code>pipeline/vtt_processor.py</code></h1>
<div class="sub">Throwaway interface for driving one module in isolation ·
practice from the Cory Gwin coaching session, 2026-07-24</div>

<div class="prov"><b>What this is.</b> The left pane is the exact string handed to
<code>parse_vtt(text, filename)</code>; the right pane is everything that comes back from it and from
<code>generate_offline_summary(meeting)</code>. Nothing is precomputed and nothing is cached — every
render is a live call into the module in this working tree. No LLM, no network, no API key.
Edit the left pane and press <b>Parse</b> (or ⌘/Ctrl + Enter) to re-run.</div>

<div class="bar">
  <label for="sample">Real transcript</label>
  <select id="sample"><option value="">— pick a file —</option></select>
  <label for="fixture">Edge case</label>
  <select id="fixture"><option value="">— pick a fixture —</option></select>
  <label for="fname">filename=</label>
  <input id="fname" style="font:13px ui-monospace,Menlo,monospace;padding:7px 9px;border:1px solid #d8d7d2;border-radius:8px;width:330px">
  <button class="primary" id="run">Parse ⌘↵</button>
  <button id="clear">Clear</button>
</div>

<div id="fixnote"></div>

<div class="cols">
  <div class="panel">
    <h2>Input — raw VTT text</h2>
    <textarea id="input" spellcheck="false" placeholder="Paste VTT text here, or load a sample above."></textarea>
    <p class="meta" id="instats">—</p>
  </div>
  <div class="panel">
    <h2>Output — module return values</h2>
    <div id="out"><p class="empty">Load a sample or paste text, then press Parse.</p></div>
  </div>
</div>

<h2>What to look for when QA-ing</h2>
<ul class="checks">
  <li><b>Every speaker turn you can see on the left appears on the right</b>, attributed to the right person,
      with nothing silently dropped.</li>
  <li><b>Speaker names resolve correctly.</b> Emails should become the right display name; a stranger's
      address should not become a teammate.</li>
  <li><b>Turn merging is justified.</b> Cues collapse only when the same speaker really does continue.</li>
  <li><b>Counts are consistent.</b> total_words matches the sum of the per-speaker words; pct_words sums to ~100;
      duration is positive and plausible.</li>
  <li><b>Derived signals are believable.</b> If the input obviously contains questions, decisions or action items,
      the counters should not be zero — and vice versa.</li>
  <li><b>Degradation is graceful.</b> Empty, whitespace, non-VTT and malformed input should return an empty-ish
      result, not raise and not fabricate.</li>
</ul>
<p class="note">A red traceback panel means the module raised. Amber flags are heuristics from
<i>this harness</i>, not from the module — treat them as places to look, then decide for yourself
by comparing the two panes.</p>

<script>
const BOOT = __BOOTSTRAP__;
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

BOOT.samples.forEach(s => {
  const o = document.createElement('option');
  o.value = s.id; o.textContent = s.label + '  (' + (s.bytes/1024).toFixed(0) + ' KB)';
  $('sample').appendChild(o);
});
Object.entries(BOOT.fixtures).forEach(([k, f]) => {
  const o = document.createElement('option');
  o.value = k; o.textContent = f.label;
  $('fixture').appendChild(o);
});

function inStats() {
  const t = $('input').value;
  $('instats').textContent = t.length + ' chars · ' + t.split('\n').length + ' lines · '
    + (t.split('-->').length - 1) + ' cue arrows';
}
$('input').addEventListener('input', inStats);

function fmtDur(s) {
  if (s === 0) return '0s';
  const neg = s < 0; s = Math.abs(s);
  const m = Math.floor(s / 60), r = s % 60;
  return (neg ? '-' : '') + (m ? m + 'm ' : '') + r + 's';
}

function render(d) {
  if (!d.ok) {
    $('out').innerHTML = '<h3>Module raised an exception</h3><pre class="err">' + esc(d.error) + '</pre>';
    return;
  }
  const m = d.meeting, s = d.summary;
  let h = '';

  h += '<div class="tiles">'
    + tile(m.turns.length, 'turns')
    + tile(m.speakers.length, 'speakers')
    + tile(m.total_words, 'words')
    + tile(fmtDur(m.duration_seconds), 'duration')
    + tile(esc(m.date), 'date (from filename)')
    + tile(d.elapsed_ms + ' ms', 'module runtime')
    + '</div>';

  h += '<h3>Harness observations</h3>';
  d.flags.forEach(f => { h += '<div class="flag ' + f.level + '">' + esc(f.msg) + '</div>'; });

  h += '<h3>Speaker stats</h3>';
  if (!m.speakers.length) {
    h += '<p class="empty">No speakers resolved.</p>';
  } else {
    h += '<table><tr><th>speaker</th><th>raw label seen</th><th class="num">turns</th>'
      + '<th class="num">words</th><th>% words</th><th class="num"></th></tr>';
    m.speakers.forEach(sp => {
      const st = m.speaker_stats[sp] || {};
      const raws = [...new Set(m.turns.filter(t => t.speaker === sp).map(t => t.speaker_raw || '(none)'))];
      h += '<tr><td><b>' + esc(sp) + '</b></td><td class="mono">' + esc(raws.join(', ')) + '</td>'
        + '<td class="num">' + st.turns + '</td><td class="num">' + st.words + '</td>'
        + '<td><div class="pbar"><div style="width:' + Math.min(100, st.pct_words) + '%"></div></div></td>'
        + '<td class="num">' + st.pct_words + '%</td></tr>';
    });
    h += '</table>';
  }

  h += '<h3>Turns (' + m.turns.length + ')</h3>';
  if (!m.turns.length) {
    h += '<p class="empty">No turns produced.</p>';
  } else {
    h += '<div class="turns"><table><tr><th>#</th><th>start → end</th><th>speaker</th><th>text</th></tr>';
    m.turns.forEach((t, i) => {
      h += '<tr><td class="num">' + (i + 1) + '</td>'
        + '<td class="mono">' + esc(t.start_time) + ' → ' + esc(t.end_time) + '</td>'
        + '<td>' + esc(t.speaker) + '</td><td>' + esc(t.text) + '</td></tr>';
    });
    h += '</table></div>';
  }

  h += '<h3>Offline summary — derived signals</h3>';
  const topics = Object.entries(s.detected_topics || {});
  h += '<table>'
    + row('detected_topics', topics.length ? topics.map(([k, v]) => esc(k) + ' (' + v + ')').join(', ') : '<span class="empty">none</span>')
    + row('questions_found', s.questions_found)
    + row('potential_decisions', s.potential_decisions)
    + row('potential_action_items', s.potential_action_items)
    + row('participant_count', s.participant_count)
    + row('duration_minutes', s.duration_minutes)
    + row('analysis_mode', esc(s.analysis_mode))
    + '</table>';

  h += samples('questions_sample', s.questions_sample);
  h += samples('decisions_sample', s.decisions_sample);
  h += samples('actions_sample', s.actions_sample);

  h += '<h3>cleaned_text (fed to downstream agents)</h3>'
    + (m.cleaned_text ? '<pre>' + esc(m.cleaned_text) + '</pre>' : '<p class="empty">empty string</p>');

  h += '<h3>Raw return value</h3><details><summary>Show full JSON</summary><pre>'
    + esc(JSON.stringify({meeting: m, summary: s}, null, 2)) + '</pre></details>';

  $('out').innerHTML = h;
}
const tile = (v, l) => '<div class="tile"><div class="v">' + v + '</div><div class="l">' + l + '</div></div>';
const row = (k, v) => '<tr><td class="mono">' + k + '</td><td>' + v + '</td></tr>';
function samples(name, arr) {
  let h = '<h3>' + name + ' (' + ((arr || []).length) + ' shown)</h3>';
  if (!arr || !arr.length) return h + '<p class="empty">empty</p>';
  h += '<table>';
  arr.forEach(x => { h += '<tr><td style="white-space:nowrap"><b>' + esc(x.speaker) + '</b></td><td>' + esc(x.text) + '</td></tr>'; });
  return h + '</table>';
}

async function run() {
  const body = JSON.stringify({text: $('input').value, filename: $('fname').value});
  $('out').innerHTML = '<p class="empty">Running…</p>';
  try {
    const r = await fetch('/api/parse', {method: 'POST', headers: {'Content-Type': 'application/json'}, body});
    render(await r.json());
  } catch (e) {
    $('out').innerHTML = '<pre class="err">harness error: ' + esc(e) + '</pre>';
  }
}
$('run').onclick = run;
document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); run(); }
});
$('clear').onclick = () => {
  $('input').value = ''; $('fname').value = 'empty.vtt'; $('fixnote').innerHTML = '';
  $('sample').value = ''; $('fixture').value = ''; inStats(); run();
};

$('sample').onchange = async (e) => {
  const id = e.target.value; if (!id) return;
  $('fixture').value = '';
  $('fixnote').innerHTML = '<div class="note">Real repo file: <code>' + esc(id) + '</code></div>';
  const r = await fetch('/api/sample?id=' + encodeURIComponent(id));
  const j = await r.json();
  if (j.error) { $('out').innerHTML = '<pre class="err">' + esc(j.error) + '</pre>'; return; }
  $('input').value = j.text;
  $('fname').value = id.split('/').pop();
  inStats(); run();
};
$('fixture').onchange = (e) => {
  const k = e.target.value; if (!k) return;
  $('sample').value = '';
  const f = BOOT.fixtures[k];
  $('fixnote').innerHTML = '<div class="note"><b>' + esc(f.label) + '.</b> ' + esc(f.note) + '</div>';
  $('input').value = f.text; $('fname').value = f.filename;
  inStats(); run();
};

$('fixture').value = 'happy_two_speakers';
$('fixture').onchange({target: $('fixture')});
</script>
</div></body></html>
"""


# --------------------------------------------------------------------------
# HTTP plumbing
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "vtt-qa/1.0"

    def log_message(self, fmt, *args):  # quieter console
        sys.stderr.write("  %s\n" % (fmt % args))

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        u = urlparse(self.path)
        if u.path == "/":
            boot = json.dumps({"samples": list_samples(), "fixtures": FIXTURES})
            html = PAGE.replace("__BOOTSTRAP__", boot)
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        elif u.path == "/api/samples":
            self._json({"samples": list_samples()})
        elif u.path == "/api/sample":
            rel = (parse_qs(u.query).get("id") or [""])[0]
            try:
                self._json({"id": rel, "text": read_sample(rel)})
            except Exception as exc:
                self._json({"error": f"{type(exc).__name__}: {exc}"}, 400)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/parse":
            self._json({"error": "not found"}, 404)
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n) or b"{}")
        except Exception as exc:
            self._json({"ok": False, "error": f"bad request: {exc}"}, 400)
            return
        self._json(run_module(str(payload.get("text") or ""), str(payload.get("filename") or "")))


def serve(port: int) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"\n  QA harness for pipeline/vtt_processor.py")
    print(f"  repo root : {REPO_ROOT}")
    print(f"  samples   : {len(list_samples())} real .vtt files · {len(FIXTURES)} edge-case fixtures")
    print(f"\n  open ->  http://127.0.0.1:{port}/\n")
    print("  Ctrl-C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.\n")
    finally:
        httpd.server_close()


# --------------------------------------------------------------------------
# Headless mode — same code path, printable
# --------------------------------------------------------------------------

def check(real_limit: int = 3) -> int:
    """Run every fixture plus a few real files and print a one-line-per-case table."""
    buf = io.StringIO()
    hdr = f"{'case':44} {'cues':>5} {'turns':>6} {'spk':>4} {'words':>7} {'dur':>7} {'q':>3} {'dec':>4} {'act':>4}  flags"
    buf.write(hdr + "\n" + "-" * len(hdr) + "\n")
    rows = [(f"fixture:{k}", v["text"], v["filename"]) for k, v in FIXTURES.items()]
    for s in list_samples()[:real_limit]:
        rows.append((f"repo:{Path(s['id']).name[:37]}", read_sample(s["id"]), Path(s["id"]).name))

    worst = 0
    for name, text, fname in rows:
        d = run_module(text, fname)
        if not d["ok"]:
            buf.write(f"{name:44} RAISED\n")
            worst = 1
            continue
        m, s2 = d["meeting"], d["summary"]
        warn = sum(1 for f in d["flags"] if f["level"] == "warn")
        marks = ("WARN x%d" % warn) if warn else "ok"
        buf.write(
            f"{name:44} {d['input_stats']['cues']:>5} {len(m['turns']):>6} "
            f"{len(m['speakers']):>4} {m['total_words']:>7} {m['duration_seconds']:>6}s "
            f"{s2['questions_found']:>3} {s2['potential_decisions']:>4} "
            f"{s2['potential_action_items']:>4}  {marks}\n"
        )
    print(buf.getvalue())
    print("Legend: cues = '-->' occurrences in input; dur = duration_seconds; "
          "q/dec/act = questions_found / potential_decisions / potential_action_items.")
    print("WARN = a harness heuristic tripped (see the web UI for the message). "
          "Not necessarily a defect — a human decides.\n")
    return worst


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port (default {DEFAULT_PORT})")
    ap.add_argument("--check", action="store_true", help="run headless over all fixtures and exit")
    args = ap.parse_args()
    if args.check:
        return check()
    serve(args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
