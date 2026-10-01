"""A3 - the rung-1b evaluator dry-run on the BURNED tables only (owner status 2026-10-01 (2)).

Reads the evaluator outputs already written by ``evaluate_1b.py --oracle burned`` into
``reports/a1_diag/rung1b/dryrun/{a,c,c_repeat}/`` and checks:

(a) identity: ``data/parsed`` as baseline and candidate -> flips 0, header association diff 0;
(b) the baseline section reproduces step 0 within +-0.1 pp (strict MER 50.1 / ERP 55.1 / STEO
    86.5, header association 85.2 / 93.2 / 94.7) on the oracle as frozen at c6c8724;
(c) rung 1's output (``data/parsed_rung1/``) as candidate reproduces 158029a within +-0.1 pp
    (strict 88.7 / 92.5 / 95.8, header 89.5 / 97.7 / 78.6, value flips 0.05 / 0.00 / 0.28 %,
    census EIA 1.72 / ERP 2.34 %, clause-1 recall sec3 99.55 / sec11 99.70 %); the bootstrap runs
    and is deterministic (a second run is byte-identical; rung 1 reported no CI to compare);
(d) ``freeze.assert_frozen()`` refuses an altered copy of ``freeze.json`` (the real file is
    untouched and still passes).

Writes ``reports/a1_diag/rung1b/dryrun.log``; exits 1 on any failure (STOP).

    uv run python scripts/a1_diag/rung1b/dryrun_1b.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import freeze  # noqa: E402

REPO = freeze.REPO
D = REPO / "reports" / "a1_diag" / "rung1b" / "dryrun"
TOL = 0.1
STEP0 = {
    "MER held-out": (50.1, 85.2),
    "ERP": (55.1, 93.2),
    "STEO": (86.5, 94.7),
}
RUNG1 = {  # 158029a, reports/a1_diag/rung1/REPORT.md
    "MER held-out": (88.7, 89.5, 0.05),
    "ERP": (92.5, 97.7, 0.00),
    "STEO": (95.8, 78.6, 0.28),
}
RUNG1_CENSUS = {"eia": 1.72, "govinfo_erp": 2.34}
RUNG1_RECALL = {"eia-pdf-sec3|10": 99.55, "eia-pdf-sec11|3": 99.70}


def load(name: str) -> dict:
    return json.loads((D / name / "evaluation.json").read_text(encoding="utf-8"))


def near(got, want) -> bool:
    return got is not None and abs(got - want) <= TOL + 1e-9


def main() -> int:
    log: list[str] = []
    ok = True

    def check(label: str, cond: bool, detail: str) -> None:
        nonlocal ok
        ok &= bool(cond)
        log.append(f"[{'OK' if cond else 'FAIL'}] {label}: {detail}")

    a, c = load("a"), load("c")
    log.append(f"burned oracle cells.jsonl sha256 {c['burned_oracle_cells_sha256']}")
    log.append("")
    log.append("(a) identity - data/parsed as baseline and candidate")
    for fam, e in a["families"].items():
        f = e["flips"]
        hb, hc = e["baseline"]["header_pct"], e["candidate"]["header_pct"]
        check(
            f"(a) {fam}",
            f.get("flip_value", 0) == 0 and f.get("flip_character_level", 0) == 0 and hb == hc,
            f"flips {f.get('flip_value', 0)} / char {f.get('flip_character_level', 0)}; "
            f"header {hb} vs {hc}",
        )
    log.append("")
    log.append("(b) baseline section vs step 0 (+-0.1 pp), oracle as frozen at c6c8724")
    for run_name, ev in (("a", a), ("c", c)):
        for fam, (s0, h0) in STEP0.items():
            b = ev["families"][fam]["baseline"]
            check(
                f"(b) run {run_name} {fam}",
                near(b["strict_pct"], s0) and near(b["header_pct"], h0),
                f"strict {b['strict_pct']} (step 0 {s0}); header {b['header_pct']} (step 0 {h0}); "
                f"{b['tables']} tables, {b['cells']:,} cells",
            )
    log.append("")
    log.append("(c) data/parsed_rung1 as candidate vs 158029a (+-0.1 pp)")
    for fam, (s1, h1, f1) in RUNG1.items():
        e = c["families"][fam]
        n = e["candidate"]
        check(
            f"(c) {fam}",
            near(n["strict_pct"], s1)
            and near(n["header_pct"], h1)
            and near(e["flips"].get("flip_value_pct"), f1),
            f"strict {n['strict_pct']} ({s1}); header {n['header_pct']} ({h1}); value flips "
            f"{e['flips'].get('flip_value', 0)} = {e['flips'].get('flip_value_pct')} % ({f1}); "
            f"bootstrap CI [{e['bootstrap_plain']['lo']}, {e['bootstrap_plain']['hi']}] over "
            f"{e['bootstrap_plain']['tables']} tables",
        )
    for src, want in RUNG1_CENSUS.items():
        got = c["census_by_source"][src]["candidate"]["all"]["rate_pct"]
        check(f"(c) census {src}", near(got, want), f"{got} % (rung 1 {want} %)")
    for key, want in RUNG1_RECALL.items():
        got = c["clause1_recall"]["candidate"][key]["recall_pct"]
        check(f"(c) clause-1 recall {key}", near(got, want), f"{got} % (rung 1 {want} %)")
    same = (D / "c" / "evaluation.json").read_bytes() == (
        D / "c_repeat" / "evaluation.json"
    ).read_bytes()
    check("(c) bootstrap deterministic", same, "second run byte-identical" if same else "differs")
    log.append("")
    log.append("(d) assert_frozen() on an altered copy of freeze.json")
    real = freeze.FREEZE
    before = hashlib.sha256(real.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        alt = Path(tmp) / "freeze.json"
        shutil.copyfile(real, alt)
        body = json.loads(alt.read_text(encoding="utf-8"))
        rel = sorted(body["groups"]["admission"])[0]
        body["groups"]["admission"][rel] = "0" * 64
        alt.write_text(json.dumps(body, indent=1), encoding="utf-8")
        freeze.FREEZE = alt
        try:
            freeze.assert_frozen()
            refused = False
        except AssertionError:
            refused = True
        finally:
            freeze.FREEZE = real
    check("(d) altered copy refused", refused, f"admission:{rel} hash zeroed in a temp copy")
    after = hashlib.sha256(real.read_bytes()).hexdigest()
    try:
        freeze.assert_frozen()
        real_ok = True
    except AssertionError:
        real_ok = False
    check("(d) real freeze.json untouched and passing", before == after and real_ok, before)
    log.append("")
    log.append(f"VERDICT: {'ALL CHECKS PASS' if ok else 'FAIL - STOP'}")
    (REPO / "reports" / "a1_diag" / "rung1b" / "dryrun.log").write_text(
        "\n".join(log) + "\n", encoding="utf-8"
    )
    print("\n".join(log))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
