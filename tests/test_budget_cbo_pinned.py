"""D-039: every BUDGET/CBO table output is byte-identical to its pinned sha256 (704 tables).

The emitter runs only on eia / govinfo_erp units; BUDGET/CBO tables must come through unchanged.
Local only: the parsed data is gitignored, so each directory that is absent is skipped and CI
(pytest + ruff, D-028) is unaffected.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PINS = json.loads((REPO / "tests" / "data" / "budget_cbo_tables_sha256.json").read_text("utf-8"))


def test_pin_count() -> None:
    assert len(PINS) == 704


@pytest.mark.parametrize("parsed_dir", ["data/parsed", "data/parsed_rung1", "data/parsed_rung1b"])
def test_budget_cbo_tables_match_pins(parsed_dir: str) -> None:
    root = REPO / parsed_dir
    units = sorted({key.split("|")[0] for key in PINS})
    if not all((root / f"{u}.json").exists() for u in units):
        pytest.skip(f"{parsed_dir}: BUDGET/CBO outputs not on disk (local data, gitignored)")
    changed = []
    for unit in units:
        doc = json.loads((root / f"{unit}.json").read_text(encoding="utf-8"))
        tables = doc.get("tables", [])
        for key in (k for k in PINS if k.split("|")[0] == unit):
            ti = int(key.split("|")[1])
            got = hashlib.sha256(json.dumps(tables[ti], sort_keys=True).encode("utf-8")).hexdigest()
            if got != PINS[key]:
                changed.append(key)
    assert not changed, f"{parsed_dir}: {len(changed)} BUDGET/CBO tables differ: {changed[:10]}"
