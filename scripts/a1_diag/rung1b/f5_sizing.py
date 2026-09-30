"""D-039 item 1 - A6 clause-(b) sizing on the BURNED pilot MER tables. Sizes; fixes nothing.

For every admitted MER cell (``reports/a1_diag/oracle/cells.jsonl``; the 47 pilot MER tables,
tuning included - all burned): is the expected value printed ON its row label's text line?

Raw text layer only (pdfplumber characters; this script must not import
``scripts/a1_diag/rung1/``):

* characters inside the table's bbox are grouped into lines by vertical centre (a new line when the
  centre moves more than half the median character height), and into tokens at space characters
  and at x-gaps wider than 0.15 x the character size; runs of leader dots are dropped;
* a line's row key is read exactly as admission reads it: ``oracle.row_key`` on the tokens left of
  the table's first oracle band, with the year carried down, called only for lines holding a
  number in a band, a repeated key voided (``oracle.read_page``'s rules);
* the value is **on the line** iff a token on the row's line canon-equals it
  (``oracle.canon``); **on the line only with a revision flag** iff it does after a leading or
  trailing R / E / RE is stripped; otherwise **not on the line**; or the **row line was not
  found** on the page.

Writes ``reports/a1_diag/rung1b/F5_sizing.md`` and ``.json``: counts overall, per table and by
stratum (row year <= 2023 / >= 2024), and a hand-check list of 30 not-on-line cells drawn with
seed 20260930 (table, page, printed row label, period, expected value, what the page prints on
that line inside the cell's band).

    uv run --with pdfplumber python scripts/a1_diag/rung1b/f5_sizing.py
"""

from __future__ import annotations

import json
import random
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import oracle as orc  # noqa: E402

REPO = orc.REPO
OUT = REPO / "reports" / "a1_diag" / "rung1b"
FLAG = re.compile(r"^(?:RE|R|E)(?=[\d(.\-])|(?<=[\d)])(?:RE|R|E)$")
SEED = 20260930


def raw_lines(chars: list[dict], box: tuple[float, float, float, float]) -> list[list[dict]]:
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
    tol = 0.5 * st.median(c["bottom"] - c["top"] for c in ink)
    groups: list[list[dict]] = []
    for c in sorted(inside, key=lambda c: (c["top"] + c["bottom"]) / 2):
        cy = (c["top"] + c["bottom"]) / 2
        if groups and abs(cy - groups[-1][0]["_cy"]) <= tol:
            groups[-1].append(c)
        else:
            groups.append([dict(c, _cy=cy)])
    lines = []
    for g in groups:
        g.sort(key=lambda c: c["x0"])
        toks: list[dict] = []
        cur: list[dict] = []
        for c in g:
            if not c["text"].strip():
                if cur:
                    toks.append(cur)
                cur = []
                continue
            if cur and c["x0"] - cur[-1]["x1"] > 0.15 * c["size"]:
                toks.append(cur)
                cur = []
            cur.append(c)
        if cur:
            toks.append(cur)
        out = []
        for t in toks:
            text = "".join(c["text"] for c in t)
            text = re.sub(r"[.…�]{2,}", "", text).strip()
            if text and not all(ch in ".…�·" for ch in text):
                out.append(
                    {
                        "text": text,
                        "x0": t[0]["x0"],
                        "x1": t[-1]["x1"],
                        "top": min(c["top"] for c in t),
                        "bottom": max(c["bottom"] for c in t),
                    }
                )
        if out:
            lines.append(out)
    return lines


def year_of(key: str) -> int | None:
    m = re.search(r"(19|20)\d\d", key)
    return int(m.group(0)) if m else None


def row_lines(unit: str, ti: int) -> dict:
    """One burned MER table: the raw lines inside its bbox, the oracle's bands, and the row key ->
    line map read as admission reads it (``oracle.read_page``'s rules). Also the page geometry,
    for the dump."""
    import pdfplumber

    doc = json.loads((REPO / "data" / "parsed" / f"{unit}.json").read_text("utf-8"))
    pg = orc.read_page(unit, "eia", ti, doc)  # the oracle's own bands for this table
    prov = doc["tables"][ti]["prov"][0]
    with pdfplumber.open(REPO / "data" / "raw" / "eia" / f"{unit}.pdf") as pdf:
        page = pdf.pages[prov["page_no"] - 1]
        h = page.height
        bb = prov["bbox"]
        top, bottom = (
            (h - bb["t"], h - bb["b"])
            if bb.get("coord_origin", "BOTTOMLEFT") == "BOTTOMLEFT"
            else (bb["t"], bb["b"])
        )
        box = (bb["l"], top, bb["r"], bottom)
        chars = list(page.chars)
        lines = raw_lines(chars, box)
    bands = pg.bands
    first = bands[0][0] if bands else float("inf")
    by_key: dict[str, list[dict]] = {}
    state: dict = {}
    seen: set[str] = set()
    for ln in lines:
        data = [
            t
            for t in ln
            if orc.canon(t["text"]) is not None
            and orc.band_index(t, bands) is not None
            and not (bands and t["x1"] < first)
        ]
        label = " ".join(t["text"] for t in ln if not bands or t["x1"] < first - 0.5)
        key = orc.row_key(label, state) if data else None
        if key and key in seen:
            key = None
        if key:
            seen.add(key)
            by_key[key] = ln
    return {
        "bands": bands,
        "first": first,
        "by_key": by_key,
        "lines": lines,
        "page_no": prov["page_no"],
        "box": box,
        "chars": chars,
    }


