"""``data/manifest.jsonl`` — the corpus reproducibility record (D-034, D6 freeze).

Line 1 is a header record (selection seed, snapshot date, frame per source); every other line is
one unit (granule or report). The listing stage writes rows with ``sha256`` and
``text_layer_ratio`` null; ``--stage fetch`` fills them, measures ``pages`` from the file with
pypdf and flips ``pages_source`` from ``estimated``/``metadata`` to ``measured``.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

UnitKind = Literal["granule", "report"]
FetchMethod = Literal["direct", "govinfo", "manual"]
PagesSource = Literal["metadata", "estimated", "measured", "unknown"]


class ManifestHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record: Literal["header"] = "header"
    selection_seed: int
    snapshot_date: str  # the date "latest edition" was evaluated — one value per listing pass
    frames: dict[str, str]  # source -> frame actually used
    pilot_composition: dict[str, int]


class ManifestRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record: Literal["unit"] = "unit"
    unit_id: str  # stable, content-derived: <source>-<package/pub id>[-<granule id>]
    source: str
    parent_series: str
    unit_kind: UnitKind
    fetch_method: FetchMethod
    title: str
    date_issued: str | None
    url: str | None  # PDF url; CBO rows get it from data/manual/cbo/sources.csv at fetch
    page_url: str | None = None  # CBO publication page (the frame link)
    package_id: str | None = None
    granule_id: str | None = None
    pages: int | None = None
    pages_source: PagesSource = "unknown"
    text_layer_ratio: float | None = None  # filled at --stage fetch
    sha256: str | None = None  # filled at --stage fetch
    snapshot_date: str
    policy_url: str | None = None
    policy_note: str | None = None
    notes: list[str] = Field(default_factory=list)


def write_manifest(path: Path, header: ManifestHeader, rows: list[ManifestRow]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(header.model_dump_json() + "\n")
        for r in rows:
            fh.write(r.model_dump_json() + "\n")


def read_manifest(path: Path) -> tuple[ManifestHeader, list[ManifestRow]]:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    header = ManifestHeader.model_validate_json(lines[0])
    rows = [ManifestRow.model_validate_json(ln) for ln in lines[1:]]
    return header, rows


def unit_count(rows: list[ManifestRow]) -> int:
    """D-001's stop counts UNITS: one manifest row = one unit (granule or report)."""
    return sum(1 for r in rows if r.record == "unit")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ---- manual CBO second hop ------------------------------------------------------------------

MANUAL_CSV_FIELDS = ["filename", "url", "date_issued", "title"]


class ManualMismatch(RuntimeError):
    pass


def check_manual_dir(manual_dir: Path) -> list[dict[str, str]]:
    """``data/manual/cbo/sources.csv`` <-> files: FAIL LOUDLY on a row with no file or a file with
    no row (D-034). Returns the rows when consistent."""
    csv_path = manual_dir / "sources.csv"
    if not csv_path.exists():
        raise ManualMismatch(f"{csv_path} missing")
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != MANUAL_CSV_FIELDS:
            raise ManualMismatch(f"{csv_path}: columns must be {MANUAL_CSV_FIELDS}")
        rows = list(reader)
    listed = {r["filename"] for r in rows}
    present = {p.name for p in manual_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"}
    missing_files = sorted(listed - present)
    orphan_files = sorted(present - listed)
    if missing_files or orphan_files:
        raise ManualMismatch(
            f"{manual_dir}: rows without a file {missing_files}; files without a row {orphan_files}"
        )
    return rows
