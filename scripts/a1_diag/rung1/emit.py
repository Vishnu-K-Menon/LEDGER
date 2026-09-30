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
OUT = REPO / "data" / "parsed_rung1"
FLAGS = {"R", "E", "RE"}
OPTS = {"wrap": True, "headers": True, "assert_bands": True, "header_check": True}


def is_value(tok: dict) -> bool:
    return tg.numeric(tok["text"])


def fix_text(t: str) -> str:
    t = re.sub(r"(?<=\d)�(?=\d)", ".", t)
    return re.sub(r"(^|\s)(-?)�(?=\d)", r"\1\2.", t)


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


def body_values(line: list[dict]) -> list[dict]:
    vals = [t for t in line[1:] if is_value(t)]
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
    return [
        {
            "right": st.median(t["x1"] for t in b),
            "x0": min(t["x0"] for t in b),
            "x1": max(t["x1"] for t in b),
            "n": len(b),
            "tol": tol,
        }
        for b in bands
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


def tf_header_rows(tbl: dict, bands: list[dict]) -> tuple[list[dict], list[str]]:
    """TableFormer's column-header rows, each as {band index or -1 (stub): text}."""
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
    body_idx = [i for i, ln in enumerate(lines) if body_values(ln)]
    if not body_idx:
        return None, ["no body lines"]
    first, last = body_idx[0], body_idx[-1]
    vals = [t for i in body_idx for t in body_values(lines[i])]
    bands = cluster_bands(vals)
    header_region = [t for ln in lines[:first] for t in ln]
    printed_cols = sum(
        1 for b in bands if any(t["x1"] > b["x0"] and t["x0"] < b["x1"] for t in header_region)
    )
    if opts["assert_bands"] and printed_cols != len(bands):
        return None, [
            f"band assertion: {len(bands)} bands vs {printed_cols} printed header columns"
        ]
    left = min(b["x0"] for b in bands)
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
    for i in range(first, last + 1):
        ln = lines[i]
        vals_i = body_values(ln)
        if not vals_i:
            text_toks = [t for t in ln if t["x1"] <= left or not is_value(t)]
            nxt = next((k for k in body_idx if k > i), None)
            if (
                opts["wrap"]
                and nxt is not None
                and lines[nxt][0]["top"] - ln[0]["top"] <= 1.5 * leading
                and not any(is_value(t) for t in ln)
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
    # emit
    out_cells: list[dict] = []
    r = 0
    header_rows: list[dict] = []
    if opts["headers"]:
        header_rows, hlog = tf_header_rows(tbl, bands)
        log += hlog
    if opts["header_check"] and header_rows:
        header_rows, clog = check_headers(header_rows, header_region, bands)
        log += clog
    for hr in header_rows:
        for key, text in hr.items():
            c = 0 if key == -1 else key + 1
            x0, x1 = (bands[key]["x0"], bands[key]["x1"]) if key >= 0 else (tbl_left(tbl), left)
            out_cells.append(cell(fix_text(text), (x0, 0, x1, 0), r, c, header=True))
        r += 1
    for row in rows:
        if "section" in row:
            toks = row["section"]
            if toks:
                out_cells.append(
                    cell(
                        fix_text(" ".join(t["text"] for t in toks)),
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
                    fix_text(" ".join(t["text"] for t in row["stub"])),
                    span_box(row["stub"]),
                    r,
                    0,
                    row_header=True,
                )
            )
        for b, toks in row["cells"].items():
            out_cells.append(
                cell(fix_text(" ".join(t["text"] for t in toks)), span_box(toks), r, b + 1)
            )
        r += 1
    new = copy.deepcopy(tbl)
    ncol = len(bands) + 1
    new["data"]["table_cells"] = out_cells
    new["data"]["num_rows"] = r
    new["data"]["num_cols"] = ncol
    new["data"]["grid"] = grid_of(out_cells, r, ncol)
    return new, log


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
    for c in cells:
        grid[c["start_row_offset_idx"]][c["start_col_offset_idx"]] = c
    return grid


def lines_for(doc: dict, tbl: dict, pdf) -> list[list[dict]]:
    page, box = tg.table_box(doc, tbl)
    return tg.tokens_in(pdf.pages[page - 1].chars, box)


def build_unit(unit: str, tables: list[int] | None, opts: dict = OPTS) -> tuple[dict, dict]:
    import pdfplumber

    doc = json.loads((PARSED / f"{unit}.json").read_text(encoding="utf-8"))
    pdf_path = next((REPO / "data" / "raw").rglob(f"{unit}.pdf"))
    logs: dict = {}
    with pdfplumber.open(pdf_path) as pdf:
        for ti in tables or []:
            tbl = doc["tables"][ti]
            new, log = rebuild(tbl, lines_for(doc, tbl, pdf), opts)
            logs[ti] = log if new is not None else ["FALLBACK (TableFormer table kept)"] + log
            if new is not None:
                doc["tables"][ti] = new
    return doc, logs
