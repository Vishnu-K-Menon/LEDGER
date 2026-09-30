"""A1 step 0 item 2 - the cell oracle (D-038): publisher tables, admitted cell by cell.

Sources (D-038 item 1; the corpus stays PDF, these are the ORACLE only):

* **MER** (EIA sections 1/3/4/8/11/13): the per-table Excel export
  ``https://www.eia.gov/totalenergy/data/browser/xls.php?tbl=T<ss>.<nn><x>``. It mirrors the printed
  layout: an ``Annual Data`` and a ``Monthly Data`` sheet with one column per printed series.
* **STEO**: ``STEO_m.xlsx`` is fetched and recorded, but **not used**. Its sheets hold monthly
  values only, while the printed tables are quarterly and annual (Q1-Q4 and year for 2025-2027), so
  the printed values are not cells in the file. Deriving them needs an aggregation rule per series,
  which is out of scope here (reported, not built).
* **ERP**: the held granule xls in ``reports/a1_digits/`` (no refetch).

Every EIA fetch goes through ``ledger.ingest.http.Fetcher`` (UA, robots, 2 s delay), eia.gov only.
Each oracle file's URL, sha256, fetch time, sniffed type and stated release are recorded beside the
PDF's edition (manifest ``date_issued`` and the PDF ``CreationDate``).

**Page model.** For each parsed TableItem, the PDF words inside its bbox (pdfplumber, cropped as in
``pdf_recall.py``) are clustered into lines. Numeric tokens on lines with >= 3 numbers give column
bands. A leftmost band that is mostly years is the stub; the rest are data columns. Each line's stub
text gives a row key: ``A:<year>``, ``M:<year>-<month>`` (the year carried down from the block
heading) or ``Q:<year>-<q>`` (ERP quarters).

**Printed precision.** An explicit decimal ``number_format`` in the file is used where present;
otherwise the modal number of decimals the PDF prints in that column. Values round half-up. A
nonzero value that rounds to zero is MER's ``(s)`` and is no-data, like blanks, ``NA`` and
``......``.

**Admission (A6).** There is no edition alignment. An oracle cell (row key, column, value) is
admitted only if its rendered value appears among the PDF's numeric tokens inside the table bbox
(multiset: each printed token admits at most one cell). Revised cells drop out.
Coverage = admitted /
oracle cells on the printed rows, flagged below 90 %. The oracle columns map to data bands in order;
a count mismatch is reported and the table is not covered.

    uv run --with pdfplumber --with xlrd python scripts/a1_diag/oracle.py

Writes ``reports/a1_diag/oracle/`` (gitignored): ``src/`` downloads, ``sources.json``,
``cells.jsonl`` (every oracle cell with its admission) and ``coverage.md``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

OUT = REPO / "reports" / "a1_diag" / "oracle"
SRC = OUT / "src"
PARSED = REPO / "data" / "parsed"
MER_UNITS = (
    "eia-pdf-sec1",
    "eia-pdf-sec3",
    "eia-pdf-sec4",
    "eia-pdf-sec8",
    "eia-pdf-sec11",
    "eia-pdf-sec13",
)
STEO_UNIT = "eia-pdf-steo_full"
AEO_UNIT = "eia-pdf-AEO_Narrative"
ERP_UNITS = ("govinfo-ERP-2026-table4", "govinfo-ERP-2026-table22")
MER_URL = "https://www.eia.gov/totalenergy/data/browser/xls.php?tbl={tbl}"
STEO_URL = "https://www.eia.gov/outlooks/steo/xls/STEO_m.xlsx"
MONTHS = {
    m: i
    for i, m in enumerate(
        (
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ),
        start=1,
    )
}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())} | {"sept": 9})  # ERP prints "2024: Jan"
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4}
TABLE_ID = re.compile(r"\s*Table\s+([0-9]+\.[0-9]+[a-z]?)\b")
YEAR = re.compile(r"(?<!\d)((?:19|20)\d\d)(?!\d)")
FLAG_BELOW = 0.90
# printed no-data markers: they locate a column but are never values (D-038 item 1)
PLACEHOLDERS = {"(s)", "NA", "W", "–", "—", "-", "--", "(NA)", "(D)", "(X)", "(Z)", "*"}


# ---- tokens --------------------------------------------------------------------------------------


NUMBER = r"-?(?:\d+(?:\.\d+)?|\.\d+)"


def canon(tok: str) -> str | None:
    """Printed numeric token -> signed plain decimal ('8,170' -> '8170', '(5.0)' -> '-5.0').

    Two text-layer quirks are normalised, both confirmed against the oracle files:
    MER prints fractions without a leading zero ('.010' -> '0.010'), and pdfminer decodes the ERP
    PDFs' decimal-point glyph as U+FFFD ('61\\ufffd2' -> '61.2', '\\ufffd9' -> '0.9'). Docling's
    own backend reads the ERP glyph correctly; only this check's pdfplumber reading needs it.
    """
    t = tok.strip().replace(",", "").replace("−", "-").replace("–", "-")
    t = t.rstrip("*")
    t = re.sub(r"(?<=\d)�(?=\d)", ".", t)
    t = re.sub(r"^(-?)�(?=\d)", r"\1.", t)
    m = re.fullmatch(r"\((" + NUMBER + r")\)", t)
    if m:
        t = "-" + m.group(1).lstrip("-")
    if not re.fullmatch(NUMBER, t):
        return None
    t = re.sub(r"^(-?)\.", r"\g<1>0.", t)
    if re.fullmatch(r"-0+(?:\.0+)?", t):
        t = t[1:]
    return t


def decimals(tok: str) -> int:
    return len(tok.split(".")[1]) if "." in tok else 0


def render(value, dec: int) -> str | None:
    """Round half-up to ``dec`` places, canonical form; None for no-data or MER's (s)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        d = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    q = d.quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP)
    if q == 0 and d != 0:
        return None  # prints as (s): no-data, not a cell
    out = format(q, "f")
    return out[1:] if re.fullmatch(r"-0+(?:\.0+)?", out) else out


