"""The real ``BatchClient`` (Protocol in ``ledger/matrix/jobs.py``), over the Anthropic Batch API.

``find_batch(token)``: the Batch API has no metadata or token field, so a token cannot be looked up
server-side. ``submit`` therefore writes a sidecar record BEFORE the API call::

    {token, n_requests, custom_ids, submitted_after}

``submitted_after`` is the local clock minus ``SKEW`` (10 minutes), so a local clock that runs ahead
of the server's ``created_at`` does not hide the batch. ``find_batch`` lists batches (newest first)
created after it whose ``request_counts`` total equals ``n_requests``; an ended candidate is
confirmed by its result ``custom_id`` set, an in-progress one cannot be confirmed and stays a
candidate. Exactly one candidate -> its id; none -> ``None`` (the caller then resubmits under the
same token); more than one -> ``AmbiguousBatch`` (never guess: a wrong id would attach another
batch's results).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ledger.matrix.jobs import BatchResult

SKEW = timedelta(minutes=10)


class AmbiguousBatch(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _total(counts: Any) -> int:
    return sum(
        getattr(counts, k, 0) or 0
        for k in ("processing", "succeeded", "errored", "canceled", "expired")
    )


class AnthropicBatchClient:
    def __init__(
        self,
        client: Any,
        sidecar: Path,
        *,
        now: Callable[[], datetime] = _now,
        list_limit: int = 100,
    ):
        self.client = client
        self.sidecar = Path(sidecar)
        self.now = now
        self.list_limit = list_limit

    # -- sidecar ------------------------------------------------------------------------------

    def _record(self, rec: dict[str, Any]) -> None:
        self.sidecar.parent.mkdir(parents=True, exist_ok=True)
        with self.sidecar.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def _lookup(self, token: str) -> dict[str, Any] | None:
        if not self.sidecar.exists():
            return None
        found = None
        for line in self.sidecar.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                if rec["token"] == token:
                    found = rec  # last record for the token wins
        return found

    # -- BatchClient --------------------------------------------------------------------------

    def submit(self, requests: list[dict[str, Any]], token: str) -> str:
        self._record(
            {
                "token": token,
                "n_requests": len(requests),
                "custom_ids": sorted(r["custom_id"] for r in requests),
                "submitted_after": (self.now() - SKEW).isoformat(),
            }
        )
        batch = self.client.messages.batches.create(requests=requests)
        return batch.id

    def find_batch(self, token: str) -> str | None:
        rec = self._lookup(token)
        if rec is None:
            return None
        after = datetime.fromisoformat(rec["submitted_after"])
        wanted = set(rec["custom_ids"])
        candidates: list[str] = []
        for batch in self.client.messages.batches.list(limit=self.list_limit):
            if batch.created_at < after:
                break  # newest first: everything further is older still
            if _total(batch.request_counts) != rec["n_requests"]:
                continue
            if batch.processing_status == "ended":
                got = {r.custom_id for r in self.client.messages.batches.results(batch.id)}
                if got != wanted:
                    continue
            candidates.append(batch.id)
        if len(candidates) > 1:
            raise AmbiguousBatch(
                f"token {token}: {len(candidates)} batches match ({', '.join(candidates)}); "
                "resolve by hand, never guess"
            )
        return candidates[0] if candidates else None

    def poll(self, batch_id: str) -> str:
        return self.client.messages.batches.retrieve(batch_id).processing_status

    def results(self, batch_id: str) -> Iterable[BatchResult]:
        for item in self.client.messages.batches.results(batch_id):
            res = item.result
            if res.type == "succeeded":
                payload = {"message": res.message.model_dump(mode="json")}
            else:
                err = getattr(res, "error", None)
                payload = {"error": err.model_dump(mode="json")} if err is not None else {}
            yield BatchResult(item.custom_id, res.type, payload)
