"""The text-layer row fix (D-038 rung 1, D-039 rung 1b) - the production port of the frozen
rung-1b emitter (``scripts/a1_diag/rung1/emit.py`` + ``run_rung1.py --fired live``, hashes in
``reports/a1_diag/rung1b/emitter_freeze.json``).

Docling's TableFormer merges rows on dense no-leading pages (D-038); for each table the rung-1b
trigger fires, rows come from the PDF text layer's y-lines and columns from x-bands of the numeric
tokens' right edges, while TableFormer supplies the table bbox and (checked against the page words)
the header text. Every other table, and every table of a source outside ``row_fix.sources``
(BUDGET / CBO, hash-pinned), passes through unchanged.

* **Trigger (rung 1b, live).** A table fires iff TableFormer holds a merged body cell (a non-header
  cell in column >= 1 holding >= ``merged_cell_min_numbers`` numbers) OR the frozen D-038 trigger's
  numeric-line count differs from TableFormer's rows. A band-count mismatch alone no longer fires
  (D-039 status 2026-10-01: a change to D-038's band clause, accepted, ported as-is). The counts use
  the frozen trigger's own tokeniser (``row_fix.trigger``); ``scripts/a1_diag/rung1/trigger.py`` is
  not the source of the rule.
* **Fallback.** When a table cannot be rebuilt safely (no body lines, band assertion, the safety
  rules), TableFormer's table is kept and the reason is logged.

Every threshold lives in ``parser.row_fix`` (D31) with the frozen value; the port is gated on
byte-identical output (D-039 status 2026-10-01, port gate), so a change re-opens that gate.
"""

from __future__ import annotations

import copy
import re
import statistics as st
from collections import Counter
from typing import Any

from ledger.config import RowFixConfig, RowTokenConfig

# ---- numbers (the oracle's reading, scripts/a1_diag/oracle.py, verbatim) -------------------------

# printed no-data markers: they locate a column but are never values (D-038 item 1)
PLACEHOLDERS = {"(s)", "NA", "W", "–", "—", "-", "--", "(NA)", "(D)", "(X)", "(Z)", "*"}
NUMBER = r"-?(?:\d+(?:\.\d+)?|\.\d+)"
FLAG = re.compile(r"^(RE|R|E)(?=[\d(.\-−�])|(?<=[\d)])(RE|R|E)$")
YEAR = re.compile(r"(19|20)\d\d")
DOTS = ".…"
MINUS = "-−"
FLAGS = {"R", "E", "RE"}
FLAG_LEAD = re.compile(r"^(RE|R|E)(?=[\d(.\-−�])")
LEADERS = ".…�\x08"


def canon(tok: str) -> str | None:
    """Printed numeric token -> signed plain decimal ('8,170' -> '8170', '(5.0)' -> '-5.0');
    U+FFFD decimal glyphs (ERP) and MER's fractions without a leading zero are normalised."""
    t = tok.strip().replace(",", "").replace("−", "-").replace("–", "-")
    t = t.rstrip("*")
    t = re.sub(r"(?<=\d)�(?=\d)", ".", t)
    t = re.sub(r"^(-?)�(?=\d)", r"\1.", t)
    m = re.fullmatch(r"\((" + NUMBER + r")\)", t)
    if m:
        t = "-" + m.group(1).lstrip("-")
    if not re.fullmatch(NUMBER, t):
        return None
    t = re.sub(r"^(-?)\.", r"\g<1>0.", t)
    if re.fullmatch(r"-0+(?:\.0+)?", t):
        t = t[1:]
    return t


def numeric(text: str) -> bool:
    """A token is numeric iff ``canon`` accepts it after an R / E / RE revision flag is stripped."""
    t = FLAG.sub("", text.strip())
    return bool(t) and canon(t) is not None


def is_value(tok: dict) -> bool:
    return numeric(tok["text"])


def table_box(doc: dict, tbl: dict) -> tuple[int, tuple[float, float, float, float]]:
    """(page, (x0, top, x1, bottom)) of the table's ``prov`` bbox in top-left points."""
    prov = tbl["prov"][0]
    page = prov["page_no"]
    b = prov["bbox"]
    if b.get("coord_origin", "BOTTOMLEFT") == "BOTTOMLEFT":
        h = doc["pages"][str(page)]["size"]["height"]
        return page, (b["l"], h - b["t"], b["r"], h - b["b"])
    return page, (b["l"], b["t"], b["r"], b["b"])


def make_token(cs: list[dict]) -> dict:
    return {
        "text": "".join(c["text"] for c in cs).strip(),
        "x0": min(c["x0"] for c in cs),
        "x1": max(c["x1"] for c in cs),
        "top": min(c["top"] for c in cs),
        "bottom": max(c["bottom"] for c in cs),
        "chars": cs,
    }