def format_decimals(fmt: str) -> int | None:
    """Decimals stated by an Excel number_format ('0.00' -> 2), or None for General/text."""
    if not fmt or fmt.lower() == "general" or "@" in fmt:
        return None
    m = re.search(r"0\.(0+)", fmt)
    if m:
        return len(m.group(1))
    return 0 if re.search(r"(^|[^.])0(?!\.)", fmt) else None


# ---- the printed page ----------------------------------------------------------------------------


@dataclass
class Line:
    key: str | None
    label: str
    tokens: list[dict]  # numeric pdfplumber words in data bands, with their band index


@dataclass
class Page:
    unit: str
    table_index: int
    page: int
    table_id: str | None
    bands: list[tuple[float, float]] = field(default_factory=list)  # data bands, stub excluded
    band_decimals: list[int | None] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)  # every canonical numeric token in the bbox
    noncanonical_digit_tokens: int = 0
    duplicate_keys: int = 0


def page_heading(doc: dict, page: int) -> tuple[str | None, str]:
    """(printed table id, heading text) from the first 'Table N.N...' text item on the page."""
    for t in doc.get("texts", []):
        if t.get("prov") and t["prov"][0]["page_no"] == page:
            m = TABLE_ID.match(t.get("text", ""))
            if m:
                return m.group(1), t["text"]
    return None, ""


def page_table_id(doc: dict, page: int) -> str | None:
    return page_heading(doc, page)[0]


def id_candidates(table_id: str) -> list[str]:
    """The printed id, plus 'l'/'i' readings when a trailing '1' may be a misread letter (3.31)."""
    out = [table_id]
    m = re.fullmatch(r"(\d+)\.(\d)1", table_id)
    if m:  # a letter suffix misread as '1'; the title check decides, so extra tries are safe
        out += [f"{m.group(1)}.{m.group(2)}{x}" for x in "lifghjk"]
    return out


