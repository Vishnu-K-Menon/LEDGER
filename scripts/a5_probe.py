"""A5 probe — one traced Sonnet 5 call plus the two D-017 evaluation records, for the
Phoenix rendering checks in docs/plan.md:

  (a) spans render with token counts        -> the `generate` LLM span under the `query` AGENT span
  (b) inline `evaluations.*` verdict         -> the `verify` TOOL span's Evaluations panel
  (c) post-hoc EVALUATOR carrier + Span Link -> shown against the *linked* verify span

Requires ANTHROPIC_API_KEY (or an `ant auth login` profile) and OTEL_EXPORTER_OTLP_ENDPOINT.
Default is a synchronous Messages call (A5 only needs token counts on a span; the CLAUDE.md
synchronous ban is scoped to the matrix runner). `--batch` submits the same request through the
Batch API and polls, so the batch usage-field path is verified once before T5 depends on it.

    uv run python scripts/a5_probe.py            # sync
    uv run python scripts/a5_probe.py --batch    # Batch API, polls until ended
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from ledger.config import load_config
from ledger.tracing import otel

REQUIRED_ENV = ("OTEL_EXPORTER_OTLP_ENDPOINT",)
PROMPT = "Reply with the single word: ready"
POLL_SECONDS = 15


def _usage(msg) -> dict[str, int | None]:
    u = msg.usage
    return {
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", None),
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", None),
    }


def _call_sync(client, model: str, max_tokens: int, temperature: float):
    return client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": PROMPT}],
    )


def _call_batch(client, model: str, max_tokens: int, temperature: float):
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    batch = client.messages.batches.create(
        requests=[
            Request(
                custom_id="a5-probe",
                params=MessageCreateParamsNonStreaming(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[{"role": "user", "content": PROMPT}],
                ),
            )
        ]
    )
    print(f"batch {batch.id} submitted; polling every {POLL_SECONDS}s")
    while client.messages.batches.retrieve(batch.id).processing_status != "ended":
        time.sleep(POLL_SECONDS)
    for result in client.messages.batches.results(batch.id):
        if result.custom_id != "a5-probe":  # results arrive in any order: key by custom_id
            continue
        if result.result.type != "succeeded":
            raise RuntimeError(f"batch request {result.result.type}: {result.result}")
        return result.result.message
    raise RuntimeError("batch ended without the a5-probe result")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--batch", action="store_true", help="use the Batch API instead of a sync call")
    ap.add_argument("--config", metavar="PATH", default=None)
    args = ap.parse_args(argv)

    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        print(f"A5 probe cannot run: {', '.join(missing)} not set", file=sys.stderr)
        return 2

    import anthropic

    cfg = load_config(override=args.config)
    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY or an `ant auth login` profile
    otel.init_tracing(cfg)
    gen = cfg.generator
    call = _call_batch if args.batch else _call_sync

    with otel.query_span(PROMPT, question_id="a5-probe", arm="none", seed=0) as root:
        with otel.llm_span(
            "generate",
            provider="anthropic",
            model_name=gen.model,
            invocation_parameters={
                "temperature": gen.temperature,
                "max_tokens": gen.max_tokens,
                "batch": args.batch,
            },
        ) as llm:
            msg = call(client, gen.model, gen.max_tokens, gen.temperature)
            text = next((b.text for b in msg.content if b.type == "text"), "")
            usage = _usage(msg)
            otel.set_llm_result(
                llm,
                input_messages=[{"role": "user", "content": PROMPT}],
                output_messages=[{"role": "assistant", "content": text}],
                usage=usage,
            )
        with otel.verify_span("a5-claim-1") as verify:
            otel.record_verdict(
                verify,
                otel.VerdictRecord(
                    claim_id="a5-claim-1",
                    label="SUPPORTED",
                    score=1.0,
                    evidence_ids=["a5::probe::chunk-0"],
                    input_mode=cfg.verifier.input_mode,
                    threshold=cfg.verifier.threshold,
                    cited_support=True,
                    verifier_model="a5-probe",
                    verifier_revision="none",
                ),
            )
            target = otel.ids_of(verify)
        price = gen.pricing_usd_per_mtok
        pin, pout = (
            (price.batch_input, price.batch_output) if args.batch else (price.input, price.output)
        )
        cost = (usage["input_tokens"] * pin + usage["output_tokens"] * pout) / 1_000_000
        otel.set_query_result(
            root, iterations=0, stop_reason="a5_probe", cost_usd=cost, answer=text
        )

    carrier = otel.emit_posthoc_evaluation(
        target,
        {"name": "human_label", "label": "SUPPORTED", "score": 1.0, "explanation": "A5 probe"},
        annotator_kind="HUMAN",
    )
    otel.shutdown_tracing()

    print(f"model={gen.model} batch={args.batch} reply={text!r}")
    print(f"usage={usage} cost_usd={cost:.6f}")
    print(f"(a) query trace_id={otel.ids_of(root)[0]}")
    print(f"(b) verify span_id={target[1]}  (inline evaluations.0.evaluation.*)")
    print(f"(c) carrier span_id={otel.ids_of(carrier)[1]} -> linked to verify {target[1]}")
    print("Open Phoenix, project 'ledger', and record pass/fail for (a)(b)(c) in docs/plan.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
