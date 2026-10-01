"""D-039 rung 1b - THE evaluator (owner status 2026-10-01). One run scores the baseline parse
first, then the candidate, against one oracle, with the same table list and the same denominators.
Nothing is printed or written until every family is complete; all results then land in one
atomic step (``<out>.tmp/`` renamed to ``<out>/``). A crash prints the exception type and the
innermost file:line only.

Modes:

* ``--oracle burned`` - the pilot oracle as frozen at c6c8724 (``reports/a1_diag/oracle/``; no
  clause (b)), step 0's split (MER held-out 45 / ERP 4 / STEO 26; tuning 2 apart). Used only for
  the A3 dry-run.
* ``--oracle fresh`` - the D-039 fresh oracle. First ``freeze.assert_frozen()``; then this
  module set's hashes, the ``data/parsed_fresh/`` manifest, the bootstrap parameters and (if given)
  the candidate manifest are checked against ``reports/a1_diag/rung1b/eval_freeze.json``. Table
  lists come from the freeze-pinned ``data/oracle/fresh/admission/tables.json`` (MER / ERP) and
  ``data/oracle/fresh/steo/cells.jsonl`` (STEO tables with >= 1 admitted cell) - owner answer at
  planning, 2026-10-01: ``freeze.json`` holds hashes only.

Per family: conservative strict (MER: every clause-(b) exclusion is a miss, D-039 status
2026-09-30 ruling (2); = plain strict for ERP / STEO), plain strict, table-bootstrap 95 %
percentile CI (B = 10,000, seed 20260930, tables resampled with replacement, cells pooled), header
association vs the in-run baseline, value flips (correct at baseline -> wrong in the candidate),
census of merged body cells (all tables of the family's units; split rebuilt / not rebuilt by the
candidate's ``_emit_log``), MER strict per section; globally the BUDGET/CBO pins over the pilot
candidate and clause-1 number recall on the eight A1 tables (pilot candidate vs ``data/parsed``).
PASS / FAIL per family by the D-039 reading; the D-038 reading beside it.

    uv run --with pdfplumber python scripts/a1_diag/rung1b/evaluate_1b.py --oracle burned \
        --baseline data/parsed --candidate data/parsed_rung1 --pilot-candidate data/parsed_rung1 \
        --out reports/a1_diag/rung1b/dryrun/c
    uv run --with pdfplumber python scripts/a1_diag/rung1b/evaluate_1b.py --oracle fresh \
        --baseline data/parsed_fresh --candidate data/parsed_fresh_rung1b \
        --pilot-candidate data/parsed_rung1b --out reports/a1_diag/rung1b/evaluation
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import logging
import os
import random
import shutil
import subprocess
import sys
import tempfile
import traceback
import warnings
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "rung1"))
sys.path.insert(0, str(HERE))
import freeze  # noqa: E402
import guards  # noqa: E402  (norm_value: the rung-1 flip normalisation)
import oracle as orc  # noqa: E402
import oracle_score as osc  # noqa: E402
import steo  # noqa: E402
import steo_footnotes  # noqa: E402
import steo_score as ss  # noqa: E402
from run_owner_scripts import is_body, localise, owner_nums  # noqa: E402

REPO = freeze.REPO
EVAL_FREEZE = REPO / "reports" / "a1_diag" / "rung1b" / "eval_freeze.json"
FRESH = REPO / "data" / "oracle" / "fresh"
RAW_FRESH = REPO / "data" / "raw_fresh"
PDF_RECALL = REPO / "reports" / "a1_scripts" / "pdf_recall.py"
PINS = REPO / "tests" / "data" / "budget_cbo_tables_sha256.json"
FRESH_STEO_UNIT = "eia-archives-aug26"
SEED = 20260930
BOOT_B = 10_000
CI_LEVEL = 0.95
TUNING = osc.TUNING
# owner status 2026-10-01 (3): MER conservative denominator and forced misses, ERP exclusions
MER_CONSERVATIVE_DEN = 13_756
MER_FORCED_MISSES = 25
ERP_OUT = ("govinfo-ERP-2026-table33", "govinfo-ERP-2026-table59")
SEC7 = "eia-pdf-sec7"


def tkey(t: dict) -> str:
    return f"{t['unit']}|{t.get('oracle_table_index', t['table_index']):05d}"


def pct(a: float, b: float) -> float | None:
    return round(100 * a / b, 2) if b else None


# ---- integrity -----------------------------------------------------------------------------------


def module_hashes() -> dict[str, str]:
    """Every repo module this process imported, plus the owner's recall script and the pins."""
    out = {}
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", None)
        if not f:
            continue
        p = Path(f).resolve()
        if REPO in p.parents and ".venv" not in p.parts:
            out[p.relative_to(REPO).as_posix()] = freeze.digest(p.relative_to(REPO).as_posix())
    for p in (PDF_RECALL, PINS):
        out[p.relative_to(REPO).as_posix()] = freeze.digest(p.relative_to(REPO).as_posix())
    return dict(sorted(out.items()))


