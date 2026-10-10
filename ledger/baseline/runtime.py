"""Shared plumbing for the T5 scripts: question files and fail-safe tracing.

Tracing must never cost results (runbook): spans export from a background thread, so a dead
endpoint only logs warnings; ``init`` and ``shutdown`` are wrapped here so that an exception from
the exporter at either end is reported on stderr and swallowed. Callers write their result files
BEFORE tracing is shut down."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ledger.config import Config
from ledger.tracing import otel


def read_questions(path: Path) -> list[dict[str, Any]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def init_tracing_safely(cfg: Config) -> bool:
    try:
        otel.init_tracing(cfg)
        return True
    except Exception as exc:  # noqa: BLE001 - tracing must not stop the run
        print(f"WARNING: tracing init failed, continuing untraced: {exc!r}", file=sys.stderr)
        return False


def shutdown_tracing_safely() -> None:
    try:
        otel.shutdown_tracing()
    except Exception as exc:  # noqa: BLE001
        print(
            f"WARNING: trace export failed at shutdown ({exc!r}); results are on disk, "
            "traces for this run are incomplete",
            file=sys.stderr,
        )
