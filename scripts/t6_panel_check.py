"""T6 attachment-error panel check (D-044 item 10): validates data/t6_panel.jsonl against run 1's
non-abstaining answers and says whether it is committed (part B refuses until it is).

    uv run python scripts/t6_panel_check.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ledger.baseline.runtime import read_questions
from ledger.claims.decompose import read_answers
from ledger.config import load_config
from ledger.pilot import repo
from ledger.pilot.panel import summary, validate_panel


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", metavar="PATH", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(override=args.config)
    path = Path(cfg.pilot.paths.panel)
    qids = [
        it.question_id
        for it in read_answers(cfg, read_questions(Path(cfg.paths.questions_draft))).items
    ]
    rows, problems = validate_panel(path, qids)
    for p in problems:
        print(f"  ! {p}")
    if problems:
        print(f"t6_panel_check: {path} INVALID ({len(problems)} problems)")
        return 2
    committed = repo.is_committed(path)
    print(f"t6_panel_check: {path} valid: {summary(rows)}; committed: {committed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