def dir_manifest(d: Path) -> dict[str, str]:
    return {
        p.relative_to(d).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(d.rglob("*"))
        if p.is_file()
    }


def check_eval_freeze(baseline: Path, candidate: Path, cand_manifest: str | None) -> dict:
    ef = json.loads(EVAL_FREEZE.read_text(encoding="utf-8"))
    now = module_hashes()
    bad = sorted(
        k
        for k in set(now) | set(ef["evaluator_modules"])
        if now.get(k) != ef["evaluator_modules"].get(k)
    )
    assert not bad, f"evaluator module set differs from eval_freeze.json: {bad}"
    assert (ef["bootstrap"]["seed"], ef["bootstrap"]["B"], ef["bootstrap"]["ci_level"]) == (
        SEED,
        BOOT_B,
        CI_LEVEL,
    ), "bootstrap parameters differ from eval_freeze.json"
    got = dir_manifest(baseline)
    assert got == ef["parsed_fresh_manifest"], "data/parsed_fresh/ differs from its manifest"
    out = {"eval_freeze_sha256": freeze.digest(EVAL_FREEZE.relative_to(REPO).as_posix())}
    if cand_manifest:
        cm = json.loads((REPO / cand_manifest).read_text(encoding="utf-8"))
        assert dir_manifest(candidate) == cm["files"], "candidate differs from its manifest"
        out["candidate_manifest_sha256"] = freeze.digest(cand_manifest)
    return out


# ---- table lists ---------------------------------------------------------------------------------


def pilot_manifest() -> dict[str, str]:
    out = {}
    for line in (REPO / "data" / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line) if line.strip() else {}
        if rec.get("record") == "unit":
            out[rec["unit_id"]] = rec["source"]
    return out


def burned_lists() -> dict:
    """Step 0's split on the oracle as frozen at c6c8724; no clause (b)."""
    cells = [json.loads(x) for x in (orc.OUT / "cells.jsonl").open(encoding="utf-8")]
    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for c in cells:
        if c["admitted"] and c.get("family") != "STEO":
            groups[(c["unit"], c["table_index"])].append(c)
    src = pilot_manifest()
    tables = []
    for (unit, ti), cs in sorted(groups.items()):
        fam = (
            "tuning"
            if (unit, cs[0]["page"]) in TUNING
            else ("ERP" if "ERP" in unit else "MER held-out")
        )
        tables.append(
            {
                "family": fam,
                "unit": unit,
                "source": src[unit],
                "table_index": ti,
                "page": cs[0]["page"],
                "table_id": cs[0]["table_id"],
                "cells": cs,
                "forced": [],
            }
        )
    admitted, info = ss.load_oracle()
    for ti, d in sorted(info.items()):
        tables.append(
            {
                "family": "STEO",
                "unit": ss.UNIT,
                "source": "eia",
                "table_index": ti,
                "page": d["page"],
                "table_id": d["table_id"],
                "rows": d["rows"],
                "cells": admitted.get(ti, []),
                "forced": [],
            }
        )
    return {
        "families": ("MER held-out", "ERP", "STEO", "tuning"),
        "tables": tables,
        "steo_pdf": steo.HELD_PDF,
        "units": {
            "MER held-out": sorted(orc.MER_UNITS),
            "ERP": sorted(orc.ERP_UNITS),
            "STEO": [ss.UNIT],
            "tuning": ["eia-pdf-sec3", "eia-pdf-sec4"],
        },
        "source_of": src,
        "denominators_asserted": {},
    }


