"""D-039 item 0: draw the fresh ERP held-out granules (seed 20260930, written in D-039 at 4aca09c
before this draw).

The pool is rebuilt exactly as the T2 listing pass built it (``ledger/ingest/listing.py``
``govinfo_source``): the latest ERP package per series in ``fetch.date_range``, its granules minus
``NON_CONTENT_CLASSES``. The pool must hold 80 granules (D-039); otherwise nothing is drawn. The two
burned pilot granules are removed, then ``draw(pool, 8, seeded(20260930, "govinfo_erp"))`` - the
listing's own salt for this source - picks eight. Listing only: nothing is fetched but the API's
package and granule lists.

    uv run python scripts/a1_diag/rung1b/erp_draw.py
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

SEED = 20260930
SALT = "govinfo_erp"
N = 8
POOL_SIZE = 80
BURNED = ("ERP-2026-table4", "ERP-2026-table22")
OUT = REPO / "data" / "oracle" / "fresh" / "erp_draw.json"


def main() -> int:
    from ledger.config import load_config
    from ledger.ingest.draw import draw, seeded
    from ledger.ingest.govinfo import NON_CONTENT_CLASSES, GovInfo
    from ledger.ingest.http import Fetcher, govinfo_api_key

    cfg = load_config()
    fetcher = Fetcher(cfg.fetch)
    gi = GovInfo(fetcher, cfg.fetch, govinfo_api_key())
    start, end = cfg.fetch.date_range
    pkgs = gi.latest_per_series(gi.published("ERP", start, end))
    pool = [g for p in pkgs for g in gi.granules(p) if g.granule_class not in NON_CONTENT_CLASSES]
    ids = sorted(g.granule_id for g in pool)
    print(f"packages: {[p.package_id for p in pkgs]}; pool: {len(pool)} granules")
    if len(pool) != POOL_SIZE:
        print(f"STOP: pool is {len(pool)}, not {POOL_SIZE} (D-039) - nothing drawn")
        return 1
    missing = [b for b in BURNED if b not in ids]
    if missing:
        print(f"STOP: burned granules not in the pool: {missing}")
        return 1
    eligible = [g for g in pool if g.granule_id not in BURNED]
    pick = draw(eligible, N, seeded(SEED, SALT), key=lambda g: (g.package_id, g.granule_id))
    drawn = [
        {
            "package_id": g.package_id,
            "granule_id": g.granule_id,
            "title": g.title,
            "granule_class": g.granule_class,
        }
        for g in pick
    ]
    record = {
        "decision": "D-039 (seed written at 4aca09c, before this draw)",
        "seed": SEED,
        "salt": SALT,
        "n": N,
        "packages": [p.package_id for p in pkgs],
        "pool_size": len(pool),
        "pool_sha256": hashlib.sha256("\n".join(ids).encode()).hexdigest(),
        "pool_ids": ids,
        "excluded_burned": list(BURNED),
        "eligible": len(eligible),
        "drawn": drawn,
        "drawn_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "http_calls_by_host": fetcher.calls_by_host,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print("drawn:", [d["granule_id"] for d in drawn])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
