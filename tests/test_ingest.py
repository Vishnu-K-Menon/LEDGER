"""T2 listing-stage tests (D-034). No network: frames are committed, GovInfo/EIA are exercised
through fixtures and fakes."""

import csv
from pathlib import Path

import pytest

from ledger.cli import main
from ledger.config import load_config
from ledger.ingest.draw import draw, draw_stratified, seeded
from ledger.ingest.frames import parse_frames, read_candidates_csv, write_candidates_csv
from ledger.ingest.manifest import (
    ManifestHeader,
    ManifestRow,
    ManualMismatch,
    check_manual_dir,
    read_manifest,
    unit_count,
    write_manifest,
)
from ledger.ingest.sources import PolicyMissing, load_sources

# ---- frames -----------------------------------------------------------------------------------


def test_frames_parse_10_per_year_40_distinct(repo_root: Path):
    rows = parse_frames(repo_root / "data" / "frames")
    per_year = {y: sum(1 for r in rows if r.frame_year == y) for y in (2023, 2024, 2025, 2026)}
    assert per_year == {2023: 10, 2024: 10, 2025: 10, 2026: 10}
    assert len({r.publication_id for r in rows}) == 40
    assert all(r.date_issued.startswith(str(r.frame_year)) for r in rows)
    assert all(r.page_url.startswith("https://www.cbo.gov/publication/") for r in rows)


def test_candidates_csv_roundtrip(repo_root: Path, tmp_path: Path):
    rows = parse_frames(repo_root / "data" / "frames")
    p = tmp_path / "c.csv"
    write_candidates_csv(rows, p)
    assert read_candidates_csv(p) == rows


# ---- sources.yaml, stage-aware ---------------------------------------------------------------


def _sources(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "sources.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_sources_null_policy_warns_at_list_fails_at_fetch(tmp_path: Path, caplog):
    p = _sources(
        tmp_path, "cbo:\n  fetch_method: manual\n  policy_url: null\n  policy_note: null\n"
    )
    with caplog.at_level("WARNING"):
        load_sources(p, stage="list")
    assert "policy_url is null" in caplog.text
    with pytest.raises(PolicyMissing):
        load_sources(p, stage="fetch")


def test_sources_note_counts_as_confirmation(tmp_path: Path):
    p = _sources(
        tmp_path,
        "cbo:\n  fetch_method: manual\n  policy_url: null\n"
        '  policy_note: "no agency page; basis 17 U.S.C. 105"\n',
    )
    assert not load_sources(p, stage="fetch")["cbo"].policy_missing


# ---- manual CBO second hop -------------------------------------------------------------------


def _manual(tmp_path: Path, rows, files):
    d = tmp_path / "cbo"
    d.mkdir()
    with (d / "sources.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["filename", "url", "date_issued", "title"])
        w.writerows(rows)
    for f in files:
        (d / f).write_bytes(b"%PDF-1.4 stub")
    return d


def test_manual_row_without_file_raises(tmp_path: Path):
    d = _manual(tmp_path, [["a.pdf", "https://x/a.pdf", "2025-12-01", "A"]], [])
    with pytest.raises(ManualMismatch, match="rows without a file"):
        check_manual_dir(d)


def test_manual_file_without_row_raises(tmp_path: Path):
    d = _manual(tmp_path, [["a.pdf", "https://x/a.pdf", "2025-12-01", "A"]], ["a.pdf", "b.pdf"])
    with pytest.raises(ManualMismatch, match="files without a row"):
        check_manual_dir(d)


def test_manual_consistent_passes(tmp_path: Path):
    d = _manual(tmp_path, [["a.pdf", "https://x/a.pdf", "2025-12-01", "A"]], ["a.pdf"])
    assert len(check_manual_dir(d)) == 1


# ---- seeded draw -------------------------------------------------------------------------------


def test_same_seed_identical_draw(repo_root: Path, base_config_path: Path):
    seed = load_config(base_config_path).corpus.selection_seed
    rows = parse_frames(repo_root / "data" / "frames")
    a = draw_stratified(
        rows, 1, seeded(seed, "cbo"), stratum=lambda c: c.frame_year, key=lambda c: c.publication_id
    )
    b = draw_stratified(
        list(reversed(rows)),  # listing order must not matter
        1,
        seeded(seed, "cbo"),
        stratum=lambda c: c.frame_year,
        key=lambda c: c.publication_id,
    )
    assert a == b and len(a) == 4 and {c.frame_year for c in a} == {2023, 2024, 2025, 2026}
    assert draw(list("abcdefgh"), 3, seeded(seed, "x"), key=str) == draw(
        list("hgfedcba"), 3, seeded(seed, "x"), key=str
    )


# ---- CLI guards --------------------------------------------------------------------------------


def test_fetch_without_draw_confirmed_errors():
    with pytest.raises(SystemExit) as exc:
        main(["ingest", "--stage", "fetch"])
    assert exc.value.code == 2


def test_all_only_on_parse_stage():
    with pytest.raises(SystemExit) as exc:
        main(["ingest", "--stage", "list", "--all", "--confirmed"])
    assert exc.value.code == 2


def test_parse_not_built_yet():
    with pytest.raises(NotImplementedError):
        main(["ingest", "--stage", "parse", "--limit", "20"])


# ---- D-001 stop counts units --------------------------------------------------------------------


def _row(i: int, kind: str) -> ManifestRow:
    return ManifestRow(
        unit_id=f"u{i}",
        source="govinfo_erp",
        parent_series="ERP",
        unit_kind=kind,
        fetch_method="govinfo",
        title=f"unit {i}",
        date_issued="2026-04-01",
        url="https://api.govinfo.gov/x",
        snapshot_date="2026-09-20",
    )


def test_d001_stop_counts_units(tmp_path: Path, base_config_path: Path):
    """One manifest row = one unit, granule or report; the header is not a unit."""
    cfg = load_config(base_config_path)
    rows = [
        _row(i, "granule" if i % 2 else "report") for i in range(cfg.ingest.confirm_after_units)
    ]
    header = ManifestHeader(
        selection_seed=1, snapshot_date="2026-09-20", frames={}, pilot_composition={"x": 20}
    )
    p = tmp_path / "manifest.jsonl"
    write_manifest(p, header, rows)
    h, r = read_manifest(p)
    assert h.selection_seed == 1
    assert unit_count(r) == cfg.ingest.confirm_after_units == 20
    assert unit_count(r) >= cfg.ingest.confirm_after_units  # the stop fires after the pilot
