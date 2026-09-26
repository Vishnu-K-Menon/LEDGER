"""A1 - the ten-table cell-integrity audit sheet (``reports/a1_tables.md``).

Selects parsed tables across sources (>= ``parser.audit_min_cells`` cells in total; the units named
in ``parser.audit_require_units`` always covered), lays the parsed cells out for the owner and names
the digit source to check them against: for ERP table granules the granule's ``download.xlsLink``
(the ``txtLink`` rendition is a ~350-byte stub), otherwise the PDF page.

Two things beyond the cell layout, because **dropped = missing = wrong** for A1:

* the **dropped-cell count per unit**, recovered from the parse log's ``MatchingPostProcessor``
  warnings by the parse window that contains each timestamp. It is *per unit* and not per table:
  the warning names no table, and its ``RxC`` figure is TableFormer's predicted grid, which
  MEASURED 2026-09-26 on ``govinfo-BUDGET-2026-DOD`` matches no parsed table for 4 of its 6
  warnings (no 215x6, 266x11, 49x7 or 49x8 among the unit's 495 tables) and matches 3 and 2 tables
  for the other two. A table whose shape equals a warning's grid is flagged *shape-consistent*,
  which is a hint and never an identification;
* the **``column_header`` flags** per table (how many rows carry them, and whether any starts at
  row 0), which is what decides whether a markdown serializer's repeated header would be blank.

The page-level probes A1.3-A1.5 live in ``audit_pages.py`` and are appended to the same sheet.
**The verdicts are the owner's - this tool scores nothing.**
"""

from __future__ import annotations

import fnmatch
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from docling_core.types.doc import DoclingDocument

from ledger.config import Config
from ledger.ingest.audit_pages import a1_3_section, a1_4_section, a1_5_section, header_flags
from ledger.ingest.http import Fetcher, govinfo_api_key
from ledger.ingest.manifest import ManifestRow, read_manifest

log = logging.getLogger(__name__)

PRIORITY_PREFIXES = ("govinfo-ERP-", "govinfo-CRPT-")

# A1.3 cross-checks the ERP granules; A1.4 the two units with blank pages; A1.5 the unit that
# produced no tables. Unit ids come from the manifest, these are the roles they fill.
A1_3_UNITS = ("govinfo-ERP-2026-table4", "govinfo-ERP-2026-table22")
A1_4_UNITS = ("govinfo-BUDGET-2027-FCS", "govinfo-BUDGET-2026-CROSSCUT")
A1_5_UNIT = "eia-pdf-sec13"


# ---- the parse log: dropped-cell warnings ----------------------------------------------------

WARN_RE = re.compile(
    r"(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+\s+MatchingPostProcessor\s+WARNING\s+"
    r"(?P<dropped>\d+) of (?P<total>\d+) pdf cells matched neither a row nor a column band "
    r"of the (?P<rows>\d+)x(?P<cols>\d+) grid"
)
STAMP_RE = re.compile(r"^\[(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\]")
PARSED_RE = re.compile(r"^\[(?P<ts>[^\]]+)\]\s+PARSED\s+\[\d+/\d+\]\s+(?P<unit>\S+)")


@dataclass
class DroppedWarning:
    ts: str
    dropped: int
    pdf_cells: int
    rows: int
    cols: int

    def render(self) -> str:
        return f"{self.dropped} of {self.pdf_cells} pdf cells ({self.rows}x{self.cols} grid)"


def read_log_text(path: Path) -> str:
    """PowerShell's ``Tee-Object`` writes UTF-16; a plain read (or grep) finds nothing in it."""
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    if raw[:4096].count(b"\x00") > 64:  # UTF-16 without a BOM
        return raw.decode("utf-16-le", errors="replace")
    return raw.decode("utf-8", errors="replace")


