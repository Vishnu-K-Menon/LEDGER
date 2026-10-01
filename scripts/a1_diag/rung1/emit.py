"""D-038 rung 1 - the text-layer grid emitter (rows and column bands from the text layer;
TableFormer for the table bbox and, per the A2 classification, header text).

Reads the saved Docling JSON (the table's ``prov`` bbox and TableFormer's header cells) and the PDF
text layer (pdfplumber characters, tokenised at character level by the frozen
``trigger.tokens_in``). Writes a copy of the document to ``data/parsed_rung1/<unit>.json`` with the
rebuilt tables replaced; every other table is copied byte-for-byte.

Builder rules:
* numeric tokens (after an R / E / RE flag) define **body lines**; a flag token standing alone is
  merged rightward into the number after it;
* **bands** are the right edges of body-line value tokens, clustered single-linkage within one
  median digit width - right edges, not gaps; a token joins the band with the nearest right edge;
* the **stub** is the tokens left of the first band; a text-only line within 1.5x leading above a
  body line is a wrapped label, prefixed to that line's stub; otherwise a section header row;
* **header rows** are TableFormer's column-header rows mapped onto the bands by x-overlap of each
  TableFormer column's body cells; a band's header text must equal the page words in the header
  region over that band (no token more often than on the page); when it does not, the page words
  are used (logged);
* the band count must equal the printed header-column count (bands under >= 1 header-region
  token); otherwise the table falls back to the unchanged TableFormer table (logged);
* lines below the last body line ("Source:", notes, footnotes) are cut; U+FFFD decimals -> ".".
"""

from __future__ import annotations

import copy
import json
import re
import statistics as st
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import oracle as orc  # noqa: E402
import trigger as tg  # noqa: E402

REPO = orc.REPO
PARSED = REPO / "data" / "parsed"
RAW = REPO / "data" / "raw"  # run_rung1.py --raw overrides (path only)
OUT = REPO / "data" / "parsed_rung1"
FLAGS = {"R", "E", "RE"}
OPTS = {"wrap": True, "headers": True, "assert_bands": True, "header_check": True}


def is_value(tok: dict) -> bool:
    return tg.numeric(tok["text"])


def fix_text(t: str) -> str:
    t = re.sub(r"(?<=\d)�(?=\d)", ".", t)
    return re.sub(r"(^|\s)(-?)�(?=\d)", r"\1\2.", t)


FLAG_LEAD = re.compile(r"^(RE|R|E)(?=[\d(.\-−�])")


def flag_space(text: str) -> str:
    """Rung 1b F1: a revision flag fused to its number ("R1,358", "E1,358" - fused by
    ``merge_flags`` or by the tokeniser, where the page sets the flag raised beside the number) is
    emitted with a space, as the page's words read ("R 1,358"); the builder's tests still see the
    fused token. Body, stub and section cells only; header text is untouched."""
    return " ".join(
        FLAG_LEAD.sub(lambda m: m.group(1) + " ", w) if is_value({"text": w}) else w
        for w in text.split(" ")
    )


def cell_text(toks: list[dict]) -> str:
    """Rung 1b (fallback cause): one band's tokens as cell text. A number the tokeniser split at a
    kerning gap around its decimal point or thousands comma ("3 .349", "11 ,459", "-1, 191") is
    rejoined - two adjacent pieces join with no space when one side of the boundary is the "." /
    "," and the joined text is a single number (``is_value``). Parameter-free."""
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


def merge_flags(line: list[dict]) -> list[dict]:
    out: list[dict] = []
    i = 0
    while i < len(line):
        t = line[i]
        if t["text"] in FLAGS and i + 1 < len(line) and is_value(line[i + 1]):
            nxt = line[i + 1]
            w = (nxt["x1"] - nxt["x0"]) / max(1, len(nxt["text"]))
            if nxt["x0"] - t["x1"] <= 1.5 * w:
                out.append(dict(nxt, text=t["text"] + nxt["text"], x0=t["x0"]))
                i += 2
                continue
        out.append(t)
        i += 1
    return out


