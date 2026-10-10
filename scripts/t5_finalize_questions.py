"""Finalize the owner-checked draft questions (D-043). Reads data/questions_draft_candidates.jsonl
(``accept`` true set by the owner on 13 table + 12 prose + 5 control lines, ``checked_by`` filled)
and writes data/questions_draft.jsonl. Refuses unless: the counts are 13 / 12 / 5; every gold
answer is an exact substring of its gold chunk's text; at most one question per distinct table;
every gold chunk id is in the lock. No API call.

    uv run python scripts/t5_finalize_questions.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ledger.baseline.drafting import FinalizeRefused, finalize
from ledger.config import load_config
from ledger.retrieval.index import read_chunks, read_lock

CANDIDATES = Path("data/questions_draft_candidates.jsonl")
OUT = Path("data/questions_draft.jsonl")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", metavar="PATH", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(override=args.config)
    latest: dict[str, dict] = {}  # a retried draft appends a new line: the last one per id wins
    for ln in CANDIDATES.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            rec = json.loads(ln)
            latest[rec["candidate_id"]] = rec
    candidates = [c for c in latest.values() if c["candidate_id"] != "c-all"]
    chunks = {c["chunk_id"]: c for c in read_chunks(cfg.paths.chunks)}
    _, entries = read_lock(cfg.paths.chunk_ids_lock)
    try:
        records = finalize(candidates, chunks, {cid for cid, _ in entries}, cfg)
    except FinalizeRefused as exc:
        print(f"t5_finalize_questions REFUSED:\n{exc}", file=sys.stderr)
        return 2
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"wrote {len(records)} questions -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
