"""T6 part B scorer (D-044 items 7, 9, 10; D-004): both verifiers x both input modes over the
committed pilot claims and the committed panel. Stores only P(supported); FAIL is a third value.

Gates (code, not instruction), checked before any model loads:
* the tree is clean (no modified tracked file; nothing untracked under ledger/ scripts/ configs/
  data/);
* the labels file is committed and fully labelled, and the gate report that names its SHA-256 is
  committed (item 5: the gate is read before any verifier runs);
* the panel is committed and valid (item 10);
* part A wrote ``results/t6/part_a.json`` at this HEAD: Granite PASS, MiniCheck PASS or NOT
  SCORED, and no MiniCheck agreement disagreement (part B does not start until the owner rules).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ledger.config import Config
from ledger.eval.labels import LabelsRefused, load_pilot_labels
from ledger.pilot import repo
from ledger.pilot.panel import validate_panel
from ledger.verify.context import context_hash, documents_for, render_context
from ledger.verify.scores import MODES, ScoreRow, ScoresManifest

MC_REPO = "bespokelabs/Bespoke-MiniCheck-7B"
GG_REPO = "ibm-granite/granite-guardian-3.3-8b"
CLEAN_DIRS = ("ledger", "scripts", "configs", "data")


class ScoreRefused(RuntimeError):
    pass


@dataclass(frozen=True)
class ScoreItem:
    kind: str  # claim | panel
    item_id: str
    question_id: str
    claim: str
    chunk_ids: tuple[str, ...]
    chunks: tuple[str, ...]

    @property
    def context_hash(self) -> str:
        return context_hash(render_context(self.chunks))


def build_items(
    label_rows: Sequence[Any],
    claims: Mapping[str, Any],
    panel: Sequence[Any],
    contexts: Mapping[str, Mapping[str, Any]],
) -> list[ScoreItem]:
    out = []

    def ctx(qid):
        ch = contexts[qid]["chunks"]
        return tuple(c["chunk_id"] for c in ch), tuple(c["text"] for c in ch)

    for lab in label_rows:
        ids, texts = ctx(lab.question_id)
        if texts and lab.context_hash != context_hash(render_context(texts)):
            raise ScoreRefused(f"{lab.claim_id}: context hash differs from the labelled one")
        out.append(
            ScoreItem("claim", lab.claim_id, lab.question_id, claims[lab.claim_id].text, ids, texts)
        )
    for p in panel:
        ids, texts = ctx(p.question_id)
        out.append(ScoreItem("panel", p.panel_id, p.question_id, p.claim, ids, texts))
    return out


# ---- gates ----------------------------------------------------------------------------------


def check_ready(cfg: Config, run: repo.Runner = repo._run) -> dict[str, Any]:
    """All part-B gates; returns part A's record."""
    paths = cfg.pilot.paths
    dirty = repo.dirty(run, CLEAN_DIRS)
    if dirty:
        raise ScoreRefused(f"the tree is not clean: {dirty[:10]}")
    if not repo.is_committed(paths.labels, run):
        raise ScoreRefused(f"{paths.labels} is not committed")
    try:
        load_pilot_labels(paths.labels)
    except LabelsRefused as exc:
        raise ScoreRefused(f"labels: {exc}") from exc
    sha = repo.sha256_file(paths.labels)
    gate = Path(paths.gate_report)
    if not repo.is_committed(gate, run) or sha not in gate.read_text(encoding="utf-8"):
        raise ScoreRefused(f"{gate} (naming the labels sha256 {sha}) is not committed")
    if not repo.is_committed(paths.panel, run):
        raise ScoreRefused(f"{paths.panel} is not committed")
    part_a = Path(paths.part_a)
    if not part_a.exists():
        raise ScoreRefused(f"{part_a} missing: part A writes its report before part B (item 9)")
    rec = json.loads(part_a.read_text(encoding="utf-8"))
    if rec.get("git_commit") != repo.head_commit(run):
        raise ScoreRefused("part A ran at another commit; run part A again at this HEAD")
    if rec.get("verifiers", {}).get(GG_REPO) != "PASS":
        raise ScoreRefused("Granite Guardian did not pass part A's reference checks")
    if rec.get("verifiers", {}).get(MC_REPO) not in ("PASS", "NOT SCORED"):
        raise ScoreRefused("part A has no MiniCheck status")
    if rec.get("minicheck_disagreement"):
        raise ScoreRefused(
            "part A recorded a MiniCheck rank-1 token / P(yes) disagreement: part B does not start "
            "until the owner rules (D-044 status 2026-10-14 (6))"
        )
    return rec


# ---- per-verifier calls -> rows -----------------------------------------------------------------


@dataclass(frozen=True)
class Call:
    status: str
    p: float | None
    parsed: str
    reason: str = ""
    n_doc_chunks: int | None = None
    n_claim_sentences: int | None = None
    package_chunk_sha256: str | None = None


def aggregate(
    item: ScoreItem, verifier: str, revision: str, mode: str, calls: Sequence[Call]
) -> ScoreRow:
    """One row from the call(s) of one (item, verifier, mode): concatenated = one call;
    per_chunk_max = max over the five chunk calls, FAIL if any call FAILs."""
    fails = [c for c in calls if c.status != "ok"]
    p = None if fails else max(c.p for c in calls)
    mc = calls[0].n_doc_chunks is not None
    return ScoreRow(
        kind=item.kind,
        item_id=item.item_id,
        question_id=item.question_id,
        verifier=verifier,
        revision=revision,
        mode=mode,
        status="FAIL" if fails else "ok",
        p_supported=p,
        per_chunk_p=[c.p for c in calls] if mode == "per_chunk_max" else None,
        parsed=[c.parsed for c in calls],
        reason="; ".join(c.reason for c in fails),
        context_hash=item.context_hash,
        n_doc_chunks=[c.n_doc_chunks for c in calls] if mc else None,
        n_claim_sentences=calls[0].n_claim_sentences if mc else None,
        package_chunk_sha256=[c.package_chunk_sha256 for c in calls] if mc else None,
    )


