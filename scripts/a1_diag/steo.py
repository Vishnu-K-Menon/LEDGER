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
    label: str  # markers and units stripped; the heading's text when the label is only a unit
    unit: str | None
    label_raw: str = ""
    own_markers: list[str] = field(default_factory=list)
    inherited_markers: list[str] = field(default_factory=list)  # from the heading above
    heading: str = ""
    values: dict[str, str] = field(default_factory=dict)  # period key -> printed token
    dashes: set[str] = field(default_factory=set)  # period keys printed "-": expected-empty
    minus_flags: list[str] = field(default_factory=list)  # "-" that could be a sign (guard)
    top: float = 0.0

    @property
    def markers(self) -> list[str]:
        return sorted(set(self.own_markers) | set(self.inherited_markers))

    @property
    def decimals(self) -> int | None:
        """The row's printed precision: the modal number of decimals of its printed values."""
        ds = [orc.decimals(orc.canon(t)) for t in self.values.values() if orc.canon(t)]
        return max(set(ds), key=ds.count) if ds else None


def clean_label(text: str) -> tuple[str, str | None]:
    """The series name: leader dots, footnote markers "(a)" and unit parentheticals removed; a
    qualifier such as "(excl GOA)" is kept as plain words - it is part of the name."""
    text = re.sub(r"[.…�]{2,}", " ", text)
    foot = re.findall(r"\(([a-z])\)", text)
    text = re.sub(r"\([a-z]\)", " ", text)
    text = re.sub(
        r"\(([^)]*)\)",
        lambda m: " " if UNIT_START.match(m.group(1).strip()) else f" {m.group(1)} ",
        text,
    )
    return re.sub(r"\s+", " ", text).strip(), (foot[-1] if foot else None)


UNIT_START = re.compile(
    r"^\s*(dollars?|cents?|percent|millions?|billions?|thousands?|trillions?|quadrillion|index|"
    r"degree|gigawatts?|megawatts?|kilowatthours?|terawatthours?|short tons|metric tons|number|"
    r"cubic|barrels?|gallons?|btu|\$)\b",
    re.I,
)


def unit_of(text: str) -> str | None:
    """A printed unit: a parenthetical that STARTS with a quantity word - "(million barrels per
    day)", "(dollars per gallon)". A descriptive parenthetical that merely mentions one ("(power
    plants larger than one megawatt)") is not a unit. An ", except ..." clause is cut: it names
    rows whose unit the page does not state as a string."""
    for m in re.finditer(r"\(([^)]*)\)", text):
        body = re.sub(r"\s+", " ", m.group(1)).strip()
        if UNIT_START.match(body):
            return re.split(r",\s*except\b", body, maxsplit=1)[0].strip()
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


MARK = re.compile(r"\(([a-z])\)")
DASHES = {"-", "\u2013", "\u2014"}


