"""T6 numeric tokens for the decomposer's number guard (D-044 item 2; status 2026-10-14 (5)).

Claim and answer are tokenised the same way: numeric tokens ``\\d+(?:[.,]\\d+)*`` on
``match.normalize_numeric`` text - the D-043 status 2026-10-11 rule ("," or "." is part of a
numeric token only when a digit follows it) - and a "-" directly before a token is a sign only
when the character before it is not a letter or digit (so the hyphens in 097-0810-0-1-051 and
B-19 are not signs). Every claim token must be in the answer's token set; a sign or digit
difference drops the claim.

``ledger/baseline/reports.py``'s ``NUM`` is NOT used and NOT changed: T5's reports are reproduced
from it and D-043 status 2026-10-11 keeps the T5 numbers as committed."""

from __future__ import annotations

import re

from ledger.baseline.match import normalize_numeric

NUM_T6 = re.compile(r"\d+(?:[.,]\d+)*")


def numeric_tokens(text: str) -> list[str]:
    t = normalize_numeric(text)
    out = []
    for m in NUM_T6.finditer(t):
        i = m.start()
        sign = i > 0 and t[i - 1] == "-" and not (i > 1 and t[i - 2].isalnum())
        out.append(("-" if sign else "") + m.group())
    return out


def missing_numbers(claim: str, answer: str) -> list[str]:
    """Claim tokens absent from the answer's token set (empty = the guard passes)."""
    have = set(numeric_tokens(answer))
    return [tok for tok in numeric_tokens(claim) if tok not in have]
