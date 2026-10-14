"""T6 decomposition Batch (D-044 item 2): submit, then (re-invoke later) collect.

Input: run 1 of the T5 Batch of record (``decomposition.input_cell``), the non-abstaining draft
answers only. Refuses unless the prompt file's SHA-256 equals ``decomposition.prompt_sha256``.
Needs ANTHROPIC_API_KEY (env only). Safe to re-run: the job ledger never resubmits a recorded
batch. When every request has been collected, writes ``data/t6_claims.jsonl`` (every returned
claim, kept or dropped by a guard) and ``reports/t6_decompose.md``.

    uv run python scripts/t6_decompose.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ledger.baseline.batch import AmbiguousBatch, AnthropicBatchClient
from ledger.baseline.runtime import init_tracing_safely, read_questions, shutdown_tracing_safely
from ledger.claims import decompose as D
from ledger.config import load_config
from ledger.tracing import otel


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", metavar="PATH", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(override=args.config)
    try:
        prompt = D.load_prompt(cfg)
    except D.PromptNotFrozen as exc:
        print(f"t6_decompose REFUSED: {exc}", file=sys.stderr)
        return 2
    if not cfg.generator.use_batch:
        print("t6_decompose: generator.use_batch is false; Batch only (D28)", file=sys.stderr)
        return 2
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("t6_decompose: ANTHROPIC_API_KEY is not set (env only)", file=sys.stderr)
        return 2
    claims_path = Path(cfg.pilot.paths.claims)
    if claims_path.exists():
        print(f"t6_decompose: {claims_path} exists; the claims are written once", file=sys.stderr)
        return 2
    if not D.input_path(cfg).exists():
        print(f"t6_decompose: {D.input_path(cfg)} missing (run 1, laptop only)", file=sys.stderr)
        return 2

    inputs = D.read_answers(cfg, read_questions(Path(cfg.paths.questions_draft)))
    print(
        f"input: {len(inputs.items)} non-abstaining answers; abstained {inputs.abstained}; "
        f"unusable {inputs.unusable}"
    )
    print(f"prompt sha256: {prompt.sha256}")

    import anthropic

    client = AnthropicBatchClient(
        anthropic.Anthropic(), Path(cfg.paths.results_dir) / "t6_decompose_sidecar.jsonl"
    )
    init_tracing_safely(cfg)
    try:
        with otel.run_span("ledger.t6_decompose", {"rag.record_type": "t6_decompose_run"}):
            summary = D.submit_or_collect(
                cfg,
                prompt,
                inputs.items,
                client,
                ledger_path=Path(cfg.paths.results_dir) / "t6_jobs.jsonl",
            )
            print(summary)
            got = D.collect(cfg, inputs.items)
            traced = D.trace_decompositions(
                cfg, inputs.items, got, Path(cfg.paths.results_dir) / "t6_decompose_traced.txt"
            )
            print(f"spans emitted for {traced} collected decompositions")
    except AmbiguousBatch as exc:
        print(f"t6_decompose STOPPED: {exc}", file=sys.stderr)
        return 3
    finally:
        shutdown_tracing_safely()

    if summary.still_in_flight or set(got.failed.values()) & {"no result"}:
        print("not every request is collected yet; re-run later")
        return 0
    manifest = D.claims_manifest(cfg, prompt, inputs.items, got)
    D.write_claims(claims_path, manifest, got.records)
    report = Path(cfg.pilot.paths.decompose_report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_bytes(D.render_report(manifest, inputs.items, got).encode("utf-8"))
    print(
        f"wrote {claims_path} ({manifest['claims_kept']} kept of {manifest['claims_returned']}; "
        f"failed answers: {list(got.failed) or 'none'}) and {report}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
