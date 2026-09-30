"""B5 held-out evaluation of rung 1 (run EXACTLY ONCE, after building stopped) - D-038 pass rule
and the A1-regression guard, line by line; families never pooled.

Inputs (produced by the unchanged tools, run before this): ``oracle_score.py --parsed-dir
data/parsed_rung1 --label rung1``; ``steo_score.py --parsed-dir data/parsed_rung1 --label rung1``;
``census.py --parsed-dir data/parsed_rung1 --label rung1``; ``run_owner_scripts.py --parsed-dir
data/parsed_rung1 --label rung1``; baselines ``*_baseline`` / ``*_rung1base``. This script adds the
flip matrix, pairing loss, and the BUDGET/CBO guards (``guards.py``, v1 as committed at A4 and the
v2 correction), and writes ``reports/a1_diag/rung1/evaluation.json`` + ``REPORT_tables.md``.

    uv run --with pdfplumber python scripts/a1_diag/rung1/evaluate.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import guards  # noqa: E402
from run_owner_scripts import is_body, owner_nums  # noqa: E402

REPO = guards.REPO
A1D = REPO / "reports" / "a1_diag"
OUT = A1D / "rung1"
NEW = "data/parsed_rung1"
BASE_SHA = "e2a8e12d1cf7787540b13a971591c53b7c5471c48cc537d8434b3aa38f9bcc0f"
FAMILIES = ("MER held-out", "ERP", "STEO", "tuning")
ADMISSION = {
    "MER held-out": "per-cell admission (A6), later edition",
    "ERP": "per-cell admission (A6), same edition",
    "STEO": "whole-row admission, same edition",
    "tuning": "per-cell admission (A6), later edition; tuning set, never held-out",
}


def pct(a, b) -> float | None:
    return round(100 * a / b, 2) if b else None


def family_rows(label: str) -> dict[str, list[dict]]:
    osr = json.loads((A1D / f"oracle_score_{label}.json").read_text(encoding="utf-8"))
    ssr = json.loads((A1D / f"steo_score_{label}.json").read_text(encoding="utf-8"))
    out: dict[str, list[dict]] = defaultdict(list)
    for r in osr:
        fam = (
            "tuning"
            if r["set"] == "tuning"
            else ("ERP" if r["source"] == "ERP" else "MER held-out")
        )
        out[fam].append(r)
    for r in ssr:
        r = dict(r, header_cols=r["periods"], unit="eia-pdf-steo_full")
        out["STEO"].append(r)
    return out


def aggregate(rows: list[dict]) -> dict:
    s = Counter()
    for r in rows:
        for k in (
            "cells",
            "strict",
            "lenient",
            "missing_row",
            "missing_col",
            "header_cols",
            "header_matched",
        ):
            s[k] += r[k]
    return {
        **s,
        "strict_pct": pct(s["strict"], s["cells"]),
        "lenient_pct": pct(s["lenient"], s["cells"]),
        "header_pct": pct(s["header_matched"], s["header_cols"]),
    }


def census(label: str) -> dict[str, dict]:
    out: dict[str, Counter] = defaultdict(Counter)
    with (A1D / f"census_tables_{label}.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out[row["source"]]["body"] += int(row["body"])
            out[row["source"]]["merged_body"] += int(row["merged_body"])
    return {k: {**v, "rate_pct": pct(v["merged_body"], v["body"])} for k, v in out.items()}


def owner(label: str, parsed_dir: str, nums) -> dict:
    res = json.loads((A1D / "repro" / label / "pdf_results.json").read_text(encoding="utf-8"))
    out = {}
    for unit, ti, page, _d, _n, n_on_page, hit, _m, _j, _e in res:
        doc = json.loads((REPO / parsed_dir / f"{unit}.json").read_text(encoding="utf-8"))
        body = [c for c in doc["tables"][ti]["data"]["table_cells"] if is_body(c)]
        mb = sum(1 for c in body if len(nums(c["text"])) > 1)
        out[f"{unit}|{ti}"] = {
            "page": page,
            "recall_pct": pct(hit, n_on_page),
            "hit": hit,
            "on_page": n_on_page,
            "ceiling_pct": pct(max(0, len(body) - 2 * mb), len(body)),
        }
    erp = json.loads((A1D / "repro" / label / "erp_results.json").read_text(encoding="utf-8"))
    tot = sum(r["gt_cells"] for r in erp.values())
    ok = sum(r["correct"] for r in erp.values())
    return {"pdf_tables": out, "erp_a1_strict_pct": pct(ok, tot)}


def main() -> int:
    nums = owner_nums((REPO / "reports" / "a1_scripts" / "pdf_recall.py").read_text("utf-8"))
    base_rows, new_rows = family_rows("baseline"), family_rows("rung1")
    logs = {}
    for p in (REPO / NEW / "_emit_log").glob("*.json"):
        lg = json.loads(p.read_text(encoding="utf-8"))
        for ti, v in lg["tables"].items():
            logs[(lg["unit"], int(ti))] = v["status"]
    ev: dict = {"families": {}, "per_table": {}}
    # per family, per table
    b_out = guards.cell_outcomes("data/parsed")
    n_out = guards.cell_outcomes(NEW)
    flips = guards.flips(b_out, n_out)
    for fam in FAMILIES:
        b, n = aggregate(base_rows[fam]), aggregate(new_rows[fam])
        f = flips[fam]
        ev["families"][fam] = {
            "admission": ADMISSION[fam],
            "baseline": b,
            "rung1": n,
            "flips_value": f["flip_value"],
            "flips_character_level": f["flip_character_level"],
            "flip_value_pct": pct(f["flip_value"], f["cells"]),
        }
        rows = []
        bmap = {(r["unit"], r["table_index"]): r for r in base_rows[fam]}
        for r in new_rows[fam]:
            key = (r["unit"], r["table_index"])
            b_r = bmap[key]
            rows.append(
                {
                    "table": r["table_id"],
                    "page": r["page"],
                    "unit": r["unit"],
                    "status": logs.get(key, "?"),
                    "cells": r["cells"],
                    "strict_base": pct(b_r["strict"], b_r["cells"]),
                    "strict": pct(r["strict"], r["cells"]),
                    "lenient": pct(r["lenient"], r["cells"]),
                    "header": f"{r['header_matched']}/{r['header_cols']}",
                    "header_base": f"{b_r['header_matched']}/{b_r['header_cols']}",
                    "row_nf": r["missing_row"],
                    "col_nf": r["missing_col"],
                }
            )
        ev["per_table"][fam] = rows
    ev["families"]["STEO"]["pairing_loss_baseline"] = guards.pairing_loss("data/parsed", b_out)
    ev["families"]["STEO"]["pairing_loss_rung1"] = guards.pairing_loss(NEW, n_out)
    # census and the owner's A1 scripts
    ev["census"] = {"baseline": census("rung1base"), "rung1": census("rung1")}
    ev["owner"] = {
        "baseline": owner("rung1base", "data/parsed", nums),
        "rung1": owner("rung1", NEW, nums),
    }
    # BUDGET / CBO guards, v1 (as committed) and v2 (correction)
    base_file = REPO / "data/parsed_rung1/_baseline/baseline_guards.json"
    committed = base_file.read_text(encoding="utf-8")
    assert hashlib.sha256(committed.encode()).hexdigest() == BASE_SHA
    bc_base = {
        "v1": json.loads(committed)["bc_tables"],
        "v2": guards.bc_tables("data/parsed", "baseline", "v2"),
    }
    ev["bc_baseline_v1_reproduced"] = (
        guards.bc_tables("data/parsed", "baseline_check", "v1") == bc_base["v1"]
    )
    bc_new = {d: guards.bc_tables(NEW, "rung1", d) for d in ("v1", "v2")}
    bc = {}
    for d in ("v1", "v2"):
        clause3, clause4, cons, fired_n = [], [], [], Counter()
        for key, b in bc_base[d].items():
            unit, ti = key.split("|")
            st = logs.get((unit, int(ti)), "not fired")
            n = bc_new[d][key]
            if st == "not fired":
                if n["sha256"] != b["sha256"]:
                    clause3.append(key)
            else:
                fired_n[b["family"]] += 1
                fired_n[f"{b['family']} {st}"] += 1
                pa = Counter({tuple(k): v for k, v in b["pairs"]})
                pb = Counter({tuple(k): v for k, v in n["pairs"]})
                ch = sum(((pa - pb) + (pb - pa)).values())
                if ch:
                    clause4.append({"table": key, "pairs_changed": ch})
            cb, cn = b.get("conservation"), n.get("conservation")
            if (
                cb
                and cn
                and ((cn["share"] or 0) < (cb["share"] or 0) or cn["excess"] > cb["excess"])
            ):
                cons.append({"table": key, "base": cb, "rung1": cn})
        bc[d] = {
            "clause3_changed_nonfired": clause3,
            "clause4_changed_tables": clause4,
            "conservation_worse": cons,
            "fired": dict(fired_n),
        }
    ev["bc"] = bc
    (OUT / "evaluation.json").write_text(json.dumps(ev, indent=1, default=str), encoding="utf-8")
    # tables for the report
    L = []
    for fam in FAMILIES:
        e = ev["families"][fam]
        b, n = e["baseline"], e["rung1"]
        L += [
            f"### {fam} ({e['admission']})",
            "",
            "| | strict | lenient | header assoc. | row not found | column not found |",
            "|---|---|---|---|---|---|",
            f"| baseline | {b['strict_pct']} % ({b['strict']}/{b['cells']}) | "
            f"{b['lenient_pct']} % | "
            f"{b['header_pct']} % | {b['missing_row']} | {b['missing_col']} |",
            f"| rung 1 | **{n['strict_pct']} %** ({n['strict']}/{n['cells']}) | "
            f"{n['lenient_pct']} % | "
            f"{n['header_pct']} % | {n['missing_row']} | {n['missing_col']} |",
            "",
            f"Flips (correct at baseline -> wrong after): value {e['flips_value']} "
            f"({e['flip_value_pct']} % of {n['cells']}), character-level (flag / fused negative) "
            f"{e['flips_character_level']}."
            + (
                f" Cells lost to repeated-label pairing: baseline {e['pairing_loss_baseline']}, "
                f"rung 1 {e['pairing_loss_rung1']}."
                if fam == "STEO"
                else " Cells lost to repeated-label pairing: n/a (period keys)."
            ),
            "",
            "| table | page | unit | trigger | cells | strict base | **strict** | lenient | header "
            "(base) | row NF | col NF |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in ev["per_table"][fam]:
            L.append(
                f"| {r['table']} | {r['page']} | `{r['unit']}` | {r['status']} | {r['cells']} | "
                f"{r['strict_base']} | **{r['strict']}** | {r['lenient']} | {r['header']} "
                f"({r['header_base']}) | {r['row_nf']} | {r['col_nf']} |"
            )
        L.append("")
    (OUT / "REPORT_tables.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                k: {kk: vv for kk, vv in v.items() if kk in ("baseline", "rung1", "flip_value_pct")}
                for k, v in ev["families"].items()
            },
            indent=1,
            default=str,
        )[:3000]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
