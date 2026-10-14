"""T6 scoring (D-044 items 7-10; status 2026-10-14 (3), (4), (6)): Granite polarity and agreement
on canned outputs, the MiniCheck agreement rule, the worker's isolation, mode aggregation, part
B's gates, part A's budget/retry/disagreement logic and the verify spans. No GPU, no network:
subprocesses, git and clocks are faked."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from ledger.config import load_config
from ledger.pilot import part_a
from ledger.tracing import otel
from ledger.verify import granite as G
from ledger.verify import minicheck_worker as W
from ledger.verify import run as R
from ledger.verify.scores import ScoreRow

YES, NO = 4893, 642


@pytest.fixture
def cfg(base_config_path):
    return load_config(base_config_path)


# ---- Granite ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texts,idx",
    [
        (["<score>", " no", " </score>"], 1),
        (["<", "score", ">", " yes", " </", "score", ">"], 3),
        (["<score> ", "no"], 1),
        (["I", " think"], None),
    ],
)
def test_verdict_index(texts, idx):
    assert G.verdict_index(texts) == idx


def test_p_supported():
    assert G.p_supported(2.0, 2.0) == 0.5
    assert G.p_supported(3.0, 0.0) > 0.95 and G.p_supported(0.0, 3.0) < 0.05


def call(parsed_word, tid, logit_no, logit_yes, texts=None):
    texts = texts or ["<score>", f" {parsed_word}", " </score>"]
    return G.judge(
        token_texts=texts,
        token_ids=[1, tid, 2],
        logits_at=lambda i: {NO: logit_no, YES: logit_yes},
        decoded="".join(texts),
        yes_id=YES,
        no_id=NO,
    )


def test_granite_polarity_and_agreement():
    ok = call("no", NO, 3.0, 0.8)  # "no" = grounded -> supported, P ~ 0.9
    assert ok.status == "ok" and ok.p > 0.5 and ok.parsed == "no"
    ok = call("yes", YES, 0.8, 3.0)
    assert ok.status == "ok" and ok.p < 0.5
    bad = call("yes", YES, 3.0, 0.8)  # parsed yes but P(supported) 0.9 -> FAIL, never a label
    assert bad.status == "FAIL" and "disagrees" in bad.reason
    assert call("no", 999, 3.0, 0.8).status == "FAIL"  # not a recorded verdict id
    nos = call("no", NO, 3.0, 0.8, texts=["The", " answer"])
    assert nos.status == "FAIL" and "no <score>" in nos.reason


# ---- MiniCheck agreement (status (6)) ----------------------------------------------------------


def test_minicheck_agreement_owner_example():
    # "No" 0.40, "yes" 0.30, "Yes" 0.25 -> P = 0.55 but the rank-1 token is "No": disagreement
    ok, tied = W.agreement([0.55], ["No"], 0.55)
    assert not ok and tied == [0]
    assert W.agreement([0.98], ["Yes"], 0.98)[0]
    assert W.agreement([0.01], ["No"], 0.01)[0]


def test_minicheck_agreement_all_tied_sentences():
    # two claim sentences tie at the minimum: both must agree
    assert not W.agreement([0.3, 0.3, 0.9], ["No", "Yes", "Yes"], 0.3)[0]
    ok, tied = W.agreement([0.3, 0.3, 0.9], ["No", "no", "Yes"], 0.3)
    assert ok and tied == [0, 1]


def test_worker_imports_nothing_from_ledger_or_gpu_at_module_level():
    tree = ast.parse(Path(W.__file__).read_text(encoding="utf-8"))
    top = [n for n in tree.body if isinstance(n, ast.Import | ast.ImportFrom)]
    names = {a.name.split(".")[0] for n in top for a in n.names} | {
        (n.module or "").split(".")[0] for n in top if isinstance(n, ast.ImportFrom)
    }
    assert not names & {"ledger", "vllm", "torch", "minicheck", "huggingface_hub"}


# ---- aggregation and modes -------------------------------------------------------------------


def item(i="q001::c01", kind="claim"):
    return R.ScoreItem(
        kind,
        i,
        "q001",
        "It was 5.",
        tuple(f"k{j}" for j in range(5)),
        tuple(f"chunk {j}" for j in range(5)),
    )


def test_score_with_builds_both_modes_and_aggregates():
    seen = []

    def calls(flat):
        seen.extend(flat)
        return [R.Call("ok", 0.1 * (k % 6), "no") for k in range(len(flat))]

    rows = R.score_with([item()], "v", "r", calls)
    assert len(seen) == 6  # 1 concatenated + 5 per chunk
    assert seen[0][0] == "\n\n".join(f"chunk {j}" for j in range(5))
    concat, pcm = rows
    assert concat.mode == "concatenated" and concat.p_supported == 0.0
    assert pcm.mode == "per_chunk_max" and pcm.p_supported == pytest.approx(0.5)
    assert pcm.per_chunk_p == pytest.approx([0.1, 0.2, 0.3, 0.4, 0.5])


def test_any_chunk_fail_fails_the_row():
    calls = [R.Call("ok", 0.9, "no")] * 4 + [R.Call("FAIL", None, "", "parse failure")]
    row = R.aggregate(item(), "v", "r", "per_chunk_max", calls)
    assert row.status == "FAIL" and row.p_supported is None and "parse failure" in row.reason


def test_minicheck_calls_mapping():
    res = [
        {
            "status": "ok",
            "p": 0.9,
            "tied": [0],
            "n_doc_chunks": 1,
            "n_claim_sentences": 1,
            "package_chunk_sha256": ["h"],
            "generations": [{"rank1_token": "Yes"}],
        },
        {
            "status": "FAIL",
            "p": 0.55,
            "tied": [0],
            "n_doc_chunks": 1,
            "n_claim_sentences": 1,
            "package_chunk_sha256": ["h"],
            "reason": "rank-1 token disagrees",
            "generations": [{"rank1_token": "No"}],
        },
    ]
    a, b = R.minicheck_calls(res)
    assert (a.status, a.p, a.parsed) == ("ok", 0.9, "Yes")
    assert (b.status, b.p) == ("FAIL", None)


def test_only_p_supported_is_stored():
    fields = set(ScoreRow.model_fields)
    assert not {"p_yes", "logits", "top5", "logprobs"} & fields


# ---- worker driver ------------------------------------------------------------------------------


def fake_worker(check_status="ok", score_rows=None):
    seen = {}

    def runner(args, **kw):
        mode = args[args.index("--mode") + 1]
        out = Path(args[args.index("--out") + 1])
        seen[mode] = kw
        if mode == "check":
            out.write_text(
                json.dumps({"status": check_status, "reason": "HF main is x, not the pin"})
            )
        else:
            rows = [{"status": "ok", "reason": "", "env": {}}, *(score_rows or [])]
            out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        return subprocess.CompletedProcess(args, 0)

    return runner, seen


def test_worker_driver_offline_scoring(cfg, tmp_path):
    runner, seen = fake_worker(score_rows=[{"id": "0", "p": 0.9}])
    status, rows, _ = R.run_minicheck_worker(cfg, [("doc", "claim")], tmp_path, runner=runner)
    assert status == "ok" and rows == [{"id": "0", "p": 0.9}]
    assert seen["score"]["env"]["HF_HUB_OFFLINE"] == "1" and "env" not in seen["check"]
    runner, seen = fake_worker(check_status="NOT SCORED")
    status, rows, reason = R.run_minicheck_worker(cfg, [("d", "c")], tmp_path, runner=runner)
    assert status == "NOT SCORED" and "score" not in seen and "pin" in reason


# ---- part A -----------------------------------------------------------------------------------


def test_verdict_ids():
    assert part_a.verdict_ids([(" no", NO), (" yes", YES), (" no", NO)]) == (YES, NO, [])
    _, _, problems = part_a.verdict_ids([(" no", NO), (" No", 7), (" yes", YES)])
    assert problems and "several token ids" in problems[0]
    assert part_a.verdict_ids([(" no", NO)])[2]


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def part_a_runner(clock, readme_by_version, *, step_seconds=60, disagree=False, check="ok"):
    state = {"version": None, "versions": []}

    def runner(args, **kw):
        clock.t += step_seconds
        if kw.get("timeout") is not None and kw["timeout"] <= 0:
            raise subprocess.TimeoutExpired(args, 0)
        if args[:3] == ["uv", "pip", "install"]:
            state["version"] = next(a for a in args if a.startswith("vllm==")).split("==")[1]
            state["versions"].append(state["version"])
        if "--mode" in args:
            out = Path(args[args.index("--out") + 1])
            if args[args.index("--mode") + 1] == "check":
                out.write_text(json.dumps({"status": check, "reason": "refs/main is not the pin"}))
            else:
                ps = readme_by_version[state["version"]]
                rows = [{"status": "ok", "reason": "", "env": {}}]
                for k, p in enumerate(ps):
                    fail = disagree and k == 0
                    rows.append(
                        {
                            "id": str(k),
                            "p": p,
                            "status": "FAIL" if fail else "ok",
                            "reason": "rank-1 token disagrees" if fail else "",
                            "generations": [{"rank1_token": "Yes", "yes_mass": p, "top5": []}],
                        }
                    )
                out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        return subprocess.CompletedProcess(args, 0, "", "")

    return runner, state


REQ = [{"id": "readme_1", "doc": "d", "claim": "c1"}, {"id": "readme_2", "doc": "d", "claim": "c2"}]
EXPECTED = [0.984, 0.011]


def test_part_a_pass_first_attempt(cfg, tmp_path):
    clock = Clock()
    runner, state = part_a_runner(clock, {"0.31.0": [0.98, 0.012]})
    rec = part_a.minicheck_part_a(cfg, REQ, EXPECTED, tmp_path, runner=runner, clock=clock)
    assert rec["status"] == "PASS" and rec["vllm"] == "0.31.0" and state["versions"] == ["0.31.0"]
    assert not rec["minicheck_disagreement"]


def test_part_a_retry_with_older_vllm(cfg, tmp_path):
    clock = Clock()
    runner, state = part_a_runner(clock, {"0.31.0": [0.0, 0.0], "0.30.0": [0.99, 0.01]})
    rec = part_a.minicheck_part_a(cfg, REQ, EXPECTED, tmp_path, runner=runner, clock=clock)
    assert state["versions"] == ["0.31.0", "0.30.0"] and rec["status"] == "PASS"
    assert rec["vllm"] == "0.30.0"


def test_part_a_budget_exhausted_is_not_scored(cfg, tmp_path):
    clock = Clock()
    runner, _ = part_a_runner(clock, {"0.31.0": [0.0, 0.0]}, step_seconds=25 * 60)
    rec = part_a.minicheck_part_a(cfg, REQ, EXPECTED, tmp_path, runner=runner, clock=clock)
    assert rec["status"] == "NOT SCORED"
    assert any(a.get("result") == "budget exhausted" for a in rec["attempts"])


def test_part_a_disagreement_flag_and_revision_stop(cfg, tmp_path):
    clock = Clock()
    runner, _ = part_a_runner(clock, {"0.31.0": [0.98, 0.012]}, disagree=True)
    rec = part_a.minicheck_part_a(cfg, REQ, EXPECTED, tmp_path, runner=runner, clock=clock)
    assert rec["minicheck_disagreement"]
    clock = Clock()
    runner, state = part_a_runner(clock, {"0.31.0": [0.98, 0.012]}, check="NOT SCORED")
    rec = part_a.minicheck_part_a(cfg, REQ, EXPECTED, tmp_path / "b", runner=runner, clock=clock)
    assert rec["status"] == "NOT SCORED" and state["versions"] == ["0.31.0"]  # no retry


# ---- part B gates -------------------------------------------------------------------------------


def git(status_out="", committed=True, head="abc"):
    def run(args):
        if args[0] == "status":
            return subprocess.CompletedProcess(args, 0, status_out, "")
        if args[0] == "rev-parse":
            return subprocess.CompletedProcess(args, 0, head + "\n", "")
        return subprocess.CompletedProcess(args, 0 if committed else 1, "", "")

    return run


def ready_files(tmp_path, monkeypatch, cfg, part_a_rec):
    monkeypatch.chdir(tmp_path)
    p = cfg.pilot.paths
    manifest = {
        "manifest": True,
        "seed": 1,
        "n": 1,
        "max_claims_per_answer": 3,
        "claims_sha256": "x",
        "sampler": "t6_sample v1",
        "label_guide_sha256": "g",
    }
    label = {
        "set": "pilot",
        "claim_id": "q001::c01",
        "question_id": "q001",
        "stratum": "table",
        "label": "SUPPORTED",
        "found_positions": [1],
        "unsure": False,
        "missing_elements": [],
        "note": "",
        "stands_alone": True,
        "entailed_by_answer": True,
        "assisted": False,
        "context_hash": "h",
    }
    Path(p.labels).parent.mkdir(parents=True)
    Path(p.labels).write_text(json.dumps(manifest) + "\n" + json.dumps(label) + "\n")
    import hashlib

    sha = hashlib.sha256(Path(p.labels).read_bytes()).hexdigest()
    Path(p.gate_report).parent.mkdir(parents=True)
    Path(p.gate_report).write_text(f"labels sha256 `{sha}`\n")
    Path(p.panel).write_text("")
    if part_a_rec is not None:
        Path(p.part_a).parent.mkdir(parents=True)
        Path(p.part_a).write_text(json.dumps(part_a_rec))


PART_A_OK = {
    "git_commit": "abc",
    "minicheck_disagreement": False,
    "verifiers": {R.GG_REPO: "PASS", R.MC_REPO: "NOT SCORED"},
}


def test_check_ready_passes_and_refuses(tmp_path, monkeypatch, cfg):
    ready_files(tmp_path, monkeypatch, cfg, PART_A_OK)
    assert R.check_ready(cfg, git())["git_commit"] == "abc"
    with pytest.raises(R.ScoreRefused, match="not clean"):
        R.check_ready(cfg, git(" M ledger/verify/run.py\n"))
    with pytest.raises(R.ScoreRefused, match="not clean"):
        R.check_ready(cfg, git("?? scripts/hack.py\n"))
    R.check_ready(cfg, git("?? notes.txt\n"))  # untracked outside the guarded dirs is fine
    with pytest.raises(R.ScoreRefused, match="not committed"):
        R.check_ready(cfg, git(committed=False))
    with pytest.raises(R.ScoreRefused, match="another commit"):
        R.check_ready(cfg, git(head="def"))


@pytest.mark.parametrize(
    "rec,match",
    [
        (None, "part A writes its report"),
        ({**PART_A_OK, "verifiers": {R.GG_REPO: "FAIL", R.MC_REPO: "PASS"}}, "Granite"),
        ({**PART_A_OK, "minicheck_disagreement": True}, "until the owner rules"),
    ],
)
def test_check_ready_part_a_gates(tmp_path, monkeypatch, cfg, rec, match):
    ready_files(tmp_path, monkeypatch, cfg, rec)
    with pytest.raises(R.ScoreRefused, match=match):
        R.check_ready(cfg, git())


def test_check_ready_needs_gate_naming_the_labels(tmp_path, monkeypatch, cfg):
    ready_files(tmp_path, monkeypatch, cfg, PART_A_OK)
    Path(cfg.pilot.paths.gate_report).write_text("some other labels\n")
    with pytest.raises(R.ScoreRefused, match="gate"):
        R.check_ready(cfg, git())


def test_build_items_refuses_context_mismatch():
    class Lab:
        claim_id, question_id, context_hash = "q001::c01", "q001", "not-the-hash"

    class C:
        text = "It was 5."

    contexts = {"q001": {"chunks": [{"chunk_id": f"k{j}", "text": f"t{j}"} for j in range(5)]}}
    with pytest.raises(R.ScoreRefused, match="context hash"):
        R.build_items([Lab()], {"q001::c01": C()}, [], contexts)


# ---- spans --------------------------------------------------------------------------------------


def test_verify_spans_inline_verdicts_and_fail_status(cfg):
    exp = InMemorySpanExporter()
    otel.init_tracing(cfg, exporter=exp)
    try:
        it = item()
        ok = R.aggregate(it, "v", "r", "concatenated", [R.Call("ok", 0.9, "no")])
        pcm = R.aggregate(it, "v", "r", "per_chunk_max", [R.Call("ok", 0.2, "yes")] * 5)
        bad = R.aggregate(it, "v", "r", "concatenated", [R.Call("FAIL", None, "", "parse")])
        R.emit_spans([ok, pcm, bad], {it.item_id: it}, 0.5)
    finally:
        otel.shutdown_tracing()
    spans = [s for s in exp.get_finished_spans() if s.name == "verify"]
    assert len(spans) == 7  # 1 + 5 + 1: one span per verifier call
    labels = [s.attributes.get("evaluations.0.evaluation.label") for s in spans]
    assert labels[:6] == ["SUPPORTED"] + ["UNSUPPORTED"] * 5 and labels[6] is None
    assert spans[6].status.status_code.name == "ERROR"
    meta = json.loads(spans[0].attributes["evaluations.0.evaluation.metadata"])
    assert meta["cited_support"] is None and meta["input_mode"] == "concatenated"
