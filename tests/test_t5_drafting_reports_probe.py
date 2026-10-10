# ruff: noqa: E501
"""Drafting/finalizer refusals, report maths and the verifier-probe logic. No API call, no GPU."""

import math
import re
from collections import Counter
from pathlib import Path

import pytest

from ledger.baseline import probe
from ledger.baseline import reports as rp
from ledger.baseline.drafting import FinalizeRefused, finalize, parse_controls, parse_draft
from ledger.baseline.run import RunRecord
from ledger.baseline.schema import Answer
from ledger.config import load_config

# ---- drafting ---------------------------------------------------------------------------------


def _cfg():
    return load_config()


def test_parse_draft_accepts_fenced_json_and_rejects_bad_type():
    ok = parse_draft(
        '```json\n{"question": "q", "gold_answer": "1,022", "answer_type": "number"}\n```'
    )
    assert ok["gold_answer"] == "1,022"
    with pytest.raises(ValueError):
        parse_draft('{"question": "q", "gold_answer": "x", "answer_type": "list"}')
    with pytest.raises(ValueError):
        parse_controls('[{"question": "q", "control_kind": "bogus", "rationale": ""}]')


def _cand(cid, stratum, i, accept, **kw):
    base = dict(candidate_id=f"{stratum[0]}{i:02d}", kind="prose" if stratum == "prose" else "table",
                stratum=stratum, order_index=i, tier="primary", chunk_id=cid, question=f"q-{cid}",
                gold_answer="NUM", answer_type="number", drafted_by="m", accept=accept,
                checked_by="owner", notes="")  # fmt: skip
    return {**base, **kw}


def _world(n_table=15, n_prose=14, n_ctrl=10, supp_sources=("cbo",)):
    """Candidates in draw order with every first-needed one accepted; the extras are reserve."""
    chunks, cands = {}, []
    for i in range(n_table):
        cid = f"u{i}::p1::tbl-{i}::s0"
        chunks[cid] = {"chunk_id": cid, "unit_id": f"u{i}", "item": f"tbl-{i}", "chunk_type": "table",
                       "source": "big", "text": f"row {i}: NUM units"}  # fmt: skip
        cands.append(_cand(cid, "table", i, i < 13))
    for i in range(n_prose):
        cid = f"v{i}::p1::txt-{i}::s0"
        chunks[cid] = {"chunk_id": cid, "unit_id": f"v{i}", "item": f"txt-{i}", "chunk_type": "prose",
                       "source": "pa", "text": f"The rate was NUM {i}."}  # fmt: skip
        cands.append(_cand(cid, "prose", i, i < 12))
    for src in supp_sources:
        for i in range(2):
            cid = f"{src}{i}::p1::tbl-0::s0"
            chunks[cid] = {"chunk_id": cid, "unit_id": f"{src}{i}", "item": "tbl-0",
                           "chunk_type": "table", "source": src, "text": "cell NUM"}  # fmt: skip
            cands.append(_cand(cid, "supplement", i, i < 1, supp_source=src,
                               candidate_id=f"s-{src}-{i}"))  # fmt: skip
    for i in range(n_ctrl):
        cands.append(dict(candidate_id=f"c{i:02d}", kind="control", stratum="control", order_index=i,
                          question=f"cq{i}", control_kind="absent_entity", drafted_by="m",
                          accept=True, checked_by="owner", notes=""))  # fmt: skip
    return cands, chunks


def test_finalize_happy_path():
    cands, chunks = _world()
    out = finalize(cands, chunks, set(chunks), _cfg())
    sets = Counter(q["set"] for q in out)
    assert sets == {"draft": 25, "supplement": 1, "control_candidate": 10}
    assert [q["question_id"] for q in out][:2] == ["q001", "q002"]
    sup = next(q for q in out if q["set"] == "supplement")
    assert sup["question_id"] == "s001" and sup["supp_source"] == "cbo" and sup["source"] == "cbo"
    ctrl = [q for q in out if q["unanswerable"]]
    assert all(q["gold_chunk_id"] is None and q["control_kind"] for q in ctrl)
    assert all(q["checked_by"] == "owner" for q in out)


