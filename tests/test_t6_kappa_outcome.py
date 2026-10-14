"""T6 kappa, gate and outcome rules (D-003; D-004 status 2026-10-13; D-044 items 5-7 and its
status lines of 2026-10-14). Synthetic fixtures only; git is stubbed.

The 6(b) cases below are rows of the T6 plan's table under the RULED rule (D-044 status
2026-10-14). Its k = 0 rows were computed there under scikit-learn's convention (sklearn
convention, not the ruled rule); under the ruled rule k = 0 -> Granite Guardian if eligible."""

from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from pathlib import Path

import pytest

from ledger.config import load_config
from ledger.eval import kappa as K
from ledger.eval import pilot_outcome as O
from ledger.eval.labels import PilotLabel
from ledger.eval.pilot_report import REFUSED, run_pilot
from ledger.verify.scores import ScoreRow

GG = "ibm-granite/granite-guardian-3.3-8b"
MC = "bespokelabs/Bespoke-MiniCheck-7B"


@pytest.fixture
def cfg(base_config_path):
    return load_config(base_config_path)


def lab(i, label, qid=None, entailed=True):
    return PilotLabel(
        set="pilot",
        claim_id=f"c{i:03d}",
        question_id=qid or f"q{i // 2:03d}",
        stratum="table",
        label=label,
        found_positions=[] if label == "UNSUPPORTED" else [1],
        unsure=False,
        missing_elements=["unit"] if label == "PARTIAL" else [],
        note="unit missing" if label == "PARTIAL" else "",
        stands_alone=True,
        entailed_by_answer=entailed,
        assisted=False,
        context_hash="h",
    )


def row(i, p, verifier=GG, mode="concatenated", status="ok", kind="claim"):
    return ScoreRow(
        kind=kind,
        item_id=f"c{i:03d}",
        question_id=f"q{i // 2:03d}",
        verifier=verifier,
        revision="r",
        mode=mode,
        status=status,
        p_supported=p if status == "ok" else None,
        parsed=["no" if (p or 0) > 0.5 else "yes"],
        reason="" if status == "ok" else "parse failure",
        context_hash="h",
    )


# ---- kappa ----------------------------------------------------------------------------------


def test_kappa_hand_computed_and_exact():
    a = ["S", "S", "U", "U", "S", "U"]
    b = ["S", "U", "U", "U", "S", "S"]
    # po = 4/6; pe = (3/6)(3/6) + (3/6)(3/6) = 1/2 -> kappa = (2/3 - 1/2) / (1/2) = 1/3
    assert K.cohen_kappa(a, b) == Fraction(1, 3)


def test_kappa_constant_column():
    truth = ["SUPPORTED", "UNSUPPORTED", "SUPPORTED", "SUPPORTED"]
    assert K.cohen_kappa(truth, ["SUPPORTED"] * 4) == 0  # one constant rater: 0, not NaN
    assert K.cohen_kappa(["SUPPORTED"] * 4, ["SUPPORTED"] * 4) is None  # undefined


def test_auroc():
    assert K.auroc([0.9, 0.8, 0.1], [True, True, False]) == 1.0
    assert K.auroc([0.5, 0.5], [True, False]) == 0.5
    assert K.auroc([0.5], [True]) is None


def test_align_refusals():
    labels = [lab(1, "SUPPORTED"), lab(2, "UNSUPPORTED")]
    with pytest.raises(K.KappaRefused, match="FAIL"):
        K.align(labels, [row(1, 0.9), row(2, None, status="FAIL")], 2)
    with pytest.raises(K.KappaRefused, match="wrong row count"):
        K.align(labels, [row(1, 0.9)], 2)
    with pytest.raises(K.KappaRefused, match="ids"):
        K.align(labels, [row(1, 0.9), row(3, 0.1)], 2)


def test_bootstrap_deterministic_and_counts_undefined():
    clusters = ["a", "a", "b", "c"]
    stat = lambda idx: None if len(set(idx)) < 3 else float(len(idx))  # noqa: E731
    one = K.cluster_bootstrap(clusters, stat, n=200, seed=5, level=0.95)
    two = K.cluster_bootstrap(clusters, stat, n=200, seed=5, level=0.95)
    assert one == two and one.undefined > 0 and one.clusters == 3


# ---- gate (item 5) ------------------------------------------------------------------------------


def test_gate(cfg):
    labels = (
        [lab(i, "SUPPORTED") for i in range(8)]
        + [lab(i, "PARTIAL") for i in range(8, 12)]
        + [lab(i, "UNSUPPORTED", entailed=i != 12) for i in range(12, 16)]
    )
    g = O.gate(labels, cfg)
    assert (g.k, g.m, g.readable) == (8, 8, True)
    assert g.n_entailed == 15 and g.n_entailed_unsupported == 7
    assert g.a3_rate == Fraction(7, 15) and g.a3_pass
    assert not O.gate(labels[:15], cfg).readable  # k = 7


# ---- item 6(b) as ruled -------------------------------------------------------------------------


