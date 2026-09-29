"""A1 step 0 item 1 - direction of the merged cells on ERP-table4 / table22, from existing records.

No re-parse. Reads the saved parse (``data/parsed/``) and the held granule xls
(``reports/a1_digits/``) with ``erp_compare.py``'s mapping: xls sheet ``si`` <-> parsed
``tables[si]``, xls column ``c`` <-> parsed column ``c``, rows keyed by the year in the row label.

Every parsed cell holding >= 2 numbers is classified pair by pair (consecutive tokens):

* **horizontal** - both values sit on one xls row in adjacent columns (a column fusion, e.g. the
  Structures and Equipment of one year);
* **vertical** - both values sit in one xls column on adjacent data rows (a row merge, e.g. the
  same series in two consecutive years);
* **both** - the pair fits either reading (repeated values); **other** - neither.

Search is local: columns within +-1 of the parsed cell's column, rows within +-3 of the xls rows of
the years in the parsed row's label (all rows when the label carries no year). A cell's direction
is its pairs' directions (``mixed`` when they differ).

    uv run --with xlrd python scripts/a1_diag/erp_direction.py

Writes ``reports/a1_diag/erp_direction.md`` (gitignored).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import xlrd

REPO = Path(__file__).resolve().parents[2]
UNITS = ("govinfo-ERP-2026-table4", "govinfo-ERP-2026-table22")
YEAR = re.compile(r"(?<!\d)((?:19|20)\d\d)(?!\d)")


def norm(s: object) -> str | None:
    """erp_compare.py's norm: strip commas and dashes to one form, format floats to one decimal."""
    s = str(s).strip().replace(",", "").replace("–", "-").replace("−", "-")
    try:
        f = float(s)
    except ValueError:
        return None
    return f"{f:.1f}" if abs(f - round(f, 1)) < 1e-9 else f"{f:g}"


def xls_grid(sheet) -> list[list[str | None]]:
    return [[norm(sheet.cell_value(r, c)) for c in range(sheet.ncols)] for r in range(sheet.nrows)]


def year_rows(sheet) -> dict[str, int]:
    out = {}
    for r in range(sheet.nrows):
        m = re.fullmatch(r"\s*((?:19|20)\d\d)\.?\s*", str(sheet.cell_value(r, 0)))
        if m:
            out.setdefault(m.group(1), r)
    return out


def data_rows(grid) -> list[int]:
    return [r for r, row in enumerate(grid) if any(v is not None for v in row[1:])]


def classify_pair(a: str, b: str, col: int, rows: range, grid, drows: list[int]) -> str:
    pos_a = [
        (r, c)
        for r in rows
        for c in (col - 1, col, col + 1)
        if 0 <= c < len(grid[r]) and grid[r][c] == a
    ]
    pos_b = [
        (r, c)
        for r in rows
        for c in (col - 1, col, col + 1)
        if 0 <= c < len(grid[r]) and grid[r][c] == b
    ]
    nxt = {r: drows[i + 1] for i, r in enumerate(drows[:-1])}
    horizontal = any(ra == rb and abs(ca - cb) == 1 for ra, ca in pos_a for rb, cb in pos_b)
    vertical = any(
        ca == cb and (nxt.get(ra) == rb or nxt.get(rb) == ra)
        for ra, ca in pos_a
        for rb, cb in pos_b
    )
    if horizontal and vertical:
        return "both"
    return "horizontal" if horizontal else "vertical" if vertical else "other"


def main() -> int:
    lines = [
        "# A1 step 0, item 1 - ERP merge direction (existing records, no re-parse)",
        "",
        "Parsed cells holding >= 2 numbers in `data/parsed/`, located in the held granule xls "
        "(erp_compare.py's row/column mapping). Definitions in `scripts/a1_diag/erp_direction.py`.",
        "",
        "| unit | sheet | page | merged cells | horizontal (column fusion) | "
        "vertical (row merge) | mixed | both | other |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    examples: list[str] = []
    totals: Counter = Counter()
    for unit in UNITS:
        wb = xlrd.open_workbook(str(REPO / "reports" / "a1_digits" / f"{unit}.xls"))
        doc = json.loads((REPO / "data" / "parsed" / f"{unit}.json").read_text(encoding="utf-8"))
        for si in range(2):
            sheet = wb.sheet_by_index(si)
            grid = xls_grid(sheet)
            drows = data_rows(grid)
            yrows = year_rows(sheet)
            tbl = doc["tables"][si]
            page = tbl["prov"][0]["page_no"]
            label_of = {}
            for c in tbl["data"]["table_cells"]:
                if c["start_col_offset_idx"] == 0:
                    label_of[c["start_row_offset_idx"]] = c["text"]
            counts: Counter = Counter()
            for cell in tbl["data"]["table_cells"]:
                if cell["start_col_offset_idx"] == 0:
                    continue
                toks = [t for t in (norm(x) for x in cell["text"].split()) if t is not None]
                if len(toks) < 2:
                    continue
                label = label_of.get(cell["start_row_offset_idx"], "")
                anchors = [yrows[y] for y in YEAR.findall(label) if y in yrows]
                if anchors:
                    rows = range(max(0, min(anchors) - 3), min(len(grid), max(anchors) + 4))
                else:
                    rows = range(len(grid))
                col = cell["start_col_offset_idx"]
                kinds = {
                    classify_pair(a, b, col, rows, grid, drows)
                    for a, b in zip(toks, toks[1:], strict=False)
                }
                kind = kinds.pop() if len(kinds) == 1 else "mixed"
                counts[kind] += 1
                if len(examples) < 400:
                    examples.append(
                        f"| `{unit}` | {page} | r{cell['start_row_offset_idx']} "
                        f"c{col} | `{label[:24]}` | `{cell['text'][:28]}` | {kind} |"
                    )
            n = sum(counts.values())
            totals.update(counts)
            lines.append(
                f"| `{unit}` | {sheet.name} | {page} | {n} | {counts['horizontal']} | "
                f"{counts['vertical']} | {counts['mixed']} | {counts['both']} | {counts['other']} |"
            )
    n = sum(totals.values())
    lines += [
        f"| **all** | | | **{n}** | **{totals['horizontal']}** | **{totals['vertical']}** | "
        f"{totals['mixed']} | {totals['both']} | {totals['other']} |",
        "",
        "## `3.6 6.4`",
        "",
        *[e for e in examples if "`3.6 6.4" in e],
        "",
        "## Every merged cell (first 400)",
        "",
        "| unit | page | cell | row label | parsed text | direction |",
        "|---|---|---|---|---|---|",
        *examples,
    ]
    out = REPO / "reports" / "a1_diag" / "erp_direction.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:14]))
    print("\n".join(e for e in examples if "`3.6 6.4" in e))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
