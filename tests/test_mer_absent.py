"""D-040: MER is EXCLUDED from v1 - zero MER rows in the active manifest, ``chunks.jsonl``,
``chunk_ids.lock``, the Qdrant payload and the BM25 index. Keyed on PROVENANCE (manifest
``parent_series`` / ``status``, chunk ``unit_id`` / ``parent_series``, chunk-ID prefix), never on
text: STEO and AEO cite "Monthly Energy Review".

The manifest is tracked, so its checks run in CI; the data artifacts are gitignored and each check
skips when its artifact is absent (D-028: CI is pytest + ruff).

``chunks.jsonl`` before the one re-chunk (D-037) is the old pilot chunking, which still holds the
MER units: until ``chunk_ids.lock`` exists the chunk check is an expected failure with that reason;
from the lock on (the index is frozen, D24) it is a hard assertion."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ledger.config import load_config
from ledger.ingest.manifest import active_rows, read_manifest
from ledger.ingest.parse import eligible_rows

REPO = Path(__file__).resolve().parents[1]
CFG = load_config(REPO / "configs" / "base.yaml")
SERIES = set(CFG.corpus.excluded_parent_series)


def _rows():
    return read_manifest(REPO / CFG.paths.manifest)[1]


def _excluded_ids() -> set[str]:
    return {r.unit_id for r in _rows() if r.parent_series in SERIES}


def _is_mer(unit_id: str | None, parent_series: str | None = None) -> bool:
    return parent_series in SERIES or unit_id in _excluded_ids()


def test_mer_is_the_configured_exclusion() -> None:
    assert SERIES == {"Monthly Energy Review"}


def test_mer_absent_from_active_manifest() -> None:
    rows = _rows()
    assert _excluded_ids(), "no MER rows in the manifest: D-040 keeps the rows (never deleted)"
    assert all(r.status == "EXCLUDED" for r in rows if r.parent_series in SERIES)
    assert not [r.unit_id for r in active_rows(rows) if _is_mer(r.unit_id, r.parent_series)]


def test_excluded_rows_are_never_parsed() -> None:
    parseable, skipped = eligible_rows(active_rows(_rows()))
    assert not [r.unit_id for r in parseable if _is_mer(r.unit_id, r.parent_series)]
    assert not [u for u in skipped if _is_mer(u)]


def test_mer_absent_from_parsed_dir() -> None:
    parsed = REPO / CFG.paths.parsed_dir
    if not parsed.exists():
        pytest.skip("data/parsed absent (local data, gitignored)")
    left = sorted(p.name for p in parsed.iterdir() if p.name.split(".")[0] in _excluded_ids())
    assert not left, f"MER parse files still in {CFG.paths.parsed_dir}: {left}"


def test_mer_absent_from_chunks() -> None:
    path = REPO / CFG.paths.chunks
    if not path.exists():
        pytest.skip("chunks.jsonl absent (local data, gitignored)")
    hits = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if _is_mer(r.get("unit_id"), r.get("parent_series")):
                hits.add(r.get("unit_id"))
    if hits and not (REPO / CFG.paths.chunk_ids_lock).exists():
        pytest.xfail(
            f"pre-re-chunk chunks.jsonl still holds {len(hits)} MER units; D-040 removes them at "
            "the one re-chunk (D-037), before chunk IDs freeze - a hard failure from the lock on"
        )
    assert not hits, f"MER units in {CFG.paths.chunks}: {sorted(hits)}"


def test_mer_absent_from_chunk_ids_lock() -> None:
    path = REPO / CFG.paths.chunk_ids_lock
    if not path.exists():
        pytest.skip("chunk_ids.lock not written yet (T4)")
    text = path.read_text(encoding="utf-8")
    hits = sorted(u for u in _excluded_ids() if f"{u}::" in text)
    assert not hits, f"MER chunk IDs in {CFG.paths.chunk_ids_lock}: {hits}"


def test_mer_absent_from_qdrant_payload() -> None:
    if not (REPO / CFG.paths.qdrant_path).exists():
        pytest.skip("Qdrant store not built yet (T4)")
    from ledger.retrieval.store import make_client  # D-002: the one QdrantClient constructor

    client = make_client(CFG)
    hits, offset = set(), None
    while True:
        points, offset = client.scroll(
            CFG.vector_store.collection, with_payload=True, limit=1000, offset=offset
        )
        for pt in points:
            pl = pt.payload or {}
            uid = pl.get("unit_id") or str(pl.get("chunk_id", "")).split("::")[0]
            if _is_mer(uid, pl.get("parent_series")):
                hits.add(uid)
        if offset is None:
            break
    assert not hits, f"MER units in the Qdrant payload: {sorted(hits)}"


def test_mer_absent_from_bm25_index() -> None:
    pytest.skip("no BM25 index or config path exists yet (built with retrieval); D-040 lists it")
