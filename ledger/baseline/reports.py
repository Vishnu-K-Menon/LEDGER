# ruff: noqa: E501
"""T5 reports (D-043, D-033 status 2026-10-09). Pure functions: data in, markdown out. Every report
carries a header with the commit and input hashes (``header_block``)."""

from __future__ import annotations

import itertools
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from statistics import mean, pstdev
from typing import Any

from ledger.baseline import match
from ledger.baseline.run import RunRecord

A4_PASS = 0.98
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def header_block(title: str, meta: Mapping[str, Any]) -> str:
    lines = [f"# {title}", ""]
    for k, v in meta.items():
        lines.append(f"- {k}: `{v}`")
    return "\n".join(lines) + "\n\n" + COMPOSITION_MARKER + "\n\n"


COMPOSITION_MARKER = "<!--composition-->"


def finish(text: str, composition: str) -> str:
    """Put the composition block (by source and unit) in the header of every T5 report."""
    return text.replace(COMPOSITION_MARKER, composition.rstrip("\n"), 1)


def composition_block(
    questions: Sequence[Mapping[str, Any]],
    chunk_meta: Mapping[str, Mapping[str, Any]],
    corpus_sources: Sequence[str],
    accepted_controls: Sequence[str] | None = None,
) -> str:
    """Composition of the drafts by source and unit (D-043 item 1: reported with every draft
    result). A source with no item is reported as not exercised."""

    def tally(rows):
        out: dict[str, Counter[str]] = {}
        for q in rows:
            m = chunk_meta[q["gold_chunk_id"]]
            out.setdefault(m["source"], Counter())[m["unit_id"]] += 1
        return out

    core = tally(q for q in questions if q.get("set") == "draft")
    supp = tally(q for q in questions if q.get("set") == "supplement")
    n_ctrl = (
        len(accepted_controls)
        if accepted_controls is not None
        else sum(q.get("set") == "control_candidate" for q in questions)
    )
    lines = ["## Composition by source and unit", ""]
    for label, comp in (("25 drafts (core)", core), ("supplement (beside the 25)", supp)):
        parts = "; ".join(
            f"{s} {sum(u.values())} ({', '.join(f'{k} x{v}' for k, v in sorted(u.items()))})"
            for s, u in sorted(comp.items())
        )
        lines += [f"**{label}**: {parts or 'none'}", ""]
    not_core = [s for s in corpus_sources if s not in core]
    not_any = [s for s in not_core if s not in supp]
    lines.append(f"Sources not exercised by the 25 drafts: {', '.join(not_core) or 'none'}.")
    lines.append(
        f"Sources not exercised by drafts plus supplement: {', '.join(not_any) or 'none'}."
    )
    state = "accepted" if accepted_controls is not None else "candidates (not yet chosen)"
    lines.append(
        f"Controls: {n_ctrl} {state}; supplement results are reported separately and enter no "
        "count on the 25."
    )
    return "\n".join(lines) + "\n"


def _pct(k: int, n: int) -> str:
    return f"{k}/{n} = {k / n:.3f}" if n else "n/a"


# ---- A6 ----------------------------------------------------------------------------------------


def classify_miss(
    rec: Mapping[str, Any], chunk_meta: Mapping[str, Mapping[str, Any]], k_dense: int
) -> str:
    """Precedence (stated in the report): sibling slice > first-stage miss > reranker demotion."""
    gold = rec["gold_chunk_id"]
    g = chunk_meta[gold]
    for cid in rec["top5"]:
        m = chunk_meta[cid]
        if cid != gold and (m["unit_id"], m["item"]) == (g["unit_id"], g["item"]):
            return "sibling slice"
    d = rec["gold_rank_dense"]
    if d is None or d > k_dense:
        return "first-stage miss"
    return "reranker demotion"


def _gold_in_top5(
    rec: Mapping[str, Any],
    golds: Mapping[str, tuple[str, str]] | None,
    chunk_meta: Mapping[str, Mapping[str, Any]],
) -> str:
    if golds is None or rec["question_id"] not in golds:
        return "n/a"
    kind, gold = golds[rec["question_id"]]
    found = [
        cid
        for cid in rec["top5"]
        if match.gold_in_text(kind, gold, str(chunk_meta[cid].get("text", "")))
    ]
    return ("yes: " + ", ".join(f"`{c}`" for c in found)) if found else "no"


