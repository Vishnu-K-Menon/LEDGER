"""D-039: the fresh MER / ERP admission (built after the fresh parse; frozen before any rung-1b
output exists). Counts only are reported; no cell value or page text is printed.

From the fresh parse ONLY each TableItem's ``prov`` (page and bbox) is used: stub documents
``{"tables": [{"prov": ...}], "texts": []}`` are written to a local mirror tree
(``data/parsed_rung1/_cache/fresh_mirror/``) beside sha256-verified copies of the fresh PDFs, and
the UNCHANGED ``oracle.py`` (A6) and ``f5_sizing.py`` (the clause-(b) checker) are run against
that tree by pointing their module ``REPO`` at it in-process - no code of either is edited.

* MER (39 matched tables, ``data/oracle/fresh/mer/sources.json`` ``fresh_set``): per matched page,
  every TableItem on it is admitted against the page's export (``oracle.read_page`` +
  ``oracle.admit``: A6, per cell), then clause (b) (D-039 status 2026-09-30): an A6-admitted cell
  stays admitted only if its value is on the row label's text line (``f5_sizing.row_lines``; a
  token equal once a leading/trailing R / E / RE flag is stripped counts as on the line - owner
  fill). A matched page with NO TableItem keeps its table in the set: the page's full text area is
  the region, and every admitted cell is flagged ``miss_by_rule`` (D-039 status ruling 3).
  Not-on-the-line strata by band token (census rule: R / E / RE stripped, attached or separated):
  numeric-but-different, placeholder (NA / (s)), split-token (joined = value / != value),
  empty band, other non-numeric. Tripwire (D-039 status 2026-09-30, ruling 2): numeric-but-different
  > 1 % of a section's A6-admitted cells -> STOP before any rung-1b output.
* ERP (8 drawn granules): A6 per cell against the granule xls, sheet i <-> the i-th TableItem
  (``oracle.py``'s pilot mapping); clause (b) is MER's (D-039).

    uv run --with pdfplumber --with openpyxl --with xlrd python \
        scripts/a1_diag/rung1b/fresh_admission.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import f5_dump  # noqa: E402
import f5_sizing as f5  # noqa: E402
import oracle as orc  # noqa: E402

FRESH = REPO / "data" / "oracle" / "fresh"
PARSED = REPO / "data" / "parsed_fresh"
RAW = REPO / "data" / "raw_fresh"
MIRROR = REPO / "data" / "parsed_rung1" / "_cache" / "fresh_mirror"
ADM = FRESH / "admission"
REPORT = REPO / "reports" / "a1_diag" / "rung1b" / "fresh_admission.md"
TRIPWIRE = 0.01
MER_SECTIONS = (2, 5, 6, 7, 9, 10, 12)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def stub(unit: str, extra: list[dict] | None = None) -> dict:
    """The fresh parse reduced to its TableItems' prov (page, bbox); no text of any kind."""
    doc = json.loads((PARSED / f"{unit}.json").read_text(encoding="utf-8"))
    tables = [{"prov": t["prov"]} for t in doc.get("tables", [])]
    return {"tables": tables + (extra or []), "texts": []}


def build_mirror(units: list[tuple[str, str]], extras: dict[str, list[dict]]) -> None:
    for unit, source in units:
        (MIRROR / "data" / "parsed").mkdir(parents=True, exist_ok=True)
        (MIRROR / "data" / "raw" / source).mkdir(parents=True, exist_ok=True)
        s = stub(unit, extras.get(unit))
        (MIRROR / "data" / "parsed" / f"{unit}.json").write_text(json.dumps(s), "utf-8")
        src = RAW / source / f"{unit}.pdf"
        dst = MIRROR / "data" / "raw" / source / f"{unit}.pdf"
        shutil.copyfile(src, dst)
        assert sha(src) == sha(dst), unit


