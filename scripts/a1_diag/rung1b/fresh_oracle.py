"""D-039 item 2 - the FRESH held-out set: fetch, hash, and the STEO aug26 admission (counts only).

Nothing fresh is printed beyond counts and coverage (D-039: nobody opens a fresh page or parse
before the evaluation); page text is read programmatically only (table ids and heading-title
checks, the frozen STEO rule).

``--fetch`` (https only, through ``ledger.ingest.http.Fetcher``):
* MER sections 2, 5, 6, 7, 9, 10, 12 (``totalenergy/data/monthly/pdf/secN.pdf``) to
  ``data/raw_fresh/eia/eia-pdf-secN.pdf`` (``parse.py:258``'s layout); the PDF edition
  (``fetch.pdf_date``); each page's printed table id from the text-layer page top; one per-table
  export ``xls.php?tbl=`` per id (``oracle.mer_tbl``), title-verified exactly as ``oracle.py``
  (>= 80 % word overlap with the page heading) and its release date (``oracle.release_of``);
* the 8 drawn ERP granules (``data/oracle/fresh/erp_draw.json``): the PDF through the GovInfo API
  (key from the environment) to ``data/raw_fresh/govinfo_erp/govinfo-<gid>.pdf``, the granule's
  ``download.xlsLink``, the keyless MODS ``dateIssued``, the self-containment check (verdict only);
* STEO ``outlooks/steo/archives/aug26.pdf`` to ``data/raw_fresh/eia/eia-archives-aug26.pdf``.
Writes the tracked ``data/oracle/fresh/{mer,erp,steo}/sources.json`` and the local
``data/manifest_fresh.jsonl`` (the fresh units, for the parse).

``--steo``: the FROZEN whole-row rule (``steo.admit_table_rows``, admission_rule.md) against the
FROZEN September snapshot, on the aug26 page text (``steo.HELD_PDF`` patched in-process; steo.py
is not edited). Cells go to the local ``data/oracle/fresh/steo/cells.jsonl`` (sha256 in
sources.json); the report ``reports/a1_diag/rung1b/fresh_steo_admission.md`` carries counts only.

MER / ERP admission is built AFTER the fresh parse (owner ruling), from each TableItem's bbox
only, and committed + hashed with the checker before any rung-1b output exists.

    uv run --with pdfplumber --with openpyxl python scripts/a1_diag/rung1b/fresh_oracle.py --fetch
    uv run --with pdfplumber python scripts/a1_diag/rung1b/fresh_oracle.py --steo
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(REPO))
import oracle as orc  # noqa: E402

RAW = REPO / "data" / "raw_fresh"
FRESH = REPO / "data" / "oracle" / "fresh"
REPORT = REPO / "reports" / "a1_diag" / "rung1b"
MER_SECTIONS = (2, 5, 6, 7, 9, 10, 12)
MER_PDF = "https://www.eia.gov/totalenergy/data/monthly/pdf/sec{n}.pdf"
STEO_URL = "https://www.eia.gov/outlooks/steo/archives/aug26.pdf"
STEO_UNIT = "eia-archives-aug26"
MODS = "https://www.govinfo.gov/metadata/granule/{pkg}/{gid}/mods.xml"


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def https(url: str) -> str:
    assert url.startswith("https://"), url
    return url


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


# D-038 third-revision bug fix of the scan (D-039 status 2026-09-30, ruling 2): MER appendix tables
# are printed "Table B1."-style; the scan accepts a letter id ([A-Z][0-9]+) as well as digits.digits
# (orc.TABLE_ID, which the burned pilot oracle keeps). Parameter-free: dictated by the printed
# format.
SCAN_ID_V1 = orc.TABLE_ID
SCAN_ID = re.compile(r"\s*Table\s+([0-9]+\.[0-9]+[a-z]?|[A-Z][0-9]+)\b")


def page_ids(pdf_path: Path, pattern: re.Pattern = SCAN_ID) -> list[tuple[int, str, str]]:
    """(page, printed table id, heading line) from the text layer's page top: the first line
    within the top quarter of the page that starts with 'Table <id>'."""
    import pdfplumber

    out = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            words = [w for w in page.extract_words(x_tolerance=1) if w["top"] < page.height / 4]
            for ln in orc.cluster(words):
                text = " ".join(w["text"] for w in ln)
                m = pattern.match(text)
                if m:
                    out.append((i, m.group(1), text))
                    break
    return out


def export_tbl(table_id: str) -> str:
    """xls.php ``tbl`` for a printed id: digits.digits via ``orc.mer_tbl``; a letter id as T<id>."""
    return f"T{table_id}" if re.fullmatch(r"[A-Z][0-9]+", table_id) else orc.mer_tbl(table_id)


def candidates(table_id: str) -> list[str]:
    return [table_id] if re.fullmatch(r"[A-Z][0-9]+", table_id) else orc.id_candidates(table_id)


def scan_unit(unit, dest, fetcher, mer, src_dir, releases, pattern=SCAN_ID) -> None:
    """One section's scan: page headings -> per-table export, title-verified as oracle.py does."""
    seen_ids: dict[str, dict] = {}
    for page, tid, heading in page_ids(dest, pattern):
        if tid in seen_ids:
            mer["pages"].append(
                {
                    "unit": unit,
                    "page": page,
                    "table_id": tid,
                    "export": seen_ids[tid].get("tbl"),
                    "title_match": seen_ids[tid].get("title_match"),
                }
            )
            continue
        got: dict = {"tbl": None, "title_match": False, "note": ""}
        for cand in candidates(tid):
            tbl = export_tbl(cand)
            xurl = https(orc.MER_URL.format(tbl=tbl))
            path = src_dir / f"{tbl}.xlsx"
            fetcher.download(xurl, path, source="eia")
            b = path.read_bytes()
            xrec = {
                "url": xurl,
                "path": path.relative_to(REPO).as_posix(),
                "sha256": hashlib.sha256(b).hexdigest(),
                "bytes": len(b),
                "type": orc.sniff(b),
                "fetched_at": now(),
                "table_id": cand,
                "table_id_printed": tid,
                "pdf_unit": unit,
            }
            mer["exports"][xurl] = xrec
            if not xrec["type"].startswith("OOXML"):
                got["note"] = f"export {tbl} is {xrec['type']}"
                continue
            title = orc.export_title(path)
            xrec["export_title"] = title
            pw, ow = orc.title_words(heading), orc.title_words(title)
            if (pw and ow and len(pw & ow) >= 0.8 * min(len(pw), len(ow))) or (
                not pw and title.startswith(f"Table {cand} ")
            ):
                xrec["release"] = orc.mer_oracle(path).release
                releases.add(xrec["release"])
                got = {"tbl": tbl, "title_match": True, "note": ""}
                break
            got["note"] = f"export {tbl} title does not match the page heading"
        seen_ids[tid] = got
        mer["pages"].append(
            {
                "unit": unit,
                "page": page,
                "table_id": tid,
                "export": got["tbl"],
                "title_match": got["title_match"],
                "note": got["note"],
            }
        )


