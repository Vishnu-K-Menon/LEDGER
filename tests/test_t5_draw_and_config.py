# ruff: noqa: E501
"""T5 config (D-042, D-043) and the candidate draw (D-043 item 1, as reworded 2026-10-10)."""

import json
import random
from collections import Counter
from itertools import islice
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from ledger.baseline.draw import (
    baseline_config_sha256,
    draw_candidates,
    eligible_pools,
    render,
    seeded_order,
    table_key,
)
from ledger.config import BaselineConfig, Config, load_config

D042 = (
    "Given a question about a U.S. government budget, economic or energy document, "
    "retrieve the passages that answer it"
)
CARD = "Given a web search query, retrieve relevant passages that answer the query"


def _mutated(base_config_path: Path, section: str, key: str, value):
    data = yaml.safe_load(base_config_path.read_text("utf-8"))
    data[section][key] = value
    return data


def test_instructions_are_the_d042_strings(base_config_path: Path):
    cfg = load_config(base_config_path)
    assert cfg.embedding.query_instruction == D042
    assert cfg.reranker.instruction == D042
    assert cfg.reranker.card_instruction == CARD


@pytest.mark.parametrize("key", ["instruction", "card_instruction"])
def test_empty_reranker_instruction_refused(base_config_path: Path, key: str):
    with pytest.raises(ValidationError, match="D-042"):
        Config.model_validate(_mutated(base_config_path, "reranker", key, "  "))


def test_empty_query_instruction_refused(base_config_path: Path):
    with pytest.raises(ValidationError, match="D-042"):
        Config.model_validate(_mutated(base_config_path, "embedding", "query_instruction", ""))


def test_baseline_block_values(base_config_path: Path):
    b = load_config(base_config_path).baseline
    assert (b.n_table, b.n_prose, b.candidates_per_slot, b.n_controls, b.runs) == (13, 12, 2, 5, 3)
    assert (b.n_control_candidates, b.reserve, b.supplement_per_source) == (10, 6, 1)
    assert (b.dense_record_k, b.record_k_finals, b.prose_min_tokens) == (100, [5, 8], 20)
    assert (b.cell, b.draw_seed) == ("t5_baseline", 20261009)


def test_baseline_block_is_strict(base_config_path: Path):
    with pytest.raises(ValidationError):
        Config.model_validate(_mutated(base_config_path, "baseline", "n_extra", 1))


def test_output_mode_defaults_empty(base_config_path: Path):
    assert load_config(base_config_path).generator.output_mode == ""


# ---- draw -------------------------------------------------------------------------------------


def _chunk(unit, item, slice_no, kind, source, text, tokens=50, barred=False):
    return {
        "chunk_id": f"{unit}::p1::{item}::s{slice_no}",
        "unit_id": unit,
        "item": item,
        "chunk_type": kind,
        "n_tokens": tokens,
        "text": text,
        "source": source,
        "question_source_barred": {"barred": barred, "reasons": []} if kind == "table" else None,
    }


def _cfg(**kw) -> BaselineConfig:
    base = dict(
        draw_seed=7, n_table=2, n_prose=2, candidates_per_slot=2, n_controls=1,
        n_control_candidates=3, reserve=2, supplement_per_source=1, runs=3, dense_record_k=100,
        record_k_finals=[5, 8], prose_min_tokens=20, cell="t5_baseline",
    )  # fmt: skip
    return BaselineConfig(**{**base, **kw})


def _corpus(small_tables=1):
    """Source `big`: 40 tables x 2 slices; `mid`: 20 tables x 2 slices; `tiny`: `small_tables`
    tables x 1 slice. Plus 60 prose chunks in two sources."""
    cs = []
    for src, n, slices in (("big", 40, 2), ("mid", 20, 2), ("tiny", small_tables, 1)):
        for i in range(n):
            for s in range(slices):
                cs.append(
                    _chunk(
                        f"{src}-u{i % 3}", f"tbl-{i}", s, "table", src, f"{src} table {i} slice {s}"
                    )
                )
    for i in range(60):
        cs.append(_chunk("pu", f"txt-{i}", 0, "prose", ["pa", "pb"][i % 2], f"prose {i}"))
    return cs


def test_eligibility_filters():
    cs = [
        _chunk("u", "tbl-1", 0, "table", "s", "barred", barred=True),
        _chunk("u", "tbl-2", 0, "table", "s", "dup"),
        _chunk("u", "tbl-3", 0, "table", "s", "dup"),
        _chunk("u", "tbl-4", 0, "table", "s", "fine"),
        _chunk("u", "txt-5", 0, "prose", "s", "short", tokens=20),  # not above 20
        _chunk("u", "txt-6", 0, "prose", "s", "ok prose", tokens=21),
    ]
    tables, prose, counts = eligible_pools(cs, _cfg())
    assert [c["text"] for c in tables] == ["fine"]
    assert [c["text"] for c in prose] == ["ok prose"]
    assert counts["chunks_sharing_text_with_another"] == 2
    assert counts["eligible_distinct_tables"] == 1


def test_seeded_order_prefix_equals_random_sample():
    pop = [f"x{i}" for i in range(500)]
    assert list(islice(seeded_order(random.Random(5), pop), 20)) == random.Random(5).sample(pop, 20)
    assert sorted(seeded_order(random.Random(5), pop)) == sorted(pop)  # a full permutation


def test_draw_is_deterministic_and_byte_identical():
    cs = _corpus()
    a = render(draw_candidates(cs, _cfg()), chunks_sha256="x")
    b = render(draw_candidates(list(cs), _cfg()), chunks_sha256="x")
    assert a == b and a.endswith("\n") and "\r" not in a