def text_area_prov(unit: str, page: int) -> dict:
    """ruling 3: the page's full text area as the table region (TOPLEFT points)."""
    import pdfplumber

    with pdfplumber.open(RAW / "eia" / f"{unit}.pdf") as pdf:
        ch = [c for c in pdf.pages[page - 1].chars if c["text"].strip()]
    return {
        "page_no": page,
        "bbox": {
            "l": min(c["x0"] for c in ch),
            "t": min(c["top"] for c in ch),
            "r": max(c["x1"] for c in ch),
            "b": max(c["bottom"] for c in ch),
            "coord_origin": "TOPLEFT",
        },
    }


def band_class(c: dict, ln: list[dict] | None, band) -> tuple[str, str]:
    if ln is None:
        return "row line not found", ""
    toks_raw = [x["text"] for x in ln if band and orc.band_index(x, [band]) == 0]
    printed = " ".join(toks_raw)
    if not toks_raw:
        return "empty band", printed
    toks = f5_dump.tolerant_tokens(printed)
    if len(toks) == 1 and orc.canon(toks[0]) is not None:
        return "numeric-but-different", printed
    if len(toks) == 1 and (toks[0] in orc.PLACEHOLDERS or toks[0] == "NA"):
        return "placeholder", printed
    if len(toks) >= 2 and all(orc.canon(t) is not None for t in toks):
        joined = orc.canon("".join(toks))
        return (
            "split-token, joined == value"
            if joined == c["value"]
            else "split-token, joined != value (numeric-but-different)"
        ), printed
    return "other non-numeric", printed


def clause_b(cells: list[dict], rl: dict) -> None:
    """f5_sizing's on-the-line test (as at 5f7e568), applied to A6-admitted cells."""
    bands = rl["bands"]
    for c in cells:
        if not c["admitted"]:
            c["clause_b"] = "not A6-admitted"
            continue
        ln = rl["by_key"].get(c["row"])
        if ln is None:
            outcome = "row line not found"
        else:
            canon = [orc.canon(x["text"]) for x in ln]
            flag = [orc.canon(f5.FLAG.sub("", x["text"])) for x in ln]
            outcome = (
                "on the line"
                if c["value"] in canon
                else "on the line only with a revision flag"
                if c["value"] in flag
                else "not on the line"
            )
        c["clause_b"] = outcome
        c["admitted_b"] = outcome in ("on the line", "on the line only with a revision flag")
        if not c["admitted_b"]:
            band = bands[c["band"]] if c["band"] is not None and c["band"] < len(bands) else None
            c["band_class"], c["band_text"] = band_class(c, ln, band)


