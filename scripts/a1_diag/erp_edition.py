"""A1 step 0 (STEO) step 4 - ERP edition assertion, keyless (D-038 item 1).

For each ERP granule the oracle uses (table4, table22), two keyless www.govinfo.gov requests go
through ``ledger.ingest.http.Fetcher`` (UA, robots, per-source delay):

* the granule MODS record (``/metadata/granule/ERP-2026/<granule>/mods.xml``): its ``dateIssued``
  must equal the held PDF's edition (``date_issued`` in ``data/manifest.jsonl``);
* the granule xls (``/content/pkg/ERP-2026/xls/<granule>.xls``): its sha256 is compared with the
  held oracle file's (``data/oracle/erp/2026-04/sources.json``).

Fetched files go to ``data/oracle/erp/2026-04/`` (gitignored); the result is appended to the
tracked ``sources.json`` as ``edition_check``. Exit 1 if an assertion fails.

    uv run python scripts/a1_diag/erp_edition.py
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
DIR = REPO / "data" / "oracle" / "erp" / "2026-04"
BASE = "https://www.govinfo.gov"
GRANULES = ("ERP-2026-table4", "ERP-2026-table22")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    from ledger.config import load_config
    from ledger.ingest.http import Fetcher

    fetcher = Fetcher(load_config().fetch)
    sources = json.loads((DIR / "sources.json").read_text(encoding="utf-8"))
    held = {f["pdf_unit"]: f for f in sources["files"]}
    manifest = {}
    for line in (REPO / "data" / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line) if line.strip() else {}
        if rec.get("record") == "unit":
            manifest[rec["unit_id"]] = rec
    checks, ok = [], True
    for g in GRANULES:
        unit = f"govinfo-{g}"
        mods_url = f"{BASE}/metadata/granule/ERP-2026/{g}/mods.xml"
        xls_url = f"{BASE}/content/pkg/ERP-2026/xls/{g}.xls"
        mods, xls = DIR / f"{g}.mods.xml", DIR / f"{g}.xls"
        fetcher.download(mods_url, mods, source="govinfo")
        fetcher.download(xls_url, xls, source="govinfo")
        text = mods.read_text(encoding="utf-8")
        issued = re.search(r"<dateIssued[^>]*>([^<]+)</dateIssued>", text)
        changed = re.search(r"<recordChangeDate[^>]*>([^<]+)</recordChangeDate>", text)
        rec = {
            "unit": unit,
            "mods_url": mods_url,
            "mods_sha256": sha(mods),
            "date_issued_mods": issued.group(1) if issued else None,
            "record_change_date": changed.group(1) if changed else None,
            "date_issued_pdf": manifest[unit]["date_issued"],
            "xls_url": xls_url,
            "xls_sha256": sha(xls),
            "xls_sha256_held": held[unit]["sha256"],
            "fetched_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        }
        rec["edition_equal"] = rec["date_issued_mods"] == rec["date_issued_pdf"]
        rec["xls_identical"] = rec["xls_sha256"] == rec["xls_sha256_held"]
        ok &= rec["edition_equal"] and rec["xls_identical"]
        checks.append(rec)
        print(json.dumps(rec, indent=1))
    sources["edition_check"] = {"passed": ok, "granules": checks}
    (DIR / "sources.json").write_text(json.dumps(sources, indent=1) + "\n", encoding="utf-8")
    print(f"hosts: {fetcher.calls_by_host}")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
