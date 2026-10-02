"""D-037 probes on the 13 parsed ACTIVE pilot units (overnight 2026-10-01, Part 1.6). READ-ONLY:
nothing under data/ is written and nothing is chunked (so no slice counts, no table_chunk_share).

A. inventory: the 13 units, their saved export and raw PDF, the tokenizer (offline);
B. parity: the row fix through ``ledger.ingest.parse.apply_row_fix`` vs the port gate's hashes
   (``reports/a1_diag/rung1b/port_parity.json``), plus the 704 BUDGET/CBO pins on the fixed docs;
C. prefix resolution per table (``parse.prefix_sources``): category and flags, counts per source and
   per unit, 5 examples per category and per flag;
D. wide rows: per unit, table rows whose markdown line + repeated header lines exceed max_tokens
   (the library's own criterion, ``line_chunker.py``), compact_tables false and true.

    HF_HUB_OFFLINE=1 uv run python scripts/probe_d037.py <out.json>
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer  # noqa: E402
from docling_core.types.doc import DoclingDocument, TableItem  # noqa: E402

from ledger.config import load_config  # noqa: E402
from ledger.ingest.manifest import active_rows, read_manifest  # noqa: E402
from ledger.ingest.parse import (  # noqa: E402
    MarkdownTableSerializerProvider,
    apply_row_fix,
    item_key,
    prefix_sources,
    rowfix_json,
)

EXPECTED_UNITS = 13
PAREN_UNIT = re.compile(r"^\(.*\)$")  # informational only: not a D-037 source kind


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def tokenizer_id(model: str) -> dict:
    from huggingface_hub import snapshot_download

    path = Path(snapshot_download(model, local_files_only=True))
    return {"id": model, "snapshot": path.name}


def paren_before(doc: DoclingDocument, key: str) -> str | None:
    """Informational only (not a D-037 source kind): the nearest text item on the table's page
    before it whose whole text is parenthesised, e.g. BUDGET's "(In millions of dollars)"."""
    items = [it for it, _lvl in doc.iterate_items()]
    pos = next(i for i, it in enumerate(items) if item_key(str(it.self_ref)) == key)
    page = items[pos].prov[0].page_no if items[pos].prov else None
    for it in reversed(items[:pos]):
        prov = getattr(it, "prov", None) or []
        if not prov or prov[0].page_no != page:
            if prov and prov[0].page_no < (page or 0):
                break
            continue
        text = str(getattr(it, "text", "") or "").strip()
        if text and PAREN_UNIT.match(text):
            return text
    return None


def wide_rows(doc: DoclingDocument, tok, max_tokens: int, compact: bool) -> dict:
    ser = MarkdownTableSerializerProvider(compact).get_serializer(doc=doc)
    rows_over = 0
    tables_with = set()
    header_too_long = []
    n_rows = 0
    for it, _lvl in doc.iterate_items():
        if not isinstance(it, TableItem):
            continue
        text = ser.serialize(item=it).text
        header, body = ser.table_serializer.get_header_and_body_lines(table_text=text)
        h = tok.count_tokens("".join(header)) if header else 0
        prefix_len = h if h < max_tokens else 0  # line_chunker.py prefix_len
        if header and h >= max_tokens:
            header_too_long.append(item_key(str(it.self_ref)))
        for line in body:
            if not line.strip():
                continue
            n_rows += 1
            if tok.count_tokens(line) + prefix_len > max_tokens:
                rows_over += 1
                tables_with.add(item_key(str(it.self_ref)))
    return {
        "body_rows": n_rows,
        "rows_over_max_tokens": rows_over,
        "tables_with_such_rows": len(tables_with),
        "tables_header_alone_ge_max_tokens": header_too_long,
    }


