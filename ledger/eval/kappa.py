"""Kappa for the T6 pilot (D-003, D-044 item 7).

* Verifier verdicts are binary: SUPPORTED iff P(supported) > threshold (0.5; MiniCheck's own
  ``> 0.5`` rule; D-044 status 2026-10-14). Human labels are three-class.
* ``kappa_binary`` is emitted FIRST, with the fold stated: PARTIAL -> UNSUPPORTED (D-003). Then the
  three-class kappa (the verifier never emits PARTIAL) and the partial rate, flagged "not
  comparable". Kappa with PARTIAL folded the other way and the PARTIAL causes are reported and
  govern nothing (item 7).
* AUROC: P(supported) against the binary truth (Mann-Whitney, ties 1/2).
* Intervals are answer-clustered: a percentile bootstrap that resamples answers (question ids)
  with replacement; resamples where the statistic is undefined are counted and reported.
* Refuses on any FAIL row, a row count different from the labels manifest, or mismatched ids.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from ledger.eval.labels import LABELS, PilotLabel, binary
from ledger.verify.scores import ScoreRow

FOLD_NOTE = "binary kappa: PARTIAL folded into UNSUPPORTED (D-003)"
THREE_CLASS_NOTE = "three-class kappa: NOT comparable to the binary kappa (D-003)"


class KappaRefused(ValueError):
    pass


def verdict(p: float, threshold: float) -> str:
    return "SUPPORTED" if p > threshold else "UNSUPPORTED"


def cohen_kappa(
    a: Sequence[str], b: Sequence[str], cats: Sequence[str] | None = None
) -> Fraction | None:
    """Cohen's kappa, exact (a fraction: D-004's tie rule compares unrounded kappa, so no float
    noise may decide it); ``None`` when undefined (expected agreement 1: both raters constant
    and equal). One constant rater gives 0, never NaN."""
    if len(a) != len(b) or not a:
        raise ValueError("kappa needs two equal-length, non-empty sequences")
    cats = list(cats or sorted(set(a) | set(b)))
    n = len(a)
    po = Fraction(sum(x == y for x, y in zip(a, b, strict=True)), n)
    ca, cb = Counter(a), Counter(b)
    pe = sum((Fraction(ca[c], n) * Fraction(cb[c], n) for c in cats), Fraction(0))
    if pe == 1:
        return None
    return (po - pe) / (1 - pe)


def auroc(p: Sequence[float], positive: Sequence[bool]) -> float | None:
    pos = [x for x, t in zip(p, positive, strict=True) if t]
    neg = [x for x, t in zip(p, positive, strict=True) if not t]
    if not pos or not neg:
        return None
    wins = sum(1.0 if x > y else 0.5 if x == y else 0.0 for x in pos for y in neg)
    return wins / (len(pos) * len(neg))


def quantile(sorted_vals: Sequence[float], q: float) -> float:
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


@dataclass(frozen=True)
class Interval:
    lo: float | None
    hi: float | None
    resamples: int
    undefined: int
    clusters: int

    def text(self, level: float) -> str:
        if self.lo is None:
            return f"[undefined in all {self.resamples} resamples]"
        extra = f"; undefined in {self.undefined}" if self.undefined else ""
        return (
            f"[{self.lo:.3f}, {self.hi:.3f}] ({level:.0%}, answer-clustered bootstrap, "
            f"{self.clusters} answers, B={self.resamples}{extra})"
        )


def cluster_bootstrap(
    clusters: Sequence[str],
    stat: Callable[[list[int]], float | None],
    *,
    n: int,
    seed: int,
    level: float,
) -> Interval:
    """``clusters[i]`` = the answer (question id) of row i. Resample answers with replacement."""
    by_c: dict[str, list[int]] = {}
    for i, c in enumerate(clusters):
        by_c.setdefault(c, []).append(i)
    keys = sorted(by_c)
    rng = random.Random(seed)
    vals: list[float] = []
    undefined = 0
    for _ in range(n):
        idx = [i for k in rng.choices(keys, k=len(keys)) for i in by_c[k]]
        v = stat(idx)
        if v is None:
            undefined += 1
        else:
            vals.append(float(v))
    if not vals:
        return Interval(None, None, n, undefined, len(keys))
    vals.sort()
    a = (1 - level) / 2
    return Interval(quantile(vals, a), quantile(vals, 1 - a), n, undefined, len(keys))


# ---- alignment and refusals ---------------------------------------------------------------------


def align(
    labels: Sequence[PilotLabel], rows: Sequence[ScoreRow], expected_n: int
) -> list[tuple[PilotLabel, ScoreRow]]:
    """One cell's rows against the labels. Refuses on FAIL, wrong count, or mismatched ids."""
    fails = [r for r in rows if r.status == "FAIL"]
    if fails:
        raise KappaRefused(
            f"{len(fails)} FAIL row(s): "
            + "; ".join(f"{r.item_id} ({r.verifier}, {r.mode}): {r.reason}" for r in fails)
        )
    if len(rows) != expected_n or len(labels) != expected_n:
        raise KappaRefused(
            f"wrong row count: {len(rows)} scores, {len(labels)} labels, manifest n = {expected_n}"
        )
    by_id = {r.item_id: r for r in rows}
    if set(by_id) != {lab.claim_id for lab in labels} or len(by_id) != len(rows):
        raise KappaRefused("score ids do not match the labelled claim ids")
    return [(lab, by_id[lab.claim_id]) for lab in labels]


