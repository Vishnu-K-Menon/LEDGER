"""Answer-vs-gold matching for T5 (D-043 status 2026-10-10, answer matching). One place: every
comparison of a model answer with a gold string goes through ``classify_run``.

Rules as logged: a run that abstains or has no usable answer is counted as such and never matched;
numeric items are matched by exact text after a fixed normalisation and a longer-number guard;
short_phrase items get lexical containment only, which is not correctness (D-007 judge, later).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ledger.baseline.run import RunRecord

_WS = re.compile(r"\s+")
_MINUS_BEFORE_DIGIT = re.compile("[−–-](?=\\d)")
NORMAL_STOP = "end_turn"  # answer-matching "usable answer" (A4 keeps its own mode-aware counts)

HIT, MISS, ABSTAINED, INVALID = "hit", "miss", "abstained", "invalid"
CONTAINED, NOT_CONTAINED = "contained", "not_contained"


def collapse(s: str) -> str:
    return _WS.sub(" ", s)


def normalize_numeric(s: str) -> str:
    """Whitespace runs -> one space; U+2212, U+2013 and ASCII '-' directly before a digit -> one
    ASCII minus sign. Nothing else (no NFKC; commas, decimals, '$', scale words stay as printed)."""
    return _MINUS_BEFORE_DIGIT.sub("-", collapse(s))


def _passes_guard(text: str, start: int, end: int) -> bool:
    """The occurrence text[start:end] is not part of a longer number."""
    if start > 0:
        b = text[start - 1]
        if b.isdigit() or b == "-":
            return False
        if b in ".," and start > 1 and text[start - 2].isdigit():
            return False
    if end < len(text):
        a = text[end]
        if a.isdigit():
            return False
        if a in ".," and end + 1 < len(text) and text[end + 1].isdigit():
            return False
    return True


def occurs(gold: str, text: str) -> bool:
    """``gold`` occurs in ``text`` at least once, not as part of a longer number."""
    if not gold:
        return False
    i = text.find(gold)
    while i != -1:
        if _passes_guard(text, i, i + len(gold)):
            return True
        i = text.find(gold, i + 1)
    return False


def numeric_match(gold: str, answer_text: str) -> tuple[bool, bool]:
    """(hit, needed_minus_mapping). ``needed_minus_mapping`` is true when the hit exists only
    because of the minus-sign mapping (whitespace collapse alone would not have matched)."""
    hit = occurs(normalize_numeric(gold), normalize_numeric(answer_text))
    if not hit:
        return False, False
    return True, not occurs(collapse(gold), collapse(answer_text))


def lexical_containment(gold: str, answer_text: str) -> bool:
    """Whitespace collapse and case-folding, same longer-number guard. NOT correctness."""
    return occurs(collapse(gold).casefold(), collapse(answer_text).casefold())


def gold_in_text(answer_type: str, gold: str, text: str) -> bool:
    """Does the gold string occur in ``text`` (a chunk), with the same guard and normalisation as
    the answer comparison? Used by the gold guard and the A6 per-miss column."""
    if answer_type == "number":
        return numeric_match(gold, text)[0]
    return lexical_containment(gold, text)


def answer_text(r: RunRecord) -> str:
    return " ".join(s.text for s in r.answer.sentences) if r.answer else ""


def usable(r: RunRecord) -> bool:
    """A usable answer: succeeded, stop_reason end_turn, passes validation."""
    return r.result_type == "succeeded" and r.stop_reason == NORMAL_STOP and r.answer is not None


@dataclass(frozen=True)
class RunMatch:
    status: str  # hit | miss | abstained | invalid  (number items)
    #            contained | not_contained | abstained | invalid  (short_phrase items)
    needed_minus: bool = False


def classify_run(answer_type: str, gold: str, r: RunRecord) -> RunMatch:
    """(a) invalid and abstained runs are counted as such and never matched."""
    if not usable(r):
        return RunMatch(INVALID)
    assert r.answer is not None
    if r.answer.abstained:
        return RunMatch(ABSTAINED)
    text = answer_text(r)
    if answer_type == "number":
        hit, minus = numeric_match(gold, text)
        return RunMatch(HIT if hit else MISS, minus)
    return RunMatch(CONTAINED if lexical_containment(gold, text) else NOT_CONTAINED)


def differing_tokens(token_sets: Sequence[frozenset[str]]) -> frozenset[str]:
    """Tokens present in some runs of a question but not in all of them."""
    if len(token_sets) < 2:
        return frozenset()
    union = frozenset().union(*token_sets)
    common = frozenset.intersection(*token_sets)
    return union - common


def tokens_absent_from(tokens: frozenset[str], supplied_texts: Sequence[str]) -> frozenset[str]:
    """Differing tokens that occur in none of the supplied chunk texts (the D12/D14 reading).
    "Occur" is the answer comparison's: ``occurs`` on normalised text, longer-number guard."""
    normalized = [normalize_numeric(text) for text in supplied_texts]
    return frozenset(
        t for t in tokens if not any(occurs(normalize_numeric(t), text) for text in normalized)
    )


def summarize(statuses: Sequence[RunMatch]) -> dict[str, Any]:
    out = {k: 0 for k in (HIT, MISS, ABSTAINED, INVALID, CONTAINED, NOT_CONTAINED)}
    for m in statuses:
        out[m.status] += 1
    out["needed_minus"] = sum(m.needed_minus for m in statuses if m.status == HIT)
    return out