def score_with(
    items: Sequence[ScoreItem],
    verifier: str,
    revision: str,
    score_calls: Callable[[list[tuple[str, str]]], list[Call]],
) -> list[ScoreRow]:
    """Builds every (doc, claim) call for both modes, scores them in one go, aggregates."""
    plan, flat = [], []
    for it in items:
        for mode in MODES:
            docs = documents_for(mode, it.chunks)
            plan.append((it, mode, len(flat), len(docs)))
            flat.extend((d, it.claim) for d in docs)
    calls = score_calls(flat)
    if len(calls) != len(flat):
        raise RuntimeError(f"{verifier}: {len(calls)} results for {len(flat)} calls")
    return [aggregate(it, verifier, revision, mode, calls[i : i + n]) for it, mode, i, n in plan]


def minicheck_calls(results: Sequence[Mapping[str, Any]]) -> list[Call]:
    """Worker rows (``minicheck_worker.score_requests``) -> calls."""
    out = []
    for r in results:
        tied = r.get("tied") or []
        gens = r["generations"]
        parsed = ",".join(gens[i]["rank1_token"] for i in tied) if tied else ""
        out.append(
            Call(
                status=r["status"],
                p=r["p"] if r["status"] == "ok" else None,
                parsed=parsed,
                reason=r.get("reason", ""),
                n_doc_chunks=r["n_doc_chunks"],
                n_claim_sentences=r["n_claim_sentences"],
                package_chunk_sha256=(r["package_chunk_sha256"] or [""])[0],
            )
        )
    return out


def run_minicheck_worker(
    cfg: Config,
    calls: list[tuple[str, str]],
    workdir: Path,
    *,
    timeout: float | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[str, list[dict[str, Any]], str]:
    """(status, rows, reason) from the worker in the MiniCheck venv: the online revision check,
    then the offline scoring process."""
    import os

    py = Path(os.path.expanduser(cfg.pilot.minicheck_venv)) / "bin" / "python"
    worker = Path(__file__).with_name("minicheck_worker.py")
    pin = cfg.verifier.pilot_pins[MC_REPO].revision
    workdir.mkdir(parents=True, exist_ok=True)
    req, res, chk = (
        workdir / "mc_requests.jsonl",
        workdir / "mc_results.jsonl",
        workdir / "mc_check.json",
    )
    req.write_text(
        "".join(
            json.dumps({"id": str(i), "doc": d, "claim": c}) + "\n"
            for i, (d, c) in enumerate(calls)
        ),
        encoding="utf-8",
    )
    base = [str(py), str(worker), "--repo", MC_REPO, "--pin", pin]
    runner([*base, "--mode", "check", "--out", str(chk)], check=False, timeout=timeout)
    head = (
        json.loads(chk.read_text())
        if chk.exists()
        else {"status": "NOT SCORED", "reason": "no check output"}
    )
    if head.get("status") != "ok":
        return "NOT SCORED", [], head.get("reason", "")
    env = {**os.environ, "HF_HUB_OFFLINE": "1"}
    runner(
        [*base, "--mode", "score", "--in", str(req), "--out", str(res)],
        check=False,
        timeout=timeout,
        env=env,
    )
    if not res.exists():
        return "NOT SCORED", [], "the scoring process wrote no output"
    lines = [json.loads(ln) for ln in res.read_text(encoding="utf-8").splitlines() if ln]
    if lines[0].get("status") != "ok":
        return "NOT SCORED", [], lines[0].get("reason", "")
    return "ok", lines[1:], ""


# ---- spans (D29: every verify call emits a span) ----------------------------------------------


def emit_spans(rows: Sequence[ScoreRow], items: Mapping[str, ScoreItem], threshold: float) -> None:
    from opentelemetry.trace import Status, StatusCode

    from ledger.eval.kappa import verdict
    from ledger.tracing import otel

    for r in rows:
        it = items[r.item_id]
        evid = [list(it.chunk_ids)] if r.mode == "concatenated" else [[c] for c in it.chunk_ids]
        ps = [r.p_supported] if r.mode == "concatenated" else (r.per_chunk_p or [None] * 5)
        for ids, p in zip(evid, ps, strict=True):
            with otel.verify_span(r.item_id) as span:
                if r.status != "ok" or p is None:
                    span.set_status(Status(StatusCode.ERROR, r.reason or "FAIL"))
                    span.set_attribute("rag.verify_status", "FAIL")
                    continue
                otel.record_verdict(
                    span,
                    otel.VerdictRecord(
                        claim_id=r.item_id,
                        label=verdict(p, threshold),
                        score=p,
                        evidence_ids=ids,
                        input_mode=r.mode,
                        threshold=threshold,
                        cited_support=None,  # D16's cited-chunk check is not part of the pilot
                        verifier_model=r.verifier,
                        verifier_revision=r.revision,
                    ),
                )


def write_scores(path: Path, manifest: ScoresManifest, rows: Sequence[ScoreRow]) -> None:
    lines = [manifest.model_dump_json()] + [r.model_dump_json() for r in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    tmp.replace(path)


def panel_rows(cfg: Config, run1_qids: Sequence[str]):
    rows, problems = validate_panel(Path(cfg.pilot.paths.panel), run1_qids)
    if problems:
        raise ScoreRefused(f"panel invalid: {problems}")
    return rows
