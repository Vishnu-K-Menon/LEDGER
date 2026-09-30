"""A1 step 0 item 3 - score a parse against the cell oracle (D-038): the number every rung is
measured against.

Scores the parse in ``--parsed-dir`` (default ``data/parsed``) on every **admitted** oracle cell in
``reports/a1_diag/oracle/cells.jsonl`` (item 2). Keys are (row, printed column) -> value.

* **Rows.** Each parsed grid row's stub text (column 0) becomes row keys, by the same rules the
  oracle used for the page (``A:<year>``, ``M:<year>-<mm>`` with the year carried down, and
  ``Q:<year>-<q>``). A merged label such as "2016 Total 2017 Total" or "February March" yields every
  key it holds, all pointing at that one parsed row, as ``erp_compare.py`` does with
  "1978 ... 1979".
  The first parsed row carrying a key is the one scored.
* **Columns.** Each parsed grid column is assigned to the printed column band holding the majority
  of its numeric cells, measured on the page from the cells' own boxes. A parsed column spanning two
  printed columns lands on one of them, and the other printed column has no parsed column, so its
  cells fail. Nothing is shifted to fit.
* **Strict** (``erp_compare.py``): the parsed cell at (row, column) holds exactly the oracle value.
  **Lenient** (``erp_lenient.py``): the value appears anywhere in the matched parsed row, each
  printed token used once.
* **Header association.** For each oracle column, the parsed ``column_header`` text of the column
  mapped to it - its leaf cell or its full header stack, whichever matches - is compared with the
  oracle's header (words of 3+ letters, units in parentheses dropped, line-break hyphens rejoined,
  one attached footnote letter allowed). It matches at >= 50 % overlap of the smaller word set.

    uv run --with pdfplumber python scripts/a1_diag/oracle_score.py
    uv run --with pdfplumber python scripts/a1_diag/oracle_score.py --parsed-dir <dir> --label <x>

Writes ``reports/a1_diag/oracle_score_<label>.md`` and ``.json`` (gitignored).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle as orc  # noqa: E402

REPO = orc.REPO
A1 = {"erp_strict": 0.557, "pdf_ceiling": 0.736, "combined": 0.674}
# the tuning set (D-038): 3.6 (sec3 p19) and 4.2b (sec4 p5). Reported apart, never in a held-out
# aggregate. STEO is scored by steo_score.py (whole-row admission); families are never pooled.
TUNING = {("eia-pdf-sec3", 19), ("eia-pdf-sec4", 5)}


def label_keys(label: str, state: dict) -> list[str]:
    """Every row key a (possibly merged) stub label holds, carrying the year across rows."""
    words = [w.strip(".:…� ") for w in label.split()]
    words = [w for w in words if w]
    keys: list[str] = []
    pending: str | None = None  # a year not yet consumed by a month, quarter or "Total"
    for w in words:
        low = w.lower()
        if orc.is_year(w):
            if pending:
                keys.append(f"A:{pending}")
            pending = w
            state["year"] = w
        elif low in orc.MONTHS and state.get("year"):
            keys.append(f"M:{state['year']}-{orc.MONTHS[low]:02d}")
            pending = None
        elif w in orc.ROMAN and state.get("year"):
            keys.append(f"Q:{state['year']}-{orc.ROMAN[w]}")
            pending = None
        elif low == "total" and state.get("year"):
            keys.append(f"A:{state['year']}")
            pending = None
    if pending:
        keys.append(f"A:{pending}")
    return keys


def words(text: str) -> set[str]:
    text = re.sub(r"\([^)]*\)", " ", text or "")
    text = re.sub(
        r"(\w)[-\u2010\u2011\u00ad\u2022] (\w)", r"\1\2", text
    )  # "Kero- sene", "Bio• mass"
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2}


def header_match(oracle_header: str, parsed_header: str) -> bool:
    """>= 50 % overlap of the smaller word set; a parsed word may carry one attached footnote
    letter ('HGLd', 'Fueld', 'TotalC' -> 'hgl', 'fuel', 'total')."""
    ow = words(oracle_header)
    pw = {w if w in ow or w[:-1] not in ow else w[:-1] for w in words(parsed_header)}
    return bool(ow and pw) and len(ow & pw) >= 0.5 * min(len(ow), len(pw))


def cell_x(cell: dict) -> float | None:
    bb = cell.get("bbox")
    return (bb["l"] + bb["r"]) / 2 if bb else None


def score_table(pg: orc.Page, tbl: dict, cells: list[dict]) -> dict:
    grid = tbl["data"].get("grid") or []
    ncol = max((len(r) for r in grid), default=0)
    # parsed row keys
    row_of: dict[str, int] = {}
    state: dict = {}
    for r, row in enumerate(grid):
        if not row:
            continue
        for k in label_keys(row[0].get("text", ""), state):
            row_of.setdefault(k, r)
    # parsed column -> printed band (majority of its numeric, non-header cells)
    votes: dict[int, Counter] = defaultdict(Counter)
    for row in grid:
        for j in range(1, len(row)):
            c = row[j]
            if (
                c.get("column_header")
                or orc.canon(c.get("text", "").split()[0] if c.get("text", "").split() else "")
                is None
            ):
                continue
            x = cell_x(c)
            if x is None:
                continue
            b = orc.band_index({"x0": x, "x1": x}, pg.bands)
            if b is not None:
                votes[j][b] += 1
    col_of_band: dict[int, int] = {}
    for j in sorted(votes):
        b = votes[j].most_common(1)[0][0]
        col_of_band.setdefault(b, j)
    # parsed header per parsed column, two readings: the LEAF (lowest column_header cell) and the
    # full STACK (every header row). A group header spanning several columns ("Fossil Fuels")
    # dilutes the stack; an oracle header that joins several header rows (ERP) needs the stack.
    leaf: dict[int, str] = {}
    stack: dict[int, str] = defaultdict(str)
    for row in grid:
        for j, c in enumerate(row):
            if c.get("column_header") and c.get("text"):
                leaf[j] = c["text"]
                stack[j] += " " + c["text"]
    strict = lenient = missing_row = missing_col = 0
    lenient_pool: dict[int, Counter] = {}
    for cell in cells:
        r = row_of.get(cell["row"])
        if r is None:
            missing_row += 1
            continue
        if r not in lenient_pool:
            lenient_pool[r] = Counter(
                t
                for c in grid[r][1:]
                for t in (orc.canon(x) for x in c.get("text", "").split())
                if t is not None
            )
        if lenient_pool[r][cell["value"]] > 0:
            lenient_pool[r][cell["value"]] -= 1
            lenient += 1
        j = col_of_band.get(cell["band"])
        if j is None or j >= len(grid[r]):
            missing_col += 1
            continue
        if orc.canon(grid[r][j].get("text", "").strip()) == cell["value"]:
            strict += 1
    # header association per oracle column
    oracle_cols = sorted({(c["col"], c["band"], c["header"]) for c in cells})
    matched = 0
    for _, band, header in oracle_cols:
        j = col_of_band.get(band)
        if j is not None and (
            header_match(header, leaf.get(j, "")) or header_match(header, stack.get(j, ""))
        ):
            matched += 1
    n = len(cells)
    return {
        "cells": n,
        "strict": strict,
        "lenient": lenient,
        "missing_row": missing_row,
        "missing_col": missing_col,
        "parsed_shape": f"{len(grid)}x{ncol}",
        "printed_cols": len(pg.bands),
        "mapped_cols": len(col_of_band),
        "header_cols": len(oracle_cols),
        "header_matched": matched,
    }


def index_strict(tbl: dict, cells: list[dict]) -> int:
    """erp_compare.py's column rule: oracle data column c <-> grid column c + 1 (col 0 = label)."""
    grid = tbl["data"].get("grid") or []
    row_of: dict[str, int] = {}
    state: dict = {}
    for r, row in enumerate(grid):
        if row:
            for k in label_keys(row[0].get("text", ""), state):
                row_of.setdefault(k, r)
    ok = 0
    for c in cells:
        r, j = row_of.get(c["row"]), c["col"] + 1
        if r is not None and j < len(grid[r]):
            ok += orc.canon(grid[r][j].get("text", "").strip()) == c["value"]
    return ok


