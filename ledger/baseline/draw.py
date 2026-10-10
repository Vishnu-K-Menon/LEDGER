"""Candidate draw for the T5 draft questions (D-043 item 1, as reworded 2026-10-10).

The sampling unit is the chunk. Within each stratum the eligible chunks are put in ONE seeded random
order and taken in that order; a table chunk is skipped when its table already has a candidate, so
each distinct table gives at most one question. A rejected candidate is replaced by the next chunk
in the same order (``baseline.reserve`` of them are listed), never by hand. There is no quota or
floor by source or unit.

Coverage supplement: every source that holds eligible tables and has no primary table candidate
gets ``baseline.supplement_per_source`` further table items, taken from that source in the same
order. They sit beside the 25 and enter no count computed on them.

Pure and deterministic: the same chunks and config give byte-identical output (no timestamps).
Eligibility: not ``question_source_barred``; text unique in the corpus (by text hash); prose chunks
above ``baseline.prose_min_tokens``. A table is identified by (unit_id, item): tables never span
pages (checked 2026-10-09).

Deviation record (D-043 item 1): the FIRST run sampled distinct tables for the table stratum
(25 govinfo_budget + 1 eia of 26 candidates; kept in data/questions_draft_draw_run1.json). The prose
stratum already sampled chunks and "stands as drawn": ``_replay_run1_table_consumption`` reproduces
that run's RNG use so the first ``n_prose x candidates_per_slot`` prose candidates are identical
to it (tested against the saved run-1 file).
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from ledger.config import BaselineConfig
from ledger.retrieval.index import text_sha256


def is_barred(rec: Mapping[str, Any]) -> bool:
    """Tables carry ``{barred, reasons}``; prose carries ``None`` (never barred)."""
    bar = rec.get("question_source_barred")
    return bool(bar and bar.get("barred", False))


def table_key(rec: Mapping[str, Any]) -> tuple[str, str]:
    return (rec["unit_id"], rec["item"])


def baseline_config_sha256(cfg: BaselineConfig) -> str:
    blob = json.dumps(cfg.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def eligible_pools(
    chunks: Sequence[Mapping[str, Any]], cfg: BaselineConfig
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]], dict[str, int]]:
    """Returns (eligible table chunks, eligible prose chunks, counts)."""
    hashes = Counter(text_sha256(c["text"]) for c in chunks)
    shared = [c for c in chunks if hashes[text_sha256(c["text"])] > 1]
    unique = [c for c in chunks if hashes[text_sha256(c["text"])] == 1]
    tables = [c for c in unique if c["chunk_type"] == "table" and not is_barred(c)]
    prose = [
        c
        for c in unique
        if c["chunk_type"] == "prose" and not is_barred(c) and c["n_tokens"] > cfg.prose_min_tokens
    ]
    counts = {
        "chunks": len(chunks),
        "chunks_sharing_text_with_another": len(shared),
        "eligible_table_chunks": len(tables),
        "eligible_distinct_tables": len({table_key(c) for c in tables}),
        "eligible_prose_chunks": len(prose),
    }
    return tables, prose, counts


def seeded_order(rng: random.Random, population: Sequence[str]) -> Iterator[str]:
    """Lazy seeded order without replacement by rejection. For a population much larger than the
    number taken, the first k elements equal ``rng.sample(population, k)`` (CPython's set-based
    branch draws exactly this sequence), so it extends a plain ``sample`` draw consistently."""
    n = len(population)
    seen: set[int] = set()
    while len(seen) < n:
        j = rng.randrange(n)
        if j in seen:
            continue
        seen.add(j)
        yield population[j]


def _replay_run1_table_consumption(
    rng: random.Random, by_table: Mapping[tuple[str, str], Sequence[str]], n_tab: int
) -> None:
    """Advance ``rng`` exactly as the first run's table branch did (it sampled tables, then one
    chunk per table), so the prose stratum, drawn from the same stream, stands as drawn."""
    keys = sorted(by_table)
    for k in rng.sample(keys, n_tab):
        rng.choice(sorted(by_table[k]))


def _walk_tables(
    order: Iterator[str],
    meta: Mapping[str, Mapping[str, Any]],
    used: set[tuple[str, str]],
    want: int,
    source: str | None = None,
) -> list[str]:
    """Take ``want`` chunk ids in order whose table is unused (and, if given, from ``source``)."""
    out: list[str] = []
    for cid in order:
        if len(out) >= want:
            break
        c = meta[cid]
        if table_key(c) in used or (source is not None and c["source"] != source):
            continue
        used.add(table_key(c))
        out.append(cid)
    return out


def _composition(ids: Sequence[str], meta: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    out: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for cid in ids:
        out[meta[cid]["source"]][meta[cid]["unit_id"]] += 1
    return {s: dict(sorted(u.items())) for s, u in sorted(out.items())}


def draw_candidates(chunks: Sequence[Mapping[str, Any]], cfg: BaselineConfig) -> dict[str, Any]:
    tables, prose, counts = eligible_pools(chunks, cfg)
    n_tab = cfg.n_table * cfg.candidates_per_slot
    n_pro = cfg.n_prose * cfg.candidates_per_slot
    meta = {c["chunk_id"]: c for c in tables}
    table_ids = sorted(meta)
    prose_ids = sorted(c["chunk_id"] for c in prose)
    if len({table_key(c) for c in tables}) < n_tab or len(prose_ids) < n_pro:
        raise ValueError(
            f"pool too small: {len({table_key(c) for c in tables})} tables for {n_tab}, "
            f"{len(prose_ids)} prose for {n_pro}"
        )

    # table stratum: one seeded order over chunks; first n_tab distinct tables are primary
    used: set[tuple[str, str]] = set()
    order = seeded_order(random.Random(cfg.draw_seed), table_ids)
    walked = _walk_tables(order, meta, used, n_tab + cfg.reserve)
    table_primary, table_reserve = walked[:n_tab], walked[n_tab:]

    # coverage supplement: sources with eligible tables but no primary table candidate
    sources_with_tables = sorted({c["source"] for c in tables})
    covered = {meta[cid]["source"] for cid in table_primary}
    supplement: dict[str, list[str]] = {}
    for src in (s for s in sources_with_tables if s not in covered):
        again = seeded_order(random.Random(cfg.draw_seed), table_ids)
        supplement[src] = _walk_tables(
            again, meta, used, cfg.supplement_per_source + cfg.reserve, source=src
        )

    # prose stratum: stands as drawn (run 1's RNG stream), extended by the same order
    by_table: dict[tuple[str, str], list[str]] = defaultdict(list)
    for c in tables:
        by_table[table_key(c)].append(c["chunk_id"])
    prng = random.Random(cfg.draw_seed)
    _replay_run1_table_consumption(prng, by_table, n_tab)
    prose_walk = list(_take(seeded_order(prng, prose_ids), n_pro + cfg.reserve))
    prose_meta = {c["chunk_id"]: c for c in prose}

    all_meta = {**meta, **prose_meta}
    sup_primary = [cid for ids in supplement.values() for cid in ids[: cfg.supplement_per_source]]
    corpus_sources = sorted({c["source"] for c in chunks})
    composition = {
        "table": _composition(table_primary, all_meta),
        "prose": _composition(prose_walk[:n_pro], all_meta),
        "supplement": _composition(sup_primary, all_meta),
    }
    exercised = {s for part in composition.values() for s in part}
    return {
        "seed": cfg.draw_seed,
        "baseline_config_sha256": baseline_config_sha256(cfg),
        "eligibility": counts,
        "table_order": table_primary + table_reserve,
        "table_primary": n_tab,
        "prose_order": prose_walk,
        "prose_primary": n_pro,
        "supplement_order": supplement,
        "supplement_primary_per_source": cfg.supplement_per_source,
        "sources_with_eligible_tables": sources_with_tables,
        "composition": composition,
        "source_mix": {
            part: {s: sum(u.values()) for s, u in comp.items()}
            for part, comp in composition.items()
        },
        "sources_not_exercised": [s for s in corpus_sources if s not in exercised],
    }


def _take(it: Iterator[str], n: int) -> Iterator[str]:
    for _ in range(n):
        try:
            yield next(it)
        except StopIteration:
            return


def render(draw: Mapping[str, Any], *, chunks_sha256: str) -> str:
    """Byte-stable serialisation (sorted keys, LF, trailing newline)."""
    body = {**draw, "chunks_sha256": chunks_sha256}
    return json.dumps(body, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
