"""``ledger ingest --stage parse`` (T3): Docling parse + HybridChunker, on CPU (D-032, D-033).

One manifest row = one unit. A row without ``sha256`` is UNFETCHABLE (``BUDGET-2027-TAB``,
D-034) and is skipped, not an error. Each parsed unit writes its Docling document JSON to
``paths.parsed_dir`` and its chunks to ``paths.chunks``; chunk ids are
``<unit_id>::p<page>::<item>::s<slice>`` (D-032: content and position, never a global counter)
and ``chunk_type`` is ``table`` iff every doc item in the chunk is a table item (D-033).

The D-001 stop fires once every row up to ``ingest.confirm_after_units`` has been parsed or
skipped; ``--all --confirmed`` continues past it.
"""

from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docling.backend.docling_parse_v4_backend import DoclingParseV4DocumentBackend
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.types.doc import TableItem

from ledger.config import Config, load_config
from ledger.ingest.manifest import ManifestRow, read_manifest

log = logging.getLogger(__name__)

BACKENDS = {
    "docling_parse_v4": DoclingParseV4DocumentBackend,
    "pypdfium2": PyPdfiumDocumentBackend,
}


# ---- construction (the D-033 switches are pinned in config; nothing numeric here) ------------


def build_converter(cfg: Config, *, backend: str | None = None) -> DocumentConverter:
    opts = PdfPipelineOptions()
    opts.do_ocr = cfg.parser.do_ocr  # D2 / validator: false in v1
    opts.do_table_structure = True
    opts.table_structure_options.mode = TableFormerMode(cfg.parser.table_mode)
    backend_cls = BACKENDS[backend or cfg.parser.pdf_backend]
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=opts, backend=backend_cls)
        }
    )


def build_chunker(cfg: Config) -> HybridChunker:
    """Tokenizer only — no embedding weights are loaded (D-032)."""
    tokenizer = HuggingFaceTokenizer.from_pretrained(
        model_name=cfg.embedding.model, max_tokens=cfg.chunking.max_tokens
    )
    return HybridChunker(
        tokenizer=tokenizer,
        merge_peers=cfg.chunking.merge_peers,
        repeat_table_header=cfg.chunking.repeat_table_header,
        omit_header_on_overflow=cfg.chunking.omit_header_on_overflow,
    )


# ---- chunk records ---------------------------------------------------------------------------


def item_key(self_ref: str) -> str:
    """``#/tables/2`` -> ``tbl-2``; ``#/texts/15`` -> ``txt-15``; content-derived, stable."""
    parts = [p for p in self_ref.split("/") if p and p != "#"]
    if len(parts) < 2:
        return self_ref.strip("#/").replace("/", "-") or "item"
    kind, idx = parts[-2], parts[-1]
    short = {"tables": "tbl", "texts": "txt", "pictures": "pic", "groups": "grp"}.get(
        kind, kind[:3]
    )
    return f"{short}-{idx}"


def _page_of(chunk: Any) -> int:
    for it in chunk.meta.doc_items:
        for prov in getattr(it, "prov", []) or []:
            if getattr(prov, "page_no", None):
                return int(prov.page_no)
    return 0


def is_table_item(it: Any) -> bool:
    """A chunk's ``meta.doc_items`` are deserialized as base ``DocItem`` on the un-split path and
    as ``TableItem`` on the split path (verified 2026-09-20), so ``isinstance`` misclassifies
    every table small enough not to split. Identity comes from ``self_ref``/``label``, which are
    the document's own facts."""
    if isinstance(it, TableItem):
        return True
    return (
        str(getattr(it, "self_ref", "")).startswith("#/tables/")
        or str(getattr(it, "label", "")) == "table"
    )


def is_caption_item(it: Any) -> bool:
    return str(getattr(it, "label", "")) in {"caption", "footnote"}