def fresh_lists(base_dir: Path) -> dict:
    """The freeze-pinned lists (read only after assert_frozen)."""
    tlist = json.loads((FRESH / "admission" / "tables.json").read_text(encoding="utf-8"))
    by_t: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for name in ("mer_cells.jsonl", "erp_cells.jsonl"):
        for line in (FRESH / "admission" / name).open(encoding="utf-8"):
            c = json.loads(line)
            by_t[(c["unit"], c["table_index"])].append(c)
    tables = []
    sec7_rows = []
    for t in tlist:
        cs = by_t.get((t["unit"], t["table_index"]), [])
        a6 = [c for c in cs if c["admitted"]]
        if t["unit"] == SEC7:  # owner: sec7 image-only, out; only an empty row may be dropped
            assert not a6, f"{SEC7} has admitted cells"
            sec7_rows.append(t["table_id"])
            continue
        if t["family"] == "MER":
            plain = [c for c in a6 if c.get("admitted_b")]
            forced = [c for c in a6 if not c.get("admitted_b")]
        else:
            plain, forced = a6, []
        tables.append(
            {
                "family": t["family"],
                "unit": t["unit"],
                "source": "eia" if t["family"] == "MER" else "govinfo_erp",
                "table_index": t["table_index"],
                "page": t["page"],
                "table_id": t["table_id"],
                "undetected": bool(t.get("undetected")),
                "cells": plain,
                "forced": forced,
            }
        )
    # STEO: every aug26 table with >= 1 admitted cell; printed rows re-derived by the FROZEN rule
    steo_cells: dict[int, list[dict]] = defaultdict(list)
    for line in (FRESH / "steo" / "cells.jsonl").open(encoding="utf-8"):
        c = json.loads(line)
        steo_cells[c["table_index"]].append(c)
    steo.HELD_PDF = RAW_FRESH / "eia" / f"{FRESH_STEO_UNIT}.pdf"  # in-process, as fresh_oracle.py
    bdoc = json.loads((base_dir / f"{FRESH_STEO_UNIT}.json").read_text(encoding="utf-8"))
    for ti, cs in sorted(steo_cells.items()):
        adm = [c for c in cs if c["admitted"]]
        if not adm:
            continue
        page, tid = cs[0]["page"], cs[0]["table_id"]
        res = steo.admit_table_rows(FRESH_STEO_UNIT, ti, page, tid, steo_footnotes.view_of(tid))
        same = [json.dumps(c, sort_keys=True) for c in res["cells"]] == [
            json.dumps(c, sort_keys=True) for c in cs
        ]
        assert same, f"STEO {tid} p{page}: the frozen rule no longer reproduces the frozen cells"
        on_page = [
            i
            for i, t in enumerate(bdoc["tables"])
            if t.get("prov") and t["prov"][0]["page_no"] == page
        ]
        tables.append(
            {
                "family": "STEO",
                "unit": FRESH_STEO_UNIT,
                "source": "eia",
                "oracle_table_index": ti,
                # the parse's TableItem on the oracle page; several -> the lowest index (recorded)
                "table_index": on_page[0] if on_page else None,
                "tableitems_on_page": len(on_page),
                "page": page,
                "table_id": tid,
                "rows": res["rows"],
                "cells": adm,
                "forced": [],
            }
        )
    mer = [t for t in tables if t["family"] == "MER"]
    erp = [t for t in tables if t["family"] == "ERP"]
    den = sum(len(t["cells"]) + len(t["forced"]) for t in mer)
    forced = sum(len(t["forced"]) for t in mer)
    assert den == MER_CONSERVATIVE_DEN, f"MER conservative denominator {den} != 13,756"
    assert forced == MER_FORCED_MISSES, f"MER forced misses {forced} != 25"
    for t in erp:
        if t["unit"] in ERP_OUT:
            assert not t["cells"], f"{t['unit']} has admitted cells"
    erp_units = sorted({t["unit"] for t in erp if t["unit"] not in ERP_OUT})
    mer_units = sorted({t["unit"] for t in mer})
    return {
        "families": ("MER", "ERP", "STEO"),
        "tables": [t for t in tables if t["unit"] not in ERP_OUT],
        "steo_pdf": steo.HELD_PDF,
        "units": {"MER": mer_units, "ERP": erp_units, "STEO": [FRESH_STEO_UNIT]},
        "source_of": {
            **{u: "eia" for u in mer_units + [FRESH_STEO_UNIT]},
            **{u: "govinfo_erp" for u in erp_units},
        },
        "sec7_rows_dropped": sec7_rows,
        "erp_excluded": list(ERP_OUT),
        "denominators_asserted": {
            "MER_conservative": den,
            "MER_forced_misses": forced,
            "MER_plain": den - forced,
        },
    }


# ---- scoring -------------------------------------------------------------------------------------


def load_doc(d: Path, unit: str, cache: dict) -> dict | None:
    key = (str(d), unit)
    if key not in cache:
        p = d / f"{unit}.json"
        cache[key] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    return cache[key]


