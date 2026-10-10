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


def a6_arm_section(
    name: str,
    header: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    chunk_meta: Mapping[str, Mapping[str, Any]],
    k_dense: int,
) -> str:
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
            "| question | gold | cause | dense rank | rerank rank |",
            "|---|---|---|---|---|",
        ]
        for r in misses:
            out.append(
                f"| {r['question_id']} | `{r['gold_chunk_id']}` | "
                f"{classify_miss(r, chunk_meta, k_dense)} | {r['gold_rank_dense']} | "
                f"{r['gold_rank_rerank']} |"
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
            "## Control candidates: top-5 for the owner to read (D-043 item 2)",
            "",
            f"All {len(ctrl)} candidates were retrieved. Accept 5 after reading their top-5 and "
            "finding no answer in them; write the ids to data/controls_accepted.json. A rejection "
            "needs no second retrieval.",
            "",
        ]
    for q in ctrl:
        out.append(f"### {q['question_id']} ({q.get('control_kind')})  {q['question']}")
        for name, recs in arms.items():
            r = next(x for x in recs if x["question_id"] == q["question_id"])
            out.append(f"- {name}: " + ", ".join(f"`{c}`" for c in r["top5"]))
        out.append("")
    return "\n".join(out)


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
        body += a6_arm_section(name, header, core, chunk_meta, k_dense) + "\n"
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


def _answer_text(r: RunRecord) -> str:
    return " ".join(s.text for s in r.answer.sentences) if r.answer else ""


def _by_question(runs: Sequence[RunRecord]) -> dict[str, list[RunRecord]]:
    out: dict[str, list[RunRecord]] = {}
    for r in sorted(runs, key=lambda x: (x.question_id, x.run)):
        out.setdefault(r.question_id, []).append(r)
    return out


def variance_report(
    meta: Mapping[str, Any], runs: Sequence[RunRecord], questions: Sequence[Mapping[str, Any]]
) -> str:
    qmap = {q["question_id"]: q for q in questions}
    by_q = _by_question(runs)
    ans_q = [q for q in by_q if not qmap[q].get("unanswerable")]

    # numeric exact match vs gold: gold string appears in the answer text
    num_q = [q for q in ans_q if qmap[q].get("answer_type") == "number"]
    per_run_hit: dict[int, int] = Counter()
    unanimous = 0
    for q in num_q:
        hits = [qmap[q]["gold_answer"] in _answer_text(r) for r in by_q[q]]
        unanimous += len(set(hits)) == 1
        for r, h in zip(by_q[q], hits, strict=True):
            per_run_hit[r.run] += h
    # digit-level disagreement: the set of numeric tokens differs between runs of one question
    digit_dis = []
    for q in ans_q:
        sets = [frozenset(NUM.findall(_answer_text(r))) for r in by_q[q] if r.answer]
        if len(sets) > 1 and len(set(sets)) > 1:
            digit_dis.append(q)
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
    body += f"- numeric exact-match agreement vs gold ({len(num_q)} numeric questions): "
    body += (
        ", ".join(f"run {r}: {_pct(per_run_hit[r], len(num_q))}" for r in sorted(per_run_hit))
        + f"; identical outcome in all runs: {_pct(unanimous, len(num_q))}\n"
        if num_q
        else "n/a\n"
    )
    body += (
        f"- **digit-level disagreement: {len(digit_dis)} of {len(ans_q)} answerable questions**"
        f" (runs cite different digit strings; non-zero is a D12/D14 problem, not a seed question)"
        + (f": {', '.join(digit_dis)}" if digit_dis else "")
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
        text = _answer_text(r)[:140].replace("|", "/") or (r.error or "")
        body += f"| {r.question_id} | {q.get('source')} | {r.run} | {cited} | {text} |\n"
    return body
