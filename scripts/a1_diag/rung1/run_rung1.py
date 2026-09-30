"""B5 emission: the frozen rung-1 emitter over every unit, fired tables only.

Re-runs the FROZEN trigger fresh on ``data/parsed`` (no cache) and asserts its fired list equals
A1's committed ``trigger_fired.json`` (sha256 c4373792...). Each fired table is rebuilt by
``emit.rebuild``; a fallback keeps TableFormer's table. Every other table dict is left untouched,
so its content is identical by construction (guard clause 3 checks it). Writes
``data/parsed_rung1/<unit>.json`` (never ``data/parsed``) and a per-table log; one unit per call
is allowed (``--units``) so no call runs long; a written unit is skipped unless ``--force``.

    uv run --with pdfplumber python scripts/a1_diag/rung1/run_rung1.py [--units U ...] [--summary]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import emit  # noqa: E402
import trigger as tg  # noqa: E402

REPO = emit.REPO
OUT = REPO / "data" / "parsed_rung1"
LOG = OUT / "_emit_log"
FIRED_SHA = "c43737920c44c7c2bf7084e187dc6f8f6ce21ce63993afd22166698ea3180419"


def fired_list() -> set[tuple[str, int]]:
    body = (REPO / "reports/a1_diag/rung1/trigger_fired.json").read_text(encoding="utf-8")
    assert hashlib.sha256(body.encode()).hexdigest() == FIRED_SHA, "trigger_fired.json changed"
    return {(u, t) for u, t in json.loads(body)}


# D-039: the emitter runs only on these manifest sources; every other unit's tables are copied
# unchanged (BUDGET/CBO outputs are hash-pinned by tests/test_budget_cbo_pinned.py)
SCOPE = frozenset({"eia", "govinfo_erp"})


def source_of(unit: str) -> str:
    for line in (REPO / "data" / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line) if line.strip() else {}
        if rec.get("unit_id") == unit:
            return rec["source"]
    raise KeyError(f"{unit}: not in data/manifest.jsonl")


def run_unit(unit: str, fired: set, covered: set, force: bool) -> dict:
    import pdfplumber

    dest = OUT / f"{unit}.json"
    log_path = LOG / f"{unit}.json"
    if dest.exists() and log_path.exists() and not force:
        return json.loads(log_path.read_text(encoding="utf-8"))
    doc = json.loads((emit.PARSED / f"{unit}.json").read_text(encoding="utf-8"))
    # the frozen trigger, fresh (its cache is bypassed): must reproduce A1's fired list
    tg.CACHE.joinpath(f"{unit}.json").unlink(missing_ok=True)
    fresh = {(r["unit"], r["table_index"]) for r in tg.run_unit(unit, covered) if r["fired"]}
    mine = {x for x in fired if x[0] == unit}
    assert fresh == mine, f"{unit}: trigger no longer reproduces A1's fired list"
    log: dict = {"unit": unit, "tables": {}}
    pdf_path = next((REPO / "data" / "raw").rglob(f"{unit}.pdf"))
    with pdfplumber.open(pdf_path) as pdf:
        in_scope = source_of(unit) in SCOPE
        for ti, tbl in enumerate(doc.get("tables", [])):
            if (unit, ti) not in fired:
                log["tables"][ti] = {"status": "not fired"}
                continue
            if not in_scope:  # D-039: BUDGET/CBO outputs stay byte-identical (hash-pinned)
                log["tables"][ti] = {"status": "out of scope (D-039)"}
                continue
            new, notes = emit.rebuild(tbl, emit.lines_for(doc, tbl, pdf))
            if new is None:
                log["tables"][ti] = {"status": "fallback", "notes": notes}
            else:
                doc["tables"][ti] = new
                log["tables"][ti] = {"status": "rebuilt", "notes": notes}
    OUT.mkdir(parents=True, exist_ok=True)
    LOG.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc), encoding="utf-8")
    log_path.write_text(json.dumps(log), encoding="utf-8")
    return log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--units", nargs="*")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()
    fired = fired_list()
    covered = tg.covered_tables()
    for unit in args.units or []:
        log = run_unit(unit, fired, covered, args.force)
        c = Counter(v["status"] for v in log["tables"].values())
        print(unit, dict(c))
    if args.summary:
        rows = json.loads((REPO / "reports/a1_diag/rung1/trigger_dryrun.json").read_text("utf-8"))
        fam = {(r["unit"], r["table_index"]): r["family"] for r in rows}
        tally: dict[str, Counter] = {}
        reasons: Counter = Counter()
        for p in sorted(LOG.glob("*.json")):
            log = json.loads(p.read_text(encoding="utf-8"))
            for ti, v in log["tables"].items():
                f = fam.get((log["unit"], int(ti)), "other")
                tally.setdefault(f, Counter())[v["status"]] += 1
                if v["status"] == "fallback":
                    reasons[v["notes"][-1].split(":")[0]] += 1
        out = {
            "by_family": {k: dict(v) for k, v in tally.items()},
            "fallback_reasons": dict(reasons),
        }
        (REPO / "reports/a1_diag/rung1/emit_summary.json").write_text(
            json.dumps(out, indent=1), encoding="utf-8"
        )
        print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
