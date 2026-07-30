"""Emit pipe-filter-architecture-v6.svg = v5.0 verbatim + one ETIM matching box.

v5.0 lives as a React component ("pipe and filter.txt"). This is a faithful
transcription of it, with exactly one addition: an "ETIM matching" filter directly
behind "ML / AI attribute matching", inside the same PredictionServiceInterface
boundary. Everything else — the staging store, the router, the rejection/audit
column, observability, all of it — is v5 untouched, because the whole point of the
slide is that ETIM was the only structural change.

Coordinates below are v5's own numbers. Y() adds the vertical shift needed to make
room for the new box, so nothing downstream had to be re-typed by hand.
"""

C = {
    "teal":   dict(bg="#E1F5EE", stroke="#0F6E56", title="#085041", sub="#0F6E56"),
    "purple": dict(bg="#EEEDFE", stroke="#534AB7", title="#3C3489", sub="#534AB7"),
    "coral":  dict(bg="#FAECE7", stroke="#993C1D", title="#712B13", sub="#993C1D"),
    "blue":   dict(bg="#E6F1FB", stroke="#185FA5", title="#0C447C", sub="#185FA5"),
    "gray":   dict(bg="#F1EFE8", stroke="#5F5E5A", title="#444441", sub="#5F5E5A"),
    "amber":  dict(bg="#FAEEDA", stroke="#854F0B", title="#412402", sub="#633806"),
}
COL_DATA, COL_API, COL_TELEM, COL_REJ = "#185FA5", "#0F6E56", "#5F5E5A", "#A32D2D"
F = "system-ui, sans-serif"

W, CX = 1280, 480
bw = 360
bx = CX - bw // 2
splitL, splitW, splitR = 200, 210, 550
STX, STW, STY = 50, 200, 360
RX, RW = 830, 200
OX, OW, OY, OH = 880, 100, 110, 130

# v5's interface boundary sat at y=460 h=88 and ended at 548. The ETIM box goes in
# behind ML/AI, so the boundary grows and everything below 548 slides down.
IF_X, IF_Y, IF_W = bx - 60, 460, bw + 120
ML_Y, ML_H = 472, 68                       # v5's ML/AI box
ETIM_Y = ML_Y + ML_H + 20                  # 560
IF_H = (ETIM_Y + ML_H + 12) - IF_Y         # boundary wraps both passes
IF_BOTTOM = IF_Y + IF_H
V5_BOTTOM = 548                            # v5's IF_BOTTOM
SHIFT = IF_BOTTOM - V5_BOTTOM
H = 1180 + SHIFT

out = []


def Y(v):
    """v5 y-coordinate -> v6. Anything below v5's interface boundary shifts down."""
    return v + SHIFT if v > V5_BOTTOM else v


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def txt(x, y, s, fill, size, weight=None, anchor="middle", style=None, spacing=None):
    a = f' text-anchor="{anchor}"' if anchor else ""
    w = f' font-weight="{weight}"' if weight else ""
    st = f' font-style="{style}"' if style else ""
    sp = f' letter-spacing="{spacing}"' if spacing else ""
    out.append(f'<text x="{x}" y="{y}"{a} dominant-baseline="central" fill="{fill}"'
               f' font-size="{size}"{w}{st}{sp} font-family="{F}">{esc(s)}</text>')


def filter_box(x, y, w, color, title, sub=None, h=68):
    c = C[color]
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{c["bg"]}"'
               f' stroke="{c["stroke"]}" stroke-width="0.8"/>')
    txt(x + w / 2, y + (h * 0.36 if sub else h / 2), title, c["title"], 20, 600)
    if sub:
        txt(x + w / 2, y + h * 0.7, sub, c["sub"], 15)


def store(x, y, w, color, title, sub=None, h=52):
    c = C[color]
    ry = 10
    out.append(f'<path d="M{x},{y + ry} Q{x},{y} {x + w / 2},{y} Q{x + w},{y} {x + w},{y + ry}'
               f' L{x + w},{y + h - ry} Q{x + w},{y + h} {x + w / 2},{y + h}'
               f' Q{x},{y + h} {x},{y + h - ry} Z" fill="{c["bg"]}" stroke="{c["stroke"]}"'
               f' stroke-width="0.6"/>')
    out.append(f'<ellipse cx="{x + w / 2}" cy="{y + ry}" rx="{w / 2}" ry="{ry}"'
               f' fill="{c["bg"]}" stroke="{c["stroke"]}" stroke-width="0.6"/>')
    txt(x + w / 2, y + (h * 0.46 if sub else h / 2 + 4), title, c["title"], 16, 500)
    if sub:
        txt(x + w / 2, y + h * 0.74, sub, c["sub"], 12)


