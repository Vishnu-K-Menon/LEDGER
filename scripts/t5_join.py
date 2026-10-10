"""T5 laptop join (D-043 item 6). Verifies the GPU tarball's sha256, extracts it to results/,
joins chunk texts from data/chunks.jsonl (every text checked against the lock) and writes
results/t5/contexts.jsonl, the generation input. Refuses on any mismatch. No API call.

    aws s3 cp s3://ledger-vkm-2026/t5/t5-retrieval.tar.gz .      (and .sha256)
    uv run python scripts/t5_join.py --tarball t5-retrieval.tar.gz
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ledger.baseline.join import (
    JoinRefused,
    build_contexts,
    read_controls_accepted,
    read_primary,
    verify_and_extract,
    write_contexts,
)
from ledger.baseline.runtime import read_questions
from ledger.config import load_config
from ledger.retrieval.index import IndexRefused, lf_sha256, read_lock
from ledger.retrieval.query import load_verified_texts

QUESTIONS = Path("data/questions_draft.jsonl")
CONTROLS = Path("data/controls_accepted.json")  # owner-edited: the 5 accepted controls


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--tarball", required=True, type=Path)
    ap.add_argument("--config", metavar="PATH", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(override=args.config)
    try:
        sha_file = args.tarball.with_name(args.tarball.name + ".sha256")
        verify_and_extract(args.tarball, sha_file, cfg.paths.results_dir)
        if not CONTROLS.exists():
            print(
                "tarball verified and extracted to results/t5/. Next: uv run python "
                "scripts/t5_report.py, read the controls' top-5 in reports/t5_a6.md, write "
                f"{CONTROLS} (5 accepted control ids), then rerun this command."
            )
            return 3
        texts = load_verified_texts(cfg.paths.chunks, cfg.paths.chunk_ids_lock)
        lock_header, _ = read_lock(cfg.paths.chunk_ids_lock)
        questions = read_questions(QUESTIONS)
        accepted = read_controls_accepted(CONTROLS, questions, cfg.baseline.n_controls)
        contexts = build_contexts(
            questions,
            read_primary(cfg.paths.results_dir),
            texts,
            questions_sha256=lf_sha256(QUESTIONS),
            lock_chunks_sha256=lock_header["chunks_jsonl_sha256 (CRLF->LF)"],
            accepted_controls=accepted,
        )
    except (JoinRefused, IndexRefused) as exc:
        print(f"t5_join REFUSED: {exc}", file=sys.stderr)
        return 2
    out = cfg.paths.results_dir / "t5" / "contexts.jsonl"
    write_contexts(out, contexts)
    print(f"{len(contexts)} contexts -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
