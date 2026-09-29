"""A1 diagnostics item 2 - merged-cell census over every parsed table. Reads only; no re-parse.

A cell is **merged** when its text holds >= 2 numeric tokens, by the owner's own ``nums()``
from ``reports/a1_scripts/pdf_recall.py`` (lifted by ``ast`` in ``run_owner_scripts.owner_nums``),
so this is the same test A1's merged-cell measure used. Rates are reported over all cells and over
**body** cells (neither ``column_header`` nor ``row_header``, the definition that reproduces A1's
body counts), overall, per source, per unit, and per table, plus by estimated OTSL sequence length
(``rows * cols + rows``) against TableFormer's caps: V2 generates 512 tokens, V1 1,024.

    uv run python scripts/a1_diag/census.py

Writes ``reports/a1_diag/census.md`` and ``reports/a1_diag/census_tables.csv`` (gitignored).
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_owner_scripts import REPO, is_body, owner_nums  # noqa: E402

PARSED = REPO / "data" / "parsed"
OUT = REPO / "reports" / "a1_diag"
BUCKETS = ((0, 512, "< 512"), (512, 1025, "512-1,024"), (1025, 10**9, "> 1,024"))


@dataclass
class Tally:
    tables: int = 0
    tables_hit: int = 0  # tables with >= 1 merged body cell
    cells: int = 0
    merged: int = 0
    body: int = 0
    merged_body: int = 0

    def add(self, other: Tally) -> None:
        for k in vars(self):
            setattr(self, k, getattr(self, k) + getattr(other, k))

    def row(self, label: str) -> str:
        def pct(a: int, b: int) -> str:
            return f"{a / b:.1%}" if b else "n/a"

        return (
            f"| {label} | {self.tables} | "
            f"{self.tables_hit} ({pct(self.tables_hit, self.tables)}) | "
            f"{self.cells:,} | {self.merged:,} | **{pct(self.merged, self.cells)}** | "
            f"{self.body:,} | {self.merged_body:,} | **{pct(self.merged_body, self.body)}** |"
        )


HEADER = [
    "| | tables | tables with a merged body cell | cells | merged | rate (all) | "
    "body cells | merged body | rate (body) |",
    "|---|---|---|---|---|---|---|---|---|",
]


def unit_sources() -> dict[str, str]:
    out = {}
    for line in (REPO / "data" / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line) if line.strip() else {}
        if rec.get("record") == "unit":
            out[rec["unit_id"]] = rec["source"]
    return out


def bucket(tokens: int) -> str:
    return next(label for lo, hi, label in BUCKETS if lo <= tokens < hi)


def main() -> int:
    nums = owner_nums((REPO / "reports" / "a1_scripts" / "pdf_recall.py").read_text("utf-8"))
    sources = unit_sources()
    total = Tally()
    by_source: dict[str, Tally] = defaultdict(Tally)
    by_unit: dict[str, Tally] = defaultdict(Tally)
    by_bucket: dict[str, Tally] = defaultdict(Tally)
    by_source_bucket: dict[tuple[str, str], Tally] = defaultdict(Tally)
    rows = []
    for path in sorted(PARSED.glob("*.json")):
        if path.name.endswith(".meta.json"):
            continue
        unit = path.stem
        doc = json.loads(path.read_text(encoding="utf-8"))
        for ti, tbl in enumerate(doc.get("tables", [])):
            data = tbl["data"]
            cells = data.get("table_cells", [])
            merged = [c for c in cells if len(nums(c.get("text", ""))) > 1]
            body = [c for c in cells if is_body(c)]
            merged_body = [c for c in body if len(nums(c.get("text", ""))) > 1]
            r, c = int(data.get("num_rows") or 0), int(data.get("num_cols") or 0)
            est = r * c + r
            t = Tally(
                1, int(bool(merged_body)), len(cells), len(merged), len(body), len(merged_body)
            )
            source = sources.get(unit, "?")
            for agg in (
                total,
                by_source[source],
                by_unit[unit],
                by_bucket[bucket(est)],
                by_source_bucket[(source, bucket(est))],
            ):
                agg.add(t)
            page = (tbl.get("prov") or [{}])[0].get("page_no", 0)
            rows.append(
                {
                    "unit": unit,
                    "source": sources.get(unit, "?"),
                    "table": f"#/tables/{ti}",
                    "page": page,
                    "rows": r,
                    "cols": c,
                    "est_otsl_tokens": est,
                    "cells": len(cells),
                    "merged": len(merged),
                    "body": len(body),
                    "merged_body": len(merged_body),
                    "rate_body": round(len(merged_body) / len(body), 4) if body else "",
                }
            )

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "census_tables.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    empty = sum(1 for x in rows if x["cells"] == 0)
    worst = sorted((x for x in rows if x["body"]), key=lambda x: -x["merged_body"])[:15]
    lines = [
        "# A1 diagnostics - merged-cell census (item 2)",
        "",
        f"Every table in `data/parsed/*.json`: **{total.tables}** ({empty} with zero cells). "
        "A cell is merged when it holds >= 2 numeric tokens by the owner's `nums()` "
        "(pdf_recall.py). Body = "
        "neither `column_header` nor `row_header`.",
        "",
        "## Overall",
        "",
        *HEADER,
        total.row("all tables"),
        "",
        "## Per source",
        "",
        *HEADER,
        *(by_source[s].row(s) for s in sorted(by_source)),
        "",
        "## By estimated OTSL length (rows x cols + rows; V2 cap 512, V1 cap 1,024)",
        "",
        *HEADER,
        *(by_bucket[label].row(label) for _, _, label in BUCKETS if label in by_bucket),
        "",
        "## Source x OTSL length (size and source are confounded; this separates them)",
        "",
        *HEADER,
        *(
            by_source_bucket[key].row(f"{key[0]} / {key[1]}")
            for key in sorted(
                by_source_bucket, key=lambda k: (k[0], [b[2] for b in BUCKETS].index(k[1]))
            )
            if by_source_bucket[key].cells
        ),
        "",
        "## Per unit",
        "",
        *HEADER,
        *(by_unit[u].row(f"`{u}`") for u in sorted(by_unit)),
        "",
        "## Fifteen tables with the most merged body cells",
        "",
        "| unit | table | page | rows x cols | est. OTSL | body | merged body | rate |",
        "|---|---|---|---|---|---|---|---|",
        *(
            f"| `{x['unit']}` | `{x['table']}` | {x['page']} | {x['rows']}x{x['cols']} | "
            f"{x['est_otsl_tokens']:,} | {x['body']} | {x['merged_body']} | {x['rate_body']:.1%} |"
            for x in worst
        ),
        "",
        "Per-table rows for all tables: `reports/a1_diag/census_tables.csv`.",
    ]
    (OUT / "census.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