def title_words(text: str) -> set[str]:
    text = re.sub(r"^\s*Table\s+\S+\s*", "", text or "")
    text = re.sub(r"\([^)]*\)", " ", text)  # units in parentheses are on the page, not the title
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2}


def export_title(path: Path) -> str:
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    for row in ws.iter_rows(min_row=1, max_row=14, max_col=1, values_only=True):
        if isinstance(row[0], str) and row[0].strip().startswith("Table "):
            return row[0].strip()
    return ""


def cluster(words: list[dict]) -> list[list[dict]]:
    if not words:
        return []
    tol = 0.5 * st.median(w["bottom"] - w["top"] for w in words)
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"] + w["bottom"]) / 2):
        cy = (w["top"] + w["bottom"]) / 2
        if lines and abs(cy - st.mean((x["top"] + x["bottom"]) / 2 for x in lines[-1])) <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(ln, key=lambda w: w["x0"]) for ln in lines]


def bands_of(words: list[dict]) -> list[tuple[float, float]]:
    spans = sorted((w["x0"], w["x1"]) for w in words)
    out: list[list[float]] = []
    for a, b in spans:
        if out and a <= out[-1][1] + 0.5:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def band_index(w: dict, bands: list[tuple[float, float]]) -> int | None:
    cx = (w["x0"] + w["x1"]) / 2
    for i, (a, b) in enumerate(bands):
        if a - 0.5 <= cx <= b + 0.5:
            return i
    return None


def is_year(tok: str) -> bool:
    return bool(re.fullmatch(r"(?:19|20)\d\d", tok))


def row_key(label: str, state: dict) -> str | None:
    """Stub text -> row key, carrying the year down through monthly and quarterly blocks."""
    words = [w.strip(".:…� ") for w in label.split()]
    words = [w for w in words if w]
    year = next((w for w in words if is_year(w)), None)
    if year:
        state["year"] = year
    low = [w.lower() for w in words]
    month = next((MONTHS[w] for w in low if w in MONTHS), None)
    roman = next((ROMAN[w] for w in words if w in ROMAN), None)
    cur = state.get("year")
    if month and cur:
        return f"M:{cur}-{month:02d}"
    if roman and cur:
        return f"Q:{cur}-{roman}"
    if "total" in low and cur and not any(re.search(r"\d-month", w) for w in low):
        return f"A:{cur}"
    if year and len([w for w in words if not is_year(w)]) <= 1:
        return f"A:{year}"
    return None


