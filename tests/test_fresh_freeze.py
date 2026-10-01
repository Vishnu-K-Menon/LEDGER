"""D-039: the fresh oracle freeze holds (admission, checker, scan, manifests, exports).

Local only: the admission files and exports are gitignored data, so the test skips when they are
absent and CI (pytest + ruff, D-028) is unaffected.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FREEZE_PY = REPO / "scripts" / "a1_diag" / "rung1b" / "freeze.py"


def _freeze():
    spec = importlib.util.spec_from_file_location("freeze", FREEZE_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_fresh_oracle_is_frozen() -> None:
    fz = _freeze()
    if not fz.FREEZE.exists():
        pytest.skip("no freeze written yet")
    needed = [rel for files in fz.GROUPS.values() for rel in files]
    if not all((REPO / rel).exists() for rel in needed):
        pytest.skip("fresh admission data not on disk (local data, gitignored)")
    fz.assert_frozen()
