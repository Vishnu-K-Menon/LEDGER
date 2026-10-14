"""T6 part A on the GPU box (D-044 items 8-9): Granite Guardian reference checks and verdict-token
ids, then the MiniCheck attempt on its official path (own venv, <= pilot.part_a_budget_min minutes
including one retry with an older vLLM). Writes results/t6/part_a.json and part_a.md BEFORE part B
can start (scripts/t6_score.py refuses without them).

Before running: E3 idle stop confirmed; the per-start /32 6006 rule; a5_probe trace seen.

    uv run python scripts/t6_part_a.py
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from ledger.baseline import probe
from ledger.baseline.runtime import init_tracing_safely, read_questions, shutdown_tracing_safely
from ledger.config import load_config
from ledger.pilot import part_a, repo
from ledger.retrieval.index import read_chunks
from ledger.tracing import otel
from ledger.verify.run import MC_REPO


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", metavar="PATH", default=None)
    args = ap.parse_args(argv)
    import torch

    if not torch.cuda.is_available():
        print("t6_part_a: CUDA is not available; refusing (GPU stage)", file=sys.stderr)
        return 2
    cfg = load_config(override=args.config)
    dirty = repo.dirty(untracked_under=("ledger", "scripts", "configs"))
    if dirty:
        print(f"t6_part_a REFUSED: the tree is not clean: {dirty[:10]}", file=sys.stderr)
        return 2
    chunks = read_chunks(cfg.paths.chunks)
    units = defaultdict(list)
    for c in chunks:
        units[c["unit_id"]].append(c)
    claims = probe.build_probe_claims(
        read_questions(Path(cfg.paths.questions_draft)), {c["chunk_id"]: c for c in chunks}, units
    )
    init_tracing_safely(cfg)
    try:
        with otel.run_span("ledger.t6_part_a", {"rag.record_type": "t6_part_a"}):
            gg = part_a.granite_part_a(cfg, claims)
            gh = probe.fetch_source(
                "MiniCheck README example",
                probe.MINICHECK_REPO,
                probe.MINICHECK_README,
                cfg.pilot.minicheck_commit,
                probe.github_url(
                    probe.MINICHECK_REPO, cfg.pilot.minicheck_commit, probe.MINICHECK_README
                ),
                probe.default_fetch,
            )
            ex = probe.extract_readme_example(gh.text)
            requests = [
                {"id": "readme_1", "doc": ex["doc"], "claim": ex["claim_1"]},
                {"id": "readme_2", "doc": ex["doc"], "claim": ex["claim_2"]},
            ] + [
                {"id": f"{c['question_id']}:{c['label']}:{c['context_chunks']}", **c}
                for c in claims
            ]
            requests = [{"id": r["id"], "doc": r["doc"], "claim": r["claim"]} for r in requests]
            mc = part_a.minicheck_part_a(
                cfg, requests, ex["expected"], Path(cfg.pilot.paths.part_a).parent / "part_a_mc"
            )
            mc["revision"] = cfg.verifier.pilot_pins[MC_REPO].revision
    finally:
        shutdown_tracing_safely()
    rec = part_a.record(repo.head_commit(), gg, mc)
    part_a.write(cfg, rec)
    print(f"wrote {cfg.pilot.paths.part_a} and {cfg.pilot.paths.part_a_report}: {rec['verifiers']}")
    if rec["minicheck_disagreement"]:
        print("MiniCheck disagreement recorded: part B will not start until the owner rules.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
