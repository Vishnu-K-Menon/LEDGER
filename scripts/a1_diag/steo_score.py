"""Score a parse against the STEO cell oracle (whole-row admission, same edition; D-038).

STEO tables run the other way from MER: rows are series, columns are periods. For each STEO data
table this scores the parsed ``TableItem`` on the oracle's **admitted** cells
(``reports/a1_diag/oracle/cells.jsonl``, ``family == "STEO"``; rule in
``data/oracle/steo/2026-09/admission_rule.md``):

* **Rows.** A printed row is keyed by its label and occurrence - the k-th printed row with that
  label (labels repeat: "Industrial Sector", "Wind"). The parsed row with the same label (stub
  text, leader dots / footnote markers / unit parentheticals removed, ``steo.clean_label``) and the
  same occurrence is its match; failing an exact label, a prefix/suffix variant. A merged stub
  ("Gasoline Diesel Fuel") matches neither row, so both rows' cells fail.
* **Columns.** Each parsed column is assigned to the printed period column (``YYYY0q`` / ``YYYY``)
  nearest its numeric cells' x-centres, by majority; measured on the page from the cells' boxes.
* **Strict**: the parsed cell at (row, column) holds exactly the printed value. **Lenient**: the
  value appears anywhere in the matched parsed row (each token used once).
* **Header association**: the mapped parsed column's header stack contains the period's tokens
  ("Q1" and "2025" for 2025-Q1; "2025" for the year column).

    uv run --with pdfplumber python scripts/a1_diag/steo_score.py [--parsed-dir DIR] [--label X]
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
import steo  # noqa: E402

REPO = steo.REPO
UNIT = "eia-pdf-steo_full"


def stub_label(text: str) -> str:
    return steo.norm_label(steo.clean_label(text or "")[0])


def occurrence_keys(labels: list[str]) -> list[tuple[str, int]]:
    seen: Counter = Counter()
    out = []
    for lab in labels:
        seen[lab] += 1
        out.append((lab, seen[lab]))
    return out


def period_tokens(key: str) -> set[str]:
    return {key[:4], f"q{key[5]}"} if len(key) == 6 else {key}


def score_table(parsed: dict, page: int, printed_rows: list[dict], cells: list[dict]) -> dict:
    """``parsed``: the TableItem dict; ``printed_rows``: the oracle's row records in printed order
    (``steo_admission.json``); ``cells``: the oracle's admitted cells for this table."""
    cols, _agree, _rows, _defs = steo.read_table_page(steo.HELD_PDF, page)
    pitch = st.median(b.x - a.x for a, b in zip(cols, cols[1:], strict=False))
    grid = parsed["data"].get("grid") or []
    # printed rows: (label, occurrence) in printed order
    p_keys = occurrence_keys([steo.norm_label(r["label"]) for r in printed_rows])
    # parsed rows: stub labels, occurrence among rows that carry some numeric cell; a row whose
    # stub is only a unit is named by the heading row above it, as on the printed side
    parsed_labels = []
    heading = ""
    for row in grid:
        lab = stub_label(row[0].get("text", "")) if row else ""
        has_num = any(orc.canon(t) for c in row[1:] for t in c.get("text", "").split())
        if not has_num:
            heading = lab or heading
        parsed_labels.append((lab or heading) if has_num else "")
    q_keys = occurrence_keys(parsed_labels)
    exact = {k: r for r, k in enumerate(q_keys) if k[0]}
    by_label: dict[str, list[int]] = defaultdict(list)
    for r, (lab, _) in enumerate(q_keys):
        if lab:
            by_label[lab].append(r)
    row_of: dict[int, int] = {}
    used: set[int] = set()
    for i, key in enumerate(p_keys):
        r = exact.get(key)
        if r is None:  # a prefix/suffix variant of the label, same occurrence among those
            lab, occ = key
            cands = [
                rr
                for pl, rows in by_label.items()
                if pl.startswith(lab + " ")
                or pl.endswith(" " + lab)
                or lab.startswith(pl + " ")
                or lab.endswith(" " + pl)
                for rr in rows
            ]
            cands = [rr for rr in cands if rr not in used]
            r = cands[occ - 1] if len(cands) >= occ else None
        if r is not None and r not in used:
            row_of[i] = r
            used.add(r)
    # parsed columns -> printed period columns, by x
    votes: dict[int, Counter] = defaultdict(Counter)
    for row in grid:
        for j in range(1, len(row)):
            c = row[j]
            toks = c.get("text", "").split()
            if (
                c.get("column_header")
                or not toks
                or orc.canon(toks[0]) is None
                or not c.get("bbox")
            ):
                continue
            x = (c["bbox"]["l"] + c["bbox"]["r"]) / 2
            col = min(cols, key=lambda k: abs(k.x - x))
            if abs(col.x - x) <= 0.5 * pitch:
                votes[j][col.key] += 1
    col_of: dict[str, int] = {}
    for j in sorted(votes):
        col_of.setdefault(votes[j].most_common(1)[0][0], j)
    header: dict[int, set[str]] = defaultdict(set)
    for row in grid:
        for j, c in enumerate(row):
            if c.get("column_header") and c.get("text"):
                header[j] |= {w.lower() for w in re.findall(r"[A-Za-z0-9]+", c["text"])}
    strict = lenient = missing_row = missing_col = 0
    pools: dict[int, Counter] = {}
    for c in cells:
        r = row_of.get(c["row_index"])
        if r is None:
            missing_row += 1
            continue
        if r not in pools:
            pools[r] = Counter(
                t
                for cell in grid[r][1:]
                for t in (orc.canon(x) for x in cell.get("text", "").split())
                if t
            )
        if pools[r][c["value"]] > 0:
            pools[r][c["value"]] -= 1
            lenient += 1
        j = col_of.get(c["period"])
        if j is None or j >= len(grid[r]):
            missing_col += 1
            continue
        if orc.canon(grid[r][j].get("text", "").strip()) == c["value"]:
            strict += 1
    periods = sorted({c["period"] for c in cells})
    matched_headers = sum(
        1 for k in periods if k in col_of and period_tokens(k) <= header.get(col_of[k], set())
    )
    return {
        "cells": len(cells),
        "strict": strict,
        "lenient": lenient,
        "missing_row": missing_row,
        "missing_col": missing_col,
        "rows_matched": len(row_of),
        "printed_rows": len(printed_rows),
        "periods": len(periods),
        "periods_mapped": sum(1 for k in periods if k in col_of),
        "header_matched": matched_headers,
    }


