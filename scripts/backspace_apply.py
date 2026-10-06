"""D-037 status 2026-10-06 (U+0008 removal and digit guard) on the installed records ONLY — a
one-off script, NOT a CLI stage. No chunking, no Docling, no PDF: it reads
``data/parsed/<unit>.chunks.jsonl``, applies ``parse.remove_backspaces`` and rewrites only the
files that change.

    uv run --no-sync python scripts/backspace_apply.py            # check: verify, write nothing
    uv run --no-sync python scripts/backspace_apply.py --apply    # back up, rewrite, rebuild

Apply order: hash everything -> back up every per-unit chunk file and ``data/chunks.jsonl`` to
``data/parsed_pre0008_20261006/`` with a sha256 manifest (verified) -> rewrite the changed per-unit
files atomically -> rebuild ``data/chunks.jsonl`` with ``parse.write_chunks`` -> assert. The only
change in any record is the removed U+0008 (plus the recomputed ``body_chars`` and ``n_tokens``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ledger.config import load_config  # noqa: E402
from ledger.ingest.manifest import active_rows, read_manifest  # noqa: E402
from ledger.ingest.parse import (  # noqa: E402
    UnitParse,
    _atomic_write,
    build_chunker,
    remove_backspaces,
    strip_leader_runs,
    write_chunks,
)
from ledger.ingest.stats import tally  # noqa: E402

BACKUP = "data/parsed_pre0008_20261006"
BS = "\x08"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_records(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def dump(records: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def verify_pair(old: dict, new: dict) -> int:
    """Before -> after: the text differs only by the removed U+0008; returns how many."""
    assert old["chunk_id"] == new["chunk_id"]
    for k in set(old) | set(new):
        if k not in {"text", "body_chars", "n_tokens"}:
            assert old.get(k) == new.get(k), (new["chunk_id"], k)
    assert new["text"] == old["text"].replace(BS, ""), new["chunk_id"]
    n = old["text"].count(BS)
    assert new["body_chars"] == old["body_chars"] - old["text"][-old["body_chars"] :].count(BS)
    assert (new["text"] == old["text"]) == (n == 0)
    if n == 0:
        assert old == new
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    cfg = load_config(REPO / "configs" / "base.yaml")
    parsed = REPO / cfg.paths.parsed_dir
    chunks_path = REPO / cfg.paths.chunks
    _, rows = read_manifest(REPO / cfg.paths.manifest)
    pages = {r.unit_id: (r.pages or 0) for r in active_rows(rows)}
    old_all = read_records(chunks_path)
    units: list[str] = []
    for r in old_all:
        if r["unit_id"] not in units:
            units.append(r["unit_id"])
    chunker = build_chunker(cfg)

    protected = {
        f"{u}{suf}": sha256(parsed / f"{u}{suf}")
        for u in units
        for suf in (".json", ".rowfix.json")
    }
    old_by_unit = {u: read_records(parsed / f"{u}.chunks.jsonl") for u in units}
    assert [r["chunk_id"] for r in old_all] == [
        r["chunk_id"] for u in units for r in old_by_unit[u]
    ], "data/chunks.jsonl is not the concatenation of the per-unit files"
    assert len(old_all) == 9678 and len(units) == 38, (len(old_all), len(units))

    # the digit guard narrows the item-5 strip: on the installed records it must be a no-op
    for u in units:
        again = strip_leader_runs(old_by_unit[u], chunker)
        for o, n in zip(old_by_unit[u], again, strict=True):
            assert n["text"] == o["text"], ("digit guard / item-5 strip changed", o["chunk_id"])

    new_by_unit: dict[str, list[dict]] = {}
    removed: Counter = Counter()
    changed_units: set[str] = set()
    for u in units:
        recs = remove_backspaces(old_by_unit[u], chunker)
        for o, n in zip(old_by_unit[u], recs, strict=True):
            k = verify_pair(o, n)
            if k:
                removed[(u, o["chunk_type"])] += k
                changed_units.add(u)
        new_by_unit[u] = recs
    new_all = [r for u in units for r in new_by_unit[u]]
    assert [r["chunk_id"] for r in new_all] == [r["chunk_id"] for r in old_all]
    assert all(BS not in r["text"] for r in new_all)

    total, _, _ = tally(new_all, pages)
    old_total, _, _ = tally(old_all, pages)
    assert (total.table_slices, total.chunks) == (old_total.table_slices, old_total.chunks)
    old_tab = [r for r in old_all if r["chunk_type"] == "table"]
    new_tab = [r for r in new_all if r["chunk_type"] == "table"]
    tok, old_tok = sum(r["n_tokens"] for r in new_all), sum(r["n_tokens"] for r in old_all)
    tab_tok, old_tab_tok = sum(r["n_tokens"] for r in new_tab), sum(r["n_tokens"] for r in old_tab)
    top = max(new_tab, key=lambda r: r["n_tokens"])
    by_type = Counter()
    for (_, t), n in removed.items():
        by_type[t] += n
    out = {
        "records": len(new_all),
        "units": len(units),
        "changed_units": sorted(changed_units),
        "changed_records": sum(o != n for o, n in zip(old_all, new_all, strict=True)),
        "u0008_removed": sum(removed.values()),
        "u0008_removed_by_type": dict(by_type),
        "u0008_removed_by_unit_and_type": {
            f"{u} | {t}": n for (u, t), n in sorted(removed.items())
        },
        "u0008_remaining": sum(r["text"].count(BS) for r in new_all),
        "chunk_count_share": [
            round(total.table_chunk_share, 6),
            round(old_total.table_chunk_share, 6),
        ],
        "table_slices": [total.table_slices, old_total.table_slices],
        "token_weighted": {
            "table_tokens": [tab_tok, old_tab_tok],
            "all_tokens": [tok, old_tok],
            "share": [round(tab_tok / tok, 6), round(old_tab_tok / old_tok, 6)],
        },
        "max_table_slice_tokens": [top["n_tokens"], max(r["n_tokens"] for r in old_tab)],
        "max_table_slice_chars": [
            max(len(r["text"]) for r in new_tab),
            max(len(r["text"]) for r in old_tab),
        ],
        "max_table_slice_id": top["chunk_id"],
        "digit_guard_records_affected": 0,
    }
    if not a.apply:
        print(json.dumps(out, indent=1))
        print("CHECK ONLY: nothing written")
        return

    bdir = REPO / BACKUP
    assert not bdir.exists(), f"{bdir} exists; refusing to overwrite a backup"
    bdir.mkdir(parents=True)
    bman = {}
    for p in [*(parsed / f"{u}.chunks.jsonl" for u in units), chunks_path]:
        dst = bdir / p.name
        shutil.copy2(p, dst)
        assert sha256(dst) == sha256(p), f"backup mismatch {p}"
        bman[p.relative_to(REPO).as_posix()] = {
            "backup": dst.relative_to(REPO).as_posix(),
            "sha256": sha256(p),
        }
    _atomic_write(bdir / "SHA256_MANIFEST.json", json.dumps(bman, indent=1) + "\n")
    for u in sorted(changed_units):
        _atomic_write(parsed / f"{u}.chunks.jsonl", dump(new_by_unit[u]))
    parses = [
        UnitParse(u, pages.get(u, 0), len(new_by_unit[u]), 0, 0, 0.0, records=new_by_unit[u])
        for u in units
    ]
    assert write_chunks(chunks_path, parses) == 9678
    after = read_records(chunks_path)
    assert [r["chunk_id"] for r in after] == [r["chunk_id"] for r in old_all]
    assert after == new_all
    for u in units:
        assert read_records(parsed / f"{u}.chunks.jsonl") == new_by_unit[u]
        if u not in changed_units:
            assert (
                sha256(parsed / f"{u}.chunks.jsonl")
                == bman[f"data/parsed/{u}.chunks.jsonl"]["sha256"]
            )
    for name, digest in protected.items():
        assert sha256(parsed / name) == digest, f"{name} changed"
    out["applied"] = True
    out["backup"] = BACKUP
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