def read_page(unit: str, source: str, ti: int, doc: dict) -> Page:
    import pdfplumber

    tbl = doc["tables"][ti]
    prov = tbl["prov"][0]
    page_no = prov["page_no"]
    pg = Page(unit, ti, page_no, page_table_id(doc, page_no))
    with pdfplumber.open(REPO / "data" / "raw" / source / f"{unit}.pdf") as pdf:
        p = pdf.pages[page_no - 1]
        h = p.height
        bb = prov["bbox"]
        top, bottom = (
            (h - bb["t"], h - bb["b"])
            if bb.get("coord_origin", "BOTTOMLEFT") == "BOTTOMLEFT"
            else (bb["t"], bb["b"])
        )
        words = p.crop((bb["l"], top, bb["r"], bottom)).extract_words(x_tolerance=1)
    for w in words:
        c = canon(w["text"])
        if c is not None:
            pg.tokens.append(c)
        elif re.search(r"\d", w["text"]):
            pg.noncanonical_digit_tokens += 1
    lines = cluster(words)

    def cell_like(w: dict) -> bool:  # a value or a no-data placeholder: column-position evidence
        return canon(w["text"]) is not None or w["text"].strip() in PLACEHOLDERS

    body = [ln for ln in lines if sum(cell_like(w) for w in ln) >= 3]
    evidence = [w for ln in body for w in ln if cell_like(w)]
    bands = bands_of(evidence)
    if bands:
        # drop thin bands with little support: footnote and superscript digits, not columns
        support = Counter(band_index(w, bands) for w in evidence)
        floor = 0.2 * st.median(support[i] for i in range(len(bands)))
        bands = [b for i, b in enumerate(bands) if support[i] >= floor]
        first = [w["text"] for w in evidence if band_index(w, bands) == 0]
        if first and sum(is_year(t) for t in first) >= 0.8 * len(first):
            bands = bands[1:]  # the stub column of year labels
    pg.bands = bands
    per_band: dict[int, list[int]] = defaultdict(list)
    state: dict = {}
    seen: set[str] = set()
    for ln in lines:
        data = [
            w
            for w in ln
            if canon(w["text"]) is not None
            and band_index(w, bands) is not None
            and not (bands and w["x1"] < bands[0][0])
        ]
        label = " ".join(w["text"] for w in ln if not bands or w["x1"] < bands[0][0] - 0.5)
        key = row_key(label, state) if data else None
        if key and key in seen:
            pg.duplicate_keys += 1  # never score one oracle row twice
            key = None
        if key:
            seen.add(key)
            row = []
            for w in data:
                b = band_index(w, bands)
                c = canon(w["text"])
                per_band[b].append(decimals(c))
                row.append({"band": b, "text": w["text"], "canon": c})
            pg.lines.append(Line(key, label, row))
    pg.band_decimals = [
        Counter(per_band[i]).most_common(1)[0][0] if per_band.get(i) else None
        for i in range(len(bands))
    ]
    return pg


# ---- oracle files ------------------------------------------------------------------------


def sniff(b: bytes) -> str:
    if b[:4] == b"PK\x03\x04":
        return "OOXML (xlsx)"
    if b[:8] == bytes.fromhex("D0CF11E0A1B11AE1"):
        return "BIFF/OLE (xls)"
    if b.lstrip()[:1] == b"<":
        return "HTML (not a spreadsheet)"
    return "text/CSV"


def mer_tbl(table_id: str) -> str:
    a, rest = table_id.split(".")
    m = re.fullmatch(r"(\d+)([a-z]?)", rest)
    return f"T{int(a):02d}.{int(m.group(1)):02d}{m.group(2).upper()}"


def fetch(fetcher, url: str, dest: Path, sources: dict, meta: dict, refetch: bool) -> dict:
    rec = sources.get(url)
    if dest.exists() and rec and not refetch:
        return rec
    fetcher.download(url, dest, source="eia")
    b = dest.read_bytes()
    rec = {
        "url": url,
        "path": dest.relative_to(REPO).as_posix(),
        "sha256": hashlib.sha256(b).hexdigest(),
        "bytes": len(b),
        "fetched_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "type": sniff(b),
        **meta,
    }
    sources[url] = rec
    return rec


def release_of(ws) -> str:
    for r in range(1, 10):
        v = ws.cell(r, 1).value
        if isinstance(v, str) and "Release Date" in v:
            return v.strip()
    return ""


@dataclass
class OracleTable:
    rows: dict[str, list]  # row key -> values in data-column order
    headers: list[str]
    col_decimals: list[int | None]
    release: str = ""


