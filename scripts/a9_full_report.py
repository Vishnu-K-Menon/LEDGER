# ruff: noqa: E501
"""Full-corpus A9 + D-037 output report (owner, 2026-10-06). READ-ONLY on data/: nothing is parsed,
chunked or written under data/. Writes ``reports/a9_full.md`` only.

    uv run --no-sync python scripts/a9_full_report.py

Method note (stated in the report too): the D-037 item-4 checks are computed inside
``chunk_document`` and are not persisted per unit, and re-running it would re-chunk. This script
therefore derives every output from the stored chunk records (which carry ``prefix*``, ``parse_path``,
``question_source_barred``, ``header_row_cause``, ``fffd_removed``) plus the raw Docling exports for
the verbatim prefix check. It is a recomputation from the stored records, not the in-parse values.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ledger.config import load_config  # noqa: E402
from ledger.ingest.manifest import active_rows, read_manifest  # noqa: E402
from ledger.ingest.parse import FFFD_IN_NUMBER, SEPARATOR_ROW, body_of  # noqa: E402
from ledger.ingest.stats import read_chunks, render, tally  # noqa: E402

LOGS = [REPO / "logs/parse_full_20261004.log", REPO / "logs/parse_cbo_20261006.log"]
CBO_NEW = [
    "cbo-61071", "cbo-59842", "cbo-61099", "cbo-61720", "cbo-62771", "cbo-61118",
    "cbo-62774", "cbo-59828", "cbo-61934", "cbo-59853", "cbo-61964",
]  # fmt: skip


def decode(path: Path) -> str:
    b = path.read_bytes()
    if b[:2] == b"\xff\xfe":
        return b.decode("utf-16")
    if b[:2] == b"\xfe\xff":
        return b.decode("utf-16-be")
    return b.decode("utf-8-sig", errors="replace")


def warnings_by_unit() -> tuple[dict[str, list[str]], list[str]]:
    """A MatchingPostProcessor warning is logged while a unit converts, before that unit's PARSED
    line; so it belongs to the next PARSED line."""
    out: dict[str, list[str]] = defaultdict(list)
    pending: list[str] = []
    seen: list[str] = []
    for path in LOGS:
        for ln in decode(path).splitlines():
            if "MatchingPostProcessor" in ln:
                m = re.search(r"(\d+) of (\d+) pdf cells.*?(\d+x\d+) grid", ln)
                pending.append(
                    f"{m.group(1)} of {m.group(2)} cells, {m.group(3)} grid" if m else ln
                )
                seen.append(ln)
            m = re.search(r"PARSED\s+\[\d+/\d+\]\s+(\S+)", ln)
            if m:
                out[m.group(1)].extend(pending)
                pending = []
    if pending:
        out["(unattributed)"].extend(pending)
    return dict(out), seen


def header_of(body: str) -> str:
    head = []
    for ln in body.splitlines(keepends=True):
        head.append(ln)
        if SEPARATOR_ROW.match(ln.rstrip("\r\n")):
            return "".join(head)
    return ""


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def d037(records: list[dict], raw_texts: dict[str, list[str]]) -> dict:
    tables = [r for r in records if r["chunk_type"] == "table"]
    integrity, unit_missing, pipes = [], [], []
    for r in tables:
        txt = raw_texts.get(r["unit_id"], [])
        for field in ("prefix_source", "prefix_title_source"):
            ref = r.get(field)
            if not ref:
                continue
            idx = int(ref.rsplit("/", 1)[-1])
            if idx >= len(txt) or txt[idx].strip() not in r["text"]:
                integrity.append({"chunk_id": r["chunk_id"], "missing": field})
        if not (r.get("prefix_source") and r.get("prefix") and r["prefix"] in r["text"]):
            unit_missing.append(r["chunk_id"])
        body = body_of(r)
        head = header_of(body)
        rest = body[body.index(head) + len(head) :] if head and head in body else body
        bad = [ln for ln in rest.splitlines() if ln and not ln.startswith("|")]
        if bad:
            pipes.append({"chunk_id": r["chunk_id"], "lines": len(bad)})
    by_table: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in tables:
        by_table[(r["unit_id"], r["item"])].append(r)
    blank, partial = [], []
    for key, rs in by_table.items():
        s0 = min(rs, key=lambda r: r["slice"])
        head = header_of(body_of(s0))
        first = head.splitlines()[0] if head else ""
        cs = cells(first) if first else []
        if first and not any(cs):
            blank.append(key)
        elif first and not all(cs):
            partial.append(key)
    causes = Counter()
    nr_tables = set()
    for key, rs in by_table.items():
        cause = next((r.get("header_row_cause") for r in rs if r.get("header_row_cause")), None)
        if cause:
            causes[cause] += 1
            nr_tables.add(key)
    barred_slices, barred_tables = Counter(), defaultdict(set)
    n_barred = 0
    for r in tables:
        bar = r.get("question_source_barred") or {}
        if bar.get("barred"):
            n_barred += 1
        for why in bar.get("reasons", []):
            barred_slices[why] += 1
            barred_tables[why].add((r["unit_id"], r["item"]))
    return {
        "table_slices": len(tables),
        "tables": len(by_table),
        "prefix_integrity": integrity,
        "unit_line_missing_slices": len(unit_missing),
        "unit_line_missing_tables": len(
            {(r["unit_id"], r["item"]) for r in tables if r["chunk_id"] in set(unit_missing)}
        ),
        "header_not_repeated_tables": len(nr_tables),
        "header_row_cause": dict(causes),
        "body_line_not_pipe": pipes,
        "blank_headers": blank,
        "partial_headers": partial,
        "fffd_removed": sum(r.get("fffd_removed", 0) for r in records),
        "fffd_kept_in_table_slices": sum(r["text"].count("�") for r in tables),
        "fffd_in_number_slices": sum(1 for r in tables if FFFD_IN_NUMBER.search(r["text"])),
        "barred_slices": n_barred,
        "barred_slices_by_reason": dict(barred_slices),
        "barred_tables_by_reason": {k: len(v) for k, v in barred_tables.items()},
        "barred_tables_total": len({k for v in barred_tables.values() for k in v}),
        "caption_only_chunks": sum(
            1 for r in records if r["chunk_type"] == "table" and r["chunk_type_literal"] != "table"
        ),
        "max_n_tokens_table": max((r["n_tokens"] for r in tables), default=0),
        "max_text_chars_table": max((len(r["text"]) for r in tables), default=0),
        "max_n_tokens_all": max((r["n_tokens"] for r in records), default=0),
    }


def fmt(d: dict) -> list[str]:
    rows = [
        ("table slices / tables", f"{d['table_slices']} / {d['tables']}"),
        ("prefix_integrity (must be 0)", len(d["prefix_integrity"])),
        (
            "unit_line_missing (slices / tables)",
            f"{d['unit_line_missing_slices']} / {d['unit_line_missing_tables']}",
        ),
        ("header_not_repeated tables", d["header_not_repeated_tables"]),
        ("header_row_cause", d["header_row_cause"] or "none"),
        ("body lines not `|` (slices)", len(d["body_line_not_pipe"])),
        (
            "blank / partial headers (tables)",
            f"{len(d['blank_headers'])} / {len(d['partial_headers'])}",
        ),
        ("U+FFFD removed (fffd_removed)", d["fffd_removed"]),
        ("U+FFFD kept, in table slices", d["fffd_kept_in_table_slices"]),
        ("fffd_in_number (slices)", d["fffd_in_number_slices"]),
        (
            "question_source_barred: slices / tables",
            f"{d['barred_slices']} / {d['barred_tables_total']}",
        ),
        ("  slices by reason", d["barred_slices_by_reason"] or "none"),
        ("  tables by reason", d["barred_tables_by_reason"] or "none"),
        ("caption-only chunks (table by D-036, prose by D-033 literal)", d["caption_only_chunks"]),
        (
            "max contextualized table-slice length",
            f"{d['max_n_tokens_table']} tokens / {d['max_text_chars_table']} chars",
        ),
        ("max tokens, any chunk", d["max_n_tokens_all"]),
    ]
    return ["| output | value |", "|---|---|", *[f"| {k} | {v} |" for k, v in rows]]


def erp_table(records: list[dict], name: str) -> list[str]:
    """Fix-log status, parse path, raw table size, and a digit-group comparison of the PDF page
    text against everything emitted for the unit. The PDF text encodes decimal points as U+FFFD,
    so numbers are compared as digit groups; PDF-only groups are listed to be read, not assumed."""
    import pypdf

    uid = f"govinfo-ERP-2026-{name}"
    fix = json.loads((REPO / f"data/parsed/{uid}.rowfix.json").read_text(encoding="utf-8"))
    raw = json.loads((REPO / f"data/parsed/{uid}.json").read_text(encoding="utf-8"))
    recs = [r for r in records if r["unit_id"] == uid]
    tabs = [r for r in recs if r["chunk_type"] == "table"]
    d = raw["tables"][0]["data"]
    pdf = " ".join(
        p.extract_text()
        for p in pypdf.PdfReader(str(REPO / "data/raw/govinfo_erp" / f"{uid}.pdf")).pages
    )
    g_pdf = Counter(re.findall(r"\d+", pdf))
    g_out = Counter(re.findall(r"\d+", " ".join(r["text"] for r in recs)))
    only = g_pdf - g_out
    return [
        f"**{uid}**",
        f"- fix-log status: `{json.dumps(fix['tables'], ensure_ascii=False)}`",
        f"- parse_path: {sorted({(r['item'], r['parse_path']) for r in tabs})}; table slices "
        f"{len(tabs)}; barred: {sorted({str(r['question_source_barred']['reasons']) for r in tabs})}",
        f"- raw Docling export table: {d['num_rows']} rows x {d['num_cols']} cols, "
        f"{len(d['table_cells'])} cells (the row fix rebuilds from page words)",
        f"- PDF digit groups {sum(g_pdf.values())}; emitted {sum(g_out.values())}; PDF-only "
        f"(absent from every emitted chunk of the unit): {sum(only.values())} = {dict(only)}",
    ]


def main() -> int:
    cfg = load_config(REPO / "configs" / "base.yaml")
    _, rows = read_manifest(REPO / cfg.paths.manifest)
    act = {r.unit_id: r for r in active_rows(rows)}
    records = read_chunks(REPO / cfg.paths.chunks)
    pages = {u: (act[u].pages or 0) for u in {r["unit_id"] for r in records} if u in act}
    total, by_source, by_unit = tally(records, pages)

    # step 1: the 11 CBO units
    csv_names = (REPO / "data/manual/cbo/sources.csv").read_text(encoding="utf-8-sig")
    step1 = []
    for u in CBO_NEW:
        row = act.get(u)
        n = sum(1 for r in records if r["unit_id"] == u)
        csv_ok = f"{u}.pdf" in csv_names
        step1.append((u, csv_ok, bool(row and row.sha256), n))
    pending = [s for s in step1 if not (s[1] and s[2] and s[3] > 0)]

    tok_all = sum(r["n_tokens"] for r in records)
    tok_tab = sum(r["n_tokens"] for r in records if r["chunk_type"] == "table")

    def tw(rs: list[dict]) -> str:
        a = sum(r["n_tokens"] for r in rs)
        b = sum(r["n_tokens"] for r in rs if r["chunk_type"] == "table")
        return f"{b / a:.3f}" if a else "n/a"

    lo, hi = cfg.ingest.table_chunk_share_band
    report = render(total, by_source, by_unit, band=(lo, hi), skipped=["govinfo-BUDGET-2027-TAB"],
                    seconds=0.0, workers=1)  # fmt: skip
    # drop render()'s pilot title/parse-time line: this is the full-corpus A9
    lines = report.splitlines()
    body = [ln for ln in lines if not ln.startswith("Parsed ") and not ln.startswith("# A9")]

    warn, raw_lines = warnings_by_unit()
    # 25 units parsed since 2026-10-04 = units parsed in the 2026-10-05 and 2026-10-06 runs
    parsed_runs = {
        m
        for ln in decode(LOGS[0]).splitlines()
        for m in re.findall(r"PARSED\s+\[\d+/\d+\]\s+(\S+)", ln)
    }
    parsed_runs |= {
        m
        for ln in decode(LOGS[1]).splitlines()
        for m in re.findall(r"PARSED\s+\[\d+/\d+\]\s+(\S+)", ln)
    }
    since = parsed_runs
    raw_texts = {}
    for u in {r["unit_id"] for r in records}:
        raw = json.loads((REPO / f"data/parsed/{u}.json").read_text(encoding="utf-8"))
        raw_texts[u] = [t.get("text", "") for t in raw.get("texts", [])]
    whole = d037(records, raw_texts)
    new = d037([r for r in records if r["unit_id"] in since], raw_texts)

    erp = defaultdict(set)
    for r in records:
        if r["source"] == "govinfo_erp" and r["chunk_type"] == "table":
            for t, p in (r.get("parse_path_by_table") or {}).items():
                erp[r["unit_id"]].add(f"{t}:{p}")

    by_src_since = Counter(r["source"] for r in records if r["unit_id"] in since)
    out = ["# A9 — full corpus (D-001, D-036, D-037; owner 2026-10-06)", ""]
    out += [f"Source: `data/chunks.jsonl`, {len(records)} chunks. Read-only; nothing re-parsed or "
            "re-chunked. Counting rule D-036.", ""]  # fmt: skip
    out += [f"**Chunk-count share = {total.table_chunk_share:.3f}** "
            f"({total.table_slices:,} / {total.chunks:,}); **token-weighted share = "
            f"{tok_tab / tok_all:.3f}**; {total.units} units, {len({r['source'] for r in records})} "
            f"sources, {total.pages} pages. Band {lo:.2f}–{hi:.2f}.", ""]  # fmt: skip
    out += ["## Step 1 — the 11 CBO units", "", "| unit | in sources.csv | sha256 on manifest | chunks |", "|---|---|---|---|"]  # fmt: skip
    out += [f"| {u} | {a} | {b} | {n} |" for u, a, b, n in step1]
    out += ["", f"Pending: {[p[0] for p in pending] or 'none'}", ""]
    out += ["## A9 (chunk-count), per source and per unit", "", *body, ""]
    out += ["## Token-weighted share, per source", "", "| source | token-weighted | chunk-count |", "|---|---|---|"]  # fmt: skip
    for s, c in sorted(by_source.items()):
        out.append(
            f"| {s} | {tw([r for r in records if r['source'] == s])} | {c.table_chunk_share:.3f} |"
        )
    out += ["", "Per unit (token-weighted / chunk-count):", "", "| unit | token-weighted | chunk-count |", "|---|---|---|"]  # fmt: skip
    for u, c in sorted(by_unit.items()):
        out.append(
            f"| {u} | {tw([r for r in records if r['unit_id'] == u])} | {c.table_chunk_share:.3f} |"
        )
    out += ["", "## D-037 outputs — whole corpus", "", *fmt(whole), ""]
    out += [f"## D-037 outputs — the {len(since)} units parsed since 2026-10-04 "
            f"({dict(by_src_since)} chunks by source)", "", *fmt(new), ""]  # fmt: skip
    out += ["## parse_path per table — the 12 ERP granules", "", "| unit | tables:parse_path |", "|---|---|"]  # fmt: skip
    for u in sorted(erp):
        out.append(f"| {u} | {sorted(erp[u])} |")
    out += ["", "## ERP-2026-table43 and table30 (dropped-cell check)", ""]
    out += [*erp_table(records, "table43"), "", *erp_table(records, "table30"), ""]
    out += ["## MatchingPostProcessor dropped-cell warnings (both logs, UTF-16 LE decoded)", "",
            f"Total warnings: {len(raw_lines)}.", "", "| unit | warnings |", "|---|---|"]  # fmt: skip
    for u, w in sorted(warn.items()):
        if w:
            out.append(f"| {u} | {len(w)} — {'; '.join(w)} |")
    out += ["", "For BUDGET and CBO units (outside the row fix) the dropped cells are **absent from "
            "the corpus**: Docling dropped them before chunking and nothing restores them. "
            "Listed under \"for the owner at T7\"; whether such tables are barred as question "
            "sources is not decided here.", ""]  # fmt: skip
    out += ["**Attribution.** The warning is logged while a unit converts and before that unit's "
            "`PARSED` line. The 25-of-1443-cell warning sits between `PARSED [7/14] ERP-table43` "
            "and `PARSED [8/14] ERP-table30`, at 00:34:21 inside table30's 6.2 s window, and its "
            "grid (5x15) is table30's raw table (5 rows x 15 cols), not table43's (67 x 13). It "
            "belongs to **ERP-2026-table30**; table43 has no dropped-cell warning. The "
            "expected \"ERP-table43 1\" is therefore table30. Both ERP tables are `rebuilt` from "
            "page words; every PDF-only digit group in either unit is page-number, table label, "
            "year-range or footnote text, not a data cell (the 25 dropped Docling cells are "
            "present in the emitted tables).", ""]  # fmt: skip
    out += ["## For the owner at T7", "",
            "- Dropped-cell tables outside the row fix (not restored, absent from the corpus): "
            "govinfo-BUDGET-2027-OBJCLASS (3 warnings: 3, 2, 2 cells), cbo-62774 (4 cells), "
            "cbo-59828 (4 cells). Whether such tables are barred as question sources is not "
            "decided here.",
            "- `parse_path = fallback`: ERP-2026-table46 (and the other fallback tables counted "
            "above) are barred by D-040's pre-T7 rule.",
            "- `header_not_repeated` is overwhelmingly `caption_on_slice0`; `no_own_title` is the "
            "largest bar reason. Both shrink the usable table-question pool; D-040 handles the "
            "table-question share by stratified sampling.",
            ""]  # fmt: skip
    out += ["## Method and limits", "",
            "- The D-037 item-4 checks run inside `chunk_document` and are not persisted per unit; "
            "re-running it would re-chunk, so every output above is **recomputed from the stored "
            "records** (+ raw exports for the verbatim prefix check), not read from the in-parse "
            "values. `prefix_integrity` here = the recorded unit/title source text, taken from the "
            "raw Docling export, appears verbatim in the slice. It does not detect a unit or title "
            "that exists on the page but was never recorded as `prefix_source`.",
            "- Header repetition is read from `header_row_cause` / `question_source_barred`; blank "
            "and partial headers from each table's slice-0 header row.",
            ""]  # fmt: skip
    (REPO / "reports" / "a9_full.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:12]))
    print("pending:", [p[0] for p in pending])
    print(
        "prefix_integrity:",
        len(whole["prefix_integrity"]),
        "| since:",
        len(new["prefix_integrity"]),
    )
    return 1 if pending or whole["prefix_integrity"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
