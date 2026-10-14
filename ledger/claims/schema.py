"""Claim schemas (D15, D21). Citations are chunk IDs (D-005); no span offsets anywhere.

``Decomposition`` is the structured-output schema the decomposer requests (D-044 item 2);
``ClaimRecord`` is one row of ``data/t6_claims.jsonl``: every claim the decomposer returned, kept
or dropped by a code guard, with the reason."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Qualifiers(BaseModel):
    """The qualifiers a claim carries (D15). Empty string = the answer states none."""

    model_config = ConfigDict(extra="forbid")

    entity: str
    unit: str
    period: str


class DecomposedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    source_sentence_idx: int
    qualifiers: Qualifiers


class Decomposition(BaseModel):
    """What the decomposer returns for one answer."""

    model_config = ConfigDict(extra="forbid")

    claims: list[DecomposedClaim]


DropReason = Literal["number_not_in_answer", "sentence_index_out_of_range", "duplicate", "empty"]


class ClaimRecord(BaseModel):
    """One claims-file row. ``kept`` claims have ids ``<question_id>::c<nn>`` (in decomposer order
    after the guards); dropped ones ``<question_id>::x<nn>`` and a ``drop_reason``."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    question_id: str
    stratum: Literal["table", "prose"]
    text: str
    source_sentence_idx: int
    qualifiers: Qualifiers
    citations: list[str] = Field(default_factory=list)  # chunk IDs of the source sentence (D-005)
    kept: bool
    drop_reason: DropReason | None = None
    drop_detail: str = ""
