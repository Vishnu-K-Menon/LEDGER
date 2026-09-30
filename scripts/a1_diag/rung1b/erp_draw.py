"""D-039 item 0: draw the fresh ERP held-out granules (seed 20260930, written in D-039 at 4aca09c
before any draw).

Pool (owner ruling, D-039 status 2026-09-30): the TABLE-class granules of the latest ERP package
that serve a ``download.xlsLink`` (the fresh ERP family is scored against the granule-xls oracle),
minus the burned pilot granules ERP-2026-table4 and ERP-2026-table22. ``--check`` lists and counts
only (every granule summary is read for its xlsLink); ``--draw --expect N`` asserts the eligible
count reported in the status line, then ``draw(eligible, 8, seeded(20260930, "govinfo_erp"))`` -
the listing's own salt for this source. Listing only: nothing is fetched but package, granule and
summary JSON from the GovInfo API (key from the environment).

    uv run python scripts/a1_diag/rung1b/erp_draw.py --check
    uv run python scripts/a1_diag/rung1b/erp_draw.py --draw --expect N
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

SEED = 20260930
SALT = "govinfo_erp"
N = 8
BURNED = ("ERP-2026-table4", "ERP-2026-table22")
OUT = REPO / "data" / "oracle" / "fresh" / "erp_draw.json"


def sha(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--draw", action="store_true")
    ap.add_argument("--expect", type=int, help="eligible count reported in the D-039 status line")
    args = ap.parse_args()

    from ledger.config import load_config
    from ledger.ingest.draw import draw, seeded
    from ledger.ingest.govinfo import GovInfo
    from ledger.ingest.http import Fetcher, govinfo_api_key

    cfg = load_config()
    fetcher = Fetcher(cfg.fetch)
    gi = GovInfo(fetcher, cfg.fetch, govinfo_api_key())
    start, end = cfg.fetch.date_range
    pkgs = gi.latest_per_series(gi.published("ERP", start, end))
    assert len(pkgs) == 1, [p.package_id for p in pkgs]
    granules = gi.granules(pkgs[0])
    classes = Counter(g.granule_class for g in granules)
    tables = [g for g in granules if g.granule_class == "TABLE"]
    xls: dict[str, str | None] = {}
    for g in tables:
        s = gi._get(f"/packages/{g.package_id}/granules/{g.granule_id}/summary")
        xls[g.granule_id] = ((s.get("download") or {}) or {}).get("xlsLink")
    no_xls = sorted(gid for gid, link in xls.items() if not link)
    pool = [g for g in tables if xls[g.granule_id]]
    eligible = [g for g in pool if g.granule_id not in BURNED]
    burned_in_pool = [b for b in BURNED if b in {g.granule_id for g in pool}]
    print(f"package {pkgs[0].package_id}: {len(granules)} granules {dict(classes)}")
    print(f"TABLE granules: {len(tables)}; with xlsLink: {len(pool)}; without: {no_xls}")
    print(f"burned in pool: {burned_in_pool}; eligible: {len(eligible)}")
    if args.check or not args.draw:
        return 0
    assert args.expect is not None, "--draw needs --expect (the count in the status line)"
    if len(eligible) != args.expect:
        print(f"STOP: eligible is {len(eligible)}, the status line says {args.expect}")
        return 1
    if len(eligible) < N:
        print(f"STOP: fewer than {N} eligible granules")
        return 1
    pick = draw(eligible, N, seeded(SEED, SALT), key=lambda g: (g.package_id, g.granule_id))
    record = {
        "decision": "D-039 (seed at 4aca09c; pool ruling in its status line, before this draw)",
        "seed": SEED,
        "salt": SALT,
        "n": N,
        "package": pkgs[0].package_id,
        "package_granules": len(granules),
        "granule_classes": dict(classes),
        "table_granules_without_xlslink": no_xls,
        "pool_rule": "TABLE-class granules serving download.xlsLink",
        "pool_ids": sorted(g.granule_id for g in pool),
        "pool_sha256": sha([g.granule_id for g in pool]),
        "excluded_burned": list(BURNED),
        "eligible_ids": sorted(g.granule_id for g in eligible),
        "eligible_sha256": sha([g.granule_id for g in eligible]),
        "drawn": [
            {"granule_id": g.granule_id, "title": g.title, "xls_link": xls[g.granule_id]}
            for g in pick
        ],
        "drawn_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "http_calls_by_host": fetcher.calls_by_host,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print("drawn:", [d["granule_id"] for d in record["drawn"]])
    print("pool sha256", record["pool_sha256"], "eligible sha256", record["eligible_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