def rescan() -> int:
    """Rerun ONLY the scan and export match on the PDFs already on disk (no PDF refetch, nothing
    from the parse); keep the v1 scan's results beside the fixed scan's."""
    from ledger.config import load_config
    from ledger.ingest.http import Fetcher

    fetcher = Fetcher(load_config().fetch)
    path = FRESH / "mer" / "sources.json"
    mer = json.loads(path.read_text(encoding="utf-8"))
    mer.setdefault("pages_scan_v1", mer["pages"])
    v1 = mer["pages_scan_v1"]
    mer["pages"], releases = [], set(mer.get("export_releases", []))
    src_dir = FRESH / "mer" / "src"
    for n in MER_SECTIONS:
        unit = f"eia-pdf-sec{n}"
        scan_unit(unit, RAW / "eia" / f"{unit}.pdf", fetcher, mer, src_dir, releases)
    mer["export_releases"] = sorted(releases)

    def ids(pages):
        return {(p["unit"], p["table_id"]) for p in pages if p.get("title_match")}

    mer["scan"] = {
        "fix": "D-038 third-revision bug fix (D-039 status 2026-09-30): letter ids accepted",
        "pattern_v1": SCAN_ID_V1.pattern,
        "pattern": SCAN_ID.pattern,
        "fresh_oracle_py_sha256": sha_file(Path(__file__)),
        "matched_tables_v1": len(ids(v1)),
        "matched_tables": len(ids(mer["pages"])),
        "added": sorted(f"{u}:{t}" for u, t in ids(mer["pages"]) - ids(v1)),
        "removed": sorted(f"{u}:{t}" for u, t in ids(v1) - ids(mer["pages"])),
        "rescanned_at": now(),
        "http_calls_by_host": fetcher.calls_by_host,
    }
    path.write_text(json.dumps(mer, indent=1) + "\n", encoding="utf-8")
    sc = mer["scan"]
    print(f"matched tables: v1 scan {sc['matched_tables_v1']} -> fixed scan {sc['matched_tables']}")
    print("added:", sc["added"])
    print("removed:", sc["removed"])
    unmatched = [
        (p["unit"], p["page"], p["table_id"], p.get("note", "")[:45])
        for p in mer["pages"]
        if not p.get("title_match")
    ]
    print("unmatched pages:", unmatched)
    print("hosts:", fetcher.calls_by_host)
    return 0


