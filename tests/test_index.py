"""T4: ``ledger index`` input checks, the lock, and the Qdrant build — offline, on a tmp_path
repo with a fake embedder. Never touches the real data/ and never calls ``main(["index"])``."""

import hashlib
import json
import uuid
from pathlib import Path

import pytest
from qdrant_client import models

from ledger.config import Config, load_config
from ledger.ingest.manifest import ManifestHeader, ManifestRow, read_manifest, write_manifest
from ledger.retrieval import index as ix
from ledger.retrieval import store

DIM = 8


class FakeEmbedder:
    def __init__(self):
        self.calls = 0

    def embed_documents(self, texts):
        self.calls += 1
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()[:DIM]
            v = [b + 1.0 for b in h]
            n = sum(x * x for x in v) ** 0.5
            out.append([x / n for x in v])
        return out

    def info(self):
        return {
            "model": "fake",
            "revision": "r0",
            "precision": "bf16",
            "torch": "t",
            "transformers": "x",
            "gpu": "none",
            "max_tokens_embedded": 3,
            "truncations": 0,
        }


def _row(unit_id: str, *, status="ACTIVE", notes=None) -> ManifestRow:
    return ManifestRow(
        unit_id=unit_id,
        source="eia",
        parent_series="S",
        unit_kind="report",
        fetch_method="direct",
        title=unit_id,
        date_issued=None,
        url=None,
        snapshot_date="2026-10-07",
        notes=notes or [],
        status=status,
    )


def _chunk(unit: str, i: int, text: str | None = None, ctype: str = "prose") -> dict:
    return {
        "chunk_id": f"{unit}::p{i}::txt-{i}::s0",
        "unit_id": unit,
        "source": "eia",
        "parent_series": "S",
        "page": i,
        "chunk_type": ctype,
        "text": text if text is not None else f"text of {unit} chunk {i}",
        "n_tokens": 5,
        "parse_path": None,
        "question_source_barred": (
            {"barred": True, "reasons": ["no_own_title"]} if ctype == "table" else None
        ),
    }


