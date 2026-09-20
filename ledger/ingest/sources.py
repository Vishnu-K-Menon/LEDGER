"""``data/sources.yaml`` — per-source provenance and licensing (D-034).

Validation is stage-aware: ``--stage list`` WARNS on a source whose ``policy_url`` is null and
``policy_note`` empty (the owner's browser pass runs in parallel with listing); ``--stage fetch``
HARD-FAILS on it. ``architecture.md:34`` ("confirm per agency page") is satisfied only when every
source has a url or a note."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

log = logging.getLogger(__name__)

Stage = Literal["list", "fetch", "parse"]


class SourcePolicy(BaseModel):
    model_config = ConfigDict(extra="allow")  # frame / robots_note / api_note are free text

    fetch_method: Literal["manual", "direct", "api"]
    policy_url: str | None = None
    policy_note: str | None = None
    policy_confirmed: str | None = None

    @property
    def policy_missing(self) -> bool:
        return self.policy_url is None and not (self.policy_note or "").strip()


class PolicyMissing(RuntimeError):
    pass


def load_sources(path: str | Path, *, stage: Stage) -> dict[str, SourcePolicy]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    sources = {name: SourcePolicy.model_validate(body) for name, body in data.items()}
    missing = [name for name, s in sources.items() if s.policy_missing]
    if missing:
        msg = (
            f"sources.yaml: policy_url is null and policy_note empty for {missing} — "
            "a blank is not a public-domain confirmation (architecture.md:34, D-034)"
        )
        if stage == "list":
            log.warning("%s (allowed at --stage list; required before --stage fetch)", msg)
        else:
            raise PolicyMissing(msg)
    return sources
