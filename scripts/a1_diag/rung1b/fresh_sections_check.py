"""Fact-finding (owner, 2026-09-30): why the fresh MER oracle scan found no tables in sec7 / sec12,
and whether the burned sec13 has tables. Report only - no fix, no decision, no admission change.

Reads the PDFs programmatically, as ``fresh_oracle.py`` does: page geometry, images, text lines
that name a table (ids and titles only - no body numbers are written), bookmarks. Checks whether
the per-table exports exist (``xls.php?tbl=``, sniff type and the export's own title only; no
values read). The fresh parse is not opened.

    uv run --with pdfplumber --with pypdf --with openpyxl python \
        scripts/a1_diag/rung1b/fresh_sections_check.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(REPO))
import oracle as orc  # noqa: E402

OUT = REPO / "reports" / "a1_diag" / "rung1b" / "fresh_sections_check.md"
CHECK = REPO / "data" / "oracle" / "fresh" / "mer" / "src_check"
UNITS = (
    ("sec7", REPO / "data" / "raw_fresh" / "eia" / "eia-pdf-sec7.pdf", "fresh"),
    ("sec12", REPO / "data" / "raw_fresh" / "eia" / "eia-pdf-sec12.pdf", "fresh"),
    ("sec13", REPO / "data" / "raw" / "eia" / "eia-pdf-sec13.pdf", "pilot (burned)"),
)
LETTER_ID = re.compile(r"^\s*Table\s+([A-Z]\d+)\.")
SOURCES = re.compile(r"\bTable\s+([A-Z]?\d+(?:\.\d+)?[a-z]?)\s+Sources\b")


def bookmarks(path: Path) -> list[tuple[int, int | None, str]]:
    from pypdf import PdfReader

    r = PdfReader(str(path))
    out: list = []

    def walk(items, depth=0):
        for it in items:
            if isinstance(it, list):
                walk(it, depth + 1)
            else:
                try:
                    pg = r.get_destination_page_number(it) + 1
                except Exception:  # noqa: BLE001
                    pg = None
                out.append((depth, pg, it.title))

    try:
        walk(r.outline)
    except Exception:  # noqa: BLE001
        pass
    return out


def title_only(text: str) -> str:
    """The heading line with any body numbers dropped: keep the table id and title words."""
    m = re.match(r"^\s*(Table\s+[A-Z]?\d+(?:\.\d+)?[a-z]?\.?)\s*(.*)$", text)
    head, rest = (m.group(1), m.group(2)) if m else ("", text)
    rest = re.sub(r"\s\S*\d\S*", "", " " + rest).strip()  # no numbers from the body
    return (head + " " + rest).strip()[:80]


def page_facts(path: Path) -> list[dict]:
    import pdfplumber
    from pypdf import PdfReader

    rot = [int(p.get("/Rotate", 0) or 0) for p in PdfReader(str(path)).pages]
    out = []
    with pdfplumber.open(path) as pdf:
        for i, p in enumerate(pdf.pages, 1):
            area = p.width * p.height
            ws = p.extract_words(x_tolerance=1)
            lines = orc.cluster(ws)
            named = []
            for ln in lines:
                t = " ".join(w["text"] for w in ln)
                kind = (
                    "Sources note"
                    if SOURCES.search(t)
                    else "digits id"
                    if orc.TABLE_ID.match(t)
                    else "letter id"
                    if LETTER_ID.match(t)
                    else None
                )
                if kind:
                    named.append(
                        {
                            "y": round(ln[0]["top"] / p.height, 2),
                            "kind": kind,
                            "text": title_only(t),
                        }
                    )
            first = " ".join(w["text"] for w in lines[0]) if lines else ""
            chars = p.chars
            out.append(
                {
                    "page": i,
                    "rotate": rot[i - 1],
                    "w": round(p.width),
                    "h": round(p.height),
                    "orientation": "portrait" if p.height >= p.width else "landscape",
                    "chars": len(chars),
                    "upright": round(sum(c.get("upright", True) for c in chars) / len(chars), 2)
                    if chars
                    else None,
                    "words": len(ws),
                    "images": [
                        round((m["x1"] - m["x0"]) * (m["bottom"] - m["top"]) / area, 2)
                        for m in p.images
                    ],
                    "named": named,
                    "first_line": title_only(first) if first else "(no text)",
                }
            )
    return out


def classify(f: dict) -> str:
    if f["words"] <= 14 and f["images"]:
        return "image-only (header + images; no body text)"
    if f["first_line"].startswith("Figure"):
        return "figure (chart) page"
    if any(n["kind"] == "Sources note" for n in f["named"]):
        return "notes (Sources)"
    if any(n["kind"] in ("digits id", "letter id") for n in f["named"]):
        return "text table (headed)"
    if f["words"] <= 12:
        return "divider / blank"
    return "text (no table heading)"


def export_check(tbls: list[str]) -> dict[str, dict]:
    from ledger.config import load_config
    from ledger.ingest.http import Fetcher

    fetcher = Fetcher(load_config().fetch)
    CHECK.mkdir(parents=True, exist_ok=True)
    out = {}
    for tbl in tbls:
        url = orc.MER_URL.format(tbl=tbl)
        assert url.startswith("https://")
        dest = CHECK / f"{tbl}.xlsx"
        try:
            fetcher.download(url, dest, source="eia")
            b = dest.read_bytes()
            kind = orc.sniff(b)
            title = orc.export_title(dest) if kind.startswith("OOXML") else ""
        except Exception as exc:  # noqa: BLE001
            kind, title = f"error {type(exc).__name__}", ""
        out[tbl] = {"type": kind, "title": title[:90]}
    out["_hosts"] = fetcher.calls_by_host
    return out


def main() -> int:
    facts = {name: page_facts(path) for name, path, _ in UNITS}
    marks = {name: bookmarks(path) for name, path, _ in UNITS}
    # candidate export ids: sec7 from its Sources notes; sec12 from appendix letter ids + A1-A6
    sec7_ids = []
    for f in facts["sec7"]:
        for n in f["named"]:
            m = SOURCES.search(n["text"] + " Sources") if n["kind"] == "Sources note" else None
            if m and m.group(1) not in sec7_ids:
                sec7_ids.append(m.group(1))
    sec12_ids = [f"A{i}" for i in range(1, 7)]
    for f in facts["sec12"]:
        for n in f["named"]:
            m = re.match(r"Table\s+([A-Z]\d+)", n["text"])
            if m and m.group(1) not in sec12_ids:
                sec12_ids.append(m.group(1))
    for extra in ("C1", "D1"):
        if extra not in sec12_ids:
            sec12_ids.append(extra)
    # sec7 probe ids: the section's numbering pattern beyond the Sources-note list (probes only)
    probes7 = [
        "7.1",
        "7.2a",
        "7.2b",
        "7.2c",
        "7.3a",
        "7.3b",
        "7.3c",
        "7.4a",
        "7.4b",
        "7.4c",
        "7.5",
        "7.6",
        "7.7a",
        "7.7b",
        "7.7c",
    ]
    ids7 = sec7_ids + [i for i in probes7 if i not in sec7_ids]
    tbls7 = [orc.mer_tbl(i) for i in ids7]
    tbls12 = [f"T{i}" for i in sec12_ids] + [f"T{i[0]}{int(i[1:]):02d}" for i in sec12_ids]
    exports = export_check(tbls7 + tbls12)

    def exists(tid: str, tbl: str) -> bool:
        """xls.php answers ANY tbl with a workbook; an export exists only if its own title names
        the table ("Table 7.2b ...", "Table E1. ...", "Table A6: ...")."""
        t = exports.get(tbl, {}).get("title", "")
        return bool(re.match(rf"Table\s+{re.escape(tid)}(?![0-9a-z])", t, re.I))

    ex7 = {i: exists(i, orc.mer_tbl(i)) for i in ids7}
    ex12 = {i: exists(i, f"T{i}") for i in sec12_ids}
    cls = {n: [classify(f) for f in facts[n]] for n in facts}
    pages_of = lambda n, c: [f["page"] for f, k in zip(facts[n], cls[n], strict=True) if k == c]  # noqa: E731
    img7, fig7, notes7 = (
        pages_of("sec7", c)
        for c in (
            "image-only (header + images; no body text)",
            "figure (chart) page",
            "notes (Sources)",
        )
    )
    img12 = pages_of("sec12", "image-only (header + images; no body text)")
    head12 = [
        (f["page"], n["text"].split(".")[0].replace("Table ", ""), round(n["y"], 2))
        for f in facts["sec12"]
        for n in f["named"]
        if n["kind"] == "letter id"
    ]
    summary = [
        "## Per section",
        "",
        "### sec7 (fresh; D-039 'entire')",
        "",
        f"- Pages: {len(facts['sec7'])}, all /Rotate 0, 612x792 portrait. Figure (chart) pages "
        f"with a text layer: {fig7}. **Image-only pages** (running header, about 12 words, plus "
        f"5-6 images of about 11-13 % of the page each, no body text layer): {img7} "
        f"({len(img7)} pages). Sources-notes pages: {notes7}; p32 continues the notes.",
        f"- (a) Printed tables: the ids named in the text layer are only those in the Sources "
        f"notes ({', '.join(sec7_ids)}). The section's per-table exports exist (title names the "
        f"table) for: {', '.join(i for i, v in ex7.items() if v)}; not found: "
        f"{', '.join(i for i, v in ex7.items() if not v) or 'none'}. The tables sit in the "
        f"image-only pages (they follow each Figure page in the section's order); their ids are "
        f"INFERRED from that order and the export list, not read - no table id or title is in "
        f"the text layer, and the pages were not viewed (viewing would expose values).",
        f"- Count: {sum(ex7.values())} table ids with an export against {len(img7)} image-only "
        "pages, so some tables take more than one page (inferred; the page-to-table mapping is "
        "not read).",
        "- (b) Why `page_ids` missed them: the tables are printed as images - there is no text "
        "layer to read an id from (not position, not rotation). Docling found 0 tables here "
        "for the same reason (OCR is off, D2). The one id `page_ids` did find (7.6, p31) is the "
        "notes line 'Table 7.6 Sources' at y 0.02, not a table heading - so item 2's '7.6 "
        "excluded: title check failed' was a notes line; table 7.6 itself is image-only.",
        "- (c) Exports: see the table below (type and export title only).",
        "- Charts / notes rather than tables: the Figure pages are charts; p28-32 are Sources "
        "notes; the image-only pages are the table positions (content not verified).",
        "",
        "### sec12 (fresh; D-039 'entire'; Appendices A-F)",
        "",
        f"- Pages: {len(facts['sec12'])}, all /Rotate 0, 612x792 portrait. Text tables headed "
        f"with LETTER ids (page, id, y): {head12}. Image-only pages: {img12} (one image of "
        f"63-75 % of the page each) in Appendix A (bookmark MER_A; 'Table A6 Sources' on p15).",
        f"- (a) Printed tables: {', '.join(sec12_ids)} ({len(sec12_ids)}); A2-A6 are on the "
        f"image-only pages (ids INFERRED from the Appendix A bookmarks, the Sources note and the "
        f"export titles; not read). Exports whose title names the table: "
        f"{', '.join(i for i, v in ex12.items() if v)}; workbook returned without a matching "
        f"title (treated as not found): {', '.join(i for i, v in ex12.items() if not v)}.",
        "- (b) Why `page_ids` missed them: FORMAT - `orc.TABLE_ID` requires `digits.digits` "
        "(e.g. 12.1); appendix tables are 'Table B1.', 'Table E1.' etc. Also C1 and D1 are "
        "headed below a title line (y 0.07 / 0.10), so the first-line rule would miss them "
        "even with a letter-id pattern; A2-A6 are images. Not rotation.",
        "- (c) Exports: see below. Zero-padded tbl forms (TA01 ...) return untitled workbooks.",
        "",
        "### sec13 (burned pilot)",
        "",
        f"- {len(facts['sec13'])} pages, all /Rotate 0, 612x792 portrait: the Glossary - prose "
        "on every page, no line anywhere naming a table (digit or letter id, or a Sources note), "
        "no images, no bookmarks. **sec13 has no tables**; Docling's 0 is correct.",
        "",
    ]

    L = [
        "# Fresh MER sections 7 and 12 (and burned sec13): page-level facts",
        "",
        "Fact-finding only (owner, 2026-09-30): no fix, no decision, no admission change. The "
        "PDFs are read programmatically (geometry, images, lines naming a table: ids and titles "
        "only, no body numbers). The fresh parse is not opened. Export check = `xls.php?tbl=` "
        "through the project Fetcher (https), file type and the export's own title only.",
        "",
    ]
    for name, path, kind in UNITS:
        fs = facts[name]
        L += [
            f"## {name} ({kind}, {path.relative_to(REPO).as_posix()}, {len(fs)} pages)",
            "",
            "| page | /Rotate | w x h | orientation | chars | upright | words | images (page "
            "share) | lines naming a table (y, kind: text) | first line | page class |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for f in fs:
            named = "; ".join(f"{n['y']}, {n['kind']}: {n['text']}" for n in f["named"]) or "-"
            L.append(
                f"| {f['page']} | {f['rotate']} | {f['w']}x{f['h']} | {f['orientation']} | "
                f"{f['chars']} | {f['upright']} | {f['words']} | {f['images'] or '-'} | {named} | "
                f"{f['first_line'][:60]} | {classify(f)} |"
            )
        L += [
            "",
            f"Bookmarks: {len(marks[name])}"
            + (
                " - " + "; ".join(f"p{pg} {t[:50]}" for _d, pg, t in marks[name][:16])
                if marks[name]
                else ""
            ),
            "",
        ]
    L[5:5] = summary
    L += [
        "## Export check (`xls.php?tbl=`; type and export title only)",
        "",
        "| tbl | type | export title |",
        "|---|---|---|",
    ]
    for tbl, v in exports.items():
        if tbl != "_hosts":
            L.append(f"| {tbl} | {v['type']} | {v['title']} |")
    L += ["", f"Fetch hosts: {exports['_hosts']}", ""]
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    from collections import Counter

    for name, _p, _k in UNITS:
        print(name, dict(Counter(classify(f) for f in facts[name])))
    print("sec7 ids from Sources notes:", sec7_ids)
    print("sec12 ids:", sec12_ids)
    print({k: v["type"][:12] for k, v in exports.items() if k != "_hosts"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