def read_table_page(
    pdf: Path, page_no: int
) -> tuple[list[Column], str, list[PrintedRow], dict[str, str]]:
    """Printed rows (with markers, heading, dashes, minus-guard flags) and footnote definitions.

    A line with < 3 values is a heading: its unit (if any) is inherited by the rows below until the
    next unit, and its markers by the rows below until the next heading. Footnote definitions
    ("(a) text", wrapped lines joined) end the table.
    """
    import pdfplumber

    with pdfplumber.open(pdf) as doc:
        words = doc.pages[page_no - 1].extract_words(x_tolerance=1)
    lines = lines_of(words)
    cols, agree = period_columns(lines)
    first_col = min(c.x for c in cols)
    pitch = st.median(b.x - a.x for a, b in zip(cols, cols[1:], strict=False))
    rows: list[PrintedRow] = []
    defs: dict[str, str] = {}
    unit: str | None = None
    heading, inherited = "", []
    in_defs, current_def = False, None
    qi = next(
        i for i, ln in enumerate(lines) if sum(bool(QUARTER.match(w["text"])) for w in ln) >= 4
    )
    for ln in lines[:qi]:  # a unit in the table title ("Table 7b. ... (billion kilowatthours)")
        title = " ".join(w["text"] for w in ln)
        if re.match(r"\s*Table\s+\d", title) and unit_of(title):
            unit = unit_of(title)
    for ln in lines[qi + 1 :]:  # the two period header lines are not data
        text = " ".join(w["text"] for w in ln)
        label_words = [w for w in ln if w["x1"] < first_col - 0.45 * pitch]
        cells = [w for w in ln if w not in label_words]
        values = [
            w
            for w in cells
            if orc.canon(w["text"]) is not None or w["text"] in DASHES or w["text"] == "NA"
        ]
        m_def = re.match(r"^\(([a-z])\)\s+(.*)$", text)
        if m_def and len(values) < 3:
            in_defs, current_def = True, m_def.group(1)
            defs[current_def] = m_def.group(2).strip()
            continue
        if in_defs:
            if text.startswith(("Notes:", "Sources:", "EIA completed", "Historical data")):
                in_defs, current_def = False, None
            elif current_def and len(values) < 3:
                defs[current_def] += " " + text.strip()
            continue
        if len(values) < 3:  # a heading line
            u = unit_of(text)
            if u:
                unit = u
            heading, inherited = text, MARK.findall(text)
            continue
        label_text = " ".join(w["text"] for w in label_words)
        label, _ = clean_label(label_text)
        if not label:  # the label is only a unit: the series is named by the heading above
            label = clean_label(heading)[0]
        row = PrintedRow(
            label,
            unit_of(label_text) or unit,
            label_raw=label_text.strip(),
            own_markers=MARK.findall(label_text),
            inherited_markers=list(inherited),
            heading=heading,
            top=ln[0]["top"],
        )
        taken: dict[str, str] = {}
        for w in values:
            cx = (w["x0"] + w["x1"]) / 2
            col = min(cols, key=lambda c: abs(c.x - cx))
            if abs(col.x - cx) > 0.5 * pitch:
                continue
            if w["text"] in DASHES:
                if col.key in taken:  # a dash sharing a column with a number: sign or no-data?
                    row.minus_flags.append(col.key)
                row.dashes.add(col.key)
                continue
            if orc.canon(w["text"]) is None:
                continue
            if w["text"].startswith(("-", "\u2212")) and w["x0"] < col.x - 0.5 * pitch:
                row.minus_flags.append(col.key)  # the sign intrudes into the previous column
            if col.key in row.dashes:
                row.minus_flags.append(col.key)
            taken[col.key] = w["text"]
            row.values[col.key] = w["text"]
        rows.append(row)
    return cols, agree, rows, defs


# ---- the snapshot ------------------------------------------------------------------------------


def json_rows(view: int, f: str) -> list[dict]:
    body = json.loads((SNAP / f"v{view}_{f}.json").read_text("utf-8"), parse_float=Decimal)
    return body["VIEWSDATA"]["ROWS"]


def data_rows(view: int) -> list[dict]:
    """JSON rows that carry data, Q and A merged. ``LAST_HISTORICAL`` is the quarterly view's
    (``YYYY0q``); ``LAST_HISTORICAL_A`` the annual view's (``YYYY``) - the forecast boundaries."""
    q = [r for r in json_rows(view, "Q") if r.get("HAS_DATA")]
    a = {
        (r.get("SERIES_ID"), r.get("DESCRIPTION")): r
        for r in json_rows(view, "A")
        if r.get("HAS_DATA")
    }
    out = []
    for r in q:
        merged = dict(r)
        ann = a.get((r.get("SERIES_ID"), r.get("DESCRIPTION"))) or {}
        data = dict(r.get("DATA") or {})
        data.update(ann.get("DATA") or {})
        merged["DATA"] = data
        merged["LAST_HISTORICAL_A"] = ann.get("LAST_HISTORICAL")
        out.append(merged)
    seen = {(r.get("SERIES_ID"), r.get("DESCRIPTION")) for r in q}
    for key, ann in a.items():  # series served at annual frequency only
        if key not in seen:
            merged = dict(ann)
            merged["LAST_HISTORICAL_A"] = ann.get("LAST_HISTORICAL")
            merged["LAST_HISTORICAL"] = None
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
    """Printed values the served series reproduces, each rounded at the decimals the PAGE prints.

    This identifies the series only. Admission separately requires the printed precision to equal
    the served PRECISION (7b prints one decimal where the JSON declares two)."""
    data = rec.get("DATA") or {}
    ok = 0
    for key, tok in row.values.items():
        c = orc.canon(tok)
        if c is not None and orc.canon(render(data.get(key), orc.decimals(c)) or "") == c:
            ok += 1
    return ok


