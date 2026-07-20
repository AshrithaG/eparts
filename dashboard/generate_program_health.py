"""
Program Health dashboard generator — answers the three review questions with
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
THROUGHPUT_WINDOW_WEEKS = 10  # sampling window for the forecast (see method note)

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


def load() -> tuple[dict, list[dict]]:
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    return payload["provenance"], payload["issues"]


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


def monte_carlo(open_count: int, sample_weeks: list[int], start: date):
    """Bootstrap weekly throughput to forecast completion of the open backlog."""
    rng = random.Random(SEED)
    finishes: list[int] = []
    for _ in range(SIMS):
        remaining, wk = open_count, 0
        while remaining > 0 and wk < 520:
            remaining -= rng.choice(sample_weeks)
            wk += 1
        finishes.append(wk)
    finishes.sort()

    def pct(p: float) -> tuple[int, date]:
        wks = finishes[min(int(SIMS * p), SIMS - 1)]
        return wks, start + timedelta(weeks=wks)

    hist = Counter(finishes)
    return pct(0.50), pct(0.85), pct(0.95), hist


# ---------------------------------------------------------------------------
# SVG helpers (inline, no libs). Marks carry <title> for native hover tooltips.
# ---------------------------------------------------------------------------


def svg_line_chart(weeks, scope, done, w=900, h=340) -> str:
    pad_l, pad_r, pad_t, pad_b = 52, 130, 18, 40
    iw, ih = w - pad_l - pad_r, h - pad_t - pad_b
    n = len(weeks)
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
    xlabels = []
    for i in range(0, n, max(1, n // 6)):
        xlabels.append(
            f'<text x="{x(i):.1f}" y="{h - 12}" text-anchor="middle" font-size="12" fill="{INK2}">{weeks[i].strftime("%b %d")}</text>'
        )
    dots = "".join(
        f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="7" fill="transparent">'
        f"<title>Week of {weeks[i]}: {v} done, {scope[i]} in scope</title></circle>"
        for i, v in enumerate(done)
    )
    return f"""<svg viewBox="0 0 {w} {h}" role="img" aria-label="Burnup: scope vs completed issues by week">
{''.join(grid)}{''.join(ticks)}{''.join(xlabels)}
<path d="{path(scope)}" fill="none" stroke="{C_SCOPE}" stroke-width="2" stroke-dasharray="6 4"/>
<path d="{path(done)}" fill="none" stroke="{C_DONE}" stroke-width="2.5"/>
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
        f"<title>Finish in week of {start + timedelta(weeks=wk)}: {hist.get(wk, 0) / SIMS * 100:.1f}% of simulations</title></rect>"
        for wk in span
    )
    xlabels = "".join(
        f'<text x="{x(wk) + bw / 2:.1f}" y="{h - 12}" text-anchor="middle" font-size="12" fill="{INK2}">{(start + timedelta(weeks=wk)).strftime("%b %d")}</text>'
        for wk in span[:: max(1, len(span) // 6)]
    )
    marks = ""
    for (wks, dt), color, label in ((p50, C_P50, "P50"), (p85, C_P85, "P85")):
        marks += (
            f'<line x1="{x(wks) + bw / 2:.1f}" y1="{pad_t - 6}" x2="{x(wks) + bw / 2:.1f}" y2="{pad_t + ih}" stroke="{color}" stroke-width="2" stroke-dasharray="4 3"/>'
            f'<text x="{x(wks) + bw / 2 + 5:.1f}" y="{pad_t + 6}" font-size="13" font-weight="700" fill="{color}">{label} · {dt.strftime("%b %d")}</text>'
        )
    return f"""<svg viewBox="0 0 {w} {h}" role="img" aria-label="Monte Carlo completion date distribution">
{bars}{xlabels}{marks}
<line x1="{pad_l}" y1="{pad_t + ih}" x2="{w - pad_r}" y2="{pad_t + ih}" stroke="{INK2}" stroke-width="1"/>
</svg>"""


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------


def main() -> None:
    prov, issues = load()
    today = parse_day(prov["fetched_at_utc"])

    total = len(issues)
    done_issues = [i for i in issues if i["status_category"] == "done"]
    open_issues = [i for i in issues if i["status_category"] != "done"]
    wip = [i for i in issues if i["status_category"] == "indeterminate"]

    pts_total = sum(i["points"] or 0 for i in issues)
    pts_done = sum(i["points"] or 0 for i in done_issues)

    weeks, created_w, resolved_w = weekly_series(issues)
    scope, done_cum = burnup(weeks, created_w, resolved_w)

    window_start = week_of(today) - timedelta(weeks=THROUGHPUT_WINDOW_WEEKS)
    sample = [r for wk, r in zip(weeks, resolved_w) if window_start <= wk < week_of(today)]
    sample = sample or [1]
    med_thru = sorted(sample)[len(sample) // 2]

    p50, p85, p95, hist = monte_carlo(len(open_issues), sample, week_of(today))

    # Stream progress (top-level epics = the six streams; weekly WBS epics fold into Ingestion)
    stream_of = {}
    for i in issues:
        s = i["parent_summary"] or "(no epic)"
        if s.startswith("W") and "—" in s and "ING" in s:
            s = "Ingestion — data ingestion pipeline"
        stream_of[i["key"]] = s.split("—")[0].strip()
    streams = defaultdict(lambda: [0, 0])  # done, total
    for i in issues:
        if i["type"] == "Epic":
            continue
        s = stream_of[i["key"]]
        streams[s][1] += 1
        if i["status_category"] == "done":
            streams[s][0] += 1
    stream_rows = "".join(
        f"<tr><td>{escape(name)}</td><td>{d}/{t}</td>"
        f'<td><div class="pbar"><div style="width:{d / t * 100:.0f}%"></div></div></td>'
        f"<td>{d / t * 100:.0f}%</td></tr>"
        for name, (d, t) in sorted(streams.items(), key=lambda kv: -kv[1][1])
        if t >= 3
    )

    wip_rows = "".join(
        f"<tr><td>{escape(i['key'])}</td><td>{escape(i['summary'] or '')}</td>"
        f"<td>{escape(i['assignee'] or '—')}</td>"
        f"<td>{(today - parse_day(i['created'])).days}d</td></tr>"
        for i in sorted(wip, key=lambda x: x["created"])
    )

    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>eParts — Program Health</title>
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

<h1>eParts — Program Health</h1>
<div class="sub">Pimsie Supreme · CMU MSE Studio · generated {today} by <code>dashboard/generate_program_health.py</code></div>

<div class="prov"><b>Provenance.</b> Every number on this page is computed from
<code>dashboard/data/jira_issues.json</code> — {total} issues exported from {escape(prov["source"])}
with <code>{escape(prov["jql"])}</code> at {escape(prov["fetched_at_utc"])}. No figure is hand-typed;
re-run the query and the script to reproduce the page (forecast seeded, {SIMS:,} simulations).</div>

<div class="tiles">
  <div class="tile"><div class="v">{len(done_issues) / total * 100:.0f}%</div><div class="l">issues complete ({len(done_issues)}/{total})</div></div>
  <div class="tile"><div class="v">{pts_done / pts_total * 100:.0f}%</div><div class="l">story points complete ({pts_done:.0f}/{pts_total:.0f})</div></div>
  <div class="tile"><div class="v">{len(open_issues)}</div><div class="l">open issues ({len(wip)} in progress)</div></div>
  <div class="tile"><div class="v">{med_thru}/wk</div><div class="l">median throughput, last {THROUGHPUT_WINDOW_WEEKS} wks</div></div>
  <div class="tile"><div class="v">{p50[1].strftime("%b %d")}</div><div class="l">P50 completion of current backlog</div></div>
  <div class="tile"><div class="v">{p85[1].strftime("%b %d")}</div><div class="l">P85 completion (85% of simulations)</div></div>
</div>

<h2>How far along — feature burnup, not time</h2>
<div class="legend"><b style="color:{C_DONE}">— Done</b> (cumulative resolved) ·
<b style="color:{C_SCOPE}">- - Scope</b> (cumulative created; the gap between the lines is the open backlog)</div>
{svg_line_chart(weeks, scope, done_cum)}

<h2>Delivery rate — issues resolved per week</h2>
<div class="legend">Full-color bars form the {THROUGHPUT_WINDOW_WEEKS}-week sampling window the forecast draws from; earlier weeks are dimmed.</div>
{svg_bar_chart(weeks, resolved_w, window_start)}

<h2>When will it be done — Monte Carlo forecast</h2>
<div class="legend">Distribution of completion dates for the current {len(open_issues)}-issue open backlog across {SIMS:,} simulations.</div>
{svg_forecast_hist(hist, p50, p85, week_of(today))}
<p class="note"><b>Method &amp; assumptions.</b> Each simulation draws weekly throughput (with replacement)
from the last {THROUGHPUT_WINDOW_WEEKS} weeks of actual resolved counts and consumes the open backlog of
{len(open_issues)} issues. P50 {p50[1]} / P85 {p85[1]} / P95 {p95[1]}. Assumes scope stays at today's
backlog — the burnup's scope line shows how much that assumption has moved historically — and that summer
throughput continues. This is a forecast with stated uncertainty, not a promise; it re-derives from data
on every refresh.</p>

<h2>Stream progress (features by delivery stream)</h2>
<table><tr><th>Stream</th><th>Done</th><th>Progress</th><th>%</th></tr>{stream_rows}</table>

<h2>Blockers — work in progress now</h2>
<table><tr><th>Key</th><th>Summary</th><th>Assignee</th><th>Age</th></tr>{wip_rows}</table>
<p class="note">Risks with triggers and mitigations are maintained in the Risk Register
(<code>docs/eParts_Risk_Register_v2.md</code>); defects follow <code>docs/defect_management.md</code>.
Items above aging past a tick without movement are escalation candidates at standup.</p>

</div></body></html>"""

    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.relative_to(HERE.parent)}")
    print(f"  {total} issues · {len(done_issues)} done · {len(open_issues)} open · median thru {med_thru}/wk")
    print(f"  forecast: P50 {p50[1]} · P85 {p85[1]} · P95 {p95[1]}")


if __name__ == "__main__":
    main()
