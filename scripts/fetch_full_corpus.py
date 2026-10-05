# ruff: noqa: E501
"""D-034 status 2026-10-04: fetch the drawn full-corpus units through ``fetch.run_fetch``, scoped
(``only=``) to the rows that have not been fetched yet, so every pilot row passes through unchanged.

    uv run python scripts/fetch_full_corpus.py

Backs up ``data/manifest.jsonl`` to ``data/manifest.prefetch_20261004.jsonl`` first (sha256 printed);
afterwards every pre-existing line must be byte-identical, else the backup is restored and the
script stops. Needs ``GOVINFO_API_KEY`` in the environment. CBO rows stay pending (owner fetch).
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ledger.config import load_config  # noqa: E402
from ledger.ingest.fetch import render_fetch_report, run_fetch  # noqa: E402
from ledger.ingest.manifest import read_manifest  # noqa: E402

MANIFEST = REPO / "data" / "manifest.jsonl"
BACKUP = REPO / "data" / "manifest.prefetch_20261004.jsonl"


def main() -> None:
    cfg = load_config(REPO / "configs" / "base.yaml")
    _, rows = read_manifest(MANIFEST)
    todo = {
        r.unit_id
        for r in rows
        if r.status == "ACTIVE" and not r.sha256 and not any("UNFETCHABLE" in n for n in r.notes)
    }
    shutil.copy2(MANIFEST, BACKUP)
    before = MANIFEST.read_bytes()
    assert BACKUP.read_bytes() == before
    print(f"backup {BACKUP.name} sha256 {hashlib.sha256(before).hexdigest()}")
    print(f"scope: {len(todo)} unfetched ACTIVE rows")
    res = run_fetch(cfg, repo=REPO, only=todo)
    print(render_fetch_report(res))
    old = before.splitlines(keepends=True)
    after = MANIFEST.read_bytes().splitlines(keepends=True)
    keep = len(old)
    changed = [i for i in range(keep) if after[i] != old[i]]
    # the appended rows are the last len(todo) lines; only they may differ
    pre_existing = [i for i in range(keep) if old[i] and _unit_id(old[i]) not in todo]
    bad = [i for i in pre_existing if after[i] != old[i]]
    if bad or len(after) != len(old):
        MANIFEST.write_bytes(before)
        raise SystemExit(f"STOP: pre-existing line(s) {bad} changed; the backup was restored")
    print(
        f"pre-existing lines byte-identical: {len(pre_existing)} (changed in-scope rows: {len(changed)})"
    )
    print(f"manifest sha256 now {hashlib.sha256(MANIFEST.read_bytes()).hexdigest()}")


def _unit_id(line: bytes) -> str:
    import json

    d = json.loads(line)
    return d.get("unit_id", "")


if __name__ == "__main__":
    main()
