"""A1 step 0 - snapshot the STEO September 2026 quarterly and annual series (D-038 item 1).

STEO's printed tables are quarterly and annual, but its only published workbook, ``STEO_m.xlsx``,
is monthly: there is no ``STEO_q.xlsx`` (404) and no ``STEO_a.xlsx`` (probed here). The data
browser serves every printed table as JSON:

    https://www.eia.gov/outlooks/steo/data/browser/data/index.php?v=<view>&f=<Q|A|M>&method=getData

That endpoint is undocumented and unversioned. The October release will overwrite what it serves,
so **the snapshot is the mitigation**: every view in the browser's table list (from ``data.php``),
at f = Q and A, is saved raw under ``data/oracle/steo/2026-09/``, and ``sources.json`` there
(tracked in git) records URL, UTC time and sha256 for each file.

**Edition check.** The monthly values of two views (Table 1, v=3; Table 2, v=8) are fetched at f=M
and compared with the held ``STEO_m.xlsx`` at each series' PRECISION (Decimal round-half-up). They
must agree for the snapshot to carry the tag "STEO 2026-09, release 2026-09-09".

**PDF check.** The held ``data/raw/eia/eia-pdf-steo_full.pdf`` is hashed, and EIA's current
``steo_full.pdf`` is fetched into the snapshot directory (never ``data/raw``) and hashed. A
difference would show EIA's 2026-09-10 correction to an Overview table.

Every request goes through ``ledger.ingest.http.Fetcher`` (UA, robots, 2 s EIA delay), and only to
eia.gov. No API key is used.

    uv run python scripts/a1_diag/steo_snapshot.py
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

SNAP = REPO / "data" / "oracle" / "steo" / "2026-09"
DATA_URL = "https://www.eia.gov/outlooks/steo/data/browser/data/index.php"
STEO_M = REPO / "reports" / "a1_diag" / "oracle" / "src" / "STEO_m.xlsx"
HELD_PDF = REPO / "data" / "raw" / "eia" / "eia-pdf-steo_full.pdf"
CURRENT_PDF_URL = "https://www.eia.gov/outlooks/steo/pdf/steo_full.pdf"
PROBES = (
    "https://www.eia.gov/outlooks/steo/xls/STEO_q.xlsx",
    "https://www.eia.gov/outlooks/steo/xls/STEO_a.xlsx",
)
# the data browser's table list, as data.php links it (view id -> printed table id)
VIEWS = {
    3: "1",
    8: "2",
    6: "3a",
    29: "3b",
    7: "3c",
    30: "3d",
    31: "3e",
    9: "4a",
    27: "4b",
    10: "4c",
    11: "4d",
    15: "5a",
    16: "5b",
    18: "6",
    19: "7a",
    20: "7b",
    21: "7c",
    22: "7d",
    23: "7e",
    24: "8a",
    5: "9a",
    4: "9b",
    28: "9c",
    32: "10a",
    33: "10b",
}
MONTH_CHECK = {3: "1tab", 8: "2tab"}  # view -> STEO_m.xlsx sheet


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def quantize(value, precision: int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP)


def month_check(view: int, sheet: str, path: Path) -> dict:
    """Every monthly JSON value vs STEO_m.xlsx, both rounded half-up at the series PRECISION."""
    import openpyxl

    rows = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)["VIEWSDATA"]["ROWS"]
    ws = openpyxl.load_workbook(STEO_M, data_only=True)[sheet]
    years, col_of = None, {}
    for c in range(3, ws.max_column + 1):
        y = ws.cell(3, c).value
        years = y if isinstance(y, int) else years
        m = ws.cell(4, c).value
        if years and isinstance(m, str):
            month = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split().index(m[:3]) + 1
            col_of[f"{years}{month:02d}"] = c
    row_of = {
        str(ws.cell(r, 1).value).strip(): r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value
    }
    equal = unequal = missing = 0
    examples = []
    for rec in rows:
        sid, prec, data = rec.get("SERIES_ID"), rec.get("PRECISION"), rec.get("DATA") or {}
        if not sid or prec is None or not isinstance(data, dict):
            continue
        r = row_of.get(sid) or row_of.get(sid.split("_")[0])
        for period, v in data.items():
            c = col_of.get(period)
            if r is None or c is None:
                missing += 1
                continue
            w = ws.cell(r, c).value
            if w is None or v is None:
                missing += 1
                continue
            if quantize(v, int(prec)) == quantize(w, int(prec)):
                equal += 1
            else:
                unequal += 1
                if len(examples) < 5:
                    examples.append((sid, period, str(v), str(w)))
    return {
        "view": view,
        "sheet": sheet,
        "equal": equal,
        "unequal": unequal,
        "not_in_both": missing,
        "examples": examples,
    }


def main() -> int:
    from ledger.config import load_config
    from ledger.ingest.http import Fetcher

    fetcher = Fetcher(load_config().fetch)
    SNAP.mkdir(parents=True, exist_ok=True)
    sources: dict = {
        "tag": "STEO 2026-09, release 2026-09-09",
        "endpoint": DATA_URL,
        "note": "undocumented, unversioned JSON endpoint; this snapshot is the mitigation",
        "files": [],
    }
    # 0. the workbooks that do not exist
    probes = []
    for url in PROBES:
        try:
            r = fetcher.get(url, source="eia")
            probes.append({"url": url, "status": r.status_code, "bytes": len(r.content)})
        except Exception as exc:  # noqa: BLE001 - a 404 is the finding
            status = getattr(getattr(exc, "response", None), "status_code", None)
            probes.append({"url": url, "status": status or repr(exc)[:80]})
    sources["probes"] = probes
    # 1. every view at Q and A, plus M for the two edition-check views
    for view, table in VIEWS.items():
        for f in ("Q", "A") + (("M",) if view in MONTH_CHECK else ()):
            dest = SNAP / f"v{view}_{f}.json"
            params = {"v": view, "f": f, "method": "getData"}
            fetcher.download(DATA_URL, dest, source="eia", params=params)
            body = json.loads(dest.read_text(encoding="utf-8"))
            rows = body.get("VIEWSDATA", {}).get("ROWS", [])
            sources["files"].append(
                {
                    "table": table,
                    "view": view,
                    "f": f,
                    "url": DATA_URL,
                    "params": params,
                    "path": dest.relative_to(REPO).as_posix(),
                    "sha256": sha(dest),
                    "bytes": dest.stat().st_size,
                    "fetched_utc": now(),
                    "rows": len(rows),
                    "series": sum(1 for x in rows if x.get("HAS_DATA")),
                    "periods": len(body.get("VIEWSDATA", {}).get("DATACOLUMNS", [])),
                }
            )
    # 2. edition check against the held monthly workbook
    sources["steo_m_xlsx"] = {"path": STEO_M.relative_to(REPO).as_posix(), "sha256": sha(STEO_M)}
    sources["month_check"] = [
        month_check(v, sheet, SNAP / f"v{v}_M.json") for v, sheet in MONTH_CHECK.items()
    ]
    # 3. the held PDF vs EIA's current file
    current = SNAP / "steo_full_current.pdf"
    fetcher.download(CURRENT_PDF_URL, current, source="eia")
    sources["pdf"] = {
        "held": {
            "path": HELD_PDF.relative_to(REPO).as_posix(),
            "sha256": sha(HELD_PDF),
            "bytes": HELD_PDF.stat().st_size,
        },
        "current": {
            "url": CURRENT_PDF_URL,
            "path": current.relative_to(REPO).as_posix(),
            "sha256": sha(current),
            "bytes": current.stat().st_size,
            "fetched_utc": now(),
        },
    }
    sources["pdf"]["identical"] = (
        sources["pdf"]["held"]["sha256"] == sources["pdf"]["current"]["sha256"]
    )
    sources["http_calls_by_host"] = dict(fetcher.calls_by_host)
    (SNAP / "sources.json").write_text(json.dumps(sources, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in sources.items() if k != "files"}, indent=1))
    print(f"files: {len(sources['files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
