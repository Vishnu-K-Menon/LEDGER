"""The ONE render function (D-044 item 7): it builds the context for labelling and for scoring.

``concatenated`` = the five supplied chunk texts, in rank order, joined by a blank line, as one
document. ``per_chunk_max`` scores each chunk text alone, so a chunk is rendered as its own text.
Truncation is off: nothing is cut, ever. Each label and score row records ``context_hash``."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

SEPARATOR = "\n\n"


def render_chunk(text: str) -> str:
    """One supplied chunk as shown to the labeller and as scored under ``per_chunk_max``."""
    return text


def render_context(texts: Sequence[str]) -> str:
    """The ``concatenated`` document: chunk texts in rank order, joined by a blank line."""
    return SEPARATOR.join(render_chunk(t) for t in texts)


def context_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def documents_for(mode: str, texts: Sequence[str]) -> list[str]:
    """The documents a verifier scores for one claim under ``mode`` (D-004)."""
    if mode == "concatenated":
        return [render_context(texts)]
    if mode == "per_chunk_max":
        return [render_chunk(t) for t in texts]
    raise ValueError(f"unknown input mode {mode!r}")
