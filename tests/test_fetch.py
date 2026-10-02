"""--stage fetch tests (D-034, owner decisions 2026-09-20). No network: a fake Fetcher writes
generated PDFs; CBO units are copied from a temp manual dir."""

import csv
import shutil
from pathlib import Path

import pytest
from pypdf import PdfWriter

from ledger.config import load_config
from ledger.ingest import fetch as fetch_mod
from ledger.ingest.fetch import ErpCheck, erp_self_containment, run_fetch
from ledger.ingest.manifest import ManifestHeader, ManifestRow, read_manifest, write_manifest

SOURCES_OK = """
cbo:
  fetch_method: manual
  policy_url: null
  policy_note: "17 U.S.C. 105"
eia:
  fetch_method: direct
  policy_url: https://www.eia.gov/about/copyrights_reuse.php
  policy_note: "public domain"
govinfo:
  fetch_method: api
  policy_url: https://www.govinfo.gov/about/policies
  policy_note: "17 U.S.C. 105"
"""


def _pdf(path: Path, pages: int = 3) -> None:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        w.write(fh)


class FakeFetcher:
    """Writes a generated PDF for every download; counts calls per host."""

    def __init__(self, pages: int = 3):
        self.pages = pages
        self.calls_by_host: dict[str, int] = {}
        self.urls: list[str] = []

    def download(self, url, dest, *, source, params=None):
        host = url.split("/")[2]
        self.calls_by_host[host] = self.calls_by_host.get(host, 0) + 1
        self.urls.append(url)
        _pdf(dest, self.pages)


def _row(uid, source, kind="report", url="https://api.govinfo.gov/x/pdf", date="2026-04-01", **kw):
    return ManifestRow(
        unit_id=uid,
        source=source,
        parent_series="S",
        unit_kind=kind,
        fetch_method="manual" if source == "cbo_manual" else "govinfo",
        title=f"T {uid}",
        date_issued=date,
        url=None if source == "cbo_manual" else url,
        snapshot_date="2026-09-20",
        **kw,
    )


