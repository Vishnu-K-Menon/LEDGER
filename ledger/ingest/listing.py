"""``ledger ingest --stage list`` (T2, D-034): frames -> candidates -> granule gate -> seeded
stratified draw -> manifest rows. Downloads nothing. Stops for the owner's confirmation."""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from pathlib import Path

from ledger.config import Config
from ledger.ingest import eia as eia_mod
from ledger.ingest.draw import draw, draw_stratified, seeded
from ledger.ingest.frames import parse_frames, write_candidates_csv
from ledger.ingest.govinfo import NON_CONTENT_CLASSES, GateReport, GovInfo, Granule, Package
from ledger.ingest.http import Fetcher, govinfo_api_key
from ledger.ingest.manifest import ManifestHeader, ManifestRow, write_manifest
from ledger.ingest.sources import SourcePolicy, load_sources

log = logging.getLogger(__name__)


@dataclass
class SourceOutcome:
    source: str
    frame: str
    candidates: int
    gate: GateReport | None
    unit_kind: str
    drawn: list[ManifestRow]
    exceptions: list[str] = field(default_factory=list)
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class ListingResult:
    header: ManifestHeader
    rows: list[ManifestRow]
    outcomes: list[SourceOutcome]
    calls: int


def _policy(sources: dict[str, SourcePolicy], key: str) -> tuple[str | None, str | None]:
    s = sources.get(key)
    return (s.policy_url, s.policy_note) if s else (None, None)


def _row(**kw) -> ManifestRow:
    return ManifestRow(**kw)


