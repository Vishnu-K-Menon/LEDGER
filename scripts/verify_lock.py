"""Laptop check: recompute every chunk hash and both file hashes against ``data/chunk_ids.lock``.

    uv run python scripts/verify_lock.py [--lock data/chunk_ids.lock]

Pure Python (no shell pipes, so no CRLF or encoding surprises). Exit 0 only if the chunk ids and
text hashes, the record count, and the LF-normalised sha256 of chunks.jsonl and manifest.jsonl all
equal the lock; otherwise prints each difference (first ten per kind) and exits 1.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ledger.retrieval.index import compare_to_lock, lf_sha256, read_chunks, read_lock  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lock", default="data/chunk_ids.lock")
    ap.add_argument("--chunks", default="data/chunks.jsonl")
    ap.add_argument("--manifest", default="data/manifest.jsonl")
    args = ap.parse_args(argv)

    header, entries = read_lock(REPO / args.lock)
    chunks = read_chunks(REPO / args.chunks)
    bad: list[str] = []

    if header.get("records") != str(len(chunks)) or len(entries) != len(chunks):
        bad.append(
            f"record count: lock header {header.get('records')}, lock entries {len(entries)}, "
            f"chunks.jsonl {len(chunks)}"
        )
    for key, path in (
        ("chunks_jsonl_sha256 (CRLF->LF)", args.chunks),
        ("manifest_jsonl_sha256 (CRLF->LF)", args.manifest),
    ):
        got = lf_sha256(REPO / path)
        if header.get(key) != got:
            bad.append(f"{path}: lock {header.get(key)} != computed {got}")
    diffs = compare_to_lock(chunks, entries)
    if diffs:
        bad.append(f"{len(diffs)} chunk id / text hash differences; first 10:")
        bad.extend(f"  {d}" for d in diffs[:10])

    if bad:
        print("LOCK MISMATCH")
        print("\n".join(bad))
        return 1
    print(f"lock OK: {len(chunks)} chunks, chunks.jsonl and manifest.jsonl hashes match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
