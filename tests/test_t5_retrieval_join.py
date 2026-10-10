# ruff: noqa: E501
"""Retrieval records (D-042 arms, D-033 status 2026-10-09 fields) and the laptop join. Fake
embedder, reranker and store: no GPU."""

import hashlib
import io
import tarfile

import pytest

from ledger.baseline.join import (
    JoinRefused,
    build_contexts,
    read_controls_accepted,
    verify_and_extract,
    write_contexts,
)
from ledger.config import load_config
from ledger.retrieval.index import IndexRefused, Qwen3Embedder, render_lock, text_sha256
from ledger.retrieval.query import (
    arms,
    load_verified_texts,
    read_arm_file,
    retrieve_arm,
    write_arm_file,
)


class _Emb:
    def __init__(self):
        self.calls = []

    def embed_queries(self, queries, instruction):
        self.calls.append(instruction)
        return [[float(i)] for i, _ in enumerate(queries)]


class _Rerank:
    def __init__(self, order):
        self.order = order
        self.calls = []

    def score(self, query, docs, instruction=None):
        self.calls.append(instruction)
        return [self.order.get(d, 0.0) for d in docs]


TEXTS = {f"c{i}": f"text{i}" for i in range(1, 41)}


def _search(vec, k):
    return [(f"c{i}", 1.0 - i / 100) for i in range(1, k + 1) if i <= 40]


def test_arms_carry_the_d042_strings(base_config_path):
    cfg = load_config(base_config_path)
    primary, card = arms(cfg)
    assert (primary.name, card.name) == ("primary", "card")
    assert primary.embed_instruction == primary.rerank_instruction == cfg.reranker.instruction
    assert card.embed_instruction == card.rerank_instruction == cfg.reranker.card_instruction
    assert primary.embed_instruction != card.embed_instruction


def test_retrieve_arm_records(base_config_path):
    cfg = load_config(base_config_path)
    emb = _Emb()
    rr = _Rerank({"text35": 0.9, "text36": 0.1})
    qs = [
        {"question_id": "q1", "question": "a?", "gold_chunk_id": "c3"},
        {"question_id": "q2", "question": "b?", "gold_chunk_id": "c35"},  # outside dense top-30
        {"question_id": "c1", "question": "ctrl?", "gold_chunk_id": None},
    ]
    arm = arms(cfg)[0]
    recs = retrieve_arm(arm, qs, embedder=emb, reranker=rr, search=_search, texts=TEXTS, cfg=cfg)
    assert emb.calls == [arm.embed_instruction]
    assert rr.calls == [arm.rerank_instruction] * 3
    r1, r2, r3 = recs
    assert len(r1["dense"]) == 40 and len(r1["rerank"]) == cfg.retrieval.k_dense
    assert r1["gold_rank_dense"] == 3 and r1["gold_rank_rerank"] is not None
    assert len(r1["top5"]) == 5 and len(r1["top8"]) == 8 and r1["top5"] == r1["top8"][:5]
    assert r2["gold_rank_dense"] == 35 and r2["gold_rank_rerank"] is None  # beyond dense top-30
    assert r3["gold_rank_dense"] is None and r3["gold_chunk_id"] is None


def test_arm_file_roundtrip(tmp_path):
    p = tmp_path / "r.jsonl"
    write_arm_file(
        p, {"record": "header", "arm": "x"}, [{"record": "question", "question_id": "q"}]
    )
    h, recs = read_arm_file(p)
    assert h["arm"] == "x" and recs[0]["question_id"] == "q"


def test_embed_queries_builds_the_card_format():
    e = object.__new__(Qwen3Embedder)
    seen = {}
    e._embed = lambda texts: seen.setdefault("t", list(texts)) or []
    e.embed_queries(["why?"], "Given X")
    assert seen["t"] == ["Instruct: Given X\nQuery:why?"]


def _write_corpus(tmp_path, texts):
    chunks = [{"chunk_id": cid, "text": t} for cid, t in texts.items()]
    lock = render_lock(
        chunks, chunks_sha256="a", manifest_sha256="b", git_commit="c", created_utc="d"
    )
    (tmp_path / "chunks.jsonl").write_text(
        "".join(__import__("json").dumps(c) + "\n" for c in chunks), encoding="utf-8"
    )
    (tmp_path / "lock").write_bytes(lock.encode("utf-8"))
    return tmp_path / "chunks.jsonl", tmp_path / "lock"


def test_texts_are_verified_against_the_lock(tmp_path):
    chunks, lock = _write_corpus(tmp_path, {"c1": "one", "c2": "two"})
    assert load_verified_texts(chunks, lock) == {"c1": "one", "c2": "two"}
    chunks.write_text(chunks.read_text("utf-8").replace("two", "TWO"), encoding="utf-8")
    with pytest.raises(IndexRefused):
        load_verified_texts(chunks, lock)
    assert text_sha256("one")  # helper used by the lock


