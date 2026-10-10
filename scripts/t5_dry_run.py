# ruff: noqa: E501
"""T5 harness check (D-043 item 3): ONE question, sent once per output mode as a SYNC call with the
exact body the Batch will carry. Prints, per mode: stop_reason, input / output / thinking tokens,
pydantic validation result and cited chunk IDs (and whether they are among the supplied five).

This is the only T5 script allowed to run with ``generator.output_mode`` empty: it passes each
mode explicitly. It runs BEFORE the GPU retrieval, so its context is not retrieved: the gold chunk
of the first answerable draft question plus the next four chunks of the same unit in file order.
That tests request shape, validity and the parser, not answer quality. 2 API calls.

Needs ANTHROPIC_API_KEY (env only). Tracing is optional (Phoenix + your IP on its SG); if the
endpoint is unreachable the printed results are unaffected.

    uv run python scripts/t5_dry_run.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from ledger.baseline.request import OUTPUT_MODES, build_params
from ledger.baseline.runtime import init_tracing_safely, read_questions, shutdown_tracing_safely
from ledger.baseline.schema import AnswerInvalid, parse_answer
from ledger.config import load_config
from ledger.retrieval.index import read_chunks
from ledger.retrieval.query import load_verified_texts
from ledger.tracing import otel


def dry_context(question: dict, chunks: list[dict], n: int = 5) -> list[tuple[str, str]]:
    gold = next(c for c in chunks if c["chunk_id"] == question["gold_chunk_id"])
    same_unit = [
        c for c in chunks if c["unit_id"] == gold["unit_id"] and c["chunk_id"] != gold["chunk_id"]
    ]
    picked = [gold, *same_unit[: n - 1]]
    return [(c["chunk_id"], c["text"]) for c in picked]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", metavar="PATH", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(override=args.config)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("t5_dry_run: ANTHROPIC_API_KEY is not set (env only)", file=sys.stderr)
        return 2

    import anthropic

    load_verified_texts(cfg.paths.chunks, cfg.paths.chunk_ids_lock)  # refuses on any mismatch
    questions = [q for q in read_questions(cfg.paths.questions_draft) if q.get("set") == "draft"]
    chunks = read_chunks(cfg.paths.chunks)
    q = questions[0]
    ctx = dry_context(q, chunks)
    supplied = {cid for cid, _ in ctx}
    client = anthropic.Anthropic()
    init_tracing_safely(cfg)
    code = 0
    try:
        with otel.run_span("ledger.t5_dry_run", {"rag.record_type": "t5_dry_run"}):
            print(f"question {q['question_id']}: {q['question']}")
            print(f"context: {sorted(supplied)}  (NOT retrieved: gold + same-unit neighbours)")
            for mode in OUTPUT_MODES:
                params = build_params(
                    cfg.generator, question=q["question"], chunks=ctx, output_mode=mode
                )
                print(f"\n== {mode}")
                try:
                    with otel.llm_span(
                        "generate",
                        provider="anthropic",
                        model_name=cfg.generator.model,
                        invocation_parameters={
                            "max_tokens": cfg.generator.max_tokens,
                            "thinking": cfg.generator.thinking,
                            "effort": cfg.generator.effort,
                            "output_mode": mode,
                            "batch": False,
                        },
                    ) as span:
                        msg = client.messages.create(**params)
                        content = [b.model_dump(mode="json") for b in msg.content]
                        u = msg.usage
                        details = getattr(u, "output_tokens_details", None)
                        otel.set_llm_result(
                            span,
                            input_messages=[
                                {"role": "user", "content": params["messages"][0]["content"]}
                            ],
                            output_messages=[
                                {
                                    "role": "assistant",
                                    "content": json.dumps(content, ensure_ascii=False),
                                }
                            ],
                            usage={
                                "input_tokens": u.input_tokens,
                                "output_tokens": u.output_tokens,
                            },
                        )
                except anthropic.APIStatusError as exc:
                    print(f"API ERROR {exc.status_code}: {exc.response.text}")
                    code = 1
                    continue
                print(f"stop_reason: {msg.stop_reason}")
                print(
                    f"tokens: input={u.input_tokens} output={u.output_tokens} "
                    f"thinking={getattr(details, 'thinking_tokens', None)}"
                )
                print(
                    f"cost (sync rates): ${cfg.generator.cost_usd({'input_tokens': u.input_tokens, 'output_tokens': u.output_tokens}, batch=False):.6f}"
                )
                try:
                    ans = parse_answer(content, output_mode=mode)
                    cited = ans.cited_ids()
                    print(f"validation: OK  abstained={ans.abstained}")
                    print(f"cited ids: {cited}  all supplied: {set(cited) <= supplied}")
                except AnswerInvalid as exc:
                    print(f"validation: FAILED: {exc}")
                    print(f"raw content: {json.dumps(content, ensure_ascii=False)[:600]}")
    finally:
        shutdown_tracing_safely()
    return code


if __name__ == "__main__":
    sys.exit(main())
