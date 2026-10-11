"""Gold guard (D-043 status 2026-10-10, answer matching): every gold of the 25 drafts and of s001
must occur in its own gold chunk's text with at least one occurrence that passes the longer-number
guard, using the same function that scores the answers (ledger/baseline/match.py). A gold that
fails is a fragment of a longer printed number and needs a status line. Texts come from
``load_verified_texts`` (the lock is checked). Writes reports/t5_gold_guard.md; exit 1 on a failure.
No API call.

    uv run python scripts/t5_gold_guard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from ledger.baseline.match import gold_in_text
from ledger.baseline.runtime import read_questions
from ledger.config import load_config
from ledger.retrieval.index import lf_sha256
from ledger.retrieval.query import load_verified_texts

QUESTIONS = Path("data/questions_draft.jsonl")
REPORT = Path("reports/t5_gold_guard.md")


def guard_rows(questions, texts):
    rows = []
    for q in questions:
        if q.get("set") not in ("draft", "supplement"):
            continue
        ok = gold_in_text(q["answer_type"], q["gold_answer"], texts[q["gold_chunk_id"]])
        rows.append((q["question_id"], q["answer_type"], q["gold_answer"], q["gold_chunk_id"], ok))
    return rows


def render(rows, questions_sha: str) -> str:
    bad = [r for r in rows if not r[4]]
    out = [
        "# T5 gold guard",
        "",
        f"- questions sha256 (LF): `{questions_sha}`",
        "- matcher: `ledger/baseline/match.py::gold_in_text` (the function that scores answers)",
        "",
        f"**{'PASS' if not bad else 'FAIL'}**: {len(rows) - len(bad)} of {len(rows)} golds occur "
        "in "
        "their own gold chunk with at least one occurrence that is not part of a longer number.",
        "",
    ]
    for qid, kind, gold, chunk, ok in rows:
        out.append(f"- {qid} ({kind}) `{gold}` in `{chunk}`: {'ok' if ok else 'FAIL'}")
    return "\n".join(out) + "\n"


def main() -> int:
    cfg = load_config()
    texts = load_verified_texts(cfg.paths.chunks, cfg.paths.chunk_ids_lock)
    questions = read_questions(QUESTIONS)
    rows = guard_rows(questions, texts)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render(rows, lf_sha256(QUESTIONS)), encoding="utf-8", newline="\n")
    bad = [r for r in rows if not r[4]]
    print(f"wrote {REPORT}: {len(rows) - len(bad)} of {len(rows)} ok")
    for r in bad:
        print(f"FAIL {r[0]} gold {r[2]!r} in {r[3]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
