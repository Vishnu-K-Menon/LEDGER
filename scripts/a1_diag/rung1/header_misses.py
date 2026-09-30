"""A2 (D-038 rung 1) - classify the MER/ERP header-association misses of the current parse.

Header association is ``oracle_score.py``'s: per oracle column (col, band, header), the parsed
column mapped to its band (majority of numeric body cells, by x) must carry a matching header in
its leaf cell or its full header stack. Every miss is classified, criteria fixed before running:

* **dropped column** - no parsed column is mapped to the oracle column's band;
* **body-caused** - a parsed column is mapped, and its header matches a DIFFERENT oracle column's
  header on the same table (the body cells pulled the mapping onto the wrong column);
* **garbled / fused header text** - a parsed column is mapped and its header matches no oracle
  column: fused with a neighbour's words, garbled, or empty (empty is counted as a sub-type).

Pre-committed rule (owner, 2026-09-30), on the MER misses: >= 50 % dropped column -> hybrid headers;
>= 50 % garbled -> text-layer headers; otherwise -> TableFormer headers.

    uv run --with pdfplumber python scripts/a1_diag/rung1/header_misses.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import oracle as orc  # noqa: E402
import oracle_score as osc  # noqa: E402

REPO = orc.REPO
OUT = REPO / "reports" / "a1_diag" / "rung1"


def mapping(pg: orc.Page, grid: list) -> dict[int, int]:
    """oracle_score.score_table's band -> parsed column mapping, unchanged."""
    votes: dict[int, Counter] = defaultdict(Counter)
    for row in grid:
        for j in range(1, len(row)):
            c = row[j]
            toks = c.get("text", "").split()
            if c.get("column_header") or orc.canon(toks[0] if toks else "") is None:
                continue
            x = osc.cell_x(c)
            if x is None:
                continue
            b = orc.band_index({"x0": x, "x1": x}, pg.bands)
            if b is not None:
                votes[j][b] += 1
    col_of_band: dict[int, int] = {}
    for j in sorted(votes):
        col_of_band.setdefault(votes[j].most_common(1)[0][0], j)
    return col_of_band


def main() -> int:
    cells = [json.loads(x) for x in (orc.OUT / "cells.jsonl").open(encoding="utf-8")]
    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for c in cells:
        if c["admitted"] and c.get("family") != "STEO":
            groups[(c["unit"], c["table_index"])].append(c)
    manifest = {}
    for line in (REPO / "data" / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line) if line.strip() else {}
        if rec.get("record") == "unit":
            manifest[rec["unit_id"]] = rec
    docs: dict[str, dict] = {}
    misses = []
    for (unit, ti), cs in sorted(groups.items()):
        doc = docs.setdefault(
            unit, json.loads((REPO / "data" / "parsed" / f"{unit}.json").read_text("utf-8"))
        )
        pg = orc.read_page(unit, manifest[unit]["source"], ti, doc)
        grid = doc["tables"][ti]["data"].get("grid") or []
        col_of_band = mapping(pg, grid)
        leaf: dict[int, str] = {}
        stack: dict[int, str] = defaultdict(str)
        for row in grid:
            for j, c in enumerate(row):
                if c.get("column_header") and c.get("text"):
                    leaf[j] = c["text"]
                    stack[j] += " " + c["text"]
        oracle_cols = sorted({(c["col"], c["band"], c["header"]) for c in cs})
        page = cs[0]["page"]
        fam = (
            "ERP"
            if "ERP" in unit
            else "MER tuning"
            if (unit, page) in {("eia-pdf-sec3", 19), ("eia-pdf-sec4", 5)}
            else "MER held-out"
        )

        def matches(header: str, j: int, leaf=leaf, stack=stack) -> bool:
            return osc.header_match(header, leaf.get(j, "")) or osc.header_match(
                header, stack.get(j, "")
            )

        for _col, band, header in oracle_cols:
            j = col_of_band.get(band)
            if j is not None and matches(header, j):
                continue
            if j is None:
                kind, sub = "dropped column", ""
            elif any(matches(h, j) for _c, b, h in oracle_cols if b != band):
                kind, sub = "body-caused", ""
            else:
                kind = "garbled / fused header text"
                sub = "empty" if not stack.get(j, "").strip() else "text"
            misses.append(
                {
                    "family": fam,
                    "unit": unit,
                    "table_index": ti,
                    "table_id": cs[0]["table_id"],
                    "page": page,
                    "band": band,
                    "oracle_header": header,
                    "parsed_col": j,
                    "parsed_leaf": leaf.get(j) if j is not None else None,
                    "parsed_stack": stack.get(j, "").strip() if j is not None else None,
                    "kind": kind,
                    "sub": sub,
                }
            )
    by = Counter((m["family"], m["kind"]) for m in misses)
    mer = [m for m in misses if m["family"] == "MER held-out"]
    mer_k = Counter(m["kind"] for m in mer)
    all_k = Counter(m["kind"] for m in misses)
    n = len(mer)
    if mer_k["dropped column"] >= 0.5 * n:
        choice = "hybrid (bands from the text layer; TableFormer header text mapped by x-overlap)"
    elif mer_k["garbled / fused header text"] >= 0.5 * n:
        choice = "text-layer headers"
    else:
        choice = "TableFormer headers"
    lines = [
        "# A2 - header-association misses of the current parse, classified",
        "",
        f"All misses: {len(misses)} (MER held-out {n}, MER tuning "
        f"{sum(m['family'] == 'MER tuning' for m in misses)}, ERP "
        f"{sum(m['family'] == 'ERP' for m in misses)}).",
        "",
        "| family | dropped column | garbled / fused | body-caused |",
        "|---|---|---|---|",
    ]
    for fam in ("MER held-out", "MER tuning", "ERP"):
        lines.append(
            f"| {fam} | {by[(fam, 'dropped column')]} | "
            f"{by[(fam, 'garbled / fused header text')]} | {by[(fam, 'body-caused')]} |"
        )
    lines.append(
        f"| **all** | {all_k['dropped column']} | {all_k['garbled / fused header text']} | "
        f"{all_k['body-caused']} |"
    )
    empty = sum(1 for m in misses if m["sub"] == "empty")
    lines += [
        "",
        f"Garbled / fused with an EMPTY parsed header: {empty}.",
        "",
        f"**Rule (on the MER held-out misses, n = {n}):** dropped {mer_k['dropped column']} "
        f"({mer_k['dropped column'] / n:.0%}), garbled {mer_k['garbled / fused header text']} "
        f"({mer_k['garbled / fused header text'] / n:.0%}), body-caused {mer_k['body-caused']} "
        f"({mer_k['body-caused'] / n:.0%}) -> **{choice}**. On all {len(misses)} misses: dropped "
        f"{all_k['dropped column'] / len(misses):.0%}, garbled "
        f"{all_k['garbled / fused header text'] / len(misses):.0%}.",
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "A2_header_misses.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "A2_header_misses.json").write_text(json.dumps(misses, indent=1), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