def mer_oracle(path: Path) -> OracleTable:
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True)
    rows: dict[str, list] = {}
    headers: list[str] = []
    col_dec: list[int | None] = []
    release = ""
    for ws in wb.worksheets:
        release = release or release_of(ws)
        hdr_row = next(
            (
                r
                for r in range(1, 20)
                if str(ws.cell(r, 1).value or "").strip() in ("Month", "Annual Total", "Year")
            ),  # "Year" on annual-only tables (1.7-1.10)
            None,
        )
        if hdr_row is None:
            continue
        ncol = ws.max_column
        hdr = [str(ws.cell(hdr_row, c).value or "").strip() for c in range(2, ncol + 1)]
        units = [str(ws.cell(hdr_row + 1, c).value or "").strip() for c in range(2, ncol + 1)]
        headers = headers or [f"{h} {u}".strip() for h, u in zip(hdr, units, strict=True)]
        monthly = str(ws.cell(hdr_row, 1).value).strip() == "Month"
        for r in range(hdr_row + 2, ws.max_row + 1):
            v = ws.cell(r, 1).value
            if isinstance(v, dt.datetime) and monthly:
                key = f"M:{v.year}-{v.month:02d}"
            elif v is not None and re.fullmatch(r"\d{4}", str(v).strip()) and not monthly:
                key = f"A:{str(v).strip()}"
            else:
                continue
            rows[key] = [ws.cell(r, c).value for c in range(2, ncol + 1)]
            if not col_dec:
                col_dec = [format_decimals(ws.cell(r, c).number_format) for c in range(2, ncol + 1)]
    return OracleTable(rows, headers, col_dec, release)


def erp_oracle(path: Path, sheet_index: int) -> OracleTable:
    import xlrd

    wb = xlrd.open_workbook(str(path), formatting_info=True)
    sh = wb.sheet_by_index(sheet_index)
    rows: dict[str, list] = {}
    state: dict = {}
    header_rows = []
    col_dec: list[int | None] = [None] * (sh.ncols - 1)
    for r in range(sh.nrows):
        label = str(sh.cell_value(r, 0))
        vals = [sh.cell_value(r, c) for c in range(1, sh.ncols)]
        numeric = [v for v in vals if isinstance(v, float)]
        if not numeric:
            if r < 8:
                header_rows.append([str(v).strip() for v in vals])
            continue
        key = row_key(label.replace("�", " "), state)
        if key and key not in rows:
            rows[key] = [v if isinstance(v, float) else None for v in vals]
            for c in range(1, sh.ncols):
                xf = wb.xf_list[sh.cell_xf_index(r, c)]
                fmt = wb.format_map[xf.format_key].format_str
                d = format_decimals(fmt)
                if d is not None and col_dec[c - 1] is None:
                    col_dec[c - 1] = d
    headers = [
        " ".join(h[i] for h in header_rows if i < len(h) and h[i]).strip()
        for i in range(sh.ncols - 1)
    ]
    return OracleTable(rows, headers, col_dec)


# ---- admission ---------------------------------------------------------------------------


def _admit_with(
    pg: Page, orc: OracleTable, unit: str, source_file: str, mapping: dict[int, int]
) -> list[dict]:
    """One admission pass; ``mapping`` = oracle column -> printed data band."""
    pool = Counter(pg.tokens)
    cells = []
    for ln in pg.lines:
        values = orc.rows.get(ln.key)
        if values is None:
            continue
        for c, v in enumerate(values):
            b = mapping.get(c)
            if b is None:
                continue
            own = orc.col_decimals[c] if c < len(orc.col_decimals) else None
            dec = own if own is not None else pg.band_decimals[b]
            if dec is None:
                continue
            rendered = render(v, dec)
            if rendered is None:
                continue
            ok = pool[rendered] > 0
            if ok:
                pool[rendered] -= 1
            cells.append(
                {
                    "unit": unit,
                    "table_index": pg.table_index,
                    "page": pg.page,
                    "table_id": pg.table_id,
                    "row": ln.key,
                    "col": c,
                    "band": b,
                    "header": orc.headers[c] if c < len(orc.headers) else "",
                    "value": rendered,
                    "admitted": ok,
                    "oracle_file": source_file,
                }
            )
    return cells


