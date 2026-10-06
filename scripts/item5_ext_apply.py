"""D-037 status 2026-10-06 (item 5 extended) on the installed records ONLY — a one-off script, NOT a
CLI stage. No chunking, no Docling, no PDF: it reads ``data/parsed/<unit>.chunks.jsonl``, applies
``parse.strip_leader_runs`` (every table body cell; U+0008 before a removed run) and rewrites only
the files that change.

    uv run --no-sync python scripts/item5_ext_apply.py            # check: verify, write nothing
    uv run --no-sync python scripts/item5_ext_apply.py --apply    # back up, rewrite, rebuild

Apply order: hash everything -> back up every per-unit chunk file and ``data/chunks.jsonl`` to
``data/parsed_prefffd2_20261006/`` with a sha256 manifest (verified) -> rewrite the changed
per-unit files atomically -> rebuild ``data/chunks.jsonl`` with ``parse.write_chunks`` -> assert.
Prints the numbers as JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ledger.config import load_config  # noqa: E402
from ledger.ingest.manifest import active_rows, read_manifest  # noqa: E402
from ledger.ingest.parse import (  # noqa: E402
    FFFD_IN_NUMBER,
    SEPARATOR_ROW,
    UnitParse,
    _atomic_write,
    _strip_row_cells,
    body_of,
    build_chunker,
    strip_leader_runs,
    write_chunks,
)
from ledger.ingest.stats import tally  # noqa: E402

BACKUP = "data/parsed_prefffd2_20261006"
F = "�"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_records(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def dump(records: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def kept_by_position(records: list[dict]) -> dict:
    """U+FFFD kept in table slices: header rows / fffd_in_number singles / everything else, plus
    prefix-heading lines (expected 0). Each character counted once."""
    out = {"header": 0, "fffd_in_number": 0, "other": 0, "prefix_heading": 0}
    for r in records:
        if r["chunk_type"] != "table":
            continue
        body = body_of(r)
        out["prefix_heading"] += r["text"][: len(r["text"]) - len(body)].count(F)
        in_header = True
        for ln in body.splitlines():
            n = ln.count(F)
            if not n:
                if SEPARATOR_ROW.match(ln):
                    in_header = False
                continue
            if in_header or not ln.startswith("|"):
                out["header" if in_header else "other"] += n
                continue
            num = len(FFFD_IN_NUMBER.findall(ln))
            out["fffd_in_number"] += num
            out["other"] += n - num
    return out


def verify_pair(old: dict, new: dict) -> None:
    """One record, before -> after: only table BODY rows may differ, and only as
    ``_strip_row_cells`` makes them; every other field is identical."""
    assert old["chunk_id"] == new["chunk_id"]
    if old["chunk_type"] != "table":
        assert old == new
        return
    keys = set(old) | set(new)
    changed_ok = {"text", "body_chars", "n_tokens", "fffd_removed", "u0008_removed"}
    for k in keys - changed_ok:
        assert old.get(k) == new.get(k), (new["chunk_id"], k)
    cut_o, cut_n = len(old["text"]) - old["body_chars"], len(new["text"]) - new["body_chars"]
    assert old["text"][:cut_o] == new["text"][:cut_n], "prefix/heading region changed"
    lo = old["text"][cut_o:].splitlines(keepends=True)
    ln = new["text"][cut_n:].splitlines(keepends=True)
    assert len(lo) == len(ln), new["chunk_id"]
    seen_sep = False
    for a, b in zip(lo, ln, strict=True):
        bare = a.rstrip("\r\n")
        if SEPARATOR_ROW.match(bare):
            seen_sep = True
            assert a == b
        elif seen_sep and bare.startswith("|"):
            assert b == _strip_row_cells(bare)[0] + a[len(bare) :], (new["chunk_id"], a[:80])
        else:
            assert a == b, (new["chunk_id"], a[:80])


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

    new_by_unit: dict[str, list[dict]] = {}
    changed_units: set[str] = set()
    u0008 = 0
    for u in units:
        recs = strip_leader_runs(old_by_unit[u], chunker)
        fixed = []
        for o, n in zip(old_by_unit[u], recs, strict=True):
            if o["chunk_type"] == "table":
                this_pass = n["fffd_removed"]
                n = dict(n)
                n["fffd_removed"] = o.get("fffd_removed", 0) + this_pass  # accumulate item 5
                if n["text"] == o["text"]:  # untouched: byte-identical record
                    n = dict(o)
                else:
                    changed_units.add(u)
                    u0008 += n.get("u0008_removed", 0)
            verify_pair(o, n)
            fixed.append(n)
        new_by_unit[u] = fixed
    new_all = [r for u in units for r in new_by_unit[u]]
    assert [r["chunk_id"] for r in new_all] == [r["chunk_id"] for r in old_all]
    assert changed_units == {"govinfo-BUDGET-2027-PER"}, changed_units
    for o, n in zip(old_all, new_all, strict=True):  # nothing but the table body rows moved
        assert o["chunk_type"] == n["chunk_type"] and o["slice"] == n["slice"]
        assert o.get("question_source_barred") == n.get("question_source_barred")

    old_tab = [r for r in old_all if r["chunk_type"] == "table"]
    new_tab = [r for r in new_all if r["chunk_type"] == "table"]
    removed = sum(
        o["text"].count(F) - n["text"].count(F) for o, n in zip(old_tab, new_tab, strict=True)
    )
    total, _, _ = tally(new_all, pages)
    old_total, _, _ = tally(old_all, pages)
    assert (total.table_slices, total.chunks) == (old_total.table_slices, old_total.chunks)
    tok = sum(r["n_tokens"] for r in new_all)
    tab_tok = sum(r["n_tokens"] for r in new_tab)
    old_tok = sum(r["n_tokens"] for r in old_all)
    old_tab_tok = sum(r["n_tokens"] for r in old_tab)
    top = max(new_tab, key=lambda r: r["n_tokens"])
    top_old = max(old_tab, key=lambda r: r["n_tokens"])
    out = {
        "records": len(new_all),
        "units": len(units),
        "changed_units": sorted(changed_units),
        "changed_records": sum(o != n for o, n in zip(old_all, new_all, strict=True)),
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
        "max_table_slice_tokens": [top["n_tokens"], top_old["n_tokens"]],
        "max_table_slice_chars": [
            max(len(r["text"]) for r in new_tab),
            max(len(r["text"]) for r in old_tab),
        ],
        "max_table_slice_id": top["chunk_id"],
        "fffd_removed_by_this_extension": removed,
        "u0008_removed": u0008,
        "fffd_kept_in_table_slices": sum(r["text"].count(F) for r in new_tab),
        "fffd_kept_before": sum(r["text"].count(F) for r in old_tab),
        "fffd_kept_by_position": kept_by_position(new_tab),
        "fffd_kept_by_position_before": kept_by_position(old_tab),
        "u0008_left_in_table_slices": sum(r["text"].count("\x08") for r in new_tab),
        "fffd_in_prose": sum(r["text"].count(F) for r in new_all if r["chunk_type"] != "table"),
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
    n = write_chunks(chunks_path, parses)
    assert n == 9678
    # post-conditions, from disk
    after = read_records(chunks_path)
    assert [r["chunk_id"] for r in after] == [r["chunk_id"] for r in old_all]
    assert after == new_all
    for u in units:
        assert read_records(parsed / f"{u}.chunks.jsonl") == new_by_unit[u]
    for name, digest in protected.items():
        assert sha256(parsed / name) == digest, f"{name} changed"
    untouched = [u for u in units if u not in changed_units]
    for u in untouched:
        assert (
            sha256(parsed / f"{u}.chunks.jsonl") == bman[f"data/parsed/{u}.chunks.jsonl"]["sha256"]
        )
    out["applied"] = True
    out["backup"] = BACKUP
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
