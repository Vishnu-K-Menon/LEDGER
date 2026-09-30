"""Rung-1 build step 6: the emitter on the FIRED BUDGET/CBO tables only (not held-out; no oracle).

For each fired BUDGET/CBO table (A1's frozen list): rebuild, then report label-number pair changes
against the saved table (guard clause 4) and word conservation (C5), both from ``guards``.

    uv run --with pdfplumber python scripts/a1_diag/rung1/bc_check.py [--show N]
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", type=int, default=0)
    ap.add_argument("--units", nargs="*")
    ap.add_argument("--conservation", action="store_true")
    args = ap.parse_args()
    import pdfplumber

    fired = json.loads((REPO / "reports/a1_diag/rung1/trigger_fired.json").read_text("utf-8"))
    by_unit: dict[str, list[int]] = defaultdict(list)
    for unit, ti in fired:
        if ("BUDGET" in unit or unit.startswith("cbo-")) and (not args.units or unit in args.units):
            by_unit[unit].append(ti)
    tally = Counter()
    shown = 0
    for unit, tis in sorted(by_unit.items()):
        doc = json.loads((emit.PARSED / f"{unit}.json").read_text(encoding="utf-8"))
        pdf_path = next((REPO / "data" / "raw").rglob(f"{unit}.pdf"))
        with pdfplumber.open(pdf_path) as pdf:
            for ti in tis:
                tbl = doc["tables"][ti]
                lines = emit.lines_for(doc, tbl, pdf)
                new, log = emit.rebuild(tbl, lines)
                tally["tables"] += 1
                if new is None:
                    tally["fallback"] += 1
                    continue
                page, box = tg.table_box(doc, tbl)
                for d in ("v1", "v2"):
                    pa = guards.label_number_pairs(tbl, d)
                    pb = guards.label_number_pairs(new, d)
                    n_ch = sum(((pa - pb) + (pb - pa)).values())
                    tally[f"changed_tables_{d}"] += n_ch > 0
                    tally[f"pairs_changed_{d}"] += n_ch
                    toks = guards.page_tokens(pdf.pages[page - 1].chars, box, d)
                    ca_d = guards.conservation(tbl, toks, d)
                    cb_d = guards.conservation(new, toks, d)
                    tally[f"conservation_worse_{d}"] += (cb_d["share"] or 0) < (
                        ca_d["share"] or 0
                    ) or cb_d["excess"] > ca_d["excess"]
                a, b = guards.label_number_pairs(tbl), guards.label_number_pairs(new)
                changed = sum(((a - b) + (b - a)).values())
                toks = guards.page_tokens(pdf.pages[page - 1].chars, box, "v2")
                ca = guards.conservation(tbl, toks)
                cb = guards.conservation(new, toks)
                if args.conservation and (
                    (cb["share"] or 0) < (ca["share"] or 0) or cb["excess"] > ca["excess"]
                ):
                    print(
                        f"{unit} t{ti}: share {ca['share']} -> {cb['share']}, excess "
                        f"{ca['excess']} -> {cb['excess']}; {log[:1]}"
                    )
                if changed and shown < args.show:
                    shown += 1
                    print(f"{unit} t{ti} p{page}: {changed} pair changes; {log[:2]}")
                    print("   lost:", list((a - b).items())[:4])
                    print("   new :", list((b - a).items())[:4])
    print(dict(tally))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
