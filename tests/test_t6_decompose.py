"""T6 decomposer (D-044 item 2; status 2026-10-14 (5)): request shape (D-041 pins, no sampling
keys, structured output), the frozen prompt, the number guard, citation inheritance, abstention
exclusion, de-duplication, Batch only. Fake client and tmp_path only: no network, no API key."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ledger.baseline import reports
from ledger.baseline.schema import Answer
from ledger.claims import decompose as D
from ledger.claims.numbers import missing_numbers, numeric_tokens
from ledger.claims.schema import Decomposition
from ledger.config import REMOVED_SAMPLING_KEYS, load_config


@pytest.fixture
def cfg(base_config_path):
    return load_config(base_config_path)


def answer(*sentences):
    return Answer.model_validate(
        {
            "abstained": False,
            "abstention_reason": "",
            "sentences": [{"text": t, "cited_chunk_ids": ids} for t, ids in sentences],
        }
    )


def item(qid="q005", *sentences):
    sentences = sentences or (("In 1995, net lending (–), NIPA, was –106.3 billion.", ["a"]),)
    return D.AnswerItem(qid, "table", "What was it?", answer(*sentences))


def dec(*claims):
    return Decomposition.model_validate(
        {
            "claims": [
                {
                    "text": t,
                    "source_sentence_idx": i,
                    "qualifiers": {"entity": "", "unit": "", "period": ""},
                }
                for t, i in claims
            ]
        }
    )


# ---- number guard (status 2026-10-14 (5)) -------------------------------------------------------


def test_reports_num_unchanged():
    """D-043 status 2026-10-11 keeps the T5 numbers as committed: NUM is never edited."""
    assert reports.NUM.pattern == r"\d[\d,]*(?:\.\d+)?"


@pytest.mark.parametrize(
    "claim,ans,ok",
    [
        ("was −106.3 billion", "was –106.3 billion", True),  # minus mapping
        ("was 106.3 billion", "was –106.3 billion", False),  # sign difference drops
        ("is 106 billion", "is 106.3 billion", False),  # digit difference drops
        ("is 1,177 units", "is 1,177 units.", True),
        ("the 12th of the month", "includes the 12th of the month", True),
        ("SEC. 112C defines", "In SEC. 112C, the term", True),
        ("account 097-0810-0-1-051 had", "For account 097-0810-0-1-051, total", True),
        ("Table B-19 shows", "According to Table B-19, total", True),
        ("is -30,637 in millions", "is -30,637 in millions", True),
        ("is 30,637 in millions", "is -30,637 in millions", False),
        ("Table 02-1, a value", "Table 02-1, a value", True),
    ],
)
def test_number_guard(claim, ans, ok):
    assert (not missing_numbers(claim, ans)) is ok


def test_numeric_tokens_rule():
    # "," or "." is part of a token only when a digit follows it (D-043 status 2026-10-11)
    assert numeric_tokens("Table B-22, 22, 5.25. 1,967") == ["22", "22", "5.25", "1,967"]
    assert numeric_tokens("(−106.3)") == ["-106.3"]


def test_every_run1_shaped_sentence_passes_against_its_own_answer():
    sentences = [
        "For account 097-0810-0-1-051, total new obligations for 2025 are 967 million dollars.",
        "In 1995, net lending or net borrowing (–), NIPA, was –106.3 billion dollars.",
        "The 2027 Budget Discretionary Surplus/Funding Gap for 2030 is -30,637 in millions.",
        "According to the note to Table B-22, data in Tables B-22 through B-28 relate to the 12th.",
        "HEA § 112C(a)(1)(A)(i) is created by § 4 of H.R. 7683.",
    ]
    whole = " ".join(sentences)
    assert all(not missing_numbers(s, whole) for s in sentences)


# ---- guards ---------------------------------------------------------------------------------


def test_citation_inheritance_and_index_guard():
    it = item("q021", ("First fact 1.", ["c1"]), ("Second fact 2.", ["c2", "c3"]))
    recs = D.apply_guards(it, dec(("Second fact 2.", 1), ("First fact 1.", 0), ("Ghost 3.", 5)))
    assert [r.citations for r in recs[:2]] == [["c2", "c3"], ["c1"]]
    assert [r.claim_id for r in recs] == ["q021::c01", "q021::c02", "q021::x01"]
    assert recs[2].drop_reason == "sentence_index_out_of_range" and recs[2].citations == []


def test_number_guard_drops_and_records():
    recs = D.apply_guards(item(), dec(("Net lending in 1995 was 106.3 billion dollars.", 0)))
    assert not recs[0].kept and recs[0].drop_reason == "number_not_in_answer"
    assert recs[0].drop_detail == "106.3"


def test_duplicates_removed_first_kept():
    recs = D.apply_guards(
        item(),
        dec(
            ("Net lending in 1995 was –106.3 billion.", 0),
            ("net lending in 1995 was  -106.3 billion.", 0),
        ),
    )
    assert [r.kept for r in recs] == [True, False] and recs[1].drop_reason == "duplicate"


def run1_record(qid, content_obj, stop="end_turn", result="succeeded"):
    msg = {"content": [{"type": "text", "text": json.dumps(content_obj)}], "stop_reason": stop}
    return {"question_id": qid, "result_type": result, "payload": {"message": msg}}


def test_read_answers_excludes_abstentions_controls_and_supplement(cfg, tmp_path):
    cfg = cfg.model_copy(update={"paths": cfg.paths.model_copy(update={"results_dir": tmp_path})})
    good = {
        "abstained": False,
        "abstention_reason": "",
        "sentences": [{"text": "It was 5.", "cited_chunk_ids": ["a"]}],
    }
    absd = {"abstained": True, "abstention_reason": "not in chunks", "sentences": []}
    path = tmp_path / cfg.decomposition.input_cell / "1.jsonl"
    path.parent.mkdir(parents=True)
    rows = [
        run1_record("q001", good),
        run1_record("q003", absd),
        run1_record("c001", absd),
        run1_record("s001", good),
        run1_record("q004", good, stop="max_tokens"),
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    questions = [
        {"question_id": "q001", "set": "draft", "chunk_type": "table", "question": "Q1?"},
        {"question_id": "q003", "set": "draft", "chunk_type": "prose", "question": "Q3?"},
        {"question_id": "q004", "set": "draft", "chunk_type": "prose", "question": "Q4?"},
        {"question_id": "c001", "set": "control_candidate", "chunk_type": None, "question": "C?"},
        {"question_id": "s001", "set": "supplement", "chunk_type": "table", "question": "S?"},
    ]
    got = D.read_answers(cfg, questions)
    assert [i.question_id for i in got.items] == ["q001"]
    assert got.abstained == ["q003"] and got.unusable == ["q004"]


# ---- prompt freeze and request shape -----------------------------------------------------------


def test_prompt_is_frozen_at_the_pinned_hash(cfg):
    p = D.load_prompt(cfg)
    assert p.sha256 == cfg.decomposition.prompt_sha256
    assert "{question}" in p.template and "{sentences}" in p.template
    assert b"\r" not in Path(cfg.decomposition.prompt_path).read_bytes()


def test_prompt_mismatch_refuses(cfg, tmp_path):
    f = tmp_path / "p.md"
    f.write_bytes(Path(cfg.decomposition.prompt_path).read_bytes() + b" ")
    bad = cfg.model_copy(
        update={"decomposition": cfg.decomposition.model_copy(update={"prompt_path": f})}
    )
    with pytest.raises(D.PromptNotFrozen, match="frozen"):
        D.load_prompt(bad)
    empty = cfg.model_copy(
        update={"decomposition": cfg.decomposition.model_copy(update={"prompt_sha256": ""})}
    )
    with pytest.raises(D.PromptNotFrozen, match="empty"):
        D.load_prompt(empty)


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def test_request_has_d041_pins_structured_output_and_no_sampling_keys(cfg):
    params = D.build_params(cfg, D.load_prompt(cfg), question="Q {x}?", sentences=["A.", "B."])
    assert params["model"] == cfg.generator.model
    assert params["thinking"] == {"type": cfg.generator.thinking}
    assert params["output_config"]["effort"] == cfg.generator.effort
    assert params["output_config"]["format"]["type"] == "json_schema"
    assert params["max_tokens"] == cfg.decomposition.max_tokens
    assert not set(_keys(params)) & REMOVED_SAMPLING_KEYS
    user = params["messages"][0]["content"]
    assert user.startswith("Question: Q {x}?") and "[0] A.\n[1] B." in user
    assert "tools" not in params and "tool_choice" not in params


class FakeClient:
    def __init__(self):
        self.requests = []

    def submit(self, requests, token):
        self.requests.extend(requests)
        return "msgbatch_1"

    def find_batch(self, token):
        return None

    def poll(self, batch_id):
        return "in_progress"

    def results(self, batch_id):
        return iter(())


def test_batch_only_one_request_per_answer(cfg, tmp_path):
    cfg = cfg.model_copy(update={"paths": cfg.paths.model_copy(update={"results_dir": tmp_path})})
    client = FakeClient()
    items = [item("q001"), item("q002")]
    D.submit_or_collect(cfg, D.load_prompt(cfg), items, client, ledger_path=tmp_path / "j.jsonl")
    assert len(client.requests) == 2
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", r["custom_id"]) for r in client.requests)
    nobatch = cfg.model_copy(
        update={"generator": cfg.generator.model_copy(update={"use_batch": False})}
    )
    with pytest.raises(RuntimeError, match="Batch-only"):
        D.submit_or_collect(nobatch, D.load_prompt(cfg), items, client, ledger_path=tmp_path / "k")


def test_decomposer_never_calls_messages_create_synchronously():
    src = Path(D.__file__).read_text(encoding="utf-8") + Path("scripts/t6_decompose.py").read_text(
        encoding="utf-8"
    )
    assert "messages.create" not in src and ".messages.stream" not in src


def test_collect_writes_records_and_failures(cfg, tmp_path):
    cfg = cfg.model_copy(update={"paths": cfg.paths.model_copy(update={"results_dir": tmp_path})})
    items = [item("q005"), item("q006")]
    out = D.results_path(cfg)
    out.parent.mkdir(parents=True)
    ok = {
        "claims": [
            {
                "text": "Net lending in 1995 was –106.3 billion.",
                "source_sentence_idx": 0,
                "qualifiers": {"entity": "net lending", "unit": "billion", "period": "1995"},
            }
        ]
    }
    rows = [run1_record("q005", ok), run1_record("q006", ok, stop="max_tokens")]
    out.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    got = D.collect(cfg, items)
    assert [r.claim_id for r in got.records] == ["q005::c01"]
    assert got.failed == {"q006": "stop_reason max_tokens"}
    inp = D.input_path(cfg)
    inp.parent.mkdir(parents=True, exist_ok=True)
    inp.write_text("{}\n", encoding="utf-8")
    manifest = D.claims_manifest(cfg, D.load_prompt(cfg), items, got)
    D.write_claims(tmp_path / "claims.jsonl", manifest, got.records)
    m, recs = D.read_claims(tmp_path / "claims.jsonl")
    assert m["prompt_sha256"] == cfg.decomposition.prompt_sha256 and m["claims_kept"] == 1
    assert recs[0].citations == ["a"] and recs[0].stratum == "table"
    assert "q006" in D.render_report(m, items, got)
