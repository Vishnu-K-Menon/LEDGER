# ruff: noqa: E501
"""Full-corpus eligible-pool report: READ-ONLY listing. Draws nothing, fetches no PDF, parses
nothing, and writes only ``reports/full_corpus_pools.{md,json}``.

It does NOT call ``listing.run_listing`` (which writes ``data/manifest.jsonl``) and does not run
``ledger ingest --stage list``; it calls the lower-level listing functions the same way
``run_listing`` does: ``GovInfo.published`` / ``latest_per_series`` / ``package_summary`` /
``granules`` / ``gate`` and ``listing.resolvable_reports``. Network use is GET-only against
api.govinfo.gov and www.eia.gov (cbo.gov and gao.gov are never contacted; the CBO frame HTML is a
local file).

    uv run python scripts/list_full_corpus.py
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ledger.config import load_config  # noqa: E402
from ledger.ingest import eia as eia_mod  # noqa: E402
from ledger.ingest.frames import parse_frames  # noqa: E402
from ledger.ingest.govinfo import NON_CONTENT_CLASSES, GovInfo, Granule, Package  # noqa: E402
from ledger.ingest.http import Fetcher, govinfo_api_key  # noqa: E402
from ledger.ingest.listing import resolvable_reports  # noqa: E402
from ledger.ingest.manifest import read_manifest  # noqa: E402

SNAPSHOT = "2026-09-20"  # the pilot's snapshot_date (D-034)
AFTER = "2026-09-21"
RATE = {"budget": (9.0, 19.0), "cbo": (2.5, 5.0), "other": (15.0, 15.0)}  # s/page (plan.md T3)
NIGHT_S = 8 * 3600
OUT = REPO / "reports"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def hrs(s: float) -> str:
    return f"{s / 3600:.1f} h"


def pkg_row(p: Package, how: str | None = None) -> dict:
    return {
        "package_id": p.package_id,
        "series": GovInfo.series_key(p),
        "title": p.title,
        "date_issued": p.date_issued,
        "pages": p.pages,
        "granules": p.granule_count,
        "pdf_link_source": how,
    }


def quart(vals: list[int]) -> dict:
    if not vals:
        return {}
    q = statistics.quantiles(vals, n=4, method="inclusive") if len(vals) > 1 else [vals[0]] * 3
    return {
        "n": len(vals),
        "min": min(vals),
        "q1": q[0],
        "median": q[1],
        "q3": q[2],
        "max": max(vals),
    }


def caps(vals: list[int]) -> dict:
    return {f"< {c}": sum(1 for v in vals if v < c) for c in (100, 200, 300, 500)}


def main() -> None:
    cfg = load_config(REPO / "configs" / "base.yaml")
    manifest_path = REPO / cfg.paths.manifest
    manifest_hash_before = sha256(manifest_path)
    _, mrows = read_manifest(manifest_path)
    in_manifest = {r.unit_id for r in mrows}
    pilot_pkgs = {r.package_id for r in mrows if r.package_id}
    start, _end = cfg.fetch.date_range
    end_all = cfg.fetch.date_range[1]
    fetcher = Fetcher(cfg.fetch)
    gi = GovInfo(fetcher, cfg.fetch, govinfo_api_key())
    R: dict = {"snapshot": SNAPSHOT, "manifest_units": len(in_manifest)}

    def pilot_series(prefix: str) -> set[str]:
        return {
            GovInfo.series_key(Package(p, "", "", ""))
            for p in pilot_pkgs
            if p.startswith(prefix + "-")
        }

    def window(coll: str) -> tuple[list[Package], list[Package]]:
        return gi.published(coll, start, SNAPSHOT), gi.published(coll, AFTER, end_all)

    # ---- BUDGET ---------------------------------------------------------------------------
    pre, post = window("BUDGET")
    latest = gi.latest_per_series(pre)
    granules: dict[str, list[Granule]] = {}
    for p in latest:
        gi.package_summary(p)
        granules[p.package_id] = gi.granules(p)
    gate = gi.gate("govinfo_budget", latest, granules)
    ps = pilot_series("BUDGET")
    cand = [p for p in latest if GovInfo.series_key(p) not in ps]
    in_pilot_series = [p for p in latest if GovInfo.series_key(p) in ps]
    keep, links, unresolvable = resolvable_reports(gi, cand, granules)
    elig = [p for p in keep if f"govinfo-{p.package_id}" not in in_manifest]
    post_series = {GovInfo.series_key(p) for p in post}
    R["budget"] = {
        "published_pre_snapshot": len(pre),
        "distinct_series_pre": len({GovInfo.series_key(p) for p in pre}),
        "latest_per_series": len(latest),
        "pilot_series": sorted(ps),
        "removed_pilot_series": [p.package_id for p in in_pilot_series],
        "candidates": len(cand),
        "no_resolvable_pdflink": unresolvable,
        "already_in_manifest": [p.package_id for p in keep if p not in elig],
        "eligible": [pkg_row(p, links[p.package_id][1]) for p in elig],
        "gate": {
            "unit_kind": gate.unit_kind,
            "check1_pdflink": gate.check1_pdflink,
            "check1_pages": gate.check1_pages,
            "check2": gate.check2_self_contained,
            "check3": gate.check3_boundary,
            "details": gate.details[:12],
        },
        "after_snapshot": [pkg_row(p) for p in post],
        "series_with_after_snapshot_edition": sorted(
            {GovInfo.series_key(p) for p in elig} & post_series
        ),
        "pages_missing": [p.package_id for p in elig if p.pages is None],
    }
    bp = [p.pages for p in elig if p.pages is not None]
    R["budget"]["page_distribution"] = quart(bp)
    R["budget"]["page_caps"] = caps(bp)

    # ---- ERP ------------------------------------------------------------------------------
    pre, post = window("ERP")
    latest_erp = gi.latest_per_series(pre)
    erp_pkg = latest_erp[0]
    gi.package_summary(erp_pkg)
    erp_gr = gi.granules(erp_pkg)
    content = [g for g in erp_gr if g.granule_class not in NON_CONTENT_CLASSES]
    tables = [g for g in content if g.granule_class.upper() == "TABLE"]
    pilot_gids = {r.granule_id for r in mrows if r.granule_id}
    erp_elig = [g for g in tables if g.granule_id not in pilot_gids]
    for g in erp_elig:
        gi.granule_summary(g)
    est = max(1, round(erp_pkg.pages / erp_pkg.granule_count)) if erp_pkg.pages else None
    draw = json.loads((REPO / "data/oracle/fresh/erp_draw.json").read_text("utf-8"))
    held = [d["granule_id"] for d in draw["drawn"]]
    erp_ids = {g.granule_id for g in erp_elig}
    R["erp"] = {
        "editions_pre_snapshot": [pkg_row(p) for p in pre],
        "one_edition": erp_pkg.package_id,
        "package_pages": erp_pkg.pages,
        "package_granules": erp_pkg.granule_count,
        "granule_classes": {
            c: sum(1 for g in erp_gr if g.granule_class == c)
            for c in sorted({g.granule_class for g in erp_gr})
        },
        "table_granules": len(tables),
        "removed_pilot": sorted(g.granule_id for g in tables if g.granule_id in pilot_gids),
        "eligible_count": len(erp_elig),
        "pages_estimate_per_granule": est,
        "metadata_pages_present": sum(1 for g in erp_elig if g.pages is not None),
        "no_pdflink": [g.granule_id for g in erp_elig if not g.pdf_link],
        "eligible": [
            {
                "granule_id": g.granule_id,
                "title": g.title,
                "pages_metadata": g.pages,
                "pages_estimate": est,
                "has_pdf_link": bool(g.pdf_link),
            }
            for g in erp_elig
        ],
        "held_out": [
            {
                "granule_id": h,
                "in_eligible_pool": h in erp_ids,
                "local_pdf": (REPO / f"data/raw_fresh/govinfo_erp/govinfo-{h}.pdf").exists(),
                "local_xls": (REPO / f"data/oracle/fresh/erp/{h}.xls").exists(),
            }
            for h in held
        ],
        "after_snapshot": [pkg_row(p) for p in post],
    }

    # ---- ECONI ----------------------------------------------------------------------------
    pre, post = window("ECONI")
    latest_e = gi.latest_per_series(pre)
    ec = latest_e[0] if latest_e else None
    R["econi"] = {
        "published_pre_snapshot": len(pre),
        "series_found": sorted({GovInfo.series_key(p) for p in pre}),
        "after_snapshot": [pkg_row(p) for p in post],
    }
    if ec:
        gi.package_summary(ec)
        egr = gi.granules(ec)
        egate = gi.gate("govinfo_econi", [ec], {ec.package_id: egr})
        row: dict = {
            **pkg_row(ec),
            "in_manifest": f"govinfo-{ec.package_id}" in in_manifest,
            "gate": {
                "unit_kind": egate.unit_kind,
                "check1_pdflink": egate.check1_pdflink,
                "check1_pages": egate.check1_pages,
                "check2": egate.check2_self_contained,
                "check3": egate.check3_boundary,
                "details": egate.details[:12],
            },
        }
        if egate.unit_kind == "report":
            _k, elinks, exc = resolvable_reports(gi, [ec], {ec.package_id: egr})
            row["pdf_link_source"] = elinks[ec.package_id][1] if elinks else None
            row["no_resolvable_pdflink"] = exc
        else:
            ec_content = [g for g in egr if g.granule_class not in NON_CONTENT_CLASSES]
            for g in ec_content:
                gi.granule_summary(g)
            e_est = (
                max(1, round(ec.pages / ec.granule_count))
                if ec.pages and ec.granule_count
                else None
            )
            row["granule_list"] = [
                {
                    "granule_id": g.granule_id,
                    "title": g.title,
                    "class": g.granule_class,
                    "pages_metadata": g.pages,
                    "pages_estimate": e_est if g.pages is None else None,
                    "has_pdf_link": bool(g.pdf_link),
                    "in_manifest": f"govinfo-{g.granule_id}" in in_manifest,
                }
                for g in ec_content
            ]
        R["econi"]["edition"] = row

    # ---- EIA ------------------------------------------------------------------------------
    sm = eia_mod.sitemap_lists(fetcher, cfg.fetch)
    units = eia_mod.list_units(fetcher, cfg.fetch)
    excluded_series = set(cfg.corpus.excluded_parent_series)
    name = {
        "mer": "Monthly Energy Review",
        "steo": "Short-Term Energy Outlook",
        "aeo": "Annual Energy Outlook",
    }

    def eia_id(u) -> str:
        return (
            "eia-" + u.url.rsplit("/", 2)[-2] + "-" + u.url.rsplit("/", 1)[-1].replace(".pdf", "")
        )

    ledger_rows = []
    for u in units:
        mer = name[u.series] in excluded_series
        ledger_rows.append(
            {
                "unit_id": eia_id(u),
                "series": u.series,
                "url": u.url,
                "mer_excluded": mer,
                "in_manifest": eia_id(u) in in_manifest,
            }
        )
    framed = {u.url for u in units}
    extras = []
    for series, page in cfg.fetch.eia_landing_pages.items():
        html = fetcher.get_text(page, source="eia")
        for href in sorted(set(eia_mod.HREF_PDF.findall(html))):
            url = eia_mod.urljoin(page, href)
            if url not in framed:
                extras.append(
                    {
                        "landing": series,
                        "url": url,
                        "robots_disallowed": eia_mod._disallowed(url, cfg.fetch),
                    }
                )
    R["eia"] = {
        "sitemap": {str(k): v for k, v in sm.items()},
        "frame_units": ledger_rows,
        "eligible": [r for r in ledger_rows if not r["mer_excluded"] and not r["in_manifest"]],
        "other_pdf_links_outside_frame": extras,
    }

    # ---- CBO (manual; cbo.gov is never contacted) -----------------------------------------
    src_csv = REPO / "data/manual/cbo/sources.csv"
    with src_csv.open(encoding="utf-8-sig", newline="") as fh:
        srows = list(csv.DictReader(fh))
    cbo_ids = {Path(r["filename"]).stem for r in srows}
    cands = parse_frames(REPO / "data" / "frames")
    cand_rows = [
        {
            "unit_id": f"cbo-{c.publication_id}",
            "frame_year": c.frame_year,
            "date_issued": c.date_issued,
            "title": c.title,
            "in_manifest": f"cbo-{c.publication_id}" in in_manifest,
        }
        for c in cands
    ]
    pilot_cbo_pages = [r.pages for r in mrows if r.source == "cbo_manual" and r.pages]
    R["cbo"] = {
        "sources_csv_rows": len(srows),
        "sources_csv_in_manifest": sum(1 for i in cbo_ids if i in in_manifest),
        "frame_candidates": len(cand_rows),
        "frame_candidates_not_in_manifest": sum(1 for c in cand_rows if not c["in_manifest"]),
        "pilot_cbo_pages": pilot_cbo_pages,
        "not_in_manifest": [c for c in cand_rows if not c["in_manifest"]],
    }

    # ---- estimates ------------------------------------------------------------------------
    est_rows = {}
    bpages = sum(p["pages"] or 0 for p in R["budget"]["eligible"])
    lo, hi = RATE["budget"]
    est_rows["budget"] = {"pages": bpages, "s_low": bpages * lo, "s_high": bpages * hi}
    erp_pages = sum((g["pages_metadata"] or g["pages_estimate"] or 0) for g in R["erp"]["eligible"])
    est_rows["erp"] = {"pages": erp_pages, "s_low": erp_pages * 15.0, "s_high": erp_pages * 15.0}
    ed = R["econi"].get("edition")
    ec_pages = (ed or {}).get("pages") or 0
    est_rows["econi"] = {"pages": ec_pages, "s_low": ec_pages * 15.0, "s_high": ec_pages * 15.0}
    avg = sum(pilot_cbo_pages) / len(pilot_cbo_pages) if pilot_cbo_pages else 0
    n_cbo = R["cbo"]["frame_candidates_not_in_manifest"]
    est_rows["cbo"] = {
        "pages": round(avg * n_cbo),
        "s_low": avg * n_cbo * RATE["cbo"][0],
        "s_high": avg * n_cbo * RATE["cbo"][1],
    }
    est_rows["eia"] = {"pages": 0, "s_low": 0, "s_high": 0}
    R["estimates"] = est_rows
    R["night_pages"] = {
        "budget_at_9": int(NIGHT_S / lo),
        "budget_at_19": int(NIGHT_S / hi),
    }
    R["http"] = {"calls": fetcher.calls, "by_host": dict(fetcher.calls_by_host)}
    manifest_hash_after = sha256(manifest_path)
    assert manifest_hash_before == manifest_hash_after, "data/manifest.jsonl changed"
    R["manifest_sha256"] = manifest_hash_after
    R["generated"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")

    OUT.mkdir(exist_ok=True)
    (OUT / "full_corpus_pools.json").write_text(
        json.dumps(R, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    (OUT / "full_corpus_pools.md").write_text(render(R), encoding="utf-8")
    print(
        json.dumps(
            {
                "http": R["http"],
                "budget_eligible": len(R["budget"]["eligible"]),
                "erp_eligible": R["erp"]["eligible_count"],
                "econi": (R["econi"].get("edition") or {}).get("gate", {}).get("unit_kind"),
                "eia_eligible": len(R["eia"]["eligible"]),
            },
            indent=1,
        )
    )


def render(R: dict) -> str:
    b, e, ec, ei, c = R["budget"], R["erp"], R["econi"], R["eia"], R["cbo"]
    L: list[str] = []
    a = L.append
    a("# Full-corpus eligible pools (read-only listing; nothing drawn, fetched or parsed)")
    a("")
    a(
        f"Generated {R['generated']} · snapshot cut-off **{R['snapshot']}** (the pilot's, D-034) ·"
        f" `data/manifest.jsonl` sha256 unchanged (`{R['manifest_sha256'][:12]}…`), {R['manifest_units']} units in it."
    )
    a("")
    a(
        "**No draw, no PDF fetch, no parse, nothing under `data/` written.** `run_listing`"
        " (`ledger/ingest/listing.py:93`, writes the manifest at :377) was not called; the script is"
        " `scripts/list_full_corpus.py`."
    )
    a("")
    a("## Functions reused")
    a("")
    a("- `ledger/ingest/http.py`: `Fetcher` :28 (`calls_by_host` :39), `govinfo_api_key` :130")
    a(
        "- `ledger/ingest/govinfo.py`: `published` :105, `package_summary` :133, `granules` :143,"
        " `granule_summary` :167, `series_key` :184, `latest_per_series` :194, `gate` :205"
    )
    a("- `ledger/ingest/listing.py`: `resolvable_reports` :75 (calls `report_pdf_link` :58)")
    a(
        "- `ledger/ingest/eia.py`: `sitemap_lists` :27, `list_units` :45, `HREF_PDF` :14, `_disallowed` :41"
    )
    a("- `ledger/ingest/frames.py`: `parse_frames` (read-only; `write_candidates_csv` not called)")
    a("- `ledger/ingest/manifest.py`: `read_manifest`")
    a("")
    a("## Readings applied")
    a("")
    a(
        "- Window: `published(<collection>, 2023-01-01, 2026-09-20)` is eligible; packages with"
        " dateIssued 2026-09-21 or later are listed separately as **after snapshot** and are not eligible."
    )
    a(
        "- D-034 one edition per series (`latest_per_series`, series from the package id), computed"
        " inside the pre-snapshot window. A series already in the pilot is ineligible in every edition"
        " (report-level BUDGET). ERP is granule-level: ERP-2026 stays the one edition and the exclusion is"
        " per unit (the pilot's two granules); ERP-2023..2025 are ineligible by the one-edition rule."
    )
    a(
        "- pdfLink rule (`resolvable_reports`), MER excluded (`corpus.excluded_parent_series`),"
        " `govinfo_crpt` = 0 (no CRPT call), every unit in the manifest excluded whatever its status."
    )
    a(
        "- ECONI is a D-034 source (`docs/decisions.md:419`, `configs/base.yaml:25`, one edition only in the"
        " full corpus, none in the pilot); D-040's composition line does not mention it. Reported in full."
    )
    a("")
    # BUDGET
    a("## govinfo_budget")
    a("")
    a(
        f"- Packages in the window: {b['published_pre_snapshot']} · distinct series {b['distinct_series_pre']}"
        f" · latest per series {b['latest_per_series']}"
    )
    a(
        f"- Removed (series already in the pilot, every edition): {', '.join(b['removed_pilot_series']) or 'none'}"
    )
    a(
        f"- Candidates: {b['candidates']} · no resolvable pdfLink: {len(b['no_resolvable_pdflink'])}"
        f" · already in the manifest: {len(b['already_in_manifest'])} · **eligible: {len(b['eligible'])}**"
    )
    for x in b["no_resolvable_pdflink"]:
        a(f"  - unresolvable: {x}")
    g = b["gate"]
    a(
        f"- Unit-kind gate (as `run_listing` runs it, on the latest-per-series set): **{g['unit_kind']}-level**"
        f" · pdfLink {g['check1_pdflink']} · pages {g['check1_pages']} · self-contained {g['check2']}"
        f" · boundary {g['check3']}"
    )
    a(
        f"- Series with a newer edition after the snapshot: {', '.join(b['series_with_after_snapshot_edition']) or 'none'}"
    )
    a("")
    a(
        "| package id | series | title | dateIssued | pages | pdfLink source | est. parse 9–19 s/page |"
    )
    a("|---|---|---|---|---|---|---|")
    for r in sorted(b["eligible"], key=lambda r: r["pages"] or 0):
        p = r["pages"]
        t = f"{hrs(p * 9)}–{hrs(p * 19)}" if p else "pages unknown"
        a(
            f"| {r['package_id']} | {r['series']} | {r['title'][:60]} | {r['date_issued']} | {p} |"
            f" {r['pdf_link_source']} | {t} |"
        )
    a("")
    d = b["page_distribution"]
    a(
        "**Page distribution (eligible volumes, package metadata pages):** "
        + (
            f"n {d['n']} · min {d['min']} · Q1 {d['q1']} · median {d['median']} · Q3 {d['q3']} · max {d['max']}"
            if d
            else "none"
        )
    )
    a("")
    a("| page cap | volumes under the cap |")
    a("|---|---|")
    for k, v in b["page_caps"].items():
        a(f"| {k} | {v} |")
    if b["pages_missing"]:
        a("")
        a(f"Pages missing in metadata: {', '.join(b['pages_missing'])}")
    a("")
    a(
        "After snapshot (not eligible): "
        + (
            ", ".join(
                f"{r['package_id']} ({r['date_issued']}, {r['pages']})" for r in b["after_snapshot"]
            )
            or "none"
        )
    )
    a("")
    # ERP
    a("## govinfo_erp")
    a("")
    a(
        f"- One edition: **{e['one_edition']}** ({e['package_pages']} pages, {e['package_granules']} granules)."
        f" Other editions in the window (ineligible, one-edition rule):"
        f" {', '.join(r['package_id'] for r in e['editions_pre_snapshot'] if r['package_id'] != e['one_edition']) or 'none'}"
    )
    a(
        f"- Granule classes: {e['granule_classes']} · TABLE granules {e['table_granules']}"
        f" · removed (pilot): {', '.join(e['removed_pilot'])} · **eligible TABLE granules: {e['eligible_count']}**"
    )
    a(
        f"- **Pages are an ESTIMATE:** package pages ÷ granules = **{e['pages_estimate_per_granule']}** per granule."
        f" That estimate overstated the pilot (6 estimated vs 2 measured, D-034 status 2026-09-20 (d));"
        f" granule summaries carry `pages` for {e['metadata_pages_present']} of {e['eligible_count']}."
        f" Measured size is expected to be nearer 2 pages, i.e. ~{2 * 15} s/granule at 15.0 s/page."
    )
    a(f"- Granules without a pdfLink: {', '.join(e['no_pdflink']) or 'none'}")
    a("")
    a(
        "**Held-out set, `data/oracle/fresh/erp_draw.json` (D-039 rung-1b; burned for the oracle). Listed, not"
        " included or excluded:**"
    )
    a("")
    a(
        "| granule | in the eligible pool | local PDF (`data/raw_fresh`) | local xls (`data/oracle/fresh/erp`) |"
    )
    a("|---|---|---|---|")
    for h in e["held_out"]:
        a(
            f"| {h['granule_id']} | {'yes' if h['in_eligible_pool'] else 'no'} | {'yes' if h['local_pdf'] else 'no'}"
            f" | {'yes' if h['local_xls'] else 'no'} |"
        )
    a("")
    held = {h["granule_id"] for h in e["held_out"]}
    a("<details><summary>Eligible TABLE granules (est. pages, not measured)</summary>")
    a("")
    a("| granule | title | pages (metadata) | pages (estimate) | held-out |")
    a("|---|---|---|---|---|")
    for r in e["eligible"]:
        a(
            f"| {r['granule_id']} | {r['title'][:70]} | {r['pages_metadata']} | {r['pages_estimate']} |"
            f" {'yes' if r['granule_id'] in held else ''} |"
        )
    a("")
    a("</details>")
    a("")
    # ECONI
    a("## govinfo_econi (one edition only, D-034)")
    a("")
    a(
        f"- Packages in the window: {ec['published_pre_snapshot']} · series: {', '.join(ec['series_found']) or 'none'}"
    )
    ed = ec.get("edition")
    if ed:
        gt = ed["gate"]
        a(
            f"- **Latest pre-snapshot edition: {ed['package_id']}** · dateIssued {ed['date_issued']} ·"
            f" pages {ed['pages']} · granules {ed['granules']} · in manifest: {ed['in_manifest']}"
        )
        a(
            f"- Unit-kind gate (as `run_listing` decides): **{gt['unit_kind']}-level** · pdfLink {gt['check1_pdflink']}"
            f" · pages {gt['check1_pages']} · self-contained {gt['check2']} · boundary {gt['check3']}"
        )
        for x in gt["details"]:
            a(f"  - gate: {x}")
        if gt["unit_kind"] == "report":
            a(
                f"- pdfLink source: {ed.get('pdf_link_source')} · unresolvable: {ed.get('no_resolvable_pdflink') or 'none'}"
            )
            p = ed["pages"] or 0
            a(
                f"- **Parse-time ESTIMATE at 15.0 s/page:** {p} pages ≈ {p * 15:.0f} s ({hrs(p * 15)})"
            )
        else:
            a("")
            a(
                "| granule | class | title | pages (metadata) | pages (estimate) | pdfLink | in manifest |"
            )
            a("|---|---|---|---|---|---|---|")
            for gr in ed["granule_list"]:
                a(
                    f"| {gr['granule_id']} | {gr['class']} | {gr['title'][:60]} | {gr['pages_metadata']} |"
                    f" {gr['pages_estimate']} | {'yes' if gr['has_pdf_link'] else 'no'} | {gr['in_manifest']} |"
                )
            tot = sum((x["pages_metadata"] or x["pages_estimate"] or 0) for x in ed["granule_list"])
            a("")
            a(
                f"**Parse-time ESTIMATE at 15.0 s/page:** {tot} pages (metadata where present, else estimate)"
                f" ≈ {tot * 15:.0f} s ({hrs(tot * 15)}); one edition only, so this is the whole ECONI cost."
            )
    a("")
    a(
        "After snapshot (not eligible): "
        + (
            ", ".join(f"{r['package_id']} ({r['date_issued']})" for r in ec["after_snapshot"])
            or "none"
        )
    )
    a("")
    # EIA
    a("## eia")
    a("")
    a(
        f"- Frame: sitemap → three landing pages → PDF links (sitemap flags: {ei['sitemap']}). Frame units found:"
        f" {len(ei['frame_units'])} (MER sections + STEO full + AEO narrative)."
    )
    a("")
    a("| unit | series | MER excluded (D-040) | in manifest | eligible |")
    a("|---|---|---|---|---|")
    for r in ei["frame_units"]:
        ok = not r["mer_excluded"] and not r["in_manifest"]
        a(
            f"| {r['unit_id']} | {r['series']} | {r['mer_excluded']} | {r['in_manifest']} | {'**yes**' if ok else 'no'} |"
        )
    a("")
    a(f"**Eligible EIA units: {len(ei['eligible'])}.**")
    a("")
    extras = ei["other_pdf_links_outside_frame"]
    if extras:
        by_land: dict[str, list[dict]] = {}
        for x in extras:
            by_land.setdefault(x["landing"], []).append(x)
        a(
            "Other PDF links on the landing pages, outside the frame filter (information only; not part of the"
            " D-034 frame, not eligible unless the frame is widened). Counts per landing page:"
        )
        a("")
        for land, xs in by_land.items():
            dis = sum(1 for x in xs if x["robots_disallowed"])
            tag = " (all MER, excluded by D-040)" if land == "mer" else ""
            a(f"- {land}: {len(xs)} links{tag}; robots-disallowed {dis}")
        for land, xs in by_land.items():
            if land != "mer":
                for x in xs:
                    a(f"  - {land}: {x['url']}")
        a("")
        a(
            "The full list is in `reports/full_corpus_pools.json` (`eia.other_pdf_links_outside_frame`)."
        )
    else:
        a("No other PDF links on the three landing pages.")
    a("")
    # CBO
    a("## cbo_manual")
    a("")
    a(
        f"- `data/manual/cbo/sources.csv` (utf-8-sig): **{c['sources_csv_rows']} rows**, {c['sources_csv_in_manifest']}"
        f" already in the manifest."
    )
    a(
        f"- Local frame files (`data/frames/frame_<year>.html`, parsed read-only): {c['frame_candidates']} candidates,"
        f" **{c['frame_candidates_not_in_manifest']} not in the manifest**. cbo.gov is never contacted by script;"
        " acquisition stays the owner's, so pages are unknown until fetched (pilot CBO units: "
        f"{c['pilot_cbo_pages']} pages)."
    )
    a("")
    a("<details><summary>Frame candidates not in the manifest</summary>")
    a("")
    for x in c["not_in_manifest"]:
        a(f"- {x['unit_id']} · {x['frame_year']} · {x['date_issued']} · {x['title'][:80]}")
    a("")
    a("</details>")
    a("")
    # estimates
    a("## Parse-time ESTIMATES (not measurements)")
    a("")
    a(
        "Rates from `docs/plan.md` T3: BUDGET 9–19 s/page, CBO 2.5–5 s/page, 15.0 s/page otherwise. Pages are"
        " package metadata (BUDGET, ECONI), the ERP per-granule estimate (overstated on the pilot), and for CBO"
        " the pilot's mean pages × the candidates not yet in the manifest. Pools, not draws."
    )
    a("")
    a("| source | pool pages (estimate) | parse, low | parse, high |")
    a("|---|---|---|---|")
    for k, v in R["estimates"].items():
        a(f"| {k} | {v['pages']} | {hrs(v['s_low'])} | {hrs(v['s_high'])} |")
    a("")
    a("BUDGET pages exclude packages whose metadata carries none (listed in the BUDGET section).")
    a("")
    n = R["night_pages"]
    a(
        f"**An 8-hour overnight parse fits ≈ {n['budget_at_9']:,} BUDGET pages at 9 s/page and"
        f" ≈ {n['budget_at_19']:,} pages at 19 s/page.**"
    )
    a("")
    a(
        "A unit can still be excluded at fetch under the image-only rule (D-034 status 2026-10-02: ≥ 1 image and"
        " ≤ 20 words on ≥ 25 % of pages), with **no replacement draw**, so the realised unit count can fall"
        " below the draw."
    )
    a("")
    a("## HTTP calls")
    a("")
    a(
        f"Total **{R['http']['calls']}** GETs through `Fetcher` (robots.txt GETs, one per host, are not counted by it):"
    )
    a("")
    for h, n_ in R["http"]["by_host"].items():
        a(f"- {h}: {n_}")
    a("- www.cbo.gov / www.gao.gov: 0 (never contacted)")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
