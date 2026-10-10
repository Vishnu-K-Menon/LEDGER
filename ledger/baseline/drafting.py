"""Draft-question tooling (D-043 items 1-2): prompts and parsing for the Sonnet drafter, and the
finalizer's refusals. The drafter is claude-sonnet-5-5 (D-041, same request shape as every other
generator call); the owner checks every item; D24's different-family rule covers the 200, not
these drafts."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from ledger.baseline.request import message_params
from ledger.config import Config

DRAFT_SYSTEM = """You write evaluation questions for a retrieval-augmented QA system over U.S. government budget, economic and energy documents.

You are given ONE source chunk. Write ONE question that this chunk alone answers.

Requirements:
- The question must be self-contained: name the entity, programme, series, period and unit it needs, so that a reader with no access to the chunk understands what is asked. Never write "this table", "the chunk" or "the document".
- The answer must be a single value or short phrase that appears VERBATIM in the chunk text, character for character (same digits, separators, unit words and spelling). Do not compute, round, convert or paraphrase.
- Numeric answers: the unit and period must be recoverable from the same chunk.
- 8 to 40 words.

Reply with one JSON object and nothing else:
{"question": "...", "gold_answer": "...", "answer_type": "number" | "short_phrase"}"""  # noqa: E501

CONTROLS_SYSTEM = """You write deliberately UNANSWERABLE evaluation questions for a retrieval-augmented QA system whose corpus is the document list below. Each question must sound like a normal question about U.S. government budget, economic or energy data, but be unanswerable from the corpus because EITHER:
- control_kind "absent_entity": it asks about a programme, agency, bill, series or table that is not covered by any listed document; OR
- control_kind "out_of_range_period": it asks about a period (year, fiscal year, month) outside the dates covered by the listed documents for that topic.
Do not rely on knowing what the documents contain beyond their titles and dates. Make each question self-contained, 8 to 40 words, and different from the others.