def all_miss(t: dict, why: str) -> tuple[dict, list]:
    cs = t["cells"]
    if t["family"] == "STEO":
        hcols = len({c["period"] for c in cs})
    else:
        hcols = len({(c["col"], c["band"], c["header"]) for c in cs})
    det = [{"cell": c, "outcome": why, "r": None, "j": None} for c in cs]
    return {
        "cells": len(cs),
        "strict": 0,
        "lenient": 0,
        "missing_row": len(cs),
        "missing_col": 0,
        "header_cols": hcols,
        "header_matched": 0,
        "unscorable": why,
    }, det


def score_side(lists: dict, d: Path, base_dir: Path, pgs: dict, docs: dict) -> dict:
    """{table key: (result, detail)} for one parse directory. Page geometry ``pgs`` is read from
    the BASELINE parse's TableItem (the bbox the oracle's bands were measured in) and shared."""
    out = {}
    for t in lists["tables"]:
        key = f"{t['unit']}|{t.get('oracle_table_index', t['table_index'])}"
        doc = load_doc(d, t["unit"], docs)
        ti = t["table_index"]
        if doc is None:
            out[key] = all_miss(t, "unit missing (emitter crash)")
            continue
        if ti is None or ti >= len(doc.get("tables", [])):
            out[key] = all_miss(t, "no TableItem")
            continue
        detail: list = []
        if t["family"] == "STEO":
            res = ss.score_table(doc["tables"][ti], t["page"], t["rows"], t["cells"], detail)
            res["header_cols"] = res["periods"]
        else:
            if key not in pgs:
                bdoc = load_doc(base_dir, t["unit"], docs)
                pgs[key] = orc.read_page(t["unit"], t["source"], ti, bdoc)
            res = osc.score_table(pgs[key], doc["tables"][ti], t["cells"], detail)
        out[key] = (res, detail)
    return out


def flips(lists: dict, base: dict, cand: dict) -> dict:
    per: dict[str, Counter] = defaultdict(Counter)
    for t in lists["tables"]:
        key = f"{t['unit']}|{t.get('oracle_table_index', t['table_index'])}"
        bd, nd = base[key][1], cand[key][1]
        assert len(bd) == len(nd), key
        fam = t["family"]
        for b, n in zip(bd, nd, strict=True):
            per[fam]["cells"] += 1
            if b["outcome"] != "strict":
                continue
            per[fam]["baseline_correct"] += 1
            if n["outcome"] == "strict":
                continue
            if n["outcome"] == "wrong" and b["cell"]["value"] in guards.norm_value(
                n.get("text", ""), "v1"
            ):
                per[fam]["flip_character_level"] += 1
            else:
                per[fam]["flip_value"] += 1
    return {f: {**v, "flip_value_pct": pct(v["flip_value"], v["cells"])} for f, v in per.items()}


def bootstrap(keyed_rows: list[tuple[str, int, int]]) -> dict:
    """Table-level resampling (with replacement) of the cell-pooled rate; 95 % percentile CI.
    Tables are sorted by key first, so the CI depends on the table set, not on list order."""
    rows = [(a, b) for _, a, b in sorted(keyed_rows) if b]
    if not rows:
        return {"lo": None, "hi": None, "tables": 0}
    rng = random.Random(SEED)
    n = len(rows)
    stats = []
    for _ in range(BOOT_B):
        s = rng.choices(rows, k=n)
        stats.append(100 * sum(a for a, _ in s) / sum(b for _, b in s))
    stats.sort()
    a = (1 - CI_LEVEL) / 2
    lo = stats[int(a * (BOOT_B - 1))]
    hi = stats[min(BOOT_B - 1, int(round((1 - a) * (BOOT_B - 1))))]
    return {"lo": round(lo, 2), "hi": round(hi, 2), "tables": n, "B": BOOT_B, "seed": SEED}


def family_summary(lists: dict, side: dict, fam: str) -> dict:
    ts = [t for t in lists["tables"] if t["family"] == fam]
    s = Counter()
    for t in ts:
        r = side[f"{t['unit']}|{t.get('oracle_table_index', t['table_index'])}"][0]
        for k in ("cells", "strict", "lenient", "missing_row", "missing_col"):
            s[k] += r[k]
        s["header_cols"] += r["header_cols"]
        s["header_matched"] += r["header_matched"]
        s["forced"] += len(t["forced"])
    return {
        **s,
        "tables": len(ts),
        "strict_pct": pct(s["strict"], s["cells"]),
        "conservative_cells": s["cells"] + s["forced"],
        "conservative_strict_pct": pct(s["strict"], s["cells"] + s["forced"]),
        "lenient_pct": pct(s["lenient"], s["cells"]),
        "header_pct": pct(s["header_matched"], s["header_cols"]),
    }


