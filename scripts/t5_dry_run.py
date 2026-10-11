"""T5 harness check (D-043 status 2026-10-10, item 5). Sync calls, in ``generator.output_mode``
only, with the exact request body the Batch carries, on RETRIEVED contexts (the primary arm's
top-5 from
results/t5/retrieval_primary.jsonl; texts verified against the lock), for s001 and for each control
candidate that is not in data/controls_accepted.json. It reads nothing from the 25 drafts or the 5
accepted controls. Writes reports/t5_harness_check.md (tracked): per question stop_reason, request
accepted, parse result, abstained, cited IDs among the supplied, and input / output / thinking
tokens; overall PASS only if every call was accepted, ended end_turn and parsed.

Runs after the controls choice and before the Batch. Refuses if data/controls_accepted.json, the
retrieval output or generator.output_mode is missing. The report is written before tracing is shut
down, so an unreachable OTLP endpoint loses nothing. Needs ANTHROPIC_API_KEY (env only).

    uv run python scripts/t5_dry_run.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ledger.baseline import harness
from ledger.baseline.join import (
    JoinRefused,
    harness_contexts,
    read_controls_accepted,
    read_primary,
)
from ledger.baseline.request import OutputModeUnset, require_output_mode
from ledger.baseline.runtime import init_tracing_safely, read_questions, shutdown_tracing_safely
from ledger.config import load_config
from ledger.retrieval.index import IndexRefused, lf_sha256, read_lock
from ledger.retrieval.query import load_verified_texts
from ledger.tracing import otel

QUESTIONS = Path("data/questions_draft.jsonl")
CONTROLS = Path("data/controls_accepted.json")
REPORT = Path("reports/t5_harness_check.md")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", metavar="PATH", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(override=args.config)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("t5_dry_run: ANTHROPIC_API_KEY is not set (env only)", file=sys.stderr)
        return 2
    try:
        mode = require_output_mode(cfg.generator)
        questions = read_questions(QUESTIONS)
        accepted = read_controls_accepted(CONTROLS, questions, cfg.baseline.n_controls)
        texts = load_verified_texts(cfg.paths.chunks, cfg.paths.chunk_ids_lock)
        lock_header, _ = read_lock(cfg.paths.chunk_ids_lock)
        ctxs = harness_contexts(
            questions,
            read_primary(cfg.paths.results_dir),
            texts,
            questions_sha256=lf_sha256(QUESTIONS),
            lock_chunks_sha256=lock_header["chunks_jsonl_sha256 (CRLF->LF)"],
            accepted_controls=accepted,
        )
    except (JoinRefused, IndexRefused, OutputModeUnset, FileNotFoundError) as exc:
        print(f"t5_dry_run: refused: {exc}", file=sys.stderr)
        return 2

    import anthropic

    client = anthropic.Anthropic()
    init_tracing_safely(cfg)
    rows: list[dict] = []
    try:
        with otel.run_span("ledger.t5_harness_check", {"rag.record_type": "t5_harness_check"}):
            for ctx in ctxs:
                row = harness.check_question(client, cfg.generator, ctx, mode)
                rows.append(row)
                print(
                    f"{row['question_id']}: accepted={row['accepted']} "
                    f"stop={row['stop_reason']} parse={row['parse']}"
                )
        meta = {
            "model": cfg.generator.model,
            "thinking / effort": f"{cfg.generator.thinking} / {cfg.generator.effort}",
            "questions sha256 (LF)": lf_sha256(QUESTIONS),
            "controls_accepted.json sha256 (LF)": lf_sha256(CONTROLS),
            "questions": ", ".join(c["question_id"] for c in ctxs),
        }
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(harness.render(meta, rows, mode), encoding="utf-8", newline="\n")
        print(f"wrote {REPORT}: {'PASS' if harness.overall_pass(rows) else 'FAIL'}")
    finally:
        shutdown_tracing_safely()
    return 0 if harness.overall_pass(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
