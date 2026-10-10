"""T5 generation run (D-043 item 3): the 30 items x 3 runs go out as ONE Batch of 90 through the
resumable job ledger. Runs are cells ``<baseline.cell>_r1.._rN`` at seed 1 (owner ruling in
D-043 item 3), so D-009's one-seed-at-a-time guard is not engaged and ``run_seed`` is used
unchanged. Results land in ``results/<cell>/1.jsonl`` keyed by ``(cell, seed, question_id)``."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ledger.baseline.request import build_params, require_output_mode
from ledger.baseline.schema import Answer, AnswerInvalid, parse_answer
from ledger.config import Config
from ledger.matrix.jobs import BatchClient, JobKey, JobLedger, RunSummary, run_seed

SEED = 1  # the T5 repeat runs are cells at seed 1; they are not matrix seeds


def run_cells(cfg: Config) -> list[str]:
    return [f"{cfg.baseline.cell}_r{n}" for n in range(1, cfg.baseline.runs + 1)]


def run_of(cell: str, cfg: Config) -> int:
    prefix = f"{cfg.baseline.cell}_r"
    if not cell.startswith(prefix):
        raise ValueError(f"{cell!r} is not a T5 run cell")
    return int(cell[len(prefix) :])


def make_build_request(
    cfg: Config, contexts: Mapping[str, Mapping[str, Any]], output_mode: str
) -> Callable[[JobKey], dict[str, Any]]:
    def build(key: JobKey) -> dict[str, Any]:
        ctx = contexts[key.question_id]
        return build_params(
            cfg.generator,
            question=ctx["question"],
            chunks=[(c["chunk_id"], c["text"]) for c in ctx["chunks"]],
            output_mode=output_mode,
        )

    return build


def submit_or_collect(
    cfg: Config,
    contexts: Sequence[Mapping[str, Any]],
    client: BatchClient,
    *,
    ledger_path: Path,
) -> RunSummary:
    """Refuses while ``generator.output_mode`` is empty (D-043 item 5)."""
    mode = require_output_mode(cfg.generator)
    by_id = {c["question_id"]: c for c in contexts}
    return run_seed(
        JobLedger(ledger_path),
        client,
        cells=run_cells(cfg),
        question_ids=sorted(by_id),
        seed=SEED,
        build_request=make_build_request(cfg, by_id, mode),
        results_dir=cfg.paths.results_dir,
    )


# ---- reading results --------------------------------------------------------------------------


@dataclass
class RunRecord:
    run: int
    question_id: str
    result_type: str  # succeeded | errored | expired | canceled | missing
    stop_reason: str | None
    content: list[dict[str, Any]]
    usage: dict[str, Any]
    answer: Answer | None
    error: str | None


def _usage(message: Mapping[str, Any]) -> dict[str, Any]:
    u = dict(message.get("usage") or {})
    details = u.get("output_tokens_details") or {}
    u["thinking_tokens"] = details.get("thinking_tokens") if isinstance(details, dict) else None
    return u


def load_runs(cfg: Config, question_ids: Sequence[str], output_mode: str) -> list[RunRecord]:
    """One ``RunRecord`` per submitted (run, question), in (run, question) order. A request with
    no result record is returned as ``missing``: A4 counts over all submitted requests."""
    out: list[RunRecord] = []
    for cell in run_cells(cfg):
        path = cfg.paths.results_dir / cell / f"{SEED}.jsonl"
        have: dict[str, dict[str, Any]] = {}
        if path.exists():
            for ln in path.read_text(encoding="utf-8").splitlines():
                if ln.strip():
                    rec = json.loads(ln)
                    have[rec["question_id"]] = rec
        run = run_of(cell, cfg)
        for qid in question_ids:
            rec = have.get(qid)
            if rec is None:
                out.append(RunRecord(run, qid, "missing", None, [], {}, None, "no result"))
                continue
            message = (rec.get("payload") or {}).get("message") or {}
            content = list(message.get("content") or [])
            answer, error = None, None
            if rec["result_type"] == "succeeded":
                try:
                    answer = parse_answer(content, output_mode=output_mode)
                except AnswerInvalid as exc:
                    error = str(exc)
            else:
                error = rec["result_type"]
            out.append(
                RunRecord(
                    run,
                    qid,
                    rec["result_type"],
                    message.get("stop_reason"),
                    content,
                    _usage(message),
                    answer,
                    error,
                )
            )
    return out


# ---- tracing the collected results (D29: every LLM call emits a span) ---------------------------


def trace_runs(
    cfg: Config,
    records: Sequence[RunRecord],
    contexts: Mapping[str, Mapping[str, Any]],
    output_mode: str,
    traced_path: Path,
) -> int:
    """Emit one query + generate span per collected result, once (a marker file remembers which).
    Batch usage arrives at collection, so spans are emitted then; they record the D-041 pins and
    the output mode in their invocation parameters, so a trace shows the pins held."""
    from ledger.tracing import otel

    done: set[str] = set()
    if traced_path.exists():
        done = {ln.strip() for ln in traced_path.read_text(encoding="utf-8").splitlines()}
    emitted = 0
    for r in records:
        marker = f"{r.run}|{r.question_id}"
        if r.result_type != "succeeded" or marker in done:
            continue
        text = json.dumps(r.content, sort_keys=True, ensure_ascii=False)
        with otel.query_span(
            contexts[r.question_id]["question"],
            question_id=r.question_id,
            arm="single_shot",
            seed=r.run,
        ) as root:
            with otel.llm_span(
                "generate",
                provider="anthropic",
                model_name=cfg.generator.model,
                invocation_parameters={
                    "max_tokens": cfg.generator.max_tokens,
                    "thinking": cfg.generator.thinking,
                    "effort": cfg.generator.effort,
                    "output_mode": output_mode,
                    "batch": True,
                },
            ) as llm:
                otel.set_llm_result(
                    llm,
                    input_messages=[
                        {"role": "user", "content": contexts[r.question_id]["question"]}
                    ],
                    output_messages=[{"role": "assistant", "content": text}],
                    usage=r.usage,
                )
            otel.set_query_result(
                root,
                iterations=0,
                stop_reason=r.stop_reason or "unknown",
                cost_usd=cfg.generator.cost_usd(r.usage, batch=True),
                answer=text,
            )
        traced_path.parent.mkdir(parents=True, exist_ok=True)
        with traced_path.open("a", encoding="utf-8") as fh:
            fh.write(marker + "\n")
        emitted += 1
    return emitted