def a6_arm_section(
    name: str,
    header: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    chunk_meta: Mapping[str, Mapping[str, Any]],
    k_dense: int,
    golds: Mapping[str, tuple[str, str]] | None = None,
) -> str:
    """``golds``: question id -> (answer_type, gold string); used only to say, per miss, whether
    the gold string occurs in a top-5 chunk (D-043 status 2026-10-10, item 2). Recall is unchanged."""
    ans = [r for r in records if r["gold_chunk_id"] is not None]
    n = len(ans)
    hit5 = [r for r in ans if r["gold_chunk_id"] in r["top5"]]
    hit8 = [r for r in ans if r["gold_chunk_id"] in r.get("top8", [])]
    lo, hi = wilson(len(hit5), n)
    rr = [1 / r["gold_rank_rerank"] if r["gold_rank_rerank"] else 0.0 for r in ans]
    out = [
        f"## Arm `{name}`",
        "",
        f"- embed instruction: {header['embed_instruction']!r}",
        f"- rerank instruction: {header['rerank_instruction']!r}",
        f"- recall@5: **{_pct(len(hit5), n)}**, Wilson 95% interval [{lo:.2f}, {hi:.2f}]",
        f"- recall@8: {_pct(len(hit8), n)}",
        f"- MRR (rank of gold in the reranked dense top-{k_dense}; 0 if absent): {mean(rr):.3f}"
        if n
        else "- MRR: n/a",
        "",
    ]
    misses = [r for r in ans if r["gold_chunk_id"] not in r["top5"]]
    causes = Counter(classify_miss(r, chunk_meta, k_dense) for r in misses)
    out.append(
        f"Misses: {len(misses)} of {n}. By cause: "
        + (", ".join(f"{k} {v}" for k, v in sorted(causes.items())) or "none")
        + "."
    )
    if misses:
        out += [
            "",
            "| question | gold | cause | dense rank | rerank rank | gold string in a top-5 chunk |",
            "|---|---|---|---|---|---|",
        ]
        for r in misses:
            out.append(
                f"| {r['question_id']} | `{r['gold_chunk_id']}` | "
                f"{classify_miss(r, chunk_meta, k_dense)} | {r['gold_rank_dense']} | "
                f"{r['gold_rank_rerank']} | {_gold_in_top5(r, golds, chunk_meta)} |"
            )
    out.append("")
    return "\n".join(out)


