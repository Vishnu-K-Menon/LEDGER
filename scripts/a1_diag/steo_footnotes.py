"""The frozen list of footnoted STEO rows (council ruling 2026-09-29): read from the PRINTED page.

For every numbered STEO data table in the held ``steo_full.pdf`` (pp31-56: Tables 1-10b, 7d in two
parts), this reads, from the PDF text layer only:

* every footnote marker "(x)" on a printed row's label, and on a heading line - a heading's marker
  propagates to the rows below it until the next heading line;
* the footnote definitions at the foot of the table ("(a) Includes lease condensate."), wrapped
  lines joined.

Each footnoted printed row is identified by SERIES_ID through ``steo.match_rows`` (label match,
with value agreement deciding between repeated labels - never position). JSON ``SUPER`` is stored
raw beside the printed letter and is never used for anything.

The list is written to ``data/oracle/steo/2026-09/footnotes.json`` (tracked) and **frozen**: it is
committed before any admission runs, and admission reads it, never re-derives it.

    uv run --with pdfplumber python scripts/a1_diag/steo_footnotes.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import steo  # noqa: E402

OUT = steo.SNAP / "footnotes.json"
TABLE_HEAD = re.compile(r"^\s*Table\s+([0-9]+[a-z]?)(?:\s+part\s+(\d))?\.")


def table_pages(doc: dict) -> list[tuple[int, int, str]]:
    """(TableItem index, page, printed id) for the numbered data tables."""
    out = []
    for i, t in enumerate(doc["tables"]):
        page = t["prov"][0]["page_no"]
        for x in doc["texts"]:
            if x.get("prov") and x["prov"][0]["page_no"] == page:
                m = TABLE_HEAD.match(x.get("text", ""))
                if m and m.group(1) in steo.VIEW_OF_TABLE or (m and m.group(1) == "8"):
                    out.append((i, page, m.group(1)))
                    break
    return [(i, p, tid) for i, p, tid in out if p >= 31]  # pp3-5 are narrative tables


def view_of(table_id: str) -> int:
    return steo.VIEW_OF_TABLE.get(table_id) or steo.VIEW_OF_TABLE[table_id + "a"]  # 8 -> 8a


def main() -> int:
    doc = json.loads((steo.REPO / "data" / "parsed" / "eia-pdf-steo_full.json").read_text("utf-8"))
    entries, per_table = [], []
    for ti, page, tid in table_pages(doc):
        view = view_of(tid)
        _cols, _agree, rows, defs = steo.read_table_page(steo.HELD_PDF, page)
        matched = steo.match_rows(rows, steo.data_rows(view))
        n_marked = 0
        for row, rec, kind in matched:
            letters = row.markers
            if not letters:
                continue
            n_marked += 1
            entries.append(
                {
                    "table": tid,
                    "table_index": ti,
                    "page": page,
                    "view": view,
                    "printed_label": row.label_raw or row.label,
                    "series_id": rec.get("SERIES_ID") if rec else None,
                    "json_description": rec.get("DESCRIPTION") if rec else None,
                    "match": kind,
                    "printed_letters": letters,
                    "source": "row" if row.own_markers else f"heading: {row.heading[:80]}",
                    "footnotes": {k: defs.get(k, "(definition not found)") for k in letters},
                    "json_super_raw": rec.get("SUPER") if rec else None,
                }
            )
        per_table.append(
            {
                "table": tid,
                "table_index": ti,
                "page": page,
                "view": view,
                "printed_rows": len(rows),
                "footnoted_rows": n_marked,
                "definitions": len(defs),
                "unmatched_printed_rows": [r.label for r, rec, _ in matched if rec is None],
            }
        )
    body = {
        "frozen": True,
        "rule": "markers read from the printed page (row label, or heading propagating to the "
        "rows below until the next heading); JSON SUPER stored raw, never used",
        "source_pdf": {
            "path": steo.HELD_PDF.relative_to(steo.REPO).as_posix(),
            "sha256": __import__("hashlib").sha256(steo.HELD_PDF.read_bytes()).hexdigest(),
        },
        "tables": per_table,
        "rows": entries,
    }
    OUT.write_text(json.dumps(body, indent=1, ensure_ascii=False), encoding="utf-8")
    print(
        f"tables {len(per_table)}; footnoted rows {len(entries)}; "
        f"unmatched to a SERIES_ID {sum(1 for e in entries if not e['series_id'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
