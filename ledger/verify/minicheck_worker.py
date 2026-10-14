"""Bespoke-MiniCheck-7B on its OFFICIAL path (D-044 items 7-8; status 2026-10-14 (3), (4), (6)).

Runs inside its own venv on the GPU box (vLLM pins torch 2.13.0; the project has 2.14.0), so it
imports nothing from ``ledger`` - stdlib, huggingface_hub and the minicheck package only:

    <mc-venv>/bin/python ledger/verify/minicheck_worker.py --mode check --repo R --pin SHA --out C
    HF_HUB_OFFLINE=1 <mc-venv>/bin/python ledger/verify/minicheck_worker.py --mode score \
        --repo R --pin SHA --in REQ --out RES

1. Revision (status (4)): ``snapshot_download`` at the pinned revision, then ``revision="main"``
   (writes refs/main; no new files when main is the pin). NOT SCORED unless HF main is the pin,
   refs/main is the pin and the only snapshot in the cache is the pin. Scoring then runs as a
   separate process with HF_HUB_OFFLINE=1, re-checks the cache offline, and cannot fetch or load
   anything else. ``MiniCheck(model_name=...)`` accepts no local path and
   ``LLMCheck`` passes no revision to vLLM (Liyan06/MiniCheck at b58b9fa), hence this check.
2. Scoring: ``MiniCheck(model_name='Bespoke-MiniCheck-7B', enable_prefix_caching=False)`` and its
   ``score()`` - the package's own re-segmentation (NLTK; status (3)) and P(yes) rule, unchanged.
   A pass-through wrapper on ``LLMCheck.llm.generate`` keeps the vLLM outputs; nothing about
   scoring changes.
3. Agreement (status (6)): every generation whose summed "yes" mass sets the final score (all of
   them when claim sentences tie) must have a rank-1 token that lower-cases to "yes" iff P > 0.5;
   otherwise the row is FAIL. A row whose package-built document is not exactly one chunk is FAIL.

Input: JSONL of ``{"id", "doc", "claim"}``. Output: JSONL, first line ``{"status": "ok" |
"NOT SCORED", "reason", "env"}``, then one line per request."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

MODEL_NAME = "Bespoke-MiniCheck-7B"


def revision_check(repo: str, pin: str) -> str:
    """'' when the cache can only serve the pinned revision, else the reason."""
    from huggingface_hub import HfApi, snapshot_download
    from huggingface_hub.constants import HF_HUB_CACHE

    main = HfApi().model_info(repo, revision="main").sha
    if main != pin:
        return f"HF main of {repo} is {main}, not the pin {pin}"
    snapshot_download(repo, revision=pin)
    snapshot_download(repo, revision="main")
    root = Path(HF_HUB_CACHE) / ("models--" + repo.replace("/", "--"))
    ref = (root / "refs" / "main").read_text().strip()
    snaps = sorted(p.name for p in (root / "snapshots").iterdir())
    if ref != pin or snaps != [pin]:
        return f"cache refs/main {ref}, snapshots {snaps}: not only the pin {pin}"
    return ""


def agreement(masses, tokens, final):
    """Status (6): every tied generation agrees; returns (ok, indices that set the score)."""
    tied = [i for i, m in enumerate(masses) if m == final]
    ok = bool(tied) and all((tokens[i].lower() == "yes") == (final > 0.5) for i in tied)
    return ok, tied


def score_requests(reqs):  # pragma: no cover - GPU, other venv
    from minicheck.minicheck import MiniCheck

    scorer = MiniCheck(model_name=MODEL_NAME, enable_prefix_caching=False, cache_dir=None)
    lc = scorer.model
    captured = []
    original = lc.llm.generate

    def generate(*a, **k):  # pass-through: keeps the outputs, changes nothing
        out = original(*a, **k)
        captured.append(out)
        return out

    lc.llm.generate = generate
    docs, claims = [r["doc"] for r in reqs], [r["claim"] for r in reqs]
    _, probs, used, _ = scorer.score(docs=docs, claims=claims)
    responses = [resp for batch in captured for resp in batch]
    out, pos = [], 0
    for idx, r in enumerate(reqs):
        sentences = lc.split_into_sentences(r["claim"])
        n_chunks = len(used[idx])
        gens = []
        for _ in range(n_chunks * len(sentences)):
            resp = responses[pos]
            pos += 1
            o = resp.outputs[0]
            tid = o.token_ids[0]
            top = o.logprobs[0]
            gens.append(
                {
                    "rank1_token": top[tid].decoded_token,
                    "yes_mass": float(lc.get_support_prob(resp)),
                    "top5": [[v.decoded_token, float(v.logprob)] for v in top.values()],
                }
            )
        final = float(probs[idx])
        row = {
            "id": r["id"],
            "p": final,
            "n_doc_chunks": n_chunks,
            "n_claim_sentences": len(sentences),
            "package_chunk_sha256": [
                hashlib.sha256(c.encode("utf-8")).hexdigest() for c in used[idx]
            ],
            "generations": gens,
        }
        if n_chunks != 1:
            row.update(status="FAIL", reason=f"package built {n_chunks} chunks, not 1")
        else:
            masses = [g["yes_mass"] for g in gens]
            ok, tied = agreement(masses, [g["rank1_token"] for g in gens], final)
            row["tied"] = tied
            row.update(
                status="ok" if ok else "FAIL",
                reason="" if ok else "rank-1 token disagrees with P(yes) > 0.5 (status (6))",
            )
        out.append(row)
    if pos != len(responses):
        raise RuntimeError(f"consumed {pos} of {len(responses)} generations")
    return out


def env_info():  # pragma: no cover - other venv
    info = {}
    for mod in ("vllm", "torch", "transformers", "nltk"):
        try:
            info[mod] = __import__(mod).__version__
        except Exception as exc:  # noqa: BLE001
            info[mod] = f"unavailable: {exc!r}"
    return info


def cache_check(repo: str, pin: str) -> str:
    """Offline re-check before loading: refs/main and the only snapshot are the pin."""
    from huggingface_hub.constants import HF_HUB_CACHE

    root = Path(HF_HUB_CACHE) / ("models--" + repo.replace("/", "--"))
    try:
        ref = (root / "refs" / "main").read_text().strip()
        snaps = sorted(p.name for p in (root / "snapshots").iterdir())
    except OSError as exc:
        return f"cache unreadable: {exc!r}"
    if ref != pin or snaps != [pin]:
        return f"cache refs/main {ref}, snapshots {snaps}: not only the pin {pin}"
    return ""


def main(argv=None) -> int:  # pragma: no cover - other venv
    """``--mode check`` (online): the revision check, run as its own process. ``--mode score``
    (HF_HUB_OFFLINE=1 set by the parent before this process starts, so huggingface_hub and vLLM
    read it at import): the offline cache re-check, then scoring."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("check", "score"), required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pin", required=True)
    ap.add_argument("--in", dest="inp")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    if a.mode == "check":
        reason = revision_check(a.repo, a.pin)
        out.write_text(json.dumps({"status": "NOT SCORED" if reason else "ok", "reason": reason}))
        return 3 if reason else 0
    if os.environ.get("HF_HUB_OFFLINE") != "1":
        out.write_text(json.dumps({"status": "NOT SCORED", "reason": "HF_HUB_OFFLINE is not 1"}))
        return 3
    reason = cache_check(a.repo, a.pin)
    if reason:
        out.write_text(json.dumps({"status": "NOT SCORED", "reason": reason}))
        return 3
    reqs = [json.loads(ln) for ln in Path(a.inp).read_text(encoding="utf-8").splitlines() if ln]
    rows = score_requests(reqs)
    head = {"status": "ok", "reason": "", "env": env_info()}
    lines = [json.dumps(x, ensure_ascii=False) for x in [head, *rows]]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
