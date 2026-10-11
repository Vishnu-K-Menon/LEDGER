"""T5 owner check, one candidate at a time (helper; not part of the repo).

Run from the LEDGER folder:
    uv run --no-sync python "$env:TEMP\\t5_review.py" --checked-by "Your Name"

Walks data/questions_draft_candidates.jsonl in draw order (D-043 item 1) and records YOUR decision:
  table: until 13 accepted   prose: until 12 accepted   supplement: until 1 accepted per source
  controls: every control candidate (accept the well-formed ones; at least 5)
Already-decided candidates are skipped, so you can quit any time and rerun to continue.
It only sets accept / checked_by / notes (and question / gold_answer if you edit them).
A backup of the candidates file is written before the first change.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

CANDS = Path("data/questions_draft_candidates.jsonl")
CHUNKS = Path("data/chunks.jsonl")
NEED = {"table": 13, "prose": 12}
SUPP_NEED = 1
MIN_CONTROLS = 5


def load():
    latest: dict[str, dict] = {}
    for ln in CANDS.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            r = json.loads(ln)
            latest[r["candidate_id"]] = r  # the finalizer also keeps the last line per id
    return latest


def save(latest: dict[str, dict]) -> None:
    tmp = CANDS.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        for r in latest.values():
            fh.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")
    tmp.replace(CANDS)


def show(c: dict, chunk: dict | None, n_acc: int, need: int | str) -> None:
    bar = "=" * 100
    print(f"\n{bar}\n{c['candidate_id']}  [{c['stratum']} #{c['order_index'] + 1}, {c.get('tier', '')}]"
          f"  accepted so far: {n_acc}/{need}")
    if c["stratum"] == "control":
        print(f"KIND:      {c.get('control_kind')}")
        print(f"QUESTION:  {c.get('question')}")
        print(f"RATIONALE: {c.get('rationale')}")
        return
    if "error" in c:
        print(f"DRAFT FAILED: {c['error']}")
        print("-" * 100)
        print(chunk["text"] if chunk else "(chunk not found in data/chunks.jsonl)")
        print("-" * 100)
        return
    print(f"SOURCE:    {c.get('source')} / {c.get('unit_id')}   chunk {c['chunk_id']}")
    print(f"QUESTION:  {c.get('question')}")
    print(f"GOLD:      {c.get('gold_answer')!r}   ({c.get('answer_type')})")
    gold_ok = chunk is not None and c.get("gold_answer", "") in chunk["text"]
    words = len(str(c.get("question", "")).split())
    print(f"CHECKS:    gold verbatim in chunk: {'YES' if gold_ok else 'NO  <-- finalizer will refuse'}"
          f"   words: {words} {'ok' if 8 <= words <= 40 else '<-- outside 8-40'}")
    print("-" * 100)
    print(chunk["text"] if chunk else "(chunk not found in data/chunks.jsonl)")
    print("-" * 100)


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return "q"


def decide(c: dict, chunk: dict | None, latest: dict, who: str, backed_up: list) -> str:
    """Returns 'a', 'r' or 'q'."""
    failed = "error" in c
    while True:
        k = ask("[r]eject  [q]uit > " if failed else "[a]ccept  [r]eject  [e]dit question/gold  [q]uit > ").lower()
        if failed and k in ("a", "e"):
            print("This draft failed, so there is nothing to accept: reject it (with the reason) or quit.")
            continue
        if k == "q":
            return "q"
        if k == "e":
            if c["stratum"] == "control":
                q = ask(f"question [{c.get('question')}]: ")
                if q:
                    c["question"] = q
            else:
                q = ask("new question (Enter keeps it): ")
                if q:
                    c["question"] = q
                g = ask("new gold answer, copied exactly from the chunk (Enter keeps it): ")
                if g:
                    c["gold_answer"] = g
            show(c, chunk, 0, "-")
            continue
        if k in ("a", "r"):
            if k == "a" and c["stratum"] != "control":
                if chunk is None or c.get("gold_answer", "") not in chunk["text"]:
                    print("Gold answer is not an exact substring of the chunk: edit it ([e]) or reject.")
                    continue
            note = ""
            if k == "r":
                while not note:
                    note = ask("reason for rejecting (required): ")
            if not backed_up:
                bak = CANDS.with_name(f"questions_draft_candidates.backup-{time.strftime('%Y%m%d-%H%M%S')}.jsonl")
                shutil.copyfile(CANDS, bak)
                backed_up.append(bak)
                print(f"(backup written: {bak})")
            c["accept"] = k == "a"
            c["checked_by"] = who
            if note:
                c["notes"] = note
            latest[c["candidate_id"]] = c
            save(latest)
            return k
        print("type a, r, e or q")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # PowerShell 5 console is cp1252
    ap = argparse.ArgumentParser()
    ap.add_argument("--checked-by", required=True)
    who = ap.parse_args().checked_by.strip()
    if not CANDS.exists():
        print(f"{CANDS} not found: run scripts/t5_draft.py first (from the LEDGER folder)")
        return 2
    latest = load()
    errs = [cid for cid, r in latest.items() if "error" in r and r.get("accept") is not False]
    if errs:
        print(f"These drafts failed: {errs}. Rerun scripts/t5_draft.py once; if one fails again, you can")
        print("reject it here with a reason (it is then replaced by the next candidate in draw order).")
    chunks = {}
    for ln in CHUNKS.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            r = json.loads(ln)
            chunks[r["chunk_id"]] = r
    backed_up: list = []

    groups: list[tuple[str, list[dict], int | None]] = []
    for s in ("table", "prose"):
        groups.append((s, [r for r in latest.values() if r["stratum"] == s], NEED[s]))
    supp: dict[str, list[dict]] = {}
    for r in latest.values():
        if r["stratum"] == "supplement":
            supp.setdefault(r["supp_source"], []).append(r)
    for src, rs in sorted(supp.items()):
        groups.append((f"supplement {src}", rs, SUPP_NEED))
    groups.append(("control", [r for r in latest.values() if r["stratum"] == "control"], None))

    for label, rs, need in groups:
        rs.sort(key=lambda r: r["order_index"])
        n_acc = sum(r.get("accept") is True for r in rs)
        print(f"\n##### {label}: {n_acc} accepted so far"
              + (f", need {need}" if need else f", accept every well-formed one (at least {MIN_CONTROLS})"))
        for c in rs:
            if need is not None and n_acc >= need:
                break
            if c.get("accept") is not None:
                continue
            show(c, chunks.get(c.get("chunk_id", "")), n_acc, need or "all")
            k = decide(c, chunks.get(c.get("chunk_id", "")), latest, who, backed_up)
            if k == "q":
                print("Saved. Rerun the same command to continue where you stopped.")
                return 0
            n_acc += k == "a"
        if need is not None and n_acc < need:
            print(f"!! {label}: only {n_acc} of {need} accepted and no candidates left. Stop and tell the planning chat.")
            return 1
    nc = sum(r.get("accept") is True for r in latest.values() if r["stratum"] == "control")
    if nc < MIN_CONTROLS:
        print(f"!! only {nc} controls accepted; at least {MIN_CONTROLS} are needed. Stop and tell the planning chat.")
        return 1
    print("\nAll quotas met. Next: uv run python scripts/t5_finalize_questions.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
