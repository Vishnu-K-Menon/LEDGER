"""A1 step 0 (STEO) step 2 - the whole-row rule vs the 22:41 rule, with an independent value check.

Reads the oracle's STEO cells under both rules (``reports/a1_diag/oracle/cells.jsonl`` - whole-row
rule; ``steo_cells_2241.jsonl`` - the superseded unit + precision gates) and reports:

* per-table admission under each rule;
* whether the 22:41 admitted set is a strict subset of the whole-row set (same table, series,
  period and printed value);
* the delta (admitted now, not under 22:41), value-checked on its own;
* an **independent** value check of every admitted cell: each cell's served value is read again
  straight from its raw snapshot file (``v<view>_<Q|A>.json``, ``parse_float=Decimal``), by
  SERIES_ID, and rounded half away from zero at the printed decimals - a separate code path from
  admission, so a defect there cannot hide here. Any mismatch is an oracle defect: STOP;
* unmapped rows, ties (rows failing uniqueness), content failures, by table;
* the discriminating-cell subset: admitted cells whose value alone rules out every other series.

    uv run python scripts/a1_diag/steo_compare.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ORACLE = REPO / "reports" / "a1_diag" / "oracle"


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def key(c: dict) -> tuple:
    return (c["table_index"], c["series_id"], c["period"], c["value"])


def independent_check(cells: list[dict]) -> list[dict]:
    """Re-read every cell's served value from its raw snapshot file; round half away from zero at
    the printed decimals; compare with the printed value. Returns the mismatches."""
    cache: dict[str, dict[str, dict]] = {}
    bad = []
    for c in cells:
        path = REPO / c["oracle_file"]
        if c["oracle_file"] not in cache:
            body = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
            cache[c["oracle_file"]] = {
                r["SERIES_ID"]: r for r in body["VIEWSDATA"]["ROWS"] if r.get("SERIES_ID")
            }
        rec = cache[c["oracle_file"]].get(c["series_id"])
        raw = (rec or {}).get("DATA", {}).get(c["period"]) if rec else None
        printed = Decimal(c["value"])
        dec = -printed.as_tuple().exponent if printed.as_tuple().exponent < 0 else 0
        if raw is None:
            bad.append({**c, "why": "not in the raw file"})
            continue
        served = Decimal(str(raw)).quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP)
        if served != printed:
            bad.append({**c, "why": f"served {raw} -> {served} at {dec} dp"})
    return bad


def main() -> int:
    new = [c for c in load(ORACLE / "cells.jsonl") if c.get("family") == "STEO"]
    old = load(ORACLE / "steo_cells_2241.jsonl")
    detail = json.loads((ORACLE / "steo_admission.json").read_text(encoding="utf-8"))

    per = defaultdict(lambda: Counter())
    for c in old:
        per[(c["table_index"], c["table_id"], c["page"])]["old_n"] += 1
        per[(c["table_index"], c["table_id"], c["page"])]["old_a"] += c["admitted"]
    for c in new:
        t = per[(c["table_index"], c["table_id"], c["page"])]
        t["new_n"] += 1
        t["new_a"] += c["admitted"]
        t["disc"] += bool(c["admitted"] and c.get("discriminating"))
    new_adm = {key(c) for c in new if c["admitted"]}
    old_adm = {key(c) for c in old if c["admitted"]}
    not_kept = old_adm - new_adm
    delta = [c for c in new if c["admitted"] and key(c) not in old_adm]
    all_bad = independent_check([c for c in new if c["admitted"]])
    delta_bad = [b for b in all_bad if key(b) not in old_adm]

    lines = [
        "# STEO step 2 - whole-row rule vs the 22:41 rule",
        "",
        "| table | page | 22:41 admitted | 22:41 rate | whole-row admitted | whole-row rate | "
        "discriminating cells |",
        "|---|---|---|---|---|---|---|",
    ]
    tot = Counter()
    for (_ti, tid, page), t in sorted(per.items()):
        tot.update(t)
        lines.append(
            f"| {tid} | {page} | {t['old_a']}/{t['old_n']} | {t['old_a'] / t['old_n']:.1%} | "
            f"{t['new_a']}/{t['new_n']} | {t['new_a'] / t['new_n']:.1%} | {t['disc']} |"
        )
    lines.append(
        f"| **all** | | {tot['old_a']}/{tot['old_n']} | {tot['old_a'] / tot['old_n']:.1%} | "
        f"{tot['new_a']}/{tot['new_n']} | {tot['new_a'] / tot['new_n']:.1%} | {tot['disc']} |"
    )
    rows = [(d["table_id"], d["page"], r) for d in detail for r in d["rows"]]
    status = Counter(r["status"] for _, _, r in rows)
    unmapped = [(t, p, r["label"]) for t, p, r in rows if r["status"].endswith("unmapped (a)")]
    ties = [(t, p, r["label"], r["tied_series"]) for t, p, r in rows if r["n_matched"] > 1]
    content = [(t, p, r["label"]) for t, p, r in rows if r["status"].endswith("content (c)")]
    disagree = Counter(
        d for _, _, r in rows if r["status"] == "admitted" for d in r["metadata_disagreements"]
    )
    summary = {
        "old_admitted": len(old_adm),
        "new_admitted": len(new_adm),
        "old_subset_of_new": not not_kept,
        "old_not_kept": len(not_kept),
        "strict_subset": not not_kept and len(new_adm) > len(old_adm),
        "delta_cells": len(delta),
        "delta_mismatches": len(delta_bad),
        "all_admitted_mismatches": len(all_bad),
        "row_status": dict(status),
        "unmapped_rows": unmapped,
        "ties": ties,
        "content_failures": content,
        "metadata_disagreements_on_admitted_rows": dict(disagree),
        "discriminating_cells": tot["disc"],
        "footnoted_admitted_cells": sum(1 for c in new if c["admitted"] and c.get("footnoted")),
        "strata_admitted": dict(Counter(c["stratum"] for c in new if c["admitted"])),
    }
    lines += ["", "```", json.dumps(summary, indent=1, default=str), "```"]
    if all_bad:
        lines += ["", "## ORACLE DEFECT - admitted cells that disagree with the page", ""]
        lines += [
            f"- {b['table_id']} {b['series_id']} {b['period']} printed {b['value']}: {b['why']}"
            for b in all_bad[:50]
        ]
    (REPO / "reports" / "a1_diag" / "steo_compare.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print("\n".join(lines))
    return 1 if all_bad else 0


if __name__ == "__main__":
    sys.exit(main())