# ---- join -------------------------------------------------------------------------------------


def _tar(tmp_path, members):
    path = tmp_path / "t.tar.gz"
    with tarfile.open(path, "w:gz") as tf:
        for name in members:
            data = b"{}\n"
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "t.tar.gz.sha256").write_text(f"{sha}  t.tar.gz\n", encoding="utf-8")
    return path


def test_verify_and_extract_ok_and_sha_mismatch(tmp_path):
    path = _tar(tmp_path, ["t5/retrieval_primary.jsonl", "t5/retrieval_card.jsonl"])
    verify_and_extract(path, tmp_path / "t.tar.gz.sha256", tmp_path / "out")
    assert (tmp_path / "out" / "t5" / "retrieval_card.jsonl").exists()
    (tmp_path / "t.tar.gz.sha256").write_text("0" * 64 + "  t.tar.gz\n", encoding="utf-8")
    with pytest.raises(JoinRefused, match="sha256"):
        verify_and_extract(path, tmp_path / "t.tar.gz.sha256", tmp_path / "out2")


def test_unexpected_tar_members_refused(tmp_path):
    path = _tar(tmp_path, ["t5/retrieval_primary.jsonl", "../evil"])
    with pytest.raises(JoinRefused, match="members"):
        verify_and_extract(path, tmp_path / "t.tar.gz.sha256", tmp_path / "o")


def _primary(qs, sha="Q", lock="L"):
    header = {"record": "header", "questions_sha256": sha, "lock_chunks_sha256": lock}
    recs = [{"question_id": q["question_id"], "top5": ["c1", "c2", "c3", "c4", "c5"]} for q in qs]
    return header, recs


def _qs():
    return [
        {"question_id": "q1", "question": "a?", "set": "draft", "gold_chunk_id": "c1"},
        {"question_id": "s1", "question": "s?", "set": "supplement", "gold_chunk_id": "c2"},
        {"question_id": "c1", "question": "x?", "set": "control_candidate", "unanswerable": True},
        {"question_id": "c2", "question": "y?", "set": "control_candidate", "unanswerable": True},
    ]


def test_build_contexts_selects_core_supplement_and_accepted_controls_only():
    qs = _qs()
    ctx = build_contexts(
        qs,
        _primary(qs),
        TEXTS,
        questions_sha256="Q",
        lock_chunks_sha256="L",
        accepted_controls=["c2"],
    )
    assert [c["question_id"] for c in ctx] == ["q1", "s1", "c2"]  # c1 retrieved but not accepted
    assert [c["set"] for c in ctx] == ["draft", "supplement", "control_candidate"]
    assert [c["chunk_id"] for c in ctx[0]["chunks"]] == ["c1", "c2", "c3", "c4", "c5"]
    assert ctx[0]["chunks"][0]["text"] == "text1" and ctx[2]["unanswerable"] is True


def test_build_contexts_refuses_mismatches():
    qs = _qs()
    kw = dict(questions_sha256="Q", lock_chunks_sha256="L", accepted_controls=["c2"])
    with pytest.raises(JoinRefused, match="questions file"):
        build_contexts(qs, _primary(qs), TEXTS, **{**kw, "questions_sha256": "X"})
    with pytest.raises(JoinRefused, match="lock"):
        build_contexts(qs, _primary(qs), TEXTS, **{**kw, "lock_chunks_sha256": "X"})
    with pytest.raises(JoinRefused, match="question ids"):
        build_contexts(
            qs + [{"question_id": "q9", "question": "?", "set": "draft"}], _primary(qs), TEXTS, **kw
        )
    with pytest.raises(JoinRefused, match="lock-verified"):
        build_contexts(qs, _primary(qs), {"c1": "x"}, **kw)


def test_controls_accepted_file_rules(tmp_path):
    qs = _qs()
    path = tmp_path / "controls_accepted.json"
    with pytest.raises(JoinRefused, match="missing"):
        read_controls_accepted(path, qs, 1)
    path.write_text('{"checked_by": "owner", "question_ids": ["c2"]}', encoding="utf-8")
    assert read_controls_accepted(path, qs, 1) == ["c2"]
    for bad, match in (
        ('{"checked_by": "owner", "question_ids": ["c1", "c2"]}', "exactly 1"),
        ('{"checked_by": "owner", "question_ids": ["q1"]}', "not control candidates"),
        ('{"checked_by": " ", "question_ids": ["c2"]}', "checked_by"),
    ):
        path.write_text(bad, encoding="utf-8")
        with pytest.raises(JoinRefused, match=match):
            read_controls_accepted(path, qs, 1)


def test_write_contexts_is_lf(tmp_path):
    p = tmp_path / "c.jsonl"
    write_contexts(p, [{"question_id": "q1"}])
    assert b"\r" not in p.read_bytes()
