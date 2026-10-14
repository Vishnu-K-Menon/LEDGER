"""T6 attachment-error panel (D-044 item 10). The owner writes about 14 claims by hand from the
run-1 answers' supplied chunks: a supported claim with its period or its row swapped, so the value
stays in the chunk but is attached to the wrong period or row. The panel is constructed: it is
scored under both modes in part B and reported per verifier and mode, outside kappa, the
readability gate and every outcome rule (no labels loader accepts a ``panel`` row)."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError


class PanelRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    set: Literal["panel"]
    panel_id: str
    question_id: str  # whose five supplied chunks the claim is scored against
    claim: str
    swap: Literal["period", "row"]
    note: str
    constructed: Literal[True]


def load_panel(path: Path) -> list[PanelRow]:
    rows = [json.loads(ln) for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln]
    return [PanelRow.model_validate(r) for r in rows]


def validate_panel(
    path: Path, run1_question_ids: Iterable[str]
) -> tuple[list[PanelRow], list[str]]:
    """Rows and a list of problems (empty = valid)."""
    allowed = set(run1_question_ids)
    problems: list[str] = []
    try:
        rows = load_panel(path)
    except (ValidationError, json.JSONDecodeError) as exc:
        return [], [f"schema: {exc}"]
    ids = [r.panel_id for r in rows]
    if len(set(ids)) != len(ids):
        problems.append("duplicate panel_id")
    for r in rows:
        if r.question_id not in allowed:
            problems.append(f"{r.panel_id}: {r.question_id} is not a run-1 non-abstaining answer")
        if not r.claim.strip():
            problems.append(f"{r.panel_id}: empty claim")
    if not rows:
        problems.append("the panel is empty")
    return rows, problems


def summary(rows: Sequence[PanelRow]) -> str:
    kinds = {k: sum(r.swap == k for r in rows) for k in ("period", "row")}
    return (
        f"{len(rows)} constructed claims ({kinds['period']} period swaps, {kinds['row']} row swaps)"
    )
