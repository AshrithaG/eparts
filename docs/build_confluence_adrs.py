"""Turn docs/00NN-*.md into paste-ready Confluence content.

Dropping a .md file into the Confluence editor attaches it as a download card. To get
real page content you paste the *text* — the editor converts Markdown on paste. This
emits two shapes:

  confluence/ADRs-all.md      one page holding all 21 ADRs, with an index table
  confluence/adr-00NN-*.md    one file per ADR, if you'd rather have child pages

Two fixes are applied on the way out, because both break on paste:
  - heading levels are demoted so each ADR sits under the page title, not beside it
  - relative links to sibling .md files are flattened to plain text; they would
    otherwise paste as dead links, since the targets live in GitHub, not Confluence
"""
import os
import re
import glob

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "confluence")
REPO = "https://github.com/AshrithaG/eparts/blob/main/docs/"

os.makedirs(OUT, exist_ok=True)
files = sorted(glob.glob(os.path.join(HERE, "0[0-9][0-9][0-9]-*.md")))


def demote(md, by=1):
    """Push every ATX heading down `by` levels, skipping fenced code blocks."""
    lines, fenced = [], False
    for ln in md.split("\n"):
        if ln.lstrip().startswith("```"):
            fenced = not fenced
        if not fenced:
            m = re.match(r"^(#{1,5})(\s)", ln)
            if m:
                ln = "#" * min(len(m.group(1)) + by, 6) + m.group(2) + ln[m.end():]
        lines.append(ln)
    return "\n".join(lines)


def fix_links(md):
    """Sibling .md links become GitHub links; they are dead as relative paths here."""
    return re.sub(r"\[([^\]]+)\]\((0[0-9]{3}-[^)]+\.md)\)", rf"[\1]({REPO}\2)", md)


def status_of(md):
    m = re.search(r"^##\s+Status\s*$(.*?)^##\s", md, re.M | re.S)
    if not m:
        return "—"
    for ln in m.group(1).strip().split("\n"):
        if ln.strip():
            return ln.strip().rstrip(".")
    return "—"


rows, bodies = [], []
for path in files:
    raw = open(path).read()
    title = raw.split("\n", 1)[0].lstrip("# ").strip()
    num = os.path.basename(path).split("-")[0]
    slug = os.path.basename(path)
    body = fix_links(raw)
    body = body.split("\n", 1)[1] if "\n" in body else ""   # drop its own H1
    rows.append((num, title, status_of(raw), slug))
    bodies.append(f"## {title}\n" + demote(body, 1).strip())

    single = (f"# {title}\n\n"
              f"> Source of truth: [`{slug}`]({REPO}{slug}) in the eparts repo. "
              f"This page is a copy for reading; edit the repo, not this page.\n\n"
              + fix_links(raw).split("\n", 1)[1].strip() + "\n")
    with open(os.path.join(OUT, f"adr-{slug}"), "w") as f:
        f.write(single)

index = ["| ADR | Decision | Status |", "|---|---|---|"]
for num, title, st, slug in rows:
    short = title.split(": ", 1)[1] if ": " in title else title
    index.append(f"| [{num}]({REPO}{slug}) | {short} | {st} |")

header = f"""# Architecture Decision Records

{len(files)} ADRs. **The repo is the source of truth** — every row below links to the
file in `eparts/docs/`. This page is a reading copy, so edit the repo rather than the
page, or the two will drift.

ADRs 0001–0012 are the spring baseline and are deliberately left unedited: they record
what we believed in April. ETIM decisions supersede them *forward*, by reference, in
0013–0021. Where a spring ADR is affected but not superseded, the change-impact analysis
is in [`ETIM-ADR-ASSESSMENT.md`]({REPO}ETIM-ADR-ASSESSMENT.md).

Requirement IDs cited by 0016–0021 resolve against Product Specification v1.4; the
forward and backward traces are in [`REQUIREMENTS-TO-ADR-MAPPING.md`]({REPO}REQUIREMENTS-TO-ADR-MAPPING.md).

{chr(10).join(index)}

---
"""

with open(os.path.join(OUT, "ADRs-all.md"), "w") as f:
    f.write(header + "\n\n---\n\n".join(bodies) + "\n")

with open(os.path.join(OUT, "ADRs-index.md"), "w") as f:
    f.write(header)

print(f"wrote {OUT}/ADRs-all.md ({len(files)} ADRs), ADRs-index.md, "
      f"and {len(files)} per-ADR files")