def admit(pg: Page, orc: OracleTable, unit: str, source_file: str) -> tuple[list[dict], str]:
    """Oracle cells on the printed rows, each admitted if its rendered value is printed in the bbox.

    Oracle columns map to printed bands in order. When the export carries up to two series the page
    does not print, the unprinted columns are chosen by value agreement: every choice is tried and
    the alignment that admits the most cells wins (reported in the note).
    """
    from itertools import combinations

    ncols = len(next(iter(orc.rows.values()))) if orc.rows else 0
    nb = len(pg.bands)
    if ncols == nb:
        return _admit_with(pg, orc, unit, source_file, {c: c for c in range(ncols)}), ""
    if not 0 < ncols - nb <= 2 or nb == 0:
        return [], f"column count: oracle {ncols} vs printed {nb}"
    best, best_drop = None, None
    for drop in combinations(range(ncols), ncols - nb):
        kept = [c for c in range(ncols) if c not in drop]
        cells = _admit_with(pg, orc, unit, source_file, dict(zip(kept, range(nb), strict=True)))
        score = sum(x["admitted"] for x in cells)
        if best is None or score > sum(x["admitted"] for x in best):
            best, best_drop = cells, drop
    names = ", ".join(orc.headers[c][:40] for c in best_drop)
    return best, f"oracle column(s) not printed, chosen by value agreement: {names}"