def render(value, precision) -> str | None:
    """Served value at the row's PRECISION, Decimal round-half-up (never Python round())."""
    if value is None or precision is None:
        return None
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return format(d.quantize(Decimal(1).scaleb(-int(precision)), rounding=ROUND_HALF_UP), "f")


ABBREV = {"e": "east", "w": "west", "n": "north", "s": "south", "ak": "alaska", "hi": "hawaii"}


def expanded(text: str) -> str:
    """Normalised label with direction abbreviations expanded, "u s" -> "united states", and a
    trailing plural "s" dropped from longer words (for the fuzzy fallback only)."""
    t = norm_label(text).replace("u s ", "united states ")
    if t == "u s" or t.endswith(" u s"):
        t = t[:-3] + "united states"
    words = [ABBREV.get(w, w) for w in t.split()]
    return " ".join(w[:-1] if len(w) > 4 and w.endswith("s") else w for w in words)


def fuzzy_ratio(printed: str, rec: dict) -> float:
    from difflib import SequenceMatcher

    p = expanded(printed)
    return max(
        SequenceMatcher(None, p, expanded(rec.get(k) or "")).ratio()
        for k in ("DESCRIPTION", "CHART_NAME")
    )


FUZZY_MIN = 0.85  # label similarity after expansion
FUZZY_CONFIRM = 0.8  # share of the row's printed values the served values must reproduce
LABEL_CONFIRM = 0.5  # the same, for exact and prefix/suffix label matches


def match_rows(
    rows: list[PrintedRow], recs: list[dict]
) -> list[tuple[PrintedRow, dict | None, str]]:
    """Each printed row to one JSON data row, by SERIES_ID identity - never by position.

    Labels must match exactly (normalised) or as a prefix/suffix variant; among candidates (labels
    repeat, and the JSON is not in printed order) the one whose served values agree most with the
    printed values wins. Failing that, a fuzzy label match (EIA's labels carry typos such as
    "exluding", "egion"; the page abbreviates "E. N. Central") counts only if the served values
    reproduce >= 80 % of the row's printed values. **Every** match needs value confirmation: a label
    alone is not identity (3b's "Non-OPEC total" shares its DESCRIPTION with the unplanned-outages
    series PADI_NONOPEC), so exact and affix matches need >= 50 %. Each JSON row is used once.
    Units play no part - they are what's checked. Returns (row, record or None, "exact" | "affix" |
    "fuzzy" | "none").
    """

    def is_exact(row: PrintedRow, rec: dict) -> bool:
        return any(
            norm_label(row.label) == norm_label(rec.get(k)) for k in ("DESCRIPTION", "CHART_NAME")
        )

    def need(row: PrintedRow, share: float) -> int:
        return max(1, int(share * len(row.values) + 0.999))

    # Passes, so a looser match never takes a series an exact label is waiting for ("Rest of Lower
    # 48 States" would otherwise take "Lower 48 States" as a suffix match first).
    passes = (
        ("exact", lambda row, r: is_exact(row, r), LABEL_CONFIRM),
        ("affix", lambda row, r: labels_match(row.label, r), LABEL_CONFIRM),
        ("fuzzy", lambda row, r: fuzzy_ratio(row.label, r) >= FUZZY_MIN, FUZZY_CONFIRM),
    )
    used: set[int] = set()
    chosen: dict[int, tuple[int, str]] = {}  # printed row index -> (record index, kind)
    for kind, test, share in passes:
        for ri, row in enumerate(rows):
            if ri in chosen:
                continue
            cands = [
                (agreement(row, r), -i, i)
                for i, r in enumerate(recs)
                if i not in used and test(row, r)
            ]
            cands = [c for c in cands if c[0] >= need(row, share)]
            if cands:
                _, _, best = max(cands)
                used.add(best)
                chosen[ri] = (best, kind)
    return [
        (row, recs[chosen[ri][0]], chosen[ri][1]) if ri in chosen else (row, None, "none")
        for ri, row in enumerate(rows)
    ]


# ---- admission (item 3; council ruling adopted 2026-09-29) ------------------------------------


def norm_unit(u: str | None) -> str | None:
    """NFKC; U+00A0 -> space; spaces around hyphens removed; whitespace collapsed; case-folded."""
    import unicodedata

    if u is None:
        return None
    u = unicodedata.normalize("NFKC", u).replace(" ", " ")
    u = re.sub(r"\s*-\s*", "-", u)
    return re.sub(r"\s+", " ", u).strip().casefold()


