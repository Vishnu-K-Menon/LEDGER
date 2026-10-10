"""The ``Answer`` schema (D13) and its validation. Citations are chunk IDs (D-005).

The schema is the single source for both output modes: ``output_config.format`` (structured
output) and the ``input_schema`` of the strict tool. Cross-field rules live in pydantic validators
because they are not expressible in the API's schema subset; A4 counts them as "passes pydantic
validation" (D-043 item 4)."""

from __future__ import annotations

import json
from typing import Any

import anthropic
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

TOOL_NAME = "submit_answer"


class Sentence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    cited_chunk_ids: list[str]


class Answer(BaseModel):
    """The answer, or the abstention form (abstained true, no sentences) when the chunks
    do not contain it. D12/D13."""

    model_config = ConfigDict(extra="forbid")

    abstained: bool
    abstention_reason: str
    sentences: list[Sentence]

    @model_validator(mode="after")
    def _form(self) -> Answer:
        if self.abstained:
            if self.sentences:
                raise ValueError("abstention form must have no sentences")
            if not self.abstention_reason.strip():
                raise ValueError("abstention form must give an abstention_reason")
            return self
        if not self.sentences:
            raise ValueError("a non-abstaining answer needs at least one sentence")
        for i, s in enumerate(self.sentences):
            if not s.text.strip():
                raise ValueError(f"sentence {i} is empty")
            if not s.cited_chunk_ids:
                raise ValueError(f"sentence {i} cites no chunk ID (D12: cite every sentence)")
        return self

    def cited_ids(self) -> list[str]:
        return [cid for s in self.sentences for cid in s.cited_chunk_ids]


class AnswerInvalid(ValueError):
    """The model output could not be turned into a valid ``Answer`` (feeds D13's retry)."""


def answer_json_schema() -> dict[str, Any]:
    """The API-ready schema: ``additionalProperties: false`` on every object, unsupported
    keywords folded into descriptions by the SDK's own transform."""
    return anthropic.transform_schema(Answer)


def parse_answer(content: list[dict[str, Any]], *, output_mode: str) -> Answer:
    """``content`` is the response's content blocks as dicts. structured_output: the text blocks
    hold one JSON object. strict_tool: exactly one ``submit_answer`` tool_use block."""
    try:
        if output_mode == "structured_output":
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
            if not text.strip():
                raise AnswerInvalid("no text block in the response")
            return Answer.model_validate(json.loads(text))
        if output_mode == "strict_tool":
            calls = [
                b for b in content if b.get("type") == "tool_use" and b.get("name") == TOOL_NAME
            ]
            if len(calls) != 1:
                raise AnswerInvalid(f"expected exactly one {TOOL_NAME} call, found {len(calls)}")
            return Answer.model_validate(calls[0].get("input"))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise AnswerInvalid(str(exc)) from exc
    raise AnswerInvalid(f"unknown output_mode {output_mode!r}")