def warnings_by_unit(cfg: Config, repo: Path) -> dict[str, list[DroppedWarning]]:
    """Attribute each ``MatchingPostProcessor`` warning to the unit whose parse window holds it.

    The warning carries a timestamp and a grid size, never a unit or a table, so the ``PARSED``
    progress lines are the only link: unit *i*'s window runs from the previous progress line to
    its own.
    """
    out: dict[str, list[DroppedWarning]] = {}
    for path in sorted(repo.glob(cfg.parser.audit_log_glob)):
        text = read_log_text(path)
        pending: list[DroppedWarning] = []  # warnings seen since the last progress line
        for line in text.splitlines():
            line = line.strip()
            parsed = PARSED_RE.match(line)
            if parsed:
                unit = parsed.group("unit")
                out.setdefault(unit, []).extend(pending)
                pending = []
                continue
            if STAMP_RE.match(line):  # any other progress line closes the window too
                pending = []
                continue
            warn = WARN_RE.search(line)
            if warn:
                pending.append(
                    DroppedWarning(
                        warn.group("ts"),
                        int(warn.group("dropped")),
                        int(warn.group("total")),
                        int(warn.group("rows")),
                        int(warn.group("cols")),
                    )
                )
        if pending:
            log.warning("%s: %d warnings after the last PARSED line", path.name, len(pending))
    return out


# ---- candidate tables ------------------------------------------------------------------------


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
    digit_source: str = ""
    header_rows: int = 0
    header_at_row0: bool = False
    unit_dropped: int = 0  # dropped cells logged anywhere in this unit's parse (not this table's)
    shape_consistent: list[DroppedWarning] = field(default_factory=list)
    shape_note: str = ""

    def dropped_text(self) -> str:
        """Unit total, plus any warning whose grid happens to match this table's shape."""
        if not self.unit_dropped:
            return "0 in the unit"
        head = f"**{self.unit_dropped} in the unit**"
        if not self.shape_consistent:
            return f"{head}; none shape-consistent with this table"
        detail = "; ".join(w.render() for w in self.shape_consistent)
        tail = f" ({self.shape_note})" if self.shape_note else ""
        return f"{head}; shape-consistent: {detail}{tail}"


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


def _markdown(tbl, doc) -> str:
    try:
        return tbl.export_to_markdown(doc)
    except Exception:  # noqa: BLE001 - older/newer signature
        return tbl.export_to_markdown()


def wanted(cfg: Config, unit_id: str) -> int:
    """How many tables the coverage rule wants from this unit (0 = only a size candidate)."""
    for pattern, n in cfg.parser.audit_require_units.items():
        if unit_id == pattern or fnmatch.fnmatch(unit_id, pattern):
            return int(n)
    return 0


def unit_candidates(
    cfg: Config, doc: DoclingDocument, row: ManifestRow, warns: list[DroppedWarning], keep: int
) -> list[TablePick]:
    """The unit's shortlist, largest first. Zero-cell tables are no evidence and are dropped.

    Selection cannot prefer "the tables that dropped cells" because the log does not identify
    them (see the module docstring); more cells to check is the next best criterion.
    """
    tables = _tables_of(doc)
    if not tables:
        return []
    unit_dropped = sum(w.dropped for w in warns)
    info = []
    for tbl in tables:
        r, c, cells = _cells(tbl)
        if cells <= 0:  # CRPT's two "tables" are 0x0: nothing to audit
            continue
        same = [w for w in warns if (w.rows, w.cols) == (r, c)]
        note = ""
        if same:
            twins = sum(1 for t in tables if _cells(t)[:2] == (r, c))
            if twins > 1:
                note = f"{twins} tables in this unit share the {r}x{c} shape"
        info.append((tbl, r, c, cells, same, note))
    order = sorted(info, key=lambda x: -x[3])
    picks: list[TablePick] = []
    for tbl, r, c, cells, matched, note in order[: max(keep, 1)]:
        hdr_rows, at_row0 = header_flags(tbl)
        picks.append(
            TablePick(
                unit_id=row.unit_id,
                source=row.source,
                table_ref=str(tbl.self_ref),
                page=_page(tbl),
                rows=r,
                cols=c,
                cells=cells,
                markdown=_markdown(tbl, doc),
                header_rows=hdr_rows,
                header_at_row0=at_row0,
                unit_dropped=unit_dropped,
                shape_consistent=matched,
                shape_note=note,
            )
        )
    return picks


