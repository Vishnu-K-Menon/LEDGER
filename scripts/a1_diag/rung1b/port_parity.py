"""D-039 port gate (owner status 2026-10-01): the production row fix (``ledger/ingest/rows.py``)
against the FROZEN rung-1b emitter, per-unit sha256.

* Pilot: all 19 units (``data/parsed`` + ``data/raw``) -> ``data/parsed_port/``; reference
  ``data/parsed_rung1b/`` (the frozen emitter's final pilot run). Every unit document and emit log
  must be byte-identical; the 77 burned oracle tables are also checked table by table; the 704
  BUDGET/CBO pins are checked on the ported output.
* Fresh: all 16 units (``data/parsed_fresh`` + ``data/raw_fresh``; MER included - parity tests
  code, not membership) -> ``data/parsed_fresh_port/``; reference ``data/parsed_fresh_rung1b/``
  (15 units, Part C) plus ``data/parsed_fresh_rung1b_sec7ref/`` (sec7, which Part C never emitted;
  produced here by the frozen ``run_rung1.py``, hashes checked against ``emitter_freeze.json``).

Writes ``reports/a1_diag/rung1b/port_parity.json``; exits 1 on any difference (STOP).

    uv run python scripts/a1_diag/rung1b/port_parity.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pdfplumber

from ledger.config import load_config
from ledger.ingest.rows import fix_document

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts" / "a1_diag" / "rung1b"))
import evaluate_1b as ev  # noqa: E402

FREEZE = REPO / "reports/a1_diag/rung1b/emitter_freeze.json"
SEC7_REF = REPO / "data/parsed_fresh_rung1b_sec7ref"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sources(manifest: Path) -> dict[str, str]:
    out = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line) if line.strip() else {}
        if rec.get("unit_id"):
            out[rec["unit_id"]] = rec["source"]
    return out


def frozen_ok() -> None:
    body = json.loads(FREEZE.read_text(encoding="utf-8"))
    for rel, h in body["files"].items():
        assert sha(REPO / rel) == h["sha256_raw"], f"{rel} changed since the emitter freeze"


def port(units: list[str], parsed: Path, raw: Path, manifest: Path, out: Path) -> None:
    cfg = load_config().parser.row_fix
    src = sources(manifest)
    (out / "_emit_log").mkdir(parents=True, exist_ok=True)
    for unit in units:
        doc = json.loads((parsed / f"{unit}.json").read_text(encoding="utf-8"))
        with pdfplumber.open(next(raw.rglob(f"{unit}.pdf"))) as pdf:
            log = fix_document(doc, pdf, src[unit], cfg)
        (out / f"{unit}.json").write_text(json.dumps(doc), encoding="utf-8")
        (out / "_emit_log" / f"{unit}.json").write_text(
            json.dumps({"unit": unit, "tables": log}), encoding="utf-8"
        )


def compare(units: list[str], got: Path, refs: dict[str, Path]) -> dict:
    rows = {}
    for unit in units:
        ref = refs[unit]
        for rel in (f"{unit}.json", f"_emit_log/{unit}.json"):
            a, b = sha(got / rel), sha(ref / rel)
            rows[rel] = {"port": a, "frozen": b, "identical": a == b, "frozen_dir": ref.name}
    return rows


def main() -> int:
    frozen_ok()
    pilot_units = sorted(p.stem for p in (REPO / "data/parsed_rung1b").glob("*.json"))
    assert len(pilot_units) == 19, pilot_units
    fresh_units = sorted(
        p.stem for p in (REPO / "data/parsed_fresh").glob("*.json") if ".meta" not in p.name
    )
    assert len(fresh_units) == 16, fresh_units
    # sec7's frozen reference (Part C emitted 15 units; sec7 was out)
    if not SEC7_REF.exists():
        run = subprocess.run(
            [
                sys.executable,
                str(REPO / "scripts/a1_diag/rung1/run_rung1.py"),
                *("--fired", "live", "--covered", "none"),
                *("--manifest", "data/manifest_fresh.jsonl", "--raw", "data/raw_fresh"),
                *("--parsed", "data/parsed_fresh", "--out", str(SEC7_REF)),
                *("--units", "eia-pdf-sec7"),
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        assert run.returncode == 0, "frozen emitter failed on sec7"
    frozen_ok()
    port(
        pilot_units,
        REPO / "data/parsed",
        REPO / "data/raw",
        REPO / "data/manifest.jsonl",
        REPO / "data/parsed_port",
    )
    port(
        fresh_units,
        REPO / "data/parsed_fresh",
        REPO / "data/raw_fresh",
        REPO / "data/manifest_fresh.jsonl",
        REPO / "data/parsed_fresh_port",
    )
    pilot = compare(
        pilot_units,
        REPO / "data/parsed_port",
        {u: REPO / "data/parsed_rung1b" for u in pilot_units},
    )
    fresh = compare(
        fresh_units,
        REPO / "data/parsed_fresh_port",
        {
            u: SEC7_REF if u == "eia-pdf-sec7" else REPO / "data/parsed_fresh_rung1b"
            for u in fresh_units
        },
    )
    # the 77 burned oracle tables, table by table
    lists = ev.burned_lists()
    burned_diff = []
    for t in lists["tables"]:
        u, ti = t["unit"], t["table_index"]
        a = json.loads((REPO / "data/parsed_port" / f"{u}.json").read_text("utf-8"))["tables"][ti]
        b = json.loads((REPO / "data/parsed_rung1b" / f"{u}.json").read_text("utf-8"))["tables"][ti]
        if json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True):
            burned_diff.append(f"{u}|{ti}")
    pins = ev.pins_check(REPO / "data/parsed_port")
    diffs = [k for k, v in {**pilot, **fresh}.items() if not v["identical"]]
    body = {
        "gate": "D-039 status 2026-10-01 port gate: ledger/ingest/rows.py vs the frozen emitter",
        "config": "configs/base.yaml parser.row_fix",
        "pilot_units": len(pilot_units),
        "fresh_units": len(fresh_units),
        "burned_tables_checked": len(lists["tables"]),
        "burned_tables_differing": burned_diff,
        "budget_cbo_pins": {k: v for k, v in pins.items() if k != "changed"}
        | {"changed": len(pins["changed"] or [])},
        "files": {"pilot": pilot, "fresh": fresh},
        "differences": diffs,
        "verdict": "IDENTICAL"
        if not diffs and not burned_diff and pins["identical"]
        else "DIFF - STOP",
    }
    out = REPO / "reports/a1_diag/rung1b/port_parity.json"
    out.write_text(json.dumps(body, indent=1) + "\n", encoding="utf-8")
    print(
        f"{body['verdict']}: pilot {len(pilot_units)} units, fresh {len(fresh_units)} units, "
        f"{len(pilot) + len(fresh)} files, {len(diffs)} differing; burned tables "
        f"{len(lists['tables'])} checked, {len(burned_diff)} differing; pins {pins['pins']} "
        f"identical={pins['identical']}"
    )
    return 0 if body["verdict"] == "IDENTICAL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