def _write_repo(root: Path, chunks: list[dict], rows: list[ManifestRow]) -> None:
    (root / "data").mkdir(parents=True, exist_ok=True)
    with (root / "data/chunks.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for c in chunks:
            fh.write(json.dumps(c) + "\n")
    hdr = ManifestHeader(
        selection_seed=1, snapshot_date="2026-10-07", frames={}, pilot_composition={}
    )
    write_manifest(root / "data/manifest.jsonl", hdr, rows)


def _rows() -> list[ManifestRow]:
    return [
        _row("A"),
        _row("B"),
        _row("C"),
        _row("D"),
        _row("U", notes=["fetch: UNFETCHABLE (no PDF)"]),  # active, never fetched, no chunks
        _row("X", status="EXCLUDED"),
    ]


@pytest.fixture
def cfg() -> Config:
    c = load_config()
    c.embedding.dim = DIM
    return c


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    chunks = [
        _chunk(u, i, ctype="table" if (u == "B" and i % 2) else "prose")
        for u in ("A", "B", "C", "D")
        for i in range(5)
    ]
    _write_repo(tmp_path, chunks, _rows())
    return tmp_path


def _lock(repo: Path) -> Path:
    return repo / "data/chunk_ids.lock"


def test_build_writes_collection_lock_and_meta(cfg, repo):
    meta = ix.build_index(cfg, repo, FakeEmbedder())
    assert meta["point_count"] == 20
    assert meta["lock_written"] is True
    header, entries = ix.read_lock(_lock(repo))
    assert header["records"] == "20" and len(entries) == 20
    assert b"\r" not in _lock(repo).read_bytes()
    saved = json.loads((repo / "data/index_meta.json").read_text(encoding="utf-8"))
    assert saved["embedding"]["dim"] == DIM and saved["point_id_scheme"] == store.POINT_ID_SCHEME
    assert saved["config_hash"] and saved["seconds"] >= 0


def test_second_run_rebuilds_and_leaves_lock_byte_identical(cfg, repo):
    ix.build_index(cfg, repo, FakeEmbedder())
    before = _lock(repo).read_bytes()
    emb = FakeEmbedder()
    meta = ix.build_index(cfg, repo, emb)
    assert emb.calls == 1 and meta["lock_written"] is False
    assert _lock(repo).read_bytes() == before


def test_changed_text_refuses_and_lists_first_ten(cfg, repo):
    ix.build_index(cfg, repo, FakeEmbedder())
    before = _lock(repo).read_bytes()
    chunks = ix.read_chunks(repo / "data/chunks.jsonl")
    for c in chunks[:12]:
        c["text"] += " edited"
    _write_repo(repo, chunks, _rows())
    with pytest.raises(ix.IndexRefused) as e:
        ix.build_index(cfg, repo, FakeEmbedder())
    assert "12 differences" in str(e.value) and str(e.value).count("position ") == 10
    assert _lock(repo).read_bytes() == before


def test_rerun_after_failure_without_lock_succeeds(cfg, repo):
    ix.build_index(cfg, repo, FakeEmbedder())
    _lock(repo).unlink()  # a run that died after the collection was built, before the lock
    meta = ix.build_index(cfg, repo, FakeEmbedder())
    assert meta["lock_written"] is True and meta["point_count"] == 20
    assert _lock(repo).exists()


def test_failure_before_lock_leaves_no_lock(cfg, repo):
    class Boom(FakeEmbedder):
        def embed_documents(self, texts):
            raise RuntimeError("gpu fell over")

    with pytest.raises(RuntimeError):
        ix.build_index(cfg, repo, Boom())
    assert not _lock(repo).exists() and not (repo / "data/index_meta.json").exists()


def test_unfetchable_row_does_not_refuse(repo):
    _, rows = read_manifest(repo / "data/manifest.jsonl")
    assert ix.check_inputs(ix.read_chunks(repo / "data/chunks.jsonl"), rows).ok


def test_active_row_without_chunks_refuses(cfg, repo):
    chunks = ix.read_chunks(repo / "data/chunks.jsonl")
    rows = [_row(u) for u in "ABCD"] + [_row("E")]  # E: active, not UNFETCHABLE, no chunks
    rep = ix.check_inputs(chunks, rows)
    assert rep.active_without_chunks == ["E"] and not rep.ok
    _write_repo(repo, chunks, rows)
    with pytest.raises(ix.IndexRefused, match="active_row_without_chunks: 1"):
        ix.build_index(cfg, repo, FakeEmbedder())
    assert not _lock(repo).exists()


def test_chunk_from_excluded_unit_refuses(cfg, repo):
    chunks = ix.read_chunks(repo / "data/chunks.jsonl") + [_chunk("X", 0)]
    rep = ix.check_inputs(chunks, _rows())
    assert rep.unit_not_active == ["X::p0::txt-0::s0"]
    _write_repo(repo, chunks, _rows())
    with pytest.raises(ix.IndexRefused, match="chunk_unit_not_active: 1"):
        ix.build_index(cfg, repo, FakeEmbedder())


def test_duplicate_prefix_and_backspace_refuse():
    rows = [_row("A")]
    a = _chunk("A", 0)
    bad_prefix = {**_chunk("A", 1), "chunk_id": "Z::p1::txt-1::s0"}
    bs = _chunk("A", 2, text="x\x08y")
    rep = ix.check_inputs([a, a, bad_prefix, bs], rows)
    assert rep.duplicate_chunk_id == [a["chunk_id"]]
    assert rep.bad_id_prefix == ["Z::p1::txt-1::s0"]
    assert rep.backspace_in_text == [bs["chunk_id"]]


def test_point_retrievable_by_uuid5_and_ids_not_positional(cfg, repo):
    ix.build_index(cfg, repo, FakeEmbedder())
    cid = "C::p3::txt-3::s0"
    assert store.point_id(cid) == str(uuid.uuid5(store.POINT_ID_NAMESPACE, cid))
    client = store.make_client(cfg, repo=repo)
    try:
        got = client.retrieve(cfg.vector_store.collection, [store.point_id(cid)])
        assert len(got) == 1 and got[0].payload["chunk_id"] == cid
        assert got[0].payload["unit_id"] == "C" and "doc_id" not in got[0].payload
    finally:
        client.close()


def _match(key: str, value) -> models.Filter:
    cond = models.FieldCondition(key=key, match=models.MatchValue(value=value))
    return models.Filter(must=[cond])


def test_filters_on_unit_id_and_is_table_work(cfg, repo):
    ix.build_index(cfg, repo, FakeEmbedder())
    client = store.make_client(cfg, repo=repo)
    name = cfg.vector_store.collection

    def ids(flt):
        pts, _ = client.scroll(name, scroll_filter=flt, limit=100, with_payload=True)
        return {p.payload["chunk_id"] for p in pts}

    try:
        assert ids(_match("unit_id", "A")) == {f"A::p{i}::txt-{i}::s0" for i in range(5)}
        assert ids(_match("is_table", True)) == {"B::p1::txt-1::s0", "B::p3::txt-3::s0"}
        hit = client.query_points(
            name,
            query=FakeEmbedder().embed_documents(["text of A chunk 2"])[0],
            using=store.DENSE_VECTOR,
            limit=1,
        ).points[0]
        assert hit.payload["chunk_id"] == "A::p2::txt-2::s0"
        # the BM25 vector is declared and left empty
        assert store.SPARSE_VECTOR in client.get_collection(name).config.params.sparse_vectors
    finally:
        client.close()


def test_payload_carries_barred_reasons():
    p = store.payload_of(_chunk("B", 1, ctype="table"))
    assert p["is_table"] is True and p["question_source_barred"] is True
    assert p["question_source_barred_reasons"] == ["no_own_title"]
    q = store.payload_of(_chunk("B", 2))
    assert q["is_table"] is False and q["question_source_barred"] is False


def test_manifest_hash_is_crlf_invariant(tmp_path):
    lf, crlf = tmp_path / "lf.jsonl", tmp_path / "crlf.jsonl"
    lf.write_bytes(b'{"a": 1}\n{"b": 2}\n')
    crlf.write_bytes(b'{"a": 1}\r\n{"b": 2}\r\n')
    assert ix.lf_sha256(lf) == ix.lf_sha256(crlf)


def test_lock_has_no_excluded_unit_ids_and_roundtrips(cfg, repo):
    ix.build_index(cfg, repo, FakeEmbedder())
    assert "X::" not in _lock(repo).read_text(encoding="utf-8")  # what test_mer_absent checks
    _, entries = ix.read_lock(_lock(repo))
    assert ix.compare_to_lock(ix.read_chunks(repo / "data/chunks.jsonl"), entries) == []


def test_run_index_refuses_without_cuda_before_touching_data(cfg, tmp_path, monkeypatch, capsys):
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    assert ix.run_index(cfg, tmp_path) == 2
    assert "CUDA is not available" in capsys.readouterr().out
    assert not (tmp_path / "data").exists()


def test_make_client_local_only(cfg, tmp_path):
    cfg2 = cfg.model_copy(deep=True)
    cfg2.vector_store.mode = "docker"
    with pytest.raises(NotImplementedError):
        store.make_client(cfg2, repo=tmp_path)


def _verify_lock_main():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "verify_lock", Path(__file__).resolve().parents[1] / "scripts/verify_lock.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.main


def test_verify_lock_script_passes_then_detects_tampering(cfg, repo, capsys):
    ix.build_index(cfg, repo, FakeEmbedder())
    args = [
        "--lock", str(_lock(repo)),
        "--chunks", str(repo / "data/chunks.jsonl"),
        "--manifest", str(repo / "data/manifest.jsonl"),
    ]  # fmt: skip
    main = _verify_lock_main()
    assert main(args) == 0
    # a CRLF checkout of the manifest still verifies (hashes are LF-normalised)
    mf = repo / "data/manifest.jsonl"
    mf.write_bytes(mf.read_bytes().replace(b"\n", b"\r\n"))
    assert main(args) == 0
    chunks = ix.read_chunks(repo / "data/chunks.jsonl")
    chunks[3]["text"] += "!"
    _write_repo(repo, chunks, _rows())
    assert main(args) == 1
    assert "LOCK MISMATCH" in capsys.readouterr().out


def test_loadtest_helpers(tmp_path, cfg):
    from ledger.retrieval import loadtest as lt

    p = tmp_path / "c.jsonl"
    p.write_text(
        "\n".join(json.dumps({**_chunk("A", i), "n_tokens": n}) for i, n in enumerate([5, 90, 40])),
        encoding="utf-8",
    )
    top = lt.corpus_max_chunks(p, 2)
    assert [c["n_tokens"] for c in top] == [90, 40]
    assert "Claim: c1" in lt.verify_prompt(top, "c1")
    res = [
        lt.CandidateResult("a/b", "r" * 40, status="NOT LOADED", detail="boom"),
        lt.CandidateResult("c/d", "s" * 40, status="PASS", smi_peak_verify_gib=30.0),
    ]
    md = lt.render_report(cfg, res, {"gpu": "x"}, {"embedder": "y"})
    assert "not a validated MiniCheck or Granite Guardian score" in md
    assert "PASS: ['c/d']" in md and "NOT LOADED" in md and "44.7" in md
