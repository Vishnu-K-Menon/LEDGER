# ruff: noqa: E501
"""T5 candidate draw (D-043 item 1). Reads data/chunks.jsonl, writes data/questions_draft_draw.json.
No API call, no GPU. Running it twice gives byte-identical output.

    uv run python scripts/t5_draw.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ledger.baseline.draw import draw_candidates, render
from ledger.config import load_config
from ledger.retrieval.index import lf_sha256, read_chunks, read_lock

OUT = Path("data/questions_draft_draw.json")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", metavar="PATH", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(override=args.config)

    chunks_path = cfg.paths.chunks
    header, _ = read_lock(cfg.paths.chunk_ids_lock)
    sha = lf_sha256(chunks_path)
    locked = header.get("chunks_jsonl_sha256 (CRLF->LF)")
    if sha != locked:
        print(f"REFUSED: chunks.jsonl sha256 {sha} != lock {locked}", file=sys.stderr)
        return 2
    draw = draw_candidates(read_chunks(chunks_path), cfg.baseline)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(render(draw, chunks_sha256=sha).encode("utf-8"))
    print(f"wrote {OUT}")
    for k, v in draw["eligibility"].items():
        print(f"  {k}: {v}")
    print(
        f"  table: {draw['table_primary']} primary + reserve = {len(draw['table_order'])} in draw order"
    )
    print(
        f"  prose: {draw['prose_primary']} primary + reserve = {len(draw['prose_order'])} in draw order"
    )
    for part, comp in draw["composition"].items():
        print(f"  composition [{part}] by source and unit: {comp}")
    print(f"  supplement sources: {sorted(draw['supplement_order'])}")
    print(f"  sources not exercised: {draw['sources_not_exercised'] or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