def pipe(points, color=COL_DATA, dashed=False, no_arrow=False, width=None):
    d = " ".join(f'{"M" if i == 0 else "L"}{p[0]} {p[1]}' for i, p in enumerate(points))
    sw = width or (1 if dashed else 1.6)
    da = ' stroke-dasharray="5 3"' if dashed else ""
    ae = "" if no_arrow else ' marker-end="url(#ah)"'
    out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}"{da}{ae}/>')


def plabel(x, y, s, color="#5F5E5A", anchor="start"):
    txt(x, y, s, color, 15, anchor=anchor, style="italic")


# ─────────────────────────────────────────────────────────────── header + legend
out.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'width="{W}" height="{H}">')
out.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
out.append('<defs><marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7"'
           ' markerHeight="7" orient="auto-start-reverse">'
           '<path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5"'
           ' stroke-linecap="round" stroke-linejoin="round"/></marker></defs>')
txt(CX, 30, "Pipe and filter — product data enrichment platform", "#2C2C2A", 22, 600)
txt(CX, 54, "v6.0 · July 2026", "#5F5E5A", 14)

out.append('<g transform="translate(30, 78)">')
out.append('<rect x="0" y="0" width="580" height="86" rx="10" fill="#FAFAF7"'
           ' stroke="#D4D2CC" stroke-width="0.8"/>')
txt(14, 14, "LEGEND", "#888780", 10, 600, anchor="start", spacing="0.08em")
out.append('<g transform="translate(14, 30)">')
for x, key, label, lx in [(0, "teal", "Processing", 20), (210, "coral", "Human-in-loop", 230),
                          (336, "amber", "Feedback loop", 356)]:
    out.append(f'<rect x="{x}" y="-7" width="14" height="14" rx="2" fill="{C[key]["bg"]}"'
               f' stroke="{C[key]["stroke"]}" stroke-width="0.6"/>')
    txt(lx, 0, label, "#444441", 12, anchor="start")
out.append(f'<path d="M108,-7 Q108,-4 116,-4 Q124,-4 124,-7 L124,5 Q124,8 116,8 Q108,8 108,5 Z"'
           f' fill="{C["blue"]["bg"]}" stroke="{C["blue"]["stroke"]}" stroke-width="0.6"/>')
out.append(f'<ellipse cx="116" cy="-7" rx="8" ry="3" fill="{C["blue"]["bg"]}"'
           f' stroke="{C["blue"]["stroke"]}" stroke-width="0.6"/>')
txt(132, 0, "Data store", "#444441", 12, anchor="start")
out.append('<rect x="458" y="-7" width="14" height="11" rx="2" fill="none" stroke="#534AB7"'
           ' stroke-width="1" stroke-dasharray="3 2"/>')
txt(478, 0, "Stable interface", "#444441", 12, anchor="start")
out.append('</g>')
out.append('<line x1="14" y1="48" x2="566" y2="48" stroke="#E5E3DC" stroke-width="0.6"/>')
out.append('<g transform="translate(14, 66)">')
pipe([[0, 0], [26, 0]], COL_DATA, width=1.8)
txt(32, 0, "Data transfer", "#444441", 12, anchor="start")
pipe([[108, 0], [134, 0]], COL_API, width=1.8)
txt(140, 0, "API call", "#444441", 12, anchor="start")
pipe([[186, 0], [212, 0]], COL_TELEM, dashed=True, width=1)
txt(218, 0, "Telemetry", "#444441", 12, anchor="start")
out.append('<rect x="290" y="-5" width="10" height="10" rx="2" fill="#0F6E56"/>')
txt(306, 0, "High-confidence port", "#444441", 12, anchor="start")
out.append('<rect x="428" y="-5" width="10" height="10" rx="2" fill="#993C1D"/>')
txt(444, 0, "Low-confidence port", "#444441", 12, anchor="start")
out.append('</g></g>')

# ─────────────────────────────────────────────────────────────── main spine
filter_box(bx, 180, bw, "gray", "Supplier data sources", "PDF, CSV, SFTP, web scraping")
pipe([[CX, 248], [CX, 276]])
plabel(CX + 14, 262, "raw catalog files")

