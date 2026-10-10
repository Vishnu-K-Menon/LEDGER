# ruff: noqa: E501
"""Request shapes for both output modes (D-043 item 5), the Answer schema, the parser and D13's
retry. No API call."""

import json

import pytest

from ledger.baseline.request import (
    OutputModeUnset,
    build_params,
    require_output_mode,
    retry_params,
)
from ledger.baseline.run import make_build_request, run_cells, submit_or_collect
from ledger.baseline.schema import (
    TOOL_NAME,
    Answer,
    AnswerInvalid,
    answer_json_schema,
    parse_answer,
)
from ledger.config import load_config
from ledger.matrix.jobs import JobKey

CHUNKS = [("c1", "alpha"), ("c2", "beta")]
GOOD = {
    "abstained": False,
    "abstention_reason": "",
    "sentences": [{"text": "It is $1,022 billion.", "cited_chunk_ids": ["c1"]}],
}
ABSTAIN = {"abstained": True, "abstention_reason": "Not in the chunks.", "sentences": []}


def _gen(base_config_path):
    return load_config(base_config_path).generator


def _no_sampling(body):
    assert not ({"temperature", "top_p", "top_k"} & set(body))


def _all_objects_closed(schema):
    stack = [schema]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
            stack += list(node.values())
        elif isinstance(node, list):
            stack += node


def test_structured_output_merges_into_effort(base_config_path):
    body = build_params(
        _gen(base_config_path), question="q?", chunks=CHUNKS, output_mode="structured_output"
    )
    assert body["model"] == "claude-sonnet-5-5"
    assert body["thinking"] == {"type": "between_tools"}  # D-041
    assert body["output_config"]["effort"] == "high"  # not replaced
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert "tools" not in body and "tool_choice" not in body
    _no_sampling(body)
    _all_objects_closed(body["output_config"]["format"]["schema"])


def test_strict_tool_shape(base_config_path):
    body = build_params(
        _gen(base_config_path), question="q?", chunks=CHUNKS, output_mode="strict_tool"
    )
    (tool,) = body["tools"]
    assert tool["name"] == TOOL_NAME and tool["strict"] is True
    assert body["tool_choice"] == {"type": "auto"}  # forced tool use is 400 on 5.5 (D-041)
    assert body["output_config"] == {"effort": "high"}
    assert body["thinking"] == {"type": "between_tools"}
    _no_sampling(body)
    _all_objects_closed(tool["input_schema"])


def test_context_labels_chunks_with_ids(base_config_path):
    body = build_params(
        _gen(base_config_path), question="Q?", chunks=CHUNKS, output_mode="structured_output"
    )
    text = body["messages"][0]["content"]
    assert '<chunk id="c1">' in text and "Question: Q?" in text
    assert "Cite every sentence" in body["system"]


def test_both_modes_share_one_schema(base_config_path):
    a = build_params(
        _gen(base_config_path), question="q", chunks=CHUNKS, output_mode="structured_output"
    )
    b = build_params(_gen(base_config_path), question="q", chunks=CHUNKS, output_mode="strict_tool")
    assert a["output_config"]["format"]["schema"] == b["tools"][0]["input_schema"]


def test_unknown_mode_and_unset_mode(base_config_path):
    with pytest.raises(ValueError):
        build_params(_gen(base_config_path), question="q", chunks=CHUNKS, output_mode="")
    with pytest.raises(OutputModeUnset):
        require_output_mode(_gen(base_config_path))


def test_answer_validation_rules():
    assert Answer.model_validate(GOOD).cited_ids() == ["c1"]
    assert Answer.model_validate(ABSTAIN).abstained
    for bad in (
        {**GOOD, "sentences": []},
        {**GOOD, "sentences": [{"text": "x", "cited_chunk_ids": []}]},
        {**ABSTAIN, "sentences": GOOD["sentences"]},
        {**ABSTAIN, "abstention_reason": " "},
        {**GOOD, "extra": 1},
    ):
        with pytest.raises(ValueError):
            Answer.model_validate(bad)


def test_schema_has_no_unsupported_keywords():
    text = json.dumps(answer_json_schema())
    for kw in ("minLength", "maxLength", "minimum", "maximum", "pattern", "anyOf", "default"):
        assert kw not in text


