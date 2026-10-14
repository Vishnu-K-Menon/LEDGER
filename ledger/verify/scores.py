"""The scorer's output schema (D-044 item 7): only P(supported) is stored as a score, for every
verifier; FAIL is a third value. Pure schema - no GPU import - so ``ledger pilot`` can read it.

``results/t6/scores.jsonl``: first line the manifest, then one row per (item, verifier, mode)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

Mode = Literal["concatenated", "per_chunk_max"]
MODES: tuple[str, ...] = ("concatenated", "per_chunk_max")


class ScoresManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest: Literal[True]
    labels_sha256: str
    panel_sha256: str
    part_a_sha256: str
    git_commit: str
    verifiers: dict[str, Literal["PASS", "NOT SCORED"]]
    revisions: dict[str, str]


class ScoreRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["claim", "panel"]
    item_id: str
    question_id: str
    verifier: str
    revision: str
    mode: Mode
    status: Literal["ok", "FAIL"]
    p_supported: float | None  # concatenated: the one P; per_chunk_max: max over the five
    per_chunk_p: list[float | None] | None = None  # per_chunk_max only
    parsed: list[str]  # Granite: parsed <score> text per call; MiniCheck: rank-1 tokens
    reason: str = ""
    context_hash: str
    n_doc_chunks: list[int] | None = None  # MiniCheck official path: must be 1 per call
    n_claim_sentences: int | None = None  # MiniCheck official path (NLTK)
    package_chunk_sha256: list[str] | None = None  # MiniCheck: hash of the text the package built

    @model_validator(mode="after")
    def _ok_has_p(self) -> ScoreRow:
        if self.status == "ok" and self.p_supported is None:
            raise ValueError("an ok row carries P(supported)")
        if self.status == "FAIL" and not self.reason:
            raise ValueError("a FAIL row says why")
        return self


def read_scores(path: Path) -> tuple[ScoresManifest, list[ScoreRow]]:
    rows = [json.loads(ln) for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln]
    if not rows or not rows[0].get("manifest"):
        raise ValueError(f"{path}: first line must be the scores manifest")
    return ScoresManifest.model_validate(rows[0]), [ScoreRow.model_validate(r) for r in rows[1:]]
