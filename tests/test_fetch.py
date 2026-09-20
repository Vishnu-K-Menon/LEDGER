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