def pct(a: int, b: int) -> str:
    return f"{a / b:.1%}" if b else "n/a"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--parsed-dir", default="data/parsed")
    ap.add_argument("--label", default="baseline")
    args = ap.parse_args()
    parsed = REPO / args.parsed_dir
    cells = [json.loads(line) for line in (orc.OUT / "cells.jsonl").open(encoding="utf-8")]
    admitted = [c for c in cells if c["admitted"] and c.get("family") != "STEO"]
    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for c in admitted:
        groups[(c["unit"], c["table_index"])].append(c)
    manifest = {}
    for line in (REPO / "data" / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line) if line.strip() else {}
        if rec.get("record") == "unit":
            manifest[rec["unit_id"]] = rec

    results = []
    docs: dict[str, dict] = {}
    for (unit, ti), cs in sorted(groups.items()):
        doc = docs.setdefault(unit, json.loads((parsed / f"{unit}.json").read_text("utf-8")))
        pg = orc.read_page(unit, manifest[unit]["source"], ti, doc)
        res = score_table(pg, doc["tables"][ti], cs)
        res.update(
            unit=unit,
            table_index=ti,
            table_id=cs[0]["table_id"],
            page=cs[0]["page"],
            source="ERP" if "ERP" in unit else "MER",
            set="tuning" if (unit, cs[0]["page"]) in TUNING else "held-out",
        )
        # ERP annual rows only - the population A1's 55.7 % was measured on
        if res["source"] == "ERP":
            annual = [c for c in cs if c["row"].startswith("A:")]
            sub = score_table(pg, doc["tables"][ti], annual)
            res["annual_cells"], res["annual_strict"] = sub["cells"], sub["strict"]
            res["annual_strict_index"] = index_strict(doc["tables"][ti], annual)
        results.append(res)

    def agg(rs: list[dict]) -> dict:
        return {
            k: sum(r[k] for r in rs)
            for k in (
                "cells",
                "strict",
                "lenient",
                "missing_row",
                "missing_col",
                "header_cols",
                "header_matched",
            )
        }

    lines = [
        f"# A1 step 0, item 3 - parse vs the cell oracle (`{args.parsed_dir}`)",
        "",
        "Admitted oracle cells only (item 2, A6). Strict / lenient per erp_compare.py / "
        "erp_lenient.py; definitions in `scripts/a1_diag/oracle_score.py`. MER: per-cell "
        "admission, later edition; ERP: same edition. Families are never pooled; the tuning "
        "set is never in a held-out row. Denominator = admitted cells; row/column not found "
        "count as misses.",
        "",
        "| | tables | oracle cells | strict | lenient | row not found | column not found | "
        "header association |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, rs in (
        ("MER held-out", [r for r in results if r["source"] == "MER" and r["set"] == "held-out"]),
        ("ERP held-out", [r for r in results if r["source"] == "ERP" and r["set"] == "held-out"]),
        ("tuning (3.6, 4.2b)", [r for r in results if r["set"] == "tuning"]),
    ):
        a = agg(rs)
        lines.append(
            f"| {name} | {len(rs)} | {a['cells']:,} | **{pct(a['strict'], a['cells'])}** | "
            f"{pct(a['lenient'], a['cells'])} | {a['missing_row']:,} | {a['missing_col']:,} | "
            f"{a['header_matched']}/{a['header_cols']} "
            f"({pct(a['header_matched'], a['header_cols'])}) |"
        )
    erp = [r for r in results if r["source"] == "ERP"]
    ac, as_ = sum(r["annual_cells"] for r in erp), sum(r["annual_strict"] for r in erp)
    ai = sum(r["annual_strict_index"] for r in erp)
    rates = [r["strict"] / r["cells"] for r in results if r["cells"] and r["set"] == "held-out"]
    buckets = Counter(
        ">= 95 %"
        if x >= 0.95
        else "90-95 %"
        if x >= 0.90
        else "75-90 %"
        if x >= 0.75
        else "50-75 %"
        if x >= 0.50
        else "< 50 %"
        for x in rates
    )
    lines += [
        "",
        f"Beside A1 (55.7 % ERP strict / 73.6 % PDF ceiling / 67.4 % combined): **ERP annual rows "
        f"only, the A1 population: {as_}/{ac} = {pct(as_, ac)} strict** with columns paired by "
        f"printed position; {ai}/{ac} = {pct(ai, ac)} with erp_compare.py's index pairing "
        "(a missing parsed column shifts every column to its right).",
        "",
        f"Per-table strict, held-out MER + ERP tables: min {min(rates):.1%} · median "
        f"{st.median(rates):.1%} · max {max(rates):.1%}; distribution "
        f"{dict(sorted(buckets.items()))}.",
        "",
        "| set | table | page | unit | parsed shape | printed cols | mapped | oracle cells | "
        "strict | lenient | row not found | col not found | header assoc. |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(results, key=lambda r: r["strict"] / r["cells"]):
        lines.append(
            f"| {r['set']} | {r['table_id']} | {r['page']} | `{r['unit']}` | {r['parsed_shape']} | "
            f"{r['printed_cols']} | {r['mapped_cols']} | {r['cells']} | "
            f"**{pct(r['strict'], r['cells'])}** | {pct(r['lenient'], r['cells'])} | "
            f"{r['missing_row']} | {r['missing_col']} | {r['header_matched']}/{r['header_cols']} |"
        )
    out = REPO / "reports" / "a1_diag" / f"oracle_score_{args.label}"
    out.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("\n".join(lines[:16]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