filter_box(bx - 25, 276, bw + 50, "teal", "Ingestion gateway", "Parse, normalize, OCR extraction")
store(STX, STY, STW, "blue", "Staging /", "canonical tables", h=64)
pipe([[bx - 25, 340], [STX + STW / 2, 340], [STX + STW / 2, STY]])
pipe([[CX, 344], [CX, IF_Y]])
plabel(CX + 14, 400, "structured records")
pipe([[STX + STW / 2, STY + 64], [STX + STW / 2, 502], [IF_X, 502]])
plabel(STX + STW / 2 + 8, STY + 90, "fetch records in case of failure")

# stable interface — unchanged contract, now wrapping both matching passes
out.append(f'<rect x="{IF_X}" y="{IF_Y}" width="{IF_W}" height="{IF_H}" rx="16" fill="none"'
           f' stroke="#534AB7" stroke-width="1.2" stroke-dasharray="6 4"/>')
txt(IF_X + IF_W + 40, IF_Y - 10, "PredictionServiceInterface", "#5F5E5A", 15,
    anchor="end", style="italic")

filter_box(bx - 40, ML_Y, bw + 80, "teal", "ML / AI attribute matching",
           "Schema match + confidence scoring")

# ── THE ONLY STRUCTURAL CHANGE IN v6
pipe([[CX, ML_Y + ML_H], [CX, ETIM_Y]])
filter_box(bx - 40, ETIM_Y, bw + 80, "teal", "ETIM matching",
           "Class, feature, value + unit · ETIM 10.0")

pipe([[CX, IF_BOTTOM], [CX, Y(568)]])
plabel(CX + 14, Y(558), "scored attributes")

filter_box(bx - 20, Y(568), bw + 40, "teal", "Request Router",
           "Route by per-attribute confidence")
out.append(f'<rect x="{CX - 66}" y="{Y(630)}" width="12" height="12" rx="2" fill="#0F6E56"'
           f' stroke="#0F6E56" stroke-width="0.5"/>')
out.append(f'<rect x="{CX + 54}" y="{Y(630)}" width="12" height="12" rx="2" fill="#993C1D"'
           f' stroke="#993C1D" stroke-width="0.5"/>')

pipe([[CX - 60, Y(642)], [CX - 60, Y(678)], [splitL + splitW / 2, Y(678)],
      [splitL + splitW / 2, Y(712)]])
txt(CX - 180, Y(664), "high confidence records", "#0F6E56", 15, 600)
pipe([[CX + 60, Y(642)], [CX + 60, Y(678)], [splitR + splitW / 2, Y(678)],
      [splitR + splitW / 2, Y(712)]])
txt(CX + 180, Y(664), "low confidence records", "#993C1D", 15, 600)

filter_box(splitL, Y(712), splitW, "teal", "Auto-accept", "Writeback approved data")
filter_box(splitR, Y(712), splitW, "coral", "Human review", "Inspect, approve, reject")

pipe([[splitL + splitW / 2, Y(780)], [splitL + splitW / 2, Y(820)], [CX, Y(820)]],
     no_arrow=True)
pipe([[splitR + splitW / 2, Y(780)], [splitR + splitW / 2, Y(820)], [CX, Y(820)],
      [CX, Y(858)]])
plabel(CX + 70, Y(804), "approve / fix", anchor="middle")
out.append(f'<circle cx="{CX}" cy="{Y(820)}" r="7" fill="#888780" stroke="#FAFAF7"'
           f' stroke-width="1.5"/>')
plabel(CX - 14, Y(808), "merge", anchor="end")
plabel(CX + 14, Y(844), "accepted structured records")

store(bx + 10, Y(858), bw - 20, "blue", "PIMS staging / approved output")
pipe([[CX, Y(910)], [CX, Y(938)]])
plabel(CX + 14, Y(924), "ETL / API upsert")
filter_box(bx, Y(938), bw, "teal", "Publish / sync job", "Upsert to target system")
pipe([[CX, Y(1006)], [CX, Y(1044)]], COL_API)
plabel(CX + 14, Y(1025), "publish")
filter_box(bx - 25, Y(1044), bw + 50, "purple", "PIMS",
           "Product information management system")