Reply with one JSON array and nothing else: [{"question": "...", "control_kind": "absent_entity" | "out_of_range_period", "rationale": "..."}, ...]"""  # noqa: E501


def draft_params(cfg: Config, chunk: Mapping[str, Any]) -> dict[str, Any]:
    g = cfg.generator
    body = message_params(
        g.model,
        g.max_tokens,
        g.thinking,
        g.effort,
        messages=[
            {
                "role": "user",
                "content": f'<chunk id="{chunk["chunk_id"]}">\n{chunk["text"]}\n</chunk>',
            }
        ],
    )
    body["system"] = DRAFT_SYSTEM
    return body


def controls_params(cfg: Config, units: Sequence[Mapping[str, Any]], n: int) -> dict[str, Any]:
    g = cfg.generator
    listing = "\n".join(
        f"- {u['unit_id']} | {u['source']} | {u.get('date_issued')} | {u.get('title')}"
        for u in units
    )
    body = message_params(
        g.model,
        g.max_tokens,
        g.thinking,
        g.effort,
        messages=[
            {"role": "user", "content": f"Corpus documents:\n{listing}\n\nWrite {n} questions."}
        ],
    )
    body["system"] = CONTROLS_SYSTEM
    return body


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.S)


def _loads(text: str) -> Any:
    return json.loads(_FENCE.sub("", text.strip()))


def parse_draft(text: str) -> dict[str, Any]:
    obj = _loads(text)
    if not isinstance(obj, dict) or not {"question", "gold_answer", "answer_type"} <= set(obj):
        raise ValueError("draft reply lacks question / gold_answer / answer_type")
    if obj["answer_type"] not in ("number", "short_phrase"):
        raise ValueError(f"bad answer_type {obj['answer_type']!r}")
    return {k: str(obj[k]) for k in ("question", "gold_answer", "answer_type")}


def parse_controls(text: str) -> list[dict[str, str]]:
    arr = _loads(text)
    if not isinstance(arr, list):
        raise ValueError("controls reply is not a JSON array")
    out = []
    for o in arr:
        if o.get("control_kind") not in ("absent_entity", "out_of_range_period"):
            raise ValueError(f"bad control_kind {o.get('control_kind')!r}")
        out.append({k: str(o.get(k, "")) for k in ("question", "control_kind", "rationale")})
    return out


def word_count(s: str) -> int:
    return len(s.split())


def auto_checks(question: str, gold: str, chunk_text: str) -> dict[str, Any]:
    return {
        "gold_in_chunk": gold in chunk_text,
        "words": word_count(question),
        "words_ok": 8 <= word_count(question) <= 40,
    }


# ---- finalizer ---------------------------------------------------------------------------------


class FinalizeRefused(RuntimeError):
    pass


def _prefix(cands: Sequence[Mapping[str, Any]], need: int, label: str, problems: list[str]) -> list:
    """D-043 item 1: within a stratum the accepted items are the first ``need`` non-rejected
    candidates in draw order. A rejected candidate needs a logged reason (``notes``); an undecided
    one before the last accepted is refused; nothing is chosen by hand."""
    accepted: list[Mapping[str, Any]] = []
    for c in sorted(cands, key=lambda x: x["order_index"]):
        cid = c.get("candidate_id")
        if len(accepted) == need:
            if c.get("accept") is True:
                problems.append(f"{label}: {cid} accepted beyond the {need} needed")
            continue
        if c.get("accept") is True:
            accepted.append(c)
        elif c.get("accept") is False:
            if not str(c.get("notes", "")).strip():
                problems.append(f"{label}: {cid} rejected without a logged reason (notes)")
        else:
            problems.append(f"{label}: {cid} is undecided but a later candidate is needed")
    if len(accepted) < need:
        problems.append(f"{label}: {len(accepted)} accepted, need {need}")
    return accepted


def finalize(
    candidates: Sequence[Mapping[str, Any]],
    chunks_by_id: Mapping[str, Mapping[str, Any]],
    lock_ids: set[str],
    cfg: Config,
) -> list[dict[str, Any]]:
    """Owner-checked candidates -> questions_draft.jsonl (evaluation.md section 1 schema plus
    set / drafted_by / checked_by). ``set``: ``draft`` (13 table + 12 prose), ``supplement`` (one
    per source the draw supplemented), ``control_candidate`` (every accepted control; the owner
    picks ``n_controls`` of them in data/controls_accepted.json after reading their top-5).
    Refuses on any rule violation, listing all of them."""
    problems: list[str] = []
    b = cfg.baseline
    by_stratum: dict[str, list[Mapping[str, Any]]] = {}
    for c in candidates:
        by_stratum.setdefault(c["stratum"], []).append(c)
    table = _prefix(by_stratum.get("table", []), b.n_table, "table", problems)
    prose = _prefix(by_stratum.get("prose", []), b.n_prose, "prose", problems)
    supp_groups: dict[str, list[Mapping[str, Any]]] = {}
    for c in by_stratum.get("supplement", []):
        supp_groups.setdefault(c["supp_source"], []).append(c)
    supplement: list[Mapping[str, Any]] = []
    for src, cs in sorted(supp_groups.items()):
        supplement += _prefix(cs, b.supplement_per_source, f"supplement {src}", problems)
    controls = [c for c in by_stratum.get("control", []) if c.get("accept") is True]
    if len(controls) < b.n_controls:
        problems.append(f"{len(controls)} controls accepted; need at least {b.n_controls}")

    seen_tables: Counter[tuple[str, str]] = Counter()
    for c in table + prose + supplement:
        cid = c["chunk_id"]
        label = c.get("candidate_id", cid)
        if cid not in lock_ids or cid not in chunks_by_id:
            problems.append(f"{label}: gold chunk id {cid} is not in the lock")
            continue
        ch = chunks_by_id[cid]
        if c["gold_answer"] not in ch["text"]:
            problems.append(f"{label}: gold answer is not an exact substring of {cid}")
        if c["stratum"] != "prose":
            seen_tables[(ch["unit_id"], ch["item"])] += 1
    for key, n in seen_tables.items():
        if n > 1:
            problems.append(f"{n} questions from one table {key} (D-043: one per table)")
    for c in table + prose + supplement + controls:
        if not str(c.get("checked_by", "")).strip():
            problems.append(f"{c.get('candidate_id')}: checked_by is empty (owner names themself)")
    if problems:
        raise FinalizeRefused("\n".join(problems))

    def item(qid: str, c: Mapping[str, Any], qset: str) -> dict[str, Any]:
        ch = chunks_by_id[c["chunk_id"]]
        rec = {
            "question_id": qid,
            "question": c["question"],
            "gold_answer": c["gold_answer"],
            "gold_chunk_id": c["chunk_id"],
            "answer_type": c["answer_type"],
            "chunk_type": ch["chunk_type"],
            "unanswerable": False,
            "set": qset,
            "source": ch["source"],
            "unit_id": ch["unit_id"],
            "drafted_by": c["drafted_by"],
            "checked_by": c["checked_by"],
        }
        if qset == "supplement":
            rec["supp_source"] = c["supp_source"]
        return rec

    out = [item(f"q{i:03d}", c, "draft") for i, c in enumerate(table + prose, 1)]
    out += [item(f"s{i:03d}", c, "supplement") for i, c in enumerate(supplement, 1)]
    for j, c in enumerate(controls, 1):
        out.append(
            {
                "question_id": f"c{j:03d}",
                "question": c["question"],
                "gold_answer": None,
                "gold_chunk_id": None,
                "answer_type": None,
                "chunk_type": None,
                "unanswerable": True,
                "control_kind": c["control_kind"],
                "set": "control_candidate",
                "drafted_by": c["drafted_by"],
                "checked_by": c["checked_by"],
            }
        )
    return out