# ---- the frozen D-038 trigger's counts (its tokeniser, verbatim) ---------------------------------


def trigger_lines(
    chars: list[dict], box: tuple[float, float, float, float], q: RowTokenConfig
) -> list[list[dict]]:
    x0, top, x1, bottom = box
    m = q.box_margin_pt
    inside = [
        c
        for c in chars
        if c["text"].strip()
        and x0 - m <= (c["x0"] + c["x1"]) / 2 <= x1 + m
        and top - m <= (c["top"] + c["bottom"]) / 2 <= bottom + m
    ]
    if not inside:
        return []
    med = st.median(c["size"] for c in inside)
    inside = [c for c in inside if c["size"] >= q.superscript_size_ratio * med]
    tol = q.line_tol_height_ratio * st.median(c["bottom"] - c["top"] for c in inside)
    lines: list[list[dict]] = []
    for c in sorted(inside, key=lambda c: (c["top"] + c["bottom"]) / 2):
        cy = (c["top"] + c["bottom"]) / 2
        if lines and abs(cy - st.mean((d["top"] + d["bottom"]) / 2 for d in lines[-1])) <= tol:
            lines[-1].append(c)
        else:
            lines.append([c])
    return [_trigger_tokens(sorted(ln, key=lambda c: c["x0"]), q) for ln in lines]


def _trigger_tokens(ln: list[dict], q: RowTokenConfig) -> list[dict]:
    groups: list[list[dict]] = []
    for c in ln:
        if groups and c["x0"] - groups[-1][-1]["x1"] <= q.gap_size_ratio * c["size"]:
            groups[-1].append(c)
        else:
            groups.append([c])
    toks: list[dict] = []
    for g in groups:
        texts = [c["text"] for c in g]
        cur: list[dict] = []
        for i, c in enumerate(g):
            ch = texts[i]
            in_run = ch in DOTS and (
                (i > 0 and texts[i - 1] in DOTS) or (i + 1 < len(g) and texts[i + 1] in DOTS)
            )
            if in_run:
                if cur:
                    toks.append(make_token(cur))
                cur = []
                continue
            if (
                ch in MINUS
                and cur
                and cur[-1]["text"].isdigit()
                and i + 1 < len(g)
                and (texts[i + 1].isdigit() or texts[i + 1] == ".")
            ):
                toks.append(make_token(cur))
                cur = []
            cur.append(c)
        if cur:
            toks.append(make_token(cur))
    return [t for t in toks if t["text"].strip()]


def text_counts(lines: list[list[dict]]) -> tuple[int, int, float]:
    """(numeric-line count, band count, band tolerance) of the frozen D-038 trigger."""
    num_lines, rights, widths = 0, [], []
    for ln in lines:
        vals = [t for t in ln[1:] if numeric(t["text"])]
        if not vals or all(YEAR.fullmatch(t["text"]) for t in vals):
            continue
        num_lines += 1
        for t in vals:
            rights.append(t["x1"])
            widths.append((t["x1"] - t["x0"]) / max(1, len(t["text"])))
    if not rights:
        return num_lines, 0, 0.0
    tol = st.median(widths)
    rights.sort()
    bands = 1 + sum(1 for a, b in zip(rights, rights[1:], strict=False) if b - a > tol)
    return num_lines, bands, tol


def tf_counts(tbl: dict) -> tuple[int, int]:
    """TableFormer rows / columns holding a numeric body cell outside the stub column."""
    grid = tbl["data"].get("grid") or []
    rows, cols = set(), set()
    for r, row in enumerate(grid):
        for j, c in enumerate(row):
            if j == 0 or c.get("column_header"):
                continue
            if any(numeric(w) for w in (c.get("text") or "").split()):
                rows.add(r)
                cols.add(j)
    return len(rows), len(cols)


# ---- the rung-1b live trigger (run_rung1.py --fired live) ----------------------------------------


def merged_body_cells(tbl: dict, p: RowFixConfig) -> int:
    """TableFormer body cells (not a column header, column >= 1) holding >= the configured number
    of numbers - the census's merged cell."""
    n = 0
    for c in tbl["data"].get("table_cells") or []:
        if c.get("column_header") or c["start_col_offset_idx"] < 1:
            continue
        if sum(numeric(w) for w in (c.get("text") or "").split()) >= p.merged_cell_min_numbers:
            n += 1
    return n


def fired_tables(doc: dict, pdf: Any, p: RowFixConfig) -> set[int]:
    """Indices of the tables the rung-1b trigger fires on (counted on the unmodified document)."""
    fired: set[int] = set()
    chars_by_page: dict[int, list] = {}
    for ti, tbl in enumerate(doc.get("tables", [])):
        if not tbl.get("prov"):
            continue
        page, box = table_box(doc, tbl)
        if page not in chars_by_page:
            chars_by_page[page] = pdf.pages[page - 1].chars
        lines, _bands, _ = text_counts(trigger_lines(chars_by_page[page], box, p.trigger))
        tf_rows, _tf_cols = tf_counts(tbl)
        if merged_body_cells(tbl, p) > 0 or lines != tf_rows:
            fired.add(ti)
    return fired