def chunk_records(
    unit: ManifestRow, chunks: list[Any], chunker: HybridChunker, cfg: Config
) -> list[dict]:
    out: list[dict] = []
    slice_of: dict[tuple[str, str], int] = {}
    for ch in chunks:
        items = list(ch.meta.doc_items)
        tbl = [it for it in items if is_table_item(it)]
        # D-033 literal: table iff EVERY doc item is a table item. Docling attaches a table's
        # caption as its own doc item (label=caption), so a small table arrives as
        # [caption, table] and the literal rule would call it prose — against D3 ("caption
        # attached"). `is_table` applies the caption-inclusive reading and `is_table_literal`
        # keeps the literal one; A9 reports both shares so the owner can ratify one (D-033).
        is_table_literal = bool(items) and len(tbl) == len(items)
        is_table = bool(tbl) and all(is_table_item(it) or is_caption_item(it) for it in items)
        mixed = bool(tbl) and not is_table  # a genuine table+prose mix: D-033 expects zero
        page = _page_of(ch)
        key = item_key(items[0].self_ref) if items else "item"
        sl = slice_of.get((str(page), key), 0)
        slice_of[(str(page), key)] = sl + 1
        text = chunker.contextualize(chunk=ch) if cfg.chunking.prepend_headings else ch.text
        out.append(
            {
                "chunk_id": f"{unit.unit_id}::p{page}::{key}::s{sl}",
                "unit_id": unit.unit_id,
                "source": unit.source,
                "parent_series": unit.parent_series,
                "page": page,
                "item": key,
                "slice": sl,
                "chunk_type": "table" if is_table else "prose",
                "chunk_type_literal": "table" if is_table_literal else "prose",
                "mixed_items": mixed,
                "table_refs": sorted({item_key(it.self_ref) for it in tbl}),
                "n_items": len(items),
                "headings": list(ch.meta.headings or []),
                # ``meta.captions`` is deprecated in docling-core 2.97.1; the caption arrives as
                # its own doc item (label=caption), so take it from there.
                "captions": [str(getattr(it, "text", "")) for it in items if is_caption_item(it)],
                "text": text,
                "n_tokens": chunker.tokenizer.count_tokens(text),
            }
        )
    return out


# ---- one unit --------------------------------------------------------------------------------


@dataclass
class UnitParse:
    unit_id: str
    pages: int
    n_chunks: int
    n_table_chunks: int
    distinct_tables: int
    seconds: float
    error: str | None = None
    records: list[dict] = field(default_factory=list)


def parse_unit(
    cfg: Config,
    repo: Path,
    row: ManifestRow,
    *,
    converter=None,
    chunker=None,
    backend: str | None = None,
) -> UnitParse:
    converter = converter or build_converter(cfg, backend=backend)
    chunker = chunker or build_chunker(cfg)
    pdf = repo / cfg.paths.raw_dir / row.source / f"{row.unit_id}.pdf"
    t0 = time.perf_counter()
    try:
        result = converter.convert(pdf)
        doc = result.document
        parsed_dir = repo / cfg.paths.parsed_dir
        parsed_dir.mkdir(parents=True, exist_ok=True)
        doc.save_as_json(parsed_dir / f"{row.unit_id}.json")
        records = chunk_records(row, list(chunker.chunk(dl_doc=doc)), chunker, cfg)
    except Exception as exc:  # noqa: BLE001 - a failed unit is data, not a crash
        return UnitParse(row.unit_id, row.pages or 0, 0, 0, 0, time.perf_counter() - t0, str(exc))
    tables = {t for r in records if r["chunk_type"] == "table" for t in r["table_refs"]}
    return UnitParse(
        unit_id=row.unit_id,
        pages=row.pages or 0,
        n_chunks=len(records),
        n_table_chunks=sum(1 for r in records if r["chunk_type"] == "table"),
        distinct_tables=len(tables),
        seconds=time.perf_counter() - t0,
        records=records,
    )


# ---- process pool (Windows spawn: module-level worker, models built once per process) ---------

_WORKER: dict[str, Any] = {}


