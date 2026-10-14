"""T6 outcome rules (D-044 items 5-7; D-004 status 2026-10-13; D-044 status lines 2026-10-14).

It only recommends: nothing here writes a decision, a config value or a plan tick.

* Readability gate (item 5): k = labels UNSUPPORTED or PARTIAL, m = labels SUPPORTED, counted from
  the committed labels file; binary kappa is readable only if k >= 8 and m >= 8. A3 is read as a
  rate - UNSUPPORTED (binary, PARTIAL folded in) >= 8 % - on the claims flagged "entailed by the
  answer".
* Readable (item 6(a)): the evaluation.md section 6 branches on the best binary kappa, except that
  "both < 0.5" is a NO-GO CANDIDATE; the verifier is the one with the best kappa and its mode is
  set by D-004 (|difference| <= 0.05 on unrounded kappa, or either undefined -> concatenated).
  An exact kappa tie between two verifiers at the best value is not decided here (no rule names
  one): the outcome stops for the owner.
* Not readable (item 6(b) as ruled 2026-10-14): INCONCLUSIVE; eligibility and balanced accuracy on
  concatenated verdicts only; BA = (TP/k + TN/m)/2 exactly (fractions); "differ by at most one
  claim" = |dTP| + |dTN| <= 1 -> Granite Guardian; an exact BA tie -> Granite Guardian; k = 0 or
  m = 0 -> BA undefined: Granite Guardian if eligible, else MiniCheck if eligible; none eligible
  -> no provisional verifier (the owner rules); one eligible -> that one, PROVISIONAL.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction

from ledger.config import Config
from ledger.eval.kappa import verdict
from ledger.eval.labels import PilotLabel, binary
from ledger.verify.scores import ScoreRow

GO, NO_GO_CANDIDATE, INCONCLUSIVE = "GO", "NO-GO CANDIDATE", "INCONCLUSIVE"


# ---- readability gate (item 5) ------------------------------------------------------------------


@dataclass(frozen=True)
class Gate:
    k: int
    m: int
    readable: bool
    n_entailed: int
    n_entailed_unsupported: int
    a3_rate: Fraction | None
    a3_pass: bool | None


def gate(labels: Sequence[PilotLabel], cfg: Config) -> Gate:
    k = sum(binary(lab.label) == "UNSUPPORTED" for lab in labels)
    m = sum(lab.label == "SUPPORTED" for lab in labels)
    ent = [lab for lab in labels if lab.entailed_by_answer]
    bad = sum(binary(lab.label) == "UNSUPPORTED" for lab in ent)
    rate = Fraction(bad, len(ent)) if ent else None
    need = cfg.pilot.readable_min_each
    return Gate(
        k=k,
        m=m,
        readable=k >= need and m >= need,
        n_entailed=len(ent),
        n_entailed_unsupported=bad,
        a3_rate=rate,
        a3_pass=None if rate is None else rate >= Fraction(str(cfg.pilot.a3_min_rate)),
    )


# ---- item 6(b) ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Tally:
    tp: int  # flags among the k
    tn: int  # non-flags among the m
    k: int
    m: int

    @property
    def flags_supported(self) -> int:
        return self.m - self.tn


def tally(pairs: Sequence[tuple[PilotLabel, ScoreRow]], threshold: float) -> Tally:
    tp = tn = k = m = 0
    for lab, row in pairs:
        flagged = verdict(row.p_supported, threshold) == "UNSUPPORTED"  # P <= 0.5
        if binary(lab.label) == "UNSUPPORTED":
            k += 1
            tp += flagged
        else:
            m += 1
            tn += not flagged
    return Tally(tp, tn, k, m)


def balanced_accuracy(t: Tally) -> Fraction | None:
    if t.k == 0 or t.m == 0:
        return None
    return (Fraction(t.tp, t.k) + Fraction(t.tn, t.m)) / 2


def eligibility(t: Tally | None, passed_reference: bool, cfg: Config) -> list[str]:
    """Reasons a verifier is NOT eligible (empty = eligible)."""
    if t is None or not passed_reference:
        return ["did not pass its reference checks / NOT SCORED (item 8)"]
    p = cfg.pilot
    out = []
    if Fraction(t.flags_supported) > Fraction(str(p.elig_max_flag_supported)) * t.m:
        out.append(
            f"flags {t.flags_supported} of {t.m} SUPPORTED-labelled "
            f"(> {p.elig_max_flag_supported:.0%})"
        )
    if t.k >= p.elig_min_k and t.tp < p.elig_min_catch:
        out.append(
            f"k = {t.k} >= {p.elig_min_k} and flags only {t.tp} of the k (< {p.elig_min_catch})"
        )
    return out


@dataclass
class Choice:
    verifier: str | None
    provisional: bool
    why: str
    eligible: dict[str, list[str]] = field(default_factory=dict)
    ba: dict[str, Fraction | None] = field(default_factory=dict)


def choose_not_readable(
    tallies: Mapping[str, Tally | None], passed: Mapping[str, bool], cfg: Config
) -> Choice:
    """Item 6(b) as ruled 2026-10-14, on concatenated tallies."""
    default = cfg.pilot.default_verifier
    reasons = {v: eligibility(tallies.get(v), passed.get(v, False), cfg) for v in tallies}
    ba = {v: (balanced_accuracy(t) if t else None) for v, t in tallies.items()}
    ok = [v for v, r in reasons.items() if not r]
    c = Choice(None, False, "", reasons, ba)
    if not ok:
        c.why = "no eligible verifier: INCONCLUSIVE with no provisional verifier; the owner rules"
        return c
    if len(ok) == 1:
        c.verifier, c.provisional, c.why = ok[0], True, "the only eligible verifier"
        return c
    if len(ok) > 2:
        raise ValueError("item 6(b) compares two verifiers")
    a, b = ok
    ta, tb = tallies[a], tallies[b]
    if ta.k == 0 or ta.m == 0:
        c.verifier, c.provisional = default, True
        c.why = f"k = {ta.k}, m = {ta.m}: balanced accuracy undefined -> {default}"
        return c
    d = abs(ta.tp - tb.tp) + abs(ta.tn - tb.tn)
    if d <= cfg.pilot.one_claim:
        c.verifier, c.provisional = default, True
        c.why = f"|dTP| + |dTN| = {d} <= {cfg.pilot.one_claim}: within one claim -> {default}"
    elif ba[a] == ba[b]:
        c.verifier, c.provisional = default, True
        c.why = f"exact tie in balanced accuracy ({ba[a]}) -> {default}"
    else:
        win = a if ba[a] > ba[b] else b
        c.verifier, c.provisional = win, True
        c.why = f"higher balanced accuracy ({ba[win]} vs {min(ba[a], ba[b])}); |dTP| + |dTN| = {d}"
    return c


# ---- item 6(a) ----------------------------------------------------------------------------------


def d004_mode(k_concat: Fraction | None, k_pcm: Fraction | None, tie: float) -> str:
    """D-004 (status 2026-10-13): unrounded (exact); |diff| <= tie or either unreadable ->
    concatenated."""
    if k_concat is None or k_pcm is None or abs(k_concat - k_pcm) <= Fraction(str(tie)):
        return "concatenated"
    return "concatenated" if k_concat > k_pcm else "per_chunk_max"


@dataclass(frozen=True)
class Readable:
    outcome: str
    verifier: str | None
    mode: str | None
    best: Fraction | None
    why: str


def choose_readable(kappas: Mapping[tuple[str, str], Fraction | None], cfg: Config) -> Readable:
    defined = {cell: k for cell, k in kappas.items() if k is not None}
    if not defined:
        return Readable("STOP", None, None, None, "no defined binary kappa in any cell")
    best = max(defined.values())
    at_best = sorted({v for (v, _), k in defined.items() if k == best})
    if len(at_best) > 1:
        return Readable(
            "STOP",
            None,
            None,
            best,
            f"exact kappa tie at {best} between {at_best}: the owner rules",
        )
    v = at_best[0]
    mode = d004_mode(
        kappas.get((v, "concatenated")), kappas.get((v, "per_chunk_max")), cfg.eval.input_mode_tie
    )
    go, tune = Fraction(str(cfg.eval.kappa_go)), Fraction(str(cfg.eval.kappa_tune))
    if best >= go:
        return Readable(
            GO, v, mode, best, f"best binary kappa {float(best):.4f} >= {cfg.eval.kappa_go}"
        )
    if best >= tune:
        return Readable(
            GO,
            v,
            mode,
            best,
            f"best binary kappa {float(best):.4f} in [{cfg.eval.kappa_tune}, {cfg.eval.kappa_go}): "
            "GO; tune the threshold on the pilot; final kappa only on week-3 labels",
        )
    return Readable(
        NO_GO_CANDIDATE,
        v,
        mode,
        best,
        f"best binary kappa {float(best):.4f} < {cfg.eval.kappa_tune}: NO-GO CANDIDATE "
        "(never a switch); "
        "run the blinded relabel (item 6(a)); the switch needs the owner's written confirmation",
    )


def relabel_selection(pairs: Sequence[tuple[PilotLabel, ScoreRow]], cfg: Config) -> list[str]:
    """Item 6(a) / status 2026-10-14 (1): from the best-kappa cell, the 10 largest disagreements
    ranked by |binary truth - P(supported)| plus 10 random agreements, shuffled."""
    p = cfg.pilot
    thr = cfg.verifier.threshold
    dis, agree = [], []
    for lab, row in pairs:
        truth = 1.0 if binary(lab.label) == "SUPPORTED" else 0.0
        if (verdict(row.p_supported, thr) == "SUPPORTED") != (truth == 1.0):
            dis.append((-abs(truth - row.p_supported), lab.claim_id))
        else:
            agree.append(lab.claim_id)
    picked = [cid for _, cid in sorted(dis)[: p.relabel_disagreements]]
    rng = random.Random(p.relabel_seed)
    picked += rng.sample(sorted(agree), min(p.relabel_agreements, len(agree)))
    rng.shuffle(picked)
    return picked
