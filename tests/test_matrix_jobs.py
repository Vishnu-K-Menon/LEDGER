"""T14 resumability (D-025, D-009, D-030, D28): fake Batch client, tmp_path only - nothing here
writes to the repo's results/ and nothing touches the network or an API key."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ledger.matrix import jobs as jobs_mod
from ledger.matrix.cells import load_matrix
from ledger.matrix.jobs import (
    BatchResult,
    JobKey,
    JobLedger,
    SeedConflict,
    custom_id,
    run_seed,
)

CELLS = ["delete__claimify", "rewrite__claimify"]
QIDS = ["q1", "q2", "q3"]


class FakeClient:
    def __init__(self):
        self.submits: list[tuple[str, list[str]]] = []  # (batch_id, custom_ids)
        self.tokens: dict[str, str] = {}
        self.status: dict[str, str] = {}
        self.outcomes: dict[str, str] = {}  # custom_id -> result type (default succeeded)
        self.crash_after_accept = False
        self.polls: list[str] = []

    def submit(self, requests, token):
        bid = f"msgbatch_{len(self.submits) + 1}"
        self.submits.append((bid, [r["custom_id"] for r in requests]))
        self.tokens[token] = bid
        self.status[bid] = "in_progress"
        if self.crash_after_accept:
            raise RuntimeError("process died after the service accepted the batch")
        return bid

    def find_batch(self, token):
        return self.tokens.get(token)

    def poll(self, batch_id):
        self.polls.append(batch_id)
        return self.status[batch_id]

    def results(self, batch_id):
        ids = dict(self.submits)[batch_id]
        for cid in reversed(ids):  # out of order on purpose
            kind = self.outcomes.get(cid, "succeeded")
            payload = {"message": {"usage": {"output_tokens": 7}, "text": cid}}
            yield BatchResult(cid, kind, payload if kind == "succeeded" else {})


def _req(key: JobKey) -> dict:
    return {
        "model": "m",
        "max_tokens": 10,
        "messages": [{"role": "user", "content": key.question_id}],
    }


def _run(tmp_path, client, seed=1, **kw):
    led = JobLedger(tmp_path / "jobs.jsonl")
    s = run_seed(
        led,
        client,
        cells=CELLS,
        question_ids=QIDS,
        seed=seed,
        build_request=_req,
        results_dir=tmp_path / "results",
        **kw,
    )
    return led, s


def _results(tmp_path, cell, seed=1):
    p = tmp_path / "results" / cell / f"{seed}.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()]


def test_submit_persists_batch_id_then_later_invocation_polls_and_collects(tmp_path):
    c = FakeClient()
    led, s = _run(tmp_path, c)
    assert s.submitted_new == 6 and len(c.submits) == 1
    assert {r["batch_id"] for r in led.jobs.values()} == {"msgbatch_1"}
    # a fresh process: ledger reloaded from disk, batch still running -> poll only
    led, s = _run(tmp_path, c)
    assert len(c.submits) == 1 and s.polled_batches == 1 and s.still_in_flight == 6
    c.status["msgbatch_1"] = "ended"
    led, s = _run(tmp_path, c)
    assert len(c.submits) == 1 and s.collected == 6
    assert all(r["state"] == "completed" for r in led.jobs.values())


def test_completed_is_skipped(tmp_path):
    c = FakeClient()
    _run(tmp_path, c)
    c.status["msgbatch_1"] = "ended"
    _run(tmp_path, c)
    polls = len(c.polls)
    led, s = _run(tmp_path, c)
    assert s.skipped_completed == 6 and len(c.submits) == 1
    assert len(c.polls) == polls  # nothing in flight, nothing polled


def test_submitted_with_batch_id_is_never_resubmitted(tmp_path):
    c = FakeClient()
    _run(tmp_path, c)
    for _ in range(3):
        _run(tmp_path, c)
    assert len(c.submits) == 1


def test_expired_and_errored_resubmit_only_those(tmp_path):
    c = FakeClient()
    _run(tmp_path, c)
    c.outcomes[custom_id(JobKey("delete__claimify", 1, "q2"))] = "expired"
    c.outcomes[custom_id(JobKey("rewrite__claimify", 1, "q3"))] = "errored"
    c.status["msgbatch_1"] = "ended"
    led, s = _run(tmp_path, c)
    assert s.collected == 4 and s.resubmitted == 2
    assert len(c.submits) == 2
    redo = {r for r in c.submits[1][1]}
    assert redo == {
        custom_id(JobKey("delete__claimify", 1, "q2")),
        custom_id(JobKey("rewrite__claimify", 1, "q3")),
    }
    assert led.jobs[JobKey("delete__claimify", 1, "q1")]["attempt"] == 1
    assert led.jobs[JobKey("delete__claimify", 1, "q2")]["attempt"] == 2


def test_crash_between_submit_and_persist_does_not_double_submit(tmp_path):
    c = FakeClient()
    c.crash_after_accept = True
    with pytest.raises(RuntimeError):
        _run(tmp_path, c)
    assert len(c.submits) == 1
    c.crash_after_accept = False
    led, s = _run(tmp_path, c)  # re-run: intent found, batch recovered by token
    assert len(c.submits) == 1
    assert {r["batch_id"] for r in led.jobs.values()} == {"msgbatch_1"}


def test_crash_before_the_service_accepted_resends_under_the_same_token(tmp_path):
    class Down(FakeClient):
        def submit(self, requests, token):
            raise ConnectionError("never reached the service")

    with pytest.raises(ConnectionError):
        _run(tmp_path, Down())
    c = FakeClient()
    led, _ = _run(tmp_path, c)
    assert len(c.submits) == 1
    assert {r["state"] for r in led.jobs.values()} == {"submitted"}


def test_results_are_keyed_per_question_not_by_position(tmp_path):
    c = FakeClient()
    _run(tmp_path, c)
    c.status["msgbatch_1"] = "ended"
    _run(tmp_path, c)
    for cell in CELLS:
        recs = _results(tmp_path, cell)
        assert sorted(r["question_id"] for r in recs) == QIDS
        for r in recs:  # the payload carries the custom_id it was returned for
            assert r["payload"]["message"]["text"] == custom_id(JobKey(cell, 1, r["question_id"]))
            assert r["usage"] == {"output_tokens": 7}
            assert set(r) >= {"cell", "seed", "question_id", "batch_id", "result_type"}


def test_results_are_per_question_records_never_aggregates(tmp_path):
    c = FakeClient()
    _run(tmp_path, c)
    c.status["msgbatch_1"] = "ended"
    _run(tmp_path, c)
    assert len(_results(tmp_path, "delete__claimify")) == len(QIDS)
    assert sorted(p.name for p in (tmp_path / "results").rglob("*.jsonl")) == ["1.jsonl"] * 2


def test_result_writes_are_idempotent_by_key(tmp_path):
    c = FakeClient()
    led, _ = _run(tmp_path, c)
    c.status["msgbatch_1"] = "ended"
    _run(tmp_path, c)
    # force a re-collect of an already written key: no duplicate line
    k = JobKey("delete__claimify", 1, "q1")
    res = BatchResult(custom_id(k), "succeeded", {"message": {}})
    jobs_mod._write_result(tmp_path / "results", k, "msgbatch_1", res)
    assert len(_results(tmp_path, "delete__claimify")) == len(QIDS)


def test_one_seed_at_a_time_and_seed_flag(tmp_path):
    c = FakeClient()
    _run(tmp_path, c, seed=1)
    with pytest.raises(SeedConflict, match="confirm_seed_1_inspected"):
        _run(tmp_path, c, seed=2)
    with pytest.raises(SeedConflict, match="one seed at a time"):
        _run(tmp_path, c, seed=2, confirm_seed_1_inspected=True)
    c.status["msgbatch_1"] = "ended"
    _run(tmp_path, c, seed=1)
    _run(tmp_path, c, seed=2, confirm_seed_1_inspected=True)  # seed 1 finished: allowed
    assert len(c.submits) == 2


def test_runner_never_builds_a_real_client_or_sampling_params():
    src = Path(jobs_mod.__file__).read_text(encoding="utf-8")
    assert "import anthropic" not in src and "from anthropic" not in src
    for banned in ("temperature", "top_p", "top_k"):
        assert banned not in src.replace("No sampling parameters", "")


def test_matrix_template_has_the_ten_d26_cells_and_two_seeds(repo_root):
    m = load_matrix(repo_root / "experiments" / "matrix.yaml")
    assert m.seeds == [1, 2] and len(m.cells) == 10
    graft = [c for c in m.cells if c.arm == "re_retrieve" and (c.max_iter or 0) > 1]
    assert {c.max_iter for c in graft} == {2, 3}
    assert all(c.decomposition == "claimify" for c in graft)
    assert sum(c.decomposition == "sentence_split" for c in m.cells) == 4
