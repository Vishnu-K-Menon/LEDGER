"""T6 label tool (D-044 item 4; status 2026-10-14 (2)). Run it directly in a PowerShell window:

    uv run python scripts/t6_label.py

Refuses unless: stdout is a UTF-8 console (not redirected); docs/t6_label_guide.md is committed;
the claim ids in data/labels_pilot.jsonl are committed. Resumable: re-run to continue at the
first unlabelled row. When every row is labelled, commit data/labels_pilot.jsonl before any
verifier runs. The tool shows no question, gold answer, chunk ID or verifier output.
--relabel: item 6(a)'s blinded relabel of the claims ledger pilot selected; it writes
data/labels_pilot_relabel.jsonl and never shows the first label.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ledger.baseline.join import read_contexts
from ledger.baseline.runtime import read_questions
from ledger.claims.decompose import read_answers, read_claims
from ledger.config import load_config
from ledger.eval.labels import load_pilot_file
from ledger.pilot import label_tool as T


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", metavar="PATH", default=None)
    ap.add_argument(
        "--relabel",
        action="store_true",
        help="item 6(a): blinded relabel of results/t6/relabel_ids.json (written by ledger pilot)",
    )
    args = ap.parse_args(argv)
    cfg = load_config(override=args.config)
    paths = cfg.pilot.paths
    try:
        T.check_console(sys.stdout)
        T.preflight(Path(paths.labels), Path(paths.label_guide))
    except T.LabelToolRefused as exc:
        print(f"t6_label REFUSED: {exc}", file=sys.stderr)
        return 2
    print(T.self_test_text())
    if input("Do all six lines show a distinct character? (y/n): ").strip().lower() != "y":
        print("t6_label REFUSED: change the console font (e.g. Cascadia Mono) and re-run")
        return 2
    _, claims = read_claims(Path(paths.claims))
    _, rows = load_pilot_file(Path(paths.labels))
    contexts = {
        c["question_id"]: c for c in read_contexts(cfg.paths.results_dir / "t5" / "contexts.jsonl")
    }
    answers = {
        it.question_id: it.text
        for it in read_answers(cfg, read_questions(Path(cfg.paths.questions_draft))).items
    }
    by_claim = {c.claim_id: c for c in claims}
    if args.relabel:
        ids = json.loads((cfg.paths.results_dir / "t6" / "relabel_ids.json").read_text())
        slot = {r.claim_id: r for r in rows}
        items = T.build_items([slot[i] for i in ids], by_claim, contexts, answers)
        T.run_relabel_session(Path(paths.relabel), items, ask=input, say=print)
        return 0
    items = T.build_items(rows, by_claim, contexts, answers)
    T.run_session(Path(paths.labels), items, ask=input, say=print)
    return 0


if __name__ == "__main__":
    sys.exit(main())