def run_listing(cfg: Config, *, repo: Path, snapshot_date: str | None = None) -> ListingResult:
    snapshot = snapshot_date or dt.date.today().isoformat()
    seed = cfg.corpus.selection_seed
    mix = cfg.corpus.source_mix
    fetcher = Fetcher(cfg.fetch)
    sources = load_sources(repo / "data" / "sources.yaml", stage="list")
    outcomes: list[SourceOutcome] = []
    rows: list[ManifestRow] = []
    frames: dict[str, str] = {}

    # ---- cbo_manual: committed frames -> candidates csv -> one per year -----------------------
    n = mix.get("cbo_manual", 0)
    cands = parse_frames(repo / "data" / "frames")
    csv_path = repo / "data" / "frames" / "cbo_candidates.csv"
    write_candidates_csv(cands, csv_path)
    per_year = n // 4 if n else 0
    picked = draw_stratified(
        cands,
        per_year,
        seeded(seed, "cbo"),
        stratum=lambda c: c.frame_year,
        key=lambda c: c.publication_id,
    )
    purl, pnote = _policy(sources, "cbo")
    drawn = [
        _row(
            unit_id=f"cbo-{c.publication_id}",
            source="cbo_manual",
            parent_series="CBO cost estimates",
            unit_kind="report",
            fetch_method="manual",
            title=c.title,
            date_issued=c.date_issued,
            url=None,
            page_url=c.page_url,
            snapshot_date=snapshot,
            policy_url=purl,
            policy_note=pnote,
            notes=[
                "second hop is the owner's: open page_url, download the PDF, "
                "fill data/manual/cbo/sources.csv"
            ],
        )
        for c in picked
    ]
    frames["cbo_manual"] = "data/frames/frame_{2023..2026}.html -> data/frames/cbo_candidates.csv"
    outcomes.append(
        SourceOutcome("cbo_manual", frames["cbo_manual"], len(cands), None, "report", drawn)
    )
    rows.extend(drawn)

    # ---- eia: sitemap -> landing pages -> pdf links --------------------------------------------
    n = mix.get("eia", 0)
    exc: list[str] = []
    extra: dict[str, str] = {}
    drawn = []
    try:
        sm = eia_mod.sitemap_lists(fetcher, cfg.fetch)
        extra["sitemap"] = (
            f"index={sm.pop('_is_index')} urls={sm.pop('_url_count')} pdfs={sm.pop('_pdf_count')} "
            f"landing pages listed={sm}"
        )
        units = eia_mod.list_units(fetcher, cfg.fetch)
        mer = [u for u in units if u.series == "mer"]
        others = [u for u in units if u.series != "mer"]
        k_mer = min(cfg.fetch.pilot_eia_mer_sections, n)
        pick = draw(mer, k_mer, seeded(seed, "eia-mer"), key=lambda u: u.url)
        pick += draw(others, n - len(pick), seeded(seed, "eia-other"), key=lambda u: u.url)
        purl, pnote = _policy(sources, "eia")
        series_name = {
            "mer": "Monthly Energy Review",
            "steo": "Short-Term Energy Outlook",
            "aeo": "Annual Energy Outlook",
        }
        for u in pick:
            uid = (
                "eia-"
                + u.url.rsplit("/", 2)[-2]
                + "-"
                + u.url.rsplit("/", 1)[-1].replace(".pdf", "")
            )
            drawn.append(
                _row(
                    unit_id=uid,
                    source="eia",
                    parent_series=series_name[u.series],
                    unit_kind="granule" if u.series == "mer" else "report",
                    fetch_method="direct",
                    title=u.title,
                    date_issued=None,
                    url=u.url,
                    snapshot_date=snapshot,
                    policy_url=purl,
                    policy_note=pnote,
                    notes=[
                        "date_issued and pages are taken from the PDF at --stage fetch "
                        "(EIA lists neither)"
                    ],
                )
            )
        if len(units) < n:
            exc.append(
                f"frame yields {len(units)} EIA units, fewer than {n}; "
                "not padded from another source"
            )
        extra["units_found"] = f"mer sections={len(mer)} other={len(others)}"
        candidates = len(units)
    except Exception as e:  # noqa: BLE001 - reported, never hidden
        exc.append(f"{type(e).__name__}: {e}")
        candidates = 0
    frames["eia"] = "sitemap.xml (HTML pages only) -> " + ", ".join(
        cfg.fetch.eia_landing_pages.values()
    )
    outcomes.append(
        SourceOutcome(
            "eia",
            frames["eia"],
            candidates,
            None,
            "granule (MER sections) / report",
            drawn,
            exc,
            extra,
        )
    )
    rows.extend(drawn)

    # ---- govinfo: BUDGET, ERP, (ECONI 0 in pilot), CRPT parse test ------------------------------
    gi = GovInfo(fetcher, cfg.fetch, govinfo_api_key())
    start, end = cfg.fetch.date_range
    purl, pnote = _policy(sources, "govinfo")

    def govinfo_source(source: str, collection: str, n: int) -> None:
        exc: list[str] = []
        drawn: list[ManifestRow] = []
        gate = None
        try:
            pkgs = gi.latest_per_series(gi.published(collection, start, end))
            granules: dict[str, list[Granule]] = {}
            for p in pkgs:
                gi.package_summary(p)
                granules[p.package_id] = gi.granules(p)
            gate = gi.gate(source, pkgs, granules)
            if gate.unit_kind == "granule":
                pool = [
                    g
                    for pid in granules
                    for g in granules[pid]
                    if g.granule_class not in NON_CONTENT_CLASSES
                ]
                # packages with no granules still contribute themselves as report units
                pool_reports = [p for p in pkgs if not granules.get(p.package_id)]
                pick_g = draw(
                    pool, n, seeded(seed, source), key=lambda g: (g.package_id, g.granule_id)
                )
                pick_p: list[Package] = []
                if len(pick_g) < n:
                    pick_p = draw(
                        pool_reports,
                        n - len(pick_g),
                        seeded(seed, source + "-reports"),
                        key=lambda p: p.package_id,
                    )
                by_pid = {p.package_id: p for p in pkgs}
                for g in pick_g:
                    if g.pdf_link is None:
                        gi.granule_summary(g)
                    parent = by_pid[g.package_id]
                    est = None
                    if g.pages is None and parent.pages and parent.granule_count:
                        est = max(1, round(parent.pages / parent.granule_count))
                    drawn.append(
                        _row(
                            unit_id=f"govinfo-{g.granule_id}",
                            source=source,
                            parent_series=parent.title,
                            unit_kind="granule",
                            fetch_method="govinfo",
                            title=g.title,
                            date_issued=g.date_issued,
                            url=g.pdf_link,
                            package_id=g.package_id,
                            granule_id=g.granule_id,
                            pages=g.pages if g.pages is not None else est,
                            pages_source="metadata"
                            if g.pages is not None
                            else ("estimated" if est else "unknown"),
                            snapshot_date=snapshot,
                            policy_url=purl,
                            policy_note=pnote,
                            notes=[f"granuleClass={g.granule_class}"],
                        )
                    )
                for p in pick_p:
                    drawn.append(_pkg_row(p, source, snapshot, purl, pnote))
            else:
                pick_p = draw(pkgs, n, seeded(seed, source), key=lambda p: p.package_id)
                for p in pick_p:
                    drawn.append(_pkg_row(p, source, snapshot, purl, pnote))
            candidates = sum(len(v) for v in granules.values()) or len(pkgs)
            extra = {"packages_latest_edition": str(len(pkgs))}
        except Exception as e:  # noqa: BLE001
            exc.append(f"{type(e).__name__}: {e}")
            candidates, extra = 0, {}
        outcomes.append(
            SourceOutcome(
                source,
                f"api.govinfo.gov /published/{start}/{end}?collection={collection}",
                candidates,
                gate,
                gate.unit_kind if gate else "?",
                drawn,
                exc,
                extra,
            )
        )
        rows.extend(drawn)

    if mix.get("govinfo_budget", 0):
        govinfo_source("govinfo_budget", "BUDGET", mix["govinfo_budget"])
    if mix.get("govinfo_erp", 0):
        govinfo_source("govinfo_erp", "ERP", mix["govinfo_erp"])
    if mix.get("govinfo_econi", 0):
        govinfo_source("govinfo_econi", "ECONI", mix["govinfo_econi"])

    # CRPT: seeded sample of N packages, filter for an embedded CBO cost estimate, draw 1.
    n = mix.get("govinfo_crpt", 0)
    if n:
        exc, drawn, extra = [], [], {}
        try:
            all_crpt = gi.published("CRPT", start, end)
            sample = draw(
                all_crpt,
                cfg.fetch.crpt_sample_n,
                seeded(seed, "crpt-sample"),
                key=lambda p: p.package_id,
            )
            passed, checked = gi.crpt_filter(sample)
            extra["filter_base_rate"] = (
                f"{len(passed)}/{checked} sampled packages contain a CBO cost estimate"
            )
            for p in draw(passed, n, seeded(seed, "crpt"), key=lambda p: p.package_id):
                r = _pkg_row(p, "govinfo_crpt", snapshot, purl, pnote)
                r.notes.append(
                    "parse test only (A1): does the GPO-typeset embedded cost estimate "
                    "parse as a table?"
                )
                drawn.append(r)
            if not passed:
                exc.append("no sampled CRPT package passed the cost-estimate filter")
            candidates = len(all_crpt)
        except Exception as e:  # noqa: BLE001
            exc.append(f"{type(e).__name__}: {e}")
            candidates = 0
        outcomes.append(
            SourceOutcome(
                "govinfo_crpt",
                f"api.govinfo.gov /published/{start}/{end}?collection=CRPT "
                f"(seeded sample of {cfg.fetch.crpt_sample_n})",
                candidates,
                None,
                "report",
                drawn,
                exc,
                extra,
            )
        )
        rows.extend(drawn)

    frames["govinfo"] = f"api.govinfo.gov /published/{start}/{end}?collection=<code> (dateIssued)"
    header = ManifestHeader(
        selection_seed=seed, snapshot_date=snapshot, frames=frames, pilot_composition=dict(mix)
    )
    write_manifest(repo / "data" / "manifest.jsonl", header, rows)
    return ListingResult(header, rows, outcomes, fetcher.calls)


