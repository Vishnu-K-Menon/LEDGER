# ruff: noqa: E501
"""Answer matching (D-043 status 2026-10-10, answer matching), the variance report built on it,
the controls abstention interval, the harness check and its question selection."""

import json
import math
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from ledger.baseline import harness, match
from ledger.baseline import reports as rp
from ledger.baseline.join import (
    JoinRefused,
    harness_contexts,
    harness_questions,
    read_controls_accepted,
    select_questions,
)
from ledger.baseline.run import RunRecord
from ledger.baseline.schema import Answer, Sentence
from ledger.config import load_config


@pytest.fixture(scope="module")
def golds(repo_root: Path) -> dict[str, dict]:
    path = repo_root / "data" / "questions_draft.jsonl"
    rows = [json.loads(ln) for ln in path.read_text("utf-8").splitlines() if ln.strip()]
    return {r["question_id"]: r for r in rows}


def run_rec(
    qid, run, text=None, *, abstain=False, result="succeeded", stop="end_turn", cites=("c1",)
):
    if text is None and not abstain:
        return RunRecord(run, qid, result, stop, [], {}, None, "no usable answer")
    ans = (
        Answer(abstained=True, abstention_reason="not in the chunks", sentences=[])
        if abstain
        else Answer(
            abstained=False,
            abstention_reason="",
            sentences=[Sentence(text=text, cited_chunk_ids=list(cites))],
        )
    )
    return RunRecord(run, qid, result, stop, [], {}, ans, None)


# ---- the owner's nine cases (question, gold from the tracked questions file, answer -> outcome)
# The owner's candidate labels in comments: t01=q001, t22=q010, t26=q012, t07=q005, t08=q006,
# p06=q016, p09=q018, p17=q025.

OWNER_CASES = [
    ("q010", "177", "outlays were 1,177 million", "miss", False),
    ("q012", "5.25", "the prime rate was 15.25 percent", "miss", False),
    ("q001", "967", "obligations were 1,967 million", "miss", False),
    ("q005", "–106.3", "net borrowing was -106.3 billion", "hit", True),
    ("q005", "–106.3", "net borrowing was (106.3) billion", "miss", False),
    ("q006", "84,804", "unpaid obligations were 84804 million", "miss", False),
    ("q016", "$194,653 million", "the requirement is $194.653 billion", "miss", False),
]


@pytest.mark.parametrize(("qid", "gold", "answer", "expected", "minus"), OWNER_CASES)
def test_owner_numeric_cases(golds, qid, gold, answer, expected, minus):
    assert golds[qid]["gold_answer"] == gold  # the case is about the gold as stored
    assert golds[qid]["answer_type"] == "number"
    r = run_rec(qid, 1, answer)
    m = match.classify_run("number", gold, r)
    assert (m.status, m.needed_minus) == (expected, minus)


@pytest.mark.parametrize(
    ("qid", "gold", "answer"),
    [
        ("q018", "12th", "the week including the 112th day"),
        ("q025", "§ 4", "created by § 41 of the bill"),
    ],
)
def test_owner_short_phrase_cases_have_no_containment(golds, qid, gold, answer):
    assert golds[qid]["gold_answer"] == gold and golds[qid]["answer_type"] == "short_phrase"
    assert (
        match.classify_run("short_phrase", gold, run_rec(qid, 1, answer)).status
        == match.NOT_CONTAINED
    )


def test_every_gold_embedded_in_a_plain_sentence(golds):
    n_num = n_phr = 0
    for qid, q in golds.items():
        if q["set"] not in ("draft", "supplement"):
            continue
        r = run_rec(qid, 1, f"The answer is {q['gold_answer']} in the report.")
        m = match.classify_run(q["answer_type"], q["gold_answer"], r)
        if q["answer_type"] == "number":
            assert m.status == match.HIT, qid
            n_num += 1
        else:
            assert m.status == match.CONTAINED, qid
            n_phr += 1
    assert (n_num, n_phr) == (15, 11)  # 14 numeric drafts + s001; 11 short_phrase drafts