@pytest.fixture
def repo(tmp_path: Path, base_config_path: Path):
    (tmp_path / "data" / "manual" / "cbo").mkdir(parents=True)
    (tmp_path / "data" / "sources.yaml").write_text(SOURCES_OK, encoding="utf-8")
    shutil.copy(base_config_path, tmp_path / "base.yaml")
    rows = [
        _row("cbo-1", "cbo_manual", date="2025-12-01"),
        _row("govinfo-B", "govinfo_budget", pages=21, pages_source="metadata"),
        _row(
            "govinfo-ERP-2026-table4",
            "govinfo_erp",
            "granule",
            package_id="ERP-2026",
            pages=6,
            pages_source="estimated",
        ),
    ]
    header = ManifestHeader(
        selection_seed=1, snapshot_date="2026-09-20", frames={}, pilot_composition={"x": 3}
    )
    write_manifest(tmp_path / "data" / "manifest.jsonl", header, rows)
    # manual csv with a BOM, as PowerShell writes it
    _pdf(tmp_path / "data" / "manual" / "cbo" / "cbo-1.pdf", 2)
    with (tmp_path / "data" / "manual" / "cbo" / "sources.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as fh:
        w = csv.writer(fh)
        w.writerow(["filename", "url", "date_issued", "title"])
        w.writerow(["cbo-1.pdf", "https://www.cbo.gov/system/files/x.pdf", "2025-12-01", "T"])
    return tmp_path


def _cfg(repo: Path):
    return load_config(repo / "base.yaml")


def test_fetch_fills_fields_and_makes_no_cbo_calls(repo: Path, monkeypatch):
    monkeypatch.setenv("GOVINFO_API_KEY", "k")
    monkeypatch.setattr(
        fetch_mod,
        "erp_self_containment",
        lambda uid, t, texts: ErpCheck(uid, "unjudgeable", "unjudgeable", "pass", "pass", {}),
    )
    f = FakeFetcher(pages=5)
    res = run_fetch(_cfg(repo), repo=repo, fetcher=f)
    _, rows = read_manifest(repo / "data" / "manifest.jsonl")
    by = {r.unit_id: r for r in rows}
    assert by["cbo-1"].url == "https://www.cbo.gov/system/files/x.pdf"
    assert by["cbo-1"].pages == 2 and by["cbo-1"].pages_source == "measured"
    assert (
        by["govinfo-B"].pages == 5 and by["govinfo-B"].pages_source == "measured"
    )  # 21 metadata -> measured
    assert by["govinfo-ERP-2026-table4"].pages_source == "measured"
    assert all(r.sha256 and len(r.sha256) == 64 for r in rows)
    assert all(r.policy_note for r in rows)
    assert "www.cbo.gov" not in f.calls_by_host and f.calls_by_host == {"api.govinfo.gov": 2}
    # blank pages have no text layer -> below threshold: noted, not dropped
    assert set(res.below_threshold) == {"cbo-1", "govinfo-B", "govinfo-ERP-2026-table4"}
    assert len(rows) == 3 and not res.erp_demoted


def test_fetch_is_idempotent(repo: Path, monkeypatch):
    monkeypatch.setenv("GOVINFO_API_KEY", "k")
    monkeypatch.setattr(
        fetch_mod,
        "erp_self_containment",
        lambda uid, t, texts: ErpCheck(uid, "pass", "pass", "pass", "pass", {}),
    )
    f = FakeFetcher()
    run_fetch(_cfg(repo), repo=repo, fetcher=f)
    first = f.calls_by_host.copy()
    res2 = run_fetch(_cfg(repo), repo=repo, fetcher=f)
    assert f.calls_by_host == first  # nothing re-downloaded
    assert {o.action for o in res2.outcomes} == {"reused"}


def test_erp_fail_demotes_without_redraw(repo: Path, monkeypatch):
    monkeypatch.setenv("GOVINFO_API_KEY", "k")
    monkeypatch.setattr(
        fetch_mod,
        "erp_self_containment",
        lambda uid, t, texts: ErpCheck(
            uid, "pass", "pass", "fail", "pass", {"carry_in": "continued"}
        ),
    )
    f = FakeFetcher()
    res = run_fetch(_cfg(repo), repo=repo, fetcher=f)
    header, rows = read_manifest(repo / "data" / "manifest.jsonl")
    assert res.erp_demoted
    erp = [r for r in rows if r.source == "govinfo_erp"]
    assert len(erp) == 1 and erp[0].unit_kind == "report" and erp[0].unit_id == "govinfo-ERP-2026"
    assert erp[0].url.endswith("/packages/ERP-2026/pdf") and erp[0].pages_source == "measured"
    assert header.pilot_composition == {"x": 3}  # intended mix unchanged


def test_manual_missing_row_or_file_or_date_mismatch(repo: Path, monkeypatch):
    monkeypatch.setenv("GOVINFO_API_KEY", "k")
    csv_path = repo / "data" / "manual" / "cbo" / "sources.csv"
    # date mismatch -> error, not overwrite
    csv_path.write_text(
        "﻿filename,url,date_issued,title\ncbo-1.pdf,https://x/x.pdf,2025-12-02,T\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="date_issued"):
        run_fetch(_cfg(repo), repo=repo, fetcher=FakeFetcher())
    # file without a row / row without a file -> ManualMismatch from check_manual_dir
    csv_path.write_text("﻿filename,url,date_issued,title\n", encoding="utf-8")
    with pytest.raises(Exception, match="files without a row"):
        run_fetch(_cfg(repo), repo=repo, fetcher=FakeFetcher())


def test_null_policy_hard_fails_at_fetch(repo: Path, monkeypatch):
    monkeypatch.setenv("GOVINFO_API_KEY", "k")
    (repo / "data" / "sources.yaml").write_text(
        "cbo:\n  fetch_method: manual\n  policy_url: null\n  policy_note: null\n", encoding="utf-8"
    )
    with pytest.raises(Exception, match="policy_url is null"):
        run_fetch(_cfg(repo), repo=repo, fetcher=FakeFetcher())


SEC7 = Path(__file__).resolve().parents[1] / "data" / "raw_fresh" / "eia" / "eia-pdf-sec7.pdf"


@pytest.mark.skipif(not SEC7.exists(), reason="sec7 is local data (gitignored)")
def test_image_only_measure_on_sec7():
    """The sec7 lesson: its data tables are printed as images. The MEASURE (pypdf, 2026-10-02):
    pages 3,5-7,9-11,13-15,17,19-27 carry 5-6 embedded images and 12-13 text-layer words (the
    running header/footer); the text pages carry no image and 72-562 words."""
    from ledger.ingest.fetch import page_measures

    m = page_measures(SEC7)
    assert len(m) == 32
    image_pages = [p.page for p in m if p.images]
    assert image_pages == [3, 5, 6, 7, 9, 10, 11, 13, 14, 15, 17, *range(19, 28)]
    assert all(p.images in (5, 6) and p.words in (12, 13) for p in m if p.images)
    assert all(p.words >= 72 for p in m if not p.images and p.page != 1)
    assert (m[0].images, m[0].words) == (0, 2)


def _fetch_cfg(**fetch):
    base = load_config()
    return base.model_copy(update={"fetch": base.fetch.model_copy(update=fetch)})


def test_image_only_thresholds_owner_values_and_null_guards():
    """D-034 status 2026-10-02: <= 20 words with >= 1 image; >= 25 % of pages. A null still loads
    and the functions that use it raise at the use site (the D-020 pattern)."""
    from ledger.ingest.fetch import PageMeasure, image_only_pages, image_only_unit

    base = load_config()
    assert base.fetch.image_only_page_max_words == 20
    assert base.fetch.image_only_unit_min_share == 0.25
    m = [
        PageMeasure(1, 6, 12),
        PageMeasure(2, 0, 200),
        PageMeasure(3, 1, 400),
        PageMeasure(4, 1, 20),
    ]
    assert image_only_pages(m, base) == [1, 4]  # <= 20 is inclusive; 0 images never count
    assert image_only_pages([PageMeasure(1, 0, 0)], base) == []  # a blank page is not image-only
    with pytest.raises(RuntimeError, match="image_only_page_max_words is null"):
        image_only_pages(m, _fetch_cfg(image_only_page_max_words=None))
    with pytest.raises(RuntimeError, match="image_only_unit_min_share is null"):
        image_only_unit(m, _fetch_cfg(image_only_unit_min_share=None))


@pytest.mark.skipif(not SEC7.exists(), reason="sec7 is local data (gitignored)")
def test_image_only_unit_rule_on_sec7():
    """sec7's measured values: 20 of 32 pages image-only (62.5 %) -> excluded."""
    from ledger.ingest.fetch import image_only_share, image_only_unit, page_measures

    m = page_measures(SEC7)
    assert image_only_share(m, load_config()) == (20, 32, 20 / 32)
    assert image_only_unit(m, load_config())


def test_image_only_unit_rule_keeps_a_1_of_33_unit():
    from ledger.ingest.fetch import PageMeasure, image_only_share, image_only_unit

    m = [PageMeasure(1, 2, 6)] + [PageMeasure(p, 1, 300) for p in range(2, 34)]
    assert image_only_share(m, load_config())[:2] == (1, 33)
    assert not image_only_unit(m, load_config())


def test_run_fetch_excludes_an_image_only_unit_and_is_idempotent(repo: Path, monkeypatch):
    """The exclusion goes through the manifest's existing mechanism (status EXCLUDED +
    status_note, as D-040), share recorded, no replacement draw. A second run adds no duplicate
    note and changes no row's status; an already-EXCLUDED row keeps its own note."""
    from ledger.ingest.fetch import PageMeasure

    monkeypatch.setenv("GOVINFO_API_KEY", "k")
    monkeypatch.setattr(
        fetch_mod,
        "erp_self_containment",
        lambda uid, t, texts: ErpCheck(uid, "pass", "pass", "pass", "pass", {}),
    )
    # govinfo-B: 2 of 3 pages image-only; every other unit: text pages only
    monkeypatch.setattr(
        fetch_mod,
        "page_measures",
        lambda path: (
            [PageMeasure(1, 3, 12), PageMeasure(2, 3, 12), PageMeasure(3, 0, 400)]
            if path.stem == "govinfo-B"
            else [PageMeasure(1, 1, 400), PageMeasure(2, 0, 300)]
        ),
    )
    header, rows = read_manifest(repo / "data" / "manifest.jsonl")
    rows[0].status, rows[0].status_note = "EXCLUDED", "D-040 (2026-10-01): earlier exclusion"
    write_manifest(repo / "data" / "manifest.jsonl", header, rows)

    f = FakeFetcher()
    res = run_fetch(_cfg(repo), repo=repo, fetcher=f)
    _, first = read_manifest(repo / "data" / "manifest.jsonl")
    by = {r.unit_id: r for r in first}
    assert res.image_only_excluded == ["govinfo-B"]
    assert by["govinfo-B"].status == "EXCLUDED"
    assert "2/3 = 66.7% image-only pages" in by["govinfo-B"].status_note
    assert "no replacement draw" in by["govinfo-B"].status_note
    assert by["govinfo-ERP-2026-table4"].status == "ACTIVE"
    assert by["cbo-1"].status_note == "D-040 (2026-10-01): earlier exclusion"
    assert len(first) == 3  # no replacement draw

    res2 = run_fetch(_cfg(repo), repo=repo, fetcher=f)
    _, second = read_manifest(repo / "data" / "manifest.jsonl")
    assert [r.model_dump() for r in second] == [r.model_dump() for r in first]
    assert res2.image_only_excluded == []
    for r in second:
        assert sum(n.startswith("fetch: image-only pages") for n in r.notes) == 1


def test_erp_self_containment_verdicts():
    texts = [
        "Table B-4. Percentage shares of gross domestic product, 1975-2025\n"
        "Year 1975 1980 1985\n1975 10.1 20.2 30.3",
        "1990 11.1 22.2 33.3\nSource: BEA",
    ]
    c = erp_self_containment("u", "Percentage shares of gross domestic product, 1975–2025", texts)
    assert (c.title_present, c.header_row, c.no_carry_in, c.no_run_off) == (
        "pass",
        "pass",
        "pass",
        "pass",
    )
    c2 = erp_self_containment(
        "u", "Other title", ["Table B-4—Continued\n1 2 3", "x continued on next page"]
    )
    assert c2.title_present == "fail" and c2.no_carry_in == "fail" and c2.no_run_off == "fail"
    assert erp_self_containment("u", "t", ["", ""]).title_present == "unjudgeable"
