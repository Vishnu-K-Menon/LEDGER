"""Configuration models (D31). Every parameter lives in ``configs/*.yaml``; nothing numeric is
hardcoded in code. ``load_config`` reads ``configs/base.yaml`` plus an optional override file."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_CONFIG_PATH = Path("configs/base.yaml")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PathsConfig(_Strict):
    data_dir: Path
    results_dir: Path
    reports_dir: Path
    manifest: Path
    parsed_dir: Path
    qdrant_path: Path
    chunk_ids_lock: Path  # D24
    questions_draft: Path
    questions: Path
    matrix_cells: Path


class CorpusConfig(_Strict):
    agency_mix: dict[str, int]


class IngestConfig(_Strict):
    confirm_after_docs: int = Field(gt=0)  # D-001
    table_chunk_share_band: tuple[float, float]

    @field_validator("table_chunk_share_band")
    @classmethod
    def _band_ordered(cls, v: tuple[float, float]) -> tuple[float, float]:
        lo, hi = v
        if not 0.0 <= lo < hi <= 1.0:
            raise ValueError("table_chunk_share_band must be [lo, hi] within [0, 1] with lo < hi")
        return v


class ParserConfig(_Strict):
    name: Literal["docling", "paddleocr_vl"]
    table_mode: str
    audit_tables_n: int = Field(gt=0)
    audit_min_cells: int = Field(gt=0)
    audit_cell_accuracy_min: float = Field(ge=0.0, le=1.0)


class ChunkingConfig(_Strict):
    max_tokens: int = Field(gt=0)
    overlap: int = Field(ge=0)
    tables_atomic: bool
    prepend_headings: bool


class EmbeddingConfig(_Strict):
    model: str
    fallback_model: str
    precision: Literal["bf16"]
    dim: int = Field(gt=0)


class VectorStoreConfig(_Strict):
    mode: Literal["local", "docker"]  # D-002
    collection: str
    sparse_enabled: bool


class RetrievalConfig(_Strict):
    k_dense: int = Field(gt=0)
    k_final: int = Field(gt=0)
    k_final_fallback: int = Field(gt=0)
    hybrid: bool
    recall_gate: float = Field(ge=0.0, le=1.0)
    hybrid_floor: float = Field(ge=0.0, le=1.0)
    max_context_chunks: int = Field(gt=0)


class RerankerConfig(_Strict):
    model: str
    precision: Literal["bf16"]


class PricingConfig(_Strict):
    input: float = Field(ge=0.0)
    output: float = Field(ge=0.0)
    batch_input: float = Field(ge=0.0)
    batch_output: float = Field(ge=0.0)


class GeneratorConfig(_Strict):
    model: str
    temperature: float = Field(ge=0.0, le=1.0)
    max_tokens: int = Field(gt=0)
    use_batch: bool
    pricing_usd_per_mtok: PricingConfig


class DecompositionConfig(_Strict):
    method: Literal["claimify", "sentence_split"]


class VerifierConfig(_Strict):
    model: str
    revision: str
    precision: str
    input_mode: Literal["concatenated", "per_chunk_max"]  # D-004
    threshold: float = Field(ge=0.0, le=1.0)
    pilot_candidates: list[str]

    @field_validator("precision")
    @classmethod
    def _bf16_only(cls, v: str) -> str:
        # D-012: the verifier runs bf16 and only bf16; there is no quantized path.
        if v != "bf16":
            raise ValueError(f"verifier.precision must be 'bf16' (D-012), got {v!r}")
        return v


class JudgeConfig(_Strict):
    model: str
    revision: str

    def require_pinned(self) -> JudgeConfig:
        """D-007: the judge loader raises until the owner has pinned an exact revision hash."""
        if not self.model or not self.revision:
            raise RuntimeError(
                "judge.model / judge.revision are empty: the judge is not chosen yet (D-007). "
                "Ask the owner, pin the revision hash in configs/base.yaml, never change it."
            )
        return self


class LoopConfig(_Strict):
    max_iter: int = Field(ge=0)
    graft_max_iters: list[int]
    max_tool_calls: int = Field(gt=0)
    max_tokens_per_query: int = Field(gt=0)


class RepairConfig(_Strict):
    arm: Literal["none", "delete", "rewrite", "re_retrieve"]
    delete_marker: str  # D-008


class QuestionsConfig(_Strict):
    n: int = Field(gt=0)
    controls: int = Field(ge=0)
    table_share: float = Field(ge=0.0, le=1.0)
    min_words: int = Field(gt=0)
    max_words: int = Field(gt=0)
    dup_cosine: float = Field(ge=0.0, le=1.0)
    hand_validated: int = Field(ge=0)
    answerable_per_run: int = Field(gt=0)
    writer_model: str


class EvalConfig(_Strict):
    seeds: list[int]
    bootstrap_n: int = Field(gt=0)
    kappa_go: float
    kappa_tune: float
    input_mode_tie: float = Field(ge=0.0)
    pilot_claims: int = Field(gt=0)
    pilot_min_unsupported: int = Field(ge=0)
    labels_per_half: int = Field(gt=0)
    schema_valid_min: float = Field(ge=0.0, le=1.0)
    budget_max_usd: float = Field(ge=0.0)
    smoke_n: int = Field(gt=0)
    decomp_audit_n: int = Field(gt=0)
    abstention_controls_min: float = Field(ge=0.0, le=1.0)
    abstention_answerable_max: float = Field(ge=0.0, le=1.0)


class TracingConfig(_Strict):
    # No endpoint field on purpose: it is read from OTEL_EXPORTER_OTLP_ENDPOINT only (D-014).
    enabled: bool
    project_name: str
    service_name: str


class Config(_Strict):
    paths: PathsConfig
    corpus: CorpusConfig
    ingest: IngestConfig
    parser: ParserConfig
    chunking: ChunkingConfig
    embedding: EmbeddingConfig
    vector_store: VectorStoreConfig
    retrieval: RetrievalConfig
    reranker: RerankerConfig
    generator: GeneratorConfig
    decomposition: DecompositionConfig
    verifier: VerifierConfig
    judge: JudgeConfig
    loop: LoopConfig
    repair: RepairConfig
    questions: QuestionsConfig
    eval: EvalConfig
    tracing: TracingConfig


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top level must be a mapping")
    return data


def load_config(
    base: str | Path = DEFAULT_CONFIG_PATH, override: str | Path | None = None
) -> Config:
    """Load ``base`` and deep-merge ``override`` on top, then validate (D31)."""
    data = _read_yaml(Path(base))
    if override is not None:
        data = _deep_merge(data, _read_yaml(Path(override)))
    return Config.model_validate(data)