def T(k, m, tp, fp):
    return O.Tally(tp=tp, tn=m - fp, k=k, m=m)


@pytest.mark.parametrize(
    "k,m,mc,gg,want",
    [
        (0, 38, (0, 1), (0, 3), GG),  # k = 0: BA undefined -> Granite (sklearn would say MC)
        (0, 38, (0, 0), (0, 2), GG),
        (1, 38, (1, 2), (0, 2), GG),  # |dTP| + |dTN| = 1
        (1, 38, (1, 1), (0, 3), MC),
        (4, 40, (4, 6), (2, 3), MC),
        (4, 40, (3, 2), (2, 0), MC),  # a trade between classes is not "one claim"
        (4, 40, (3, 0), (2, 0), GG),
        (4, 40, (3, 0), (0, 0), MC),  # Granite not eligible (k >= 4, catches < 2)
        (6, 36, (3, 6), (2, 0), GG),  # exact BA tie
        (6, 36, (3, 1), (2, 0), MC),
        (6, 36, (3, 0), (3, 0), GG),
        (7, 45, (3, 0), (2, 1), MC),  # dTP = +1, dTN = +1: two claims
        (7, 30, (3, 0), (2, 6), MC),
    ],
)
def test_6b_ruled(cfg, k, m, mc, gg, want):
    ch = O.choose_not_readable({MC: T(k, m, *mc), GG: T(k, m, *gg)}, {MC: True, GG: True}, cfg)
    assert ch.verifier == want and ch.provisional


def test_6b_eligibility_and_none(cfg):
    # Granite flags 9 of 40 SUPPORTED (> 20 %); MiniCheck NOT SCORED -> none eligible
    ch = O.choose_not_readable({MC: None, GG: T(4, 40, 3, 9)}, {MC: False, GG: True}, cfg)
    assert ch.verifier is None and "owner rules" in ch.why
    assert ch.eligible[MC] and ch.eligible[GG]
    # 8 of 40 = exactly 20 % is eligible
    assert O.eligibility(T(4, 40, 2, 8), True, cfg) == []
    ch = O.choose_not_readable({MC: T(4, 40, 2, 0), GG: T(4, 40, 1, 0)}, {MC: True, GG: True}, cfg)
    assert ch.verifier == MC and ch.why == "the only eligible verifier"


def test_balanced_accuracy_exact():
    assert O.balanced_accuracy(T(6, 36, 3, 6)) == O.balanced_accuracy(T(6, 36, 2, 0))
    assert O.balanced_accuracy(T(0, 36, 0, 1)) is None


def test_tally_flags_at_or_below_half():
    pairs = [(lab(1, "PARTIAL"), row(1, 0.5)), (lab(2, "SUPPORTED"), row(2, 0.5000001))]
    assert O.tally(pairs, 0.5) == O.Tally(tp=1, tn=1, k=1, m=1)


# ---- item 6(a) and D-004 ------------------------------------------------------------------------


def test_d004_tie_exact_at_005():
    assert O.d004_mode(Fraction(65, 100), Fraction(60, 100), 0.05) == "concatenated"
    assert O.d004_mode(Fraction(60, 100), Fraction(66, 100), 0.05) == "per_chunk_max"
    assert O.d004_mode(None, Fraction(9, 10), 0.05) == "concatenated"


def test_choose_readable_branches(cfg):
    ks = {(GG, "concatenated"): Fraction(7, 10), (GG, "per_chunk_max"): Fraction(62, 100)}
    r = O.choose_readable(ks, cfg)
    assert (r.outcome, r.verifier, r.mode) == (O.GO, GG, "concatenated")  # 0.08 apart
    r = O.choose_readable({(GG, "concatenated"): Fraction(55, 100)}, cfg)
    assert r.outcome == O.GO and "tune the threshold" in r.why
    r = O.choose_readable(
        {(GG, "concatenated"): Fraction(4, 10), (MC, "concatenated"): Fraction(3, 10)}, cfg
    )
    assert r.outcome == O.NO_GO_CANDIDATE and "never a switch" in r.why
    r = O.choose_readable(
        {(GG, "concatenated"): Fraction(7, 10), (MC, "per_chunk_max"): Fraction(7, 10)}, cfg
    )
    assert r.outcome == "STOP" and "owner rules" in r.why


def test_relabel_selection(cfg):
    labels = [lab(i, "SUPPORTED" if i % 2 else "UNSUPPORTED") for i in range(40)]
    pairs = [(la, row(i, 0.9 if i % 3 else 0.1)) for i, la in enumerate(labels)]
    one = O.relabel_selection(pairs, cfg)
    assert one == O.relabel_selection(pairs, cfg) and len(one) == 20 and len(set(one)) == 20


# ---- ledger pilot end to end -------------------------------------------------------------------


def git_ok(args):
    return subprocess.CompletedProcess(args, 0, "", "")


def git_untracked(args):
    return subprocess.CompletedProcess(args, 1, "", "")


