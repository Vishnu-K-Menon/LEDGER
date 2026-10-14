"""T6 sample (D-044 item 3): write the pilot claim ids to data/labels_pilot.jsonl.

At most ``pilot.max_claims_per_answer`` kept claims per answer (seeded draw where an answer has
more; seed ``pilot.sample_seed``); every remaining claim is kept; rows in a seeded shuffled order.
Refuses unless data/t6_claims.jsonl is committed, and while any answer's decomposition failed (the
owner rules first). A rerun reproduces the same file; it never overwrites labels.

    uv run python scripts/t6_sample.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ledger.claims.decompose import read_claims
from ledger.config import load_config
from ledger.pilot import repo
from ledger.pilot.sample import SampleRefused, manifest_for, sample_slots, strata, write_slots


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", metavar="PATH", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(override=args.config)
    claims_path = Path(cfg.pilot.paths.claims)
    if not repo.is_committed(claims_path):
        print(f"t6_sample REFUSED: commit {claims_path} first", file=sys.stderr)
        return 2
    manifest, records = read_claims(claims_path)
    if manifest.get("failed"):
        print(
            f"t6_sample REFUSED: decomposition failed for {sorted(manifest['failed'])}; "
            "the owner rules before any sample is drawn",
            file=sys.stderr,
        )
        return 2
    p = cfg.pilot
    slots = sample_slots(records, seed=p.sample_seed, max_per=p.max_claims_per_answer)
    m = manifest_for(
        slots,
        seed=p.sample_seed,
        max_per=p.max_claims_per_answer,
        claims_sha=repo.sha256_file(claims_path),
    )
    try:
        state = write_slots(Path(p.paths.labels), m, slots)
    except SampleRefused as exc:
        print(f"t6_sample REFUSED: {exc}", file=sys.stderr)
        return 2
    kept = sum(r.kept for r in records)
    print(
        f"{p.paths.labels}: {state}; {len(slots)} claims of {kept} kept "
        f"({len({s['question_id'] for s in slots})} answers); strata {strata(slots)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
