"""T6 part A (D-044 items 8-9; status 2026-10-14 (4), (6)): reference checks before any pilot
claim is scored. Writes ``results/t6/part_a.json`` and ``.md``; part B refuses without them.

* Granite Guardian: the T5 probe's README markers and 16 mechanical checks (4 supported + 4
  digit-altered claims at one-chunk and five-chunk context); the verdict-token ids after
  ``<score>`` must be exactly one id for "yes" and one for "no"; then every check is re-scored
  with P(supported) at that position and must be correct and agree with its parsed text.
* MiniCheck: one attempt on the official path, capped at ``pilot.part_a_budget_min`` minutes
  INCLUDING the venv build and one retry with an older vLLM (the clock starts before the venv is
  built). Pass = the README example within +/- ``pilot.readme_tolerance``. Fail = NOT SCORED.
  The README example and the same 16 probe claims are scored; every call's rank-1 token and summed
  "yes" mass are written; ANY disagreement sets ``minicheck_disagreement`` and part B refuses until
  the owner rules.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from ledger.baseline import probe
from ledger.config import Config
from ledger.tracing import otel
from ledger.verify.run import GG_REPO, MC_REPO

Runner = Callable[..., subprocess.CompletedProcess]


# ---- Granite ----------------------------------------------------------------------------------


def verdict_ids(observed: Sequence[tuple[str, int]]) -> tuple[int | None, int | None, list[str]]:
    """``observed`` = (decoded text, token id) of the token after ``<score>`` in each output.
    Exactly one id per verdict word, and no other word, or problems are returned."""
    by_word: dict[str, set[int]] = {}
    for text, tid in observed:
        by_word.setdefault(text.strip().lower(), set()).add(tid)
    problems = []
    extra = sorted(set(by_word) - {"yes", "no"})
    if extra:
        problems.append(f"verdict tokens other than yes/no: {extra}")
    for w in ("yes", "no"):
        if len(by_word.get(w, ())) > 1:
            problems.append(f"{w!r} appears as several token ids {sorted(by_word[w])}")
    yes = next(iter(by_word["yes"])) if len(by_word.get("yes", ())) == 1 else None
    no = next(iter(by_word["no"])) if len(by_word.get("no", ())) == 1 else None
    if yes is None or no is None:
        problems.append(f"both verdict ids are needed; got yes={yes}, no={no}")
    return yes, no, problems


def granite_part_a(
    cfg: Config, claims: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:  # pragma: no cover - GPU
    import gc

    import torch

    from ledger.verify import granite

    pin = cfg.verifier.pilot_pins[GG_REPO].revision
    readme = probe.fetch_source(
        "Granite Guardian 3.3 model card",
        GG_REPO,
        "README.md",
        pin,
        probe.hf_url(GG_REPO, pin, "README.md"),
        probe.default_fetch,
    )
    rec: dict[str, Any] = {"readme_sha256": readme.sha256, "revision": pin}
    try:
        probe.check_gg_readme(readme.text)
    except probe.ProbeStop as exc:
        return {**rec, "status": "FAIL", "reason": str(exc)}
    sc = granite.GraniteScorer(pin, -1, -1, cfg.pilot.granite_max_new_tokens)
    try:
        observed, outs = [], []
        for c in claims:
            with otel.verify_span(f"part_a:{c['question_id']}:{c['label']}:{c['context_chunks']}"):
                ids, texts, decoded, logits = sc.generate(c["doc"], c["claim"])
            i = granite.verdict_index(texts)
            if i is not None:
                observed.append((texts[i], ids[i]))
            outs.append((c, ids, texts, decoded, logits))
        yes, no, problems = verdict_ids(observed)
        rec.update(yes_id=yes, no_id=no, yes_token=None, no_token=None)
        if yes is not None and no is not None:
            rec.update(yes_token=sc.tok.decode([yes]), no_token=sc.tok.decode([no]))
        checks = []
        for c, ids, texts, decoded, logits in outs:
            if problems:
                break
            call = granite.judge(
                token_texts=texts,
                token_ids=ids,
                decoded=decoded,
                yes_id=yes,
                no_id=no,
                logits_at=lambda i, lg=logits: {
                    yes: float(lg[i][0].float()[yes]),
                    no: float(lg[i][0].float()[no]),
                },
            )
            correct = call.status == "ok" and probe.correct(c["label"], call.p > 0.5)
            checks.append(
                {
                    "question_id": c["question_id"],
                    "label": c["label"],
                    "context_chunks": c["context_chunks"],
                    "status": call.status,
                    "p": call.p,
                    "parsed": call.parsed,
                    "reason": call.reason,
                    "correct": correct,
                }
            )
        rec["checks"] = checks
        ok = not problems and len(checks) == len(claims) and all(x["correct"] for x in checks)
        rec.update(
            status="PASS" if ok else "FAIL",
            reason="; ".join(problems) or ("" if ok else "a reference check is wrong or FAIL"),
        )
        return rec
    finally:
        del sc
        gc.collect()
        torch.cuda.empty_cache()


# ---- MiniCheck ----------------------------------------------------------------------------------


def minicheck_part_a(
    cfg: Config,
    requests: Sequence[Mapping[str, str]],
    expected: Sequence[float],
    workdir: Path,
    *,
    runner: Runner = subprocess.run,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Venv build + worker, at most two attempts (``minicheck_vllm`` then ``minicheck_vllm_retry``)
    inside one budget. ``requests[:2]`` are the README example's two claims."""
    p = cfg.pilot
    deadline = clock() + p.part_a_budget_min * 60
    attempts: list[dict[str, Any]] = []
    for n, version in enumerate((p.minicheck_vllm, p.minicheck_vllm_retry)):
        venv = Path(os.path.expanduser(p.minicheck_venv + ("" if n == 0 else "-retry")))
        py = venv / "bin" / "python"
        steps = [
            ["uv", "venv", "--clear", "--python", "3.12", str(venv)],
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(py),
                f"vllm=={version}",
                f"minicheck[llm] @ git+https://github.com/Liyan06/MiniCheck.git@{p.minicheck_commit}",
                "huggingface_hub",
            ],
            [str(py), "-c", "import nltk; nltk.download('punkt'); nltk.download('punkt_tab')"],
        ]
        att: dict[str, Any] = {"vllm": version, "venv": str(venv)}
        attempts.append(att)
        try:
            for step in steps:
                left = deadline - clock()
                if left <= 0:
                    raise subprocess.TimeoutExpired(step, 0)
                res = runner(step, check=False, timeout=left, capture_output=True, text=True)
                if res.returncode != 0:
                    raise RuntimeError(f"{step[:3]} exited {res.returncode}: {res.stderr[-500:]}")
            left = deadline - clock()
            if left <= 0:
                raise subprocess.TimeoutExpired("worker", 0)
            cfg_n = cfg.model_copy(
                update={"pilot": p.model_copy(update={"minicheck_venv": str(venv)})}
            )
            from ledger.verify.run import run_minicheck_worker

            status, rows, reason = run_minicheck_worker(
                cfg_n,
                [(r["doc"], r["claim"]) for r in requests],
                workdir / f"attempt{n + 1}",
                timeout=left,
                runner=runner,
            )
        except subprocess.TimeoutExpired:
            att["result"] = "budget exhausted"
            break
        except RuntimeError as exc:
            att["result"] = f"error: {exc}"
            continue
        if status != "ok":
            att["result"] = f"NOT SCORED: {reason}"
            if "pin" in reason or "refs/main" in reason or "OFFLINE" in reason:
                break  # an older vLLM cannot fix the revision
            continue
        for row, req in zip(rows, requests, strict=True):
            row["name"] = req["id"]
            with otel.verify_span(f"part_a:{req['id']}") as span:  # D29: one span per call
                span.set_attribute("rag.verify_status", row["status"])
        got = [r["p"] for r in rows[:2]]
        att.update(result="scored", readme_got=got, calls=rows)
        att["readme_ok"] = probe.within(got, expected, p.readme_tolerance)
        if att["readme_ok"]:
            break
    last = attempts[-1]
    calls = [c for a in attempts for c in a.get("calls", [])]
    disagreement = any(
        c.get("status") == "FAIL" and "disagrees" in c.get("reason", "") for c in calls
    )
    passed = bool(last.get("readme_ok"))
    return {
        "status": "PASS" if passed else "NOT SCORED",
        "reason": ""
        if passed
        else f"README example not reproduced / attempt failed: {last.get('result')}",
        "vllm": last["vllm"] if passed else None,
        "venv": last["venv"] if passed else None,
        "readme_expected": list(expected),
        "attempts": attempts,
        "minicheck_disagreement": disagreement,
        "seconds_left": max(0.0, deadline - clock()),
    }