def pick_tables(cfg: Config, repo: Path, rows: list[ManifestRow]) -> list[TablePick]:
    """Required units first (``parser.audit_require_units``), then the largest tables until n."""
    parsed_dir = repo / cfg.paths.parsed_dir
    by_id = {r.unit_id: r for r in rows}
    warns = warnings_by_unit(cfg, repo)
    shortlists: dict[str, list[TablePick]] = {}
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
        keep = max(wanted(cfg, unit_id), 1)
        cands = unit_candidates(cfg, doc, row, warns.get(unit_id, []), keep)
        if cands:
            shortlists[unit_id] = cands
        del doc

    picked: list[TablePick] = []
    taken: dict[str, int] = {}
    for pattern, n in cfg.parser.audit_require_units.items():
        matches = [u for u in shortlists if u == pattern or fnmatch.fnmatch(u, pattern)]
        # a pattern such as `cbo-*` takes the unit with the largest table
        matches.sort(key=lambda u: -shortlists[u][0].cells)
        for unit_id in matches:
            free = [p for p in shortlists[unit_id] if p not in picked]
            for p in free[: int(n)]:
                if len(picked) < cfg.parser.audit_tables_n:
                    picked.append(p)
                    taken[unit_id] = taken.get(unit_id, 0) + 1
            if taken.get(unit_id):
                break  # one unit satisfies the pattern
    rest = sorted(
        (s[0] for u, s in shortlists.items() if u not in taken),
        key=lambda p: (0 if p.unit_id.startswith(PRIORITY_PREFIXES) else 1, -p.cells),
    )
    for p in rest:
        if len(picked) >= cfg.parser.audit_tables_n:
            break
        picked.append(p)
    return picked


# ---- the digit source ------------------------------------------------------------------------


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


# ---- the sheet -------------------------------------------------------------------------------


def log_section(cfg: Config, repo: Path, warns: dict[str, list[DroppedWarning]]) -> list[str]:
    """Every dropped-cell warning in the parse log, with the unit its window puts it in."""
    rows = [
        "| unit | time | dropped | of pdf cells | TableFormer grid | "
        "a parsed table of that shape? |",
        "|---|---|---|---|---|---|",
    ]
    dims_cache: dict[str, set[tuple[int, int]]] = {}
    for unit_id, ws in sorted(warns.items()):
        if not ws:
            continue
        if unit_id not in dims_cache:
            path = repo / cfg.paths.parsed_dir / f"{unit_id}.json"
            try:
                doc = DoclingDocument.load_from_json(path)
                dims_cache[unit_id] = {_cells(t)[:2] for t in _tables_of(doc)}
            except Exception:  # noqa: BLE001
                dims_cache[unit_id] = set()
        for w in ws:
            hit = (w.rows, w.cols) in dims_cache[unit_id]
            rows.append(
                f"| `{unit_id}` | {w.ts} | **{w.dropped}** | {w.pdf_cells} | "
                f"{w.rows}x{w.cols} | {'yes' if hit else '**no**'} |"
            )
    if len(rows) == 2:
        return ["_No dropped-cell warnings in the parse log._", ""]
    return rows + [""]


