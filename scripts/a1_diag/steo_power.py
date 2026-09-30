"""A1 step 0 (STEO) step 3 - oracle-power check: does the STEO oracle score known-bad tables low?

No real parser score is reported here (that is step 4). Synthetic failures are injected into two
bases and scored with ``steo_score.score_table`` on the whole-row-admitted cells:

* **control** - a perfect grid built from the printed text layer (every printed row, its label,
  its printed tokens at the printed column x; heading rows kept). It must score ~100 %: anything
  less is a scorer defect.
* **parse copy** - a deep copy of ``data/parsed/eia-pdf-steo_full.json`` (in memory; variant files
  go to ``reports/a1_diag/steo_power/``, never ``data/parsed``). Its unmodified score is not
  computed.

Variants (labels and cell boxes stay put; only value text moves):

* ``shift_down`` / ``shift_up`` - every body row's value cells take the next/previous data row's
  values (a one-row misregistration over the whole table);
* ``shift_mid`` - the same from the middle data row downward only (one row inserted mid-table);
  control only - on the parse copy its untouched top half would be a real-parse score;
* ``merge_pairs`` - consecutive data rows merged pairwise the way TableFormer merges on dense
  pages: one cell spanning both rows, stub and values joined ("13.32 105.5"), repeated in both grid
  rows as Docling's grid repeats a spanning cell.

    uv run --with pdfplumber python scripts/a1_diag/steo_power.py
"""

from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle as orc  # noqa: E402
import steo  # noqa: E402
import steo_score as ss  # noqa: E402

REPO = steo.REPO
OUT = REPO / "reports" / "a1_diag" / "steo_power"


def cell(text: str, x: float | None = None, top: float = 0.0, header: bool = False) -> dict:
    box = None if x is None else {"l": x - 8, "t": top, "r": x + 8, "b": top + 7}
    return {"text": text, "column_header": header, "row_header": False, "bbox": box}


def control_grid(page: int) -> list[list[dict]]:
    cols, _agree, rows, _defs = steo.read_table_page(steo.HELD_PDF, page)
    years = [cell(c.key[:4], c.x, header=True) for c in cols]
    quarters = [cell(f"Q{c.key[5]}" if len(c.key) == 6 else c.key, c.x, header=True) for c in cols]
    grid = [[cell("", header=True), *years], [cell("", header=True), *quarters]]
    heading = None
    for r in rows:
        if r.heading and r.heading != heading:
            heading = r.heading
            grid.append([cell(r.heading)] + [cell("") for _ in cols])
        grid.append(
            [cell(r.label_raw, 20, r.top)]
            + [cell(r.values.get(c.key, ""), c.x, r.top) for c in cols]
        )
    return grid


def data_rows(grid: list[list[dict]]) -> list[int]:
    return [
        r
        for r, row in enumerate(grid)
        if not any(c.get("column_header") for c in row)
        and any(orc.canon(t) for c in row[1:] for t in c.get("text", "").split())
    ]


def with_text(c: dict, text: str) -> dict:
    out = dict(c)
    out["text"] = text
    return out


def shift(grid: list[list[dict]], step: int, start_frac: float = 0.0) -> list[list[dict]]:
    """Value cells of data row k take the text of data row k - step (step 1: down)."""
    g = copy.deepcopy(grid)
    rows = data_rows(grid)
    start = int(len(rows) * start_frac)
    for k in range(start, len(rows)):
        src = k - step
        for j in range(1, len(g[rows[k]])):
            text = ""
            if start <= src < len(rows) and j < len(grid[rows[src]]):
                text = grid[rows[src]][j].get("text", "")
            g[rows[k]][j] = with_text(grid[rows[k]][j], text)
    return g


def merge_pairs(grid: list[list[dict]]) -> list[list[dict]]:
    g = copy.deepcopy(grid)
    rows = data_rows(grid)
    for a, b in zip(rows[0::2], rows[1::2], strict=False):
        for j in range(min(len(g[a]), len(g[b]))):
            ta, tb = grid[a][j].get("text", ""), grid[b][j].get("text", "")
            merged = with_text(grid[a][j], " ".join(t for t in (ta, tb) if t))
            merged["row_span"] = 2
            g[a][j] = merged
            g[b][j] = dict(merged)
    return g


VARIANTS = {
    "unmodified": None,
    "shift_down": lambda g: shift(g, 1),
    "shift_up": lambda g: shift(g, -1),
    "shift_mid": lambda g: shift(g, 1, 0.5),
    "merge_pairs": merge_pairs,
}


def main() -> int:
    admitted, detail = ss.load_oracle()
    doc = json.loads((REPO / "data" / "parsed" / f"{ss.UNIT}.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    totals: dict[tuple[str, str], Counter] = {}
    per_table: dict[tuple[str, str], list[float]] = {}
    for base in ("control", "parse copy"):
        for name, fn in VARIANTS.items():
            if base == "parse copy" and name in ("unmodified", "shift_mid"):
                continue  # the real-parse score is step 4's; shift_mid leaves half of it intact
            tot, fracs = Counter(), []
            variant_doc = copy.deepcopy(doc)
            for ti, d in sorted(detail.items()):
                cells = admitted.get(ti, [])
                grid = (
                    control_grid(d["page"])
                    if base == "control"
                    else doc["tables"][ti]["data"]["grid"]
                )
                grid = fn(grid) if fn else grid
                variant_doc["tables"][ti]["data"]["grid"] = grid
                res = ss.score_table({"data": {"grid": grid}}, d["page"], d["rows"], cells)
                tot.update(
                    {
                        k: res[k]
                        for k in ("cells", "strict", "lenient", "missing_row", "missing_col")
                    }
                )
                if res["cells"]:
                    fracs.append(res["strict"] / res["cells"])
            totals[(base, name)] = tot
            per_table[(base, name)] = fracs
            if base == "parse copy":
                (OUT / f"{name}.json").write_text(json.dumps(variant_doc), encoding="utf-8")
    lines = [
        "# STEO step 3 - oracle-power check (synthetic failures; no real parser score)",
        "",
        "Scored on the whole-row-admitted STEO cells (26 tables). `control` = a perfect grid built "
        "from the printed text layer; `parse copy` = the current parse with the failure injected "
        "(its unmodified score is step 4's and is not computed here).",
        "",
        "| base | variant | cells | strict | lenient | row not found | column not found | "
        "strict, worst table | strict, best table |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for (base, name), t in totals.items():
        f = per_table[(base, name)]
        lines.append(
            f"| {base} | {name} | {t['cells']} | **{t['strict'] / t['cells']:.1%}** | "
            f"{t['lenient'] / t['cells']:.1%} | {t['missing_row']} | {t['missing_col']} | "
            f"{min(f):.1%} | {max(f):.1%} |"
        )
    (REPO / "reports" / "a1_diag" / "steo_power.md").write_text("\n".join(lines) + "\n", "utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