def test_replacement_by_the_next_candidate_needs_a_logged_reason():
    cands, chunks = _world()
    cands[2]["accept"] = False  # t02 rejected ...
    cands[13]["accept"] = True  # ... replaced by the next in order (the first reserve)
    with pytest.raises(FinalizeRefused, match="without a logged reason"):
        finalize(cands, chunks, set(chunks), _cfg())
    cands[2]["notes"] = "gold answer ambiguous"
    out = finalize(cands, chunks, set(chunks), _cfg())
    assert sum(q["set"] == "draft" and q["chunk_type"] == "table" for q in out) == 13
    assert chunks[cands[2]["chunk_id"]] and cands[2]["chunk_id"] not in {
        q["gold_chunk_id"] for q in out
    }


def test_choosing_out_of_order_is_refused():
    cands, chunks = _world()
    cands[12]["accept"] = False  # the 13th is dropped without being the reserve's turn ...
    cands[12]["notes"] = "no"
    cands[13]["accept"] = None  # the first reserve is left undecided ...
    cands[14]["accept"] = True  # ... and the SECOND reserve is taken, skipping the first
    with pytest.raises(FinalizeRefused, match="undecided"):
        finalize(cands, chunks, set(chunks), _cfg())


def test_accepting_more_than_needed_is_refused():
    cands, chunks = _world()
    cands[14]["accept"] = True
    with pytest.raises(FinalizeRefused, match="accepted beyond the 13"):
        finalize(cands, chunks, set(chunks), _cfg())


def test_finalize_refuses_too_few_accepted_and_too_few_controls():
    cands, chunks = _world()
    cands[0]["accept"] = False
    cands[0]["notes"] = "bad"
    cands[13]["accept"] = False
    cands[13]["notes"] = "bad"
    cands[14]["accept"] = False
    cands[14]["notes"] = "bad"
    with pytest.raises(FinalizeRefused, match="table: 12 accepted, need 13"):
        finalize(cands, chunks, set(chunks), _cfg())
    cands, chunks = _world(n_ctrl=4)
    with pytest.raises(FinalizeRefused, match="4 controls accepted"):
        finalize(cands, chunks, set(chunks), _cfg())


def test_finalize_refuses_non_substring_gold():
    cands, chunks = _world()
    cands[0]["gold_answer"] = "9,999"
    with pytest.raises(FinalizeRefused, match="exact substring"):
        finalize(cands, chunks, set(chunks), _cfg())


def test_finalize_refuses_two_questions_from_one_table_across_core_and_supplement():
    cands, chunks = _world()
    s = next(c for c in cands if c["stratum"] == "supplement" and c["accept"])
    chunks[s["chunk_id"]] = {**chunks[s["chunk_id"]], "unit_id": "u0", "item": "tbl-0"}
    with pytest.raises(FinalizeRefused, match="one table"):
        finalize(cands, chunks, set(chunks), _cfg())


def test_finalize_refuses_ids_missing_from_lock_and_unnamed_checker():
    cands, chunks = _world()
    with pytest.raises(FinalizeRefused, match="not in the lock"):
        finalize(cands, chunks, set(list(chunks)[1:]), _cfg())
    cands, chunks = _world()
    cands[3]["checked_by"] = ""
    with pytest.raises(FinalizeRefused, match="checked_by"):
        finalize(cands, chunks, set(chunks), _cfg())


# ---- reports ----------------------------------------------------------------------------------


def test_wilson_matches_the_decision_text():
    lo, hi = rp.wilson(21, 25)  # D-033 status 2026-10-09: 0.65-0.94
    assert (round(lo, 2), round(hi, 2)) == (0.65, 0.94)
    assert rp.wilson(0, 0) == (0.0, 0.0)


def _meta(cid, unit="u", item="tbl-1"):
    return {"unit_id": unit, "item": item, "chunk_id": cid}