@pytest.mark.parametrize(
    ("gold", "answer", "hit", "minus"),
    [
        ("106.3", "(106.3)", True, False),
        ("-106.3", "(106.3)", False, False),
        ("1,177", "$1,177 million", True, False),
        ("15.25", "15.25%", True, False),
        ("15.25", "115.25", False, False),
        ("1,967", "1,967.5", False, False),
        ("84804", "184804", False, False),
        ("$194.653 billion", "it is $194.653 billion.", True, False),
        ("-106.3", "−106.3", True, True),
        ("-106.3", "–106.3", True, True),
        ("177", "values 177, 178", True, False),
        ("177", "it was 177.", True, False),
        ("2020", "fiscal 2019-2020", False, False),  # a hyphen before a digit is a minus (3(b))
        ("14.79", "14.79 and 114.79", True, False),
        ("5", "5.25", False, False),
        ("19", "1,9", False, False),
        ("a  b", "a b", True, False),
    ],
)
def test_numeric_guard_extras(gold, answer, hit, minus):
    assert match.numeric_match(gold, answer) == (hit, minus and hit)


def test_short_phrase_containment_is_case_folded_and_whitespace_collapsed():
    assert match.lexical_containment(
        "Multiple  Award   Schedule", "the multiple award schedule program"
    )
    assert not match.lexical_containment("12th", "112th")
    assert not match.lexical_containment("§ 4", "§ 41")
    assert match.lexical_containment("112th", "the 112th Congress")


def test_abstained_and_invalid_runs_are_never_matched():
    quote = run_rec("q010", 1, abstain=True)
    assert match.classify_run("number", "177", quote).status == match.ABSTAINED
    # an abstention is not matched even when it would quote the number
    cases = [
        run_rec("q010", 1, None, result="errored", stop=None),
        run_rec("q010", 1, None, result="expired", stop=None),
        run_rec("q010", 1, "The answer is 177.", stop="max_tokens"),
        run_rec("q010", 1, "The answer is 177.", result="canceled", stop=None),
    ]
    for r in cases:
        assert match.classify_run("number", "177", r).status == match.INVALID


def test_summarize_sums_to_the_denominator():
    runs = [
        match.classify_run("number", "177", r)
        for r in (
            run_rec("a", 1, "177"),
            run_rec("a", 2, "1,177"),
            run_rec("a", 3, abstain=True),
            run_rec("a", 4, None, result="errored", stop=None),
        )
    ]
    s = match.summarize(runs)
    assert (s["hit"], s["miss"], s["abstained"], s["invalid"]) == (1, 1, 1, 1)
    assert s["hit"] + s["miss"] + s["abstained"] + s["invalid"] == len(runs)


# ---- the variance report ------------------------------------------------------------------------

QUESTIONS = [
    {
        "question_id": "A",
        "set": "draft",
        "answer_type": "number",
        "gold_answer": "–106.3",
        "unanswerable": False,
    },
    {
        "question_id": "B",
        "set": "draft",
        "answer_type": "number",
        "gold_answer": "177",
        "unanswerable": False,
    },
    {
        "question_id": "P",
        "set": "draft",
        "answer_type": "short_phrase",
        "gold_answer": "12th",
        "unanswerable": False,
    },
]


def _runs():
    return [
        run_rec("A", 1, "net borrowing was -106.3 billion"),
        run_rec("A", 2, abstain=True),
        run_rec("A", 3, None, result="errored", stop=None),
        run_rec("B", 1, "outlays were 1,177"),
        run_rec("B", 2, "outlays were 177"),
        run_rec("B", 3, "outlays were 177"),
        run_rec("P", 1, "the 12th"),
        run_rec("P", 2, "the 112th"),
        run_rec("P", 3, abstain=True),
    ]


