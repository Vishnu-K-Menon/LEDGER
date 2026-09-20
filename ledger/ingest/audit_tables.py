"""A1 — the ten-table cell-integrity audit sheet (``reports/a1_tables.md``).

Selects parsed tables across sources (≥ ``parser.audit_min_cells`` cells in total; both ERP
granules and the CRPT unit included when present), lays the parsed cells out for the owner and
names the digit source to check them against: for ERP table granules the granule's
``download.xlsLink`` (the ``txtLink`` rendition is a ~350-byte stub), otherwise the PDF page.
**The verdicts are the owner's — this tool scores nothing.**
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from docling_core.types.doc import DoclingDocument

from ledger.config import Config
from ledger.ingest.http import Fetcher, govinfo_api_key
from ledger.ingest.manifest import ManifestRow, read_manifest

log = logging.getLogger(__name__)

PRIORITY_PREFIXES = ("govinfo-ERP-", "govinfo-CRPT-")


@dataclass
class TablePick:
    unit_id: str
    source: str
    table_ref: str
    page: int
    rows: int
    cols: int
    cells: int
    markdown: str
    digit_source: str


def _tables_of(doc: DoclingDocument) -> list:
    return list(getattr(doc, "tables", []) or [])


def _cells(tbl) -> tuple[int, int, int]:
    data = tbl.data
    r = int(getattr(data, "num_rows", 0) or 0)
    c = int(getattr(data, "num_cols", 0) or 0)
    return r, c, r * c


def _page(tbl) -> int:
    for prov in getattr(tbl, "prov", []) or []:
        if getattr(prov, "page_no", None):
            return int(prov.page_no)
    return 0


def pick_tables(cfg: Config, repo: Path, rows: list[ManifestRow]) -> list[TablePick]:
    """Largest table per unit, priority units first, then by size until n and the cell floor."""
    parsed_dir = repo / cfg.paths.parsed_dir
    per_unit: list[TablePick] = []
    by_id = {r.unit_id: r for r in rows}
    for path in sorted(parsed_dir.glob("*.json")):
        unit_id = path.stem
        row = by_id.get(unit_id)
        if row is None:
            continue
        try:
            doc = DoclingDocument.load_from_json(path)
        except Exception as exc:  # noqa: BLE001
            log.warning("%s: cannot load parsed json: %s", unit_id, exc)
            continue
        tables = _tables_of(doc)
        if not tables:
            continue
        best = max(tables, key=lambda t: _cells(t)[2])
        r, c, cells = _cells(best)
        try:
            md = best.export_to_markdown(doc)
        except Exception:  # noqa: BLE001 - older/newer signature
            md = best.export_to_markdown()
        per_unit.append(
            TablePick(unit_id, row.source, best.self_ref, _page(best), r, c, cells, md, "")
        )
    priority = [p for p in per_unit if p.unit_id.startswith(PRIORITY_PREFIXES)]
    rest = sorted((p for p in per_unit if p not in priority), key=lambda p: -p.cells)
    picks = (priority + rest)[: cfg.parser.audit_tables_n]
    return picks


def digit_source(
    cfg: Config, pick: TablePick, row: ManifestRow, fetcher: Fetcher | None, repo: Path
) -> str:
    """ERP granules: download the granule's xlsLink beside the sheet. Others: PDF page."""
    if row.source == "govinfo_erp" and row.granule_id and fetcher is not None:
        base = cfg.fetch.govinfo_base_url.rstrip("/")
        url = f"{base}/packages/{row.package_id}/granules/{row.granule_id}/xls"
        dest = repo / cfg.paths.reports_dir / "a1_digits" / f"{row.unit_id}.xls"
        try:
            fetcher.download(url, dest, source="govinfo", params={"api_key": govinfo_api_key()})
            return f"`{dest.relative_to(repo).as_posix()}` (granule download.xlsLink)"
        except Exception as exc:  # noqa: BLE001 - reported, the sheet still ships
            return f"xlsLink download failed: {exc}"
    raw = (repo / cfg.paths.raw_dir / row.source / f"{row.unit_id}.pdf").relative_to(repo)
    return f"`{raw.as_posix()}` page {pick.page}"


def build_sheet(
    cfg: Config, repo: Path, *, fetcher: Fetcher | None = None
) -> tuple[str, list[TablePick]]:
    _, rows = read_manifest(repo / cfg.paths.manifest)
    by_id = {r.unit_id: r for r in rows}
    picks = pick_tables(cfg, repo, rows)
    for p in picks:
        p.digit_source = digit_source(cfg, p, by_id[p.unit_id], fetcher, repo)
    total_cells = sum(p.cells for p in picks)
    lines = [
        "# A1 — table cell-integrity audit (D2, gated)",
        "",
        f"{len(picks)} tables · **{total_cells} cells** (floor {cfg.parser.audit_min_cells}) · "
        f"parser `{cfg.parser.name}`, TableFormer `{cfg.parser.table_mode}`, "
        f"backend `{cfg.parser.pdf_backend}`, OCR `{cfg.parser.do_ocr}`.",
        "",
        f"**Threshold: ≥ {cfg.parser.audit_cell_accuracy_min:.0%} of cells correct with header "
        "association.** The verdicts below are the owner's; this sheet reports what the parser "
        "produced and where to check it. Fail → `parser: paddleocr_vl`, re-audit.",
        "",
        "| # | unit | source | table | page | rows × cols | cells | digit source | "
        "cells correct? | header association? |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, p in enumerate(picks, 1):
        lines.append(
            f"| {i} | `{p.unit_id}` | {p.source} | `{p.table_ref}` | {p.page} | "
            f"{p.rows} × {p.cols} | {p.cells} | {p.digit_source} | ___ | ___ |"
        )
    lines += ["", "---", ""]
    for i, p in enumerate(picks, 1):
        lines += [
            f"## {i}. `{p.unit_id}` — `{p.table_ref}` "
            f"(page {p.page}, {p.rows}×{p.cols} = {p.cells} cells)",
            "",
            f"Digit source: {p.digit_source}",
            "",
            p.markdown,
            "",
        ]
    return "\n".join(lines), picks