# ─────────────────────────────────────────────────────────────── rejection column
pipe([[splitR + splitW, Y(746)], [RX, Y(746)]])
plabel((splitR + splitW + RX) / 2, Y(736), "rejection", anchor="middle")
out.append(f'<rect x="{RX}" y="{Y(722)}" width="{RW}" height="48" rx="10" fill="#FCEBEB"'
           f' stroke="{COL_REJ}" stroke-width="0.7"/>')
txt(RX + RW / 2, Y(740), "Rejected items log", "#791F1F", 15, 600)
txt(RX + RW / 2, Y(758), "rejection + corrected value", COL_REJ, 12)
pipe([[RX + RW / 2, Y(770)], [RX + RW / 2, Y(806)]])
plabel(RX + RW / 2 + 8, Y(788), "write decision")

out.append(f'<rect x="{RX}" y="{Y(806)}" width="{RW}" height="66" rx="10"'
           f' fill="{C["amber"]["bg"]}" stroke="{C["amber"]["stroke"]}" stroke-width="0.7"/>')
txt(RX + RW / 2, Y(826), "Audit Trail", C["amber"]["title"], 16, 600)
txt(RX + RW / 2, Y(846), "prediction, confidence,", C["amber"]["sub"], 12)
txt(RX + RW / 2, Y(860), "corrected value", C["amber"]["sub"], 12)
pipe([[RX + RW, Y(839)], [RX + RW + 55, Y(839)]], COL_API)
plabel(RX + RW + 27, Y(830), "notify", color=COL_API, anchor="middle")
out.append(f'<rect x="{RX + RW + 55}" y="{Y(818)}" width="140" height="42" rx="10"'
           f' fill="{C["amber"]["bg"]}" stroke="{C["amber"]["stroke"]}" stroke-width="0.7"/>')
txt(RX + RW + 125, Y(833), "Catalog Team", C["amber"]["title"], 13, 600)
txt(RX + RW + 125, Y(849), "Alert", C["amber"]["sub"], 12)
pipe([[RX + RW / 2, Y(872)], [RX + RW / 2, Y(912)]])
plabel(RX + RW / 2 + 8, Y(892), "corrected record")

cb = C["blue"]
out.append(f'<path d="M{RX + 30},{Y(922)} Q{RX + 30},{Y(912)} {RX + RW / 2},{Y(912)}'
           f' Q{RX + RW - 30},{Y(912)} {RX + RW - 30},{Y(922)} L{RX + RW - 30},{Y(970)}'
           f' Q{RX + RW - 30},{Y(980)} {RX + RW / 2},{Y(980)} Q{RX + 30},{Y(980)}'
           f' {RX + 30},{Y(970)} Z" fill="{cb["bg"]}" stroke="{cb["stroke"]}"'
           f' stroke-width="0.6"/>')
out.append(f'<ellipse cx="{RX + RW / 2}" cy="{Y(922)}" rx="{(RW - 60) / 2}" ry="10"'
           f' fill="{cb["bg"]}" stroke="{cb["stroke"]}" stroke-width="0.6"/>')
txt(RX + RW / 2, Y(948), "Correction Store", cb["title"], 14, 600)
txt(RX + RW / 2, Y(966), "accumulates corrections", cb["sub"], 12)

# ─────────────────────────────────────────────────────────────── observability
cg = C["gray"]
out.append(f'<rect x="{OX}" y="{OY}" width="{OW}" height="{OH}" rx="12" fill="{cg["bg"]}"'
           f' stroke="{cg["stroke"]}" stroke-width="0.6" stroke-dasharray="6 3"/>')
txt(OX + OW / 2, OY + 24, "Observability", cg["title"], 14, 600)
for i, lbl in enumerate(["Logs", "Metrics", "Traces", "Dashboards"]):
    txt(OX + OW / 2, OY + 50 + i * 18, lbl, cg["sub"], 12)
pipe([[bx + bw + 25, 310], [OX - 50, 310], [OX - 50, 156], [OX, 156]],
     COL_TELEM, dashed=True)
pipe([[IF_X + IF_W, 506], [OX - 30, 506], [OX - 30, 200], [OX, 200]],
     COL_TELEM, dashed=True)
pipe([[RX + RW / 2, Y(722)], [RX + RW / 2, OY + OH]], COL_TELEM, dashed=True)

out.append('</svg>')

DEST = "/Users/arjun/Documents/CMU/studio-project/Diagrams/pipe-filter-architecture-v6.svg"
with open(DEST, "w") as f:
    f.write("\n".join(out))
print(f"wrote {DEST} — {W}x{H}, shift={SHIFT}, one box added to v5.0")