def test_variance_report_keeps_every_run_in_the_denominator():
    text = rp.variance_report({"k": "v"}, _runs(), QUESTIONS, {"B": ["outlays 177", "other"]})
    assert "Numeric items (2) x runs = 6 runs, all in the denominator" in text
    assert "hits 3, misses 1, abstained 1, invalid 1 (sum 6 of 6)" in text
    assert "hits that needed the minus mapping: 1" in text
    assert "- B run 1: gold `177`; answer: 'outlays were 1,177'" in text
    assert "Not checked at T5" in text
    assert "lexical containment, NOT correctness" in text
    assert "contained 1, not contained 1, abstained 1, invalid 0 (sum 3 of 3)" in text
    # digit disagreement (committed definition: any run-to-run difference in the numeric tokens), which is in none of the supplied texts
    assert "digit-level disagreement: 3 of 3 answerable questions" in text
    assert "differing tokens ['1,177', '177']" in text
    assert "in none of the run's five supplied chunk texts: 1**" in text


def test_variance_report_without_contexts_says_so():
    text = rp.variance_report({}, _runs(), QUESTIONS)
    assert "n/a (contexts missing)" in text


# ---- controls: exact interval and the abstention report -------------------------------------------


def test_clopper_pearson_known_values():
    lo, hi = rp.clopper_pearson(5, 5)
    assert math.isclose(lo, 0.5 ** (1 / 5) if False else 0.4782, abs_tol=2e-3) and hi == 1.0
    assert rp.clopper_pearson(0, 5)[0] == 0.0
    assert math.isclose(rp.clopper_pearson(0, 5)[1], 0.5218, abs_tol=2e-3)
    lo, hi = rp.clopper_pearson(3, 10)
    assert math.isclose(lo, 0.0667, abs_tol=2e-3) and math.isclose(hi, 0.6525, abs_tol=2e-3)


def test_controls_abstention_report_by_kind_and_tag():
    qs = [
        {"question_id": "c001", "set": "control_candidate", "control_kind": "absent_entity"},
        {"question_id": "c002", "set": "control_candidate", "control_kind": "out_of_range_period"},
        {"question_id": "c003", "set": "control_candidate", "control_kind": "out_of_range_period"},
    ]
    controls = {
        "checked_by": "o",
        "question_ids": ["c001", "c002", "c003"],
        "candidates": [
            {"id": "c001", "decision": "accept", "reason": "r", "tag": None},
            {"id": "c002", "decision": "accept", "reason": "r", "tag": "near_miss"},
            {"id": "c003", "decision": "accept", "reason": "r", "tag": "near_miss"},
        ],
    }
    runs = [
        run_rec("c001", 1, abstain=True),
        run_rec("c002", 1, abstain=True),
        run_rec("c003", 1, "an answer"),
        run_rec("c001", 2, "run 2 is ignored"),
    ]
    text = rp.controls_abstention_report({}, runs, qs, controls)
    assert "not a rate" in text
    assert "| all accepted controls | 2 of 3 |" in text
    assert "| kind: out_of_range_period | 1 of 2 |" in text
    assert "| tag: near_miss | 1 of 2 |" in text
    assert "c003 (out_of_range_period, tag near_miss): ANSWERED" in text


def test_controls_rule_text_and_no_gate(base_config_path):
    arms = {"primary": [{"question_id": "c001", "top5": ["x"]}]}
    qs = [
        {"question_id": "c001", "set": "control_candidate", "question": "q?", "control_kind": "k"}
    ]
    text = rp.a6_controls_section(arms, qs, None)
    assert "near_miss" in text and "fewer than five" in text and "asked quantity" in text
    assert "Accept 5 after reading" not in text
    assert "1 candidates were retrieved" in text  # the count is computed, not written
    # nothing gates on abstention_controls_min: it is defined in the config and read nowhere else
    users = [
        str(p)
        for d in ("ledger", "scripts")
        for p in Path(d).rglob("*.py")
        if "abstention_controls_min" in p.read_text("utf-8")
    ]
    assert [Path(u).name for u in users] == ["config.py"]


