"""One source for the generator request shape (D-041 pins, D-019 no sampling keys).

``message_params`` is the minimal body ``scripts/a5_probe.py`` sends; ``build_params`` adds the
D12 system prompt, the context and one of the two output modes (D-043 item 5, undecided until the
owner rules). ``generator.output_mode`` empty -> ``OutputModeUnset`` for every caller except the
dry run, which passes the mode explicitly."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ledger.baseline.prompt import system_prompt, user_message
from ledger.baseline.schema import TOOL_NAME, answer_json_schema
from ledger.config import GeneratorConfig

OUTPUT_MODES = ("structured_output", "strict_tool")


class OutputModeUnset(RuntimeError):
    pass


def require_output_mode(gen: GeneratorConfig) -> str:
    if gen.output_mode not in OUTPUT_MODES:
        raise OutputModeUnset(
            "generator.output_mode is empty: the owner rules on it (D-043 item 5) after the "
            "dry run; only scripts/t5_dry_run.py may run without it"
        )
    return gen.output_mode


def message_params(
    model: str,
    max_tokens: int,
    thinking: str,
    effort: str,
    *,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": max_tokens,
        "thinking": {"type": thinking},
        "output_config": {"effort": effort},
        "messages": messages,
    }


def build_params(
    gen: GeneratorConfig,
    *,
    question: str,
    chunks: Sequence[tuple[str, str]],
    output_mode: str,
) -> dict[str, Any]:
    if output_mode not in OUTPUT_MODES:
        raise ValueError(f"unknown output_mode {output_mode!r}")
    body = message_params(
        gen.model,
        gen.max_tokens,
        gen.thinking,
        gen.effort,
        messages=[{"role": "user", "content": user_message(question, chunks)}],
    )
    body["system"] = system_prompt(output_mode)
    schema = answer_json_schema()
    if output_mode == "structured_output":
        # merged into the dict that carries D-041's effort - never replacing it
        body["output_config"] = {
            **body["output_config"],
            "format": {"type": "json_schema", "schema": schema},
        }
    else:
        body["tools"] = [
            {
                "name": TOOL_NAME,
                "description": "Submit the final answer (or the abstention form) with citations.",
                "input_schema": schema,
                "strict": True,
            }
        ]
        body["tool_choice"] = {"type": "auto"}
    return body


def retry_params(
    params: dict[str, Any], content: list[dict[str, Any]], error: str, *, output_mode: str
) -> dict[str, Any]:
    """D13: one retry with the validation error appended to the conversation."""
    msg = f"Your previous output failed validation: {error}\nReturn a corrected answer."
    messages = list(params["messages"]) + [{"role": "assistant", "content": content}]
    call = next((b for b in content if b.get("type") == "tool_use"), None)
    if output_mode == "strict_tool" and call is not None:
        tail: Any = [
            {"type": "tool_result", "tool_use_id": call["id"], "content": msg, "is_error": True}
        ]
    else:
        tail = msg
    messages.append({"role": "user", "content": tail})
    return {**params, "messages": messages}
