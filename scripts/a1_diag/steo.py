"""STEO printed tables vs the 2026-09 JSON snapshot (D-038 item 1): page reader, period normaliser,
unit reader, row alignment. Used by item 2's check here and by ``oracle.py``'s STEO admission.

**Periods.** A printed STEO table has two header lines: years ("2025 2026 2027 Year") above
quarters and year columns ("Q1 Q2 Q3 Q4 ... 2025 2026 2027"). Each quarter token takes the year
printed above its group of four - by position, the year whose x-centre is nearest the group's - and
each year token under "Year" is a calendar-year column. The JSON keys are ``YYYY0q`` (quarters) and
``YYYY`` (years). The sequence reading (quarters in fours, left to right) is checked against the
positional one; they must agree.

**Units.** Printed units are parentheses on a heading line ("Crude Oil (dollars per barrel)"),
inherited by the rows below until the next unit, or on the row's own label ("Henry Hub Spot
(dollars per million Btu)"). Footnote markers such as "(a)" are not units.

**Rows.** Labels repeat within a table ("Industrial Sector" under both natural gas and
electricity), so printed data rows are aligned with the JSON rows that carry data **in printed
order**, and each pair's labels are checked (DESCRIPTION or CHART_NAME, leader dots and footnote
markers removed). Values are read by x-position against the period columns, so "-" (no data)
keeps its column.

    uv run --with pdfplumber python scripts/a1_diag/steo.py     # item 2: Table 2 check
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics as st
import sys
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import oracle as orc  # noqa: E402

SNAP = REPO / "data" / "oracle" / "steo" / "2026-09"
HELD_PDF = REPO / "data" / "raw" / "eia" / "eia-pdf-steo_full.pdf"
TAB_PDF_URL = "https://www.eia.gov/outlooks/steo/tables/pdf/{t}tab.pdf"
VIEW_OF_TABLE = {
    "1": 3,
    "2": 8,
    "3a": 6,
    "3b": 29,
    "3c": 7,
    "3d": 30,
    "3e": 31,
    "4a": 9,
    "4b": 27,
    "4c": 10,
    "4d": 11,
    "5a": 15,
    "5b": 16,
    "6": 18,
    "7a": 19,
    "7b": 20,
    "7c": 21,
    "7d": 22,
    "7e": 23,
    "8a": 24,
    "9a": 5,
    "9b": 4,
    "9c": 28,
    "10a": 32,
    "10b": 33,
}
UNIT_WORDS = re.compile(
    r"\b(dollars?|cents?|per|percent|btu|barrels?|gallons?|kilowatthours?|million|billion|"
    r"thousand|quadrillion|short tons|cubic feet|days?|index|degree|megawatts?|gigawatts?|"
    r"metric tons|terawatthours?|rigs|wells)\b",
    re.I,
)
QUARTER = re.compile(r"^Q([1-4])$")


# ---- the printed page --------------------------------------------------------------------------


@dataclass
class Column:
    x: float
    key: str  # JSON period key: YYYY0q or YYYY


@dataclass
class PrintedRow:
    label: str
    unit: str | None
    footnote: str | None  # "(a)" etc. on the label
    values: dict[str, str] = field(default_factory=dict)  # period key -> printed token
    top: float = 0.0


def clean_label(text: str) -> tuple[str, str | None]:
    text = re.sub(r"[.…�]{2,}", " ", text)
    foot = re.findall(r"\(([a-z])\)", text)
    text = re.sub(r"\([a-z]\)", " ", text)
    text = re.sub(
        r"\((?:[^)]*)\)", lambda m: m.group(0) if UNIT_WORDS.search(m.group(0)) else " ", text
    )
    return re.sub(r"\s+", " ", text).strip(), (foot[-1] if foot else None)


def unit_of(text: str) -> str | None:
    for m in re.finditer(r"\(([^)]*)\)", text):
        if UNIT_WORDS.search(m.group(1)):
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return None


def lines_of(words: list[dict]) -> list[list[dict]]:
    tol = 0.5 * st.median(w["bottom"] - w["top"] for w in words)
    out: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"] + w["bottom"]) / 2):
        cy = (w["top"] + w["bottom"]) / 2
        if out and abs(cy - st.mean((x["top"] + x["bottom"]) / 2 for x in out[-1])) <= tol:
            out[-1].append(w)
        else:
            out.append([w])
    return [sorted(ln, key=lambda w: w["x0"]) for ln in out]


def period_columns(lines: list[list[dict]]) -> tuple[list[Column], str]:
    """Positional reading of the two header lines, cross-checked against the sequence reading."""
    qi = next(
        i for i, ln in enumerate(lines) if sum(bool(QUARTER.match(w["text"])) for w in ln) >= 4
    )
    years_line = [w for w in lines[qi - 1] if orc.is_year(w["text"]) or w["text"] == "Year"]
    cols: list[Column] = []
    quarters = [w for w in lines[qi] if QUARTER.match(w["text"])]
    annuals = [w for w in lines[qi] if orc.is_year(w["text"])]
    spans = [w for w in years_line if orc.is_year(w["text"])]
    for g in range(0, len(quarters), 4):
        group = quarters[g : g + 4]
        gx = st.mean((w["x0"] + w["x1"]) / 2 for w in group)
        year = min(spans, key=lambda w: abs((w["x0"] + w["x1"]) / 2 - gx))["text"]
        for w in group:
            q = QUARTER.match(w["text"]).group(1)
            cols.append(Column((w["x0"] + w["x1"]) / 2, f"{year}0{q}"))
    for w in annuals:
        cols.append(Column((w["x0"] + w["x1"]) / 2, w["text"]))
    # sequence reading: quarters in fours under the spanning years, left to right
    seq = [
        f"{spans[g // 4]['text']}0{QUARTER.match(w['text']).group(1)}"
        for g, w in enumerate(quarters)
    ] + [w["text"] for w in annuals]
    agree = "agree" if [c.key for c in cols] == seq else f"DISAGREE: {seq}"
    return sorted(cols, key=lambda c: c.x), agree


def read_table_page(pdf: Path, page_no: int) -> tuple[list[Column], str, list[PrintedRow]]:
    import pdfplumber

    with pdfplumber.open(pdf) as doc:
        words = doc.pages[page_no - 1].extract_words(x_tolerance=1)
    lines = lines_of(words)
    cols, agree = period_columns(lines)
    first_col = min(c.x for c in cols)
    pitch = st.median(b.x - a.x for a, b in zip(cols, cols[1:], strict=False))
    rows: list[PrintedRow] = []
    unit: str | None = None
    qi = next(
        i for i, ln in enumerate(lines) if sum(bool(QUARTER.match(w["text"])) for w in ln) >= 4
    )
    for ln in lines[qi + 1 :]:  # the two period header lines are not data
        label_words = [w for w in ln if w["x1"] < first_col - 0.45 * pitch]
        cells = [w for w in ln if w not in label_words]
        label_text = " ".join(w["text"] for w in label_words)
        values = [w for w in cells if orc.canon(w["text"]) is not None or w["text"] in ("-", "NA")]
        if len(values) < 3:  # a heading line: may set the unit
            u = unit_of(" ".join(w["text"] for w in ln))
            if u:
                unit = u
            continue
        label, foot = clean_label(label_text)
        own = unit_of(label_text)
        row = PrintedRow(
            re.sub(r"\s*\([^)]*\)", "", label).strip(), own or unit, foot, top=ln[0]["top"]
        )
        for w in values:
            cx = (w["x0"] + w["x1"]) / 2
            col = min(cols, key=lambda c: abs(c.x - cx))
            if abs(col.x - cx) <= 0.5 * pitch and orc.canon(w["text"]) is not None:
                row.values[col.key] = w["text"]
        rows.append(row)
    return cols, agree, rows


# ---- the snapshot ------------------------------------------------------------------------------


def json_rows(view: int, f: str) -> list[dict]:
    body = json.loads((SNAP / f"v{view}_{f}.json").read_text("utf-8"), parse_float=Decimal)
    return body["VIEWSDATA"]["ROWS"]


def data_rows(view: int) -> list[dict]:
    """JSON rows that carry data, in printed order, with Q and A merged."""
    q = [r for r in json_rows(view, "Q") if r.get("HAS_DATA")]
    a = {
        (r.get("SERIES_ID"), r.get("DESCRIPTION")): r
        for r in json_rows(view, "A")
        if r.get("HAS_DATA")
    }
    out = []
    for r in q:
        merged = dict(r)
        data = dict(r.get("DATA") or {})
        data.update((a.get((r.get("SERIES_ID"), r.get("DESCRIPTION"))) or {}).get("DATA") or {})
        merged["DATA"] = data
        out.append(merged)
    return out


def norm_label(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def labels_match(printed: str, rec: dict) -> bool:
    """Exact after normalising, or one label a prefix/suffix of the other ("U.S. Imported Average"
    / "Imported Average", "No. 6 Residual Fuel Oil" / "No. 6 Residual Fuel")."""
    p = norm_label(printed)
    for k in ("DESCRIPTION", "CHART_NAME"):
        j = norm_label(rec.get(k))
        if (
            p
            and j
            and (
                p == j
                or p.startswith(j + " ")
                or p.endswith(" " + j)
                or j.startswith(p + " ")
                or j.endswith(" " + p)
            )
        ):
            return True
    return False


def agreement(row: PrintedRow, rec: dict) -> int:
    data = rec.get("DATA") or {}
    return sum(
        1
        for key, tok in row.values.items()
        if orc.canon(render(data.get(key), rec.get("PRECISION")) or "") == orc.canon(tok)
    )


def match_rows(rows: list[PrintedRow], recs: list[dict]) -> list[tuple[PrintedRow, dict | None]]:
    """Each printed row to one JSON data row: labels must match; among matching candidates (labels
    repeat, and the JSON is not in printed order) the one whose served values agree most with the
    printed values wins. Each JSON row is used once. Units play no part - they are what's
    checked."""
    used: set[int] = set()
    out = []
    for row in rows:
        cands = [
            (agreement(row, r), -i, i)
            for i, r in enumerate(recs)
            if i not in used and labels_match(row.label, r)
        ]
        if not cands:
            out.append((row, None))
            continue
        _, _, best = max(cands)
        used.add(best)
        out.append((row, recs[best]))
    return out


def render(value, precision) -> str | None:
    if value is None or precision is None:
        return None
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return format(d.quantize(Decimal(1).scaleb(-int(precision)), rounding=ROUND_HALF_UP), "f")


# ---- item 2 ------------------------------------------------------------------------------------


def main() -> int:
    from ledger.config import load_config
    from ledger.ingest.http import Fetcher

    doc = json.loads((REPO / "data" / "parsed" / "eia-pdf-steo_full.json").read_text("utf-8"))
    page = next(
        t["prov"][0]["page_no"]
        for t in doc["texts"]
        if t.get("prov") and t["text"].strip().startswith("Table 2.")
    )
    tab = SNAP / "2tab.pdf"
    fetcher = Fetcher(load_config().fetch)
    fetcher.download(TAB_PDF_URL.format(t="2"), tab, source="eia")
    tab_sha = hashlib.sha256(tab.read_bytes()).hexdigest()
    # the test vector joins the snapshot's tracked manifest
    manifest_path = SNAP / "sources.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest.setdefault("test_vectors", {})["2tab.pdf"] = {
        "url": TAB_PDF_URL.format(t="2"),
        "path": tab.relative_to(REPO).as_posix(),
        "sha256": tab_sha,
        "bytes": tab.stat().st_size,
        "fetched_utc": __import__("datetime")
        .datetime.now(__import__("datetime").UTC)
        .isoformat(timespec="seconds"),
    }
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    out = []
    for name, pdf, pno in (("held steo_full.pdf", HELD_PDF, page), ("tables/pdf/2tab.pdf", tab, 1)):
        cols, agree, rows = read_table_page(pdf, pno)
        recs = data_rows(VIEW_OF_TABLE["2"])
        matched = match_rows(rows, recs)
        label_miss = [r.label for r, rec in matched if rec is None]
        pairs = [(r, rec) for r, rec in matched if rec is not None]
        unit_miss = [
            (r.label, r.unit, rec.get("UNITS"), rec.get("SERIES_ID"))
            for r, rec in pairs
            if (r.unit or "").lower() != (rec.get("UNITS") or "").lower()
        ]
        value_miss, value_ok = [], 0
        for r, rec in pairs:
            for key, tok in r.values.items():
                served = render((rec.get("DATA") or {}).get(key), rec.get("PRECISION"))
                if served is not None and orc.canon(served) == orc.canon(tok):
                    value_ok += 1
                else:
                    value_miss.append((r.label, key, tok, served))
        mg = [
            (r.label, r.unit, rec.get("UNITS"), rec.get("SERIES_ID"), rec.get("PRECISION"))
            for r, rec in pairs
            if (rec.get("SERIES_ID") or "").startswith("MGWHUUS")
        ]
        out.append(
            {
                "source": name,
                "page": pno,
                "columns": [c.key for c in cols],
                "normaliser": agree,
                "printed_rows": len(rows),
                "json_rows": len(recs),
                "label_mismatches": label_miss,
                "unit_mismatches": unit_miss,
                "values_ok": value_ok,
                "value_mismatches": value_miss[:20],
                "value_mismatch_count": len(value_miss),
                "MGWHUUS": mg,
            }
        )
    report = {"2tab_pdf": {"url": TAB_PDF_URL.format(t="2"), "sha256": tab_sha}, "checks": out}
    (REPO / "reports" / "a1_diag" / "steo_table2_check.json").write_text(
        json.dumps(report, indent=1, default=str), encoding="utf-8"
    )
    print(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
