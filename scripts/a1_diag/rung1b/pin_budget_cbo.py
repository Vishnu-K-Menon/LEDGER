"""D-039: write the sha256 pins of every BUDGET/CBO table output (704 tables) from ``data/parsed``.

Hash = sha256 of ``json.dumps(table, sort_keys=True)`` (``scripts/a1_diag/rung1/guards.py``'s
hashing). Pins go to ``tests/data/budget_cbo_tables_sha256.json``; the local test
``tests/test_budget_cbo_pinned.py`` checks ``data/parsed`` and ``data/parsed_rung1`` against them.

    uv run python scripts/a1_diag/rung1b/pin_budget_cbo.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "tests" / "data" / "budget_cbo_tables_sha256.json"


def main() -> int:
    pins: dict[str, str] = {}
    for path in sorted((REPO / "data" / "parsed").glob("*.json")):
        unit = path.stem
        if path.name.endswith(".meta.json") or not ("BUDGET" in unit or unit.startswith("cbo-")):
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        for ti, tbl in enumerate(doc.get("tables", [])):
            pins[f"{unit}|{ti}"] = hashlib.sha256(
                json.dumps(tbl, sort_keys=True).encode("utf-8")
            ).hexdigest()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(pins, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(pins)} BUDGET/CBO tables pinned -> {OUT.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