def build_sheet(
    cfg: Config, repo: Path, *, fetcher: Fetcher | None = None
) -> tuple[str, list[TablePick]]:
    _, rows = read_manifest(repo / cfg.paths.manifest)
    by_id = {r.unit_id: r for r in rows}
    picks = pick_tables(cfg, repo, rows)
    for p in picks:
        p.digit_source = digit_source(cfg, p, by_id[p.unit_id], fetcher, repo)
    total_cells = sum(p.cells for p in picks)
    warns = warnings_by_unit(cfg, repo)
    pilot_dropped = sum(w.dropped for ws in warns.values() for w in ws)
    lines = [
        "# A1 - table cell-integrity audit (D2, gated)",
        "",
        f"{len(picks)} tables · **{total_cells} cells** (floor {cfg.parser.audit_min_cells}) · "
        f"parser `{cfg.parser.name}`, TableFormer `{cfg.parser.table_mode}`, "
        f"backend `{cfg.parser.pdf_backend}`, OCR `{cfg.parser.do_ocr}`.",
        "",
        f"**Threshold: >= {cfg.parser.audit_cell_accuracy_min:.0%} of cells correct with header "
        "association.** The verdicts below are the owner's; this sheet reports what the parser "
        "produced and where to check it. Fail -> `parser: paddleocr_vl`, re-audit.",
        "",
        f"**Dropped cells logged over the whole 19-unit pilot: {pilot_dropped}** "
        f"(every warning listed below). A dropped cell is a PDF text cell that matched no "
        "row/column band of TableFormer's grid, so it is missing from the parse and for A1 "
        "dropped = missing = wrong. The count is **per unit, not per table** - see the module "
        "docstring: the warning names no table and its grid size is TableFormer's prediction, "
        "which matches no parsed table for 4 of DOD's 6 warnings.",
        "",
    ]
    lines += log_section(cfg, repo, warns)
    lines += [
        "**`column_header` flags** decide whether a repeated markdown header would be blank: "
        "`_count_header_rows` reads the header rows at the top of the table, so a table whose "
        "header cells do not start at row 0 has nothing to repeat.",
        "",
        "| # | unit | source | table | page | rows x cols | cells | dropped cells (unit) | "
        "header rows | header at row 0 | digit source | cells correct? | header association? |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, p in enumerate(picks, 1):
        lines.append(
            f"| {i} | `{p.unit_id}` | {p.source} | `{p.table_ref}` | {p.page} | "
            f"{p.rows} x {p.cols} | {p.cells} | {p.dropped_text()} | {p.header_rows} | "
            f"{'yes' if p.header_at_row0 else '**no**'} | {p.digit_source} | ___ | ___ |"
        )
    lines += ["", "---", ""]
    for i, p in enumerate(picks, 1):
        lines += [
            f"## {i}. `{p.unit_id}` - `{p.table_ref}` "
            f"(page {p.page}, {p.rows}x{p.cols} = {p.cells} cells)",
            "",
            f"Digit source: {p.digit_source}",
            "",
            f"Dropped cells: {p.dropped_text()} · `column_header` rows: {p.header_rows}, "
            f"starts at row 0: {p.header_at_row0}",
            "",
            p.markdown,
            "",
        ]
    lines += ["---", ""]
    a1_3 = [(u, by_id[u].source) for u in A1_3_UNITS if u in by_id]
    a1_4 = [(u, by_id[u].source) for u in A1_4_UNITS if u in by_id]
    for section, args in (
        (a1_3_section, (cfg, repo, a1_3)),
        (a1_4_section, (cfg, repo, a1_4)),
    ):
        try:
            lines += section(*args)
        except Exception as exc:  # noqa: BLE001 - a failed probe is reported, not fatal
            log.warning("%s failed: %s", section.__name__, exc)
            lines += [f"_{section.__name__} failed: {exc}_", ""]
    if A1_5_UNIT in by_id:
        try:
            lines += a1_5_section(cfg, repo, A1_5_UNIT, by_id[A1_5_UNIT].source)
        except Exception as exc:  # noqa: BLE001
            log.warning("a1_5_section failed: %s", exc)
            lines += [f"_a1_5_section failed: {exc}_", ""]
    return "\n".join(lines), picks
