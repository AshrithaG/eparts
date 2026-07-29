"""Build the Software System (requirements + architecture) crit section.

Palette and grid come from eParts_Section4_10min.pptx so the two sections read as one
deck. Everything on a slide is >= 20 pt so it survives projection; that is the binding
constraint on how much text each card can hold, so the slides carry phrases and the
talking script carries the sentences.
"""
from pptx import Presentation
from pptx.util import Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

BLACK = RGBColor(0x00, 0x00, 0x00)
BANNER = RGBColor(0x11, 0x11, 0x11)
CARD = RGBColor(0x1C, 0x1C, 0x1C)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
MUTED = RGBColor(0x99, 0x99, 0x99)      # lifted from 777777 — 20 pt grey needs contrast
LEAD = RGBColor(0xCC, 0xCC, 0xCC)
GREEN = RGBColor(0x70, 0xAD, 0x47)
AMBER = RGBColor(0xD8, 0xA5, 0x2C)

MIN_PT = 20.0                            # nothing on a slide may be smaller
FONT = "Aptos"
OUT = "/Users/arjun/Documents/CMU/studio-project/eParts_Section3_SoftwareSystem.pptx"
DIAG = "/Users/arjun/Documents/CMU/studio-project/Diagrams/"
CONFLUENCE = ("https://cmu-mse.atlassian.net/wiki/spaces/AISDLC/pages/76742657/"
              "Engineering+System+Artifacts")
ADR_INDEX = "https://github.com/AshrithaG/eparts/blob/main/docs/adr-index.md"

prs = Presentation()
prs.slide_width = Emu(9144000)           # 720 pt
prs.slide_height = Emu(5143500)          # 405 pt
BLANK = prs.slide_layouts[6]


def P(v):
    return Emu(int(v * 12700))


