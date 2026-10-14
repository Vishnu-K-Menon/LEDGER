"""T6 part B on the GPU box (D-044 items 7, 9, 10): score the committed pilot claims and the
committed panel with every verifier that part A passed, under both input modes. Writes
results/t6/scores.jsonl (P(supported) only; FAIL is a third value). Granite Guardian runs first in
this process (transformers, bf16) and is unloaded before the MiniCheck worker starts vLLM.

Refuses unless: the tree is clean; labels, gate report and panel are committed; part A ran at this
HEAD with Granite PASS and no MiniCheck disagreement (scripts/t6_part_a.py). Needs
results/t5/contexts.jsonl (gitignored; copied from the laptop); every labelled row's context hash
must match it.

    uv run python scripts/t6_score.py
"""

from __future__ import annotations

import argparse
import gc
import sys
from pathlib import Path

from ledger.baseline.join import read_contexts
from ledger.baseline.runtime import init_tracing_safely, shutdown_tracing_safely
from ledger.claims.decompose import read_claims
from ledger.config import load_config
from ledger.eval.labels import load_pilot_labels
from ledger.pilot import repo
from ledger.tracing import otel
from ledger.verify import run as R
from ledger.verify.scores import ScoresManifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", metavar="PATH", default=None)
    args = ap.parse_args(argv)
    import torch

    if not torch.cuda.is_available():
        print("t6_score: CUDA is not available; refusing (GPU stage)", file=sys.stderr)
        return 2
    cfg = load_config(override=args.config)
    paths = cfg.pilot.paths
    try:
        part_a = R.check_ready(cfg)
    except R.ScoreRefused as exc:
        print(f"t6_score REFUSED: {exc}", file=sys.stderr)
        return 2
    _, labels = load_pilot_labels(paths.labels)
    _, claims = read_claims(paths.claims)
    ctx_path = cfg.paths.results_dir / "t5" / "contexts.jsonl"
    if not ctx_path.exists():
        print(f"t6_score: {ctx_path} missing; copy it from the laptop", file=sys.stderr)
        return 2
    contexts = {c["question_id"]: c for c in read_contexts(ctx_path)}
    # run 1's non-abstaining answers = the answers the committed claims file decomposed (the
    # panel was validated against run 1 itself on the laptop by scripts/t6_panel_check.py)
    panel = R.panel_rows(cfg, sorted({c.question_id for c in claims}))
    items = R.build_items(labels, {c.claim_id: c for c in claims}, panel, contexts)
    by_id = {it.item_id: it for it in items}
    statuses = dict(part_a["verifiers"])
    revisions = {v: cfg.verifier.pilot_pins[v].revision for v in statuses}
    rows = []
    init_tracing_safely(cfg)
    try:
        with otel.run_span("ledger.t6_score", {"rag.record_type": "t6_score"}):
            from ledger.verify.granite import GraniteScorer

            gg = part_a["granite"]
            sc = GraniteScorer(
                revisions[R.GG_REPO], gg["yes_id"], gg["no_id"], cfg.pilot.granite_max_new_tokens
            )

            def gg_calls(calls):
                return [
                    R.Call(c.status, c.p, c.parsed, c.reason)
                    for c in (sc.score(d, claim) for d, claim in calls)
                ]

            rows += R.score_with(items, R.GG_REPO, revisions[R.GG_REPO], gg_calls)
            sc = None  # unload Granite before vLLM starts
            gc.collect()
            torch.cuda.empty_cache()
            if statuses.get(R.MC_REPO) == "PASS":
                mc_cfg = cfg.model_copy(
                    update={
                        "pilot": cfg.pilot.model_copy(
                            update={"minicheck_venv": part_a["minicheck"]["venv"]}
                        )
                    }
                )

                def mc_calls(calls):
                    status, res, reason = R.run_minicheck_worker(
                        mc_cfg, calls, Path(paths.scores).parent / "part_b_mc"
                    )
                    if status != "ok":
                        raise RuntimeError(f"MiniCheck worker: {status}: {reason}")
                    return R.minicheck_calls(res)

                rows += R.score_with(items, R.MC_REPO, revisions[R.MC_REPO], mc_calls)
            R.emit_spans(rows, by_id, cfg.verifier.threshold)
    finally:
        shutdown_tracing_safely()
    manifest = ScoresManifest(
        manifest=True,
        labels_sha256=repo.sha256_file(paths.labels),
        panel_sha256=repo.sha256_file(paths.panel),
        part_a_sha256=repo.sha256_file(paths.part_a),
        git_commit=repo.head_commit(),
        verifiers=statuses,
        revisions=revisions,
    )
    R.write_scores(Path(paths.scores), manifest, rows)
    fails = sum(r.status == "FAIL" for r in rows)
    sha = repo.sha256_file(paths.scores)
    print(f"wrote {paths.scores}: {len(rows)} rows, FAIL {fails}; sha256 {sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
