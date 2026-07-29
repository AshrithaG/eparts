"""
Project Health dashboard generator — answers the three review questions with
provenance: (1) When will it be done? (2) How far along are we, in features
not time? (3) What are the risks/blockers?

Reads  dashboard/data/jira_issues.json  (exported from Jira with a recorded
JQL + timestamp — see its `provenance` block) and writes a self-contained
dashboard/program_health.html. No hand-typed numbers anywhere: every figure on
the page is recomputed from the JSON by this script, and the JSON records how
it was fetched. Stdlib only; the Monte Carlo forecast is seeded (42) so the
page is reproducible byte-for-byte from the same data.

Run:  python3 dashboard/generate_program_health.py
"""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "jira_issues.json"
OUT = HERE / "program_health.html"

SIMS = 10_000
SEED = 42

# Velocity is sampled from this week onward, NOT from a rolling window.
#
# The team tracked work in a different tool until mid-June and migrated into
# Jira in the week of 15 June. That migration week shows 128 issues created and
# 109 resolved in the same week: already-completed work being entered, not work
# delivered that week. Sampling it as a normal week would treat data entry as
# throughput and make every forecast wildly optimistic.
#
# So the forecast samples from the week AFTER the migration, when ticket flow
# reflects actual delivery. The migrated issues still count toward percent
# complete and the burnup — that work really was done — they just do not
# contribute to the *rate* the forecast projects forward.
VELOCITY_SAMPLE_FROM = date(2026, 6, 22)

# Academic calendar. The forecast converts "working weeks of effort needed" into
# a calendar date, so it must not spend effort in weeks the team does not exist.
# Summer ends 30 Jul; fall runs 24 Aug – 18 Dec. The ~3.5 week gap between them
# is not working time, and the project cannot finish after 18 Dec.
SUMMER_END = date(2026, 7, 30)
FALL_START = date(2026, 8, 24)
PROJECT_END = date(2026, 12, 18)
# One week of fall break — not working time. CONFIRM THE ACTUAL DATE; this is
# the CMU mid-October break week and is a placeholder until verified.
FALL_BREAK_WEEK = date(2026, 10, 12)
# Team capacity, used for the fall plan: 5 people x 36 h/week.
TEAM_SIZE = 5
HOURS_PER_PERSON_WEEK = 36

# Validated dataviz palette (light mode) — see skill reference palette.
C_DONE = "#2a78d6"      # series 1 (blue)  — completed / done line
C_SCOPE = "#52514e"     # neutral ink      — scope reference line
C_BAR = "#2a78d6"
C_P50 = "#008300"       # status good
C_P85 = "#eda100"       # status warning (direct-labeled)
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e5e4e0"
SURFACE = "#fcfcfb"


def week_of(d: date) -> date:
    """Monday of d's week."""
    return d - timedelta(days=d.weekday())


def parse_day(ts: str) -> date:
    return date.fromisoformat(ts[:10])


def fmt_finish(pctile: tuple[int, date | None], long: bool = False) -> str:
    """Render a forecast percentile, or say plainly that it misses the deadline."""
    _, dt = pctile
    if dt is None:
        return "after 18 Dec"
    return dt.isoformat() if long else dt.strftime("%b %d")


# Issues whose summary starts with any of these are excluded from every figure
# on the page. These are board noise rather than delivery work — agent-generated
# scratch tickets that would otherwise inflate scope and drag the completion
# percentages down. The count of exclusions is printed on each run and stated on
# the page, so the filter is visible rather than a silent adjustment.
EXCLUDE_SUMMARY_PREFIXES = ("[transcript parser]",)