COMMITTED = {
    "on the line": 19093,
    "on the line only with a revision flag": 58,
    "not on the line": 610,
}  # row line not found: 0


def classify_off(off: list[dict]) -> dict[tuple, str]:
    """Band class of every not-on-the-line cell: the diagnosed class for the 23 anomalous cells
    (``F5_dump.json``), else numeric-but-different or placeholder (census rule: R / E / RE strip,
    attached or whitespace-separated)."""
    import f5_dump

    dumped = {}
    path = OUT / "F5_dump.json"
    if path.exists():
        for d in json.loads(path.read_text(encoding="utf-8")):
            dumped[(d["table"], d["row"], d["band_prints"], d["expected"])] = d["class"]
    anomalous = {id(c) for c in f5_dump.anomalous(off)}
    out = {}
    for c in off:
        key = (c["table"], c["row"], c["band"])
        if id(c) in anomalous:
            out[key] = dumped[(c["table"], c["row"], c["page_prints_in_band"], c["expected"])]
            continue
        toks = f5_dump.tolerant_tokens(c["page_prints_in_band"])
        placeholder = len(toks) == 1 and (toks[0] in orc.PLACEHOLDERS or toks[0] == "NA")
        out[key] = "placeholder (NA / (s))" if placeholder else "numeric-but-different"
    return out