def test_classify_miss_precedence():
    meta = {"g": _meta("g"), "s": _meta("s"), "x": _meta("x", item="tbl-9")}
    base = {"gold_chunk_id": "g", "top5": ["x"], "gold_rank_dense": 4, "gold_rank_rerank": 9}
    assert rp.classify_miss({**base, "top5": ["s", "x"]}, meta, 30) == "sibling slice"
    assert rp.classify_miss({**base, "gold_rank_dense": None}, meta, 30) == "first-stage miss"
    assert rp.classify_miss({**base, "gold_rank_dense": 31}, meta, 30) == "first-stage miss"
    assert rp.classify_miss(base, meta, 30) == "reranker demotion"


def _qs():
    return [
        {"question_id": "q1", "set": "draft", "gold_chunk_id": "g", "unanswerable": False},
        {"question_id": "q2", "set": "draft", "gold_chunk_id": "g", "unanswerable": False},
        {"question_id": "s1", "set": "supplement", "gold_chunk_id": "g", "unanswerable": False},
        {"question_id": "c1", "set": "control_candidate", "question": "ctrl1?", "unanswerable": True,
         "control_kind": "absent_entity", "gold_chunk_id": None},
        {"question_id": "c2", "set": "control_candidate", "question": "ctrl2?", "unanswerable": True,
         "control_kind": "absent_entity", "gold_chunk_id": None},
    ]  # fmt: skip


def _recs():
    r = lambda qid, gold, top, d, rr: {  # noqa: E731
        "question_id": qid, "gold_chunk_id": gold, "top5": top, "top8": top,
        "gold_rank_dense": d, "gold_rank_rerank": rr}  # fmt: skip
    return [
        r("q1", "g", ["g"], 1, 1),
        r("q2", "g", ["x"], 5, 7),
        r("s1", "g", ["x"], None, None),  # a supplement MISS must not touch the core numbers
        r("c1", None, ["x"], None, None),
        r("c2", None, ["g"], None, None),
    ]


def test_a6_core_only_with_supplement_and_control_choice():
    meta = {"g": {**_meta("g"), "source": "S", "unit_id": "U"}, "x": _meta("x", item="tbl-9")}
    header = {"embed_instruction": "E", "rerank_instruction": "R"}
    text = rp.a6_report({"git commit": "abc"}, {"primary": (header, _recs())}, _qs(), meta, 30)
    assert "recall@5: **1/2 = 0.500**" in text and "reranker demotion 1" in text  # core 25 only
    assert (
        "## Supplement (reported separately" in text and "| s1 | S | U | primary | False |" in text
    )
    assert "Control candidates: top-5 for the owner to read" in text
    assert "ctrl1?" in text and "ctrl2?" in text  # all candidates until the owner chooses
    chosen = rp.a6_report({"x": 1}, {"primary": (header, _recs())}, _qs(), meta, 30, ["c2"])
    assert "Controls (the 5 accepted)" in chosen and "ctrl2?" in chosen and "ctrl1?" not in chosen


def test_composition_block_by_source_and_unit_and_not_exercised():
    meta = {
        "a": {"source": "big", "unit_id": "u1"},
        "b": {"source": "big", "unit_id": "u2"},
        "c": {"source": "tiny", "unit_id": "u3"},
    }
    qs = [
        {"set": "draft", "gold_chunk_id": "a"},
        {"set": "draft", "gold_chunk_id": "b"},
        {"set": "supplement", "gold_chunk_id": "c"},
        {"set": "control_candidate", "gold_chunk_id": None},
    ]
    text = rp.composition_block(qs, meta, ["big", "tiny", "zero"], None)
    assert "big 2 (u1 x1, u2 x1)" in text and "supplement (beside the 25)**: tiny 1 (u3 x1)" in text
    assert "not exercised by the 25 drafts: tiny, zero" in text
    assert "not exercised by drafts plus supplement: zero" in text
    assert "candidates (not yet chosen)" in text
    out = rp.finish(rp.header_block("T", {"k": 1}), text)
    assert "<!--composition-->" not in out and "## Composition by source and unit" in out


