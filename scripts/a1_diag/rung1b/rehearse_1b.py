"""A3, extra - rehearsal of the evaluator's FRESH code path on the BURNED tables (no fresh file is
read; owner status 2026-10-01: "no fresh file is read" in the dry-run).

The burned oracle (as frozen at c6c8724) is rewritten into the fresh oracle's file format in a temp
dir: ``admission/tables.json`` + ``mer_cells.jsonl`` (``admitted_b`` = ``admitted``, so no forced
misses) + ``erp_cells.jsonl`` + ``steo/cells.jsonl`` (STEO cells re-keyed to synthetic
``table_index`` 1000+k, as the fresh STEO admission writes them). ``evaluate_1b.run`` is then
called in fresh mode with its fresh paths pointed at that dir and at ``data/raw`` (the
integrity check against ``eval_freeze.json`` is skipped - it is not written yet - and the
fresh denominators are set to the burned ones). Every number must equal the burned-mode run
(``dryrun/c``): this exercises the fresh table-list loading, the temp PDF mirror for
``oracle.read_page``, the STEO page mapping and the frozen-rule reproduction assert.

    uv run --with pdfplumber python scripts/a1_diag/rung1b/rehearse_1b.py
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate_1b as ev1b  # noqa: E402

REPO = ev1b.REPO
OUT = REPO / "reports" / "a1_diag" / "rung1b" / "dryrun" / "rehearsal.log"


def main() -> int:
    orc = ev1b.orc
    cells = [json.loads(x) for x in (orc.OUT / "cells.jsonl").open(encoding="utf-8")]
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp)
        (fresh / "admission").mkdir()
        (fresh / "steo").mkdir()
        mer, erp, steo_cells, tables = [], [], [], []
        seen: set = set()
        for c in cells:
            fam = c.get("family")
            if fam == "STEO":
                continue
            if (c["unit"], c["page"]) in ev1b.TUNING:
                continue  # tuning tables are not in the held-out comparison
            is_erp = "ERP" in c["unit"]
            c = dict(c, family="ERP" if is_erp else "MER")
            if not is_erp:
                c["admitted_b"] = c["admitted"]
            (erp if is_erp else mer).append(c)
            key = (c["unit"], c["table_index"])
            if key not in seen:
                seen.add(key)
                tables.append(
                    {
                        "family": c["family"],
                        "unit": c["unit"],
                        "page": c["page"],
                        "table_id": c["table_id"],
                        "table_index": c["table_index"],
                        "undetected": False,
                    }
                )
        # STEO: re-key every table to 1000+k in page order, as fresh_oracle.py writes them
        by_ti = defaultdict(list)
        for c in cells:
            if c.get("family") == "STEO":
                by_ti[c["table_index"]].append(c)
        # written as fresh_oracle.py writes them: the frozen rule called with 1000+k (the footnote
        # list is keyed by table index, so re-keying the burned records would not reproduce)
        for k, ti in enumerate(sorted(by_ti, key=lambda t: by_ti[t][0]["page"])):
            page, tid = by_ti[ti][0]["page"], by_ti[ti][0]["table_id"]
            res = ev1b.steo.admit_table_rows(
                "eia-pdf-steo_full", 1000 + k, page, tid, ev1b.steo_footnotes.view_of(tid)
            )
            assert [c["admitted"] for c in res["cells"]] == [c["admitted"] for c in by_ti[ti]]
            steo_cells += res["cells"]
        for name, rows in (("admission/mer_cells.jsonl", mer), ("admission/erp_cells.jsonl", erp)):
            (fresh / name).write_text(
                "".join(json.dumps(c, sort_keys=True) + "\n" for c in rows), "utf-8"
            )
        (fresh / "steo" / "cells.jsonl").write_text(
            "".join(json.dumps(c) + "\n" for c in steo_cells), "utf-8"
        )
        (fresh / "admission" / "tables.json").write_text(json.dumps(tables), "utf-8")
        den = sum(c["admitted"] for c in mer)
        ev1b.FRESH = fresh
        ev1b.RAW_FRESH = REPO / "data" / "raw"
        ev1b.FRESH_STEO_UNIT = "eia-pdf-steo_full"
        ev1b.MER_CONSERVATIVE_DEN, ev1b.MER_FORCED_MISSES = den, 0
        ev1b.ERP_OUT = ()
        ev1b.check_eval_freeze = lambda *a: {"skipped": "rehearsal"}
        args = argparse.Namespace(
            oracle="fresh",
            baseline="data/parsed",
            candidate="data/parsed_rung1",
            pilot_baseline="data/parsed",
            pilot_candidate="data/parsed_rung1",
            candidate_manifest=None,
        )
        got = ev1b.run(args)
    ref = json.loads(
        (REPO / "reports/a1_diag/rung1b/dryrun/c/evaluation.json").read_text(encoding="utf-8")
    )
    log, ok = [], True
    pairs = (("MER", "MER held-out"), ("ERP", "ERP"), ("STEO", "STEO"))
    for fam, rfam in pairs:
        g, r = got["families"][fam], ref["families"][rfam]
        for side in ("baseline", "candidate"):
            for k in ("tables", "cells", "strict", "header_cols", "header_matched"):
                same = g[side][k] == r[side][k]
                ok &= same
                if not same:
                    log.append(f"[FAIL] {fam} {side} {k}: fresh path {g[side][k]} vs {r[side][k]}")
        same = g["flips"] == r["flips"] and g["bootstrap_plain"] == r["bootstrap_plain"]
        ok &= same
        log.append(
            f"[{'OK' if same else 'FAIL'}] {fam}: strict {g['baseline']['strict_pct']} -> "
            f"{g['candidate']['strict_pct']} (burned path {r['baseline']['strict_pct']} -> "
            f"{r['candidate']['strict_pct']}); header {g['candidate']['header_pct']} "
            f"({r['candidate']['header_pct']}); flips {g['flips'].get('flip_value', 0)} "
            f"({r['flips'].get('flip_value', 0)}); CI {g['bootstrap_plain']} "
            f"({r['bootstrap_plain']}); conservative == plain: "
            f"{g['candidate']['conservative_strict_pct'] == g['candidate']['strict_pct']}"
        )
    log.append(f"STEO TableItems on each oracle page: {got['steo_tableitems_on_page']}")
    log.append(f"VERDICT: {'FRESH PATH REPRODUCES THE BURNED PATH' if ok else 'FAIL'}")
    OUT.write_text("\n".join(log) + "\n", encoding="utf-8")
    print("\n".join(log))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
