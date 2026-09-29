"""Write the tracked hash manifests for the MER and ERP oracle files (D-038, owner 2026-09-29).

``oracle.py`` records every oracle file it fetched or used in
``reports/a1_diag/oracle/sources.json``, which is gitignored. D-038 cites those hashes, so this
writes them to tracked manifests beside the STEO snapshot's:

* ``data/oracle/mer/2026-09/sources.json`` - the 47 MER per-table xlsx exports (URL, sha256, fetch
  time, stated release, the printed table id they serve);
* ``data/oracle/erp/2026-04/sources.json`` - the two held ERP granule xls files (sha256).

The files themselves stay where they are, local and untracked.

    uv run python scripts/a1_diag/oracle_manifests.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "reports" / "a1_diag" / "oracle" / "sources.json"


def main() -> int:
    records = json.loads(SRC.read_text(encoding="utf-8"))
    mer = [
        r
        for u, r in records.items()
        if "xls.php" in u and r.get("type", "").startswith("OOXML") and r.get("export_title")
    ]
    erp = [r for u, r in records.items() if u.startswith("held:")]
    keep = (
        "url",
        "path",
        "sha256",
        "bytes",
        "fetched_at",
        "type",
        "release",
        "table_id",
        "table_id_printed",
        "export_title",
        "pdf_unit",
        "pdf_date_issued",
        "pdf_creation_date",
    )
    out = {
        REPO / "data" / "oracle" / "mer" / "2026-09" / "sources.json": {
            "tag": "MER per-table Excel exports, release 2026-09-29 (PDFs: August 2026 edition)",
            "admission": "A6 - a cell counts only if its value is printed in the table bbox",
            "files": [{k: r.get(k) for k in keep if r.get(k) is not None} for r in mer],
        },
        REPO / "data" / "oracle" / "erp" / "2026-04" / "sources.json": {
            "tag": "ERP-2026 granule xls, held since 2026-09-26 (reports/a1_digits)",
            "files": [{k: r.get(k) for k in keep if r.get(k) is not None} for r in erp],
        },
    }
    for path, body in out.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body, indent=1), encoding="utf-8")
        print(f"{path.relative_to(REPO).as_posix()}: {len(body['files'])} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
