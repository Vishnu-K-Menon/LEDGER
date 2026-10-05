"""Resumable job ledger for Batch submissions (D-025), keyed ``(cell, seed, question_id)`` (D28).

State machine per key: ``pending -> intended -> submitted -> completed | expired | errored``.
  completed -> skip; submitted (batch id recorded) -> poll, never resubmit;
  expired / errored -> resubmit only those keys.
Sequence per invocation: collect what finished, then submit what is left, persist, exit.

Crash safety: before ``client.submit`` an *intent* (deterministic token) is persisted; a re-run
that finds an intent without a batch id asks ``client.find_batch(token)`` instead of submitting
again, so a crash between submit and persist cannot spend the budget twice.

Results land in ``<results_dir>/<cell>/<seed>.jsonl`` as one record per question - never
aggregates (D-030). No sampling parameters are ever added here (D-019).
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple, Protocol

PENDING, INTENDED, SUBMITTED = "pending", "intended", "submitted"
COMPLETED, EXPIRED, ERRORED = "completed", "expired", "errored"
RESUBMIT = {EXPIRED, ERRORED}
IN_FLIGHT = {INTENDED, SUBMITTED}
UNFINISHED = {PENDING, INTENDED, SUBMITTED, EXPIRED, ERRORED}


class JobKey(NamedTuple):
    cell: str
    seed: int
    question_id: str


def custom_id(key: JobKey) -> str:
    """Batch ``custom_id`` must match ``[A-Za-z0-9_-]{1,64}``; a hash of the key does, and the
    ledger maps it back, so results are never matched by position."""
    return hashlib.sha256("|".join(map(str, key)).encode()).hexdigest()[:40]


@dataclass(frozen=True)
class BatchResult:
    custom_id: str
    type: str  # succeeded | errored | canceled | expired
    payload: dict[str, Any]


class BatchClient(Protocol):
    """Injected interface; tests use a fake. No real implementation exists tonight."""

    def submit(self, requests: list[dict[str, Any]], token: str) -> str: ...

    def find_batch(self, token: str) -> str | None: ...

    def poll(self, batch_id: str) -> str:  # in_progress | canceling | ended
        ...

    def results(self, batch_id: str) -> Iterable[BatchResult]: ...


class SeedConflict(RuntimeError):
    pass


class JobLedger:
    """Append-only JSONL, last record per key wins; each append is flushed and fsynced."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.jobs: dict[JobKey, dict[str, Any]] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self.jobs[JobKey(rec["cell"], rec["seed"], rec["question_id"])] = rec

    def update(self, key: JobKey, **fields: Any) -> None:
        rec = {**self.jobs.get(key, {}), **fields}
        rec.update(cell=key.cell, seed=key.seed, question_id=key.question_id)
        rec.setdefault("attempt", 0)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self.jobs[key] = rec

    def state(self, key: JobKey) -> str | None:
        rec = self.jobs.get(key)
        return rec["state"] if rec else None

    def keys_in(self, seed: int, states: set[str]) -> list[JobKey]:
        return sorted(k for k, r in self.jobs.items() if k.seed == seed and r["state"] in states)


