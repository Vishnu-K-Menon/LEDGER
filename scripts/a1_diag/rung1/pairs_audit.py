"""Clause-4 diagnostic (report only, never a gate): are the label-number pairs that rung 1 changes
on fired BUDGET/CBO tables corrections or regressions, judged against the printed page?

A pair (label, number) is **page-consistent** iff some printed line in the table bbox carries the
number as a value token and the label's last two words (all of them if shorter; an empty label:
no words) among that line's other tokens, or on the line just above it (a wrapped label). Changed
pairs are split into: baseline pairs lost (consistent = rung 1 lost a right pair; inconsistent =
rung 1 dropped a TableFormer mispairing) and rung-1 pairs gained (consistent = a right pair
TableFormer lacked; inconsistent = a rung-1 mispairing). Normalisation: guards v2.

    uv run --with pdfplumber python scripts/a1_diag/rung1/pairs_audit.py [--parsed-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import emit  # noqa: E402
import guards  # noqa: E402
import trigger as tg  # noqa: E402

REPO = emit.REPO


def line_index(lines: list[list[dict]]) -> list[tuple[set[str], list[str]]]:
    out = []
    for ln in lines:
        words = [w for t in ln for w in guards.norm_words(t["text"], "v2")]
        vals = set(guards.norm_value(" ".join(t["text"] for t in ln), "v2"))
        out.append((vals, words))
    return out


def consistent(label: str, number: str, idx) -> bool:
    want = label.split()[-2:]
    for i, (vals, words) in enumerate(idx):
        if number not in vals:
            continue
        if not want:
            if not words:
                return True
            continue
        pool = words + (idx[i - 1][1] if i > 0 else [])
        if all(w in pool for w in want):
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parsed-dir", default=None, help="rung-1 output; default: rebuild in memory")
    args = ap.parse_args()
    import pdfplumber

    fired = json.loads((REPO / "reports/a1_diag/rung1/trigger_fired.json").read_text("utf-8"))
    by_unit: dict[str, list[int]] = defaultdict(list)
    for unit, ti in fired:
        if "BUDGET" in unit or unit.startswith("cbo-"):
            by_unit[unit].append(ti)
    tally: Counter = Counter()
    per_table = []
    for unit, tis in sorted(by_unit.items()):
        doc = json.loads((emit.PARSED / f"{unit}.json").read_text(encoding="utf-8"))
        new_doc = (
            json.loads((REPO / args.parsed_dir / f"{unit}.json").read_text(encoding="utf-8"))
            if args.parsed_dir
            else None
        )
        with pdfplumber.open(next((REPO / "data" / "raw").rglob(f"{unit}.pdf"))) as pdf:
            for ti in tis:
                tbl = doc["tables"][ti]
                if new_doc is not None:
                    new = new_doc["tables"][ti]
                else:
                    new, _ = emit.rebuild(tbl, emit.lines_for(doc, tbl, pdf))
                    new = new or tbl
                a = guards.label_number_pairs(tbl, "v2")
                b = guards.label_number_pairs(new, "v2")
                if a == b:
                    continue
                page, box = tg.table_box(doc, tbl)
                idx = line_index(emit.tokens_in(pdf.pages[page - 1].chars, box))
                t = Counter()
                lost_ok: Counter = Counter()
                new_ok: Counter = Counter()
                for (lab, num), n in (a - b).items():
                    if consistent(lab, num, idx):
                        lost_ok[num] += n
                    else:
                        t["lost_inconsistent (TableFormer mispairing dropped)"] += n
                for (lab, num), n in (b - a).items():
                    if consistent(lab, num, idx):
                        new_ok[num] += n
                    else:
                        t["new_inconsistent (rung-1 mispairing)"] += n
                # the same number, correctly placed both times, under a label whose text differs
                relabel = sum((lost_ok & new_ok).values())
                t["relabelled (both page-consistent)"] += relabel
                t["lost_consistent (rung 1 lost a right pair)"] += sum((lost_ok - new_ok).values())
                t["new_consistent (a right pair TableFormer lacked)"] += sum(
                    (new_ok - lost_ok).values()
                )
                tally.update(t)
                tally["tables"] += 1
                per_table.append({"unit": unit, "table_index": ti, **t})
    print(dict(tally))
    out = REPO / "reports" / "a1_diag" / "rung1" / "pairs_audit.json"
    out.write_text(json.dumps({"totals": dict(tally), "tables": per_table}, indent=0), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
