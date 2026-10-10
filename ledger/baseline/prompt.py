"""D12 strict grounding stance: the system prompt and the context layout (D17: top-5 chunks,
each labelled with its chunk ID; no chain-of-thought requested)."""

from __future__ import annotations

from collections.abc import Sequence

from ledger.baseline.schema import TOOL_NAME

SYSTEM = """You answer questions about U.S. government budget, economic and energy documents using ONLY the source chunks supplied in the user message. Each chunk is labelled with its chunk ID.

Rules:
1. Use only information stated in the chunks. Do not use outside knowledge, even if you are sure it is true.
2. Cite every sentence of your answer with the ID of each chunk that supports it. Copy chunk IDs exactly as printed.
3. If the chunks do not contain the answer, abstain: set abstained to true, leave sentences empty, and give a one-sentence abstention_reason. Do not guess and do not answer partially from memory.
4. Copy numbers verbatim, with the unit and period exactly as printed in the chunk (for example "$1,022 billion in fiscal year 2026"). Do not round, convert units, or compute new figures.
5. Keep the answer short: one to three sentences."""  # noqa: E501

_TAIL = {
    "structured_output": "Respond with a single JSON object that matches the required schema.",
    "strict_tool": f"Return your answer by calling the {TOOL_NAME} tool exactly once.",
}


def system_prompt(output_mode: str) -> str:
    return f"{SYSTEM}\n\n{_TAIL[output_mode]}"


def user_message(question: str, chunks: Sequence[tuple[str, str]]) -> str:
    """``chunks`` = ``(chunk_id, text)`` in rank order."""
    body = "\n\n".join(f'<chunk id="{cid}">\n{text}\n</chunk>' for cid, text in chunks)
    return f"{body}\n\nQuestion: {question}"
