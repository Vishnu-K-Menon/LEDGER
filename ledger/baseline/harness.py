"""T5 harness check (D-043 status 2026-10-10, item 5): sync calls in the configured output mode,
on retrieved contexts, for s001 and each control candidate not accepted. Pass = request accepted,
``end_turn``, the reply parses. The Batch carries the same request body (``build_params``)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

import anthropic

from ledger.baseline.request import build_params
from ledger.baseline.schema import AnswerInvalid, parse_answer
from ledger.config import GeneratorConfig
from ledger.tracing import otel

NORMAL_STOP = "end_turn"


def check_question(
    client: Any, gen: GeneratorConfig, ctx: Mapping[str, Any], mode: str
) -> dict[str, Any]:
    """One sync call. Never raises on an API error: the row records ``accepted: False``."""
    chunks = [(c["chunk_id"], c["text"]) for c in ctx["chunks"]]
    supplied = {cid for cid, _ in chunks}
    row: dict[str, Any] = {
        "question_id": ctx["question_id"],
        "set": ctx.get("set"),
        "accepted": False,
        "stop_reason": None,
        "parse": None,
        "abstained": None,
        "cited_ok": None,
        "input_tokens": None,
        "output_tokens": None,
        "thinking_tokens": None,
        "detail": "",
    }
    params = build_params(gen, question=ctx["question"], chunks=chunks, output_mode=mode)
    try:
        with otel.llm_span(
            "generate",
            provider="anthropic",
            model_name=gen.model,
            invocation_parameters={
                "max_tokens": gen.max_tokens,
                "thinking": gen.thinking,
                "effort": gen.effort,
                "output_mode": mode,
                "batch": False,
            },
        ) as span:
            msg = client.messages.create(**params)
            content = [b.model_dump(mode="json") for b in msg.content]
            u = msg.usage
            otel.set_llm_result(
                span,
                input_messages=[{"role": "user", "content": params["messages"][0]["content"]}],
                output_messages=[
                    {"role": "assistant", "content": json.dumps(content, ensure_ascii=False)}
                ],
                usage={"input_tokens": u.input_tokens, "output_tokens": u.output_tokens},
            )
    except anthropic.APIStatusError as exc:
        row["detail"] = f"API {exc.status_code}: {exc.response.text[:300]}"
        return row
    row["accepted"] = True
    row["stop_reason"] = msg.stop_reason
    details = getattr(u, "output_tokens_details", None)
    row["input_tokens"] = u.input_tokens
    row["output_tokens"] = u.output_tokens
    row["thinking_tokens"] = getattr(details, "thinking_tokens", None)
    try:
        ans = parse_answer(content, output_mode=mode)
    except AnswerInvalid as exc:
        row["parse"] = "failed"
        row["detail"] = str(exc)[:300]
        return row
    row["parse"] = "ok"
    row["abstained"] = ans.abstained
    row["cited_ok"] = set(ans.cited_ids()) <= supplied
    return row


def row_passes(row: Mapping[str, Any]) -> bool:
    return bool(row["accepted"]) and row["stop_reason"] == NORMAL_STOP and row["parse"] == "ok"


def overall_pass(rows: Sequence[Mapping[str, Any]]) -> bool:
    return bool(rows) and all(row_passes(r) for r in rows)


def render(meta: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], mode: str) -> str:
    verdict = "PASS" if overall_pass(rows) else "FAIL"
    out = ["# T5 harness check", ""]
    out += [f"- {k}: `{v}`" for k, v in meta.items()]
    out += [
        "",
        f"**{verdict}**: {sum(row_passes(r) for r in rows)} of {len(rows)} calls accepted, ended "
        f"`{NORMAL_STOP}` and parsed (output mode `{mode}`; D-043 status 2026-10-10, item 5).",
        "",
        "| question | set | accepted | stop_reason | parse | abstained | cited ids ⊆ supplied "
        "| input | output | thinking | pass |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        out.append(
            f"| {r['question_id']} | {r['set']} | {r['accepted']} | {r['stop_reason']} | "
            f"{r['parse']} | {r['abstained']} | {r['cited_ok']} | {r['input_tokens']} | "
            f"{r['output_tokens']} | {r['thinking_tokens']} | {row_passes(r)} |"
        )
    bad = [r for r in rows if r["detail"]]
    if bad:
        out += ["", "## Details", ""]
        out += [f"- {r['question_id']}: {r['detail']}" for r in bad]
    out += ["", "Cited-ID and abstention columns are informational, not part of the pass rule."]
    return "\n".join(out) + "\n"
