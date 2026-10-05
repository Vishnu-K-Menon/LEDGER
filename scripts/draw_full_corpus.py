# ruff: noqa: E501
"""D-034 status 2026-10-04: the full-corpus draw. A one-off script, NOT a CLI stage.

    uv run python scripts/draw_full_corpus.py --pools   # phase A: recompute the pools, assert they
                                                        # equal the e1a9618 listing, write the record
    # ... commit data/draw_20261004.json ...
    uv run python scripts/draw_full_corpus.py --draw    # phase B: draw, append rows (append-only)

Seed 20261004, salt = source key (``draw.seeded``). Counts: BUDGET every eligible volume under the
page cap (no draw: all taken), ERP 10 of 59, CBO 11 of 36, ECONI 0, EIA 0, CRPT 0. Phase B refuses
unless the record is committed and unmodified, and never redraws (it refuses if any drawn id is
already in the manifest). The manifest is appended to, never rewritten: every existing byte is
asserted identical before and after.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ledger.config import load_config  # noqa: E402
from ledger.ingest.draw import draw, seeded  # noqa: E402
from ledger.ingest.frames import parse_frames  # noqa: E402
from ledger.ingest.govinfo import NON_CONTENT_CLASSES, GovInfo, Package  # noqa: E402
from ledger.ingest.http import Fetcher, govinfo_api_key  # noqa: E402
from ledger.ingest.listing import _pkg_row, _row, resolvable_reports  # noqa: E402
from ledger.ingest.manifest import ManifestRow, read_manifest  # noqa: E402
from ledger.ingest.sources import load_sources  # noqa: E402

SEED = 20261004
SNAPSHOT = "2026-09-20"
PAGE_CAP = 200
COUNTS = {"govinfo_budget": None, "govinfo_erp": 10, "cbo_manual": 11}  # None = all under the cap
RECORD = REPO / "data" / "draw_20261004.json"
LISTING = REPO / "reports" / "full_corpus_pools.json"
MANIFEST = REPO / "data" / "manifest.jsonl"
ONE_THIRD = 1 / 3


def sha(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    return r.stdout.strip()


def compute_pools(cfg, gi: GovInfo, in_manifest: set[str], pilot_pkgs, pilot_gids):
    """The same read-only calls and rules as ``scripts/list_full_corpus.py`` (e1a9618)."""
    start = cfg.fetch.date_range[0]
    pre = gi.published("BUDGET", start, SNAPSHOT)
    latest = gi.latest_per_series(pre)
    pilot_series = {
        GovInfo.series_key(Package(p, "", "", "")) for p in pilot_pkgs if p.startswith("BUDGET-")
    }
    cand = [p for p in latest if GovInfo.series_key(p) not in pilot_series]
    granules = {}
    for p in cand:
        gi.package_summary(p)
        granules[p.package_id] = gi.granules(p)
    keep, links, _unres = resolvable_reports(gi, cand, granules)
    budget = [p for p in keep if f"govinfo-{p.package_id}" not in in_manifest]

    erp_pre = gi.published("ERP", start, SNAPSHOT)
    erp_pkg = gi.latest_per_series(erp_pre)[0]
    gi.package_summary(erp_pkg)
    erp_gr = gi.granules(erp_pkg)
    tables = [
        g
        for g in erp_gr
        if g.granule_class not in NON_CONTENT_CLASSES and g.granule_class.upper() == "TABLE"
    ]
    erp = [g for g in tables if g.granule_id not in pilot_gids]

    cands = parse_frames(REPO / "data" / "frames")
    cbo = [c for c in cands if f"cbo-{c.publication_id}" not in in_manifest]
    return budget, links, erp_pkg, erp_gr, erp, cbo


def phase_a() -> None:
    cfg = load_config(REPO / "configs" / "base.yaml")
    _, mrows = read_manifest(MANIFEST)
    in_manifest = {r.unit_id for r in mrows}
    pilot_pkgs = {r.package_id for r in mrows if r.package_id}
    pilot_gids = {r.granule_id for r in mrows if r.granule_id}
    fetcher = Fetcher(cfg.fetch)
    gi = GovInfo(fetcher, cfg.fetch, govinfo_api_key())
    budget, _links, erp_pkg, _gr, erp, cbo = compute_pools(
        cfg, gi, in_manifest, pilot_pkgs, pilot_gids
    )
    listing = json.loads(LISTING.read_text("utf-8"))
    want = {
        "govinfo_budget": sorted(r["package_id"] for r in listing["budget"]["eligible"]),
        "govinfo_erp": sorted(r["granule_id"] for r in listing["erp"]["eligible"]),
        "cbo_manual": sorted(r["unit_id"] for r in listing["cbo"]["not_in_manifest"]),
    }
    got = {
        "govinfo_budget": sorted(p.package_id for p in budget),
        "govinfo_erp": sorted(g.granule_id for g in erp),
        "cbo_manual": sorted(f"cbo-{c.publication_id}" for c in cbo),
    }
    diffs = {
        k: {
            "only_now": sorted(set(got[k]) - set(want[k])),
            "only_e1a9618": sorted(set(want[k]) - set(got[k])),
        }
        for k in want
        if got[k] != want[k]
    }
    if diffs:
        print(json.dumps(diffs, indent=1))
        raise SystemExit("STOP: the recomputed pools differ from the e1a9618 listing")
    cap_sel = sorted(p.package_id for p in budget if p.pages is None or p.pages < PAGE_CAP)
    rec = {
        "decision": "D-034 status 2026-10-04 (owner; full-corpus mix); pools equal the e1a9618 listing",
        "seed": SEED,
        "snapshot_cutoff": SNAPSHOT,
        "draw_key": "ids sorted as strings, then random.Random(f'{seed}:{salt}').sample (ledger/ingest/draw.py)",
        "sources": {
            "govinfo_budget": {
                "salt": "govinfo_budget",
                "rule": f"every eligible volume with package metadata pages < {PAGE_CAP}; "
                "no metadata pages (BUDGET-2025-CLIMATE) is taken pending measured pages at fetch",
                "n_drawn": len(cap_sel),
                "pool_ids": got["govinfo_budget"],
                "pool_sha256": sha(got["govinfo_budget"]),
                "pool_pages": {p.package_id: p.pages for p in budget},
                "selected_by_cap": cap_sel,
            },
            "govinfo_erp": {
                "salt": "govinfo_erp",
                "n_drawn": COUNTS["govinfo_erp"],
                "package": erp_pkg.package_id,
                "pool_ids": got["govinfo_erp"],
                "pool_sha256": sha(got["govinfo_erp"]),
            },
            "cbo_manual": {
                "salt": "cbo_manual",
                "n_drawn": COUNTS["cbo_manual"],
                "pool_ids": got["cbo_manual"],
                "pool_sha256": sha(got["cbo_manual"]),
            },
            "govinfo_econi": {"n_drawn": 0, "note": "0 in v1 (D-034 status 2026-10-04 (3))"},
            "eia": {"n_drawn": 0, "note": "pool empty after D-040"},
            "govinfo_crpt": {"n_drawn": 0},
        },
        "manifest_sha256_before_draw": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "http_calls_by_host": dict(fetcher.calls_by_host),
    }
    RECORD.write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {k: (v.get("n_drawn"), len(v.get("pool_ids", []))) for k, v in rec["sources"].items()}
        )
    )
    print("pools equal the e1a9618 listing; record written:", RECORD.relative_to(REPO))


def counted(rows: list[ManifestRow]) -> list[ManifestRow]:
    """D-034 status 2026-10-04 (0): ACTIVE plus pending rows; UNFETCHABLE and EXCLUDED not counted."""
    return [
        r for r in rows if r.status == "ACTIVE" and not any("UNFETCHABLE" in n for n in r.notes)
    ]


def publication(r: ManifestRow) -> str:
    return r.package_id if r.source.startswith("govinfo") and r.package_id else r.unit_id


def shares(rows: list[ManifestRow]) -> dict[str, tuple[int, float]]:
    cs = counted(rows)
    out: dict[str, int] = {}
    for r in cs:
        out[publication(r)] = out.get(publication(r), 0) + 1
    return {k: (v, v / len(cs)) for k, v in sorted(out.items(), key=lambda kv: -kv[1])}


def phase_b() -> None:
    rel = RECORD.relative_to(REPO).as_posix()
    if not git("ls-files", rel):
        raise SystemExit(f"STOP: {rel} is not committed")
    if git("status", "--porcelain", "--", rel):
        raise SystemExit(f"STOP: {rel} differs from the committed copy")
    rec = json.loads(RECORD.read_text("utf-8"))
    before = MANIFEST.read_bytes()
    if hashlib.sha256(before).hexdigest() != rec["manifest_sha256_before_draw"]:
        raise SystemExit("STOP: the manifest changed since the pools were recorded")
    cfg = load_config(REPO / "configs" / "base.yaml")
    header, mrows = read_manifest(MANIFEST)
    in_manifest = {r.unit_id for r in mrows}
    S = rec["sources"]
    drawn_ids: dict[str, list[str]] = {
        "govinfo_budget": S["govinfo_budget"]["selected_by_cap"],
        "govinfo_erp": draw(
            S["govinfo_erp"]["pool_ids"],
            S["govinfo_erp"]["n_drawn"],
            seeded(rec["seed"], "govinfo_erp"),
            key=str,
        ),
        "cbo_manual": draw(
            S["cbo_manual"]["pool_ids"],
            S["cbo_manual"]["n_drawn"],
            seeded(rec["seed"], "cbo_manual"),
            key=str,
        ),
    }
    unit_ids = [
        f"govinfo-{i}" if k == "govinfo_budget" else (f"govinfo-{i}" if k == "govinfo_erp" else i)
        for k, ids in drawn_ids.items()
        for i in ids
    ]
    if any(u in in_manifest for u in unit_ids):
        raise SystemExit("STOP: a drawn unit is already in the manifest (never redraw)")

    sources = load_sources(REPO / "data" / "sources.yaml", stage="list")
    pol = sources.get("govinfo")
    purl, pnote = (pol.policy_url, pol.policy_note) if pol else (None, None)
    cbo_pol = sources.get("cbo")
    cpurl, cpnote = (cbo_pol.policy_url, cbo_pol.policy_note) if cbo_pol else (None, None)
    fetcher = Fetcher(cfg.fetch)
    gi = GovInfo(fetcher, cfg.fetch, govinfo_api_key())
    new_rows: list[ManifestRow] = []

    # BUDGET: report-level rows, pdfLink resolved as the listing does
    pkgs = []
    for pid in drawn_ids["govinfo_budget"]:
        p = Package(pid, "", "", "")
        # package_summary fills pages / pdfLink / title; date_issued comes from /published
        pkgs.append(p)
    pub = {p.package_id: p for p in gi.published("BUDGET", cfg.fetch.date_range[0], SNAPSHOT)}
    pkgs = [pub[p.package_id] for p in pkgs]
    for p in pkgs:
        gi.package_summary(p)
    gr = {p.package_id: gi.granules(p) for p in pkgs}
    keep, links, unres = resolvable_reports(gi, pkgs, gr)
    assert not unres and len(keep) == len(pkgs), unres
    for p in pkgs:
        new_rows.append(_pkg_row(p, "govinfo_budget", SNAPSHOT, purl, pnote, links[p.package_id]))

    # ERP: granule rows (pages estimated until fetch measures them)
    erp_pkg = gi.package_summary(
        next(
            p
            for p in gi.published("ERP", cfg.fetch.date_range[0], SNAPSHOT)
            if p.package_id == S["govinfo_erp"]["package"]
        )
    )
    erp_gr = {g.granule_id: g for g in gi.granules(erp_pkg)}
    est = max(1, round(erp_pkg.pages / erp_pkg.granule_count)) if erp_pkg.pages else None
    for gid in drawn_ids["govinfo_erp"]:
        g = erp_gr[gid]
        gi.granule_summary(g)
        new_rows.append(
            _row(
                unit_id=f"govinfo-{g.granule_id}",
                source="govinfo_erp",
                parent_series=erp_pkg.title,
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
                snapshot_date=SNAPSHOT,
                policy_url=purl,
                policy_note=pnote,
                notes=[f"granuleClass={g.granule_class}"],
            )
        )

    # CBO: pending owner fetch (cbo.gov is never contacted)
    cands = {f"cbo-{c.publication_id}": c for c in parse_frames(REPO / "data" / "frames")}
    for uid in drawn_ids["cbo_manual"]:
        c = cands[uid]
        new_rows.append(
            _row(
                unit_id=uid,
                source="cbo_manual",
                parent_series="CBO cost estimates",
                unit_kind="report",
                fetch_method="manual",
                title=c.title,
                date_issued=c.date_issued,
                url=None,
                page_url=c.page_url,
                snapshot_date=SNAPSHOT,
                policy_url=cpurl,
                policy_note=cpnote,
                notes=[
                    "second hop is the owner's: open page_url, download the PDF, "
                    "fill data/manual/cbo/sources.csv"
                ],
            )
        )

    pre_sh = shares([*mrows, *new_rows])
    pre_top = next(iter(pre_sh.items()))
    if pre_top[1][1] > ONE_THIRD:
        raise SystemExit(
            f"STOP before writing: {pre_top[0]} exceeds one third of the counted units"
        )

    appended = "".join(r.model_dump_json() + "\n" for r in new_rows).encode("utf-8")
    assert before.endswith(b"\n")
    with MANIFEST.open("ab") as fh:
        fh.write(appended)
    after = MANIFEST.read_bytes()
    assert after.startswith(before) and after[len(before) :] == appended, "existing bytes changed"
    old_lines = before.splitlines(keepends=True)
    assert after.splitlines(keepends=True)[: len(old_lines)] == old_lines

    _, all_rows = read_manifest(MANIFEST)
    sh = shares(all_rows)
    cs = counted(all_rows)
    top = next(iter(sh.items()))
    held = json.loads((REPO / "data/oracle/fresh/erp_draw.json").read_text("utf-8"))
    held_ids = {d["granule_id"] for d in held["drawn"]}
    erp_drawn_held = sorted(set(drawn_ids["govinfo_erp"]) & held_ids)
    out = {
        "drawn": drawn_ids,
        "d039_held_out_drawn": erp_drawn_held,
        "counted_units": len(cs),
        "shares": {k: {"units": v[0], "share": round(v[1], 4)} for k, v in sh.items() if v[0] > 1},
        "max_publication": {top[0]: {"units": top[1][0], "share": round(top[1][1], 4)}},
        "manifest_sha256_after": hashlib.sha256(after).hexdigest(),
        "http_calls_by_host": dict(fetcher.calls_by_host),
    }
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pools", action="store_true")
    g.add_argument("--draw", action="store_true")
    a = ap.parse_args()
    phase_a() if a.pools else phase_b()