def per_table(lists: dict, base: dict, cand: dict, logs: dict) -> list[dict]:
    rows = []
    for t in lists["tables"]:
        key = f"{t['unit']}|{t.get('oracle_table_index', t['table_index'])}"
        b, n = base[key][0], cand[key][0]
        rows.append(
            {
                "family": t["family"],
                "unit": t["unit"],
                "table_index": t["table_index"],
                "table_id": t["table_id"],
                "page": t["page"],
                "emit_status": logs.get((t["unit"], t["table_index"]), "?"),
                "cells": n["cells"],
                "forced_misses": len(t["forced"]),
                "strict_base": b["strict"],
                "strict": n["strict"],
                "strict_base_pct": pct(b["strict"], b["cells"]),
                "strict_pct": pct(n["strict"], n["cells"]),
                "conservative_strict_pct": pct(n["strict"], n["cells"] + len(t["forced"])),
                "header_base": f"{b['header_matched']}/{b['header_cols']}",
                "header": f"{n['header_matched']}/{n['header_cols']}",
                "row_nf": n["missing_row"],
                "col_nf": n["missing_col"],
                "unscorable": n.get("unscorable") or b.get("unscorable"),
            }
        )
    return rows


# ---- census, pins, clause-1 recall ---------------------------------------------------------------


def emit_logs(d: Path) -> dict[tuple[str, int], str]:
    out = {}
    for p in sorted((d / "_emit_log").glob("*.json")):
        lg = json.loads(p.read_text(encoding="utf-8"))
        for ti, v in lg["tables"].items():
            out[(lg["unit"], int(ti))] = v["status"]
    return out


def census(d: Path, units: list[str], logs: dict, nums) -> dict:
    tally: dict[str, Counter] = defaultdict(Counter)
    missing = []
    for unit in units:
        p = d / f"{unit}.json"
        if not p.exists():
            missing.append(unit)
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        for ti, tbl in enumerate(doc.get("tables", [])):
            body = [c for c in tbl["data"].get("table_cells", []) if is_body(c)]
            mb = sum(1 for c in body if len(nums(c.get("text", ""))) > 1)
            st = logs.get((unit, ti), "?")
            part = "rebuilt" if st == "rebuilt" else "not rebuilt"
            for k in ("all", part):
                tally[k]["tables"] += 1
                tally[k]["body"] += len(body)
                tally[k]["merged_body"] += mb
    out = {k: {**v, "rate_pct": pct(v["merged_body"], v["body"])} for k, v in tally.items()}
    out["units_missing"] = missing
    return out


def pins_check(d: Path) -> dict:
    pins = json.loads(PINS.read_text(encoding="utf-8"))
    units = sorted({k.split("|")[0] for k in pins})
    absent = [u for u in units if not (d / f"{u}.json").exists()]
    if absent:
        return {"identical": False, "absent_units": absent, "changed": None, "pins": len(pins)}
    changed = []
    for unit in units:
        tables = json.loads((d / f"{unit}.json").read_text(encoding="utf-8")).get("tables", [])
        for key in (k for k in pins if k.split("|")[0] == unit):
            ti = int(key.split("|")[1])
            got = hashlib.sha256(json.dumps(tables[ti], sort_keys=True).encode("utf-8")).hexdigest()
            if got != pins[key]:
                changed.append(key)
    return {"identical": not changed, "changed": changed, "pins": len(pins), "absent_units": []}


