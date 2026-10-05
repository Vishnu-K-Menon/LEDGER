"""Cell definitions read from ``experiments/matrix.yaml`` (D26; seeds per D-035)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class Cell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    arm: Literal["no_repair", "delete", "rewrite", "re_retrieve"]
    decomposition: Literal["claimify", "sentence_split"]
    max_iter: int | None = None


class MatrixConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seeds: list[int]
    cells: list[Cell]

    @field_validator("seeds")
    @classmethod
    def _seeds(cls, v: list[int]) -> list[int]:
        if not v or len(set(v)) != len(v):
            raise ValueError("seeds must be a non-empty list of distinct ints")
        return v

    @model_validator(mode="after")
    def _unique_ids(self) -> MatrixConfig:
        ids = [c.id for c in self.cells]
        if len(set(ids)) != len(ids):
            raise ValueError("cell ids must be unique")
        return self


def load_matrix(path: Path) -> MatrixConfig:
    return MatrixConfig.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
