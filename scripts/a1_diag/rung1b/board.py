"""Rung-1b build scoreboard on the 77 BURNED tables (D-039; the fresh set is never touched).

Each checkpoint: (1) the emitter on the pilot units via the rung-1b path - ``run_rung1.py
--fired live --covered none --out data/parsed_rung1b --force`` (the same trigger path Part C runs
on the fresh set; owner requirement 2026-10-01); (2) the burned oracle (as frozen at c6c8724)
scored on ``data/parsed_rung1b`` with the evaluator's own scoring functions, beside rung 1's
output (``data/parsed_rung1``); per family MER (47 = held-out 45 + tuning 2) / ERP 4 / STEO 26:
strict and header association, trigger fired before (rung 1's pinned list) / after (live), newly
fired, no longer fired, fired-then-fell-back, every table whose strict FELL vs rung 1; (3) the
BUDGET/CBO pins on ``data/parsed_rung1b`` and clause-1 recall on the eight A1 tables.
Appends to ``reports/a1_diag/rung1b/build_log.md``.

    uv run --with pdfplumber python scripts/a1_diag/rung1b/board.py [--label L] [--units U ...]
        [--no-emit]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate_1b as ev  # noqa: E402

REPO = ev.REPO
OUT = "data/parsed_rung1b"
LOG = REPO / "reports" / "a1_diag" / "rung1b" / "build_log.md"
PILOT_EIA_ERP = [
    "eia-pdf-AEO_Narrative",
    "eia-pdf-sec1",
    "eia-pdf-sec3",
    "eia-pdf-sec4",
    "eia-pdf-sec8",
    "eia-pdf-sec11",
    "eia-pdf-sec13",
    "eia-pdf-steo_full",
    "govinfo-ERP-2026-table4",
    "govinfo-ERP-2026-table22",
]
FAM = {"MER held-out": "MER", "tuning": "MER", "ERP": "ERP", "STEO": "STEO"}


def emit(units: list[str]) -> None:
    cmd = [
        sys.executable,
        str(REPO / "scripts/a1_diag/rung1/run_rung1.py"),
        "--fired",
        "live",
        "--covered",
        "none",
        "--out",
        OUT,
        "--force",
        "--units",
        *units,
    ]
    run = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    if run.returncode:
        raise SystemExit(run.stdout[-2000:] + run.stderr[-4000:])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--label", default="")
    ap.add_argument("--units", nargs="*", help="emit only these (default: the 10 EIA/ERP units)")
    ap.add_argument("--all", action="store_true", help="emit all 19 pilot units (checkpoints)")
    ap.add_argument("--no-emit", action="store_true")
    args = ap.parse_args()
    if not args.no_emit:
        units = args.units or PILOT_EIA_ERP
        if args.all:
            units = sorted(p.stem for p in (REPO / "data/parsed_rung1").glob("*.json"))
        emit(units)
    lists = ev.burned_lists()
    docs: dict = {}
    pgs: dict = {}
    base = REPO / "data/parsed"
    r1 = ev.score_side(lists, REPO / "data/parsed_rung1", base, pgs, docs)
    r1b = ev.score_side(lists, REPO / OUT, base, pgs, docs)
    log1 = ev.emit_logs(REPO / "data/parsed_rung1")
    log1b = ev.emit_logs(REPO / OUT)
    agg: dict[str, Counter] = {f: Counter() for f in ("MER", "ERP", "STEO")}
    fell, newly, gone, fellback = [], [], [], []
    for t in lists["tables"]:
        fam = FAM[t["family"]]
        key = f"{t['unit']}|{t['table_index']}"
        a, b = r1[key][0], r1b[key][0]
        for side, r in (("r1", a), ("r1b", b)):
            agg[fam][f"{side}_strict"] += r["strict"]
            agg[fam][f"{side}_hm"] += r["header_matched"]
            agg[fam][f"{side}_hc"] += r["header_cols"]
        agg[fam]["cells"] += b["cells"]
        k = (t["unit"], t["table_index"])
        s1, s2 = log1.get(k, "not fired"), log1b.get(k, "not fired")
        agg[fam]["fired_before"] += s1 != "not fired"
        agg[fam]["fired_after"] += s2 != "not fired"
        tag = f"{t['table_id']} p{t['page']}"
        if s1 == "not fired" and s2 != "not fired":
            newly.append(f"{fam} {tag} ({s2})")
        if s1 != "not fired" and s2 == "not fired":
            gone.append(f"{fam} {tag}")
        if s2 == "fallback":
            agg[fam]["fell_back"] += 1
            fellback.append(f"{fam} {tag}")
        if b["strict"] < a["strict"]:
            was, now_ = ev.pct(a["strict"], a["cells"]), ev.pct(b["strict"], b["cells"])
            fell.append(f"{fam} {tag}: {was} -> {now_}")
    pins = ev.pins_check(REPO / OUT)
    rec_b, rec_n = ev.clause1("data/parsed"), ev.clause1(OUT)
    rec_changed = {
        k: f"{v['recall_pct']} -> {rec_n[k]['recall_pct']}"
        for k, v in rec_b.items()
        if (v["hit"], v["on_page"]) != (rec_n[k]["hit"], rec_n[k]["on_page"])
    }
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    L = [
        f"### {now} {args.label}",
        "",
        "| family | cells | strict rung 1 -> 1b | header rung 1 -> 1b | fired before -> after | "
        "fell back |",
        "|---|---|---|---|---|---|",
    ]
    for fam, c in agg.items():
        L.append(
            f"| {fam} | {c['cells']} | {ev.pct(c['r1_strict'], c['cells'])} -> "
            f"**{ev.pct(c['r1b_strict'], c['cells'])}** | {ev.pct(c['r1_hm'], c['r1_hc'])} -> "
            f"{ev.pct(c['r1b_hm'], c['r1b_hc'])} | {c['fired_before']} -> {c['fired_after']} | "
            f"{c['fell_back']} |"
        )
    L += [
        "",
        f"- newly fired ({len(newly)}): {newly}",
        f"- no longer fired ({len(gone)}): {gone}",
        f"- fired then fell back ({len(fellback)}): {fellback}",
        f"- strict FELL vs rung 1 ({len(fell)}): {fell}",
        f"- BUDGET/CBO pins on {OUT}: identical={pins['identical']} "
        f"changed={len(pins['changed'] or [])} absent={pins['absent_units']}",
        f"- clause-1 recall changed vs data/parsed: {rec_changed or 'none (unchanged on all 8)'}",
        "",
    ]
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