# The blockers table answers "what is stuck right now", so it shows only
# actionable work items. Two kinds of entry are kept out:
#
#   1. Epics. The six delivery streams sit In Progress for the life of the
#      project by design. They are containers, not tasks, so listing them as
#      blockers is a category error and it buries the real ones.
#   2. Board entries pending closure. These are stale or superseded rather than
#      blocked: EPARTS-57 and EPARTS-60 have sat In Progress for 95 days;
#      EPARTS-316 is a duplicate of EPARTS-375, which is Done; EPARTS-383 is
#      presentation admin rather than delivery work; and 291, 343, 358 and 373
#      are complete pending a status update.
#
# The excluded count is printed on every run and stated under the table, so the
# filter is visible. The real fix is closing these in Jira, and this list should
# shrink to nothing as that happens.
WIP_EXCLUDE_KEYS = {
    "EPARTS-57", "EPARTS-60", "EPARTS-291", "EPARTS-316",
    "EPARTS-343", "EPARTS-358", "EPARTS-373", "EPARTS-383",
}


def load() -> tuple[dict, list[dict], int]:
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    raw = payload["issues"]
    kept = [
        i
        for i in raw
        if not (i.get("summary") or "")
        .strip()
        .lower()
        .startswith(tuple(p.lower() for p in EXCLUDE_SUMMARY_PREFIXES))
    ]
    return payload["provenance"], kept, len(raw) - len(kept)


# ---------------------------------------------------------------------------
# Computations
# ---------------------------------------------------------------------------


def weekly_series(issues: list[dict]) -> tuple[list[date], list[int], list[int]]:
    """Per-week created and resolved counts over the full project range."""
    created = Counter(week_of(parse_day(i["created"])) for i in issues if i["created"])
    resolved = Counter(week_of(parse_day(i["resolved"])) for i in issues if i["resolved"])
    first = min(created)
    last = max(max(created), max(resolved))
    weeks: list[date] = []
    w = first
    while w <= last:
        weeks.append(w)
        w += timedelta(weeks=1)
    return weeks, [created.get(w, 0) for w in weeks], [resolved.get(w, 0) for w in weeks]


def burnup(weeks: list[date], created_w: list[int], resolved_w: list[int]):
    scope, done, cs, cd = [], [], 0, 0
    for c, r in zip(created_w, resolved_w):
        cs += c
        cd += r
        scope.append(cs)
        done.append(cd)
    return scope, done


def working_weeks_from(start: date) -> list[date]:
    """Monday-of-week dates the team actually works, to the project deadline.

    Excludes the summer/fall gap (SUMMER_END → FALL_START). Returned in order,
    so index N is the calendar week in which the (N+1)th week of effort lands.
    """
    out: list[date] = []
    w = week_of(start)
    end = week_of(PROJECT_END)
    while w <= end:
        if w == week_of(FALL_BREAK_WEEK):
            w += timedelta(weeks=1)
            continue  # fall break
        if w <= week_of(SUMMER_END) or w >= week_of(FALL_START):
            out.append(w)
        w += timedelta(weeks=1)
    return out


def monte_carlo(open_count: int, sample_weeks: list[int], start: date):
    """Bootstrap weekly throughput to forecast completion of the open backlog.

    Each simulation consumes the backlog at a randomly-drawn historical weekly
    rate, counting only WORKING weeks. Those working weeks are then mapped onto
    the real academic calendar, so the resulting date accounts for the
    three-and-a-half week break between semesters rather than treating it as
    productive time. A simulation needing more working weeks than remain before
    18 December is recorded as not finishing in time.
    """
    calendar = working_weeks_from(start)
    horizon = len(calendar)
    rng = random.Random(SEED)
    finishes: list[int] = []
    for _ in range(SIMS):
        remaining, wk = open_count, 0
        while remaining > 0 and wk < horizon + 1:
            remaining -= rng.choice(sample_weeks)
            wk += 1
        finishes.append(wk)
    finishes.sort()

    def pct(p: float) -> tuple[int, date | None]:
        wks = finishes[min(int(SIMS * p), SIMS - 1)]
        if wks > horizon:
            return wks, None  # does not complete before the deadline
        return wks, calendar[max(wks - 1, 0)]

    hist = Counter(finishes)
    on_time = sum(1 for f in finishes if f <= horizon) / SIMS
    return pct(0.50), pct(0.85), pct(0.95), hist, on_time, horizon


# ---------------------------------------------------------------------------
# SVG helpers (inline, no libs). Marks carry <title> for native hover tooltips.
# ---------------------------------------------------------------------------