def test_supplement_report_is_separate_and_counts_its_own_requests():
    qs = [{"question_id": "s1", "set": "supplement", "source": "cbo", "gold_chunk_id": "g"}]
    runs = [_run(r, "s1", _ans()) for r in (1, 2, 3)]
    text = rp.supplement_report({"x": 1}, runs, qs, {"s1": ["c1", "g"]}, "structured_output")
    assert "no count, rate or kappa on the 25 includes them" in text
    assert "stop `end_turn` 3/3" in text and text.count("| s1 | cbo |") == 3


def _run(run, qid, answer=None, stop="end_turn", rtype="succeeded", out_tokens=10):
    return RunRecord(
        run,
        qid,
        rtype,
        stop,
        [],
        {"input_tokens": 100, "output_tokens": out_tokens},
        answer,
        None if answer else "bad",
    )


def _ans(cites=("c1",), text="It is 5."):
    return Answer.model_validate({"abstained": False, "abstention_reason": "",
                                  "sentences": [{"text": text, "cited_chunk_ids": list(cites)}]})  # fmt: skip


def test_a4_counts_and_pass_rule():
    supplied = {"q1": ["c1", "c2"], "q2": ["c1"]}
    runs = [
        _run(1, "q1", _ans()),
        _run(1, "q2", _ans(cites=("zz",))),  # cites an unsupplied ID
        _run(2, "q1", None),  # invalid
        _run(2, "q2", _ans(), stop="max_tokens"),
        _run(3, "q1", None, rtype="missing", stop=None),
    ]
    c = rp.a4_counts(runs, supplied, "structured_output")
    assert (c["n"], c["stop"], c["valid"], c["cited"]) == (5, 3, 3, 2)
    text = rp.a4_report({"x": 1}, runs, supplied, "structured_output")
    assert "FAIL" in text and "## Failures (4)" in text
    assert rp.normal_stop("strict_tool") == "tool_use"


def test_variance_flags_digit_disagreement():
    qs = [{"question_id": "q1", "answer_type": "number", "gold_answer": "5", "unanswerable": False}]
    runs = [_run(1, "q1", _ans(text="It is 5.")), _run(2, "q1", _ans(text="It is 5.")),
            _run(3, "q1", _ans(text="It is 6."))]  # fmt: skip
    text = rp.variance_report({"x": 1}, runs, qs)
    assert "digit-level disagreement: 1 of 1" in text and "q1" in text


def test_a7_projection_arithmetic():
    runs = [_run(1, f"q{i}", _ans(), out_tokens=100) for i in range(3)]
    matrix = {"seeds": [1, 2], "cells": [
        {"arm": "no_repair", "decomposition": "claimify"},
        {"arm": "rewrite", "decomposition": "claimify"},
        {"arm": "re_retrieve", "decomposition": "claimify", "max_iter": 2},
    ]}  # fmt: skip
    prices = {"batch_input": 1.0, "batch_output": 5.0}
    text = rp.a7_report({"x": 1}, runs, matrix, prices, n_questions=10)
    # calls: gen 2*10 + dec 20 + rewrite 1*2*10 + rr 2*2*10 = 100; per call 100*1+100*5 = 600 -> 0.06
    assert "| **total** | 100 | **0.06** |" in text and "WITHIN" in text


def test_claim_yield_counts_sentences():
    runs = [_run(1, "q1", _ans(text="A is 5. B is 6."))]
    text = rp.claim_yield_report({"x": 1}, runs, [{"question_id": "q1", "chunk_type": "table"}])
    assert "| table | 1 |" in text


# ---- probe ------------------------------------------------------------------------------------


UTILS = (
    'SYSTEM_PROMPT = """Judge it."""\n\nUSER_PROMPT = """Document: [DOCUMENT]\\nClaim: [CLAIM]"""\n'
)
README = (
    'doc = "D text."\nclaim_1 = "C one."\nclaim_2 = "C two."\n'
    "scorer = MiniCheck(model_name='flan-t5-large')\nprint(raw_prob)   # [0.1, 0.2]\n"
    "scorer = MiniCheck(model_name='Bespoke-MiniCheck-7B', cache_dir='./c')\n"
    "print(raw_prob)   # [0.9840446675150499, 0.010986349594852094]\n"
)


