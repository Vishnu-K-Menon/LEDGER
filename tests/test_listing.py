"""Listing pass, pre-draw pdfLink rule — D-034 status 2026-09-20 (owner decisions closing T2),
item (2): a report-level unit needs a resolvable pdfLink at listing (the package's, or a single
granule's, as CRPT-118hrpt468 was resolved); packages without one are excluded BEFORE the draw.
No network: a fake GovInfo client."""

from __future__ import annotations

from pathlib import Path

import pytest

from ledger.config import load_config
from ledger.ingest import listing
from ledger.ingest.govinfo import GateReport, Granule, Package
from ledger.ingest.manifest import read_manifest


def _pkg(pid: str, pdf: str | None = None) -> Package:
    return Package(pid, f"T {pid}", "2026-01-01", "x", pages=10, pdf_link=pdf)


def _gr(pid: str, gid: str, pdf: str | None = None) -> Granule:
    return Granule(pid, gid, f"G {gid}", "PART", "2026-01-01", pdf_link=pdf)


class FakeGovInfo:
    """Packages and granules from tables; records every granule lookup."""

    def __init__(self, pkgs=(), granules=None, granule_pdf=None, crpt=()):
        self.pkgs = list(pkgs)
        self.g = granules or {}
        self.granule_pdf = granule_pdf or {}
        self.crpt = list(crpt)
        self.lookups: list[str] = []

    def __call__(self, *_a, **_k):  # stands in for the GovInfo constructor
        return self

    def published(self, collection, *_a, **_k):
        return self.crpt if collection == "CRPT" else self.pkgs

    def latest_per_series(self, pkgs):
        return pkgs

    def package_summary(self, p):
        return p

    def granules(self, p):
        self.lookups.append(p.package_id)
        return [Granule(**vars(g)) for g in self.g.get(p.package_id, [])]

    def granule_summary(self, g):
        g.pdf_link = self.granule_pdf.get(g.granule_id)
        return g

    def gate(self, source, pkgs, granules):
        return GateReport(source=source, unit_kind="report")

    def crpt_filter(self, sample):
        return list(sample), len(sample)


def test_package_pdflink_resolves():
    gi = FakeGovInfo()
    assert listing.report_pdf_link(gi, _pkg("A", "https://x/A.pdf")) == (
        "https://x/A.pdf",
        "package pdfLink",
    )
    assert gi.lookups == []  # no granule lookup when the package has its own pdfLink


def test_single_granule_pdflink_resolves_like_crpt_118hrpt468():
    gi = FakeGovInfo(granules={"C": [_gr("C", "C-FIRSTPART")]}, granule_pdf={"C-FIRSTPART": "g"})
    assert listing.report_pdf_link(gi, _pkg("C")) == ("g", "single granule C-FIRSTPART pdfLink")


@pytest.mark.parametrize(
    ("granules", "granule_pdf", "why"),
    [
        ([], {}, "0 granules"),
        ([_gr("T", "T-1", "a"), _gr("T", "T-2", "b")], {}, "2 granules"),
        ([_gr("T", "T-1")], {}, "single granule T-1 has no pdfLink"),
    ],
)
def test_unresolvable_package_is_not_drawable(granules, granule_pdf, why):
    gi = FakeGovInfo(granules={"T": granules}, granule_pdf=granule_pdf)
    link, how = listing.report_pdf_link(gi, _pkg("T"))
    assert link is None and why in how


def test_pkg_row_refuses_an_unresolved_url():
    with pytest.raises(ValueError, match="resolvable pdfLink"):
        listing._pkg_row(_pkg("T"), "govinfo_budget", "2026-10-01", None, None, (None, "none"))


def _repo(tmp_path: Path, mix: dict[str, int]) -> tuple[Path, object]:
    cfg = load_config()
    cfg = cfg.model_copy(update={"corpus": cfg.corpus.model_copy(update={"source_mix": mix})})
    (tmp_path / "data").mkdir()
    return tmp_path, cfg


def _offline(monkeypatch, fake: FakeGovInfo) -> None:
    monkeypatch.setenv("GOVINFO_API_KEY", "k")
    monkeypatch.setattr(listing, "GovInfo", fake)
    monkeypatch.setattr(listing, "load_sources", lambda *_a, **_k: {})
    monkeypatch.setattr(listing, "parse_frames", lambda *_a, **_k: [])
    monkeypatch.setattr(listing, "write_candidates_csv", lambda *_a, **_k: None)

    def _no_eia(*_a, **_k):
        raise RuntimeError("offline test: no EIA frame")

    monkeypatch.setattr(listing.eia_mod, "sitemap_lists", _no_eia)


def test_unresolvable_packages_are_excluded_before_the_draw(tmp_path: Path, monkeypatch):
    """BUDGET-2027-TAB's case: no package pdfLink, several granules without one. It never reaches
    the draw, so the seeded draw is over resolvable packages only and no row has url=None."""
    pkgs = [
        _pkg("BUDGET-2027-APP", "https://x/app.pdf"),
        _pkg("BUDGET-2027-TAB"),
        _pkg("BUDGET-2027-MSR", "https://x/msr.pdf"),
        _pkg("BUDGET-2027-ONE"),
    ]
    fake = FakeGovInfo(
        pkgs=pkgs,
        granules={
            "BUDGET-2027-TAB": [_gr("BUDGET-2027-TAB", f"T{i}") for i in range(3)],
            "BUDGET-2027-ONE": [_gr("BUDGET-2027-ONE", "ONE-1")],
        },
        granule_pdf={"ONE-1": "https://x/one-1.pdf"},
    )
    _offline(monkeypatch, fake)
    repo, cfg = _repo(tmp_path, {"govinfo_budget": 4})
    res = listing.run_listing(cfg, repo=repo, snapshot_date="2026-10-01")
    ids = [r.unit_id for r in res.rows]
    assert "govinfo-BUDGET-2027-TAB" not in ids and len(ids) == 3
    assert all(r.url for r in res.rows)
    one = next(r for r in res.rows if r.unit_id == "govinfo-BUDGET-2027-ONE")
    assert one.url == "https://x/one-1.pdf" and "single granule ONE-1" in one.notes[0]
    out = next(o for o in res.outcomes if o.source == "govinfo_budget")
    assert "BUDGET-2027-TAB" in out.extra["excluded before the draw (no resolvable pdfLink)"]
    _, rows = read_manifest(repo / "data" / "manifest.jsonl")
    assert [r.unit_id for r in rows] == ids


def test_crpt_pool_is_filtered_before_the_unit_draw(tmp_path: Path, monkeypatch):
    crpt = [_pkg("CRPT-1"), _pkg("CRPT-2"), _pkg("CRPT-3", "https://x/3.pdf")]
    fake = FakeGovInfo(
        crpt=crpt,
        granules={"CRPT-1": [_gr("CRPT-1", "C1-FIRSTPART")], "CRPT-2": []},
        granule_pdf={"C1-FIRSTPART": "https://x/c1.pdf"},
    )
    _offline(monkeypatch, fake)
    repo, cfg = _repo(tmp_path, {"govinfo_crpt": 3})
    res = listing.run_listing(cfg, repo=repo, snapshot_date="2026-10-01")
    assert sorted(r.unit_id for r in res.rows) == ["govinfo-CRPT-1", "govinfo-CRPT-3"]
    out = next(o for o in res.outcomes if o.source == "govinfo_crpt")
    assert "CRPT-2" in out.extra["excluded before the draw (no resolvable pdfLink)"]