def in_parenthetical(line: list[dict]) -> set[int]:
    """Rung 1b (fallback cause): indices of tokens inside an open parenthetical on the line - a
    unit label "(billion chained 2017 dollars - SAAR)" or "(index, 1982=1.00)" - opened by a token
    that starts with "(" and holds no ")", closed by a token ending with ")" ON THE SAME LINE (an
    unclosed "(" - MER 11.5's "( h" placeholder - opens nothing). A balanced token ("(1.2)", "(s)")
    opens nothing. Such tokens are label text, never body values."""
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
    if not vals or all(tg.YEAR.fullmatch(t["text"]) for t in vals):
        return []
    return vals


def cluster_bands(tokens: list[dict]) -> list[dict]:
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
            p = merged[-1]
            p0, p1 = min(t["x0"] for t in p), max(t["x1"] for t in p)
            b0, b1 = min(t["x0"] for t in b), max(t["x1"] for t in b)
            if min(p1, b1) - max(p0, b0) > 0.5 * min(p1 - p0, b1 - b0):
                p.extend(b)
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


def phrases_of(ln: list[dict]) -> list[list[dict]]:
    """Header-line phrases: words one word-space apart (<= 0.6 x size)."""
    phrases: list[list[dict]] = []
    for t in sorted(ln, key=lambda t: t["x0"]):
        size = t["bottom"] - t["top"]
        if phrases and t["x0"] - phrases[-1][-1]["x1"] <= 0.6 * size:
            phrases[-1].append(t)
        else:
            phrases.append([t])
    return phrases


def header_cells(
    tbl: dict,
    bands: list[dict],
    header_lines: list[list[dict]],
    stub_header: list[dict],
    use_tf: bool = True,
    check: bool = True,
) -> tuple[list[dict], int, list[str]]:
    """Header cells as {row, bands (band indices, or [-1] for the stub column), text}, spans kept.

    TableFormer's header cells (A2: TableFormer headers) are mapped onto the bands through each
    TableFormer column's body extent, keeping their spans. Check: a band's header words must equal
    the page words over that band in the header region (no token more often than on the page).
    Bands that fail - and every band sharing a TableFormer cell with one - take page-derived cells
    instead: per header line, consecutive tokens over the same failing bands form one cell spanning
    them, so a spanning word is written once. Header-region words over no band go to the stub
    column's header cell, as printed."""
    log: list[str] = []
    col_band = tf_col_band(tbl, bands)
    tcells = [
        c for c in tbl["data"].get("table_cells") or [] if c.get("column_header") and c.get("text")
    ]
    hrows = sorted({c["start_row_offset_idx"] for c in tcells})
    tf: list[dict] = []
    if use_tf:
        for c in tcells:
            cols = range(c["start_col_offset_idx"], c["end_col_offset_idx"])
            bset = sorted({col_band[j] for j in cols if j in col_band})
            if c["start_col_offset_idx"] == 0 or not bset:
                if c["start_col_offset_idx"] != 0:
                    log.append(f"TF header cell maps to no band: {c['text']!r}")
                    continue
                bset = [-1]
            tf.append(
                {"row": hrows.index(c["start_row_offset_idx"]), "bands": bset, "text": c["text"]}
            )

    def over(t: dict, b: dict) -> bool:
        return t["x1"] > b["x0"] - 2 and t["x0"] < b["x1"] + 2

    # rung 1b F2 (spanning-header extent): a head printed once, centred over the bands it spans
    # ("2025" over four quarters), physically overlaps only some of them. Its extent is taken from
    # the gaps to its neighbours on the header line (midpoints to the previous / next phrase that
    # lies over a band); the bands whose centres fall in that tile are its bands IF the phrase
    # crosses the midpoint of their hull (a centred head) - otherwise, and for every other phrase,
    # the bands it physically overlaps. Parameter-free; used by the check and the page cells.
    def centred(ext: dict, ks: set[int]) -> bool:
        mid = (min(bands[k]["x0"] for k in ks) + max(bands[k]["x1"] for k in ks)) / 2
        return ext["x0"] <= mid <= ext["x1"]

    def phrase_bands(ln: list[dict]) -> list[tuple[list[dict], set[int]]]:
        out = []
        for ph in phrases_of(ln):
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
                    # a lone group head on its line ("Petroleum" over four columns, 11.6) has no
                    # neighbour gaps: TableFormer's span for the same words, if centred on it
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
    if check:
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
                if (
                    h["bands"] != [-1]
                    and set(h["bands"]) & failing
                    and not set(h["bands"]) <= failing
                ):
                    failing |= set(h["bands"])
                    grew = True
    else:
        covered = {k for h in tf for k in h["bands"]}
        failing = set(range(len(bands))) - covered
    kept = [h for h in tf if h["bands"] == [-1] or not set(h["bands"]) & failing]
    if failing:
        log.append(f"header check: page words for bands {sorted(failing)}")
    nrow = max((h["row"] for h in kept), default=-1) + 1
    page_cells: list[dict] = []
    stub_phrases: list[list[dict]] = []
    for lb in line_bands:
        # a spanning group header ("Hydrocarbon Gas Liquids") is one phrase over all its bands
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
    # a column head printed over several lines ("Pro-" / "pane") is one cell, as Docling models it:
    # consecutive page-derived cells over the same bands merge, text in printed order
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
        del stub_header  # superseded: the stub head is built from the same phrases as the bands
        text = " ".join(" ".join(t["text"] for t in ph) for ph in stub_phrases)
        stub = [{"row": 0, "bands": [-1], "text": text}]
    out += stub
    return out, max(nrow, 1 if out else 0), log


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