# ---- the emitter (scripts/a1_diag/rung1/emit.py as frozen) ---------------------------------------


def fix_text(t: str) -> str:
    t = re.sub(r"(?<=\d)�(?=\d)", ".", t)
    return re.sub(r"(^|\s)(-?)�(?=\d)", r"\1\2.", t)


def flag_space(text: str) -> str:
    """A revision flag fused to its number ("R1,358", "E1,358") is emitted with a space, as the
    page's words read ("R 1,358"). Body, stub and section cells only (F1, rung 1b)."""
    return " ".join(
        FLAG_LEAD.sub(lambda m: m.group(1) + " ", w) if is_value({"text": w}) else w
        for w in text.split(" ")
    )


def cell_text(toks: list[dict]) -> str:
    """One band's tokens as cell text; a number split at a kerning gap around its decimal point
    or thousands comma ("3 .349", "11 ,459") is rejoined when the joined text is one number."""
    out: list[str] = []
    for t in toks:
        w = t["text"]
        if out:
            a = out[-1]
            seam = w[:1] in ".," or a[-1:] in ".,"
            if seam and (a[-1:].isdigit() or a[-1:] in ".,") and is_value({"text": a + w}):
                out[-1] = a + w
                continue
        out.append(w)
    return " ".join(out)


def merge_flags(line: list[dict], p: RowFixConfig) -> list[dict]:
    out: list[dict] = []
    i = 0
    while i < len(line):
        t = line[i]
        if t["text"] in FLAGS and i + 1 < len(line) and is_value(line[i + 1]):
            nxt = line[i + 1]
            w = (nxt["x1"] - nxt["x0"]) / max(1, len(nxt["text"]))
            if nxt["x0"] - t["x1"] <= p.flag_merge_gap_char_widths * w:
                out.append(dict(nxt, text=t["text"] + nxt["text"], x0=t["x0"]))
                i += 2
                continue
        out.append(t)
        i += 1
    return out


def in_parenthetical(line: list[dict]) -> set[int]:
    """Indices of tokens inside a parenthetical that opens and closes on the line (a unit label
    "(billion chained 2017 dollars - SAAR)"); such tokens are label text, never body values."""
    inside: set[int] = set()
    span: list[int] = []
    for i, t in enumerate(line):
        w = t["text"]
        if span:
            span.append(i)
            if w.endswith(")"):
                inside.update(span)
                span = []
        elif w.startswith("(") and ")" not in w:
            span = [i]
    return inside


def body_values(line: list[dict]) -> list[dict]:
    paren = in_parenthetical(line)
    vals = [t for i, t in enumerate(line[1:], 1) if is_value(t) and i not in paren]
    if not vals or all(YEAR.fullmatch(t["text"]) for t in vals):
        return []
    return vals


def cluster_bands(tokens: list[dict], p: RowFixConfig) -> list[dict]:
    widths = [(t["x1"] - t["x0"]) / max(1, len(t["text"])) for t in tokens]
    tol = st.median(widths)
    bands: list[list[dict]] = []
    for t in sorted(tokens, key=lambda t: t["x1"]):
        if bands and t["x1"] - bands[-1][-1]["x1"] <= tol:
            bands[-1].append(t)
        else:
            bands.append([t])
    # a centred column's right edges wander with digit count and can split into two clusters whose
    # x-extents overlap heavily; right-aligned neighbours never overlap that much: merge those
    merged: list[list[dict]] = []
    for b in bands:
        if merged:
            q = merged[-1]
            p0, p1 = min(t["x0"] for t in q), max(t["x1"] for t in q)
            b0, b1 = min(t["x0"] for t in b), max(t["x1"] for t in b)
            if min(p1, b1) - max(p0, b0) > p.band_overlap_merge_ratio * min(p1 - p0, b1 - b0):
                q.extend(b)
                continue
        merged.append(list(b))
    return [
        {
            "right": st.median(t["x1"] for t in b),
            "x0": min(t["x0"] for t in b),
            "x1": max(t["x1"] for t in b),
            "n": len(b),
            "tol": tol,
        }
        for b in merged
    ]


def band_of(tok: dict, bands: list[dict]) -> int:
    return min(range(len(bands)), key=lambda i: abs(bands[i]["right"] - tok["x1"]))