def test_draw_seed_changes_the_draw():
    cs = _corpus()
    assert (
        draw_candidates(cs, _cfg(draw_seed=1))["table_order"]
        != draw_candidates(cs, _cfg(draw_seed=2))["table_order"]
    )


def test_sizes_primary_reserve_and_one_per_table():
    cs = _corpus()
    d = draw_candidates(cs, _cfg())
    assert d["table_primary"] == 4 and len(d["table_order"]) == 4 + 2
    assert d["prose_primary"] == 4 and len(d["prose_order"]) == 4 + 2
    meta = {c["chunk_id"]: c for c in cs}
    every = d["table_order"] + [cid for ids in d["supplement_order"].values() for cid in ids]
    tables = [table_key(meta[cid]) for cid in every]
    assert len(tables) == len(set(tables))  # no table has two candidates, supplement included
    assert d["baseline_config_sha256"] == baseline_config_sha256(_cfg())


def test_sampling_unit_is_the_chunk_not_the_table():
    """A table with many slices is proportionally likelier (evaluation.md section 1); the first
    run sampled tables, which made every table equally likely."""
    cs = [_chunk("u", "tbl-big", s, "table", "a", f"big {s}") for s in range(60)]
    cs += [_chunk("u", f"tbl-{i}", 0, "table", "a", f"small {i}") for i in range(10)]
    cs += [_chunk("p", f"txt-{i}", 0, "prose", "b", f"prose {i}") for i in range(30)]
    hits = sum(
        any(table_key({"unit_id": "u", "item": "tbl-big"}) == ("u", cid.split("::")[2]) for cid in
            draw_candidates(cs, _cfg(draw_seed=s, n_table=1, candidates_per_slot=1, reserve=0))["table_order"])
        for s in range(200)
    )  # fmt: skip
    assert hits / 200 > 0.7  # table-uniform sampling would give 1/11


def test_supplement_covers_sources_without_a_primary_candidate():
    cs = _corpus(small_tables=3)
    hit_supplement = 0
    for seed in range(40):
        d = draw_candidates(cs, _cfg(draw_seed=seed))
        meta = {c["chunk_id"]: c for c in cs}
        primary_sources = {meta[cid]["source"] for cid in d["table_order"][: d["table_primary"]]}
        missing = {s for s in d["sources_with_eligible_tables"] if s not in primary_sources}
        assert set(d["supplement_order"]) == missing  # exactly the uncovered sources
        for src, ids in d["supplement_order"].items():
            assert 1 <= len(ids) <= 1 + 2 and all(meta[i]["source"] == src for i in ids)
        hit_supplement += bool(missing)
    assert hit_supplement > 0  # the rule actually fired in this corpus


def test_supplement_order_follows_the_table_order():
    cs = _corpus(small_tables=3)
    for seed in range(40):
        d = draw_candidates(cs, _cfg(draw_seed=seed))
        full = list(
            seeded_order(
                random.Random(seed), sorted(c["chunk_id"] for c in cs if c["chunk_type"] == "table")
            )
        )
        for ids in d["supplement_order"].values():
            pos = [full.index(i) for i in ids]
            assert pos == sorted(pos)


def _old_prose(cs, cfg):
    """The first run's logic for the prose stratum (it consumed the RNG sampling tables first)."""
    tables, prose, _ = eligible_pools(cs, cfg)
    by_table: dict = {}
    for c in tables:
        by_table.setdefault(table_key(c), []).append(c["chunk_id"])
    rng = random.Random(cfg.draw_seed)
    n_tab = cfg.n_table * cfg.candidates_per_slot
    for k in rng.sample(sorted(by_table), n_tab):
        rng.choice(sorted(by_table[k]))
    return rng.sample(sorted(c["chunk_id"] for c in prose), cfg.n_prose * cfg.candidates_per_slot)


def test_prose_stratum_stands_as_drawn_in_run_one():
    cs = _corpus()
    for seed in range(10):
        cfg = _cfg(draw_seed=seed)
        assert draw_candidates(cs, cfg)["prose_order"][: cfg.n_prose * 2] == _old_prose(cs, cfg)


def test_real_corpus_prose_equals_the_saved_run_one(repo_root: Path):
    run1 = repo_root / "data" / "questions_draft_draw_run1.json"
    chunks = repo_root / "data" / "chunks.jsonl"
    if not (run1.exists() and chunks.exists()):
        pytest.skip("corpus or run-1 record not present")
    from ledger.retrieval.index import read_chunks

    d = draw_candidates(read_chunks(chunks), load_config().baseline)
    saved = json.loads(run1.read_text("utf-8"))
    assert d["prose_order"][: len(saved["prose_candidates"])] == saved["prose_candidates"]
    assert Counter(c.split("::")[0] for c in saved["table_candidates"]) is not None
    assert saved["source_mix"]["table"] == {"eia": 1, "govinfo_budget": 25}  # the deviation record


def test_draw_refuses_a_pool_too_small():
    with pytest.raises(ValueError, match="pool too small"):
        draw_candidates(_corpus()[:6], _cfg())


def test_real_corpus_counts_match_the_plan(repo_root: Path):
    """D-043 item 1 counts on the laptop's chunks.jsonl (skipped where the corpus is absent)."""
    path = repo_root / "data" / "chunks.jsonl"
    if not path.exists():
        pytest.skip("data/chunks.jsonl not present")
    from ledger.retrieval.index import read_chunks

    _, _, counts = eligible_pools(read_chunks(path), load_config().baseline)
    assert counts["chunks_sharing_text_with_another"] == 1257
    assert counts["eligible_table_chunks"] == 2516
    assert counts["eligible_distinct_tables"] == 635
    assert counts["eligible_prose_chunks"] == 3548