def main() -> int:
    from ledger.config import load_config
    from ledger.ingest.http import Fetcher

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--refetch", action="store_true", help="download again even if on disk")
    args = ap.parse_args()
    SRC.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for line in (REPO / "data" / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line) if line.strip() else {}
        if rec.get("record") == "unit":
            manifest[rec["unit_id"]] = rec
    src_path = OUT / "sources.json"
    sources = json.loads(src_path.read_text("utf-8")) if src_path.exists() else {}
    fetcher = Fetcher(load_config().fetch)

    from pypdf import PdfReader

    def pdf_edition(unit: str) -> dict:
        row = manifest[unit]
        meta = PdfReader(str(REPO / "data" / "raw" / row["source"] / f"{unit}.pdf")).metadata or {}
        return {
            "pdf_unit": unit,
            "pdf_date_issued": row.get("date_issued"),
            "pdf_creation_date": str(meta.get("/CreationDate", "")),
        }

    all_cells: list[dict] = []
    table_rows: list[dict] = []

    def record(unit, ti, pg, cells, reason, src_rec):
        n = len(cells)
        a = sum(c["admitted"] for c in cells)
        table_rows.append(
            {
                "unit": unit,
                "table": f"#/tables/{ti}",
                "page": pg.page if pg else None,
                "table_id": pg.table_id if pg else None,
                "oracle_cells": n,
                "admitted": a,
                "coverage": a / n if n else None,
                "reason": reason,
                "oracle_file": src_rec.get("path", "") if src_rec else "",
                "sha256": (src_rec.get("sha256", "") if src_rec else "")[:16],
                "edition_pdf": src_rec.get("pdf_date_issued", "") if src_rec else "",
                "edition_oracle": src_rec.get("release", "") if src_rec else "",
            }
        )
        all_cells.extend(cells)

    # MER
    for unit in MER_UNITS:
        doc = json.loads((PARSED / f"{unit}.json").read_text(encoding="utf-8"))
        for ti in range(len(doc["tables"])):
            pg = read_page(unit, manifest[unit]["source"], ti, doc)
            if not pg.table_id:
                record(unit, ti, pg, [], "no printed table id on the page", None)
                continue
            heading = page_heading(doc, pg.page)[1]
            rec, dest, note = None, None, ""
            for cand in id_candidates(pg.table_id):
                tbl = mer_tbl(cand)
                url = MER_URL.format(tbl=tbl)
                path = SRC / f"{tbl}.xlsx"
                r = fetch(
                    fetcher,
                    url,
                    path,
                    sources,
                    {"table_id_printed": pg.table_id, "table_id": cand, **pdf_edition(unit)},
                    args.refetch,
                )
                if not r["type"].startswith("OOXML"):
                    note = f"export {tbl} is {r['type']}"
                    continue
                title = export_title(path)
                r["export_title"] = title
                pw, ow = title_words(heading), title_words(title)
                same_id = title.startswith(f"Table {cand} ") or title.startswith(f"Table {cand} ")
                if (pw and ow and len(pw & ow) >= 0.8 * min(len(pw), len(ow))) or (
                    not pw and same_id
                ):
                    rec, dest = r, path
                    if cand != pg.table_id:
                        note = f"printed id {pg.table_id} resolved to {cand} by title"
                    elif not pw:
                        note = "heading carries the id only; accepted on the export's own id"
                    break
                note = f"export {tbl} title does not match the page heading"
            if rec is None:
                record(unit, ti, pg, [], note, None)
                continue
            orc = mer_oracle(dest)
            rec["release"] = orc.release
            cells, reason = admit(pg, orc, unit, rec["path"])
            record(unit, ti, pg, cells, "; ".join(x for x in (note, reason) if x), rec)

    # STEO: the 2026-09 JSON snapshot (data/oracle/steo/2026-09), admitted cell by cell against
    # the printed page under the council's rules (steo.admit_table). STEO_m.xlsx (monthly) is kept
    # as the edition check only.
    import steo
    import steo_footnotes

    fetch(fetcher, STEO_URL, SRC / "STEO_m.xlsx", sources, pdf_edition(STEO_UNIT), args.refetch)
    steo_doc = json.loads((PARSED / f"{STEO_UNIT}.json").read_text(encoding="utf-8"))
    data_tables = {ti: (page, tid) for ti, page, tid in steo_footnotes.table_pages(steo_doc)}
    steo_detail = []
    steo_2241_cells: list[dict] = []
    snap_rec = {
        "path": "data/oracle/steo/2026-09",
        "sha256": "see data/oracle/steo/2026-09/sources.json",
        "pdf_date_issued": manifest[STEO_UNIT].get("date_issued"),
        "release": "STEO 2026-09, release 2026-09-09",
    }
    for ti in range(len(steo_doc["tables"])):
        if ti not in data_tables:
            record(STEO_UNIT, ti, None, [], "narrative table (pp3-5): no oracle series", None)
            continue
        page, tid = data_tables[ti]
        # the oracle: the council's whole-row rule (data/oracle/steo/2026-09/admission_rule.md)
        res = steo.admit_table_rows(STEO_UNIT, ti, page, tid, steo_footnotes.view_of(tid))
        pg_stub = Page(STEO_UNIT, ti, page, tid)
        record(STEO_UNIT, ti, pg_stub, res["cells"], "", snap_rec)
        steo_detail.append({k: v for k, v in res.items() if k != "cells"})
        # the superseded 22:41 rule (unit + precision gates), kept only for the comparison
        old = steo.admit_table_2241(STEO_UNIT, ti, page, tid, steo_footnotes.view_of(tid))
        steo_2241_cells.extend(old["cells"])
    (OUT / "steo_admission.json").write_text(
        json.dumps(steo_detail, indent=1, default=str), encoding="utf-8"
    )
    with (OUT / "steo_cells_2241.jsonl").open("w", encoding="utf-8") as fh:
        for c in steo_2241_cells:
            fh.write(json.dumps(c) + "\n")
    aeo_doc = json.loads((PARSED / f"{AEO_UNIT}.json").read_text(encoding="utf-8"))
    for ti in range(len(aeo_doc["tables"])):
        record(AEO_UNIT, ti, None, [], "no printed table id; no oracle source", None)

    # ERP: held xls, sheet si <-> tables[si] (erp_compare.py's mapping)
    for unit in ERP_UNITS:
        doc = json.loads((PARSED / f"{unit}.json").read_text(encoding="utf-8"))
        path = REPO / "reports" / "a1_digits" / f"{unit}.xls"
        b = path.read_bytes()
        rec = {
            "url": "held (reports/a1_digits)",
            "path": path.relative_to(REPO).as_posix(),
            "sha256": hashlib.sha256(b).hexdigest(),
            "type": sniff(b),
            **pdf_edition(unit),
        }
        sources[f"held:{unit}"] = rec
        for si in range(2):
            pg = read_page(unit, manifest[unit]["source"], si, doc)
            pg.table_id = pg.table_id or f"{unit.split('-')[-1]} sheet{si}"
            orc = erp_oracle(path, si)
            cells, reason = admit(pg, orc, unit, rec["path"])
            record(unit, si, pg, cells, reason, rec)

    src_path.write_text(json.dumps(sources, indent=1), encoding="utf-8")
    with (OUT / "cells.jsonl").open("w", encoding="utf-8") as fh:
        for c in all_cells:
            fh.write(json.dumps(c) + "\n")
    (OUT / "tables.json").write_text(json.dumps(table_rows, indent=1), encoding="utf-8")
    write_report(table_rows, sources)
    return 0