def _pkg_row(p: Package, source: str, snapshot: str, purl, pnote) -> ManifestRow:
    return _row(
        unit_id=f"govinfo-{p.package_id}",
        source=source,
        parent_series=p.title,
        unit_kind="report",
        fetch_method="govinfo",
        title=p.title,
        date_issued=p.date_issued,
        url=p.pdf_link,
        package_id=p.package_id,
        pages=p.pages,
        pages_source="metadata" if p.pages is not None else "unknown",
        snapshot_date=snapshot,
        policy_url=purl,
        policy_note=pnote,
    )


def render_report(res: ListingResult) -> str:
    lines = [
        f"LISTING PASS — seed {res.header.selection_seed} · snapshot "
        f"{res.header.snapshot_date} · HTTP calls {res.calls}",
        "",
    ]
    for o in res.outcomes:
        g = o.gate
        gate_txt = (
            f"1 pdfLink={g.check1_pdflink} pages={g.check1_pages} · "
            f"2 self-contained={g.check2_self_contained} · 3 boundary={g.check3_boundary}"
            if g
            else "n/a"
        )
        lines.append(f"== {o.source}: frame={o.frame}")
        lines.append(f"   candidates={o.candidates} · gate: {gate_txt} · unit_kind={o.unit_kind}")
        for k, v in o.extra.items():
            lines.append(f"   {k}: {v}")
        if g:
            for d in g.details:
                lines.append(f"   gate: {d}")
        for r in o.drawn:
            lines.append(
                f"   - {r.unit_id} · {r.date_issued or '?'} · {r.title[:70]} · "
                f"pages={r.pages} ({r.pages_source})"
            )
        for e in o.exceptions:
            lines.append(f"   ! {e}")
    lines.append("")
    lines.append(
        f"TOTAL pilot units: {len(res.rows)} (target {sum(res.header.pilot_composition.values())})"
    )
    lines.append(
        "Nothing downloaded. Confirm the draw, then `ledger ingest --stage fetch --draw-confirmed`."
    )
    return "\n".join(lines)
