"""D-037 item 5 on the installed pilot records ONLY — a one-off script, NOT a CLI stage.

Applies the same post-chunking transform ``parse.chunk_document`` now carries (leader-run strip,
``fffd_in_number`` bar, ``header_row_cause``) to ``data/parsed/<unit>.chunks.jsonl``. No chunking,
no Docling, no PDF: the saved exports (read-only) give each table's attached caption, and the
re-chunk's MANIFEST.json gives the item-4 ``header_not_repeated`` lists.

    uv run python scripts/item5_pilot.py            # check: verify everything, write nothing
    uv run python scripts/item5_pilot.py --apply    # back up, rewrite, rebuild chunks.jsonl

Order of work (apply): hash everything -> back up the 13 chunk files and ``data/chunks.jsonl`` to
``data/parsed_prefffd_20261002/`` with a sha256 manifest and verify the copy -> rewrite each
``<unit>.chunks.jsonl`` -> rebuild ``data/chunks.jsonl`` with ``parse.write_chunks`` -> assert.
Prints the numbers for ``reports/rechunk_20261002.md`` as a JSON object.
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
    LEADER_RUN,
    SEPARATOR_ROW,
    UnitParse,
    _atomic_write,
    build_chunker,
    captioned_tables,
    header_row_causes,
    mark_fffd_bars,
    mark_header_row_causes,
    strip_leader_runs,
    write_chunks,
)
from ledger.ingest.stats import tally  # noqa: E402

BACKUP = "data/parsed_prefffd_20261002"
CHANGED_BY_ITEM5 = {"text", "body_chars", "n_tokens", "fffd_removed"}
ADDED_BY_ITEM5 = {"fffd_removed", "header_row_cause"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_records(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def dump(records: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def first_cell_strip(line: str) -> str:
    """The expected new line: leader runs removed from the first cell only."""
    bare = line.rstrip("\r\n")
    i, end = 1, len(bare)
    while i < len(bare):
        if bare[i] == "\\":
            i += 2
            continue
        if bare[i] == "|":
            end = i
            break
        i += 1
    return "|" + LEADER_RUN.sub("", bare[1:end]) + line[end:]


def verify_pair(old: dict, new: dict) -> None:
    """One record, before -> after: item 5 touched only the first cell of body rows."""
    assert old["chunk_id"] == new["chunk_id"]
    extra = set(new) - set(old)
    assert extra <= ADDED_BY_ITEM5, (new["chunk_id"], extra)
    for k in old:
        if k in CHANGED_BY_ITEM5 or k == "question_source_barred":
            continue
        assert old[k] == new[k], (new["chunk_id"], k)
    if old["chunk_type"] != "table":
        assert old == new
        return
    cut = len(old["text"]) - old["body_chars"]
    assert old["text"][:cut] == new["text"][: len(new["text"]) - new["body_chars"]], "front part"
    old_lines = old["text"][cut:].splitlines(keepends=True)
    new_lines = new["text"][len(new["text"]) - new["body_chars"] :].splitlines(keepends=True)
    assert len(old_lines) == len(new_lines), new["chunk_id"]
    seen_sep = False
    for a, b in zip(old_lines, new_lines, strict=True):
        if SEPARATOR_ROW.match(a.rstrip("\r\n")):
            seen_sep = True
            assert a == b
        elif seen_sep and a.startswith("|"):
            assert b == first_cell_strip(a), (new["chunk_id"], a[:80])
        else:
            assert a == b, (new["chunk_id"], a[:80])
    ob, nb = old["question_source_barred"], new["question_source_barred"]
    assert nb["reasons"][: len(ob["reasons"])] == ob["reasons"]
    assert set(nb["reasons"]) - set(ob["reasons"]) <= {"fffd_in_number"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--config", type=Path, default=REPO / "configs" / "base.yaml")
    a = ap.parse_args()
    cfg = load_config(a.config)
    parsed = REPO / cfg.paths.parsed_dir
    chunks_path = REPO / cfg.paths.chunks
    manifest = json.loads((REPO / "data/rechunk_20261002/MANIFEST.json").read_text("utf-8"))
    units: list[str] = manifest["units"]
    item4 = manifest["d037_item4_checks"]
    _, rows = read_manifest(REPO / cfg.paths.manifest)
    pages = {r.unit_id: (r.pages or 0) for r in active_rows(rows)}
    chunker = build_chunker(cfg)

    protected = {
        f"{u}{suf}": sha256(parsed / f"{u}{suf}")
        for u in units
        for suf in (".json", ".rowfix.json")
    }
    old_by_unit = {u: read_records(parsed / f"{u}.chunks.jsonl") for u in units}
    old_all = read_records(chunks_path)
    assert [r["chunk_id"] for r in old_all] == [
        r["chunk_id"] for u in units for r in old_by_unit[u]
    ]
    assert len(old_all) == 6358

    new_by_unit: dict[str, list[dict]] = {}
    causes_all: dict[str, str] = {}
    for u in units:
        recs = strip_leader_runs(old_by_unit[u], chunker)
        recs = mark_fffd_bars(recs)
        raw = json.loads((parsed / f"{u}.json").read_text(encoding="utf-8"))
        causes = header_row_causes(
            recs, item4[u]["header_not_repeated"], captioned_tables(raw), chunker,
            cfg.chunking.max_tokens,
        )  # fmt: skip
        causes_all.update({f"{u}::{k}": v for k, v in causes.items()})
        recs = mark_header_row_causes(recs, causes)
        for o, n in zip(old_by_unit[u], recs, strict=True):
            verify_pair(o, n)
        # item-4 outputs derivable from the records are identical to f4b6a12's (MANIFEST)
        tabs = [r for r in recs if r["chunk_type"] == "table"]
        c = item4[u]
        assert len(tabs) == c["table_slices"]
        missing = [
            r["chunk_id"]
            for r in tabs
            if not (r.get("prefix_source") and r.get("prefix") and r["prefix"] in r["text"])
        ]
        assert missing == c["unit_line_missing"], u
        assert c["prefix_integrity"] == []  # the prefix region is byte-identical (verify_pair)
        new_by_unit[u] = recs

    # ---- numbers --------------------------------------------------------------------------
    new_all = [r for u in units for r in new_by_unit[u]]
    n_removed = sum(r.get("fffd_removed", 0) for r in new_all)
    per_unit = {}
    for u in units:
        tabs = [r for r in new_by_unit[u] if r["chunk_type"] == "table"]
        per_unit[u] = {
            "removed": sum(r["fffd_removed"] for r in tabs),
            "kept": sum(r["text"].count("�") for r in tabs),
            "touched_slices": sum(1 for r in tabs if r["fffd_removed"]),
        }
    old_tab = [r for r in old_all if r["chunk_type"] == "table"]
    assert sum(r["text"].count("�") for r in old_tab) == n_removed + sum(
        v["kept"] for v in per_unit.values()
    )
    fn = [
        r
        for r in new_all
        if "fffd_in_number" in (r["question_source_barred"] or {}).get("reasons", [])
    ]
    fn_tables = {(r["unit_id"], t) for r in fn for t in (r["table_refs"] or [r["item"]])}
    tot_tok = sum(r["n_tokens"] for r in new_all)
    tab_tok = sum(r["n_tokens"] for r in new_all if r["chunk_type"] == "table")
    old_tab_tok = sum(r["n_tokens"] for r in old_tab)
    max_tab = max((r["n_tokens"] for r in new_all if r["chunk_type"] == "table"), key=int)
    max_rec = max((r for r in new_all if r["chunk_type"] == "table"), key=lambda r: r["n_tokens"])
    total, _bs, _bu = tally(new_all, pages)
    old_total, _, _ = tally(old_all, pages)
    barred = [r for r in new_all if (r["question_source_barred"] or {}).get("barred")]
    by_reason: dict[str, int] = {}
    for r in barred:
        for x in r["question_source_barred"]["reasons"]:
            by_reason[x] = by_reason.get(x, 0) + 1
    out = {
        "units": len(units),
        "records": len(new_all),
        "chunk_count_share": [
            round(total.table_chunk_share, 6),
            round(old_total.table_chunk_share, 6),
        ],
        "table_slices": [total.table_slices, old_total.table_slices],
        "token_weighted": {
            "table_tokens": [tab_tok, old_tab_tok],
            "all_tokens": [tot_tok, sum(r["n_tokens"] for r in old_all)],
            "share": [
                round(tab_tok / tot_tok, 6),
                round(old_tab_tok / sum(r["n_tokens"] for r in old_all), 6),
            ],
        },
        "max_table_slice_tokens": [max_tab, max(r["n_tokens"] for r in old_tab)],
        "max_table_slice_id": max_rec["chunk_id"],
        "fffd": {
            "removed": n_removed,
            "kept": sum(v["kept"] for v in per_unit.values()),
            "before": sum(r["text"].count("�") for r in old_tab),
            "per_unit": per_unit,
        },
        "fffd_in_number": {
            "slices": len(fn),
            "tables": len(fn_tables),
            "by_unit": sorted({r["unit_id"] for r in fn}),
        },
        "header_row_cause": {
            k: list(causes_all.values()).count(k) for k in sorted(set(causes_all.values()))
        },
        "barred": {"slices": len(barred), "slices_by_reason": by_reason},
    }
    assert out["header_row_cause"] == {"caption_on_slice0": 59, "header_over_max_tokens": 1}, out[
        "header_row_cause"
    ]

    if not a.apply:
        print(json.dumps(out, indent=1))
        print("CHECK ONLY: nothing written")
        return

    # ---- apply ----------------------------------------------------------------------------
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
    for u in units:
        _atomic_write(parsed / f"{u}.chunks.jsonl", dump(new_by_unit[u]))
    parses = [
        UnitParse(u, pages.get(u, 0), len(new_by_unit[u]), 0, 0, 0.0, records=new_by_unit[u])
        for u in units
    ]
    n = write_chunks(chunks_path, parses)
    assert n == 6358
    after = read_records(chunks_path)
    assert [r["chunk_id"] for r in after] == [r["chunk_id"] for r in old_all], "ids/order"
    assert after == new_all
    for name, h in protected.items():
        assert sha256(parsed / name) == h, f"{name} changed"
    out["chunks_jsonl_sha256"] = sha256(chunks_path)
    out["backup_manifest"] = f"{BACKUP}/SHA256_MANIFEST.json"
    print(json.dumps(out, indent=1))
    print("APPLIED")


if __name__ == "__main__":
    main()