def _worker_parse(args: tuple[str, str, str, int]) -> dict:
    """(config_path, repo, row_json, n_workers) -> UnitParse as a dict.

    Each worker loads its own models. Torch defaults to one intra-op thread per core in *every*
    process, so N workers on an N-core box oversubscribe it and the pool runs no faster than a
    single process (measured 2026-09-20: 330s single vs 335s with 5 workers). The per-worker
    thread count is therefore derived from the machine, not configured: cores // workers.
    """
    config_path, repo_s, row_json, n_workers = args
    if "cfg" not in _WORKER:
        threads = max(1, (os.cpu_count() or 1) // max(n_workers, 1))
        os.environ.setdefault("OMP_NUM_THREADS", str(threads))
        try:
            import torch

            torch.set_num_threads(threads)
        except Exception:  # noqa: BLE001 - threading is an optimisation, never a hard failure
            pass
        cfg = load_config(config_path)
        _WORKER["cfg"] = cfg
        _WORKER["converter"] = build_converter(cfg)
        _WORKER["chunker"] = build_chunker(cfg)
    cfg = _WORKER["cfg"]
    row = ManifestRow.model_validate_json(row_json)
    up = parse_unit(
        cfg, Path(repo_s), row, converter=_WORKER["converter"], chunker=_WORKER["chunker"]
    )
    return {
        "unit_id": up.unit_id,
        "pages": up.pages,
        "n_chunks": up.n_chunks,
        "n_table_chunks": up.n_table_chunks,
        "distinct_tables": up.distinct_tables,
        "seconds": up.seconds,
        "error": up.error,
        "records": up.records,
    }


def parse_pool(
    cfg: Config, repo: Path, rows: list[ManifestRow], *, config_path: str, workers: int
) -> list[UnitParse]:
    payload = [(config_path, str(repo), r.model_dump_json(), workers) for r in rows]
    out: list[UnitParse] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for d in ex.map(_worker_parse, payload):
            out.append(UnitParse(**d))
    return out


def pool_size(cfg: Config) -> int:
    return cfg.parser.workers or (os.cpu_count() or 1)


# ---- the stage -------------------------------------------------------------------------------


@dataclass
class ParseResult:
    parsed: list[UnitParse]
    skipped: list[str]
    stopped: bool
    seconds: float
    workers: int


def eligible_rows(rows: list[ManifestRow]) -> tuple[list[ManifestRow], list[str]]:
    """(parseable, skipped-unfetchable). A row without sha256 was never fetched (D-034)."""
    parseable = [r for r in rows if r.sha256]
    skipped = [r.unit_id for r in rows if not r.sha256]
    return parseable, skipped


def d001_stop_reached(rows: list[ManifestRow], done: int, skipped: int, cfg: Config) -> bool:
    """D-001: the stop fires once every row up to confirm_after_units is parsed or skipped."""
    return (done + skipped) >= min(cfg.ingest.confirm_after_units, len(rows))


def write_chunks(path: Path, parses: list[UnitParse]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for up in parses:
            for rec in up.records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
    return n


def run_parse(
    cfg: Config,
    repo: Path,
    *,
    config_path: str,
    limit: int | None = None,
    all_: bool = False,
    workers: int | None = None,
) -> ParseResult:
    _, rows = read_manifest(repo / cfg.paths.manifest)
    parseable, skipped = eligible_rows(rows)
    if limit:
        parseable = parseable[:limit]
    if not all_:
        budget = max(cfg.ingest.confirm_after_units - len(skipped), 0)
        parseable = parseable[:budget]
    n_workers = workers if workers is not None else pool_size(cfg)
    t0 = time.perf_counter()
    if n_workers > 1 and len(parseable) > 1:
        parses = parse_pool(cfg, repo, parseable, config_path=config_path, workers=n_workers)
    else:
        converter, chunker = build_converter(cfg), build_chunker(cfg)
        parses = [parse_unit(cfg, repo, r, converter=converter, chunker=chunker) for r in parseable]
    seconds = time.perf_counter() - t0
    write_chunks(repo / cfg.paths.chunks, parses)
    stopped = not all_ and d001_stop_reached(rows, len(parses), len(skipped), cfg)
    return ParseResult(parses, skipped, stopped, seconds, n_workers)