def write_report(rows: list[dict], sources: dict) -> None:
    covered = [r for r in rows if r["oracle_cells"]]
    n = sum(r["oracle_cells"] for r in covered)
    a = sum(r["admitted"] for r in covered)
    flagged = [r for r in covered if r["coverage"] < FLAG_BELOW]
    by_source: dict[str, list] = defaultdict(list)
    for r in rows:
        src = (
            "ERP"
            if "ERP" in r["unit"]
            else "STEO"
            if "steo" in r["unit"]
            else "AEO"
            if "AEO" in r["unit"]
            else "MER"
        )
        by_source[src].append(r)
    lines = [
        "# A1 step 0, item 2 - the cell oracle (D-038)",
        "",
        f"TableItems considered: **{len(rows)}**; covered by the oracle: **{len(covered)}**; "
        f"oracle cells on printed rows: **{n:,}**; admitted (value printed in the bbox, A6): "
        f"**{a:,} ({a / n:.1%})**; tables below {FLAG_BELOW:.0%} coverage: **{len(flagged)}**.",
        "",
        "| source | TableItems | covered | oracle cells | admitted | coverage |",
        "|---|---|---|---|---|---|",
    ]
    for src, rs in sorted(by_source.items()):
        cov = [r for r in rs if r["oracle_cells"]]
        nn = sum(r["oracle_cells"] for r in cov)
        aa = sum(r["admitted"] for r in cov)
        lines.append(
            f"| {src} | {len(rs)} | {len(cov)} | {nn:,} | {aa:,} | "
            f"{f'{aa / nn:.1%}' if nn else 'n/a'} |"
        )
    lines += [
        "",
        "| unit | table | page | printed id | oracle file | sha256 (16) | PDF edition | "
        "oracle release | "
        "oracle cells | admitted | coverage | note |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        cov = f"{r['coverage']:.1%}" if r["coverage"] is not None else "-"
        flag = " **< 90 %**" if r["coverage"] is not None and r["coverage"] < FLAG_BELOW else ""
        lines.append(
            f"| `{r['unit']}` | `{r['table']}` | {r['page'] or '-'} | {r['table_id'] or '-'} | "
            f"{r['oracle_file'] or '-'} | {r['sha256'] or '-'} | {r['edition_pdf'] or '-'} | "
            f"{r['edition_oracle'] or '-'} | {r['oracle_cells']} | {r['admitted']} | {cov}{flag} | "
            f"{r['reason']} |"
        )
    lines += [
        "",
        "## Oracle files",
        "",
        "| url | type | sha256 | fetched | release |",
        "|---|---|---|---|---|",
    ]
    for rec in sources.values():
        lines.append(
            f"| {rec['url']} | {rec['type']} | `{rec['sha256']}` | "
            f"{rec.get('fetched_at', 'held')} | "
            f"{rec.get('release', '')} |"
        )
    (OUT / "coverage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    raise SystemExit(main())