def pdf_record(dest: Path, url: str) -> dict:
    from ledger.ingest.fetch import pdf_date, pdf_pages_and_text_ratio

    pages, ratio, _ = pdf_pages_and_text_ratio(dest)
    date, how = pdf_date(dest)
    return {
        "url": url,
        "path": dest.relative_to(REPO).as_posix(),
        "sha256": sha_file(dest),
        "bytes": dest.stat().st_size,
        "pages": pages,
        "text_layer_ratio": round(ratio, 4),
        "pdf_edition_date": date,
        "pdf_edition_source": how,
        "fetched_at": now(),
    }


def fetch_all() -> int:
    from ledger.config import load_config
    from ledger.ingest.fetch import erp_self_containment, pdf_pages_and_text_ratio
    from ledger.ingest.http import Fetcher, govinfo_api_key
    from ledger.ingest.manifest import ManifestHeader, ManifestRow, read_manifest, write_manifest

    cfg = load_config()
    fetcher = Fetcher(cfg.fetch)
    today = dt.date.today().isoformat()
    _, corpus_rows = read_manifest(REPO / "data" / "manifest.jsonl")
    policy = {r.source: (r.policy_url, r.policy_note) for r in corpus_rows}
    rows: list[ManifestRow] = []

    # ---- MER -----------------------------------------------------------------------------
    mer = {"tag": "", "pdfs": {}, "exports": {}, "pages": []}
    src_dir = FRESH / "mer" / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    releases = set()
    for n in MER_SECTIONS:
        url = https(MER_PDF.format(n=n))
        unit = f"eia-pdf-sec{n}"
        dest = RAW / "eia" / f"{unit}.pdf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        fetcher.download(url, dest, source="eia")
        rec = pdf_record(dest, url)
        mer["pdfs"][unit] = rec
        rows.append(
            ManifestRow(
                unit_id=unit,
                source="eia",
                parent_series="Monthly Energy Review",
                unit_kind="granule",
                fetch_method="direct",
                title=f"MER section {n}",
                date_issued=rec["pdf_edition_date"],
                url=url,
                pages=rec["pages"],
                pages_source="measured",
                text_layer_ratio=rec["text_layer_ratio"],
                sha256=rec["sha256"],
                snapshot_date=today,
                policy_url=policy["eia"][0],
                policy_note=policy["eia"][1],
                notes=["D-039 fresh held-out set (not corpus)"],
            )
        )
        scan_unit(unit, dest, fetcher, mer, src_dir, releases)
    mer["export_releases"] = sorted(releases)
    mer["pdf_editions"] = sorted({r["pdf_edition_date"] for r in mer["pdfs"].values()})
    mer["tag"] = (
        f"MER fresh sections {MER_SECTIONS}, PDF editions {mer['pdf_editions']}, "
        f"export releases {mer['export_releases']}"
    )

    # ---- ERP -----------------------------------------------------------------------------
    draw = json.loads((FRESH / "erp_draw.json").read_text(encoding="utf-8"))
    key = govinfo_api_key()  # environment only; never written anywhere
    erp = {"tag": "ERP-2026 fresh granules (D-039 draw, seed 20260930)", "granules": {}}
    (FRESH / "erp").mkdir(parents=True, exist_ok=True)
    corpus_erp = next(r for r in corpus_rows if r.source == "govinfo_erp")
    for g in draw["drawn"]:
        gid = g["granule_id"]
        unit = f"govinfo-{gid}"
        pdf_url = https(f"https://api.govinfo.gov/packages/{draw['package']}/granules/{gid}/pdf")
        dest = RAW / "govinfo_erp" / f"{unit}.pdf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        fetcher.download(pdf_url, dest, source="govinfo", params={"api_key": key})
        rec = pdf_record(dest, pdf_url)
        xls = FRESH / "erp" / f"{gid}.xls"
        fetcher.download(https(g["xls_link"]), xls, source="govinfo", params={"api_key": key})
        xb = xls.read_bytes()
        mods = FRESH / "erp" / f"{gid}.mods.xml"
        fetcher.download(https(MODS.format(pkg=draw["package"], gid=gid)), mods, source="govinfo")
        issued = re.search(r"<dateIssued[^>]*>([^<]+)</dateIssued>", mods.read_text("utf-8"))
        _, _, texts = pdf_pages_and_text_ratio(dest)
        check = erp_self_containment(unit, g["title"], texts)
        erp["granules"][gid] = {
            **rec,
            "xls_url": g["xls_link"],
            "xls_path": xls.relative_to(REPO).as_posix(),
            "xls_sha256": hashlib.sha256(xb).hexdigest(),
            "xls_type": orc.sniff(xb),
            "mods_sha256": sha_file(mods),
            "date_issued_mods": issued.group(1) if issued else None,
            "self_containment_failed": check.failed,
        }
        rows.append(
            ManifestRow(
                unit_id=unit,
                source="govinfo_erp",
                parent_series=corpus_erp.parent_series,
                unit_kind="granule",
                fetch_method="govinfo",
                title=g["title"],
                date_issued=issued.group(1) if issued else None,
                url=pdf_url,
                package_id=draw["package"],
                granule_id=gid,
                pages=rec["pages"],
                pages_source="measured",
                text_layer_ratio=rec["text_layer_ratio"],
                sha256=rec["sha256"],
                snapshot_date=today,
                policy_url=corpus_erp.policy_url,
                policy_note=corpus_erp.policy_note,
                notes=[
                    "granuleClass=TABLE",
                    "D-039 fresh held-out set (not corpus)",
                    f"fetch: ERP self-containment failed={check.failed}",
                ],
            )
        )

    # ---- STEO aug26 ----------------------------------------------------------------------
    dest = RAW / "eia" / f"{STEO_UNIT}.pdf"
    fetcher.download(https(STEO_URL), dest, source="eia")
    srec = pdf_record(dest, STEO_URL)
    steo_src = {
        "tag": "STEO aug26 (archives), admitted against the FROZEN 2026-09 snapshot",
        "pdf": srec,
        "snapshot": "data/oracle/steo/2026-09 (frozen)",
    }
    rows.append(
        ManifestRow(
            unit_id=STEO_UNIT,
            source="eia",
            parent_series="Short-Term Energy Outlook",
            unit_kind="report",
            fetch_method="direct",
            title="STEO August 2026 (archives)",
            date_issued=srec["pdf_edition_date"],
            url=STEO_URL,
            pages=srec["pages"],
            pages_source="measured",
            text_layer_ratio=srec["text_layer_ratio"],
            sha256=srec["sha256"],
            snapshot_date=today,
            policy_url=policy["eia"][0],
            policy_note=policy["eia"][1],
            notes=["D-039 fresh held-out set (not corpus)"],
        )
    )

    for fam, body in (("mer", mer), ("erp", erp), ("steo", steo_src)):
        body["http_calls_by_host"] = fetcher.calls_by_host
        (FRESH / fam).mkdir(parents=True, exist_ok=True)
        (FRESH / fam / "sources.json").write_text(json.dumps(body, indent=1) + "\n", "utf-8")
    header = ManifestHeader(
        selection_seed=20260930,
        snapshot_date=today,
        frames={
            "eia": "MER sections 2,5,6,7,9,10,12 + STEO archives/aug26 (D-039)",
            "govinfo": "ERP-2026 TABLE granules with xlsLink, draw seed 20260930 (D-039)",
        },
        pilot_composition={"eia": len(MER_SECTIONS) + 1, "govinfo_erp": len(draw["drawn"])},
    )
    write_manifest(REPO / "data" / "manifest_fresh.jsonl", header, rows)
    print(
        f"MER: {len(mer['pdfs'])} PDFs, {len(mer['pages'])} table pages, "
        f"{sum(1 for p in mer['pages'] if p['title_match'])} matched to an export, "
        f"{len({x['table_id'] for x in mer['exports'].values()})} exports fetched; "
        f"PDF editions {mer['pdf_editions']}; export releases {mer['export_releases']}"
    )
    print(
        f"ERP: {len(erp['granules'])} granules; self-containment failed: "
        f"{sum(g['self_containment_failed'] for g in erp['granules'].values())}; "
        f"dateIssued {sorted({g['date_issued_mods'] for g in erp['granules'].values()})}"
    )
    print(f"STEO: {srec['pages']} pages, edition {srec['pdf_edition_date']}")
    print("hosts:", fetcher.calls_by_host)
    return 0


