"""Laptop join (D-043 item 6): verify the GPU tarball, join chunk texts to the retrieval records,
refuse on any mismatch. The generation context is the primary arm's top-5 (D17), each text checked
against the lock before use."""

from __future__ import annotations

import hashlib
import json
import tarfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ledger.retrieval.query import read_arm_file

EXPECTED_MEMBERS = {"t5/retrieval_primary.jsonl", "t5/retrieval_card.jsonl"}


class JoinRefused(RuntimeError):
    pass


def verify_and_extract(tarball: Path, sha_file: Path, dest: Path) -> None:
    want = sha_file.read_text(encoding="utf-8").split()[0]
    got = hashlib.sha256(tarball.read_bytes()).hexdigest()
    if got != want:
        raise JoinRefused(f"tarball sha256 {got} != recorded {want}")
    with tarfile.open(tarball, "r:gz") as tf:
        names = {m.name for m in tf.getmembers()}
        if names != EXPECTED_MEMBERS:
            raise JoinRefused(f"unexpected tarball members: {sorted(names ^ EXPECTED_MEMBERS)}")
        tf.extractall(dest, filter="data")


CORE_SETS = ("draft", "supplement")


def read_controls_accepted(path: Path, questions: Sequence[Mapping[str, Any]], n: int) -> list[str]:
    """``data/controls_accepted.json``: the owner's choice of ``n`` control candidates after reading
    their top-5 (D-043 item 2). ``{"checked_by": "<name>", "question_ids": [...]}``."""
    if not path.exists():
        raise JoinRefused(
            f"{path} is missing: choose {n} of the control candidates after reading their top-5 "
            "(reports/t5_a6.md lists them), then write that file"
        )
    obj = json.loads(path.read_text(encoding="utf-8"))
    ids = obj.get("question_ids", [])
    candidates = {q["question_id"] for q in questions if q.get("set") == "control_candidate"}
    if len(ids) != n or len(set(ids)) != n:
        raise JoinRefused(f"{path}: need exactly {n} distinct question_ids, got {ids}")
    if not set(ids) <= candidates:
        raise JoinRefused(
            f"{path}: not control candidates of the questions file: {sorted(set(ids) - candidates)}"
        )
    if not str(obj.get("checked_by", "")).strip():
        raise JoinRefused(f"{path}: checked_by is empty")
    return list(ids)


def select_questions(
    questions: Sequence[Mapping[str, Any]], accepted_controls: Sequence[str]
) -> list[Mapping[str, Any]]:
    """The 25 drafts, the supplement items and the accepted controls; unaccepted control
    candidates are retrieved but never generated or reported."""
    keep = set(accepted_controls)
    return [
        q
        for q in questions
        if q.get("set") in CORE_SETS
        or (q.get("set") == "control_candidate" and q["question_id"] in keep)
    ]


def build_contexts(
    questions: Sequence[Mapping[str, Any]],
    primary: tuple[Mapping[str, Any], Sequence[Mapping[str, Any]]],
    texts: Mapping[str, str],
    *,
    questions_sha256: str,
    lock_chunks_sha256: str,
    accepted_controls: Sequence[str],
    k: int = 5,
) -> list[dict[str, Any]]:
    header, records = primary
    if header.get("questions_sha256") != questions_sha256:
        raise JoinRefused("retrieval was run against a different questions file")
    if header.get("lock_chunks_sha256") != lock_chunks_sha256:
        raise JoinRefused("retrieval was run against a different chunks.jsonl (lock hash differs)")
    by_id = {r["question_id"]: r for r in records}
    if set(by_id) != {q["question_id"] for q in questions} or len(by_id) != len(questions):
        raise JoinRefused("question ids in the retrieval file differ from the questions file")
    out = []
    for q in select_questions(questions, accepted_controls):
        rec = by_id[q["question_id"]]
        top = rec[f"top{k}"]
        missing = [cid for cid in top if cid not in texts]
        if missing:
            raise JoinRefused(f"{q['question_id']}: ids not in the lock-verified corpus: {missing}")
        out.append(
            {
                "question_id": q["question_id"],
                "question": q["question"],
                "set": q.get("set", "draft"),
                "gold_chunk_id": q.get("gold_chunk_id"),
                "unanswerable": bool(q.get("unanswerable", False)),
                "chunks": [{"chunk_id": cid, "text": texts[cid]} for cid in top],
            }
        )
    return out


def write_contexts(path: Path, contexts: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for c in contexts:
            fh.write(json.dumps(c, sort_keys=True, ensure_ascii=False) + "\n")


def read_contexts(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def read_primary(results_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return read_arm_file(results_dir / "t5" / "retrieval_primary.jsonl")