# ---- one cell ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class CellStats:
    verifier: str
    mode: str
    n: int
    kappa_binary: Fraction | None
    kappa_binary_ci: Interval
    kappa_3class: Fraction | None
    kappa_partial_to_supported: Fraction | None
    kappa_partial_to_supported_ci: Interval
    auroc: float | None
    auroc_ci: Interval


def cell_stats(
    pairs: Sequence[tuple[PilotLabel, ScoreRow]],
    *,
    threshold: float,
    n_boot: int,
    seed: int,
    level: float,
) -> CellStats:
    labs = [lab for lab, _ in pairs]
    p = [r.p_supported for _, r in pairs]
    ver = [verdict(x, threshold) for x in p]
    truth = [binary(lab.label) for lab in labs]
    truth_rev = [binary(lab.label, partial_to="SUPPORTED") for lab in labs]
    three = [lab.label for lab in labs]
    clusters = [lab.question_id for lab in labs]

    def k_of(t: Sequence[str]) -> Callable[[list[int]], float | None]:
        return lambda idx: cohen_kappa([t[i] for i in idx], [ver[i] for i in idx])

    def auc_of(idx: list[int]) -> float | None:
        return auroc([p[i] for i in idx], [truth[i] == "SUPPORTED" for i in idx])

    boot = {"n": n_boot, "seed": seed, "level": level}
    verifier, mode = pairs[0][1].verifier, pairs[0][1].mode
    all_idx = list(range(len(pairs)))
    return CellStats(
        verifier=verifier,
        mode=mode,
        n=len(pairs),
        kappa_binary=k_of(truth)(all_idx),
        kappa_binary_ci=cluster_bootstrap(clusters, k_of(truth), **boot),
        kappa_3class=cohen_kappa(three, ver, LABELS),
        kappa_partial_to_supported=k_of(truth_rev)(all_idx),
        kappa_partial_to_supported_ci=cluster_bootstrap(clusters, k_of(truth_rev), **boot),
        auroc=auc_of(all_idx),
        auroc_ci=cluster_bootstrap(clusters, auc_of, **boot),
    )


def partial_rate(labels: Sequence[PilotLabel]) -> float:
    return sum(lab.label == "PARTIAL" for lab in labels) / len(labels)


def partial_causes(labels: Sequence[PilotLabel]) -> Mapping[str, int]:
    c = Counter(e for lab in labels if lab.label == "PARTIAL" for e in lab.missing_elements)
    return dict(sorted(c.items()))