def new_slide():
    s = prs.slides.add_slide(BLANK)
    bg = s.shapes.add_shape(1, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = BLACK
    bg.line.fill.background()
    bg.shadow.inherit = False
    return s


def rect(s, x, y, w, h, color):
    sh = s.shapes.add_shape(1, P(x), P(y), P(w), P(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = color
    sh.line.fill.background()
    sh.shadow.inherit = False
    return sh


def text(s, x, y, w, h, runs, size=MIN_PT, color=MUTED, bold=False, space=0,
         align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, line=1.18, gap=7):
    assert size >= MIN_PT, f"{size} pt is below the {MIN_PT} pt projection floor"
    tb = s.shapes.add_textbox(P(x), P(y), P(w), P(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    paras = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line
        if i:
            p.space_before = Pt(gap)
        for txt, b, c in (para if isinstance(para, list) else [(para, bold, color)]):
            r = p.add_run()
            r.text = txt
            f = r.font
            f.name = FONT
            f.size = Pt(size)
            f.bold = b
            f.color.rgb = c
            if space:
                r.font._rPr.set("spc", str(int(space * 100)))
    return tb


def title(s, txt):
    text(s, 28.8, 21.6, 662.4, 40, txt, size=28, color=WHITE, bold=True, line=1.0)


def artifact_link(s, label, url=None):
    tb = s.shapes.add_textbox(P(340), P(3.0), P(351.2), P(16.0))
    tf = tb.text_frame
    tf.word_wrap = False
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    para = tf.paragraphs[0]
    para.alignment = PP_ALIGN.RIGHT
    r = para.add_run()
    r.text = label
    r.hyperlink.address = url or CONFLUENCE
    f = r.font
    f.name, f.size, f.bold, f.underline = FONT, Pt(MIN_PT), True, False
    f.color.rgb = GREEN
    return tb


def banner(s, chunks, y=68.0, h=52.0):
    rect(s, 28.8, y, 662.4, h, BANNER)
    text(s, 42.0, y + 5, 636.0, h - 10, [chunks], color=LEAD,
         anchor=MSO_ANCHOR.MIDDLE, line=1.14)


def card(s, x, y, w, h, bar, head, body, head_color=WHITE, head_size=22):
    rect(s, x, y, w, h, CARD)
    rect(s, x, y, w, 5.04, bar)
    pad = 12.0
    text(s, x + pad, y + 12, w - 2 * pad, 30, head, size=head_size, color=head_color,
         bold=True, line=1.0)
    text(s, x + pad, y + 12 + head_size * 1.55, w - 2 * pad, h - 34 - head_size * 1.55,
         body, gap=9)


def footer(s, txt, color=GREEN, y=372.0):
    rect(s, 28.8, y, 4.5, 24.0, color)
    text(s, 42.0, y, 649.2, 24.0, txt.upper(), color=color, bold=True, space=0.5,
         anchor=MSO_ANCHOR.MIDDLE, line=1.0)


# two-column geometry
LX, RX, CW = 28.8, 368.4, 322.8
CY, CH = 126.0, 238.0

# ─────────────────────────────────────────────────────────── 1. requirements delta
s = new_slide()
title(s, "How the requirements changed")
artifact_link(s, "SPEC v1.2 ↗")
banner(s, [
    ("ETIM was the biggest change.", True, GREEN),
    ("  Predict free-form attributes  →  classify into an ETIM class, match a "
     "controlled vocabulary.", False, LEAD),
])
card(s, LX, CY, CW, CH, WHITE, "What changed", [
    [("WHY", True, WHITE), ("  + industry standard", False, MUTED)],
    [("WHAT", True, WHITE), ("  predict → match", False, MUTED)],
    [("HOW WELL", True, WHITE), ("  vs. the vocabulary", False, MUTED)],
    [("NEW", True, WHITE), ("  FR-10, reference data", False, MUTED)],
])
card(s, RX, CY, CW, CH, AMBER, "What no longer holds", [
    [("HLR-2", True, WHITE), ("  now ETIM-keyed", False, MUTED)],
    [("FR-3", True, WHITE), ("  now constrained matching", False, MUTED)],
    [("Flat record", True, WHITE), ("  → product + attribute", False, MUTED)],
    [("C-4", True, GREEN), ("  ETIM 10.0 pinned", False, MUTED)],
], head_color=AMBER)
footer(s, "ETIM 10.0 EI verified and pinned — 5,640 classes")

# ─────────────────────────────────────────────────────────── 2. managing the change
s = new_slide()
title(s, "How we managed the change")
banner(s, [
    ("Spec 1.0 → 1.1 → 1.2.", True, WHITE),
    ("  Each version-history entry is the change record.", False, LEAD),
])
card(s, LX, CY, CW, CH, WHITE, "Version control", [
    [("IDs were ", False, MUTED), ("added", True, WHITE),
     (" — HLR-6, FR-9, FR-10, DR-4, C-4", False, MUTED)],
    [("Nothing renumbered.", True, WHITE)],
    [("Every existing trace link survives the change.", False, MUTED)],
])
card(s, RX, CY, CW, CH, AMBER, "Blocked on the client", [
    [("Phase-one class list", True, WHITE)],
    [("Feature policy per class", True, WHITE)],
    [("ETIM ships no required-field flag, so we can't yet write a firm validation "
      "requirement.", False, MUTED)],
], head_color=AMBER)
footer(s, "trace: HLR-6 → FR-9/10 → tickets → golden tests")

# ─────────────────────────────────────────────────────────── 3. architecture v5 → v6
s = new_slide()
title(s, "How the architecture changed")
artifact_link(s, "FULL v6.0 DIAGRAM ↗")
banner(s, [
    ("v5.0 → v6.0. The spine held.", True, WHITE),
    ("  Solid = running code. Dashed = designed, not built.", False, LEAD),
], h=40.0)
IY = 124.0
s.shapes.add_picture(DIAG + "pipe-filter-architecturev5.png", P(28.8), P(IY),
                     width=P(186), height=P(172))
s.shapes.add_picture(DIAG + "pipe-filter-architecture-v6.png", P(224), P(IY),
                     width=P(168), height=P(188))
text(s, 28.8, IY + 192, 186, 24, "v5.0 · MAY", color=MUTED, bold=True)
text(s, 224, IY + 192, 168, 24, "v6.0 · JULY", color=GREEN, bold=True)

DX, DW = 404.0, 287.2
rect(s, DX, IY, DW, 216.0, CARD)
rect(s, DX, IY, DW, 5.04, GREEN)
text(s, DX + 12, IY + 12, DW - 24, 28, "Five deltas", size=22, color=GREEN, bold=True)
yy = IY + 48
for n, label in [("1", "ETIM reference layer"),
                 ("2", "Matching in five stages"),
                 ("3", "Evidence vs. interpretation"),
                 ("4", "Frozen ML handoff"),
                 ("5", "PIMS re-keyed on ETIM")]:
    text(s, DX + 12, yy, 16, 26, n, color=GREEN, bold=True)
    text(s, DX + 30, yy, DW - 44, 26, label, color=WHITE)
    yy += 33
footer(s, "verified in code — alembic 0005–0007")

# ─────────────────────────────────────────────────────────── 4. decisions
s = new_slide()
title(s, "Decisions, and what we chose against")
artifact_link(s, "ALL 21 ADRs ↗ GITHUB", url=ADR_INDEX)
RY, RH, RG = 74.0, 48.0, 8.0
decisions = [
    ("Ingestion owns ETIM, not ML", "reference data, its own cadence"),
    ("Evidence + interpretation, not one row", "or you can't trace a value"),
    ("Supersede forward, not rewrite", "the April ADRs stay intact"),
    ("Pin ETIM 10.0, not chase releases", "a stated limit beats a half-built path"),
]
for i, (head, why) in enumerate(decisions):
    y = RY + i * (RH + RG)
    rect(s, 28.8, y, 662.4, RH, CARD)
    rect(s, 28.8, y, 4.5, RH, GREEN if i == 3 else WHITE)
    text(s, 45.0, y, 348.0, RH, head, color=WHITE, bold=True,
         anchor=MSO_ANCHOR.MIDDLE, line=1.0)
    text(s, 400.0, y, 280.0, RH, why, color=MUTED, anchor=MSO_ANCHOR.MIDDLE, line=1.0)
rect(s, 28.8, 300.0, 662.4, 52.0, BANNER)
text(s, 42.0, 305.0, 636.0, 42.0, [[
    ("Five client decisions still open.", True, WHITE),
    ("  Two of them gate validation.", False, LEAD),
]], anchor=MSO_ANCHOR.MIDDLE, line=1.14)
footer(s, "matching stages designed, not yet built", color=AMBER)

# ─────────────────────────────────────────────────────────── presenter notes
NOTES = [
    "ETIM is a mid-project requirements CHANGE, not a new project.\n\n"
    "One line: we went from predicting free-form attributes to classifying each product "
    "into an ETIM class and matching its attributes to a controlled vocabulary.\n\n"
    "Principle: original supplier data is evidence, ETIM is a standardized "
    "interpretation over it, confidence is how sure we are of the interpretation.\n\n"
    "C-4 is the newest piece: we are pinned to ETIM 10.0 EI for the project. Adopting "
    "later releases is out of scope. If asked why — the upgrade path is a diff report, "
    "a bulk re-match and a second review queue for an event that won't happen inside "
    "this project, and nobody has decided who authorizes an upgrade. A stated limit is "
    "defensible; a half-built upgrade path isn't.\n\n"
    "Artifacts: docs/product-spec-v1.2.pdf, product-spec-changelog.md, "
    "etim-requirements-change.md.",

    "Four classes of requirements management: change control, version control, status "
    "tracking, tracing.\n\n"
    "Strongest point is version control: we ADDED IDs (HLR-6, FR-9, FR-10, DR-4, then "
    "C-4) rather than renumbering, so every existing trace link survives.\n\n"
    "We used the same discipline twice — v1.1 integrated ETIM, v1.2 pinned the release "
    "rather than silently editing v1.1.\n\n"
    "Be honest about the blocked items. ETIMARTCLASSFEATUREMAP.csv genuinely has no "
    "'required' column, so until the client defines a feature policy, 'what blocks "
    "publish?' is unanswerable. ADR-019 records the seam so the build doesn't stall.\n\n"
    "Known defect to own before it's found: two spec lineages exist — this one "
    "(0.1 -> 0.5 -> 1.0 -> 1.1 -> 1.2) and a 'Document Version 2.0' from April with a "
    "different ID set. ADRs 0001-0015 cite the April IDs; 0016-0021 cite v1.2. "
    "Recorded in product-spec-changelog.md and section 10.10 of the matrix.",

    "Open the full v6 PNG rather than squinting at the thumbnail:\n"
    "Diagrams/pipe-filter-architecture-v6.png\n\n"
    "Lead with what did NOT change — pipe-and-filter, per-attribute routing, "
    "human-in-the-loop, audit trail. The spine survived a major requirements change.\n\n"
    "Delta 2 is the one to dwell on. You can't match an attribute until you know the "
    "class, because the legal feature set is defined per class. Get the class wrong and "
    "every feature under it is wrong at high confidence, so routing won't catch it. "
    "Hence five stages and a class-review step ahead of attribute routing.\n\n"
    "Delta 3: supplier text is evidence, ETIM is interpretation. One table mixes them "
    "and you lose the ability to trace a published value back to its source.\n\n"
    "Built and merged: reference layer (alembic 0005), evidence staging split (0006), "
    "extracted_inputs handoff (0007). Not built: matching stages, ETIM-aware routing, "
    "re-keyed writeback. Say so.\n\n"
    "Telemetry question: Datadog is the production target (ADR-012 stands). Prometheus "
    "+ OpenTelemetry + structlog is the local substrate. The assessment doc read the "
    "code without the deployment intent and called it a contradiction.",

    "Four decisions, each with the alternative we rejected.\n\n"
    "Row 3 is the one I'd defend hardest: we did not edit ADRs 0001-0012. They record "
    "what we decided in April. We superseded forward and wrote an assessment that goes "
    "ADR by ADR through what ETIM affected. Editing in place erases the history.\n\n"
    "Row 4 is the newest decision. ETIM 10.0 is pinned via C-4. We accept the catalog "
    "goes stale relative to ETIM; that's the trade. The etim_release_id columns stay in "
    "the schema for provenance, so a published row still names the release it was "
    "matched under, and un-pinning later is a scope change rather than a migration.\n\n"
    "The five still-open client decisions: phase-one class list, feature policy per "
    "class, 'ETIM Other' handling, metric-canonical storage and display units, and "
    "mapping sign-off ownership. Release-upgrade governance used to be a sixth; C-4 "
    "closed it.\n\n"
    "If asked what we'd do differently: reconcile the two spec lineages earlier, and "
    "wire the handoff builder into the orchestrator (EPARTS-363) so the boundary is "
    "exercised in production flow, not only in unit tests.",
]
for slide, note in zip(prs.slides, NOTES):
    slide.notes_slide.notes_text_frame.text = note

prs.save(OUT)

# python-pptx cannot set theme hlink colours; the theme otherwise forces links to blue.
import re as _re, shutil as _shutil, zipfile as _zipfile
_tmp = OUT + ".tmp"
with _zipfile.ZipFile(OUT) as _zin, _zipfile.ZipFile(_tmp, "w", _zipfile.ZIP_DEFLATED) as _zout:
    for _i in _zin.infolist():
        _d = _zin.read(_i.filename)
        if _i.filename.startswith("ppt/theme/theme"):
            _t = _d.decode("utf-8")
            for _tag in ("hlink", "folHlink"):
                _t = _re.sub(rf'(<a:{_tag}>).*?(</a:{_tag}>)',
                             rf'\1<a:srgbClr val="70AD47"/>\2', _t, flags=_re.S)
            _d = _t.encode("utf-8")
        _zout.writestr(_i, _d)
_shutil.move(_tmp, OUT)
print(f"wrote {OUT} — 4 slides, all text >= {MIN_PT} pt")