def a6_controls_section(
    arms: Mapping[str, Sequence[Mapping[str, Any]]],
    questions: Sequence[Mapping[str, Any]],
    accepted: Sequence[str] | None,
) -> str:
    ctrl = [q for q in questions if q.get("set") == "control_candidate"]
    if accepted is not None:
        ctrl = [q for q in ctrl if q["question_id"] in set(accepted)]
        out = ["## Controls (the 5 accepted): top-5", ""]
    else:
        out = [
            "## Control candidates: top-5 for the owner to read (D-043 status 2026-10-10, item 2)",
            "",
            f"All {len(ctrl)} candidates were retrieved (primary arm's top-5 is the one the "
            "generator receives). Read them in file order. Reject a candidate only if a top-5 "
            "chunk states the asked quantity for the asked entity and the asked period, and "
            "record the rejecting chunk ID. The same series for another period, or the same "
            "quantity for another entity, does not reject: accept it and tag it `near_miss`. The "
            "first five not rejected are the controls; if fewer than five pass, T5 stops for a "
            "further status line (no candidate is drafted or picked by hand). Write all candidates "
            "with decision, reason and tag, and the five ids, to data/controls_accepted.json.",
            "",
        ]
    for q in ctrl:
        out.append(f"### {q['question_id']} ({q.get('control_kind')})  {q['question']}")
        for name, recs in arms.items():
            r = next(x for x in recs if x["question_id"] == q["question_id"])
            out.append(f"- {name}: " + ", ".join(f"`{c}`" for c in r["top5"]))
        out.append("")
    return "\n".join(out)


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact two-sided interval, by bisection on the binomial tail (no SciPy dependency)."""
    if n == 0:
        return (0.0, 1.0)

    def tail_ge(p: float) -> float:  # P(X >= k | p)
        return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))

    def tail_le(p: float) -> float:  # P(X <= k | p)
        return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(0, k + 1))

    def solve(f, target: float, increasing: bool) -> float:
        lo, hi = 0.0, 1.0
        for _ in range(100):
            mid = (lo + hi) / 2
            if (f(mid) < target) == increasing:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    lower = 0.0 if k == 0 else solve(tail_ge, alpha / 2, True)
    upper = 1.0 if k == n else solve(tail_le, alpha / 2, False)
    return (lower, upper)


def controls_abstention_report(
    meta: Mapping[str, Any],
    runs: Sequence[RunRecord],
    questions: Sequence[Mapping[str, Any]],
    controls: Mapping[str, Any],
    baseline_run: int = 1,
) -> str:
    """Abstention on the accepted controls, run 1 (D-043 status 2026-10-10, item 2): k of n with
    an exact interval, by control_kind and by tag. A check for gross failure, not a rate. Nothing
    gates on it (the config's abstention floor is not read here)."""
    qmap = {q["question_id"]: q for q in questions}
    tags = {
        c["id"]: c.get("tag") or "none"
        for c in controls.get("candidates", [])
        if isinstance(c, Mapping) and "id" in c
    }
    ids = set(controls["question_ids"])
    rows = [r for r in runs if r.run == baseline_run and r.question_id in ids]

    def line(label: str, sel: Sequence[RunRecord]) -> str:
        k = sum(1 for r in sel if match.usable(r) and r.answer is not None and r.answer.abstained)
        bad = sum(1 for r in sel if not match.usable(r))
        lo, hi = clopper_pearson(k, len(sel))
        return f"| {label} | {k} of {len(sel)} | [{lo:.2f}, {hi:.2f}] | {bad} |"

    body = header_block(f"T5 controls: abstention, run {baseline_run}", meta)
    body += (
        "A check for gross failure, **not a rate** (5 of 5 has a 95 % lower bound of 0.48). "
        "k = runs that returned a valid abstention; n = all run-1 requests for the accepted "
        "controls (an invalid run stays in n and is counted in the last column). Exact "
        "(Clopper-Pearson) 95 % interval. Nothing gates on this number.\n\n"
        "| group | abstained | 95 % interval | invalid |\n|---|---|---|---|\n"
    )
    body += line("all accepted controls", rows) + "\n"
    for kind in sorted({qmap[r.question_id].get("control_kind") or "?" for r in rows}):
        sel = [r for r in rows if (qmap[r.question_id].get("control_kind") or "?") == kind]
        body += line(f"kind: {kind}", sel) + "\n"
    for tag in sorted({tags.get(r.question_id, "none") for r in rows}):
        sel = [r for r in rows if tags.get(r.question_id, "none") == tag]
        body += line(f"tag: {tag}", sel) + "\n"
    body += "\n### Per control\n\n"
    for r in rows:
        status = (
            "invalid"
            if not match.usable(r)
            else ("abstained" if r.answer and r.answer.abstained else "ANSWERED")
        )
        body += (
            f"- {r.question_id} ({qmap[r.question_id].get('control_kind')}, tag "
            f"{tags.get(r.question_id, 'none')}): {status}\n"
        )
    return body


def a6_supplement_section(
    arms: Mapping[str, Sequence[Mapping[str, Any]]],
    questions: Sequence[Mapping[str, Any]],
    chunk_meta: Mapping[str, Mapping[str, Any]],
) -> str:
    sup = [q for q in questions if q.get("set") == "supplement"]
    out = [
        "## Supplement (reported separately; in no count above)",
        "",
        "| question | source | unit | arm | gold in top-5 | dense rank | rerank rank |",
        "|---|---|---|---|---|---|---|",
    ]
    for q in sup:
        m = chunk_meta[q["gold_chunk_id"]]
        for name, recs in arms.items():
            r = next(x for x in recs if x["question_id"] == q["question_id"])
            out.append(
                f"| {q['question_id']} | {m['source']} | {m['unit_id']} | {name} | "
                f"{q['gold_chunk_id'] in r['top5']} | {r['gold_rank_dense']} | "
                f"{r['gold_rank_rerank']} |"
            )
    return "\n".join(out) + "\n"


def a6_report(
    meta: Mapping[str, Any],
    arms: Mapping[str, tuple[Mapping[str, Any], Sequence[Mapping[str, Any]]]],
    questions: Sequence[Mapping[str, Any]],
    chunk_meta: Mapping[str, Mapping[str, Any]],
    k_dense: int,
    accepted_controls: Sequence[str] | None = None,
) -> str:
    core_ids = {q["question_id"] for q in questions if q.get("set", "draft") == "draft"}
    golds = {
        q["question_id"]: (q.get("answer_type") or "", q["gold_answer"])
        for q in questions
        if q.get("gold_answer")
    }
    body = header_block("T5 A6: retrieval on the draft questions", meta)
    body += (
        "Descriptive only (D-033 status 2026-10-09): recall@5 with its Wilson interval, MRR and the "
        "cause of every miss, on the 25 drafts. Cause precedence: sibling slice (another slice of "
        "the gold table in the top-5) > first-stage miss (gold not in dense top-"
        f"{k_dense}) > reranker demotion. Hybrid BM25 is built at T5 only if recall@5 < 0.75 on "
        "the drafts (7 or more misses of 25); the `card` arm decides nothing (D-042).\n\n"
    )
    for name, (header, recs) in arms.items():
        core = [r for r in recs if r["question_id"] in core_ids]
        body += a6_arm_section(name, header, core, chunk_meta, k_dense, golds) + "\n"
    all_arms = {k: v[1] for k, v in arms.items()}
    body += a6_supplement_section(all_arms, questions, chunk_meta) + "\n"
    body += a6_controls_section(all_arms, questions, accepted_controls)
    return body


# ---- A4 ----------------------------------------------------------------------------------------


def normal_stop(output_mode: str) -> str:
    return "tool_use" if output_mode == "strict_tool" else "end_turn"


def a4_counts(
    runs: Sequence[RunRecord],
    supplied: Mapping[str, Sequence[str]],
    output_mode: str,
) -> dict[str, Any]:
    stop_ok, valid, cited_ok = [], [], []
    for r in runs:
        stop_ok.append(r.stop_reason == normal_stop(output_mode))
        valid.append(r.answer is not None)
        cited_ok.append(
            r.answer is not None and set(r.answer.cited_ids()) <= set(supplied[r.question_id])
        )
    n = len(runs)
    return {
        "n": n,
        "stop": sum(stop_ok),
        "valid": sum(valid),
        "cited": sum(cited_ok),
        "failures": [
            (r.run, r.question_id, r.result_type, r.stop_reason, r.error or "", not c)
            for r, s, v, c in zip(runs, stop_ok, valid, cited_ok, strict=True)
            if not (s and v and c)
        ],
        "per": list(zip(stop_ok, valid, cited_ok, strict=True)),
    }


def a4_report(
    meta: Mapping[str, Any],
    runs: Sequence[RunRecord],
    supplied: Mapping[str, Sequence[str]],
    output_mode: str,
) -> str:
    c = a4_counts(runs, supplied, output_mode)
    n = c["n"]
    body = header_block("T5 A4: output-mode validity", meta)
    body += (
        f"Output mode: `{output_mode}`. Counted over all {n} submitted requests (D-043 item 4); "
        f"a request with no result counts as a failure. Pass: at least {A4_PASS:.0%} on each count.\n\n"
        "| count | passes | rate | verdict |\n|---|---|---|---|\n"
    )
    for label, k in (
        (f"stop_reason is `{normal_stop(output_mode)}`", c["stop"]),
        ("answer passes pydantic validation", c["valid"]),
        ("every cited chunk ID is among the five supplied", c["cited"]),
    ):
        body += f"| {label} | {k}/{n} | {k / n:.3f} | {'PASS' if k / n >= A4_PASS else 'FAIL'} |\n"
    body += f"\n## Failures ({len(c['failures'])})\n\n"
    if not c["failures"]:
        body += "None.\n"
    else:
        body += "| run | question | result | stop_reason | detail |\n|---|---|---|---|---|\n"
        for run, qid, rtype, stop, err, _ in c["failures"]:
            body += f"| {run} | {qid} | {rtype} | {stop} | {err[:160].replace('|', '/')} |\n"
    return body


# ---- variance (plan.md:41) ---------------------------------------------------------------------


def _by_question(runs: Sequence[RunRecord]) -> dict[str, list[RunRecord]]:
    out: dict[str, list[RunRecord]] = {}
    for r in sorted(runs, key=lambda x: (x.question_id, x.run)):
        out.setdefault(r.question_id, []).append(r)
    return out


def variance_report(
    meta: Mapping[str, Any],
    runs: Sequence[RunRecord],
    questions: Sequence[Mapping[str, Any]],
    supplied_texts: Mapping[str, Sequence[str]] | None = None,
) -> str:
    """D-043 status 2026-10-10 (answer matching). ``supplied_texts``: question id -> the texts of
    the five chunks the generator was given (``results/t5/contexts.jsonl``)."""
    qmap = {q["question_id"]: q for q in questions}
    by_q = _by_question(runs)
    ans_q = [q for q in by_q if not qmap[q].get("unanswerable")]
    num_q = [q for q in ans_q if qmap[q].get("answer_type") == "number"]
    phr_q = [q for q in ans_q if qmap[q].get("answer_type") == "short_phrase"]

    # (b) numeric items: every run stays in the denominator (items x runs)
    num_runs = {
        q: [(r, match.classify_run("number", qmap[q]["gold_answer"], r)) for r in by_q[q]]
        for q in num_q
    }
    flat = [m for rs in num_runs.values() for _, m in rs]
    sm = match.summarize(flat)
    per_run: dict[int, Counter[str]] = {}
    for rs in num_runs.values():
        for r, m in rs:
            per_run.setdefault(r.run, Counter())[m.status] += 1
    misses = [
        (q, r, qmap[q]["gold_answer"], match.answer_text(r))
        for q, rs in num_runs.items()
        for r, m in rs
        if m.status == match.MISS
    ]
    # (d) short_phrase items: lexical containment only
    phr_flat = [
        match.classify_run("short_phrase", qmap[q]["gold_answer"], r)
        for q in phr_q
        for r in by_q[q]
    ]
    pm = match.summarize(phr_flat)
    # (e) digit-level disagreement: the set of numeric tokens differs between runs of one question
    digit_dis, differing, absent = [], {}, {}
    for q in ans_q:
        usable_runs = [r for r in by_q[q] if r.answer]
        sets = [frozenset(NUM.findall(match.answer_text(r))) for r in usable_runs]
        if len(sets) > 1 and len(set(sets)) > 1:
            digit_dis.append(q)
            differing[q] = match.differing_tokens(sets)
            if supplied_texts is not None and q in supplied_texts:
                absent[q] = match.tokens_absent_from(differing[q], supplied_texts[q])
    # abstention consistency
    abst_cons = 0
    for rs in by_q.values():
        flags = {bool(r.answer.abstained) for r in rs if r.answer}
        abst_cons += len(flags) <= 1
    # citation-set stability: mean pairwise Jaccard
    jac, identical = [], 0
    for rs in by_q.values():
        sets = [set(r.answer.cited_ids()) for r in rs if r.answer]
        pairs = list(itertools.combinations(sets, 2))
        if not pairs:
            continue
        vals = [len(a & b) / len(a | b) if (a | b) else 1.0 for a, b in pairs]
        jac.append(mean(vals))
        identical += all(v == 1.0 for v in vals)
    # answer-token spread
    spreads, allout = [], []
    for rs in by_q.values():
        toks = [
            r.usage.get("output_tokens") for r in rs if r.usage.get("output_tokens") is not None
        ]
        if toks:
            spreads.append(max(toks) - min(toks))
            allout += toks
    body = header_block("T5 variance probe (plan.md:41)", meta)
    body += (
        "Same prompt, repeat runs at default sampling (D-019). **This does not decide the seed "
        "count**: that waits for the first run with an unsupported-claim rate (T9/T11).\n\n"
    )
    n_runs = max((len(v) for v in num_runs.values()), default=0)
    body += (
        "## Answer match (D-043 status 2026-10-10)\n\n"
        f"Numeric items ({len(num_q)}) x runs = {len(flat)} runs, all in the denominator. "
        "Normalisation: whitespace runs to one space; U+2212, U+2013 and ASCII `-` directly before a "
        "digit to one minus sign; nothing else. Correct = the gold occurs in the answer text and "
        "is not part of a longer number. Abstained and invalid runs (no usable answer: failed "
        "validation, stop_reason other than end_turn, errored/expired/canceled/missing) are counted "
        "as such and not matched.\n\n"
        f"- hits {sm['hit']}, misses {sm['miss']}, abstained {sm['abstained']}, invalid "
        f"{sm['invalid']} (sum {sm['hit'] + sm['miss'] + sm['abstained'] + sm['invalid']} of "
        f"{len(flat)}); hit rate {_pct(sm['hit'], len(flat))}\n"
        f"- hits that needed the minus mapping: {sm['needed_minus']}\n"
        + "".join(
            f"- run {r}: hits {c['hit']}, misses {c['miss']}, abstained {c['abstained']}, "
            f"invalid {c['invalid']} (of {len(num_q)})\n"
            for r, c in sorted(per_run.items())
        )
        + "- **Not checked at T5:** whether the matched number is attached to the right period, "
        "entity or unit.\n"
    )
    if not flat:
        body += f"- no numeric items (n_runs {n_runs})\n"
    body += "\n### Misses (gold and answer text)\n\n"
    if misses:
        for q, r, gold, text in misses:
            body += f"- {q} run {r.run}: gold `{gold}`; answer: {text!r}\n"
    else:
        body += "None.\n"
    body += (
        f"\n### short_phrase items ({len(phr_q)}): lexical containment, NOT correctness\n\n"
        "Not scored at T5: correctness waits for the D-007 judge (evaluation.md section 3). "
        "Reported only: gold phrase present after whitespace collapse and case-folding, with the "
        "same longer-number guard.\n\n"
        f"- contained {pm['contained']}, not contained {pm['not_contained']}, abstained "
        f"{pm['abstained']}, invalid {pm['invalid']} (sum "
        f"{pm['contained'] + pm['not_contained'] + pm['abstained'] + pm['invalid']} of "
        f"{len(phr_flat)})\n\n"
        "### Other probes\n\n"
    )
    body += (
        f"- **digit-level disagreement: {len(digit_dis)} of {len(ans_q)} answerable questions**"
        " (runs cite different digit strings)"
        + (f": {', '.join(digit_dis)}" if digit_dis else "")
        + "\n"
    )
    for q in digit_dis:
        body += f"  - {q}: differing tokens {sorted(differing[q])}\n"
    if supplied_texts is None:
        body += "- differing tokens in none of the supplied chunk texts: n/a (contexts missing)\n"
    else:
        n_abs = sum(len(v) for v in absent.values())
        body += (
            f"- **differing tokens that occur in none of the run's five supplied chunk texts: "
            f"{n_abs}** (this line, not the one above, is the D12/D14 reading; scale-word and "
            "period swaps between runs are not measured here)"
            + "".join(f"\n  - {q}: {sorted(v)}" for q, v in absent.items() if v)
            + "\n"
        )
    body += f"- abstention consistency: {_pct(abst_cons, len(by_q))} questions with the same abstention decision in every run\n"
    body += (
        f"- citation-set stability: mean pairwise Jaccard {mean(jac):.3f}; identical set in every run for {_pct(identical, len(jac))}\n"
        if jac
        else "- citation-set stability: n/a\n"
    )
    body += (
        f"- answer-token spread: mean max-min output tokens per question {mean(spreads):.1f}, "
        f"largest {max(spreads)}; overall output tokens mean {mean(allout):.1f}, sd {pstdev(allout):.1f}\n"
        if spreads
        else "- answer-token spread: n/a\n"
    )
    return body


# ---- A7 ----------------------------------------------------------------------------------------


def a7_report(
    meta: Mapping[str, Any],
    runs: Sequence[RunRecord],
    matrix: Mapping[str, Any],
    prices: Mapping[str, float],
    n_questions: int,
    gate_usd: float = 120.0,
) -> str:
    ok = [r for r in runs if r.result_type == "succeeded"]
    ins = [r.usage.get("input_tokens", 0) or 0 for r in ok]
    outs = [r.usage.get("output_tokens", 0) or 0 for r in ok]
    thinks = [r.usage.get("thinking_tokens") or 0 for r in ok]
    b_in, b_out = mean(ins), mean(outs)
    seeds = len(matrix["seeds"])
    cells = matrix["cells"]
    rewrite = sum(c["arm"] == "rewrite" for c in cells)
    rr_iters = sum(c.get("max_iter", 0) for c in cells if c["arm"] == "re_retrieve")
    claimify = any(c["decomposition"] == "claimify" for c in cells)
    q = n_questions

    def usd(calls: float) -> float:
        return calls * (b_in * prices["batch_input"] + b_out * prices["batch_output"]) / 1e6

    gen_calls = (
        seeds * q
    )  # generation is shared within a seed across arms (evaluation.md section 5)
    dec_calls = seeds * q if claimify else 0
    rew_calls = rewrite * seeds * q
    rr_calls = rr_iters * seeds * q
    total_calls = gen_calls + dec_calls + rew_calls + rr_calls
    body = header_block("T5 A7: cost projection from measured tokens", meta)
    body += (
        f"## Measured ({len(ok)} succeeded generation requests)\n\n"
        f"- input tokens per request: mean {b_in:.0f}, max {max(ins)}\n"
        f"- output tokens per request: mean {b_out:.0f}, max {max(outs)}"
        f" (thinking tokens mean {mean(thinks):.1f})\n"
        f"- Batch prices from config: input ${prices['batch_input']}/MTok, output ${prices['batch_output']}/MTok\n\n"
        "## Projection (upper-bound style: every non-generation LLM call is priced as one baseline "
        "generation call)\n\n"
        "```\ncost = calls x (B_in x p_in + B_out x p_out) / 1e6\n"
        "calls = seeds x Q                          generation, shared across arms within a seed\n"
        "      + seeds x Q  [if any claimify cell]  decomposition\n"
        "      + n_rewrite_cells x seeds x Q        rewrite (every answer assumed rewritten)\n"
        "      + sum(max_iter over re_retrieve cells) x seeds x Q   re-retrieval iterations\n```\n\n"
        f"Inputs read from `experiments/matrix.yaml`: seeds = {matrix['seeds']} ({seeds}), "
        f"{len(cells)} cells, rewrite cells = {rewrite}, re_retrieve iterations = {rr_iters}; "
        f"Q = {q} (150 + 20 controls).\n\n"
        "| part | calls | USD | basis |\n|---|---|---|---|\n"
        f"| generation | {gen_calls} | {usd(gen_calls):.2f} | B_in, B_out measured; call count from config |\n"
        f"| decomposition | {dec_calls} | {usd(dec_calls):.2f} | ASSUMED same tokens as a generation call |\n"
        f"| rewrite | {rew_calls} | {usd(rew_calls):.2f} | ASSUMED same tokens; every answer rewritten |\n"
        f"| re-retrieval | {rr_calls} | {usd(rr_calls):.2f} | ASSUMED same tokens; max_iter used in full |\n"
        f"| **total** | {total_calls} | **{usd(total_calls):.2f}** | gate: <= ${gate_usd:.0f} |\n\n"
        f"Verdict against the gate: {'WITHIN' if usd(total_calls) <= gate_usd else 'OVER'}. "
        "Measured: the generation tokens and the prices. Assumed: everything in the decomposition, "
        "rewrite and re-retrieval rows (their prompts do not exist yet; re-retrieval contexts grow "
        "up to 12 chunks, D17, which this under-counts). Verifier and judge run locally and cost "
        "nothing in API dollars.\n"
    )
    return body


# ---- claim yield -------------------------------------------------------------------------------


def claim_yield_report(
    meta: Mapping[str, Any],
    runs: Sequence[RunRecord],
    questions: Sequence[Mapping[str, Any]],
    baseline_run: int = 1,
) -> str:
    qmap = {q["question_id"]: q for q in questions}
    rows = []
    for r in runs:
        if r.run != baseline_run or r.answer is None or r.answer.abstained:
            continue
        kind = qmap[r.question_id].get("chunk_type") or "?"
        sents = len(r.answer.sentences)
        cites = len(r.answer.cited_ids())
        nums = sum(len(NUM.findall(s.text)) for s in r.answer.sentences)
        rows.append((r.question_id, kind, sents, cites, nums))
    body = header_block(f"T5 claim yield (run {baseline_run}, the baseline of record)", meta)
    body += (
        "Definitions: *sentences* = answer sentences; *citations* = (sentence, chunk ID) pairs; "
        "*numbers* = numeric tokens in the answer text (a proxy for atomic facts). The real claim "
        "count comes from decomposition at T6; T6 needs about 125 claims from 25 answers "
        "(evaluation.md:67).\n\n"
        "| kind | answers | sentences (mean) | citations (mean) | numbers (mean) |\n"
        "|---|---|---|---|---|\n"
    )
    for kind in ("table", "prose"):
        sel = [r for r in rows if r[1] == kind]
        if sel:
            body += (
                f"| {kind} | {len(sel)} | {mean(r[2] for r in sel):.2f} | "
                f"{mean(r[3] for r in sel):.2f} | {mean(r[4] for r in sel):.2f} |\n"
            )
    if rows:
        body += (
            f"\nAll non-abstaining answers: {len(rows)}; sentences {sum(r[2] for r in rows)}, "
            f"citations {sum(r[3] for r in rows)}, numbers {sum(r[4] for r in rows)}. "
            f"Sentences per answer projected to 25 answers: {mean(r[2] for r in rows) * 25:.0f} "
            "(a floor for the claim count, since decomposition splits sentences).\n"
        )
    body += "\n| question | kind | sentences | citations | numbers |\n|---|---|---|---|---|\n"
    for r in rows:
        body += f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |\n"
    return body


# ---- supplement (reported separately from every count on the 25) -------------------------------


def supplement_report(
    meta: Mapping[str, Any],
    runs: Sequence[RunRecord],
    questions: Sequence[Mapping[str, Any]],
    supplied: Mapping[str, Sequence[str]],
    output_mode: str,
) -> str:
    """Per supplement item: the three runs' validity and answers. No rate here enters any number on
    the 25 drafts (D-043 item 1, coverage supplement)."""
    qmap = {q["question_id"]: q for q in questions if q.get("set") == "supplement"}
    body = header_block("T5 supplement items (reported separately)", meta)
    body += (
        "Coverage supplement (D-043 item 1): answered and reported beside the 25; no count, rate "
        "or kappa on the 25 includes them.\n\n"
    )
    c = a4_counts([r for r in runs if r.question_id in qmap], supplied, output_mode)
    body += (
        f"Validity over {c['n']} supplement requests: stop `{normal_stop(output_mode)}` "
        f"{c['stop']}/{c['n']}, pydantic {c['valid']}/{c['n']}, citations among the five supplied "
        f"{c['cited']}/{c['n']}.\n\n"
    )
    body += "| question | source | run | gold cited | answer |\n|---|---|---|---|---|\n"
    for r in sorted(
        (r for r in runs if r.question_id in qmap), key=lambda x: (x.question_id, x.run)
    ):
        q = qmap[r.question_id]
        cited = q["gold_chunk_id"] in r.answer.cited_ids() if r.answer else False
        text = match.answer_text(r)[:140].replace("|", "/") or (r.error or "")
        body += f"| {r.question_id} | {q.get('source')} | {r.run} | {cited} | {text} |\n"
    return body