def test_parse_both_modes():
    structured = [{"type": "text", "text": json.dumps(GOOD)}]
    tool = [{"type": "tool_use", "id": "t1", "name": TOOL_NAME, "input": GOOD}]
    assert parse_answer(structured, output_mode="structured_output").abstained is False
    assert parse_answer(tool, output_mode="strict_tool").cited_ids() == ["c1"]
    with pytest.raises(AnswerInvalid):
        parse_answer([{"type": "text", "text": "not json"}], output_mode="structured_output")
    with pytest.raises(AnswerInvalid):  # prose reply: tool_choice auto did not force the call
        parse_answer([{"type": "text", "text": "The answer is 5"}], output_mode="strict_tool")
    with pytest.raises(AnswerInvalid):
        parse_answer(tool, output_mode="bogus")


def test_retry_text_mode_appends_error_turn(base_config_path):
    params = build_params(
        _gen(base_config_path), question="q", chunks=CHUNKS, output_mode="structured_output"
    )
    content = [{"type": "text", "text": "{bad"}]
    r = retry_params(params, content, "boom", output_mode="structured_output")
    assert len(r["messages"]) == len(params["messages"]) + 2
    assert r["messages"][-2] == {"role": "assistant", "content": content}
    assert "boom" in r["messages"][-1]["content"]
    assert len(params["messages"]) == 1  # original untouched


def test_retry_tool_mode_answers_the_tool_call(base_config_path):
    params = build_params(
        _gen(base_config_path), question="q", chunks=CHUNKS, output_mode="strict_tool"
    )
    content = [{"type": "tool_use", "id": "t9", "name": TOOL_NAME, "input": {}}]
    r = retry_params(params, content, "boom", output_mode="strict_tool")
    tr = r["messages"][-1]["content"][0]
    assert tr["type"] == "tool_result" and tr["tool_use_id"] == "t9" and tr["is_error"] is True


# ---- runs -------------------------------------------------------------------------------------


class _FakeBatch:
    def __init__(self):
        self.submits = []

    def submit(self, requests, token):
        self.submits.append(requests)
        return "b1"

    def find_batch(self, token):
        return None

    def poll(self, batch_id):
        return "in_progress"

    def results(self, batch_id):
        return []


def _contexts():
    return [
        {
            "question_id": f"q{i:03d}",
            "question": f"Q{i}?",
            "chunks": [{"chunk_id": "c1", "text": "a"}],
        }
        for i in range(1, 31)
    ]


def test_run_cells_are_repeat_cells_not_seeds(base_config_path):
    assert run_cells(load_config(base_config_path)) == [
        "t5_baseline_r1",
        "t5_baseline_r2",
        "t5_baseline_r3",
    ]


def test_submit_refuses_while_output_mode_empty(base_config_path, tmp_path):
    cfg = load_config(base_config_path)
    with pytest.raises(OutputModeUnset):
        submit_or_collect(cfg, _contexts(), _FakeBatch(), ledger_path=tmp_path / "jobs.jsonl")


def test_one_batch_of_ninety_at_seed_one(base_config_path, tmp_path):
    cfg = load_config(base_config_path)
    cfg = cfg.model_copy(
        update={"generator": cfg.generator.model_copy(update={"output_mode": "structured_output"})}
    )
    fake = _FakeBatch()
    summary = submit_or_collect(cfg, _contexts(), fake, ledger_path=tmp_path / "jobs.jsonl")
    assert summary.submitted_new == 90 and len(fake.submits) == 1 and len(fake.submits[0]) == 90
    # re-invoking never resubmits a recorded batch (jobs ledger)
    again = submit_or_collect(cfg, _contexts(), fake, ledger_path=tmp_path / "jobs.jsonl")
    assert len(fake.submits) == 1 and again.still_in_flight == 90


def test_build_request_uses_the_context(base_config_path):
    cfg = load_config(base_config_path)
    ctx = {c["question_id"]: c for c in _contexts()}
    body = make_build_request(cfg, ctx, "structured_output")(JobKey("t5_baseline_r1", 1, "q001"))
    assert "Q1?" in body["messages"][0]["content"]


def test_batch_and_runner_code_never_calls_the_generator_synchronously(repo_root):
    """D28: only the drafting, dry-run and A5 probe scripts may call messages.create."""
    for rel in (
        "ledger/baseline/run.py",
        "ledger/baseline/batch.py",
        "ledger/baseline/request.py",
        "ledger/matrix/jobs.py",
        "scripts/t5_batch.py",
    ):
        assert "messages.create(" not in (repo_root / rel).read_text("utf-8"), rel
