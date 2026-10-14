"""T6 sampler (D-044 item 3): at most ``pilot.max_claims_per_answer`` claims per answer, a seeded
draw where an answer has more; every remaining claim is kept. No table/prose quota: strata are
recorded as they fall. The rows are written in a seeded shuffled order (D-044 status 2026-10-14
(2)). A rerun reproduces the ids and the order."""

from __future__ import annotations

import json
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ledger.claims.schema import ClaimRecord
from ledger.eval.labels import load_pilot_file

SAMPLER = "t6_sample v1"


class SampleRefused(RuntimeError):
    pass


def sample_slots(records: Sequence[ClaimRecord], *, seed: int, max_per: int) -> list[dict]:
    by_q: dict[str, list[ClaimRecord]] = {}
    for r in records:
        if r.kept:
            by_q.setdefault(r.question_id, []).append(r)
    rng = random.Random(seed)
    chosen: list[ClaimRecord] = []
    for qid in sorted(by_q):
        cs = sorted(by_q[qid], key=lambda r: r.claim_id)
        if len(cs) > max_per:
            cs = sorted(rng.sample(cs, max_per), key=lambda r: r.claim_id)
        chosen.extend(cs)
    rng.shuffle(chosen)  # label order (status 2026-10-14 (2))
    return [
        {
            "set": "pilot",
            "claim_id": r.claim_id,
            "question_id": r.question_id,
            "stratum": r.stratum,
            "label": None,
        }
        for r in chosen
    ]


def manifest_for(slots: Sequence[Mapping[str, Any]], *, seed: int, max_per: int, claims_sha: str):
    return {
        "manifest": True,
        "seed": seed,
        "n": len(slots),
        "max_claims_per_answer": max_per,
        "claims_sha256": claims_sha,
        "sampler": SAMPLER,
        "label_guide_sha256": None,
    }


def render_lines(manifest: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> bytes:
    lines = [json.dumps(dict(manifest), sort_keys=True, ensure_ascii=False)]
    lines += [json.dumps(dict(r), sort_keys=True, ensure_ascii=False) for r in rows]
    return ("\n".join(lines) + "\n").encode("utf-8")


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def write_slots(path: Path, manifest: Mapping[str, Any], slots: Sequence[Mapping]) -> str:
    """Write the ids file. Refuses to touch a file holding any label, or a different draw."""
    data = render_lines(manifest, slots)
    if path.exists():
        _, rows = load_pilot_file(path)
        if any(getattr(r, "label", None) is not None for r in rows):
            raise SampleRefused(f"{path} already holds labels; the sampler never overwrites them")
        if path.read_bytes() == data:
            return "unchanged"
        raise SampleRefused(f"{path} exists with a different draw; it is never redrawn silently")
    write_atomic(path, data)
    return "written"


def strata(slots: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(s["stratum"] for s in slots).items()))
