"""T5 baseline Batch (D-043 item 3): submit, then (re-invoke later) collect, the one Batch of 90.

Refuses while ``generator.output_mode`` is empty - the owner rules on it first (D-043 item 5).
Needs ANTHROPIC_API_KEY (env only) and results/t5/contexts.jsonl (scripts/t5_join.py). Safe to
re-run at any time: the job ledger (results/t5_jobs.jsonl) never resubmits a recorded batch, and
``AnthropicBatchClient.find_batch`` recovers a batch whose id was not persisted.

Tracing is optional and never stops the run: results are written by the job ledger as they are
collected; an unreachable OTLP endpoint only costs the spans.

    uv run python scripts/t5_batch.py
"""

from __future__ import annotations

import argparse
import os
import sys

from ledger.baseline.batch import AmbiguousBatch, AnthropicBatchClient
from ledger.baseline.join import read_contexts
from ledger.baseline.request import OutputModeUnset, require_output_mode
from ledger.baseline.run import load_runs, submit_or_collect, trace_runs
from ledger.baseline.runtime import init_tracing_safely, shutdown_tracing_safely
from ledger.config import load_config
from ledger.tracing import otel


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", metavar="PATH", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(override=args.config)
    if not cfg.generator.use_batch:
        print("t5_batch: generator.use_batch is false; this script is Batch-only", file=sys.stderr)
        return 2
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("t5_batch: ANTHROPIC_API_KEY is not set (env only)", file=sys.stderr)
        return 2
    contexts_path = cfg.paths.results_dir / "t5" / "contexts.jsonl"
    if not contexts_path.exists():
        print(f"t5_batch: {contexts_path} missing; run scripts/t5_join.py", file=sys.stderr)
        return 2

    import anthropic

    client = AnthropicBatchClient(
        anthropic.Anthropic(), cfg.paths.results_dir / "t5_batch_sidecar.jsonl"
    )
    init_tracing_safely(cfg)
    try:
        with otel.run_span("ledger.t5_batch", {"rag.record_type": "t5_batch_run"}):
            contexts = read_contexts(contexts_path)
            summary = submit_or_collect(
                cfg, contexts, client, ledger_path=cfg.paths.results_dir / "t5_jobs.jsonl"
            )
            by_id = {c["question_id"]: c for c in contexts}
            traced = trace_runs(
                cfg,
                load_runs(cfg, sorted(by_id), require_output_mode(cfg.generator)),
                by_id,
                require_output_mode(cfg.generator),
                cfg.paths.results_dir / "t5_traced.txt",
            )
            print(f"spans emitted for {traced} collected results")
    except OutputModeUnset as exc:
        print(f"t5_batch REFUSED: {exc}", file=sys.stderr)
        return 2
    except AmbiguousBatch as exc:
        print(f"t5_batch STOPPED: {exc}", file=sys.stderr)
        return 3
    finally:
        shutdown_tracing_safely()
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