def load_frozen() -> tuple[dict, dict]:
    """The frozen footnote list (by table + SERIES_ID) and the closed unit alias list."""
    foot = json.loads((SNAP / "footnotes.json").read_text("utf-8"))
    by_row = {(e["table_index"], e["series_id"]): e for e in foot["rows"] if e["series_id"]}
    aliases = json.loads((SNAP / "unit_aliases.json").read_text("utf-8"))
    pairs = {(norm_unit(a["printed"]), norm_unit(a["served"])) for a in aliases["aliases"]}
    return by_row, {"pairs": pairs}


def unit_verdict(printed: str | None, served: str | None, aliases: dict) -> tuple[bool, str]:
    """(ok, how): equal raw, equal after normalisation, an alias pair, or a mismatch."""
    if printed is not None and printed == served:
        return True, "equal"
    p, s = norm_unit(printed), norm_unit(served)
    if p is not None and p == s:
        return True, "normalised"
    if (p, s) in aliases["pairs"]:
        return True, "alias"
    return False, "mismatch"


def stratum(key: str, rec: dict) -> str:
    """history / forecast from the row's LAST_HISTORICAL (YYYY0q) or LAST_HISTORICAL_A (YYYY)."""
    lh = rec.get("LAST_HISTORICAL") if len(key) == 6 else rec.get("LAST_HISTORICAL_A")
    if not lh:
        return "unknown"
    return "history" if key <= str(lh) else "forecast"


def admit_table_2241(unit_id: str, table_index: int, page: int, table_id: str, view: int) -> dict:
    """Admit the printed cells of one STEO table against the 2026-09 snapshot.

    Rows: printed rows mapped to JSON by SERIES_ID (``match_rows``); unserved printed rows and
    unprinted JSON rows are out of the denominator. Row gates: the unit rule (normalised equality or
    a CLOSED alias pair) and printed precision == served PRECISION. Cells: admitted iff
    |printed - served| <= half a printed unit (Decimal, absolute). "-" cells are expected-empty -
    never values, never zero - and are kept as a separate check. Footnoted rows (frozen list) are
    admitted and reported as a stratum; one that disagrees with the served values while both
    neighbours agree is excluded by name (the flip condition).
    """
    footnoted, aliases = load_frozen()
    _cols, agree, rows, _defs = read_table_page(HELD_PDF, page)
    matched = match_rows(rows, data_rows(view))
    per_row = []
    for row, rec, kind in matched:
        if rec is None:
            per_row.append(
                {"row": row, "rec": None, "kind": kind, "cells": [], "status": "unserved"}
            )
            continue
        sid = rec.get("SERIES_ID")
        u_ok, u_how = unit_verdict(row.unit, rec.get("UNITS"), aliases)
        prec = rec.get("PRECISION")
        p_ok = prec is not None and row.decimals is not None and int(prec) == row.decimals
        cells = []
        for key, tok in row.values.items():
            served = (rec.get("DATA") or {}).get(key)
            printed = Decimal(orc.canon(tok))
            if not u_ok:
                status = "excluded: unit"
            elif not p_ok:
                status = "excluded: precision"
            elif served is None:
                status = "value mismatch: not served"
            else:
                half = Decimal(1).scaleb(-int(prec)) / 2
                status = (
                    "admitted" if abs(printed - Decimal(str(served))) <= half else "value mismatch"
                )
            cells.append(
                {
                    "unit": unit_id,
                    "table_index": table_index,
                    "page": page,
                    "table_id": table_id,
                    "family": "STEO",
                    "series_id": sid,
                    "row": sid,
                    "label": row.label,
                    "period": key,
                    "col": key,
                    "band": key,
                    "header": key,
                    "value": orc.canon(tok),
                    "served": None if served is None else str(served),
                    "precision": prec,
                    "status": status,
                    "admitted": status == "admitted",
                    "stratum": stratum(key, rec),
                    "footnoted": (table_index, sid) in footnoted,
                    "oracle_file": (
                        f"data/oracle/steo/2026-09/v{view}_{'Q' if len(key) == 6 else 'A'}.json"
                    ),
                }
            )
        per_row.append(
            {
                "row": row,
                "rec": rec,
                "kind": kind,
                "cells": cells,
                "status": "served",
                "unit_how": u_how,
                "printed_unit": row.unit,
                "served_unit": rec.get("UNITS"),
                "precision_ok": p_ok,
                "printed_decimals": row.decimals,
                "served_precision": prec,
                "dashes": sorted(row.dashes),
                "minus_flags": list(row.minus_flags),
                "footnoted": (table_index, sid) in footnoted,
            }
        )
    # flip condition: a footnoted row that disagrees while both served neighbours agree
    served_rows = [r for r in per_row if r["status"] == "served"]
    flipped = []
    for i, r in enumerate(served_rows):
        bad = any(c["status"].startswith("value mismatch") for c in r["cells"])
        if not (r["footnoted"] and bad):
            continue
        neigh = [served_rows[j] for j in (i - 1, i + 1) if 0 <= j < len(served_rows)]
        if neigh and all(
            not any(c["status"].startswith("value mismatch") for c in n["cells"]) for n in neigh
        ):
            r["status"] = "excluded: flip"
            flipped.append(r["rec"].get("SERIES_ID"))
    cells = [c for r in served_rows if r["status"] == "served" for c in r["cells"]]
    expected_empty = [
        {
            "series_id": r["rec"].get("SERIES_ID"),
            "label": r["row"].label,
            "period": k,
            "served": None
            if (r["rec"].get("DATA") or {}).get(k) is None
            else str(r["rec"]["DATA"][k]),
        }
        for r in served_rows
        for k in r["dashes"]
    ]
    return {
        "unit": unit_id,
        "table_index": table_index,
        "page": page,
        "table_id": table_id,
        "view": view,
        "normaliser": agree,
        "cells": cells,
        "printed_rows": len(rows),
        "unserved_rows": [r["row"].label for r in per_row if r["status"] == "unserved"],
        "flip_excluded": flipped,
        "unit_hits": [
            (r["rec"].get("SERIES_ID"), r["unit_how"], r["printed_unit"], r["served_unit"])
            for r in served_rows
            if r["unit_how"] in ("normalised", "alias", "mismatch")
        ],
        "precision_mismatch_rows": [
            (r["rec"].get("SERIES_ID"), r["printed_decimals"], r["served_precision"])
            for r in served_rows
            if not r["precision_ok"]
        ],
        "expected_empty": expected_empty,
        "minus_flags": [
            (r["rec"].get("SERIES_ID"), f) for r in served_rows for f in r["minus_flags"]
        ],
        "match_kinds": [r["kind"] for r in per_row if r["status"] != "unserved"],
    }