def main(out_path: str) -> int:
    cfg = load_config(REPO / "configs" / "base.yaml")
    _, rows = read_manifest(REPO / cfg.paths.manifest)
    active = active_rows(rows)
    parsed = REPO / cfg.paths.parsed_dir
    units = [r for r in active if (parsed / f"{r.unit_id}.json").exists()]
    no_parse = [r.unit_id for r in active if not (parsed / f"{r.unit_id}.json").exists()]
    assert len(units) == EXPECTED_UNITS, [r.unit_id for r in units]
    out: dict = {"A": {}, "B": {}, "C": {}, "D": {}}

    # ---- A ---------------------------------------------------------------------------------------
    inv = []
    for r in units:
        pdf = REPO / cfg.paths.raw_dir / r.source / f"{r.unit_id}.pdf"
        inv.append(
            {
                "unit": r.unit_id,
                "source": r.source,
                "export": (parsed / f"{r.unit_id}.json").exists(),
                "pdf": pdf.exists(),
            }
        )
    try:
        tok = HuggingFaceTokenizer.from_pretrained(
            model_name=cfg.embedding.model, max_tokens=cfg.chunking.max_tokens
        )
        tok_info = tokenizer_id(cfg.embedding.model)
    except Exception as exc:  # noqa: BLE001 - reported; D and 1.7 are then skipped
        tok, tok_info = None, {"error": f"{type(exc).__name__}: {exc}"}
    out["A"] = {
        "units": inv,
        "n_units": len(units),
        "active_without_parse": no_parse,
        "tokenizer": tok_info,
    }

    # ---- B, C, D ---------------------------------------------------------------------------
    gate = json.loads((REPO / "reports/a1_diag/rung1b/port_parity.json").read_text("utf-8"))
    pins = json.loads((REPO / "tests/data/budget_cbo_tables_sha256.json").read_text("utf-8"))
    parity, pin_changed, pin_checked = {}, [], 0
    c_tables = []
    d_rows = {}
    for r in units:
        uid = r.unit_id
        raw = json.loads((parsed / f"{uid}.json").read_text(encoding="utf-8"))
        pdf = REPO / cfg.paths.raw_dir / r.source / f"{uid}.pdf"
        fixed, log = apply_row_fix(raw, pdf, r, cfg)
        got_doc = sha(json.dumps(fixed).encode("utf-8"))
        got_log = sha(rowfix_json(uid, log).encode("utf-8"))
        ref = gate["files"]["pilot"]
        parity[uid] = {
            "doc_sha256": got_doc,
            "doc_port": ref[f"{uid}.json"]["port"],
            "doc_identical": got_doc == ref[f"{uid}.json"]["port"],
            "log_identical": got_log == ref[f"_emit_log/{uid}.json"]["port"],
            "fix_log": dict(Counter(v["status"] for v in log.values())),
        }
        for key in (k for k in pins if k.split("|")[0] == uid):
            pin_checked += 1
            t = fixed["tables"][int(key.split("|")[1])]
            if sha(json.dumps(t, sort_keys=True).encode("utf-8")) != pins[key]:
                pin_changed.append(key)
        doc = DoclingDocument.model_validate(fixed)
        for key, s in prefix_sources(doc).items():
            c_tables.append(
                {
                    "unit_id": uid,
                    "source": r.source,
                    "table": key,
                    "page": s["page"],
                    "category": s["category"],
                    "flags": s["flags"],
                    "unit_item": s["unit"],
                    "title_item": s["title"],
                    "paren_item_before": paren_before(doc, key),
                }
            )
        if tok is not None:
            d_rows[uid] = {
                "padded": wide_rows(doc, tok, cfg.chunking.max_tokens, False),
                "compact": wide_rows(doc, tok, cfg.chunking.max_tokens, True),
            }
        pu = parity[uid]
        print(f"{uid}: parity doc={pu['doc_identical']} log={pu['log_identical']}")
    out["B"] = {
        "units": parity,
        "all_doc_identical": all(v["doc_identical"] for v in parity.values()),
        "all_log_identical": all(v["log_identical"] for v in parity.values()),
        "pins_checked": pin_checked,
        "pins_changed": pin_changed,
    }

    # ---- C summary ---------------------------------------------------------------------------
    flags = ["table_between", "no_title_on_page", "unit_after_title_only"]
    per_source = defaultdict(Counter)
    per_unit = defaultdict(Counter)
    for t in c_tables:
        for bucket in (per_source[t["source"]], per_unit[t["unit_id"]]):
            bucket["tables"] += 1
            bucket[t["category"]] += 1
            for f in flags:
                bucket[f] += int(t["flags"][f])
            bucket["title only, parenthesised item before"] += int(
                t["category"] == "title only" and bool(t["paren_item_before"])
            )
    examples: dict[str, list] = {}
    for cat in ["caption", "bracketed-unit", "title only", "nothing", *flags]:
        hits = [t for t in c_tables if t["category"] == cat or t["flags"].get(cat)]
        # spread the 5 examples over units: the first hit of each unit, then the rest
        seen, pick = set(), []
        for t in hits:
            if t["unit_id"] not in seen:
                seen.add(t["unit_id"])
                pick.append(t)
        pick += [t for t in hits if t not in pick]
        examples[cat] = pick[:5]
    out["C"] = {
        "tables": c_tables,
        "per_source": {k: dict(v) for k, v in per_source.items()},
        "per_unit": {k: dict(v) for k, v in per_unit.items()},
        "examples": examples,
    }
    out["D"] = d_rows
    Path(out_path).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("B all identical:", out["B"]["all_doc_identical"], "pins changed:", len(pin_changed))
    return 0 if out["B"]["all_doc_identical"] and not pin_changed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