def test_richer_controls_file_is_accepted(tmp_path):
    qs = [{"question_id": f"c00{i}", "set": "control_candidate"} for i in range(1, 8)]
    f = tmp_path / "controls_accepted.json"
    f.write_text(
        json.dumps(
            {
                "checked_by": "owner",
                "question_ids": ["c001", "c002", "c003", "c005", "c006"],
                "candidates": [
                    {
                        "id": "c004",
                        "decision": "reject",
                        "reason": "answered",
                        "tag": None,
                        "rejecting_chunk_id": "x::p1::txt-1::s0",
                    },
                    {"id": "c001", "decision": "accept", "reason": "no answer", "tag": "near_miss"},
                ],
                "note": "extra keys are ignored",
            }
        ),
        encoding="utf-8",
    )
    assert read_controls_accepted(f, qs, 5) == ["c001", "c002", "c003", "c005", "c006"]


# ---- A6 per-miss gold string ---------------------------------------------------------------------


def test_a6_miss_table_says_whether_the_gold_string_is_in_a_top5_chunk():
    meta = {
        "g": {"unit_id": "u", "item": "tbl-1", "source": "s", "text": "gold chunk 1,177"},
        "x": {"unit_id": "u", "item": "tbl-2", "source": "s", "text": "other chunk 177 here"},
    }
    rec = {
        "question_id": "q1",
        "gold_chunk_id": "g",
        "top5": ["x"],
        "gold_rank_dense": 3,
        "gold_rank_rerank": 9,
    }
    header = {"embed_instruction": "e", "rerank_instruction": "r"}
    text = rp.a6_arm_section("primary", header, [rec], meta, 100, {"q1": ("number", "177")})
    assert "| gold string in a top-5 chunk |" in text and "yes: `x`" in text
    assert "recall@5: **0/1" in text  # recall unchanged by the extra column
    text2 = rp.a6_arm_section("primary", header, [rec], meta, 100, {"q1": ("number", "999")})
    assert "| no |" in text2


# ---- harness check ---------------------------------------------------------------------------------


def _msg(stop="end_turn", content=None, cites=("a",), abstained=False):
    body = (
        {"abstained": True, "abstention_reason": "no", "sentences": []}
        if abstained
        else {
            "abstained": False,
            "abstention_reason": "",
            "sentences": [{"text": "x", "cited_chunk_ids": list(cites)}],
        }
    )
    block = SimpleNamespace(
        model_dump=lambda mode="json": (
            {"type": "text", "text": json.dumps(body)} if content is None else content
        )
    )
    usage = SimpleNamespace(
        input_tokens=11, output_tokens=7, output_tokens_details=SimpleNamespace(thinking_tokens=3)
    )
    return SimpleNamespace(content=[block], stop_reason=stop, usage=usage)


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **params):
        self.calls.append(params)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


CTX = {
    "question_id": "s001",
    "set": "supplement",
    "question": "q?",
    "chunks": [{"chunk_id": "a", "text": "t"}],
}


def test_harness_pass_row():
    gen = load_config().generator
    row = harness.check_question(FakeClient([_msg()]), gen, CTX, "structured_output")
    assert (row["accepted"], row["stop_reason"], row["parse"], row["cited_ok"]) == (
        True,
        "end_turn",
        "ok",
        True,
    )
    assert (row["input_tokens"], row["output_tokens"], row["thinking_tokens"]) == (11, 7, 3)
    assert harness.overall_pass([row])


def test_harness_sends_one_call_in_the_configured_mode_only():
    gen = load_config().generator
    c = FakeClient([_msg()])
    harness.check_question(c, gen, CTX, "structured_output")
    assert len(c.calls) == 1
    assert "tools" not in c.calls[0] and "format" in c.calls[0]["output_config"]


@pytest.mark.parametrize(
    "reply",
    [
        _msg(stop="max_tokens"),
        _msg(stop="refusal"),
        _msg(content={"type": "text", "text": "not json"}),
        _msg(content={"type": "text", "text": ""}),
    ],
)
def test_harness_fails_on_stop_or_parse(reply):
    gen = load_config().generator
    row = harness.check_question(FakeClient([reply]), gen, CTX, "structured_output")
    assert not harness.row_passes(row) and not harness.overall_pass([row])


def test_harness_fails_when_the_request_is_not_accepted():
    gen = load_config().generator
    resp = httpx.Response(400, request=httpx.Request("POST", "http://x"), text="bad request")
    err = anthropic.BadRequestError("bad", response=resp, body=None)
    row = harness.check_question(FakeClient([err]), gen, CTX, "structured_output")
    assert row["accepted"] is False and "400" in row["detail"]
    assert not harness.overall_pass([row])