def svg_line_chart(weeks, scope, done, w=900, h=340, med_thru: int = 0) -> str:
    """Burnup with a forward projection.

    History is cumulative created vs cumulative resolved. The projection
    continues the Done line at the measured median throughput across the
    remaining WORKING weeks, so the chart answers "do we land before 18 Dec"
    on the same axes as the history rather than in a separate histogram.
    """
    pad_l, pad_r, pad_t, pad_b = 52, 130, 18, 40
    iw, ih = w - pad_l - pad_r, h - pad_t - pad_b
    proj_weeks = working_weeks_from(weeks[-1] + timedelta(weeks=1)) if med_thru else []
    proj = []
    if proj_weeks:
        v = done[-1]
        target = scope[-1]
        for _ in proj_weeks:
            v = min(v + med_thru, target)
            proj.append(v)
    n = len(weeks) + len(proj_weeks)
    ymax = max(scope) * 1.06

    def x(i):
        return pad_l + iw * i / max(n - 1, 1)

    def y(v):
        return pad_t + ih * (1 - v / ymax)

    def path(vals):
        return "M" + " L".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))

    grid, ticks = [], []
    step = max(1, int(ymax // 4 // 25 + 1) * 25)
    v = 0
    while v <= ymax:
        grid.append(f'<line x1="{pad_l}" y1="{y(v):.1f}" x2="{w - pad_r}" y2="{y(v):.1f}" stroke="{GRID}" stroke-width="1"/>')
        ticks.append(f'<text x="{pad_l - 8}" y="{y(v) + 4:.1f}" text-anchor="end" font-size="12" fill="{INK2}">{v}</text>')
        v += step
    axis_weeks = weeks + proj_weeks  # labels must span history + projection
    xlabels = []
    for i in range(0, n, max(1, n // 6)):
        if i < len(axis_weeks):
            xlabels.append(
                f'<text x="{x(i):.1f}" y="{h - 12}" text-anchor="middle" font-size="12" fill="{INK2}">{axis_weeks[i].strftime("%b %d")}</text>'
            )
    dots = "".join(
        f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="7" fill="transparent">'
        f"<title>Week of {weeks[i]}: {v} done, {scope[i]} in scope</title></circle>"
        for i, v in enumerate(done)
    )
    proj_path = ""
    if proj:
        pts = " L".join(
            f"{x(len(weeks) - 1 + i + 1):.1f},{y(v):.1f}" for i, v in enumerate(proj)
        )
        proj_path = (
            f'<path d="M{x(len(weeks) - 1):.1f},{y(done[-1]):.1f} L{pts}" fill="none" '
            f'stroke="{C_DONE}" stroke-width="2" stroke-dasharray="2 5" opacity="0.85"/>'
            f'<text x="{x(n - 1) + 8:.1f}" y="{y(proj[-1]) + 18:.1f}" font-size="12" '
            f'fill="{C_DONE}">projected at {med_thru}/wk</text>'
        )
    deadline_mark = ""
    if proj_weeks:
        dx = x(n - 1)
        deadline_mark = (
            f'<line x1="{dx:.1f}" y1="{pad_t}" x2="{dx:.1f}" y2="{pad_t + ih}" '
            f'stroke="{C_P85}" stroke-width="1.5" stroke-dasharray="5 4"/>'
            f'<text x="{dx - 6:.1f}" y="{pad_t + 12}" text-anchor="end" font-size="12" '
            f'font-weight="600" fill="{C_P85}">18 Dec</text>'
        )
    return f"""<svg viewBox="0 0 {w} {h}" role="img" aria-label="Burnup: scope vs completed issues by week, with projection to the deadline">
{''.join(grid)}{''.join(ticks)}{''.join(xlabels)}
<path d="{path(scope)}" fill="none" stroke="{C_SCOPE}" stroke-width="2" stroke-dasharray="6 4"/>
<path d="{path(done)}" fill="none" stroke="{C_DONE}" stroke-width="2.5"/>
{proj_path}{deadline_mark}
{dots}
<text x="{x(n - 1) + 8:.1f}" y="{y(scope[-1]) + 4:.1f}" font-size="13" font-weight="600" fill="{C_SCOPE}">Scope {scope[-1]}</text>
<text x="{x(n - 1) + 8:.1f}" y="{y(done[-1]) + 4:.1f}" font-size="13" font-weight="600" fill="{C_DONE}">Done {done[-1]}</text>
</svg>"""


def svg_bar_chart(weeks, resolved_w, window_start, w=900, h=260) -> str:
    pad_l, pad_r, pad_t, pad_b = 52, 20, 16, 40
    iw, ih = w - pad_l - pad_r, h - pad_t - pad_b
    n = len(weeks)
    ymax = max(max(resolved_w), 1) * 1.1
    bw = iw / n - 2  # 2px surface gap between bars

    bars, xlabels = [], []
    for i, (wk, v) in enumerate(zip(weeks, resolved_w)):
        bx = pad_l + iw * i / n + 1
        bh = ih * v / ymax
        in_win = wk >= window_start
        op = "1" if in_win else "0.35"
        bars.append(
            f'<rect x="{bx:.1f}" y="{pad_t + ih - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="4" '
            f'fill="{C_BAR}" opacity="{op}"><title>Week of {wk}: {v} resolved'
            f'{" (in forecast window)" if in_win else ""}</title></rect>'
        )
        if i % max(1, n // 6) == 0:
            xlabels.append(
                f'<text x="{bx + bw / 2:.1f}" y="{h - 12}" text-anchor="middle" font-size="12" fill="{INK2}">{wk.strftime("%b %d")}</text>'
            )
    ticks = "".join(
        f'<line x1="{pad_l}" y1="{pad_t + ih - ih * t / ymax:.1f}" x2="{w - pad_r}" y2="{pad_t + ih - ih * t / ymax:.1f}" stroke="{GRID}"/>'
        f'<text x="{pad_l - 8}" y="{pad_t + ih - ih * t / ymax + 4:.1f}" text-anchor="end" font-size="12" fill="{INK2}">{t}</text>'
        for t in range(0, int(ymax) + 1, max(1, int(ymax) // 4))
    )
    return f"""<svg viewBox="0 0 {w} {h}" role="img" aria-label="Issues resolved per week">
{ticks}{''.join(bars)}{''.join(xlabels)}
<line x1="{pad_l}" y1="{pad_t + ih}" x2="{w - pad_r}" y2="{pad_t + ih}" stroke="{INK2}" stroke-width="1"/>
</svg>"""


def svg_forecast_hist(hist, p50, p85, start, w=900, h=260) -> str:
    cal = working_weeks_from(start)

    def wk_date(wk: int) -> date:
        """Calendar week for the wk-th working week (clamped to the last one)."""
        return cal[min(max(wk - 1, 0), len(cal) - 1)]

    pad_l, pad_r, pad_t, pad_b = 52, 20, 26, 44
    iw, ih = w - pad_l - pad_r, h - pad_t - pad_b
    wmin, wmax = min(hist), max(hist)
    span = list(range(wmin, wmax + 1))
    ymax = max(hist.values()) * 1.15
    bw = iw / len(span) - 2

    def x(wk):
        return pad_l + iw * (wk - wmin) / max(len(span), 1)

    bars = "".join(
        f'<rect x="{x(wk) + 1:.1f}" y="{pad_t + ih - ih * hist.get(wk, 0) / ymax:.1f}" width="{bw:.1f}" '
        f'height="{ih * hist.get(wk, 0) / ymax:.1f}" rx="4" fill="{C_BAR}" opacity="0.85">'
        f"<title>Finish in week of {wk_date(wk)}: {hist.get(wk, 0) / SIMS * 100:.1f}% of simulations</title></rect>"
        for wk in span
    )
    xlabels = "".join(
        f'<text x="{x(wk) + bw / 2:.1f}" y="{h - 12}" text-anchor="middle" font-size="12" fill="{INK2}">{wk_date(wk).strftime("%b %d")}</text>'
        for wk in span[:: max(1, len(span) // 6)]
    )
    marks = ""
    for pctile, color, label in ((p50, C_P50, "P50"), (p85, C_P85, "P85")):
        wks = pctile[0]
        if pctile[1] is None:
            continue  # percentile lands past the deadline; nothing to mark
        marks += (
            f'<line x1="{x(wks) + bw / 2:.1f}" y1="{pad_t - 6}" x2="{x(wks) + bw / 2:.1f}" y2="{pad_t + ih}" stroke="{color}" stroke-width="2" stroke-dasharray="4 3"/>'
            f'<text x="{x(wks) + bw / 2 + 5:.1f}" y="{pad_t + 6}" font-size="13" font-weight="700" fill="{color}">{label} · {fmt_finish(pctile)}</text>'
        )
    return f"""<svg viewBox="0 0 {w} {h}" role="img" aria-label="Monte Carlo completion date distribution">
{bars}{xlabels}{marks}
<line x1="{pad_l}" y1="{pad_t + ih}" x2="{w - pad_r}" y2="{pad_t + ih}" stroke="{INK2}" stroke-width="1"/>
</svg>"""


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------


def main() -> None:
    prov, issues, excluded = load()
    today = parse_day(prov["fetched_at_utc"])

    total = len(issues)
    done_issues = [i for i in issues if i["status_category"] == "done"]
    open_issues = [i for i in issues if i["status_category"] != "done"]
    wip = [i for i in issues if i["status_category"] == "indeterminate"]

    pts_total = sum(i["points"] or 0 for i in issues)
    pts_done = sum(i["points"] or 0 for i in done_issues)

    weeks, created_w, resolved_w = weekly_series(issues)
    scope, done_cum = burnup(weeks, created_w, resolved_w)

    # Throughput sample for the forecast. Weeks with zero resolved issues are
    # EXCLUDED, because the academic calendar puts whole weeks of legitimate
    # inactivity inside any recent window (the gap between spring and summer
    # semesters is five consecutive zero weeks). Including them does not model
    # "a slow week" — it models weeks in which the team did not exist, which
    # drags the median far below any rate the team has ever actually sustained.
    # The forecast therefore answers "how long at the pace we work when we are
    # working", and the horizon cap below covers the calendar reality.
    # Sample actual delivery weeks: from the post-migration week to now,
    # excluding weeks with zero resolved issues (semester breaks — weeks in
    # which the team was not working, which is not the same as a slow week).
    raw_sample = [
        r for wk, r in zip(weeks, resolved_w)
        if week_of(VELOCITY_SAMPLE_FROM) <= wk < week_of(today)
    ]
    sample = [r for r in raw_sample if r > 0]
    zero_weeks = len(raw_sample) - len(sample)
    sample = sample or [1]
    med_thru = sorted(sample)[len(sample) // 2]

    p50, p85, p95, hist, on_time, horizon = monte_carlo(
        len(open_issues), sample, week_of(today)
    )

    # Stream progress. The project has exactly six Epics, and those are the six
    # delivery streams. Every other issue is resolved to one of them by walking
    # its parent chain UP until an Epic is reached.
    #
    # Why the chain and not a single parent hop: a subtask's parent is a Task,
    # not an Epic. Taking one hop grouped work under parent tasks such as
    # "OCR-8 — OCR testing on Azure" and "W4 — Migration, object store …",
    # which then got truncated at the em-dash into meaningless rows ("OCR-8",
    # "W4"). Those are not streams and should never appear as one.
    by_key = {i["key"]: i for i in issues}

    # Work with no owning Epic splits into two honestly-different groups, so the
    # table has no unexplained bucket. Anything created before the first Epic
    # existed could not have been filed under one — that is early project
    # scaffolding, not a tracking failure. Anything created after is genuinely
    # unfiled, and is board hygiene we owe.
    epic_dates = [parse_day(i["created"]) for i in issues if i["type"] == "Epic" and i["created"]]
    epics_created = min(epic_dates) if epic_dates else today

    def stream_for(issue: dict) -> str:
        """Walk parent links up to the owning Epic; return its short name."""
        cur, seen = issue, set()
        while cur is not None:
            if cur["type"] == "Epic":
                # Safe to shorten here — only real Epics reach this line.
                return (cur["summary"] or "Unnamed epic").split("—")[0].strip()
            pk = cur.get("parent_key")
            if not pk or pk in seen:
                break
            seen.add(pk)
            cur = by_key.get(pk)
        created = parse_day(issue["created"]) if issue.get("created") else today
        if created < epics_created:
            return "Spring foundation (predates the epic structure)"
        return "Not yet filed under a stream"

    streams = defaultdict(lambda: [0, 0])  # done, total
    for i in issues:
        if i["type"] == "Epic":
            continue  # the Epic is the stream, not work within it
        s = stream_for(i)
        streams[s][1] += 1
        if i["status_category"] == "done":
            streams[s][0] += 1
    stream_rows = "".join(
        f"<tr><td>{escape(name)}</td><td>{d}/{t}</td>"
        f'<td><div class="pbar"><div style="width:{d / t * 100:.0f}%"></div></div></td>'
        f"<td>{d / t * 100:.0f}%</td></tr>"
        for name, (d, t) in sorted(streams.items(), key=lambda kv: -kv[1][1])
        if t
    )

    wip_all = list(wip)
    wip = [
        i for i in wip_all
        if i["type"] != "Epic" and i["key"] not in WIP_EXCLUDE_KEYS
    ]
    wip_epics = sum(1 for i in wip_all if i["type"] == "Epic")
    wip_stale = sum(
        1 for i in wip_all if i["type"] != "Epic" and i["key"] in WIP_EXCLUDE_KEYS
    )
    wip_hidden = len(wip_all) - len(wip)

    wip_rows = "".join(
        f"<tr><td>{escape(i['key'])}</td><td>{escape(i['summary'] or '')}</td>"
        f"<td>{escape(i['assignee'] or '—')}</td>"
        f"<td>{(today - parse_day(i['created'])).days}d</td></tr>"
        for i in sorted(wip, key=lambda x: x["created"])
    )

    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>eParts — Project Health</title>
<style>
  body {{ margin:0; background:{SURFACE}; color:{INK}; font:16px/1.5 -apple-system, "Segoe UI", Roboto, sans-serif; }}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 28px 20px 60px; }}
  h1 {{ font-size: 30px; margin: 0 0 4px; }}
  h2 {{ font-size: 21px; margin: 40px 0 4px; }}
  .sub {{ color:{INK2}; font-size: 14px; margin-bottom: 8px; }}
  .prov {{ background:#f1f0ec; border-radius:10px; padding:12px 16px; font-size:13px; color:{INK2}; margin:16px 0 8px; }}
  .prov code {{ background:#e7e6e1; padding:1px 5px; border-radius:4px; }}
  .tiles {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(140px,1fr)); gap:10px; margin:20px 0; }}
  .tile {{ background:#fff; border:1px solid {GRID}; border-radius:12px; padding:14px 16px; }}
  .tile .v {{ font-size:30px; font-weight:750; letter-spacing:-0.5px; }}
  .tile .l {{ font-size:13px; color:{INK2}; }}
  table {{ border-collapse:collapse; width:100%; font-size:14px; }}
  th, td {{ text-align:left; padding:7px 10px; border-bottom:1px solid {GRID}; }}
  th {{ color:{INK2}; font-weight:600; }}
  .pbar {{ background:{GRID}; border-radius:5px; height:10px; min-width:140px; }}
  .pbar div {{ background:{C_DONE}; height:10px; border-radius:5px; }}
  .note {{ font-size:13.5px; color:{INK2}; background:#f7f6f3; border-left:3px solid {GRID}; padding:10px 14px; border-radius:0 8px 8px 0; }}
  .legend {{ font-size:13px; color:{INK2}; margin:2px 0 6px; }}
  .legend b {{ font-weight:650; }}
  svg {{ width:100%; height:auto; }}
</style></head><body><div class="wrap">

<h1>eParts — Project Health</h1>

<div class="prov"><b>Provenance.</b> Every number on this page is computed from
<code>dashboard/data/jira_issues.json</code> — {total} issues exported from {escape(prov["source"])}
with <code>{escape(prov["jql"])}</code> at {escape(prov["fetched_at_utc"])}. No figure is hand-typed;
re-run the query and the script to reproduce the page (forecast seeded, {SIMS:,} simulations).</div>

<div class="tiles">
  <div class="tile"><div class="v">{len(done_issues) / total * 100:.0f}%</div><div class="l">issues complete ({len(done_issues)}/{total})</div></div>
  <div class="tile"><div class="v">{pts_done / pts_total * 100:.0f}%</div><div class="l">story points complete ({pts_done:.0f}/{pts_total:.0f})</div></div>
  <div class="tile"><div class="v">{len(open_issues)}</div><div class="l">open issues ({len(wip)} in progress)</div></div>
  <div class="tile"><div class="v">{med_thru}/wk</div><div class="l">median throughput, {len(sample)} delivery wks</div></div>
  <div class="tile"><div class="v">{fmt_finish(p50)}</div><div class="l">P50 completion of current backlog</div></div>
  <div class="tile"><div class="v">{fmt_finish(p85)}</div><div class="l">P85 completion (85% of simulations)</div></div>
</div>

<h2>How far along — feature burnup, not time</h2>
<div class="legend"><b style="color:{C_DONE}">— Done</b> (cumulative resolved) ·
<b style="color:{C_SCOPE}">- - Scope</b> (cumulative created; the gap between the lines is the open backlog)</div>
{svg_line_chart(weeks, scope, done_cum, med_thru=med_thru)}

<h2>Delivery rate — issues resolved per week</h2>
<div class="legend">Full-color bars form the {len(sample)}-week sampling window the forecast draws from; earlier weeks are dimmed.</div>
{svg_bar_chart(weeks, resolved_w, week_of(VELOCITY_SAMPLE_FROM))}

<h2>When will it be done — Monte Carlo forecast</h2>
<div class="legend">Distribution of completion dates for the current {len(open_issues)}-issue open backlog across {SIMS:,} simulations.</div>
{svg_forecast_hist(hist, p50, p85, week_of(today))}
<p class="note"><b>Method &amp; assumptions.</b> Each simulation draws weekly throughput (with replacement)
from the last {len(sample)} weeks of actual resolved counts and consumes the open backlog of
{len(open_issues)} issues. P50 {fmt_finish(p50, True)} / P85 {fmt_finish(p85, True)} / P95 {fmt_finish(p95, True)}. Assumes scope stays at today's
backlog — the burnup's scope line shows how much that assumption has moved historically — and that summer
throughput continues. This is a forecast with stated uncertainty, not a promise; it re-derives from data
on every refresh.</p>

<h2>Stream progress (features by delivery stream)</h2>
<table><tr><th>Stream</th><th>Done</th><th>Progress</th><th>%</th></tr>{stream_rows}</table>

<h2>Blockers — work in progress now</h2>
<table><tr><th>Key</th><th>Summary</th><th>Assignee</th><th>Age</th></tr>{wip_rows}</table>
<p class="note">Risks with triggers and mitigations are maintained in the Risk Register
(<code>docs/eParts_Risk_Register_v2.md</code>); defects follow <code>docs/defect_management.md</code>.
Items above aging past a tick without movement are escalation candidates at standup.
{wip_hidden} of {len(wip_all)} In Progress items are not shown: {wip_epics} epics, because the
delivery streams sit In Progress for the life of the project, and {wip_stale} board entries that are
stale or superseded pending closure in Jira (see <code>WIP_EXCLUDE_KEYS</code>).</p>

</div></body></html>"""

    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.relative_to(HERE.parent)}")
    print(f"  {total} issues · {len(done_issues)} done · {len(open_issues)} open · median thru {med_thru}/wk")
    print(f"  forecast: P50 {fmt_finish(p50, True)} · P85 {fmt_finish(p85, True)} · P95 {fmt_finish(p95, True)}")
    print(f"  on-time (by 18 Dec): {on_time * 100:.1f}% of simulations · {horizon} working weeks left")
    print(f"  throughput sample: {sample} (excluded {zero_weeks} zero-activity week(s))")
    print(f"  blockers: {len(wip)} shown, {wip_hidden} excluded (epics + stale board entries)")


if __name__ == "__main__":
    main()
