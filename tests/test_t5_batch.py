# ruff: noqa: E501
"""AnthropicBatchClient: find_batch recovery by sidecar + request count + custom_ids (owner rules:
10-minute skew margin, one candidate -> return, none -> None, several -> raise)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as NS

import pytest

from ledger.baseline.batch import SKEW, AmbiguousBatch, AnthropicBatchClient

T0 = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
REQS = [{"custom_id": f"id{i}", "params": {}} for i in range(3)]


def _counts(n, ended=True):
    return NS(
        processing=0 if ended else n, succeeded=n if ended else 0, errored=0, canceled=0, expired=0
    )


def _batch(bid, created, n=3, status="ended"):
    return NS(
        id=bid,
        created_at=created,
        request_counts=_counts(n, status == "ended"),
        processing_status=status,
    )


class _Batches:
    def __init__(self, existing=(), results=None):
        self.existing = list(existing)
        self.result_ids = results or {}
        self.created = []

    def create(self, requests):
        self.created.append(requests)
        return NS(id="new")

    def list(self, limit=None):
        return iter(sorted(self.existing, key=lambda b: b.created_at, reverse=True))

    def results(self, bid):
        return [NS(custom_id=c) for c in self.result_ids[bid]]

    def retrieve(self, bid):
        return NS(processing_status="ended")


def _client(tmp_path, batches, now=T0):
    api = NS(messages=NS(batches=batches))
    return AnthropicBatchClient(api, tmp_path / "side.jsonl", now=lambda: now)


def _intent(tmp_path, batches, now=T0):
    c = _client(tmp_path, batches, now)
    c.submit(REQS, "tok")
    return c


def test_submit_writes_sidecar_before_the_api_call(tmp_path):
    order = []

    class B(_Batches):
        def create(self, requests):
            order.append("create:" + str((tmp_path / "side.jsonl").exists()))
            return super().create(requests)

    c = _client(tmp_path, B())
    assert c.submit(REQS, "tok") == "new"
    assert order == ["create:True"]
    assert (tmp_path / "side.jsonl").read_text("utf-8").count('"token": "tok"') == 1


def test_skew_constant_is_ten_minutes():
    assert SKEW == timedelta(minutes=10)


def test_unknown_token_returns_none(tmp_path):
    assert _client(tmp_path, _Batches()).find_batch("nope") is None


def test_single_ended_candidate_confirmed_by_custom_ids(tmp_path):
    b = _Batches([_batch("A", T0 + timedelta(minutes=1))], {"A": ["id0", "id1", "id2"]})
    assert _intent(tmp_path, b).find_batch("tok") == "A"


def test_ended_candidate_with_other_custom_ids_is_excluded(tmp_path):
    b = _Batches([_batch("A", T0 + timedelta(minutes=1))], {"A": ["x", "y", "z"]})
    assert _intent(tmp_path, b).find_batch("tok") is None


def test_in_progress_candidate_is_returned_unconfirmed(tmp_path):
    b = _Batches([_batch("A", T0 + timedelta(minutes=1), status="in_progress")])
    assert _intent(tmp_path, b).find_batch("tok") == "A"


def test_wrong_request_count_is_not_a_candidate(tmp_path):
    b = _Batches([_batch("A", T0 + timedelta(minutes=1), n=4, status="in_progress")])
    assert _intent(tmp_path, b).find_batch("tok") is None


def test_clock_skew_local_clock_ahead_of_server(tmp_path):
    """Local clock 8 minutes AHEAD of the server: the server stamps created_at 8 minutes before the
    local time at which we recorded the intent. Inside the 10-minute margin it is still found."""
    inside = _Batches([_batch("A", T0 - timedelta(minutes=8), status="in_progress")])
    assert _intent(tmp_path, inside).find_batch("tok") == "A"


def test_clock_skew_beyond_the_margin_is_not_found(tmp_path):
    outside = _Batches([_batch("A", T0 - timedelta(minutes=11), status="in_progress")])
    assert _intent(tmp_path, outside).find_batch("tok") is None


def test_two_candidates_raise(tmp_path):
    b = _Batches(
        [
            _batch("A", T0 + timedelta(minutes=1), status="in_progress"),
            _batch("B", T0 + timedelta(minutes=2), status="in_progress"),
        ]
    )
    with pytest.raises(AmbiguousBatch):
        _intent(tmp_path, b).find_batch("tok")


def test_results_payload_and_types(tmp_path):
    ok = NS(
        custom_id="id0",
        result=NS(
            type="succeeded", message=NS(model_dump=lambda mode: {"content": [], "usage": {}})
        ),
    )
    bad = NS(custom_id="id1", result=NS(type="expired"))
    b = _Batches()
    b.results = lambda bid: [ok, bad]
    out = list(_client(tmp_path, b).results("A"))
    assert out[0].type == "succeeded" and out[0].payload["message"]["content"] == []
    assert out[1].type == "expired" and out[1].payload == {}