def load_oracle() -> tuple[dict, dict]:
    cells = [json.loads(x) for x in (orc.OUT / "cells.jsonl").open(encoding="utf-8")]
    admitted = defaultdict(list)
    for c in cells:
        if c.get("family") == "STEO" and c["admitted"]:
            admitted[c["table_index"]].append(c)
    detail = {
        d["table_index"]: d
        for d in json.loads((orc.OUT / "steo_admission.json").read_text(encoding="utf-8"))
    }
    return admitted, detail


def score_document(doc: dict) -> list[dict]:
    admitted, detail = load_oracle()
    out = []
    for ti, d in sorted(detail.items()):
        res = score_table(doc["tables"][ti], d["page"], d["rows"], admitted.get(ti, []))
        res.update(table_index=ti, table_id=d["table_id"], page=d["page"])
        out.append(res)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--parsed-dir", default="data/parsed")
    ap.add_argument("--label", default="baseline")
    args = ap.parse_args()
    doc = json.loads((REPO / args.parsed_dir / f"{UNIT}.json").read_text(encoding="utf-8"))
    rows = score_document(doc)
    n = sum(r["cells"] for r in rows)
    s = sum(r["strict"] for r in rows)
    lnt = sum(r["lenient"] for r in rows)
    rates = [r["strict"] / r["cells"] for r in rows if r["cells"]]
    lines = [
        f"# STEO - parse vs the cell oracle (`{args.parsed_dir}`)",
        "",
        "Whole-row admission, same edition (STEO 2026-09 snapshot vs the September PDF). Never "
        "pooled with MER (per-cell admission, later edition) or ERP.",
        "",
        f"**STEO strict {s}/{n} = {s / n:.1%} · lenient {lnt / n:.1%}** over {len(rows)} tables; "
        f"row not found {sum(r['missing_row'] for r in rows):,} · column not found "
        f"{sum(r['missing_col'] for r in rows):,} (both counted as misses). Denominator = the "
        f"{n:,} admitted oracle cells, fixed. Pass rule is strict only; lenient is not a merge "
        "detector (steo_power.md).",
        "",
        f"Per-table strict: min {min(rates):.1%} · median {st.median(rates):.1%} · max "
        f"{max(rates):.1%}.",
        "",
        "| table | page | admitted cells | strict | lenient | rows matched | row not found | "
        "column not found | header assoc. |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['table_id']} | {r['page']} | {r['cells']} | "
            f"**{r['strict'] / r['cells']:.1%}** | {r['lenient'] / r['cells']:.1%} | "
            f"{r['rows_matched']}/{r['printed_rows']} | {r['missing_row']} | {r['missing_col']} | "
            f"{r['header_matched']}/{r['periods']} |"
        )
    out = REPO / "reports" / "a1_diag" / f"steo_score_{args.label}"
    out.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