def main() -> int:
    import xlrd

    mer_src = json.loads((FRESH / "mer" / "sources.json").read_text(encoding="utf-8"))
    in_set = set(tuple(x.split(":", 1)) for x in mer_src["fresh_set"]["tables"])
    assert len(in_set) == 39, len(in_set)
    export_of = {x["url"].split("tbl=")[1]: x for x in mer_src["exports"].values()}
    pages = [
        p for p in mer_src["pages"] if p.get("title_match") and (p["unit"], p["table_id"]) in in_set
    ]
    erp_src = json.loads((FRESH / "erp" / "sources.json").read_text(encoding="utf-8"))

    # pages without a detected TableItem get the page text area (ruling 3)
    extras: dict[str, list[dict]] = defaultdict(list)
    undetected = []
    for p in pages:
        s = stub(p["unit"])
        if not any(t["prov"][0]["page_no"] == p["page"] for t in s["tables"] if t["prov"]):
            extras[p["unit"]].append(
                {"prov": [text_area_prov(p["unit"], p["page"])], "_undetected": True}
            )
            undetected.append(f"{p['unit']} p{p['page']} ({p['table_id']})")
    units = [(f"eia-pdf-sec{n}", "eia") for n in MER_SECTIONS] + [
        (f"govinfo-{g}", "govinfo_erp") for g in erp_src["granules"]
    ]
    build_mirror(units, extras)
    orc.REPO = MIRROR  # the unchanged oracle and checker now read the mirror tree
    f5.REPO = MIRROR

    mer_cells: list[dict] = []
    tables: list[dict] = []
    for p in pages:
        unit, page, tid = p["unit"], p["page"], p["table_id"]
        doc = json.loads((MIRROR / "data" / "parsed" / f"{unit}.json").read_text("utf-8"))
        tis = [i for i, t in enumerate(doc["tables"]) if t["prov"][0]["page_no"] == page]
        xrec = export_of[p["export"]]
        ot = orc.mer_oracle(REPO / xrec["path"])
        for ti in tis:
            undet = bool(doc["tables"][ti].get("_undetected"))
            pg = orc.read_page(unit, "eia", ti, doc)
            pg.table_id = tid
            cells, note = orc.admit(pg, ot, unit, xrec["path"])
            if cells:
                clause_b(cells, f5.row_lines(unit, ti))
            for c in cells:
                c["family"] = "MER"
                c["undetected_region"] = undet
                c["miss_by_rule"] = undet and c.get("admitted_b", False)
            mer_cells += cells
            tables.append(
                {
                    "family": "MER",
                    "unit": unit,
                    "page": page,
                    "table_id": tid,
                    "table_index": ti,
                    "undetected": undet,
                    "note": note,
                    "oracle_cells": len(cells),
                    "a6_admitted": sum(c["admitted"] for c in cells),
                    "admitted_b": sum(c.get("admitted_b", False) for c in cells),
                }
            )

    erp_cells: list[dict] = []
    for gid, g in erp_src["granules"].items():
        unit = f"govinfo-{gid}"
        doc = json.loads((MIRROR / "data" / "parsed" / f"{unit}.json").read_text("utf-8"))
        xls = REPO / g["xls_path"]
        nsheets = xlrd.open_workbook(str(xls)).nsheets
        ntab = len(doc["tables"])
        for si in range(min(nsheets, ntab)):
            pg = orc.read_page(unit, "govinfo_erp", si, doc)
            pg.table_id = f"{gid} sheet{si}"
            cells, note = orc.admit(pg, orc.erp_oracle(xls, si), unit, g["xls_path"])
            for c in cells:
                c["family"] = "ERP"
            erp_cells += cells
            tables.append(
                {
                    "family": "ERP",
                    "unit": unit,
                    "page": pg.page,
                    "table_id": pg.table_id,
                    "table_index": si,
                    "note": note
                    + ("" if nsheets == ntab else f"; sheets {nsheets} vs TableItems {ntab}"),
                    "oracle_cells": len(cells),
                    "a6_admitted": sum(c["admitted"] for c in cells),
                }
            )

    ADM.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, rows in (("mer_cells.jsonl", mer_cells), ("erp_cells.jsonl", erp_cells)):
        body = "".join(json.dumps(c, sort_keys=True) + "\n" for c in rows)
        (ADM / name).write_text(body, encoding="utf-8")
        files[name] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    tbody = json.dumps(tables, indent=1, sort_keys=True)
    (ADM / "tables.json").write_text(tbody, encoding="utf-8")
    files["tables.json"] = hashlib.sha256(tbody.encode("utf-8")).hexdigest()

    # per-section report and the tripwire
    sec = defaultdict(Counter)
    for c in mer_cells:
        s = sec[c["unit"]]
        s["oracle"] += 1
        s["a6"] += c["admitted"]
        if c["admitted"]:
            s[c["clause_b"]] += 1
            s["admitted_b"] += c.get("admitted_b", False)
            s["miss_by_rule"] += c["miss_by_rule"]
            if not c.get("admitted_b", False):
                s["cls:" + c.get("band_class", "")] += 1
    detected_ids = {
        (t["unit"], t["table_id"]) for t in tables if t["family"] == "MER" and not t["undetected"]
    }
    tabsec = defaultdict(lambda: Counter())
    for t in tables:
        if t["family"] == "MER":
            tabsec[t["unit"]]["tableitems"] += 1
            tabsec[t["unit"]]["undetected"] += t["undetected"]
    matched = Counter(u for u, _ in in_set)
    tripped = []
    L = [
        "# D-039 - fresh MER / ERP admission (counts only)",
        "",
        "From the fresh parse only TableItem page + bbox (stub documents); the unchanged "
        "`oracle.py` (A6) and `f5_sizing.py` (clause (b)) run on a sha256-verified mirror tree. "
        "MER: A6 then clause (b); a page with no TableItem uses the page text area and every "
        "admitted cell there is a miss by rule. ERP: A6 against the granule xls.",
        "",
        f"MER matched tables: {len(in_set)} (fresh set). Matched pages: {len(pages)}. Pages with "
        f"no detected TableItem (page-text-area region, ruling 3): {len(undetected)} "
        f"{undetected}.",
        "",
        f"**Ruling 3 applies to {len(in_set - detected_ids)} tables** "
        f"{sorted(f'{u}:{t}' for u, t in in_set - detected_ids)}: every other matched table has a "
        f"detected TableItem on its table page. The {len(undetected)} page(s) above are "
        "Sources-notes pages whose top-quarter line is 'Table X.Y Sources' for an id already "
        "matched on its table page (the scan carries the first page's export match to a repeated "
        "id); each contributes "
        f"{sum(t['oracle_cells'] for t in tables if t['family'] == 'MER' and t['undetected'])} "
        "oracle cells. Reported, not changed (a further scan change is the owner's).",
        "",
        "| section | matched tables | TableItems admitted | undetected regions | oracle cells | "
        "A6-admitted | on the line | flag only | not on the line | row not found | admitted "
        "after (b) | miss by rule | numeric-but-different | share of A6 | tripwire (> 1 %) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for n in MER_SECTIONS:
        u = f"eia-pdf-sec{n}"
        s, t = sec[u], tabsec[u]
        nbd = (
            s["cls:numeric-but-different"]
            + s["cls:split-token, joined != value (numeric-but-different)"]
        )
        share = nbd / s["a6"] if s["a6"] else 0.0
        hit = share > TRIPWIRE
        if hit:
            tripped.append(u)
        L.append(
            f"| sec{n} | {matched[u]} | {t['tableitems']} | {t['undetected']} | {s['oracle']} | "
            f"{s['a6']} | {s['on the line']} | {s['on the line only with a revision flag']} | "
            f"{s['not on the line']} | {s['row line not found']} | {s['admitted_b']} | "
            f"{s['miss_by_rule']} | {nbd} | {share:.2%} | {'**HIT**' if hit else 'ok'} |"
        )
    strata = Counter()
    for s in sec.values():
        for k, v in s.items():
            if k.startswith("cls:"):
                strata[k[4:]] += v
    L += [
        "",
        "Clause-(b) exclusions by band class (all sections): "
        + ", ".join(f"{k} {v}" for k, v in strata.most_common())
        + ".",
        "",
    ]
    e = Counter()
    for c in erp_cells:
        e["oracle"] += 1
        e["a6"] += c["admitted"]
    L += [
        "## ERP (A6, granule xls)",
        "",
        f"{len(erp_src['granules'])} granules · {sum(1 for t in tables if t['family'] == 'ERP')} "
        f"sheet/TableItem pairs · oracle cells {e['oracle']} · A6-admitted {e['a6']} "
        f"({(e['a6'] / e['oracle']) if e['oracle'] else 0:.1%}).",
        "",
        "| granule | page | oracle cells | A6-admitted | note |",
        "|---|---|---|---|---|",
    ]
    for t in tables:
        if t["family"] == "ERP":
            L.append(
                f"| {t['table_id']} | {t['page']} | {t['oracle_cells']} | "
                f"{t['a6_admitted']} | {t['note'][:60]} |"
            )
    L += [
        "",
        "**Tripwire:** "
        + (
            f"HIT in {tripped} - STOP before any rung-1b output."
            if tripped
            else "not hit in any section."
        ),
        "",
    ]
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    (ADM / "files_sha256.json").write_text(json.dumps(files, indent=1), encoding="utf-8")
    print("\n".join(L))
    return 2 if tripped else 0


if __name__ == "__main__":
    raise SystemExit(main())
