"""T5 retrieval on the GPU box (D-043 item 6): both arms of D-042, written to results/t5/.

Needs CUDA, data/chunks.jsonl (synced from S3), the Qdrant file at data/qdrant (T4), and
data/questions_draft.jsonl (from git). No Claude API key is read here. Tracing is optional:
OTEL_EXPORTER_OTLP_ENDPOINT unset or unreachable never stops the run (results are written first).

    uv run python scripts/t5_retrieve.py
    bash scripts/t5_return.sh ledger-vkm-2026        # then: upload the tarball
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from ledger.baseline.runtime import init_tracing_safely, read_questions, shutdown_tracing_safely
from ledger.config import load_config
from ledger.retrieval import store
from ledger.retrieval.index import config_hash, git_commit, lf_sha256, read_lock
from ledger.retrieval.query import arms, load_verified_texts, retrieve_arm, write_arm_file
from ledger.tracing import otel

REPO = Path(__file__).resolve().parent.parent
QUESTIONS = Path("data/questions_draft.jsonl")
OUT_DIR = Path("results/t5")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", metavar="PATH", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(override=args.config)

    import torch

    if not torch.cuda.is_available():
        print("t5_retrieve: CUDA is not available; refusing (GPU stage, D-043 item 6).")
        return 2
    if not QUESTIONS.exists():
        print(f"t5_retrieve: {QUESTIONS} missing; git pull the owner-checked questions first.")
        return 2

    from ledger.retrieval.index import Qwen3Embedder
    from ledger.retrieval.rerank import Qwen3Reranker

    questions = read_questions(QUESTIONS)
    texts = load_verified_texts(cfg.paths.chunks, cfg.paths.chunk_ids_lock)  # lock-checked
    lock_header, _ = read_lock(cfg.paths.chunk_ids_lock)
    init_tracing_safely(cfg)
    code = 0
    try:
        client = store.make_client(cfg, repo=REPO)
        embedder = Qwen3Embedder(cfg)
        reranker = Qwen3Reranker(cfg)

        def search(vec, k):
            return store.dense_search(client, cfg, vec, k)

        with otel.run_span("ledger.t5_retrieve", {"rag.record_type": "t5_retrieval_run"}) as span:
            print(f"trace id: {otel.ids_of(span)[0]}")
            for arm in arms(cfg):
                t0 = time.time()
                records = retrieve_arm(
                    arm,
                    questions,
                    embedder=embedder,
                    reranker=reranker,
                    search=search,
                    texts=texts,
                    cfg=cfg,
                )
                info = embedder.info()
                header = {
                    "record": "header",
                    "arm": arm.name,
                    "git_commit": git_commit(REPO),
                    "config_hash": config_hash(cfg),
                    "lock_chunks_sha256": lock_header.get("chunks_jsonl_sha256 (CRLF->LF)"),
                    "questions_sha256": lf_sha256(QUESTIONS),
                    "n_questions": len(questions),
                    "embed_instruction": arm.embed_instruction,
                    "rerank_instruction": arm.rerank_instruction,
                    "embedder": {
                        "model": cfg.embedding.model,
                        "revision": cfg.embedding.revision,
                    },
                    "reranker": {
                        "model": cfg.reranker.model,
                        "revision": cfg.reranker.revision,
                    },
                    "torch": info["torch"],
                    "transformers": info["transformers"],
                    "gpu": info["gpu"],
                    "k_dense": cfg.retrieval.k_dense,
                    "dense_record_k": cfg.baseline.dense_record_k,
                    "record_k_finals": cfg.baseline.record_k_finals,
                }
                path = OUT_DIR / f"retrieval_{arm.name}.jsonl"
                write_arm_file(path, header, records)  # on disk before tracing is shut down
                print(f"{arm.name}: {len(records)} questions -> {path} ({time.time() - t0:.1f}s)")
        client.close()
    except Exception as exc:  # noqa: BLE001 - report, never traceback-and-lose-state
        print(f"t5_retrieve FAILED: {exc!r}", file=sys.stderr)
        code = 1
    finally:
        shutdown_tracing_safely()
    return code


if __name__ == "__main__":
    sys.exit(main())
