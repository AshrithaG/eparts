# `qa/` — throwaway QA interfaces

Small, purpose-built interfaces whose only job is to let a **human** drive **one module in
isolation** and confirm it behaves as expected — instead of only reading the code or trusting
a green test suite.

The practice comes from the AI-tools coaching session with **Cory Gwin** (Senior Software
Engineer, GitHub / Copilot) on **2026-07-24**. From the session minutes:

> **Build Throwaway QA Interfaces:** Because code is now cheap to produce, it is practical to
> build small purpose-built interfaces solely for QA — tools that let a human interact with one
> module in isolation and confirm it behaves as expected, rather than only reading code. Cory
> clarified this means user interfaces, not additional agents.

These are deliberately cheap and disposable. They are not part of the product, not imported by
anything, and safe to delete.

---

## 1. `vtt_qa_server.py` — QA interface for `pipeline/vtt_processor.py`

### Run it

```bash
python3 qa/vtt_qa_server.py          # then open http://127.0.0.1:8777/
```

```bash
python3 qa/vtt_qa_server.py --check  # headless: parse every fixture, print a table, exit
```

Python 3.10+ (uses `X | Y` type syntax, same as the rest of `pipeline/`). Standard library only —
no pip installs, no network, no LLM, **no API key**. The tool is read-only: it never writes to the
repo. `--port N` if 8777 is taken.

### What it is

`pipeline/vtt_processor.py` is the front door of the ingestion pipeline: `parse_vtt()` turns a raw
Zoom VTT transcript into `MeetingData`, and `generate_offline_summary()` derives speaker stats,
topics, questions, decisions and action items from it without an LLM. Its output feeds
`pipeline/ingest.py` (meeting minutes) and the offline path in
`agents/requirements/transcript_parser.py`. If it silently drops turns, every downstream artifact
is quietly wrong.

The page is two panes:

- **Left** — the exact string handed to `parse_vtt(text, filename)`, in an editable textarea.
- **Right** — everything that comes back: turn count, speakers, words, duration, the resolved
  date, per-speaker stats, the full turn list with timestamps, the derived summary counters and
  samples, the `cleaned_text` that goes downstream, and the raw JSON.

Nothing is precomputed or cached. Every render is a live call into the module in the current
working tree, timed in milliseconds. Edit the left pane and press **Parse** (or ⌘/Ctrl + Enter)
to re-run. If the module raises, you get the traceback instead of a blank screen.

Two ways to load input:

- **Real transcript** — any of the 25 `.vtt` files under `transcripts/` and `coach_meetings/`.
- **Edge case** — 17 built-in synthetic fixtures (empty, whitespace, non-VTT prose, missing
  speaker labels, missing cue numbers, unknown speaker emails, malformed and out-of-order
  timestamps, CRLF, colons inside speech, single cue, and so on). Each one states in a caption
  what you should expect to see, so you can check the claim rather than guess.

### What a human should look for

1. **Every turn you can see on the left appears on the right**, attributed to the right person,
   with nothing silently dropped. Scroll both panes together on a real transcript.
2. **Speaker names resolve correctly.** An email should become the right display name, and a
   stranger's address should *not* become a teammate.
3. **Turn merging is justified.** Cues collapse only where the same speaker genuinely continues.
   Compare the "cues" count in the input stats against the turn count.
4. **Counts are consistent.** `total_words` equals the sum of per-speaker words, `pct_words` sums
   to ~100, duration is positive and plausible for the transcript length.
5. **Derived signals are believable.** If the input obviously contains questions, decisions or
   action items, the counters should not be zero — and vice versa.
6. **Degradation is graceful.** Empty, whitespace-only, non-VTT and malformed input should return
   an empty-ish result: no exception, and no fabricated turns.

The amber/green **harness observations** panel is heuristics from *this tool*, not from the
module. A flag means "go look at this", never "this is a bug". You decide by comparing the panes.

### Findings from the first QA pass (2026-07-27)

Recorded here because the point of the exercise is to find things. All four were found by
eyeballing input against output in this interface, and all four reproduce via `--check`. **None
has been fixed** — this directory does not touch `pipeline/`.

1. **`*.cc.vtt` files parse to nothing.** `parse_vtt()` skips the header by advancing until it
   finds a bare cue number, but Zoom's closed-caption exports have no cue numbers, so the scan
   consumes the whole file. `transcripts/GMT20260416-180324_Recording.cc.vtt` (21,553 chars, 196
   cues) yields **0 turns, 0 speakers, 0 words** with no error. Three such files sit in
   `transcripts/`. Reproduce: fixture *"Zoom .cc.vtt style"*, or load any `.cc.vtt` file.
   Mitigating factor: `batch_process()` defaults to `pattern="*.transcript.vtt"`, so the pipeline
   does not currently ingest these files — but nothing stops a caller passing `*.vtt`.
2. **Question detection never sees a question mark.** `generate_offline_summary()` splits each
   turn on `re.split(r'[.!?]+', ...)`, which removes the `?`, then tests `s.endswith("?")` —
   a branch that can never be true. Detection therefore relies entirely on the six hardcoded
   opening phrases (`should we`, `can we`, `how do`, …). Reproduce: fixture *"Ordinary questions
   ending in '?'"* — three unmistakable questions, `questions_found == 0`. Contrast with fixture
   *"Questions starting with stock phrases"*, which reports 3.
3. **Unknown emails are mapped onto real teammates.** `_resolve_speaker()` falls back to
   `if prefix in email` over `SPEAKER_MAP`, an unanchored substring test. `n@n.com` and `a@x.com`
   both resolve to **"Hrishik"**, because `"n"` and `"a"` appear inside
   `hrishikb@andrew.cmu.edu`. Attributing words to the wrong person corrupts the speaker stats
   that the program-health narrative rests on. Reproduce: fixture *"Unknown speaker email"*.
4. **Duration can go negative.** Duration is `last turn's end − first turn's start` with no
   ordering check; out-of-order cues give a negative value (fixture *"Out-of-order timestamps"*
   returns `-598s`, which `generate_offline_summary` then floor-divides into
   `duration_minutes = -10`). No real repo file trips this today.

Also worth a human's judgement rather than a defect claim: on
`transcripts/GMT20260122-191430_Recording.transcript.vtt`, 363 cues collapse into **17 turns**
across only 2 speakers. That is the intended merging behaviour meeting a transcript where Zoom
labelled speakers sparsely — plausible, but worth confirming against the raw file before trusting
the per-speaker word split.

### Limitations

- The harness exercises `parse_vtt()` and `generate_offline_summary()` only. The LLM-backed
  online path in `vtt_processor`'s docstring and in `transcript_parser.py` is **not** covered —
  it needs an API key.
- The "harness observations" are heuristics, not assertions. `--check` prints `WARN` counts but
  always exits 0 unless the module actually raises; it is a QA aid, not a CI gate.
- Binds to `127.0.0.1` only, and `/api/sample` refuses paths outside `transcripts/` and
  `coach_meetings/` and anything that is not a `.vtt`. It is still a local dev tool with no auth
  — do not expose it.