def test_extract_prompts_and_example():
    system, user = probe.extract_prompts(UTILS)
    assert system == "Judge it." and user == "Document: [DOCUMENT]\nClaim: [CLAIM]"
    ex = probe.extract_readme_example(README)
    assert ex["expected"] == [0.9840446675150499, 0.010986349594852094] and ex["doc"] == "D text."


def test_missing_template_stops_the_probe():
    with pytest.raises(probe.ProbeStop):
        probe.extract_prompts("X = 1\n")
    with pytest.raises(probe.ProbeStop):
        probe.extract_prompts('SYSTEM_PROMPT = "s"\nUSER_PROMPT = "no placeholders"\n')
    with pytest.raises(probe.ProbeStop):
        probe.extract_readme_example("nothing here")
    with pytest.raises(probe.ProbeStop):
        probe.check_gg_readme("a README without the groundedness example")


def test_fetch_failure_is_a_probe_stop():
    def boom(url):
        raise OSError("no network")

    with pytest.raises(probe.ProbeStop, match="cannot fetch"):
        probe.fetch_source("r", "repo", "p", "rev", "https://x", boom)


def test_source_records_sha256():
    s = probe.fetch_source("r", "repo", "p", "rev", "https://x", lambda u: b"hello")
    assert s.sha256 == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_pinned_commit_and_urls():
    assert re.fullmatch(r"[0-9a-f]{40}", probe.MINICHECK_COMMIT)
    assert probe.MINICHECK_COMMIT in probe.github_url(
        probe.MINICHECK_REPO, probe.MINICHECK_COMMIT, "a.py"
    )


def test_support_prob_and_tolerance():
    top = [("Yes", math.log(0.9)), ("yes", math.log(0.05)), ("No", math.log(0.03)), (" Yes", -1.0)]
    assert probe.support_prob(top) == pytest.approx(0.95)  # ' Yes' does not match (exact rule)
    assert probe.within([0.98, 0.01], [0.984, 0.011]) and not probe.within(
        [0.9, 0.01], [0.984, 0.011]
    )


def test_parse_gg_score():
    assert probe.parse_gg_score("<score> yes </score>") == "yes"
    assert probe.parse_gg_score("<think>x</think><score> No </score>") == "no"
    assert probe.parse_gg_score("garbled") is None


def test_alter_digits_and_claims():
    assert probe.alter_digits("1,022") == "1,023" and probe.alter_digits("$9") == "$0"
    with pytest.raises(ValueError):
        probe.alter_digits("none")
    chunks = {f"c{i}": {"chunk_id": f"c{i}", "unit_id": "u", "text": f"t{i}"} for i in range(6)}
    units = {"u": list(chunks.values())}
    qs = [{"question_id": "q1", "question": "How many?", "gold_answer": "1,022", "gold_chunk_id": "c0",
           "answer_type": "number", "unanswerable": False}]  # fmt: skip
    claims = probe.build_probe_claims(qs, chunks, units, n=4)
    assert len(claims) == 4  # supported/altered x one-chunk/five-chunk for the one question
    five = next(c for c in claims if c["context_chunks"] == 5)
    assert five["doc"].count("\n\n") == 4 and five["doc"].startswith("t0")
    assert {c["label"] for c in claims} == {"supported", "altered"}
    assert any("1,023" in c["claim"] for c in claims if c["label"] == "altered")
    assert probe.correct("altered", False) and not probe.correct("supported", False)


def test_report_records_repo_path_revision_and_stops(tmp_path: Path):
    s = probe.fetch_source("role", "o/r", "a/b.py", "deadbeef", "https://x", lambda u: b"x")
    text = probe.render_report(
        {"torch": "1"}, [s], {"Granite": "body"}, {"Bespoke-MiniCheck-7B": "no template"}
    )
    assert "o/r" in text and "`a/b.py`" in text and "`deadbeef`" in text and s.sha256 in text
    assert "## Stopped" in text and "no template" in text