def steo_admission() -> int:
    import steo
    import steo_footnotes

    pdf = RAW / "eia" / f"{STEO_UNIT}.pdf"
    steo.HELD_PDF = pdf  # in-process only: the frozen rule reads this page text
    import pdfplumber

    cands = []
    with pdfplumber.open(pdf) as doc:
        for i, page in enumerate(doc.pages, 1):
            words = [w for w in page.extract_words(x_tolerance=1) if w["top"] < page.height / 4]
            for ln in orc.cluster(words):
                m = steo_footnotes.TABLE_HEAD.match(" ".join(w["text"] for w in ln))
                if m and (m.group(1) in steo.VIEW_OF_TABLE or m.group(1) == "8"):
                    cands.append((i, m.group(1)))
                    break
    # the data-table block: from the LAST "Table 1." page on (narrative tables precede it)
    first = max((p for p, t in cands if t == "1"), default=0)
    pages = [(p, t) for p, t in cands if p >= first]
    rows_out, cells_all, unreadable = [], [], []
    for k, (page, tid) in enumerate(pages):
        try:
            res = steo.admit_table_rows(STEO_UNIT, 1000 + k, page, tid, steo_footnotes.view_of(tid))
        except Exception as exc:  # noqa: BLE001 - an unreadable page is a count, not a crash
            unreadable.append({"page": page, "table_id": tid, "error": type(exc).__name__})
            continue
        cells = res["cells"]
        cells_all.extend(cells)
        adm = [c for c in cells if c["admitted"]]
        status = Counter(r["status"] for r in res["rows"])
        rows_out.append(
            {
                "table_id": tid,
                "page": page,
                "printed_rows": len(res["rows"]),
                "admitted_rows": status.get("admitted", 0),
                "rejected_unmapped_a": status.get("not admitted: unmapped (a)", 0),
                "rejected_tie_b": status.get("not admitted: tie (b)", 0),
                "rejected_content_c": status.get("not admitted: content (c)", 0),
                "cells": len(cells),
                "admitted_cells": len(adm),
                "coverage": round(len(adm) / len(cells), 4) if cells else None,
                "strata": dict(Counter(c["stratum"] for c in adm)),
            }
        )
    out = FRESH / "steo" / "cells.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(c) + "\n" for c in cells_all)
    out.write_text(body, encoding="utf-8")
    src = json.loads((FRESH / "steo" / "sources.json").read_text(encoding="utf-8"))
    src["admission"] = {
        "rule": "whole-row (data/oracle/steo/2026-09/admission_rule.md), frozen",
        "cells_path": out.relative_to(REPO).as_posix(),
        "cells_sha256": hashlib.sha256(body.encode()).hexdigest(),
        "steo_py_sha256": sha_file(HERE.parent / "steo.py"),
        "admitted_utc": now(),
        "table_pages": [f"{t} p{p}" for p, t in pages],
        "first_data_page": first,
    }
    (FRESH / "steo" / "sources.json").write_text(json.dumps(src, indent=1) + "\n", "utf-8")
    n_any = sum(1 for r in rows_out if r["admitted_rows"] >= 1)
    n_90 = sum(1 for r in rows_out if r["coverage"] is not None and r["coverage"] >= 0.9)
    tot = Counter()
    strata = Counter()
    for r in rows_out:
        for k2 in (
            "printed_rows",
            "admitted_rows",
            "rejected_unmapped_a",
            "rejected_tie_b",
            "rejected_content_c",
            "cells",
            "admitted_cells",
        ):
            tot[k2] += r[k2]
        strata.update(r["strata"])
    reach = n_any >= 15
    md = [
        "# D-039 item 2 - STEO aug26 admission (fresh; counts only)",
        "",
        "FROZEN whole-row rule (`data/oracle/steo/2026-09/admission_rule.md`) against the FROZEN "
        "2026-09 JSON snapshot, on the aug26 PDF's text layer (`steo.HELD_PDF` patched "
        "in-process). Revised rows drop out by rule (a). No page content or value is reported.",
        "",
        f"Data-table pages: {len(pages)} (from p{first}); unreadable: {len(unreadable)} "
        f"{[(u['table_id'], u['page'], u['error']) for u in unreadable]}.",
        "",
        f"**Tables admitting >= 1 row: {n_any}** of {len(rows_out)} · tables at >= 90 % "
        f"coverage: {n_90}.",
        "",
        '**Reading applied for D-039\'s "< 15 aug26 tables admit": a table admits when it has '
        ">= 1 admitted row** (the rule admits rows; coverage is reported, flagged < 90 %, never "
        "gated - D-039). The >= 90 % count is reported beside it. Under this reading: "
        + (
            "**>= 15 - STEO's fresh strict gate is reachable.**"
            if reach
            else "**< 15 - D-039's branch applies as written: STEO's fresh strict gate is declared "
            "unreachable here; STEO keeps 95.8 % with header association re-tested on aug26 "
            "only.**"
        )
        + (
            " The >= 90 % reading gives the same branch."
            if (n_90 >= 15) == reach
            else " **The >= 90 % reading gives the OTHER branch - owner ruling needed.**"
        ),
        "",
        f"Rows: {tot['printed_rows']} printed · admitted {tot['admitted_rows']} · rejected: "
        f"unmapped (a) {tot['rejected_unmapped_a']} · tie (b) {tot['rejected_tie_b']} · content "
        f"(c) {tot['rejected_content_c']}. Cells: {tot['admitted_cells']:,} / {tot['cells']:,} "
        f"admitted. Admitted-cell strata (LAST_HISTORICAL): {dict(strata)}.",
        "",
        "| table | page | printed rows | admitted rows | (a) unmapped | (b) tie | (c) content | "
        "cells | admitted | coverage | strata |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows_out:
        cov = r["coverage"]
        cov_s = "" if cov is None else f"{cov:.1%}" + (" (flag < 90 %)" if cov < 0.9 else "")
        md.append(
            f"| {r['table_id']} | {r['page']} | {r['printed_rows']} | {r['admitted_rows']} | "
            f"{r['rejected_unmapped_a']} | {r['rejected_tie_b']} | {r['rejected_content_c']} | "
            f"{r['cells']} | {r['admitted_cells']} | {cov_s} | {r['strata']} |"
        )
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "fresh_steo_admission.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:12]))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--steo", action="store_true")
    ap.add_argument("--rescan", action="store_true", help="scan + export match only (bug fix)")
    args = ap.parse_args()
    if args.rescan:
        return rescan()
    if args.fetch:
        fetch_all()
    if args.steo:
        steo_admission()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
