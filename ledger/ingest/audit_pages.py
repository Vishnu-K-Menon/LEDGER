"""A1 page-level probes that sit beside the cell audit (``reports/a1_tables.md``).

Three questions the owner asks before ruling on A1:

* **A1.3** - do the ERP decimal separators survive? One row of the same table verbatim under the
  configured ``docling_parse_v4`` parse (read from ``data/parsed/``) and under a one-off
  ``pypdfium2`` convert of the same PDF, written to ``reports/a1_pypdfium2/`` - **never** to
  ``data/parsed``, because nothing in this pass re-parses the corpus (D-032).
* **A1.4** - what did Docling emit for pages with no text layer, given ``do_ocr: false``?
* **A1.5** - a unit that produced no tables at all: does its PDF hold any, and what did Docling
  label them instead?

Every probe reports what it found; none of them scores anything (the verdicts are the owner's).
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from docling_core.types.doc import DoclingDocument
from pypdf import PdfReader

from ledger.config import Config

log = logging.getLogger(__name__)

REPLACEMENT = "�"


# ---- shared helpers --------------------------------------------------------------------------


def page_of(item) -> int:
    for prov in getattr(item, "prov", []) or []:
        if getattr(prov, "page_no", None):
            return int(prov.page_no)
    return 0


def rows_of(tbl) -> dict[int, list[str]]:
    """``{row index: cell texts left to right}`` from the parsed table cells."""
    rows: dict[int, list[tuple[int, str]]] = {}
    for cell in getattr(tbl.data, "table_cells", []) or []:
        r = int(getattr(cell, "start_row_offset_idx", 0) or 0)
        c = int(getattr(cell, "start_col_offset_idx", 0) or 0)
        rows.setdefault(r, []).append((c, str(getattr(cell, "text", "") or "")))
    return {r: [t for _, t in sorted(cells)] for r, cells in sorted(rows.items())}


def header_flags(tbl) -> tuple[int, bool]:
    """``(rows carrying column_header cells, whether any such row starts at row 0)``.

    This is what ``markdown.py::_count_header_rows`` keys on: a markdown serializer repeats the
    header rows it finds at the top of the table, so a header that does not start at row 0 means
    the repeated header would come out blank.
    """
    header_rows = {
        int(getattr(c, "start_row_offset_idx", 0) or 0)
        for c in getattr(tbl.data, "table_cells", []) or []
        if getattr(c, "column_header", False)
    }
    return len(header_rows), 0 in header_rows


def numeric_row(row: list[str], minimum: int = 3) -> bool:
    n = sum(1 for cell in row if any(ch.isdigit() for ch in cell))
    return n >= minimum


def page_char_counts(pdf: Path) -> dict[int, int]:
    """Characters pypdf extracts per 1-based page - 0 means no text layer on that page."""
    counts: dict[int, int] = {}
    reader = PdfReader(str(pdf))
    for i, page in enumerate(reader.pages, 1):
        try:
            counts[i] = len((page.extract_text() or "").strip())
        except Exception as exc:  # noqa: BLE001 - a broken page is data, not a crash
            log.warning("%s page %d: extract_text failed: %s", pdf.name, i, exc)
            counts[i] = -1
    return counts


def items_on_page(doc: DoclingDocument, page: int) -> Counter:
    """Label -> count for every item Docling placed on that page."""
    out: Counter = Counter()
    for attr in ("texts", "tables", "pictures"):
        for item in getattr(doc, attr, []) or []:
            if page_of(item) == page:
                out[str(getattr(item, "label", attr))] += 1
    return out


# ---- A1.3: the ERP decimal cross-check under both backends -----------------------------------


@dataclass
class RowComparison:
    unit_id: str
    table_ref: str
    row_index: int
    v4_row: list[str]
    other_row: list[str] | None
    other_backend: str
    note: str

    @property
    def v4_text(self) -> str:
        return " | ".join(self.v4_row)

    @property
    def other_text(self) -> str:
        return " | ".join(self.other_row) if self.other_row else "(not extracted)"


def first_numeric_row(tbl) -> tuple[int, list[str]] | None:
    for idx, row in rows_of(tbl).items():
        if numeric_row(row):
            return idx, row
    return None


def compare_backends(cfg: Config, repo: Path, unit_id: str, source: str) -> RowComparison | None:
    """One row of the unit's largest table, verbatim under ``docling_parse_v4`` and ``pypdfium2``.

    The second convert is a one-off into ``reports/a1_pypdfium2/``; ``data/parsed`` is untouched.
    """
    from ledger.ingest.parse import build_converter

    parsed = repo / cfg.paths.parsed_dir / f"{unit_id}.json"
    pdf = repo / cfg.paths.raw_dir / source / f"{unit_id}.pdf"
    if not parsed.exists() or not pdf.exists():
        return None
    doc = DoclingDocument.load_from_json(parsed)
    tables = list(getattr(doc, "tables", []) or [])
    if not tables:
        return None
    tbl = max(tables, key=lambda t: len(getattr(t.data, "table_cells", []) or []))
    picked = first_numeric_row(tbl)
    if picked is None:
        return None
    idx, v4_row = picked
    table_ref = str(tbl.self_ref)

    other, note = None, ""
    try:
        conv = build_converter(cfg, backend="pypdfium2")
        result = conv.convert(str(pdf))
        out_dir = repo / cfg.paths.reports_dir / "a1_pypdfium2"
        out_dir.mkdir(parents=True, exist_ok=True)
        result.document.save_as_json(out_dir / f"{unit_id}.json")
        others = list(getattr(result.document, "tables", []) or [])
        if others:
            twin = max(others, key=lambda t: len(getattr(t.data, "table_cells", []) or []))
            twin_rows = rows_of(twin)
            stub = v4_row[0].strip()
            match = next(
                (r for r, cells in twin_rows.items() if cells and cells[0].strip() == stub), idx
            )
            other = twin_rows.get(match)
            note = (
                f"matched by row stub {stub!r} at row {match}"
                if match != idx or stub
                else f"row index {idx}"
            )
        else:
            note = "pypdfium2 convert produced no tables"
    except Exception as exc:  # noqa: BLE001 - reported in the sheet, the sheet still ships
        note = f"pypdfium2 convert failed: {exc}"
    return RowComparison(unit_id, table_ref, idx, v4_row, other, "pypdfium2", note)


def a1_3_section(cfg: Config, repo: Path, units: list[tuple[str, str]]) -> list[str]:
    lines = [
        "## A1.3 - ERP digits under both PDF backends",
        "",
        "One row of the same table verbatim, as parsed by the configured backend and by a one-off "
        "`pypdfium2` convert (saved under `reports/a1_pypdfium2/`; `data/parsed` untouched). "
        f"`{REPLACEMENT!r}` in either row means the decimal separator was lost, the failure pypdf "
        "showed at T2.",
        "",
    ]
    for unit_id, source in units:
        cmp_ = compare_backends(cfg, repo, unit_id, source)
        if cmp_ is None:
            lines += [f"- `{unit_id}`: no parsed table to compare.", ""]
            continue
        lines += [
            f"### `{unit_id}` - `{cmp_.table_ref}` row {cmp_.row_index}",
            "",
            f"- `docling_parse_v4`: `{cmp_.v4_text}`",
            f"- `pypdfium2`: `{cmp_.other_text}`",
            f"- U+FFFD present: docling_parse_v4 **{REPLACEMENT in cmp_.v4_text}**, "
            f"pypdfium2 **{REPLACEMENT in cmp_.other_text}**",
            f"- note: {cmp_.note}",
            "",
        ]
    return lines


# ---- A1.4: pages with no text layer, do_ocr false --------------------------------------------


def a1_4_section(cfg: Config, repo: Path, units: list[tuple[str, str]]) -> list[str]:
    lines = [
        "## A1.4 - pages with no text layer (`do_ocr: false`)",
        "",
        "Pages where pypdf extracts zero characters, and what Docling emitted for them.",
        "",
        "| unit | pages | empty-text pages | what Docling emitted there |",
        "|---|---|---|---|",
    ]
    detail: list[str] = []
    for unit_id, source in units:
        pdf = repo / cfg.paths.raw_dir / source / f"{unit_id}.pdf"
        parsed = repo / cfg.paths.parsed_dir / f"{unit_id}.json"
        if not pdf.exists() or not parsed.exists():
            lines.append(f"| `{unit_id}` | - | - | not on disk |")
            continue
        counts = page_char_counts(pdf)
        blank = [p for p, n in counts.items() if n == 0]
        doc = DoclingDocument.load_from_json(parsed)
        labels: Counter = Counter()
        empty_pages = 0
        for p in blank:
            on_page = items_on_page(doc, p)
            if not on_page:
                empty_pages += 1
            labels.update(on_page)
        summary = (
            f"{empty_pages} page(s) with **no items at all**; "
            f"labels elsewhere: {dict(labels) or 'none'}"
        )
        lines.append(f"| `{unit_id}` | {len(counts)} | {len(blank)} | {summary} |")
        detail += [
            "",
            f"`{unit_id}`: empty-text pages {blank[:30]}"
            + (" (first 30)" if len(blank) > 30 else ""),
        ]
    return lines + detail + [""]


# ---- A1.5: a unit that produced no tables ----------------------------------------------------


def a1_5_section(cfg: Config, repo: Path, unit_id: str, source: str, pages: int = 2) -> list[str]:
    parsed = repo / cfg.paths.parsed_dir / f"{unit_id}.json"
    pdf = repo / cfg.paths.raw_dir / source / f"{unit_id}.pdf"
    lines = [
        f"## A1.5 - `{unit_id}`: zero tables detected",
        "",
    ]
    if not parsed.exists():
        return lines + ["Not parsed.", ""]
    doc = DoclingDocument.load_from_json(parsed)
    n_tables = len(list(getattr(doc, "tables", []) or []))
    all_labels = Counter(
        str(getattr(t, "label", "text")) for t in (getattr(doc, "texts", []) or [])
    )
    lines += [
        f"Docling detected **{n_tables} tables**. Text-item labels for the whole unit: "
        f"{dict(all_labels)}.",
        "",
    ]
    if pdf.exists():
        reader = PdfReader(str(pdf))
        tabular = 0
        for page in reader.pages:
            try:
                text = page.extract_text() or ""
            except Exception:  # noqa: BLE001
                continue
            for ln in text.splitlines():
                if len([tk for tk in ln.split() if any(ch.isdigit() for ch in tk)]) >= 3:
                    tabular += 1
        lines += [
            f"In the PDF text layer, **{tabular} lines** carry 3+ numeric tokens, i.e. read as "
            "tabular rows. Docling labelled them as shown below, not as table cells.",
            "",
        ]
    # two pages of evidence: the pages with the most items
    by_page: Counter = Counter()
    for t in getattr(doc, "texts", []) or []:
        by_page[page_of(t)] += 1
    for page, _ in by_page.most_common(pages):
        on_page = items_on_page(doc, page)
        lines += [f"### page {page}", "", f"item labels: {dict(on_page)}", ""]
        shown = 0
        for t in getattr(doc, "texts", []) or []:
            if page_of(t) == page and numeric_row(str(getattr(t, "text", "")).split(), 3):
                lines.append(
                    f"- `{getattr(t, 'label', '?')}` `{getattr(t, 'self_ref', '?')}`: "
                    f"`{str(getattr(t, 'text', ''))[:160]}`"
                )
                shown += 1
                if shown >= 4:
                    break
        lines.append("")
    return lines
