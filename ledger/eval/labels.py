"""Human claim labels (D-003): three classes, SUPPORTED / PARTIAL / UNSUPPORTED.

Two loaders, never one with a switch:

* ``load_pilot_labels`` - the T6 pilot (D-044 item 4). Accepts only ``set: "pilot"`` rows.
* ``load_paired_labels`` - the week-3 set (D-010): accepts only ``baseline`` / ``post_repair`` rows
  and refuses a set whose two halves do not share the same question ids. A pilot row is refused
  here: pilot labels are never pooled into the week-3 kappa (D-044 item 6(c)).

A pilot labels file is JSONL whose first line is the manifest (``{"manifest": true, ...}``, written
by the sampler, D-044 item 3); every other line is one claim slot, unlabelled (``label`` null)
until the owner labels it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Label = Literal["SUPPORTED", "PARTIAL", "UNSUPPORTED"]
LABELS: tuple[str, ...] = ("SUPPORTED", "PARTIAL", "UNSUPPORTED")
MissingElement = Literal["entity", "unit", "period", "label", "other"]
POSITIONS = (1, 2, 3, 4, 5)


class LabelsRefused(ValueError):
    pass


class PilotManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest: Literal[True]
    seed: int
    n: int = Field(ge=0)
    max_claims_per_answer: int
    claims_sha256: str
    sampler: str
    label_guide_sha256: str | None = None  # written by the label tool when labelling starts


class PilotSlot(BaseModel):
    """A sampled claim before labelling (D-044 item 3): ids committed before labelling starts."""

    model_config = ConfigDict(extra="forbid")

    set: Literal["pilot"]
    claim_id: str
    question_id: str
    stratum: Literal["table", "prose"]
    label: None = None


class _LabelFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    question_id: str
    stratum: Literal["table", "prose"]
    label: Label
    found_positions: list[int]  # SUPPORTED: where every element is; PARTIAL: where the value is
    unsure: bool
    missing_elements: list[MissingElement] = Field(default_factory=list)
    note: str = ""
    stands_alone: bool
    entailed_by_answer: bool
    assisted: Literal[False]  # the owner labels alone (D-043 status 2026-10-10, item 1)
    context_hash: str

    @model_validator(mode="after")
    def _consistent(self) -> _LabelFields:
        if any(p not in POSITIONS for p in self.found_positions):
            raise ValueError(f"found_positions must be within {POSITIONS}")
        if len(set(self.found_positions)) != len(self.found_positions):
            raise ValueError("found_positions has duplicates")
        if self.label in ("SUPPORTED", "PARTIAL") and not self.found_positions:
            raise ValueError(f"{self.label} needs the position(s) where it was found")
        if self.label == "UNSUPPORTED" and self.found_positions:
            raise ValueError("UNSUPPORTED records no found position")
        if self.label == "SUPPORTED" and self.missing_elements:
            raise ValueError("SUPPORTED has no missing element")
        if self.label == "PARTIAL":
            if not self.missing_elements:
                raise ValueError("PARTIAL needs the missing element(s)")
            if not self.note.strip():
                raise ValueError("PARTIAL needs a note (evaluation.md section 6)")
        if self.missing_elements and not self.note.strip():
            # D-043 status 2026-10-10: a missing unit/label/period cause says so in its note
            raise ValueError("a recorded cause needs a note")
        return self


class PilotLabel(_LabelFields):
    set: Literal["pilot"]


class PilotRelabel(_LabelFields):
    """Item 6(a)'s blinded relabel, written to its own file; the first label is never shown."""

    set: Literal["pilot_relabel"]


class PairedLabel(BaseModel):
    """Week-3 label (D-010, D-027). Pairing branch is written when the pair is selected (T13)."""

    model_config = ConfigDict(extra="forbid")

    set: Literal["baseline", "post_repair"]
    claim_id: str
    question_id: str
    label: Label
    assisted: Literal[False]
    branch: str | None = None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(ln) for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()
    ]


def _set_of(row: dict[str, Any]) -> Any:
    return row.get("set")


def split_manifest(rows: list[dict[str, Any]]) -> tuple[PilotManifest, list[dict[str, Any]]]:
    if not rows or not rows[0].get("manifest"):
        raise LabelsRefused("pilot labels file must start with the sampler's manifest line")
    return PilotManifest.model_validate(rows[0]), rows[1:]


def load_pilot_file(
    path: Path,
) -> tuple[PilotManifest, list[PilotSlot | PilotLabel]]:
    """Manifest + every row, labelled or not. Refuses any non-pilot row and duplicate ids."""
    manifest, body = split_manifest(read_jsonl(path))
    out: list[PilotSlot | PilotLabel] = []
    for row in body:
        if _set_of(row) != "pilot":
            raise LabelsRefused(
                f"{row.get('claim_id')}: set {_set_of(row)!r} is not a pilot row (D-044 item 6(c))"
            )
        out.append(PilotSlot.model_validate(row) if row.get("label") is None else PilotLabel(**row))
    ids = [r.claim_id for r in out]
    if len(set(ids)) != len(ids):
        raise LabelsRefused("duplicate claim ids in the pilot labels file")
    if len(out) != manifest.n:
        raise LabelsRefused(f"manifest n = {manifest.n} but the file has {len(out)} rows")
    return manifest, out


def load_pilot_labels(path: Path) -> tuple[PilotManifest, list[PilotLabel]]:
    """The labelled pilot set: every row labelled, or refused."""
    manifest, rows = load_pilot_file(path)
    unlabelled = [r.claim_id for r in rows if not isinstance(r, PilotLabel)]
    if unlabelled:
        raise LabelsRefused(f"{len(unlabelled)} rows are not labelled (first: {unlabelled[0]})")
    return manifest, [r for r in rows if isinstance(r, PilotLabel)]


def load_relabels(path: Path) -> list[PilotRelabel]:
    rows = read_jsonl(path)
    for row in rows:
        if _set_of(row) != "pilot_relabel":
            raise LabelsRefused(f"{row.get('claim_id')}: not a pilot_relabel row")
    return [PilotRelabel(**r) for r in rows]


def load_paired_labels(path: Path) -> list[PairedLabel]:
    """D-010: refuses anything but baseline / post_repair rows, and unpaired halves."""
    rows = read_jsonl(path)
    for row in rows:
        if _set_of(row) not in ("baseline", "post_repair"):
            raise LabelsRefused(
                f"{row.get('claim_id')}: set {_set_of(row)!r} cannot enter the week-3 set "
                "(D-010; pilot labels are never pooled, D-044 item 6(c))"
            )
    labels = [PairedLabel.model_validate(r) for r in rows]
    halves: dict[str, list[str]] = {"baseline": [], "post_repair": []}
    for lab in labels:
        halves[lab.set].append(lab.question_id)
    for name, qids in halves.items():
        if len(set(qids)) != len(qids):
            raise LabelsRefused(f"{name} half has more than one label for a question (D-010)")
    if set(halves["baseline"]) != set(halves["post_repair"]):
        raise LabelsRefused("the two halves do not share the same question ids (D-010)")
    return labels


def binary(label: str, partial_to: str = "UNSUPPORTED") -> str:
    """D-003 fold: the headline folds PARTIAL into UNSUPPORTED; the reverse is reported only."""
    if label not in LABELS:
        raise ValueError(f"unknown label {label!r}")
    if partial_to not in ("UNSUPPORTED", "SUPPORTED"):
        raise ValueError("partial_to must be UNSUPPORTED or SUPPORTED")
    return partial_to if label == "PARTIAL" else label