def setup_pilot(tmp_path, monkeypatch, cfg, labels, rows, verifiers):
    tmp_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    manifest = {
        "manifest": True,
        "seed": 1,
        "n": len(labels),
        "max_claims_per_answer": 3,
        "claims_sha256": "x",
        "sampler": "t6_sample v1",
        "label_guide_sha256": "g",
    }
    lp = Path("data/labels_pilot.jsonl")
    lp.parent.mkdir(parents=True)
    lp.write_text(
        "\n".join(json.dumps(x) for x in [manifest, *[la.model_dump() for la in labels]]) + "\n"
    )
    import hashlib

    pa = Path(cfg.pilot.paths.part_a)
    pa.parent.mkdir(parents=True)
    pa.write_text("{}", encoding="utf-8")
    sm = {
        "manifest": True,
        "labels_sha256": hashlib.sha256(lp.read_bytes()).hexdigest(),
        "panel_sha256": "p",
        "part_a_sha256": hashlib.sha256(pa.read_bytes()).hexdigest(),
        "git_commit": "abc",
        "verifiers": verifiers,
        "revisions": {},
    }
    sp = Path(cfg.pilot.paths.scores)
    sp.write_text("\n".join(json.dumps(x) for x in [sm, *[r.model_dump() for r in rows]]) + "\n")
    return lp


def cells_for(labels, ps, verifier=GG):
    return [
        row(int(la.claim_id[1:]), p, verifier, mode)
        for mode in ("concatenated", "per_chunk_max")
        for la, p in zip(labels, ps, strict=True)
    ]


def test_pilot_gate_only_and_uncommitted(tmp_path, monkeypatch, cfg):
    labels = [lab(i, "SUPPORTED") for i in range(4)]
    lp = setup_pilot(tmp_path, monkeypatch, cfg, labels, [], {GG: "PASS", MC: "NOT SCORED"})
    Path(cfg.pilot.paths.scores).unlink()
    code, text = run_pilot(cfg, lp, run=git_untracked)
    assert code == REFUSED and "committed" in text
    code, text = run_pilot(cfg, lp, run=git_ok)
    assert code == 0 and "gate only" in text and Path(cfg.pilot.paths.gate_report).exists()


def test_pilot_readable_granite_alone(tmp_path, monkeypatch, cfg):
    labels = [lab(i, "SUPPORTED") for i in range(10)] + [
        lab(i, "UNSUPPORTED") for i in range(10, 20)
    ]
    ps = [0.9] * 9 + [0.2] + [0.1] * 9 + [0.8]
    rows = cells_for(labels, ps) + [row(99, 0.2, kind="panel")]
    lp = setup_pilot(tmp_path, monkeypatch, cfg, labels, rows, {GG: "PASS", MC: "NOT SCORED"})
    code, text = run_pilot(cfg, lp, run=git_ok)
    assert code == 0, text
    assert text.index(K.FOLD_NOTE) < text.index(K.THREE_CLASS_NOTE)
    assert "Outcome: **GO**" in text and "mode (D-004): concatenated" in text
    assert "flagged 1 of 1" in text  # panel reported outside kappa


def test_pilot_refuses_on_fail_and_count(tmp_path, monkeypatch, cfg):
    labels = [lab(i, "SUPPORTED") for i in range(10)] + [
        lab(i, "UNSUPPORTED") for i in range(10, 20)
    ]
    rows = cells_for(labels, [0.9] * 10 + [0.1] * 10)
    rows[3] = row(3, None, status="FAIL")
    lp = setup_pilot(tmp_path, monkeypatch, cfg, labels, rows, {GG: "PASS", MC: "NOT SCORED"})
    code, text = run_pilot(cfg, lp, run=git_ok)
    assert code == REFUSED and "FAIL" in text and "Outcome" not in text
    rows = cells_for(labels, [0.9] * 10 + [0.1] * 10)[:-1]
    lp = setup_pilot(tmp_path / "b", monkeypatch, cfg, labels, rows, {GG: "PASS", MC: "NOT SCORED"})
    code, text = run_pilot(cfg, lp, run=git_ok)
    assert code == REFUSED and "Outcome" not in text


def test_pilot_not_readable_uses_6b(tmp_path, monkeypatch, cfg):
    labels = [lab(i, "SUPPORTED") for i in range(30)] + [lab(i, "PARTIAL") for i in range(30, 34)]
    gg_p = [0.9] * 30 + [0.1, 0.1, 0.9, 0.9]
    mc_p = [0.9] * 30 + [0.1, 0.1, 0.1, 0.9]
    rows = cells_for(labels, gg_p) + cells_for(labels, mc_p, MC)
    lp = setup_pilot(tmp_path, monkeypatch, cfg, labels, rows, {GG: "PASS", MC: "PASS"})
    code, text = run_pilot(cfg, lp, run=git_ok)
    assert code == 0, text
    assert "INCONCLUSIVE" in text and f"provisional verifier: **{GG}**" in text
    assert "|dTP| + |dTN| = 1" in text
