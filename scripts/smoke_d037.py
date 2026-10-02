"""D-037 smoke on ONE unit (overnight 2026-10-01, Part 1.7): ``scripts/rechunk_d037.py`` into
``data/rechunk_smoke/<setting>/`` under compact_tables false and true, the item-4 checks, slice
counts; plus the unit's UNFIXED saved export chunked in memory under each setting (nothing
written) to compare with the 2026-09-26 measurement. Reads data/parsed and data/raw only.

    HF_HUB_OFFLINE=1 uv run python scripts/smoke_d037.py [unit]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import rechunk_d037  # noqa: E402
from docling_core.types.doc import DoclingDocument  # noqa: E402

from ledger.config import load_config  # noqa: E402
from ledger.ingest.manifest import read_manifest  # noqa: E402
from ledger.ingest.parse import build_chunker, chunk_records  # noqa: E402


def main(unit: str = "govinfo-ERP-2026-table4") -> int:
    smoke = REPO / "data" / "rechunk_smoke"
    out: dict = {"unit": unit, "settings": {}}
    _, rows = read_manifest(REPO / "data" / "manifest.jsonl")
    row = next(r for r in rows if r.unit_id == unit)
    raw = json.loads((REPO / "data" / "parsed" / f"{unit}.json").read_text(encoding="utf-8"))
    for name, compact in (("compact_false", False), ("compact_true", True)):
        d = smoke / name
        d.mkdir(parents=True, exist_ok=True)
        override = d / "override.yaml"
        override.write_text(
            f"chunking:\n  markdown_compact_tables: {str(compact).lower()}\n", encoding="utf-8"
        )
        cfg = load_config(REPO / "configs" / "base.yaml", override)
        chunker = build_chunker(cfg)
        body = rechunk_d037.rechunk(cfg, d, units=[unit], chunker=chunker)
        recs = [
            json.loads(ln)
            for ln in (d / f"{unit}.chunks.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        tables = [r for r in recs if r["chunk_type"] == "table"]
        unfixed = chunk_records(
            row, list(chunker.chunk(dl_doc=DoclingDocument.model_validate(raw))), chunker, cfg
        )
        ut = [r for r in unfixed if r["chunk_type"] == "table"]
        out["settings"][name] = {
            "fixed": {
                "chunks": len(recs),
                "table_slices": len(tables),
                "per_table": {
                    t: sum(1 for r in tables if r["item"] == t)
                    for t in sorted({r["item"] for r in tables})
                },
                "parse_path": sorted({r["parse_path"] for r in tables}),
                "prefix_sources": sorted({str(r["prefix_source"]) for r in tables}),
                "max_n_tokens_table": max(r["n_tokens"] for r in tables),
                "item4": body["d037_item4_checks"][unit],
            },
            "unfixed_in_memory": {
                "chunks": len(unfixed),
                "table_slices": len(ut),
                "per_table": {
                    t: sum(1 for r in ut if r["item"] == t) for t in sorted({r["item"] for r in ut})
                },
            },
            "manifest": str((d / "MANIFEST.json").relative_to(REPO)),
        }
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