def half_away(value: Decimal, decimals: int) -> Decimal:
    """Round half away from zero (Decimal ROUND_HALF_UP) - never Python round()."""
    return value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


def served_decimal(v) -> Decimal | None:
    if v is None:
        return None
    return v if isinstance(v, Decimal) else Decimal(str(v))


def printed_cells(row: PrintedRow) -> dict[str, tuple[Decimal, int]]:
    """Non-"-" printed cells: period -> (value, printed decimals), parsed from the text layer
    (thousands separators stripped; "-", U+2212 and parenthesised negatives read as negative)."""
    out = {}
    for key, tok in row.values.items():
        c = orc.canon(tok)
        if c is not None:
            out[key] = (Decimal(c), orc.decimals(c))
    return out


def satisfies(cells: dict[str, tuple[Decimal, int]], rec: dict) -> bool:
    """(a): every printed cell equals the served value rounded half away from zero at the printed
    decimals."""
    data = rec.get("DATA") or {}
    for key, (pv, dec) in cells.items():
        sv = served_decimal(data.get(key))
        if sv is None or half_away(sv, dec) != pv:
            return False
    return True


def series_key(rec: dict) -> str:
    return rec.get("SERIES_ID") or f"desc:{rec.get('DESCRIPTION')}"


def admit_table_rows(unit_id: str, table_index: int, page: int, table_id: str, view: int) -> dict:
    """The council's whole-row rule (data/oracle/steo/2026-09/admission_rule.md).

    A printed row is admitted iff (a) every non-"-" cell equals a served series rounded half away
    from zero at the printed decimals, (b) exactly one served series (distinct SERIES_ID) in the
    view satisfies (a), and (c) the row has >= 1 non-"-" cell and >= 2 distinct values. Units,
    aliases, PRECISION, n_matched, printed-unit presence and label agreement are recorded columns,
    never gates.
    """
    footnoted, aliases = load_frozen()
    _cols, agree, rows, _defs = read_table_page(HELD_PDF, page)
    recs = data_rows(view)
    row_records, cells_out = [], []
    for row in rows:
        cells = printed_cells(row)
        distinct = len({v for v, _ in cells.values()})
        sat = {}
        for rec in recs:
            if cells and satisfies(cells, rec):
                sat.setdefault(series_key(rec), rec)
        n = len(sat)
        if not cells or distinct < 2:
            status = "not admitted: content (c)"
        elif n == 0:
            status = "not admitted: unmapped (a)"
        elif n > 1:
            status = "not admitted: tie (b)"
        else:
            status = "admitted"
        rec = next(iter(sat.values())) if n == 1 else None
        sid = rec.get("SERIES_ID") if rec else None
        u_ok, u_how = unit_verdict(row.unit, rec.get("UNITS"), aliases) if rec else (None, None)
        prec = rec.get("PRECISION") if rec else None
        label_ok = bool(rec) and (
            labels_match(row.label, rec) or fuzzy_ratio(row.label, rec) >= FUZZY_MIN
        )
        disagreements = []
        if rec:
            if not u_ok:
                disagreements.append("unit")
            if prec is not None and row.decimals is not None and int(prec) != row.decimals:
                disagreements.append("precision")
            if not label_ok:
                disagreements.append("label")
        others = [
            r for k, r in ((series_key(r), r) for r in recs) if rec is None or k != series_key(rec)
        ]
        row_records.append(
            {
                "label": row.label,
                "status": status,
                "series_id": sid,
                "n_matched": n,
                "tied_series": sorted(sat) if n > 1 else [],
                "printed_cells": len(cells),
                "distinct_values": distinct,
                "printed_unit": row.unit,
                "printed_unit_present": row.unit is not None,
                "served_unit": rec.get("UNITS") if rec else None,
                "unit_verdict": u_how,
                "served_precision": prec,
                "printed_decimals": row.decimals,
                "label_agrees": label_ok,
                "metadata_disagreements": disagreements,
                "footnoted": (table_index, sid) in footnoted if sid else False,
                "dashes": sorted(row.dashes),
                "minus_flags": list(row.minus_flags),
                "dash_served": {
                    k: str((rec.get("DATA") or {}).get(k))
                    for k in row.dashes
                    if rec and (rec.get("DATA") or {}).get(k) is not None
                },
            }
        )
        for key, tok in row.values.items():
            if key not in cells:
                continue
            pv, dec = cells[key]
            disc = None
            if rec is not None:  # does this cell alone rule out every other series in the view?
                disc = not any(
                    (sv := served_decimal((o.get("DATA") or {}).get(key))) is not None
                    and half_away(sv, dec) == pv
                    for o in others
                )
            cells_out.append(
                {
                    "unit": unit_id,
                    "table_index": table_index,
                    "page": page,
                    "table_id": table_id,
                    "family": "STEO",
                    "series_id": sid,
                    "row": sid or f"label:{row.label}",
                    "label": row.label,
                    "period": key,
                    "col": key,
                    "band": key,
                    "header": key,
                    "value": orc.canon(tok),
                    "printed_decimals": dec,
                    "served": None
                    if rec is None or (rec.get("DATA") or {}).get(key) is None
                    else str(rec["DATA"][key]),
                    "status": status,
                    "admitted": status == "admitted",
                    "stratum": stratum(key, rec) if rec else "n/a",
                    "footnoted": (table_index, sid) in footnoted if sid else False,
                    "discriminating": disc,
                    "oracle_file": (
                        f"data/oracle/steo/2026-09/v{view}_{'Q' if len(key) == 6 else 'A'}.json"
                    ),
                }
            )
    return {
        "unit": unit_id,
        "table_index": table_index,
        "page": page,
        "table_id": table_id,
        "view": view,
        "normaliser": agree,
        "rule": "whole-row (admission_rule.md)",
        "cells": cells_out,
        "rows": row_records,
    }


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
        cols, agree, rows, _defs = read_table_page(pdf, pno)
        recs = data_rows(VIEW_OF_TABLE["2"])
        matched = match_rows(rows, recs)
        label_miss = [r.label for r, rec, _k in matched if rec is None]
        pairs = [(r, rec) for r, rec, _k in matched if rec is not None]
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