def main() -> int:
    cells = [json.loads(x) for x in (orc.OUT / "cells.jsonl").open(encoding="utf-8")]
    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for c in cells:
        if c["admitted"] and c["unit"] in orc.MER_UNITS:
            groups[(c["unit"], c["table_index"])].append(c)
    results: list[dict] = []
    per_table: dict[str, Counter] = {}
    for (unit, ti), cs in sorted(groups.items()):
        rl = row_lines(unit, ti)
        bands, first, by_key = rl["bands"], rl["first"], rl["by_key"]
        tid = cs[0]["table_id"]
        t = per_table.setdefault(f"{tid} p{cs[0]['page']} ({unit})", Counter())
        for c in cs:
            ln = by_key.get(c["row"])
            if ln is None:
                outcome = "row line not found"
                printed = None
            else:
                canon_toks = [orc.canon(x["text"]) for x in ln]
                flag_toks = [orc.canon(FLAG.sub("", x["text"])) for x in ln]
                if c["value"] in canon_toks:
                    outcome = "on the line"
                elif c["value"] in flag_toks:
                    outcome = "on the line only with a revision flag"
                else:
                    outcome = "not on the line"
                band = (
                    bands[c["band"]] if c["band"] is not None and c["band"] < len(bands) else None
                )
                printed = (
                    " ".join(x["text"] for x in ln if band and orc.band_index(x, [band]) == 0)
                    or "(nothing in the band)"
                )
            y = year_of(c["row"])
            stratum = "row year <= 2023" if y and y <= 2023 else "row year >= 2024"
            t[outcome] += 1
            results.append(
                {
                    "table": tid,
                    "page": c["page"],
                    "unit": unit,
                    "row": c["row"],
                    "label": " ".join(x["text"] for x in ln if x["x1"] < first - 0.5)
                    if ln
                    else None,
                    "period": c["header"],
                    "band": c["band"],
                    "expected": c["value"],
                    "outcome": outcome,
                    "stratum": stratum,
                    "page_prints_in_band": printed,
                }
            )
    tot = Counter(r["outcome"] for r in results)
    # the committed totals (5f7e568): regeneration must not move admission
    assert dict(tot) == COMMITTED, (dict(tot), COMMITTED)
    strata = Counter((r["stratum"], r["outcome"]) for r in results)
    off = [r for r in results if r["outcome"] == "not on the line"]
    sample = random.Random(SEED).sample(off, min(30, len(off))) if off else []
    n = len(results)
    band_classes = classify_off(off)
    lines_md = [
        "# D-039 item 1 - A6 clause-(b) sizing on the burned pilot MER tables",
        "",
        "Admitted MER cells (A6: the value is printed somewhere in the table bbox), "
        "checked against "
        "the raw text layer: is the value printed on its own row label's line? Method: "
        "`scripts/a1_diag/rung1b/f5_sizing.py` docstring. Sizes only; nothing is fixed.",
        "",
        f"**{n:,} admitted MER cells on {len(groups)} tables (all burned).**",
        "",
        "| outcome | cells | share |",
        "|---|---|---|",
    ]
    for k in (
        "on the line",
        "on the line only with a revision flag",
        "not on the line",
        "row line not found",
    ):
        lines_md.append(f"| {k} | {tot[k]:,} | {tot[k] / n:.2%} |")
    lines_md += [
        "",
        "| stratum | on the line | flag only | not on the line | row not found |",
        "|---|---|---|---|---|",
    ]
    for s in ("row year <= 2023", "row year >= 2024"):
        lines_md.append(
            f"| {s} | {strata[(s, 'on the line')]:,} | "
            f"{strata[(s, 'on the line only with a revision flag')]:,} | "
            f"{strata[(s, 'not on the line')]:,} | {strata[(s, 'row line not found')]:,} |"
        )
    lines_md += [
        "",
        "Whitespace-tolerant strip measured read-only: 96 cells on the line → flag only; "
        "not-on-the-line set identical (610); admitted under the owner fill 19,151 under both. "
        "The checker keeps its committed single-token strip (D-039 status 2026-09-30).",
        "",
        "## Strata of the 610 not-on-the-line cells (D-039 status 2026-09-30)",
        "",
        "Band class per cell: the 23 anomalous cells from the diagnosis (`F5_dump.md`, crops "
        "checked); a single numeric band token after the R / E / RE strip (attached or "
        "whitespace-separated) = numeric-but-different; NA / (s) = placeholder.",
        "",
        "| band class | cells | conservative-strict miss? |",
        "|---|---|---|",
    ]
    miss = {
        "no-digit-at-position": "yes (decode defect)",
        "footnote-fused": "yes",
        "digit-on-other-line": "yes (checker geometry)",
        "split-token, joined == value": "yes (checker geometry)",
        "split-token, joined != value (numeric-but-different)": "no - numeric-but-different",
        "numeric-but-different": "no - out of the denominator when clause (b) is applied",
        "placeholder (NA / (s))": "no - page != export; with numeric-but-different",
        "outside": "OWNER RULING NEEDED (see F5_dump.md #20)",
    }
    for k, v in Counter(band_classes.values()).most_common():
        lines_md.append(f"| {k} | {v} | {miss[k]} |")
    n_miss = sum(1 for v in band_classes.values() if miss[v].startswith("yes"))
    lines_md += [
        "",
        f"Conservative-strict miss set (decode / footnote-fused / empty-band checker geometry / "
        f"split-token joined = value only): **{n_miss}** cells = {n_miss / n:.2%} of {n:,} "
        f"(reference bound 0.5 %); 1 cell (#20, `RF4`) awaits a ruling. Numeric-but-different and "
        "placeholder cells leave the denominator when clause (b) is applied to admission and are "
        "NOT in the miss set.",
        "",
        "## Per table",
        "",
        "| table | cells | not on the line | flag only | row not found |",
        "|---|---|---|---|---|",
    ]
    for k, c in per_table.items():
        lines_md.append(
            f"| {k} | {sum(c.values())} | {c['not on the line']} | "
            f"{c['on the line only with a revision flag']} | {c['row line not found']} |"
        )
    lines_md += [
        "",
        f"## Hand-check list: {len(sample)} not-on-the-line cells (seed {SEED})",
        "",
        "For each: does the page print the expected value on this row's line? (owner hand-check)",
        "",
        "| # | table | page | row key | row label (printed) | series (period column) | expected | "
        "page prints on that line, in the cell's band | band class | owner: provably != page? |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(sample, 1):
        lines_md.append(
            f"| {i} | {r['table']} | {r['page']} | {r['row']} | {r['label']} | {r['period']} | "
            f"{r['expected']} | {r['page_prints_in_band']} | "
            f"{band_classes[(r['table'], r['row'], r['band'])]} | |"
        )
    for r in off:
        r["band_class"] = band_classes[(r["table"], r["row"], r["band"])]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "F5_sizing.md").write_text("\n".join(lines_md) + "\n", encoding="utf-8")
    (OUT / "F5_sizing.json").write_text(
        json.dumps({"totals": dict(tot), "sample": sample, "cells": results}, indent=0),
        encoding="utf-8",
    )
    print("\n".join(lines_md[:18]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
