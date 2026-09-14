"""``ledger`` command-line interface — the contract from CLAUDE.md, built incrementally T1–T14.

T1 registers every subcommand with its real name and argument signature so later sessions copy
argument names from here, not from prose. Bodies raise ``NotImplementedError`` until the task
that builds them lands. Nothing numeric is passed on the command line except ``--seed``,
``--n``, ``--limit`` (and ``--controls``, kept because the CLAUDE.md command block shows it);
everything else lives in ``configs/base.yaml`` plus an optional ``--config`` override (D31).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence

from ledger import __version__
from ledger.config import DEFAULT_CONFIG_PATH, Config, load_config

Handler = Callable[[Config, argparse.Namespace], int]


def _not_built(task: str) -> Handler:
    def handler(cfg: Config, args: argparse.Namespace) -> int:
        raise NotImplementedError(f"`ledger {args.command}` is built in {task}")

    return handler


# ---- subcommand handlers (all stubs in T1) -------------------------------------------------

cmd_ingest = _not_built("T2/T3 (D-001: stops at ingest.confirm_after_docs until confirmed)")
cmd_audit_tables = _not_built("T3 (A1)")
cmd_index = _not_built("T4 (D-002, D24: writes data/chunk_ids.lock)")
cmd_loadtest = _not_built("T4 (A8, D-012)")
cmd_baseline = _not_built("T5 (A4/A6/A7)")
cmd_questions = _not_built("T7 (D24: refuses to run without data/chunk_ids.lock)")
cmd_pilot = _not_built("T6 (A2, D-003/D-004)")
cmd_matrix = _not_built("T14 (D-009, Batch only per D28)")
cmd_eval = _not_built("T16 (D26)")
cmd_kappa = _not_built("T16 (D-010)")
cmd_audit_decomp = _not_built("T8/T15 (D15)")
cmd_smoke = _not_built("T17 (D28)")


# ---- parser ---------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ledger",
        description="LEDGER v1 — claim-level verification and repair for RAG.",
    )
    parser.add_argument("--version", action="version", version=f"ledger {__version__}")
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help=f"override YAML deep-merged onto {DEFAULT_CONFIG_PATH} (D31)",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p = sub.add_parser("ingest", help="download + parse the corpus; stops at 20 docs (D-001)")
    p.add_argument("--limit", type=int, metavar="N", help="parse only the first N documents")
    p.add_argument("--all", action="store_true", help="continue past the D-001 stop")
    p.add_argument(
        "--confirmed",
        action="store_true",
        help="owner has confirmed table_chunk_share; required with --all",
    )
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("audit-tables", help="A1 cell-integrity audit -> reports/a1_tables.md")
    p.add_argument("--n", type=int, metavar="N", help="number of tables to audit")
    p.set_defaults(func=cmd_audit_tables)

    p = sub.add_parser("index", help="chunk, embed (bf16), build the Qdrant file, freeze chunk IDs")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("loadtest", help="A8: embedder + reranker + verifier resident, nvidia-smi")
    p.set_defaults(func=cmd_loadtest)

    p = sub.add_parser("baseline", help="single-shot run; also A4/A6/A7 numbers")
    p.add_argument("--questions", metavar="PATH", required=True, help="questions JSONL")
    p.set_defaults(func=cmd_baseline)

    p = sub.add_parser("questions", help="D24 question generation + filters")
    p.add_argument("--n", type=int, metavar="N", help="questions to generate")
    p.add_argument("--controls", type=int, metavar="N", help="unanswerable controls to generate")
    p.set_defaults(func=cmd_questions)

    p = sub.add_parser("pilot", help="A2: 2 verifiers x 2 input modes -> kappa table")
    p.add_argument("--labels", metavar="PATH", required=True, help="pilot labels JSONL")
    p.set_defaults(func=cmd_pilot)

    p = sub.add_parser("matrix", help="run every cell for one seed via Batch (D-009)")
    p.add_argument("--seed", type=int, required=True, metavar="N", help="seed to run")
    p.add_argument(
        "--confirm-seed-1-inspected",
        action="store_true",
        dest="confirm_seed_1_inspected",
        help="required for any seed other than 1 (D-009)",
    )
    p.set_defaults(func=cmd_matrix)

    p = sub.add_parser("eval", help="D26 table with CIs -> reports/results.md")
    p.add_argument("results_dir", metavar="RESULTS_DIR", help="directory of results/*.jsonl")
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("kappa", help="paired 100/100 kappa (D-010)")
    p.add_argument("--labels", metavar="PATH", required=True, help="week-3 labels JSONL")
    p.set_defaults(func=cmd_kappa)

    p = sub.add_parser("audit-decomp", help="D15 decomposition audit sheet")
    p.add_argument("--answers", metavar="RUN", required=True, help="answers run to audit")
    p.add_argument("--n", type=int, metavar="N", help="answers to sample")
    p.set_defaults(func=cmd_audit_decomp)

    p = sub.add_parser("smoke", help="20-question regression eval (D28)")
    p.set_defaults(func=cmd_smoke)

    return parser


def _validate(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Cross-argument guards that argparse cannot express. These are code guards, not context."""
    if args.command == "ingest" and args.all and not args.confirmed:
        parser.error("--all requires --confirmed: report table_chunk_share first (D-001)")
    if args.command == "matrix" and args.seed != 1 and not args.confirm_seed_1_inspected:
        parser.error("seeds other than 1 require --confirm-seed-1-inspected (D-009)")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate(parser, args)
    cfg = load_config(override=args.config)
    return args.func(cfg, args)


if __name__ == "__main__":
    sys.exit(main())