def cell(text, box, r, c, *, header=False, row_header=False, section=False) -> dict:
    x0, top, x1, bottom = box
    return {
        "bbox": {"l": x0, "t": top, "r": x1, "b": bottom, "coord_origin": "TOPLEFT"},
        "row_span": 1,
        "col_span": 1,
        "start_row_offset_idx": r,
        "end_row_offset_idx": r + 1,
        "start_col_offset_idx": c,
        "end_col_offset_idx": c + 1,
        "text": text,
        "column_header": header,
        "row_header": row_header,
        "row_section": section,
        "fillable": False,
    }


def span_box(toks: list[dict]) -> tuple[float, float, float, float]:
    return (
        min(t["x0"] for t in toks),
        min(t["top"] for t in toks),
        max(t["x1"] for t in toks),
        max(t["bottom"] for t in toks),
    )


def phrases_of(ln: list[dict], p: RowFixConfig) -> list[list[dict]]:
    """Header-line phrases: words one word-space apart."""
    phrases: list[list[dict]] = []
    for t in sorted(ln, key=lambda t: t["x0"]):
        size = t["bottom"] - t["top"]
        if phrases and t["x0"] - phrases[-1][-1]["x1"] <= p.phrase_gap_size_ratio * size:
            phrases[-1].append(t)
        else:
            phrases.append([t])
    return phrases


def tf_col_band(tbl: dict, bands: list[dict]) -> dict[int, int]:
    """TableFormer column -> band, by the x-overlap of the column's body cells."""
    grid = tbl["data"].get("grid") or []
    ncol = max((len(r) for r in grid), default=0)
    ext: dict[int, list[float]] = {}
    for row in grid:
        for j, c in enumerate(row):
            if c.get("column_header") or not c.get("bbox") or not c.get("text"):
                continue
            b = c["bbox"]
            e = ext.setdefault(j, [b["l"], b["r"]])
            e[0], e[1] = min(e[0], b["l"]), max(e[1], b["r"])
    col_band: dict[int, int] = {}
    for j in range(1, ncol):
        if j not in ext:
            continue
        lo, hi = ext[j]
        best = max(
            range(len(bands)),
            key=lambda i: min(hi, bands[i]["x1"]) - max(lo, bands[i]["x0"]),
        )
        if min(hi, bands[best]["x1"]) - max(lo, bands[best]["x0"]) > 0:
            col_band.setdefault(j, best)
    return col_band