# ---- record -----------------------------------------------------------------------------------


def record(git_commit: str, gg: Mapping[str, Any], mc: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "git_commit": git_commit,
        "granite": dict(gg),
        "minicheck": dict(mc),
        "verifiers": {GG_REPO: gg.get("status"), MC_REPO: mc.get("status")},
        "minicheck_disagreement": bool(mc.get("minicheck_disagreement")),
    }


def render(rec: Mapping[str, Any]) -> str:
    gg, mc = rec["granite"], rec["minicheck"]
    out = ["# T6 part A (D-044 items 8-9)", "", f"- git: `{rec['git_commit']}`"]
    out += [f"- {v}: **{s}**" for v, s in rec["verifiers"].items()]
    out += [f"- MiniCheck disagreement (status 2026-10-14 (6)): {rec['minicheck_disagreement']}"]
    out += ["", "## Granite Guardian", "", f"- reason: {gg.get('reason', '')}"]
    out += [
        f"- verdict ids: yes {gg.get('yes_id')} ({gg.get('yes_token')!r}), "
        f"no {gg.get('no_id')} ({gg.get('no_token')!r})",
        "",
    ]
    out += [
        "| question | label | chunks | status | P(supported) | parsed | correct |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in gg.get("checks", []):
        p = "" if c["p"] is None else f"{c['p']:.4f}"
        out.append(
            f"| {c['question_id']} | {c['label']} | {c['context_chunks']} | {c['status']} | "
            f"{p} | {c['parsed']} | {c['correct']} |"
        )
    out += ["", "## Bespoke-MiniCheck-7B", "", f"- reason: {mc.get('reason', '')}"]
    out += [f"- README expected {mc.get('readme_expected')}"]
    for a in mc.get("attempts", []):
        out += [
            "",
            f"### attempt: vLLM {a['vllm']} -> {a.get('result')} "
            f"(README got {a.get('readme_got')})",
            "",
        ]
        out += [
            "| call | P | status | rank-1 token(s) | yes mass(es) | top-5 |",
            "|---|---|---|---|---|---|",
        ]
        for c in a.get("calls", []):
            g = c["generations"]
            toks = ", ".join(repr(x["rank1_token"]) for x in g)
            masses = ", ".join(f"{x['yes_mass']:.4f}" for x in g)
            top = "; ".join(f"{t!r}:{lp:.3f}" for x in g for t, lp in x["top5"]).replace("|", "\\|")
            name = c.get("name", c["id"])
            out.append(f"| {name} | {c['p']:.4f} | {c['status']} | {toks} | {masses} | {top} |")
    return "\n".join(out) + "\n"


def write(cfg: Config, rec: Mapping[str, Any]) -> None:
    path, md = Path(cfg.pilot.paths.part_a), Path(cfg.pilot.paths.part_a_report)
    path.parent.mkdir(parents=True, exist_ok=True)
    md.write_bytes(render(rec).encode("utf-8"))
    path.write_bytes(json.dumps(rec, indent=1, ensure_ascii=False).encode("utf-8"))
