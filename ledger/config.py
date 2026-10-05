"""Configuration models (D31). Every parameter lives in ``configs/*.yaml``; nothing numeric is
hardcoded in code. ``load_config`` reads ``configs/base.yaml`` plus an optional override file."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_CONFIG_PATH = Path("configs/base.yaml")

# D-019: sampling parameters were removed from the Claude API (anthropic SDK 1.0.0, 2026-08-20;
# Sonnet 5 returns 400 for non-default values on both the sync and Batch paths). They may not be
# reintroduced anywhere in config; a "seed" is an independent run at the model's default sampling.
REMOVED_SAMPLING_KEYS = frozenset({"temperature", "top_p", "top_k"})


def _reject_sampling_keys(data: Any, path: str = "") -> None:
    if isinstance(data, dict):
        for key, value in data.items():
            here = f"{path}.{key}" if path else str(key)
            if key in REMOVED_SAMPLING_KEYS:
                raise ValueError(
                    f"config key {here!r} is not allowed (D-019): {key} was removed from the "
                    "Claude API itself (anthropic SDK 1.0.0, 2026-08-20; Sonnet 5 rejects it with "
                    "400 on both the sync and Batch paths). This is not a missing schema field - "
                    "do not add it. A 'seed' is an independent run at default sampling."
                )
            _reject_sampling_keys(value, here)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            _reject_sampling_keys(item, f"{path}[{i}]")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PathsConfig(_Strict):
    data_dir: Path
    results_dir: Path
    reports_dir: Path
    manifest: Path
    raw_dir: Path
    parsed_dir: Path
    qdrant_path: Path
    chunks: Path  # D-032: chunk output of the ingest stage
    chunk_ids_lock: Path  # D24
    questions_draft: Path
    questions: Path
    matrix_cells: Path
    s3_bucket: str  # empty until T4 (bucket + IAM instance profile)


class CorpusConfig(_Strict):
    source_mix: dict[str, int]  # D-034: pilot composition by source key
    min_units: int = Field(gt=0)  # D-034 floor: >= 25 units
    min_sources: int = Field(gt=0)  # D-034 floor: >= 3 sources
    selection_seed: int
    # D-040: units of these parent series are EXCLUDED from v1 (manifest rows kept); the key
    # test_mer_absent checks provenance on, never text
    excluded_parent_series: list[str]


class IngestConfig(_Strict):
    confirm_after_units: int = Field(gt=0)  # D-001: one manifest row = one unit
    table_chunk_share_band: tuple[float, float]

    @field_validator("table_chunk_share_band")
    @classmethod
    def _band_ordered(cls, v: tuple[float, float]) -> tuple[float, float]:
        lo, hi = v
        if not 0.0 <= lo < hi <= 1.0:
            raise ValueError("table_chunk_share_band must be [lo, hi] within [0, 1] with lo < hi")
        return v


class RowTokenConfig(_Strict):
    """A text-layer tokeniser of the row fix (D-038 / D-039; frozen values, port parity)."""

    box_margin_pt: float = Field(
        ge=0
    )  # a char belongs to the table if its centre is inside +- this
    superscript_size_ratio: float = Field(
        gt=0, le=1
    )  # chars smaller than this x median are dropped
    line_tol_height_ratio: float = Field(gt=0)  # line grouping: |dy| <= this x median char height
    gap_size_ratio: float = Field(gt=0)  # a token breaks on an x-gap > this x char size


class RowFixConfig(_Strict):
    """D-038 rung 1 / D-039 rung 1b: the text-layer row fix (ledger/ingest/rows.py). Every value is
    the frozen rung-1b emitter's (reports/a1_diag/rung1b/emitter_freeze.json); the port is gated on
    byte-identical output, so a change here re-opens the parity gate."""

    sources: list[str]  # D-039: the emitter runs only on these manifest sources
    trigger: RowTokenConfig  # the frozen D-038 trigger's tokeniser (counts only)
    tokens: RowTokenConfig  # the emitter's own tokeniser
    merged_cell_min_numbers: int = Field(ge=2)  # live trigger: a TF body cell this full is merged
    flag_merge_gap_char_widths: float = Field(gt=0)  # a lone R/E flag joins the next number
    band_overlap_merge_ratio: float = Field(gt=0, le=1)  # centred-column split clusters merge
    dense_band_min_tokens: int = Field(ge=1)  # a dense band holds >= max(this, ...) tokens
    dense_band_line_divisor: int = Field(ge=1)  # ... and >= ceil(candidate lines / this)
    in_band_tol_multiple: float = Field(gt=0)  # a value is in a band within this x band tolerance
    word_min_alpha: int = Field(ge=1)  # a token with this many letters is a word
    prose_min_words: int = Field(ge=1)  # a line with this many words right of the stub is prose
    prose_safety_share: float = Field(gt=0, le=1)  # fallback if prose lines exceed this share
    text_column_gap_em: float = Field(gt=0)  # stub segments split by more than this many em
    text_column_min_segments: int = Field(ge=2)  # worded stub segments that make a text column
    text_column_safety_share: float = Field(gt=0, le=1)  # fallback if split stubs reach this share
    header_tolerance_pt: float = Field(ge=0)  # header-word / band x-overlap tolerance
    phrase_gap_size_ratio: float = Field(gt=0)  # header words this close (x size) are one phrase
    default_leading_pt: float = Field(gt=0)  # line pitch when a table has one body line
    wrap_leading_multiple: float = Field(gt=0)  # a wrapped label sits within this x leading
    stub_left_tolerance_pt: float = Field(
        ge=0
    )  # stub = tokens ending left of the first band + this
    multi_number_safety_share: float = Field(gt=0, le=1)  # fallback if this share of cells hold 2+


class ParserConfig(_Strict):
    name: Literal["docling"]  # the paddleocr_vl fallback is retired (D-038; D2 status 2026-09-30)
    table_mode: str
    do_ocr: bool
    pdf_backend: Literal["docling_parse_v4", "pypdfium2"]
    workers: int = Field(ge=0)  # 0 = os.cpu_count()
    audit_tables_n: int = Field(gt=0)
    audit_min_cells: int = Field(gt=0)
    audit_cell_accuracy_min: float = Field(ge=0.0, le=1.0)
    audit_require_units: dict[str, int] = Field(default_factory=dict)
    audit_log_glob: str = "logs/parse_*.log"
    row_fix: RowFixConfig  # D-038 / D-039: the text-layer row fix (production port)

    @field_validator("do_ocr")
    @classmethod
    def _no_ocr_in_v1(cls, v: bool) -> bool:
        # D2: the corpus is born-digital and the text layer holds the exact digits. OCR would
        # invent text on the very pages A1 measures (FCS/CROSSCUT blank pages).
        if v is not False:
            raise ValueError(
                "parser.do_ocr must be false in v1 (D2): Docling is used as a text-layer parser; "
                "the A1 failure is repaired inside the Docling pipeline (D-038), not by OCR"
            )
        return v


class ChunkingConfig(_Strict):
    max_tokens: int = Field(gt=0)
    overlap: int = Field(ge=0)
    repeat_table_header: bool
    omit_header_on_overflow: bool
    merge_peers: bool
    prepend_headings: bool
    # D-037: markdown is the serializer under which D-033's switches act (header/body split)
    table_serializer: str
    # docling-core 2.97.1 MarkdownParams.compact_tables: padded (false) vs minimal (true) columns.
    # Owner: false (D-037 status 2026-10-02, ruling 1). Null still loads; build_chunker raises at
    # the use site while it is null (the D-020 pattern).
    markdown_compact_tables: bool | None = None

    @field_validator("table_serializer")
    @classmethod
    def _markdown_tables(cls, v: str) -> str:
        if v != "markdown":
            raise ValueError(
                "chunking.table_serializer must be 'markdown' (D-037): under the default triplet "
                "serializer the header switches never act and slices cut values from their labels"
            )
        return v

    # D-033: the three HybridChunker switches that decide whether a table slice keeps its
    # header (unit, period) and stays unmixed with prose. Pinned; a later library default flip
    # is caught here and by the T3 test, not in a label sheet.
    @field_validator("repeat_table_header")
    @classmethod
    def _header_on_every_slice(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError(
                "chunking.repeat_table_header must be true (D-033): every table slice carries the "
                "header row, or the unit and period leave the chunk"
            )
        return v

    @field_validator("omit_header_on_overflow")
    @classmethod
    def _never_drop_header(cls, v: bool) -> bool:
        if v is not False:
            raise ValueError(
                "chunking.omit_header_on_overflow must be false (D-033): a slice that drops its "
                "header silently loses the unit and period"
            )
        return v

    @field_validator("merge_peers")
    @classmethod
    def _no_table_prose_merge(cls, v: bool) -> bool:
        if v is not False:
            raise ValueError(
                "chunking.merge_peers must be false (D-033): HybridChunker merges undersized "
                "peers on headings only, so a table slice would merge with prose and chunk_type "
                "becomes ambiguous"
            )
        return v


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
    max_tokens: int = Field(gt=0)
    use_batch: bool
    pricing_usd_per_mtok: PricingConfig

    def cost_usd(self, usage: Mapping[str, int | None], *, batch: bool) -> float:
        """D30/D31: cost = measured API usage fields x configured price. ``batch`` selects the
        Batch rates (50%); applying sync rates to a Batch run would double every D26 cost figure.
        Cache tokens are not priced here until caching is used (T5 adds the keys)."""
        p = self.pricing_usd_per_mtok
        rate_in, rate_out = (p.batch_input, p.batch_output) if batch else (p.input, p.output)
        tokens_in = usage.get("input_tokens") or 0
        tokens_out = usage.get("output_tokens") or 0
        return (tokens_in * rate_in + tokens_out * rate_out) / 1_000_000


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


class CrptFilterTerms(_Strict):
    all_of: list[str]
    any_of: list[str]


class FetchConfig(_Strict):
    user_agent: str
    request_delay_s: dict[str, float]
    backoff_base_s: float = Field(gt=0)
    backoff_max_s: float = Field(gt=0)
    max_retries: int = Field(ge=0)
    timeout_s: float = Field(gt=0)
    text_layer_ratio_min: float = Field(ge=0.0, le=1.0)
    govinfo_base_url: str
    govinfo_page_size: int = Field(gt=0, le=1000)
    date_range: tuple[str, str]
    eia_sitemap_url: str
    eia_landing_pages: dict[str, str]
    eia_disallow_patterns: list[str]
    crpt_sample_n: int = Field(gt=0)
    crpt_filter_terms: CrptFilterTerms
    gate_spot_check_n: int = Field(gt=0)
    gate_min_text_chars: int = Field(gt=0)
    pilot_eia_mer_sections: int = Field(ge=0)
    # Image-only units (the sec7 lesson; D-034 status 2026-10-02): a page is image-only with >= 1
    # embedded image and at most ``image_only_page_max_words`` text-layer words; a unit with at
    # least ``image_only_unit_min_share`` image-only pages is EXCLUDED at fetch. Null loads; the
    # functions that use them raise (the D-020 pattern).
    image_only_page_max_words: int | None = Field(default=None, ge=0)
    image_only_unit_min_share: float | None = Field(default=None, ge=0.0, le=1.0)
    # D-034 status 2026-10-04 (1): a BUDGET unit whose measured pages exceed this is EXCLUDED at
    # fetch, no replacement draw (the owner's cap; package-metadata pages are < 200 for the draw)
    budget_page_cap: int = Field(gt=0)


class TracingConfig(_Strict):
    # No endpoint field on purpose: it is read from OTEL_EXPORTER_OTLP_ENDPOINT only (D-014).
    enabled: bool
    project_name: str
    service_name: str


class Config(_Strict):
    @model_validator(mode="before")
    @classmethod
    def _no_sampling_parameters(cls, data: Any) -> Any:
        """D-019: raise explicitly, before ``extra="forbid"`` can turn this into a vague error."""
        _reject_sampling_keys(data)
        return data

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
    fetch: FetchConfig
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