def header_cells(
    tbl: dict, bands: list[dict], header_lines: list[list[dict]], p: RowFixConfig
) -> tuple[list[dict], int, list[str]]:
    """Header cells as {row, bands (band indices, or [-1] for the stub column), text}, spans kept.

    TableFormer's header cells are mapped onto the bands through each TableFormer column's body
    extent. A band's header words must equal the page words over it (no token more often than on
    the page); failing bands - and every band sharing a TableFormer cell with one - take
    page-derived cells. A spanning head takes the bands of its gap tile when centred on them (F2,
    rung 1b), or TableFormer's span for the same words when it is alone on its line."""
    log: list[str] = []
    tol = p.header_tolerance_pt
    col_band = tf_col_band(tbl, bands)
    tcells = [
        c for c in tbl["data"].get("table_cells") or [] if c.get("column_header") and c.get("text")
    ]
    hrows = sorted({c["start_row_offset_idx"] for c in tcells})
    tf: list[dict] = []
    for c in tcells:
        cols = range(c["start_col_offset_idx"], c["end_col_offset_idx"])
        bset = sorted({col_band[j] for j in cols if j in col_band})
        if c["start_col_offset_idx"] == 0 or not bset:
            if c["start_col_offset_idx"] != 0:
                log.append(f"TF header cell maps to no band: {c['text']!r}")
                continue
            bset = [-1]
        tf.append({"row": hrows.index(c["start_row_offset_idx"]), "bands": bset, "text": c["text"]})

    def over(t: dict, b: dict) -> bool:
        return t["x1"] > b["x0"] - tol and t["x0"] < b["x1"] + tol

    def centred(ext: dict, ks: set[int]) -> bool:
        mid = (min(bands[k]["x0"] for k in ks) + max(bands[k]["x1"] for k in ks)) / 2
        return ext["x0"] <= mid <= ext["x1"]

    def phrase_bands(ln: list[dict]) -> list[tuple[list[dict], set[int]]]:
        out = []
        for ph in phrases_of(ln, p):
            ext = {"x0": min(t["x0"] for t in ph), "x1": max(t["x1"] for t in ph)}
            out.append((ph, ext, {k for k, b in enumerate(bands) if over(ext, b)}))
        on = [x for x in out if x[2]]
        res = []
        for ph, ext, phys in out:
            eff = phys
            if phys:
                i = next(j for j, x in enumerate(on) if x[0] is ph)
                lo = (on[i - 1][1]["x1"] + ext["x0"]) / 2 if i > 0 else float("-inf")
                hi = (ext["x1"] + on[i + 1][1]["x0"]) / 2 if i + 1 < len(on) else float("inf")
                tile = {k for k, b in enumerate(bands) if lo <= (b["x0"] + b["x1"]) / 2 <= hi}
                if len(tile) > len(phys) and phys <= tile and centred(ext, tile):
                    eff = tile
                else:
                    words = Counter(w for t in ph for w in t["text"].split())
                    for h in tf:
                        hb = set(h["bands"])
                        if (
                            hb != {-1}
                            and len(hb) > len(phys)
                            and phys <= hb
                            and Counter(h["text"].split()) == words
                            and centred(ext, hb)
                        ):
                            eff = hb
                            break
            res.append((ph, eff))
        return res

    line_bands = [phrase_bands(ln) for ln in header_lines]
    failing: set[int] = set()
    for k in range(len(bands)):
        pw = Counter(
            w
            for lb in line_bands
            for ph, eff in lb
            if k in eff
            for t in ph
            for w in t["text"].split()
        )
        tw = Counter(w for h in tf if k in h["bands"] for w in h["text"].split())
        if not (tw and not (tw - pw) and set(tw) == set(pw)):
            failing.add(k)
    grew = True
    while grew:  # a TableFormer cell over a failing band is dropped whole
        grew = False
        for h in tf:
            if h["bands"] != [-1] and set(h["bands"]) & failing and not set(h["bands"]) <= failing:
                failing |= set(h["bands"])
                grew = True
    kept = [h for h in tf if h["bands"] == [-1] or not set(h["bands"]) & failing]
    if failing:
        log.append(f"header check: page words for bands {sorted(failing)}")
    nrow = max((h["row"] for h in kept), default=-1) + 1
    page_cells: list[dict] = []
    stub_phrases: list[list[dict]] = []
    for lb in line_bands:
        cells_ln: list[dict] = []
        for ph, eff in lb:
            if not eff:
                stub_phrases.append(ph)  # over no band: the stub column's head
                continue
            ov = tuple(k for k in sorted(failing) if k in eff)
            if ov:
                cells_ln.append({"key": ov, "text": " ".join(t["text"] for t in ph)})
        if not cells_ln:
            continue
        for c in cells_ln:
            page_cells.append({"row": nrow, "bands": list(c["key"]), "text": c["text"]})
        nrow += 1
    # a column head printed over several lines is one cell: consecutive page-derived cells over
    # the same bands merge, text in printed order
    merged_cells: list[dict] = []
    last_by_key: dict[tuple, dict] = {}
    for c in page_cells:
        key = tuple(c["bands"])
        prev = last_by_key.get(key)
        if prev is not None and prev["row"] + prev.get("rows", 1) == c["row"]:
            prev["text"] += " " + c["text"]
            prev["rows"] = prev.get("rows", 1) + 1
            continue
        merged_cells.append(c)
        last_by_key[key] = c
        for k in [k for k in last_by_key if k != key and set(k) & set(key)]:
            del last_by_key[k]  # a different cell over these bands ends the run
    page_cells = merged_cells
    out = [h for h in kept if h["bands"] != [-1]] + page_cells
    stub = [h for h in kept if h["bands"] == [-1]]
    if stub_phrases:
        text = " ".join(" ".join(t["text"] for t in ph) for ph in stub_phrases)
        stub = [{"row": 0, "bands": [-1], "text": text}]
    out += stub
    return out, max(nrow, 1 if out else 0), log


FOOTER = re.compile(
    r"^(Sources?\b|Notes?\b|NOTES?\b|Footnotes?\b|\*\s*(?:=|[A-Za-z])|†|‡|[a-z]\)|\([a-z0-9]{1,2}\)|"
    r"\d{1,2}/|\d{1,2}\s+[A-Z]|[A-Z]{1,2}\s?=|\(s\)\s?=|-\s?=|–\s?=|Components may not)"
)
CONNECTORS = {
    "and",
    "or",
    "of",
    "for",
    "the",
    "to",
    "in",
    "on",
    "by",
    "with",
    "excluding",
    "including",
    "from",
    "at",
    "a",
    "an",
}


def continues(text_toks: list[dict], nxt: list[dict]) -> bool:
    """A text-only line is the first part of a wrapped label (not a section header) iff it ends
    with "," "-" "(" "/" or a connector word, or the next line's label starts in lower case."""
    if not text_toks:
        return False
    last = text_toks[-1]["text"]
    if last.endswith(":"):
        return False
    if last[-1:] in ",-(/–" or last.lower() in CONNECTORS:
        return True
    first = nxt[0]["text"] if nxt else ""
    return first[:1].islower()


def tbl_left(tbl: dict) -> float:
    return tbl["prov"][0]["bbox"]["l"]