def _read_result_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {
        json.loads(line)["question_id"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def _write_result(results_dir: Path, key: JobKey, batch_id: str, res: BatchResult) -> None:
    path = results_dir / key.cell / f"{key.seed}.jsonl"
    if key.question_id in _read_result_keys(path):  # idempotent by key
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    message = res.payload.get("message") or {}
    rec = {
        "cell": key.cell,
        "seed": key.seed,
        "question_id": key.question_id,
        "custom_id": res.custom_id,
        "batch_id": batch_id,
        "result_type": res.type,
        "payload": res.payload,
        "usage": message.get("usage") or res.payload.get("usage"),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


@dataclass
class RunSummary:
    skipped_completed: int = 0
    polled_batches: int = 0
    collected: int = 0
    resubmitted: int = 0
    submitted_new: int = 0
    still_in_flight: int = 0


def _submit(
    ledger: JobLedger,
    client: BatchClient,
    ks: list[JobKey],
    token: str,
    build_request: Callable[[JobKey], dict[str, Any]],
) -> None:
    for k in ks:  # persist the intent BEFORE the call
        ledger.update(k, state=INTENDED, token=token)
    requests = [{"custom_id": custom_id(k), "params": build_request(k)} for k in ks]
    batch_id = client.submit(requests, token)
    for k in ks:  # persist the batch id before exiting
        ledger.update(k, state=SUBMITTED, batch_id=batch_id)


def run_seed(
    ledger: JobLedger,
    client: BatchClient,
    *,
    cells: list[str],
    question_ids: list[str],
    seed: int,
    build_request: Callable[[JobKey], dict[str, Any]],
    results_dir: Path,
    confirm_seed_1_inspected: bool = False,
    first_seed: int = 1,
) -> RunSummary:
    """One invocation for one seed (D-009): collect, then submit what remains, then return."""
    if seed != first_seed and not confirm_seed_1_inspected:
        raise SeedConflict(f"seed {seed} requires confirm_seed_1_inspected (D-009)")
    for other in sorted({k.seed for k in ledger.jobs} - {seed}):
        if ledger.keys_in(other, UNFINISHED):
            raise SeedConflict(f"seed {other} has unfinished jobs; one seed at a time (D-009)")

    summary = RunSummary()
    keys = [JobKey(c, seed, q) for c in cells for q in question_ids]
    for k in keys:
        if ledger.state(k) is None:
            ledger.update(k, state=PENDING, custom_id=custom_id(k))
    summary.skipped_completed = sum(ledger.state(k) == COMPLETED for k in keys)

    # 1. an intent without a batch id: recover it, never resubmit blindly (crash safety)
    by_token: dict[str, list[JobKey]] = {}
    for k in ledger.keys_in(seed, {INTENDED}):
        by_token.setdefault(ledger.jobs[k]["token"], []).append(k)
    for token, ks in by_token.items():
        found = client.find_batch(token)
        if found is not None:
            for k in ks:
                ledger.update(k, state=SUBMITTED, batch_id=found)
        else:  # the submit never reached the service: safe to send again under the same token
            _submit(ledger, client, ks, token, build_request)

    # 2. poll recorded batches; collect when ended
    submitted = ledger.keys_in(seed, {SUBMITTED})
    for batch_id in sorted({ledger.jobs[k]["batch_id"] for k in submitted}):
        summary.polled_batches += 1
        if client.poll(batch_id) != "ended":
            continue
        by_cid = {
            ledger.jobs[k]["custom_id"]: k
            for k in submitted
            if ledger.jobs[k]["batch_id"] == batch_id
        }
        for res in client.results(batch_id):
            k = by_cid.pop(res.custom_id, None)
            if k is None:
                continue
            if res.type == "succeeded":
                _write_result(results_dir, k, batch_id, res)
                ledger.update(k, state=COMPLETED)
                summary.collected += 1
            else:
                state = EXPIRED if res.type == "expired" else ERRORED
                ledger.update(k, state=state, last_result_type=res.type)
        for k in by_cid.values():  # batch ended but the key is absent from its results
            ledger.update(k, state=ERRORED, last_result_type="missing")

    # 3. submit what is left: new keys and expired / errored ones, only those
    todo = [k for k in keys if ledger.state(k) in {PENDING} | RESUBMIT]
    summary.resubmitted = sum(ledger.state(k) in RESUBMIT for k in todo)
    summary.submitted_new = len(todo) - summary.resubmitted
    if todo:
        for k in todo:
            ledger.update(k, attempt=ledger.jobs[k]["attempt"] + 1)
        ident = "|".join(f"{custom_id(k)}:{ledger.jobs[k]['attempt']}" for k in todo)
        _submit(
            ledger, client, todo, hashlib.sha256(ident.encode()).hexdigest()[:32], build_request
        )
    summary.still_in_flight = len(ledger.keys_in(seed, IN_FLIGHT))
    return summary
