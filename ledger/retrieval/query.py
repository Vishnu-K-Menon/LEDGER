"""T5 retrieval for the draft questions: dense top-``dense_record_k`` -> rerank the dense
top-``k_dense`` -> store top-5 and top-8, for two arms (D-042):

* ``primary`` - the D-042 domain string on both stages (``embedding.query_instruction``,
  ``reranker.instruction``);
* ``card``    - the model cards' example string on both stages (``reranker.card_instruction``);
  descriptive only, it decides nothing.

Both strings live in config (D-021), so an invocation runs both arms and no flag selects one.
Embedder, reranker and the dense search are injected: tests use fakes, the GPU script the real
ones. Texts are read from ``data/chunks.jsonl`` and verified against the lock before any use; the
index payload holds ids only.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from openinference.semconv.trace import RerankerAttributes

from ledger.config import Config
from ledger.retrieval.index import IndexRefused, compare_to_lock, read_chunks, read_lock
from ledger.tracing import otel


@dataclass(frozen=True)
class Arm:
    name: str
    embed_instruction: str
    rerank_instruction: str


def arms(cfg: Config) -> list[Arm]:
    return [
        Arm("primary", cfg.embedding.query_instruction, cfg.reranker.instruction),
        Arm("card", cfg.reranker.card_instruction, cfg.reranker.card_instruction),
    ]


class QueryEmbedder(Protocol):
    def embed_queries(self, queries: Sequence[str], instruction: str) -> list[list[float]]: ...


class Scorer(Protocol):
    def score(
        self, query: str, docs: Sequence[str], instruction: str | None = None
    ) -> list[Any]: ...


Search = Callable[[list[float], int], list[tuple[str, float]]]


def load_verified_texts(chunks_path: Path, lock_path: Path) -> dict[str, str]:
    """``chunk_id -> text``, only if every id and text hash equals the lock (all-or-nothing)."""
    chunks = read_chunks(chunks_path)
    _, entries = read_lock(lock_path)
    diffs = compare_to_lock(chunks, entries)
    if diffs:
        raise IndexRefused(f"chunks.jsonl differs from the lock ({len(diffs)}): {diffs[:5]}")
    return {c["chunk_id"]: c["text"] for c in chunks}


def _rank(ids: Sequence[str], target: str | None) -> int | None:
    if target is None:
        return None
    try:
        return list(ids).index(target) + 1
    except ValueError:
        return None


def retrieve_arm(
    arm: Arm,
    questions: Sequence[Mapping[str, Any]],
    *,
    embedder: QueryEmbedder,
    reranker: Scorer,
    search: Search,
    texts: Mapping[str, str],
    cfg: Config,
) -> list[dict[str, Any]]:
    k_dense = cfg.retrieval.k_dense
    k_record = max(cfg.baseline.dense_record_k, k_dense)
    finals = sorted(cfg.baseline.record_k_finals)
    vectors = embedder.embed_queries([q["question"] for q in questions], arm.embed_instruction)
    out = []
    for q, vec in zip(questions, vectors, strict=True):
        gold = q.get("gold_chunk_id")  # None for controls
        with otel.retriever_span(q["question"]) as rspan:
            dense = search(vec, k_record)
            otel.set_retrieved_documents(
                rspan, [{"id": cid, "score": s} for cid, s in dense[:k_dense]]
            )
        dense_ids = [cid for cid, _ in dense]
        pool = dense[:k_dense]
        with otel.reranker_span(
            q["question"], top_k=max(finals), model_name=cfg.reranker.model
        ) as kspan:
            scores = reranker.score(
                q["question"], [texts[cid] for cid, _ in pool], arm.rerank_instruction
            )
            ranked = sorted(
                ((cid, float(s)) for (cid, _), s in zip(pool, scores, strict=True)),
                key=lambda x: (-x[1], x[0]),
            )
            otel.set_retrieved_documents(
                kspan,
                [{"id": cid, "score": s} for cid, s in ranked[: max(finals)]],
                prefix=RerankerAttributes.RERANKER_OUTPUT_DOCUMENTS,
            )
        rerank_ids = [cid for cid, _ in ranked]
        rec: dict[str, Any] = {
            "record": "question",
            "arm": arm.name,
            "question_id": q["question_id"],
            "gold_chunk_id": gold,
            "dense": [[cid, s] for cid, s in dense],
            "rerank": [[cid, s] for cid, s in ranked],
            "gold_rank_dense": _rank(dense_ids, gold),
            "gold_rank_rerank": _rank(rerank_ids, gold),
        }
        for k in finals:
            rec[f"top{k}"] = rerank_ids[:k]
        out.append(rec)
    return out


def write_arm_file(
    path: Path, header: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for rec in (header, *records):
            fh.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")


def read_arm_file(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    lines = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines or lines[0].get("record") != "header":
        raise ValueError(f"{path}: first record is not a header")
    return lines[0], lines[1:]