def clause1(parsed_dir: str) -> dict:
    """The owner's pdf_recall.py, localised to ``parsed_dir``, run in a temp dir (output kept in
    memory)."""
    with tempfile.TemporaryDirectory() as work:
        src = localise(PDF_RECALL.read_text(encoding="utf-8"), parsed_dir)
        (Path(work) / "pdf_recall.py").write_text(src, encoding="utf-8")
        run = subprocess.run(
            [sys.executable, "pdf_recall.py"],
            cwd=work,
            env=dict(os.environ, PYTHONUTF8="1"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert run.returncode == 0, f"pdf_recall.py failed on {parsed_dir}"
        res = json.loads((Path(work) / "pdf_results.json").read_text(encoding="utf-8"))
    return {
        f"{u}|{ti}": {"page": pg, "hit": hit, "on_page": tot, "recall_pct": pct(hit, tot)}
        for u, ti, pg, _d, _n, tot, hit, _m, _j, _e in res
    }


# ---- the run -------------------------------------------------------------------------------------


def run(args: argparse.Namespace) -> dict:
    freeze.assert_frozen()  # first, in every mode
    base_dir, cand_dir = REPO / args.baseline, REPO / args.candidate
    ev: dict = {
        "mode": args.oracle,
        "baseline": args.baseline,
        "candidate": args.candidate,
        "pilot_candidate": args.pilot_candidate,
        "bootstrap": {"B": BOOT_B, "seed": SEED, "ci": "95 % two-sided percentile, table-level"},
    }
    mirror = None
    try:
        if args.oracle == "fresh":
            ev["integrity"] = check_eval_freeze(base_dir, cand_dir, args.candidate_manifest)
            lists = fresh_lists(base_dir)
            # oracle.read_page reads <REPO>/data/raw/<source>/<unit>.pdf: a temp mirror of the
            # fresh PDFs (sha-checked copies), as fresh_admission.py does
            mirror = Path(tempfile.mkdtemp())
            for src in ("eia", "govinfo_erp"):
                (mirror / "data" / "raw" / src).mkdir(parents=True)
                for p in (RAW_FRESH / src).glob("*.pdf"):
                    shutil.copyfile(p, mirror / "data" / "raw" / src / p.name)
                    assert p.read_bytes() == (mirror / "data" / "raw" / src / p.name).read_bytes()
            orc.REPO = mirror
        else:
            lists = burned_lists()
            ev["burned_oracle_cells_sha256"] = hashlib.sha256(
                (orc.OUT / "cells.jsonl").read_bytes()
            ).hexdigest()
        ev["table_lists"] = {
            f: [
                {k: t.get(k) for k in ("unit", "table_index", "table_id", "page")}
                | {"cells": len(t["cells"]), "forced": len(t["forced"])}
                for t in lists["tables"]
                if t["family"] == f
            ]
            for f in lists["families"]
        }
        ev["denominators_asserted"] = lists["denominators_asserted"]
        for k in ("sec7_rows_dropped", "erp_excluded"):
            if k in lists:
                ev[k] = lists[k]
        ev["steo_tableitems_on_page"] = {
            f"{t['table_id']} p{t['page']}": t["tableitems_on_page"]
            for t in lists["tables"]
            if "tableitems_on_page" in t
        }
        docs: dict = {}
        pgs: dict = {}
        base = score_side(lists, base_dir, base_dir, pgs, docs)  # BASELINE first
        cand = score_side(lists, cand_dir, base_dir, pgs, docs)  # then the candidate
    finally:
        orc.REPO = freeze.REPO
        if mirror:
            shutil.rmtree(mirror, ignore_errors=True)
    logs = emit_logs(cand_dir)
    nums = owner_nums(PDF_RECALL.read_text(encoding="utf-8"))
    fl = flips(lists, base, cand)
    pins = pins_check(REPO / args.pilot_candidate)
    rec_base = clause1(args.pilot_baseline)
    rec_cand = clause1(args.pilot_candidate)
    recall_unchanged = all(
        rec_cand[k]["hit"] == v["hit"] and rec_cand[k]["on_page"] == v["on_page"]
        for k, v in rec_base.items()
    )
    ev["clause1_recall"] = {
        "baseline": rec_base,
        "candidate": rec_cand,
        "unchanged": recall_unchanged,
    }
    ev["budget_cbo_pins"] = pins
    # census by source over every unit in the candidate directory (A3(c): rung 1's definition)
    src_units: dict[str, list[str]] = defaultdict(list)
    man = pilot_manifest() if args.oracle == "burned" else lists["source_of"]
    for p in sorted(cand_dir.glob("*.json")):
        if not p.name.endswith(".meta.json") and p.stem in man:
            src_units[man[p.stem]].append(p.stem)
    ev["census_by_source"] = {
        s: {
            "baseline": census(base_dir, us, {}, nums)["all"],
            "candidate": census(cand_dir, us, logs, nums),
        }
        for s, us in sorted(src_units.items())
    }
    ev["families"] = {}
    for fam in lists["families"]:
        b = family_summary(lists, base, fam)
        n = family_summary(lists, cand, fam)
        ts = [t for t in lists["tables"] if t["family"] == fam]
        keyed = [
            (t, cand[f"{t['unit']}|{t.get('oracle_table_index', t['table_index'])}"][0]) for t in ts
        ]
        boot_plain = bootstrap([(tkey(t), r["strict"], r["cells"]) for t, r in keyed])
        boot_cons = bootstrap(
            [(tkey(t), r["strict"], r["cells"] + len(t["forced"])) for t, r in keyed]
        )
        cen_b = census(base_dir, lists["units"][fam], {}, nums)
        cen_n = census(cand_dir, lists["units"][fam], logs, nums)
        f = fl.get(fam, {})
        is_mer = fam.startswith("MER")
        gate_strict = n["conservative_strict_pct"] if is_mer else n["strict_pct"]
        census_rate = cen_n.get("all", {}).get("rate_pct")
        d039 = {
            "strict >= 95 % (" + ("conservative" if is_mer else "plain") + ")": (
                gate_strict is not None and gate_strict >= 95.0
            ),
            "header association >= in-run baseline": (
                n["header_pct"] is not None
                and b["header_pct"] is not None
                and n["header_pct"] >= b["header_pct"]
            ),
            "flips <= 0.5 %": (f.get("flip_value_pct") or 0.0) <= 0.5,
            "census <= 1.0 %": census_rate is not None and census_rate <= 1.0,
            "BUDGET/CBO manifest identical": bool(pins["identical"]),
            "clause-1 recall unchanged": recall_unchanged,
        }
        d038 = {
            "plain strict >= 95 %": n["strict_pct"] is not None and n["strict_pct"] >= 95.0,
            "flips <= 0.5 %": d039["flips <= 0.5 %"],
            "census <= 1.0 %": d039["census <= 1.0 %"],
            "BUDGET/CBO census and word conservation unchanged (byte-identical tables)": bool(
                pins["identical"]
            ),
            "header association (no threshold in D-038; reported)": n["header_pct"],
        }
        sections = {}
        if is_mer:
            for unit in lists["units"][fam]:
                us = [r for t, r in keyed if t["unit"] == unit]
                fo = sum(len(t["forced"]) for t in ts if t["unit"] == unit)
                cl = sum(r["cells"] for r in us)
                sk = sum(r["strict"] for r in us)
                sections[unit] = {
                    "cells": cl,
                    "forced": fo,
                    "strict_pct": pct(sk, cl),
                    "conservative_strict_pct": pct(sk, cl + fo),
                }
        ev["families"][fam] = {
            "baseline": b,
            "candidate": n,
            "bootstrap_plain": boot_plain,
            "bootstrap_conservative": boot_cons,
            "bootstrap_note": "unreliable (6 granules), not interpreted"
            if fam == "ERP" and args.oracle == "fresh"
            else "",
            "flips": f,
            "census_baseline": cen_b,
            "census_candidate": cen_n,
            "mer_sections": sections,
            "d039": d039,
            "d039_verdict": "PASS" if all(d039.values()) else "FAIL",
            "d038": d038,
            "d038_verdict": "PASS"
            if all(v for k, v in d038.items() if not k.startswith("header"))
            else "FAIL",
        }
    ev["per_table"] = per_table(lists, base, cand, logs)
    return ev


def render(ev: dict) -> str:
    L = [
        f"# Rung-1b evaluator output - mode `{ev['mode']}`",
        "",
        f"Baseline `{ev['baseline']}` (scored first) · candidate `{ev['candidate']}` · pilot "
        f"candidate `{ev['pilot_candidate']}` · bootstrap {ev['bootstrap']}.",
        "",
        "| family | tables | cells (plain / conservative) | strict base -> cand | conservative "
        "strict | 95 % CI | header base -> cand | flips | census base -> cand (rebuilt / not) "
        "| D-039 | D-038 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for fam, e in ev["families"].items():
        b, n = e["baseline"], e["candidate"]
        cn = e["census_candidate"]
        ci = e["bootstrap_conservative"] if fam.startswith("MER") else e["bootstrap_plain"]
        L.append(
            f"| {fam} | {n['tables']} | {n['cells']:,} / {n['conservative_cells']:,} | "
            f"{b['strict_pct']} -> **{n['strict_pct']}** | **{n['conservative_strict_pct']}** | "
            f"[{ci['lo']}, {ci['hi']}]{' (unreliable)' if e['bootstrap_note'] else ''} | "
            f"{b['header_pct']} -> {n['header_pct']} | {e['flips'].get('flip_value', 0)} "
            f"({e['flips'].get('flip_value_pct')} %) | "
            f"{e['census_baseline'].get('all', {}).get('rate_pct')} -> "
            f"{cn.get('all', {}).get('rate_pct')} ({cn.get('rebuilt', {}).get('rate_pct')} / "
            f"{cn.get('not rebuilt', {}).get('rate_pct')}) | **{e['d039_verdict']}** | "
            f"{e['d038_verdict']} |"
        )
    L.append("")
    for fam, e in ev["families"].items():
        L += [f"## {fam}", ""]
        L += [f"- D-039 · {k}: {'PASS' if v else 'FAIL'}" for k, v in e["d039"].items()]
        L += [f"- D-038 · {k}: {v}" for k, v in e["d038"].items()]
        if e["mer_sections"]:
            L += [
                "",
                "| section | cells | forced | strict | conservative strict |",
                "|---|---|---|---|---|",
            ]
            L += [
                f"| {u} | {s['cells']} | {s['forced']} | {s['strict_pct']} | "
                f"{s['conservative_strict_pct']} |"
                for u, s in e["mer_sections"].items()
            ]
        L.append("")
    L += [
        "## Per table",
        "",
        "| family | table | page | unit | emit | cells | forced | strict base | strict | "
        "cons. strict | header (base) | row NF | col NF | note |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in ev["per_table"]:
        L.append(
            f"| {r['family']} | {r['table_id']} | {r['page']} | `{r['unit']}` | {r['emit_status']} "
            f"| {r['cells']} | {r['forced_misses']} | {r['strict_base_pct']} | {r['strict_pct']} | "
            f"{r['conservative_strict_pct']} | {r['header']} ({r['header_base']}) | "
            f"{r['row_nf']} | {r['col_nf']} | {r['unscorable'] or ''} |"
        )
    return "\n".join(L) + "\n"


def write_eval_freeze() -> int:
    """Before the build clock (owner status 2026-10-01 (1)): the comparator's manifest, this module
    set's hashes and the bootstrap parameters. Reads file BYTES of data/parsed_fresh/ (hashes
    only); scores nothing."""
    assert not EVAL_FREEZE.exists(), "eval_freeze.json exists; it is written once"
    body = {
        "note": "D-039 rung 1b: written before the build clock; checked by evaluate_1b.py --oracle "
        "fresh before it scores anything. Module hashes: text CRLF -> LF (freeze.digest); "
        "parsed_fresh: raw-byte sha256.",
        "bootstrap": {
            "seed": SEED,
            "B": BOOT_B,
            "ci_level": CI_LEVEL,
            "method": "percentile, "
            "table-level resampling with replacement, cell-pooled, tables sorted by key",
        },
        "evaluator_modules": module_hashes(),
        "parsed_fresh_manifest": dir_manifest(REPO / "data" / "parsed_fresh"),
    }
    EVAL_FREEZE.write_text(json.dumps(body, indent=1) + "\n", encoding="utf-8")
    print(
        f"eval_freeze.json: {len(body['evaluator_modules'])} modules, "
        f"{len(body['parsed_fresh_manifest'])} parsed_fresh files"
    )
    return 0


def main() -> int:
    if sys.argv[1:] == ["--write-eval-freeze"]:
        return write_eval_freeze()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--oracle", choices=("burned", "fresh"), required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--pilot-baseline", default="data/parsed")
    ap.add_argument("--pilot-candidate", required=True)
    ap.add_argument("--candidate-manifest", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = REPO / args.out
    tmp = out.with_name(out.name + ".tmp")
    try:
        assert not out.exists() and not tmp.exists(), f"{args.out} exists: one evaluation only"
        warnings.filterwarnings("ignore")
        logging.disable(logging.CRITICAL)
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            ev = run(args)
            body = json.dumps(ev, indent=1, default=str)
            md = render(ev)
        tmp.mkdir(parents=True)
        (tmp / "evaluation.json").write_text(body + "\n", encoding="utf-8")
        (tmp / "evaluation.md").write_text(md, encoding="utf-8")
        os.replace(tmp, out)  # the one write: the directory appears complete or not at all
    except BaseException as exc:  # noqa: BLE001 - type and file:line only (owner status (4))
        tb = traceback.extract_tb(exc.__traceback__)
        fr = tb[-1] if tb else None
        where = f"{Path(fr.filename).name}:{fr.lineno}" if fr else "?"
        sys.__stderr__.write(f"{type(exc).__name__} at {where}\n")
        return 1
    sys.__stdout__.write(f"written {args.out}/evaluation.json, evaluation.md\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
