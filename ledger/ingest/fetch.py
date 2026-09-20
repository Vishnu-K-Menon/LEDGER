"""``ledger ingest --stage fetch --draw-confirmed`` (T2 second half, D-034).

Per manifest unit: obtain the PDF (GovInfo / EIA over HTTP through ``Fetcher``; CBO copied from
``data/manual/cbo/`` — cbo.gov is never fetched by script), then fill ``sha256``, ``pages``
(measured with pypdf, ``pages_source`` -> ``measured``), ``text_layer_ratio``, the policy fields
from ``sources.yaml``, and for EIA ``date_issued`` from the PDF metadata. ERP granule units run
the self-containment check (owner decision 2, 2026-09-20); any FAIL demotes ERP to report-level
with no replacement draw. The manifest is rewritten in place; a second run re-hashes and skips
downloads whose sha256 already matches.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pypdf import PdfReader

from ledger.config import Config
from ledger.ingest.http import Fetcher, govinfo_api_key
from ledger.ingest.manifest import (
    ManifestRow,
    check_manual_dir,
    read_manifest,
    sha256_of,
    write_manifest,
)
from ledger.ingest.sources import load_sources

log = logging.getLogger(__name__)

Verdict = Literal["pass", "fail", "unjudgeable"]
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
CONTINUED = re.compile(r"\bcontinued\b|—\s*con\.|\(cont(?:'d|inued)?\.?\)", re.IGNORECASE)
RUN_OFF = re.compile(r"continued on (?:the )?next page|see next page", re.IGNORECASE)
UNIT_BRACKET = re.compile(r"^\[.+\]$")
HEADER_WINDOW = 15


@dataclass
class ErpCheck:
    unit_id: str
    title_present: Verdict
    header_row: Verdict
    no_carry_in: Verdict
    no_run_off: Verdict
    evidence: dict[str, str] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return "fail" in (self.title_present, self.header_row, self.no_carry_in, self.no_run_off)


@dataclass
class UnitOutcome:
    unit_id: str
    action: str  # downloaded | copied | reused
    pages_before: str
    pages_after: str
    text_layer_ratio: float | None
    date_issued: str | None
    notes: list[str]


@dataclass
class FetchResult:
    outcomes: list[UnitOutcome]
    erp_checks: list[ErpCheck]
    erp_demoted: bool
    below_threshold: list[str]
    calls_by_host: dict[str, int]
    rows: list[ManifestRow]
    unfetchable: list[str] = field(default_factory=list)


# ---- pdf measurements ------------------------------------------------------------------------


def pdf_pages_and_text_ratio(path: Path) -> tuple[int, float, list[str]]:
    """(pages, share of pages with a non-empty text layer, per-page text)."""
    reader = PdfReader(str(path))
    texts = []
    for page in reader.pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception as exc:  # noqa: BLE001 - a broken page is a data fact, not a crash
            log.warning("%s: extract_text failed on a page: %s", path.name, exc)
            texts.append("")
    n = len(texts)
    ratio = (sum(1 for t in texts if t.strip()) / n) if n else 0.0
    return n, ratio, texts


def pdf_date(path: Path) -> tuple[str | None, str]:
    """ISO date from PDF metadata (CreationDate, else ModDate) and which one was used."""
    md = PdfReader(str(path)).metadata
    for attr, label in (
        ("creation_date", "pdf CreationDate"),
        ("modification_date", "pdf ModDate"),
    ):
        try:
            d = getattr(md, attr) if md else None
        except Exception:  # noqa: BLE001 - malformed date strings are common
            d = None
        if d:
            return d.date().isoformat(), label
    return None, "no pdf date metadata"


# ---- ERP granule self-containment (owner decision 2, 2026-09-20) ----------------------------


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("–", "-").replace("—", "-")).strip().lower()


def erp_self_containment(unit_id: str, title: str, texts: list[str]) -> ErpCheck:
    first = texts[0] if texts else ""
    last = texts[-1] if texts else ""
    ev: dict[str, str] = {}
    if not first.strip():
        return ErpCheck(
            unit_id,
            "unjudgeable",
            "unjudgeable",
            "unjudgeable",
            "unjudgeable",
            {"page1": "no text layer"},
        )
    # 1. the granule title appears in the PDF text (page 1 preferred, any page accepted)
    t = _norm(title)
    where = (
        "page 1"
        if t in _norm(first)
        else ("later page" if any(t in _norm(x) for x in texts) else None)
    )
    title_present: Verdict = "pass" if where else "fail"
    ev["title"] = f"'{title[:60]}' found on {where}" if where else f"'{title[:60]}' not found"
    # 2. own header row on page 1: AFTER the title line, within HEADER_WINDOW lines, a unit
    # statement in brackets ("[Percent of nominal GDP]"), a "Year ..." stub, or a line with
    # >= 2 year tokens. The title line itself does not count (it carries years too).
    lines = first.splitlines()
    t_idx = next((i for i, ln in enumerate(lines) if t in _norm(ln)), None)
    window = (
        lines[t_idx + 1 : t_idx + 1 + HEADER_WINDOW] if t_idx is not None else lines[:HEADER_WINDOW]
    )
    header_line = next(
        (
            ln
            for ln in window
            if UNIT_BRACKET.match(ln.strip())
            or ln.strip().lower().startswith("year")
            or len(YEAR.findall(ln)) >= 2
        ),
        None,
    )
    header_row: Verdict = "pass" if header_line else "unjudgeable"
    ev["header"] = (
        f"after the title, page-1 header/unit line: '{header_line.strip()[:80]}'"
        if header_line
        else "no unit statement, 'Year' stub or year-bearing line found after the title on page 1"
    )
    # 3. no carried-over table on page 1
    m = CONTINUED.search(first[:600])
    no_carry_in: Verdict = "fail" if m else "pass"
    ev["carry_in"] = (
        f"'{m.group(0)}' in the first 600 chars of page 1"
        if m
        else "no 'continued' marker at the top of page 1"
    )
    # 4. no run-off on the last page
    m2 = RUN_OFF.search(last[-600:])
    tail = " | ".join(ln.strip() for ln in last.strip().splitlines()[-2:])
    no_run_off: Verdict = "fail" if m2 else "pass"
    ev["run_off"] = (
        f"'{m2.group(0)}' at the end of the last page" if m2 else f"last lines: '{tail[:100]}'"
    )
    return ErpCheck(unit_id, title_present, header_row, no_carry_in, no_run_off, ev)


# ---- the stage --------------------------------------------------------------------------------


def resolve_package_pdf(
    fetcher, cfg: Config, api_key: str, package_id: str
) -> tuple[str | None, str]:
    """Package has no pdfLink: with exactly one granule carrying a pdfLink, that is the document."""
    base = cfg.fetch.govinfo_base_url.rstrip("/")
    try:
        data = fetcher.get_json(
            f"{base}/packages/{package_id}/granules",
            source="govinfo",
            params={"offsetMark": "*", "pageSize": 2, "api_key": api_key},
        )
    except Exception as exc:  # noqa: BLE001 - reported on the row, never hidden
        return None, f"granules lookup failed: {exc}"
    gs = data.get("granules", [])
    if int(data.get("count", 0) or 0) != 1:
        return None, f"package has {data.get('count')} granules; not resolved"
    gid = gs[0]["granuleId"]
    summ = fetcher.get_json(
        f"{base}/packages/{package_id}/granules/{gid}/summary",
        source="govinfo",
        params={"api_key": api_key},
    )
    link = (summ.get("download") or {}).get("pdfLink")
    return link, f"single granule {gid} pdfLink"


def _source_key(row: ManifestRow) -> str:
    return "govinfo" if row.source.startswith("govinfo") else row.source


def run_fetch(cfg: Config, *, repo: Path, fetcher: Fetcher | None = None) -> FetchResult:
    manifest_path = repo / "data" / "manifest.jsonl"
    header, rows = read_manifest(manifest_path)
    sources = load_sources(
        repo / "data" / "sources.yaml", stage="fetch"
    )  # hard-fails on null policy
    manual_rows = {r["filename"]: r for r in check_manual_dir(repo / "data" / "manual" / "cbo")}
    raw_dir = repo / cfg.paths.raw_dir
    fetcher = fetcher or Fetcher(cfg.fetch)
    api_key = None
    outcomes: list[UnitOutcome] = []
    erp_checks: list[ErpCheck] = []
    below: list[str] = []
    unfetchable: list[str] = []

    for row in rows:
        dest = raw_dir / row.source / f"{row.unit_id}.pdf"
        before = f"{row.pages} ({row.pages_source})"
        notes = [n for n in row.notes if not n.startswith("fetch:")]
        policy_key = "cbo" if row.source == "cbo_manual" else _source_key(row)
        pol = sources.get(policy_key)
        if pol:
            row.policy_url, row.policy_note = pol.policy_url, pol.policy_note

        if row.source == "cbo_manual":
            fname = f"{row.unit_id}.pdf"
            mrow = manual_rows.get(fname)
            if mrow is None:
                raise RuntimeError(
                    f"{row.unit_id}: no row in data/manual/cbo/sources.csv for {fname}"
                )
            if mrow["date_issued"] != row.date_issued:
                raise RuntimeError(
                    f"{row.unit_id}: sources.csv date_issued {mrow['date_issued']!r} != manifest "
                    f"{row.date_issued!r} — fix one; not overwritten"
                )
            src = repo / "data" / "manual" / "cbo" / fname
            if dest.exists() and sha256_of(dest) == sha256_of(src):
                action = "reused"
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)
                action = "copied"
            row.url = mrow["url"]
        else:
            if not row.url and row.package_id and row.granule_id is None:
                # CRPT packages expose the PDF on their single FIRSTPART granule, not the
                # package. Resolve through the granule; the unit is unchanged (no redraw).
                api_key = api_key or govinfo_api_key()
                url, how = resolve_package_pdf(fetcher, cfg, api_key, row.package_id)
                if url:
                    row.url = url
                    notes.append(f"fetch: url resolved via {how}")
            if not row.url:
                # A fact about the source (BUDGET-2027-TAB: the package exposes premis/zip/mods
                # only — no PDF exists). Recorded, not redrawn; the owner decides at A9.
                notes.append(
                    "fetch: UNFETCHABLE — the source exposes no pdfLink for this unit "
                    "(package download keys lack pdfLink); no PDF exists to parse"
                )
                row.notes = notes
                unfetchable.append(row.unit_id)
                outcomes.append(
                    UnitOutcome(
                        row.unit_id, "unfetchable", before, "—", None, row.date_issued, notes
                    )
                )
                continue
            if dest.exists() and row.sha256 and sha256_of(dest) == row.sha256:
                action = "reused"
            else:
                params = None
                if _source_key(row) == "govinfo":
                    api_key = api_key or govinfo_api_key()
                    params = {"api_key": api_key}
                fetcher.download(row.url, dest, source=_source_key(row), params=params)
                action = "downloaded"

        row.sha256 = sha256_of(dest)
        pages, ratio, texts = pdf_pages_and_text_ratio(dest)
        row.pages, row.pages_source = pages, "measured"
        row.text_layer_ratio = round(ratio, 4)
        if ratio < cfg.fetch.text_layer_ratio_min:
            notes.append(
                f"fetch: text_layer_ratio {ratio:.3f} < {cfg.fetch.text_layer_ratio_min} — kept, "
                "flagged for A1/A9"
            )
            below.append(row.unit_id)
        if row.source == "eia" and not row.date_issued:
            d, how = pdf_date(dest)
            row.date_issued = d
            notes.append(f"fetch: date_issued from {how}")
        if row.source == "govinfo_erp" and row.unit_kind == "granule":
            chk = erp_self_containment(row.unit_id, row.title, texts)
            erp_checks.append(chk)
            notes.append(
                "fetch: ERP self-containment "
                f"title={chk.title_present} header={chk.header_row} carry_in={chk.no_carry_in} "
                f"run_off={chk.no_run_off}"
            )
        row.notes = notes
        outcomes.append(
            UnitOutcome(
                row.unit_id,
                action,
                before,
                f"{row.pages} (measured)",
                row.text_layer_ratio,
                row.date_issued,
                notes,
            )
        )

    # ---- owner decision 2: any ERP FAIL -> report-level, no replacement draw --------------------
    demoted = any(c.failed for c in erp_checks)
    if demoted:
        gran = [r for r in rows if r.source == "govinfo_erp" and r.unit_kind == "granule"]
        pkg_id = gran[0].package_id if gran else "ERP-2026"
        rows = [r for r in rows if not (r.source == "govinfo_erp" and r.unit_kind == "granule")]
        pkg_url = f"{cfg.fetch.govinfo_base_url.rstrip('/')}/packages/{pkg_id}/pdf"
        pol = sources.get("govinfo")
        pkg_row = ManifestRow(
            unit_id=f"govinfo-{pkg_id}",
            source="govinfo_erp",
            parent_series=gran[0].parent_series if gran else "ERP",
            unit_kind="report",
            fetch_method="govinfo",
            title=gran[0].parent_series if gran else "ERP",
            date_issued=gran[0].date_issued if gran else None,
            url=pkg_url,
            package_id=pkg_id,
            snapshot_date=header.snapshot_date,
            policy_url=pol.policy_url if pol else None,
            policy_note=pol.policy_note if pol else None,
            notes=[
                "fetch: ERP demoted to report-level — a granule failed self-containment "
                "(owner decision 2, 2026-09-20); no replacement draw"
            ],
        )
        dest = raw_dir / "govinfo_erp" / f"{pkg_row.unit_id}.pdf"
        api_key = api_key or govinfo_api_key()
        fetcher.download(pkg_url, dest, source="govinfo", params={"api_key": api_key})
        pkg_row.sha256 = sha256_of(dest)
        pages, ratio, _ = pdf_pages_and_text_ratio(dest)
        pkg_row.pages, pkg_row.pages_source, pkg_row.text_layer_ratio = (
            pages,
            "measured",
            round(ratio, 4),
        )
        rows.append(pkg_row)
        outcomes.append(
            UnitOutcome(
                pkg_row.unit_id,
                "downloaded",
                "— (demotion)",
                f"{pages} (measured)",
                pkg_row.text_layer_ratio,
                pkg_row.date_issued,
                pkg_row.notes,
            )
        )

    write_manifest(manifest_path, header, rows)
    return FetchResult(
        outcomes, erp_checks, demoted, below, dict(fetcher.calls_by_host), rows, unfetchable
    )


def render_fetch_report(res: FetchResult) -> str:
    out = ["FETCH STAGE", ""]
    for o in res.outcomes:
        out.append(
            f"- {o.unit_id} · {o.action} · pages {o.pages_before} -> {o.pages_after} · "
            f"text_layer {o.text_layer_ratio} · date {o.date_issued}"
        )
        for n in o.notes:
            if n.startswith("fetch:"):
                out.append(f"    {n}")
    out.append("")
    for c in res.erp_checks:
        out.append(
            f"ERP {c.unit_id}: title={c.title_present} header={c.header_row} "
            f"carry_in={c.no_carry_in} run_off={c.no_run_off}"
        )
        for k, v in c.evidence.items():
            out.append(f"    {k}: {v}")
    out.append(f"ERP demoted to report-level: {res.erp_demoted}")
    out.append(f"below text_layer_ratio_min: {res.below_threshold or 'none'}")
    out.append(f"HTTP calls by host: {res.calls_by_host or 'none'}")
    out.append(f"unfetchable (no pdfLink at the source): {res.unfetchable or 'none'}")
    out.append(f"manifest units: {len(res.rows)}")
    return "\n".join(out)
