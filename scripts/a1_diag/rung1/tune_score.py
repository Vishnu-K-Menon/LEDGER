"""Rung-1 build loop: rebuild and score ONLY the two tuning tables (3.6 sec3 p19, 4.2b sec4 p5).

Held-out tables are never opened here (D-038 rung 1, hard rule). Scores through the unchanged
``oracle_score.score_table``; writes nothing under data/parsed/.

    uv run --with pdfplumber python scripts/a1_diag/rung1/tune_score.py [--naive] [--show]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import emit  # noqa: E402
import oracle as orc  # noqa: E402
import oracle_score as osc  # noqa: E402

TUNING = (("eia-pdf-sec3", 10), ("eia-pdf-sec4", 2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--naive", action="store_true", help="rows + bands only (B1)")
    ap.add_argument("--show", action="store_true", help="print the misses")
    args = ap.parse_args()
    opts = dict(emit.OPTS)
    if args.naive:
        opts.update(wrap=False, header_check=False, assert_bands=False)
    cells = [json.loads(x) for x in (orc.OUT / "cells.jsonl").open(encoding="utf-8")]
    tot = ok = 0
    for unit, ti in TUNING:
        cs = [c for c in cells if c["admitted"] and c["unit"] == unit and c["table_index"] == ti]
        doc, logs = emit.build_unit(unit, [ti], opts)
        pg = orc.read_page(unit, "eia", ti, doc)
        detail: list = []
        res = osc.score_table(pg, doc["tables"][ti], cs, detail)
        tot += res["cells"]
        ok += res["strict"]
        print(
            f"{unit} t{ti}: strict {res['strict']}/{res['cells']} = "
            f"{res['strict'] / res['cells']:.1%} lenient {res['lenient'] / res['cells']:.1%} "
            f"rowNF {res['missing_row']} colNF {res['missing_col']} header "
            f"{res['header_matched']}/{res['header_cols']} shape {res['parsed_shape']}"
        )
        for line in logs.get(ti, [])[:8]:
            print("   log:", line)
        if args.show:
            for d in detail:
                if d["outcome"] != "strict":
                    c = d["cell"]
                    print(
                        "   miss",
                        d["outcome"],
                        c["row"],
                        c["band"],
                        c["value"],
                        repr(d.get("text")),
                    )
    print(f"TUNING strict {ok}/{tot} = {ok / tot:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
