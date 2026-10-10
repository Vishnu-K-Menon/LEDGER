# ruff: noqa: E501
"""T5 reports (D-043, D-033 status 2026-10-09), written to reports/t5_*.md, each with the commit,
the input hashes and the composition by source and unit in its header. No API call, no GPU.

  reports/t5_a6.md           needs results/t5/retrieval_{primary,card}.jsonl (extracted by t5_join)
                             lists all control candidates until data/controls_accepted.json exists
  reports/t5_a4.md           the 90 core requests (25 drafts + 5 accepted controls, 3 runs);
  reports/t5_variance.md     these three need the collected Batch results and
  reports/t5_claim_yield.md  generator.output_mode set
  reports/t5_a7.md           measured tokens over every submitted request
  reports/t5_supplement.md   the supplement items, separately from every count above

    uv run python scripts/t5_report.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from ledger.baseline import reports as rp
from ledger.baseline.join import read_contexts
from ledger.baseline.run import load_runs
from ledger.baseline.runtime import read_questions
from ledger.config import load_config
from ledger.retrieval.index import git_commit, lf_sha256, read_chunks
from ledger.retrieval.query import read_arm_file

REPO = Path(__file__).resolve().parent.parent
QUESTIONS = Path("data/questions_draft.jsonl")
CONTROLS = Path("data/controls_accepted.json")
MATRIX = Path("experiments/matrix.yaml")


def _write(name: str, text: str) -> None:
    path = Path("reports") / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {path}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", metavar="PATH", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(override=args.config)
    res = cfg.paths.results_dir
    questions = read_questions(QUESTIONS)
    chunks = read_chunks(cfg.paths.chunks)
    chunk_meta = {c["chunk_id"]: c for c in chunks}
    accepted = (
        json.loads(CONTROLS.read_text(encoding="utf-8"))["question_ids"]
        if CONTROLS.exists()
        else None
    )
    composition = rp.composition_block(
        questions, chunk_meta, sorted({c["source"] for c in chunks}), accepted
    )
    base_meta = {
        "git commit": git_commit(REPO),
        "questions sha256": lf_sha256(QUESTIONS),
        "chunks.jsonl sha256 (LF)": lf_sha256(cfg.paths.chunks),
    }
    if CONTROLS.exists():
        base_meta["controls_accepted.json sha256"] = lf_sha256(CONTROLS)

    arm_paths = {n: res / "t5" / f"retrieval_{n}.jsonl" for n in ("primary", "card")}
    if all(p.exists() for p in arm_paths.values()):
        arms = {n: read_arm_file(p) for n, p in arm_paths.items()}
        meta = {
            **base_meta,
            **{f"retrieval_{n} sha256": lf_sha256(p) for n, p in arm_paths.items()},
        }
        text = rp.a6_report(meta, arms, questions, chunk_meta, cfg.retrieval.k_dense, accepted)
        _write("t5_a6.md", rp.finish(text, composition))
    else:
        print("A6 skipped: retrieval files missing (run t5_retrieve on the GPU, then t5_join)")

    ctx_path = res / "t5" / "contexts.jsonl"
    if not cfg.generator.output_mode:
        print(
            "A4 / variance / A7 / claim yield skipped: generator.output_mode is empty (D-043 item 5)"
        )
        return 0
    if not ctx_path.exists():
        print("A4 / variance / A7 / claim yield skipped: contexts.jsonl missing")
        return 0
    contexts = read_contexts(ctx_path)
    supplied = {c["question_id"]: [x["chunk_id"] for x in c["chunks"]] for c in contexts}
    mode = cfg.generator.output_mode
    runs = load_runs(cfg, sorted(supplied), mode)
    set_of = {c["question_id"]: c["set"] for c in contexts}
    core_runs = [r for r in runs if set_of[r.question_id] != "supplement"]
    supp_runs = [r for r in runs if set_of[r.question_id] == "supplement"]
    core_q = [
        q for q in questions if set_of.get(q["question_id"]) in ("draft", "control_candidate")
    ]
    meta = {
        **base_meta,
        "contexts sha256": lf_sha256(ctx_path),
        "output_mode": mode,
        "model": cfg.generator.model,
        "thinking / effort": f"{cfg.generator.thinking} / {cfg.generator.effort}",
        "core requests": len(core_runs),
        "supplement requests": len(supp_runs),
    }
    _write("t5_a4.md", rp.finish(rp.a4_report(meta, core_runs, supplied, mode), composition))
    _write("t5_variance.md", rp.finish(rp.variance_report(meta, core_runs, core_q), composition))
    matrix = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))
    prices = cfg.generator.pricing_usd_per_mtok.model_dump()
    _write(
        "t5_a7.md",
        rp.finish(rp.a7_report(meta, runs, matrix, prices, n_questions=170), composition),
    )
    _write(
        "t5_claim_yield.md", rp.finish(rp.claim_yield_report(meta, core_runs, core_q), composition)
    )
    _write(
        "t5_supplement.md",
        rp.finish(rp.supplement_report(meta, supp_runs, questions, supplied, mode), composition),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
