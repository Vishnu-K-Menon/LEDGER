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
                out.append({"text": text, "x0": t[0]["x0"], "x1": t[-1]["x1"]})
        if out:
            lines.append(out)
    return lines


def year_of(key: str) -> int | None:
    m = re.search(r"(19|20)\d\d", key)
    return int(m.group(0)) if m else None


def main() -> int:
    import pdfplumber

    cells = [json.loads(x) for x in (orc.OUT / "cells.jsonl").open(encoding="utf-8")]
    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for c in cells:
        if c["admitted"] and c["unit"] in orc.MER_UNITS:
            groups[(c["unit"], c["table_index"])].append(c)
    results: list[dict] = []
    per_table: dict[str, Counter] = {}
    for (unit, ti), cs in sorted(groups.items()):
        doc = json.loads((REPO / "data" / "parsed" / f"{unit}.json").read_text("utf-8"))
        pg = orc.read_page(unit, "eia", ti, doc)  # the oracle's own bands for this table
        tbl = doc["tables"][ti]
        prov = tbl["prov"][0]
        with pdfplumber.open(REPO / "data" / "raw" / "eia" / f"{unit}.pdf") as pdf:
            page = pdf.pages[prov["page_no"] - 1]
            h = page.height
            bb = prov["bbox"]
            top, bottom = (
                (h - bb["t"], h - bb["b"])
                if bb.get("coord_origin", "BOTTOMLEFT") == "BOTTOMLEFT"
                else (bb["t"], bb["b"])
            )
            lines = raw_lines(page.chars, (bb["l"], top, bb["r"], bottom))
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
    strata = Counter((r["stratum"], r["outcome"]) for r in results)
    off = [r for r in results if r["outcome"] == "not on the line"]
    sample = random.Random(SEED).sample(off, min(30, len(off))) if off else []
    n = len(results)
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
        "| # | table | page | row label (printed) | period | expected | page prints on that line, "
        "in the cell's band | owner: provably != page? |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(sample, 1):
        lines_md.append(
            f"| {i} | {r['table']} | {r['page']} | {r['label']} | {r['period']} | "
            f"{r['expected']} | {r['page_prints_in_band']} | |"
        )
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
