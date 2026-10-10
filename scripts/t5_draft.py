"""T5 drafting (D-043 items 1-2): claude-sonnet-5-5 (D-041 pins) drafts one question per candidate
chunk of data/questions_draft_draw.json, plus one request for 10 control candidates. SYNC calls,
~51 of them (the matrix-runner ban on synchronous generation does not apply to this script).

Writes data/questions_draft_candidates.jsonl (gitignored), one line per candidate, appended as
each reply arrives and resumable (candidates already present are skipped). The owner then edits
each line: ``accept`` true/false, ``checked_by``, and may correct ``question``/``gold_answer`` by
hand. ``scripts/t5_finalize_questions.py`` turns the accepted lines into data/questions_draft.jsonl.

Requires ANTHROPIC_API_KEY (env only). OTEL_EXPORTER_OTLP_ENDPOINT is optional: if Phoenix is
down, the run continues and every result is still written.

    uv run python scripts/t5_draft.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from ledger.baseline import drafting
from ledger.baseline.runtime import init_tracing_safely, shutdown_tracing_safely
from ledger.config import load_config
from ledger.ingest.manifest import active_rows, read_manifest
from ledger.retrieval.index import lf_sha256, read_chunks
from ledger.tracing import otel

DRAW = Path("data/questions_draft_draw.json")
OUT = Path("data/questions_draft_candidates.jsonl")


def _done_ids() -> set[str]:
    if not OUT.exists():
        return set()
    return {
        json.loads(ln)["candidate_id"]
        for ln in OUT.read_text(encoding="utf-8").splitlines()
        if ln.strip() and "error" not in json.loads(ln)
    }


def _append(rec: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _slots(draw: dict) -> list[tuple[dict, str, str]]:
    """Every candidate of the draw in draw order: primary and reserve of each stratum, then the
    supplement. ``tier`` marks primary vs reserve; the owner's replacements follow draw order."""
    slots: list[tuple[dict, str, str]] = []
    for stratum, key, prim, prefix in (
        ("table", "table_order", draw["table_primary"], "t"),
        ("prose", "prose_order", draw["prose_primary"], "p"),
    ):
        for i, cid in enumerate(draw[key]):
            meta = {
                "stratum": stratum,
                "order_index": i,
                "tier": "primary" if i < prim else "reserve",
            }
            slots.append((meta, f"{prefix}{i + 1:02d}", cid))
    per = draw["supplement_primary_per_source"]
    for src, ids in sorted(draw["supplement_order"].items()):
        for i, cid in enumerate(ids):
            meta = {
                "stratum": "supplement",
                "supp_source": src,
                "order_index": i,
                "tier": "primary" if i < per else "reserve",
            }
            slots.append((meta, f"s-{src}-{i + 1:02d}", cid))
    return slots


def _call(client, cfg, params, span_name: str):
    gen = cfg.generator
    with otel.llm_span(
        span_name,
        provider="anthropic",
        model_name=gen.model,
        invocation_parameters={
            "max_tokens": gen.max_tokens,
            "thinking": gen.thinking,
            "effort": gen.effort,
            "output_mode": "none",
            "batch": False,
        },
    ) as span:
        msg = client.messages.create(**params)
        text = "".join(b.text for b in msg.content if b.type == "text")
        usage = {
            "input_tokens": msg.usage.input_tokens,
            "output_tokens": msg.usage.output_tokens,
        }
        otel.set_llm_result(
            span,
            input_messages=[{"role": "user", "content": params["messages"][0]["content"]}],
            output_messages=[{"role": "assistant", "content": text}],
            usage=usage,
        )
    return text, usage, msg.stop_reason


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", metavar="PATH", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(override=args.config)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("t5_draft: ANTHROPIC_API_KEY is not set (env only)", file=sys.stderr)
        return 2
    draw = json.loads(DRAW.read_text(encoding="utf-8"))
    if draw["chunks_sha256"] != lf_sha256(cfg.paths.chunks):
        print(
            "t5_draft: draw was made against a different chunks.jsonl; rerun t5_draw",
            file=sys.stderr,
        )
        return 2

    import anthropic

    client = anthropic.Anthropic()
    chunks = {c["chunk_id"]: c for c in read_chunks(cfg.paths.chunks)}
    _, rows = read_manifest(cfg.paths.manifest)
    units = [r.model_dump() for r in active_rows(rows)]
    done = _done_ids()
    spent = 0.0
    errors = 0
    init_tracing_safely(cfg)
    try:
        with otel.run_span("ledger.t5_draft", {"rag.record_type": "t5_draft_run"}):
            slots = _slots(draw)
            for meta, cand_id, cid in slots:
                if cand_id in done:
                    continue
                ch = chunks[cid]
                try:
                    text, usage, stop = _call(client, cfg, drafting.draft_params(cfg, ch), "draft")
                    d = drafting.parse_draft(text)
                    rec = {
                        "candidate_id": cand_id,
                        "kind": "prose" if meta["stratum"] == "prose" else "table",
                        **meta,
                        "chunk_id": cid,
                        "source": ch["source"],
                        "unit_id": ch["unit_id"],
                        **d,
                        "auto": drafting.auto_checks(d["question"], d["gold_answer"], ch["text"]),
                        "drafted_by": cfg.generator.model,
                        "stop_reason": stop,
                        "usage": usage,
                        "accept": None,
                        "checked_by": "",
                        "notes": "",
                    }
                    spent += cfg.generator.cost_usd(usage, batch=False)
                except Exception as exc:  # noqa: BLE001 - one bad reply must not lose the rest
                    errors += 1
                    rec = {
                        "candidate_id": cand_id,
                        **meta,
                        "chunk_id": cid,
                        "error": repr(exc),
                        "accept": None,
                        "notes": "",
                    }
                _append(rec)
                print(f"{cand_id} {cid}: {'ERROR' if 'error' in rec else 'ok'}")

            if "c-all" not in done and not any(i.startswith("c") for i in done):
                try:
                    text, usage, stop = _call(
                        client,
                        cfg,
                        drafting.controls_params(cfg, units, cfg.baseline.n_control_candidates),
                        "draft_controls",
                    )
                    spent += cfg.generator.cost_usd(usage, batch=False)
                    for i, c in enumerate(drafting.parse_controls(text), 1):
                        _append(
                            {
                                "candidate_id": f"c{i:02d}",
                                "kind": "control",
                                "stratum": "control",
                                "order_index": i - 1,
                                **c,
                                "drafted_by": cfg.generator.model,
                                "stop_reason": stop,
                                "usage": usage,
                                "accept": None,
                                "checked_by": "",
                                "notes": "",
                            }
                        )
                except Exception as exc:  # noqa: BLE001
                    errors += 1
                    _append(
                        {
                            "candidate_id": "c-all",
                            "kind": "control",
                            "stratum": "control",
                            "order_index": 0,
                            "error": repr(exc),
                            "accept": None,
                            "notes": "",
                        }
                    )
                    print(f"controls: ERROR {exc!r}")
    finally:
        shutdown_tracing_safely()
    print(f"cost (sync rates, measured usage): ${spent:.4f}; errors: {errors}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