def tf_header_rows(tbl: dict, bands: list[dict]) -> tuple[list[dict], list[str]]:
    """(superseded by header_cells; kept for the B1 record) TableFormer's column-header rows."""
    grid = tbl["data"].get("grid") or []
    ncol = max((len(r) for r in grid), default=0)
    # x extent of each TableFormer column from its body cells
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
    rows, log = [], []
    for row in grid:
        if not row or not all(c.get("column_header") or not c.get("text") for c in row):
            continue
        if not any(c.get("column_header") and c.get("text") for c in row):
            continue
        out: dict[int, str] = {}
        for j, c in enumerate(row):
            if not c.get("text"):
                continue
            key = -1 if j == 0 else col_band.get(j)
            if key is None:
                log.append(f"header cell in TF column {j} maps to no band: {c['text']!r}")
                continue
            out[key] = c["text"] if key not in out else out[key]
        rows.append(out)
    return rows, log


def rebuild(tbl: dict, lines: list[list[dict]], opts: dict = OPTS) -> tuple[dict | None, list[str]]:
    log: list[str] = []
    lines = [merge_flags(ln) for ln in lines]
    cand = [i for i, ln in enumerate(lines) if body_values(ln)]
    if not cand:
        return None, ["no body lines"]

    # rung 1b (11.6): a no-data placeholder right of a body line's first value is column-position
    # evidence, as in the oracle's own band rule (``oracle.read_page``); a column printed only as
    # "NA" / "(s)" in some years otherwise has no band and its tokens join a neighbour's cells
    def evidence(ln: list[dict]) -> list[dict]:
        vals = body_values(ln)
        return vals + [
            t for t in ln[1:] if vals and t["text"] in orc.PLACEHOLDERS and t["x0"] > vals[0]["x0"]
        ]

    all_bands = cluster_bands([t for i in cand for t in evidence(lines[i])])
    # dense bands (>= max(2, 10 % of candidate lines) tokens) define the body; a number outside
    # them - a title's bill number, a footnote marker, a code inside a label - is text
    min_n = max(2, -(-len(cand) // 10))
    dense = [b for b in all_bands if b["n"] >= min_n]
    if not dense:
        return None, ["no dense band"]

    def in_bands(t: dict, bands: list[dict]) -> int | None:
        k = min(range(len(bands)), key=lambda i: abs(bands[i]["right"] - t["x1"]))
        return k if abs(bands[k]["right"] - t["x1"]) <= 1.5 * bands[k]["tol"] else None

    def prose(ln: list[dict]) -> bool:
        x_num = dense[0]["x0"] - dense[0]["tol"]
        words = [
            t
            for t in ln
            if t["x0"] >= x_num
            and sum(ch.isalpha() for ch in t["text"]) >= 2
            and t["text"] not in orc.PLACEHOLDERS
        ]
        return len(words) >= 2

    body_idx = [
        i
        for i in cand
        if any(in_bands(t, dense) is not None for t in body_values(lines[i]))
        and not prose(lines[i])
    ]
    if not body_idx:
        return None, ["no body lines in dense bands"]
    # safety fallbacks (the text grid assumes numeric columns right of one label): keep
    # TableFormer's table when that does not hold
    n_prose = sum(1 for i in cand if prose(lines[i]))
    if opts.get("safety", True) and n_prose > 0.2 * len(cand):
        return None, [f"safety: {n_prose}/{len(cand)} candidate lines are prose"]
    split_stubs = 0
    for i in body_idx:  # a text column = >= 2 gap-separated stub segments holding words
        stub_toks = [t for t in lines[i] if t["x1"] <= dense[0]["x0"]]
        segs: list[list[dict]] = []
        for t in stub_toks:
            if segs and t["x0"] - segs[-1][-1]["x1"] <= 2 * (t["bottom"] - t["top"]):
                segs[-1].append(t)
            else:
                segs.append([t])
        worded = [s for s in segs if any(sum(ch.isalpha() for ch in t["text"]) >= 2 for t in s)]
        if len(worded) >= 2:
            split_stubs += 1
    if opts.get("safety", True) and split_stubs >= 0.3 * len(body_idx):
        return None, [f"safety: text column ({split_stubs}/{len(body_idx)} stubs split by > 2 em)"]
    first, last = body_idx[0], body_idx[-1]
    header_region = [t for ln in lines[:first] for t in ln]

    def headed(b: dict) -> bool:  # +-2 pt, as header_cells and over_band
        return any(t["x1"] > b["x0"] - 2 and t["x0"] < b["x1"] + 2 for t in header_region)

    # a thin band right of the first dense band is a sparse column iff a header sits above it
    bands = [b for b in all_bands if b["n"] >= min_n or (b["x0"] > dense[0]["x0"] and headed(b))]
    if len(bands) < len(all_bands):
        log.append(f"{len(all_bands) - len(bands)} thin band(s) without a header taken as text")
    printed_cols = sum(1 for b in bands if headed(b))
    if opts["assert_bands"] and printed_cols != len(bands):
        return None, [
            f"band assertion: {len(bands)} bands vs {printed_cols} printed header columns"
        ]
    left = min(b["x0"] for b in bands)
    body_set = set(body_idx)

    def over_band(t: dict) -> bool:  # the same +-2 pt tolerance as header_cells
        return any(t["x1"] > b["x0"] - 2 and t["x0"] < b["x1"] + 2 for b in bands)

    # the column-header block ends at the last line above the body with a token over a band;
    # stub-only lines between it and the first body line are section headers, not header text
    hdr_end = max((i for i in range(first) if any(over_band(t) for t in lines[i])), default=-1)
    header_region = [t for ln in lines[: hdr_end + 1] for t in ln]
    stub_header = [t for t in header_region if not over_band(t)]
    # body rows (with wrapped labels and section headers)
    rows: list[dict] = []
    pending: list[dict] = []
    leading = (
        st.median(
            lines[b][0]["top"] - lines[a][0]["top"]
            for a, b in zip(body_idx, body_idx[1:], strict=False)
        )
        if len(body_idx) > 1
        else 10.0
    )
    for i in range(hdr_end + 1, last + 1):
        ln = lines[i]
        if i not in body_set:
            text_toks = list(ln)
            nxt = next((k for k in body_idx if k > i), None)
            if (
                opts["wrap"]
                and nxt is not None
                and lines[nxt][0]["top"] - ln[0]["top"] <= 1.5 * leading
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
        stub = pending + [t for t in ln if t["x1"] <= left + 0.5]
        pending = []
        cells: dict[int, list[dict]] = {}
        for t in ln:
            if t in stub:
                continue
            cells.setdefault(band_of(t, bands), []).append(t)
        rows.append({"stub": stub, "cells": cells})
    if pending:
        rows.append({"section": pending})
    # below the last numeric line: text rows are kept (a CBO summary's "Contains ... mandate? No");
    # the footer block - from the first Source / Note / footnote / legend line on - is cut
    for ln in lines[last + 1 :]:
        if FOOTER.match(ln[0]["text"]) or FOOTER.match(" ".join(t["text"] for t in ln[:2])):
            log.append(f"footer cut at: {' '.join(t['text'] for t in ln)[:60]!r}")
            break
        stub = [t for t in ln if t["x1"] <= left + 0.5]
        cells = {}
        for t in ln:
            if t not in stub:
                cells.setdefault(band_of(t, bands), []).append(t)
        rows.append({"stub": stub, "cells": cells} if cells else {"section": list(ln)})
    # emit
    out_cells: list[dict] = []
    r = 0
    hcells, nhead, hlog = header_cells(
        tbl, bands, lines[: hdr_end + 1], stub_header, opts["headers"], opts["header_check"]
    )
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
            out_cells.append(
                cell(
                    flag_space(fix_text(cell_text(toks))),
                    span_box(toks),
                    r,
                    b + 1,
                )
            )
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
    if opts.get("safety", True) and numeric_cells and multi > 0.02 * len(numeric_cells):
        return None, [f"safety: {multi}/{len(numeric_cells)} emitted cells hold >= 2 numbers"]
    new = copy.deepcopy(tbl)
    ncol = len(bands) + 1
    new["data"]["table_cells"] = out_cells
    new["data"]["num_rows"] = r
    new["data"]["num_cols"] = ncol
    new["data"]["grid"] = grid_of(out_cells, r, ncol)
    return new, log


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
    """A text-only line is the first part of a wrapped label (not a section header) iff it shows
    a continuation: it ends with "," "-" "(" "/" or a connector word, or the next line's label
    starts in lower case. A line ending in ":" is a section header."""
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


def check_headers(header_rows, header_region, bands) -> tuple[list[dict], list[str]]:
    """A band's header text must equal the page words over that band in the header region, no
    token more often than on the page; otherwise the page words replace it (logged)."""
    log = []
    per_band: dict[int, str] = {}
    for hr in header_rows:
        for k, text in hr.items():
            if k >= 0:
                per_band[k] = (per_band.get(k, "") + " " + text).strip()
    fixed = {}
    for k, b in enumerate(bands):
        page = [t for t in header_region if t["x1"] > b["x0"] - 2 and t["x0"] < b["x1"] + 2]
        pw = Counter(w for t in page for w in t["text"].split())
        tw = Counter((per_band.get(k) or "").split())
        if tw and not (tw - pw) and set(tw) == set(pw):
            continue
        fixed[k] = " ".join(t["text"] for t in sorted(page, key=lambda t: (t["top"], t["x0"])))
        log.append(f"header check band {k}: TF {per_band.get(k)!r} != page {fixed[k]!r}")
    if not fixed:
        return header_rows, log
    out = []
    for hr in header_rows:
        out.append({k: v for k, v in hr.items() if k < 0 or k not in fixed})
    if out:
        for k, text in fixed.items():
            out[-1][k] = text
    else:
        out = [dict(fixed)]
    return out, log


def grid_of(cells: list[dict], nrows: int, ncols: int) -> list[list[dict]]:
    empty = {"text": "", "column_header": False, "row_header": False, "bbox": None}
    grid = [[dict(empty) for _ in range(ncols)] for _ in range(nrows)]
    for c in cells:  # a spanning cell fills every position it covers, as Docling's grid does
        for r in range(c["start_row_offset_idx"], c["end_row_offset_idx"]):
            for j in range(c["start_col_offset_idx"], c["end_col_offset_idx"]):
                grid[r][j] = c
    return grid


LEADERS = ".…�\x08"


def lines_for(doc: dict, tbl: dict, pdf) -> list[list[dict]]:
    page, box = tg.table_box(doc, tbl)
    return tokens_in(pdf.pages[page - 1].chars, box)


def tokens_in(chars: list[dict], box: tuple[float, float, float, float]) -> list[list[dict]]:
    """The emitter's own tokeniser (the trigger's is frozen). Differs from ``trigger.tokens_in``
    in three ways found on the fired BUDGET/CBO tables: an explicit space character breaks a word
    (these PDFs encode spaces as zero-gap characters); a run of >= 2 leader glyphs - ".", "…",
    and U+FFFD / U+0008, as BUDGET's leaders decode - is dropped; a year range ("2025-2030") is not
    split as a negative."""
    x0, top, x1, bottom = box
    inside = [
        c
        for c in chars
        if x0 - 1 <= (c["x0"] + c["x1"]) / 2 <= x1 + 1
        and top - 1 <= (c["top"] + c["bottom"]) / 2 <= bottom + 1
    ]
    ink = [c for c in inside if c["text"].strip()]
    if not ink:
        return []
    med = st.median(c["size"] for c in ink)
    inside = [c for c in inside if not c["text"].strip() or c["size"] >= 0.75 * med]
    tol = 0.5 * st.median(c["bottom"] - c["top"] for c in ink)
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
                    toks.append(tg.make_token(cur))
                cur = []
                continue
            # 0.15 x size: BUDGET's condensed font sets words 0.24-0.27 x size apart with no space
            # character (DOD "Operatingforces"); letters inside a word sit at ~0
            if cur and c["x0"] - cur[-1]["x1"] > 0.15 * c["size"]:
                toks.append(tg.make_token(cur))
                cur = []
            in_run = ch in LEADERS and (
                (i > 0 and texts[i - 1] in LEADERS) or (i + 1 < len(ln) and texts[i + 1] in LEADERS)
            )
            if in_run:
                if cur:
                    toks.append(tg.make_token(cur))
                cur = []
                continue
            if ch in tg.MINUS and cur and cur[-1]["text"].isdigit():
                # a fused negative ("-0.02-0.02") splits; a code ("097-0118-0-1-051") or a year
                # range ("2025-2030") does not: split only with a decimal or comma on either side
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
                        toks.append(tg.make_token(cur))
                        cur = []
            cur.append(c)
        if cur:
            toks.append(tg.make_token(cur))
        # a lone "(" joins the next token when that one closes it ("( d)" -> "(d)", "( s)")
        joined: list[dict] = []
        for t in toks:
            if joined and joined[-1]["text"] == "(" and t["text"].endswith(")"):
                p = joined.pop()
                joined.append(tg.make_token(p["chars"] + t["chars"]))
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


def build_unit(unit: str, tables: list[int] | None, opts: dict = OPTS) -> tuple[dict, dict]:
    import pdfplumber

    doc = json.loads((PARSED / f"{unit}.json").read_text(encoding="utf-8"))
    pdf_path = next(RAW.rglob(f"{unit}.pdf"))
    logs: dict = {}
    with pdfplumber.open(pdf_path) as pdf:
        for ti in tables or []:
            tbl = doc["tables"][ti]
            new, log = rebuild(tbl, lines_for(doc, tbl, pdf), opts)
            logs[ti] = log if new is not None else ["FALLBACK (TableFormer table kept)"] + log
            if new is not None:
                doc["tables"][ti] = new
    return doc, logs