def test_harness_overall_needs_every_row_and_at_least_one():
    ok = {"accepted": True, "stop_reason": "end_turn", "parse": "ok"}
    bad = {"accepted": True, "stop_reason": "end_turn", "parse": "failed"}
    assert harness.overall_pass([ok, ok]) and not harness.overall_pass([ok, bad])
    assert not harness.overall_pass([])


def test_harness_cited_ids_outside_the_supplied_five_are_reported_not_gating():
    gen = load_config().generator
    row = harness.check_question(FakeClient([_msg(cites=("zzz",))]), gen, CTX, "structured_output")
    assert row["cited_ok"] is False and harness.row_passes(row)
    assert "FAIL" not in harness.render({}, [row], "structured_output").split("\n")[4]


def test_harness_report_has_the_columns():
    gen = load_config().generator
    row = harness.check_question(FakeClient([_msg()]), gen, CTX, "structured_output")
    text = harness.render({"model": "m"}, [row], "structured_output")
    for col in ("stop_reason", "accepted", "parse", "abstained", "input", "output", "thinking"):
        assert col in text
    assert "**PASS**" in text


# ---- question selection -------------------------------------------------------------------------


def _qs():
    return (
        [{"question_id": f"q{i:03d}", "set": "draft", "question": "q"} for i in range(1, 4)]
        + [{"question_id": "s001", "set": "supplement", "question": "q"}]
        + [
            {"question_id": f"c00{i}", "set": "control_candidate", "question": "q"}
            for i in range(1, 8)
        ]
    )


def test_harness_ids_are_s001_and_the_unaccepted_candidates():
    acc = ["c001", "c002", "c003", "c004", "c005"]
    ids = [q["question_id"] for q in harness_questions(_qs(), acc)]
    assert ids == ["s001", "c006", "c007"]
    batch = {q["question_id"] for q in select_questions(_qs(), acc)}
    assert not batch & set(ids) - {"s001"}  # unaccepted candidates are never in the Batch
    assert not set(ids) & {"q001", "q002", "q003"} and not set(ids) & set(acc)


def test_harness_contexts_come_from_the_primary_retrieval_and_the_verified_texts():
    acc = ["c001", "c002", "c003", "c004", "c005"]
    recs = [{"question_id": q["question_id"], "top5": ["a", "b"]} for q in _qs()]
    header = {"questions_sha256": "Q", "lock_chunks_sha256": "L"}
    ctx = harness_contexts(
        _qs(),
        (header, recs),
        {"a": "TA", "b": "TB"},
        questions_sha256="Q",
        lock_chunks_sha256="L",
        accepted_controls=acc,
    )
    assert [c["question_id"] for c in ctx] == ["s001", "c006", "c007"]
    assert ctx[0]["chunks"] == [{"chunk_id": "a", "text": "TA"}, {"chunk_id": "b", "text": "TB"}]
    with pytest.raises(JoinRefused, match="different questions"):
        harness_contexts(
            _qs(),
            (header, recs),
            {"a": "", "b": ""},
            questions_sha256="X",
            lock_chunks_sha256="L",
            accepted_controls=acc,
        )
    with pytest.raises(JoinRefused, match="lock-verified"):
        harness_contexts(
            _qs(),
            (header, recs),
            {"a": "TA"},
            questions_sha256="Q",
            lock_chunks_sha256="L",
            accepted_controls=acc,
        )


def test_harness_selection_on_the_real_questions_file(golds):
    qs = list(golds.values())
    acc = ["c001", "c002", "c003", "c004", "c005"]
    assert [q["question_id"] for q in harness_questions(qs, acc)] == ["s001", "c006", "c007"]


def test_dry_run_script_refuses_without_the_controls_file(tmp_path, monkeypatch, repo_root):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "t5_dry_run", repo_root / "scripts" / "t5_dry_run.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(mod, "CONTROLS", tmp_path / "missing.json")
    assert mod.main([]) == 2
