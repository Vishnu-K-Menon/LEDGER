"""A9 statistics (D-001, D-033 status 2026-09-19): ``table_chunk_share`` plus the parts —
chunks, table slices, distinct tables, prose chunks — per source and per unit, because the two
chunker switches push the share in opposite directions and the share alone hides which.
Written to ``reports/a9_pilot.md`` and printed at the D-001 stop."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Counts:
    units: int = 0
    pages: int = 0
    chunks: int = 0
    table_slices: int = 0
    prose_chunks: int = 0
    distinct_tables: int = 0
    mixed_chunks: int = 0
    table_slices_literal: int = 0  # D-033 literal rule: caption item excluded from "table"
    caption_only_chunks: int = 0  # D-036: chunks whose non-table items are captions/footnotes
    table_ids: set[str] = field(default_factory=set)

    @property
    def table_chunk_share(self) -> float:
        return (self.table_slices / self.chunks) if self.chunks else 0.0

    @property
    def table_chunk_share_literal(self) -> float:
        return (self.table_slices_literal / self.chunks) if self.chunks else 0.0


def read_chunks(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def tally(
    records: list[dict], pages_by_unit: dict[str, int]
) -> tuple[Counts, dict[str, Counts], dict[str, Counts]]:
    total, by_source, by_unit = Counts(), {}, {}
    for r in records:
        for bucket, key in ((by_source, r["source"]), (by_unit, r["unit_id"])):
            c = bucket.setdefault(key, Counts())
            _add(c, r)
        _add(total, r)
    for unit_id, c in by_unit.items():
        c.units = 1
        c.pages = pages_by_unit.get(unit_id, 0)
    for src, c in by_source.items():
        units = {r["unit_id"] for r in records if r["source"] == src}
        c.units = len(units)
        c.pages = sum(pages_by_unit.get(u, 0) for u in units)
    total.units = len({r["unit_id"] for r in records})
    total.pages = sum(pages_by_unit.get(u, 0) for u in {r["unit_id"] for r in records})
    for c in [total, *by_source.values(), *by_unit.values()]:
        c.distinct_tables = len(c.table_ids)
    return total, by_source, by_unit


def _add(c: Counts, r: dict) -> None:
    c.chunks += 1
    if r.get("chunk_type_literal", r["chunk_type"]) == "table":
        c.table_slices_literal += 1
    elif r["chunk_type"] == "table":
        # table under D-036, prose under the literal reading: the difference is exactly the
        # chunks whose only non-table items are captions/footnotes.
        c.caption_only_chunks += 1
    if r["chunk_type"] == "table":
        c.table_slices += 1
        c.table_ids.update(f"{r['unit_id']}::{t}" for t in r["table_refs"])
    else:
        c.prose_chunks += 1
    if r.get("mixed_items"):
        c.mixed_chunks += 1


def _row(name: str, c: Counts) -> str:
    return (
        f"| {name} | {c.units} | {c.pages} | {c.chunks} | {c.table_slices} | "
        f"{c.distinct_tables} | {c.prose_chunks} | {c.table_chunk_share:.3f} |"
    )


def render(
    total: Counts,
    by_source: dict[str, Counts],
    by_unit: dict[str, Counts],
    *,
    band: tuple[float, float],
    skipped: list[str],
    seconds: float,
    workers: int,
) -> str:
    lo, hi = band
    branch = (
        "IN BAND"
        if lo <= total.table_chunk_share <= hi
        else ("BELOW BAND" if total.table_chunk_share < lo else "ABOVE BAND")
    )
    head = (
        "| scope | units | pages | chunks | table slices | distinct tables | "
        "prose chunks | table share |"
    )
    sep = "|---|---|---|---|---|---|---|---|"
    lines = [
        "# A9 — pilot chunk statistics (D-001, D-033)",
        "",
        f"`table_chunk_share` = **{total.table_chunk_share:.3f}** · "
        f"band {lo:.2f}–{hi:.2f} · **{branch}**",
        "",
        f"Parsed {total.units} units, {total.pages} pages, {total.chunks} chunks in {seconds:.1f}s "
        f"({workers} worker(s)). Skipped (UNFETCHABLE, D-034): {skipped or 'none'}.",
        "",
        "**Counting rule: D-036.** `chunk_type = table` iff the chunk holds ≥ 1 table item and "
        "every other doc item is a caption or footnote — Docling emits the caption as its own "
        "item, so D-033's literal wording counted every unsplit table as prose. Primary above is "
        f"that rule: **{total.table_chunk_share:.3f}**. The literal reading, printed once for "
        f"comparison: **{total.table_chunk_share_literal:.3f}** ({total.table_slices_literal} of "
        f"{total.chunks} chunks). The difference is **{total.caption_only_chunks} caption-only "
        "chunks**. Nothing is re-chunked either way — this is a counting rule (D-032).",
        "",
        "## Per source",
        "",
        head,
        sep,
        *[_row(s, by_source[s]) for s in sorted(by_source)],
        _row("**TOTAL**", total),
        "",
        "## Per unit",
        "",
        head,
        sep,
        *[_row(u, by_unit[u]) for u in sorted(by_unit)],
    ]
    if total.mixed_chunks:
        lines += [
            "",
            f"**{total.mixed_chunks} chunks mix table and prose items** — D-033 expects zero.",
        ]
    return "\n".join(lines)