def grid_of(cells: list[dict], nrows: int, ncols: int) -> list[list[dict]]:
    empty = {"text": "", "column_header": False, "row_header": False, "bbox": None}
    grid = [[dict(empty) for _ in range(ncols)] for _ in range(nrows)]
    for c in cells:  # a spanning cell fills every position it covers, as Docling's grid does
        for r in range(c["start_row_offset_idx"], c["end_row_offset_idx"]):
            for j in range(c["start_col_offset_idx"], c["end_col_offset_idx"]):
                grid[r][j] = c
    return grid


def rebuild(tbl: dict, lines: list[list[dict]], p: RowFixConfig) -> tuple[dict | None, list[str]]:
    """One fired table -> (rebuilt TableItem dict, log), or (None, reason) to keep TableFormer's."""
    log: list[str] = []
    lines = [merge_flags(ln, p) for ln in lines]
    cand = [i for i, ln in enumerate(lines) if body_values(ln)]
    if not cand:
        return None, ["no body lines"]

    # a no-data placeholder right of a body line's first value is column-position evidence, as
    # in the oracle's own band rule (11.6, rung 1b)
    def evidence(ln: list[dict]) -> list[dict]:
        vals = body_values(ln)
        return vals + [
            t for t in ln[1:] if vals and t["text"] in PLACEHOLDERS and t["x0"] > vals[0]["x0"]
        ]

    all_bands = cluster_bands([t for i in cand for t in evidence(lines[i])], p)
    # dense bands define the body; a number outside them - a title's bill number, a footnote
    # marker, a code inside a label - is text
    min_n = max(p.dense_band_min_tokens, -(-len(cand) // p.dense_band_line_divisor))
    dense = [b for b in all_bands if b["n"] >= min_n]
    if not dense:
        return None, ["no dense band"]

    def in_bands(t: dict, bands: list[dict]) -> int | None:
        k = min(range(len(bands)), key=lambda i: abs(bands[i]["right"] - t["x1"]))
        return (
            k
            if abs(bands[k]["right"] - t["x1"]) <= p.in_band_tol_multiple * bands[k]["tol"]
            else None
        )

    def is_word(t: dict) -> bool:
        return sum(ch.isalpha() for ch in t["text"]) >= p.word_min_alpha

    def prose(ln: list[dict]) -> bool:
        x_num = dense[0]["x0"] - dense[0]["tol"]
        words = [t for t in ln if t["x0"] >= x_num and is_word(t) and t["text"] not in PLACEHOLDERS]
        return len(words) >= p.prose_min_words

    body_idx = [
        i
        for i in cand
        if any(in_bands(t, dense) is not None for t in body_values(lines[i]))
        and not prose(lines[i])
    ]
    if not body_idx:
        return None, ["no body lines in dense bands"]
    # safety fallbacks (the text grid assumes numeric columns right of one label)
    n_prose = sum(1 for i in cand if prose(lines[i]))
    if n_prose > p.prose_safety_share * len(cand):
        return None, [f"safety: {n_prose}/{len(cand)} candidate lines are prose"]
    split_stubs = 0
    for i in body_idx:  # a text column = gap-separated stub segments holding words
        stub_toks = [t for t in lines[i] if t["x1"] <= dense[0]["x0"]]
        segs: list[list[dict]] = []
        for t in stub_toks:
            if segs and t["x0"] - segs[-1][-1]["x1"] <= p.text_column_gap_em * (
                t["bottom"] - t["top"]
            ):
                segs[-1].append(t)
            else:
                segs.append([t])
        worded = [s for s in segs if any(is_word(t) for t in s)]
        if len(worded) >= p.text_column_min_segments:
            split_stubs += 1
    if split_stubs >= p.text_column_safety_share * len(body_idx):
        return None, [f"safety: text column ({split_stubs}/{len(body_idx)} stubs split by > 2 em)"]
    first, last = body_idx[0], body_idx[-1]
    header_region = [t for ln in lines[:first] for t in ln]
    tol = p.header_tolerance_pt

    def headed(b: dict) -> bool:
        return any(t["x1"] > b["x0"] - tol and t["x0"] < b["x1"] + tol for t in header_region)

    # a thin band right of the first dense band is a sparse column iff a header sits above it
    bands = [b for b in all_bands if b["n"] >= min_n or (b["x0"] > dense[0]["x0"] and headed(b))]
    if len(bands) < len(all_bands):
        log.append(f"{len(all_bands) - len(bands)} thin band(s) without a header taken as text")
    printed_cols = sum(1 for b in bands if headed(b))
    if printed_cols != len(bands):
        return None, [
            f"band assertion: {len(bands)} bands vs {printed_cols} printed header columns"
        ]
    left = min(b["x0"] for b in bands)
    body_set = set(body_idx)

    def over_band(t: dict) -> bool:
        return any(t["x1"] > b["x0"] - tol and t["x0"] < b["x1"] + tol for b in bands)

    # the column-header block ends at the last line above the body with a token over a band;
    # stub-only lines between it and the first body line are section headers, not header text
    hdr_end = max((i for i in range(first) if any(over_band(t) for t in lines[i])), default=-1)
    rows: list[dict] = []
    pending: list[dict] = []
    leading = (
        st.median(
            lines[b][0]["top"] - lines[a][0]["top"]
            for a, b in zip(body_idx, body_idx[1:], strict=False)
        )
        if len(body_idx) > 1
        else p.default_leading_pt
    )
    for i in range(hdr_end + 1, last + 1):
        ln = lines[i]
        if i not in body_set:
            text_toks = list(ln)
            nxt = next((k for k in body_idx if k > i), None)
            if (
                nxt is not None
                and lines[nxt][0]["top"] - ln[0]["top"] <= p.wrap_leading_multiple * leading
                and not any(is_value(t) for t in ln[1:])
                and continues(text_toks, lines[nxt])
            ):
                pending += text_toks
            else:
                if pending:
                    rows.append({"section": pending})
                pending = []
                rows.append({"section": text_toks})
            continue
        stub = pending + [t for t in ln if t["x1"] <= left + p.stub_left_tolerance_pt]
        pending = []
        cells: dict[int, list[dict]] = {}
        for t in ln:
            if t in stub:
                continue
            cells.setdefault(band_of(t, bands), []).append(t)
        rows.append({"stub": stub, "cells": cells})
    if pending:
        rows.append({"section": pending})
    # below the last numeric line: text rows are kept; the footer block - from the first
    # Source / Note / footnote / legend line on - is cut
    for ln in lines[last + 1 :]:
        if FOOTER.match(ln[0]["text"]) or FOOTER.match(" ".join(t["text"] for t in ln[:2])):
            log.append(f"footer cut at: {' '.join(t['text'] for t in ln)[:60]!r}")
            break
        stub = [t for t in ln if t["x1"] <= left + p.stub_left_tolerance_pt]
        cells = {}
        for t in ln:
            if t not in stub:
                cells.setdefault(band_of(t, bands), []).append(t)
        rows.append({"stub": stub, "cells": cells} if cells else {"section": list(ln)})
    # emit
    out_cells: list[dict] = []
    hcells, nhead, hlog = header_cells(tbl, bands, lines[: hdr_end + 1], p)
    log += hlog
    for h in hcells:
        if h["bands"] == [-1]:
            c0, c1, x0, x1 = 0, 1, tbl_left(tbl), left
        else:
            c0, c1 = min(h["bands"]) + 1, max(h["bands"]) + 2
            x0, x1 = bands[min(h["bands"])]["x0"], bands[max(h["bands"])]["x1"]
        hc = cell(fix_text(h["text"]), (x0, 0, x1, 0), h["row"], c0, header=True)
        hc["col_span"], hc["end_col_offset_idx"] = c1 - c0, c1
        rows_n = h.get("rows", 1)
        hc["row_span"], hc["end_row_offset_idx"] = rows_n, h["row"] + rows_n
        out_cells.append(hc)
    r = nhead
    for row in rows:
        if "section" in row:
            toks = row["section"]
            if toks:
                out_cells.append(
                    cell(
                        flag_space(fix_text(" ".join(t["text"] for t in toks))),
                        span_box(toks),
                        r,
                        0,
                        row_header=True,
                        section=True,
                    )
                )
                r += 1
            continue
        if row["stub"]:
            out_cells.append(
                cell(
                    flag_space(fix_text(" ".join(t["text"] for t in row["stub"]))),
                    span_box(row["stub"]),
                    r,
                    0,
                    row_header=True,
                )
            )
        for b, toks in row["cells"].items():
            out_cells.append(cell(flag_space(fix_text(cell_text(toks))), span_box(toks), r, b + 1))
        r += 1
    numeric_cells = [
        c
        for c in out_cells
        if not c["column_header"]
        and c["start_col_offset_idx"] > 0
        and any(is_value({"text": w}) for w in c["text"].split())
    ]
    multi = sum(
        1 for c in numeric_cells if sum(is_value({"text": w}) for w in c["text"].split()) > 1
    )
    if numeric_cells and multi > p.multi_number_safety_share * len(numeric_cells):
        return None, [f"safety: {multi}/{len(numeric_cells)} emitted cells hold >= 2 numbers"]
    new = copy.deepcopy(tbl)
    ncol = len(bands) + 1
    new["data"]["table_cells"] = out_cells
    new["data"]["num_rows"] = r
    new["data"]["num_cols"] = ncol
    new["data"]["grid"] = grid_of(out_cells, r, ncol)
    return new, log


# ---- the emitter's tokeniser ---------------------------------------------------------------------


def emitter_lines(doc: dict, tbl: dict, pdf: Any, p: RowFixConfig) -> list[list[dict]]:
    page, box = table_box(doc, tbl)
    return tokens_in(pdf.pages[page - 1].chars, box, p.tokens)


def tokens_in(
    chars: list[dict], box: tuple[float, float, float, float], q: RowTokenConfig
) -> list[list[dict]]:
    """Lines of tokens inside ``box``: an explicit space character breaks a word; a run of >= 2
    leader glyphs is dropped; a fused negative splits only with a decimal or comma beside it."""
    x0, top, x1, bottom = box
    m = q.box_margin_pt
    inside = [
        c
        for c in chars
        if x0 - m <= (c["x0"] + c["x1"]) / 2 <= x1 + m
        and top - m <= (c["top"] + c["bottom"]) / 2 <= bottom + m
    ]
    ink = [c for c in inside if c["text"].strip()]
    if not ink:
        return []
    med = st.median(c["size"] for c in ink)
    inside = [
        c for c in inside if not c["text"].strip() or c["size"] >= q.superscript_size_ratio * med
    ]
    tol = q.line_tol_height_ratio * st.median(c["bottom"] - c["top"] for c in ink)
    lines: list[list[dict]] = []
    for c in sorted(inside, key=lambda c: (c["top"] + c["bottom"]) / 2):
        cy = (c["top"] + c["bottom"]) / 2
        if lines and abs(cy - lines[-1][0]["_cy"]) <= tol:
            lines[-1].append(c)
        else:
            c = dict(c)
            c["_cy"] = cy
            lines.append([c])
            continue
    out = []
    for ln in lines:
        ln = [c for c in sorted(ln, key=lambda c: c["x0"])]
        toks: list[dict] = []
        cur: list[dict] = []
        texts = [c["text"] for c in ln]
        for i, c in enumerate(ln):
            ch = texts[i]
            if not ch.strip():
                if cur:
                    toks.append(make_token(cur))
                cur = []
                continue
            if cur and c["x0"] - cur[-1]["x1"] > q.gap_size_ratio * c["size"]:
                toks.append(make_token(cur))
                cur = []
            in_run = ch in LEADERS and (
                (i > 0 and texts[i - 1] in LEADERS) or (i + 1 < len(ln) and texts[i + 1] in LEADERS)
            )
            if in_run:
                if cur:
                    toks.append(make_token(cur))
                cur = []
                continue
            if ch in MINUS and cur and cur[-1]["text"].isdigit():
                ahead = ""
                for x in texts[i + 1 :]:
                    if not (x.isdigit() or x in ".,"):
                        break
                    ahead += x
                before = ""
                for x in reversed(cur):
                    if not (x["text"].isdigit() or x["text"] in ".,"):
                        break
                    before = x["text"] + before
                if ahead[:1].isdigit() or ahead[:1] == ".":
                    if any(ch2 in ".," for ch2 in before + ahead):
                        toks.append(make_token(cur))
                        cur = []
            cur.append(c)
        if cur:
            toks.append(make_token(cur))
        # a lone "(" joins the next token when that one closes it ("( d)" -> "(d)")
        joined: list[dict] = []
        for t in toks:
            if joined and joined[-1]["text"] == "(" and t["text"].endswith(")"):
                prev = joined.pop()
                joined.append(make_token(prev["chars"] + t["chars"]))
            else:
                joined.append(t)
        toks = joined
        # spaced leader dots (MER prints ". . . .") arrive as one-glyph tokens: never content
        toks = [
            t
            for t in toks
            if t["text"].strip() and not all(ch in LEADERS + "·" for ch in t["text"])
        ]
        if toks:
            out.append(toks)
    return out


# ---- one document --------------------------------------------------------------------------------


def fix_document(doc: dict, pdf: Any, source: str, p: RowFixConfig) -> dict[int, dict]:
    """Apply the row fix to ``doc`` (a Docling document dict) IN PLACE; ``pdf`` is the unit's open
    ``pdfplumber.PDF``. Returns the per-table log {table index: {"status", "notes"?}}: "not
    fired", "out of scope (D-039)" (fired, source outside ``row_fix.sources``), "fallback"
    (TableFormer's table kept) or "rebuilt"."""
    fired = fired_tables(doc, pdf, p)
    in_scope = source in p.sources
    log: dict[int, dict] = {}
    for ti, tbl in enumerate(doc.get("tables", [])):
        if ti not in fired:
            log[ti] = {"status": "not fired"}
            continue
        if not in_scope:  # D-039: BUDGET/CBO outputs stay byte-identical (hash-pinned)
            log[ti] = {"status": "out of scope (D-039)"}
            continue
        new, notes = rebuild(tbl, emitter_lines(doc, tbl, pdf, p), p)
        if new is None:
            log[ti] = {"status": "fallback", "notes": notes}
        else:
            doc["tables"][ti] = new
            log[ti] = {"status": "rebuilt", "notes": notes}
    return log
