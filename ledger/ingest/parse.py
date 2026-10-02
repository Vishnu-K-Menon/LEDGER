"""``ledger ingest --stage parse`` (T3): Docling parse + HybridChunker, on CPU (D-032, D-033).

One manifest row = one unit. A row without ``sha256`` is UNFETCHABLE (``BUDGET-2027-TAB``,
D-034) and is skipped, not an error. Each parsed unit writes its Docling document JSON to
``paths.parsed_dir`` and its chunks to ``paths.chunks``; chunk ids are
``<unit_id>::p<page>::<item>::s<slice>`` (D-032: content and position, never a global counter)
and ``chunk_type`` is ``table`` iff the chunk holds at least one table item and every other doc
item is a caption or footnote (**D-036**, successor to D-033's literal wording).

**Resumable** (D-032 status 2026-09-25): a unit whose document JSON *and* chunk records are both
on disk is reused, never re-parsed; every write is atomic (temp file + ``os.replace``), so an
interrupted unit leaves neither file. Each unit's provenance — library versions, backend,
``table_mode``, ``do_ocr``, device, wall seconds, chunk count — is written to
``<unit>.meta.json`` and onto the manifest row, so laptop and g6e parses stay tellable apart.

The D-001 stop fires once every row up to ``ingest.confirm_after_units`` has been parsed or
skipped; ``--all --confirmed`` continues past it.

**One chunking path (D-037).** ``chunk_document`` takes the raw Docling export (a dict), the unit's
PDF, its manifest row and the config: the row fix (``rows.fix_document``; it rebuilds only
``parser.row_fix.sources`` tables, BUDGET/CBO pass through) -> ``DoclingDocument`` ->
``HybridChunker`` with the markdown table serializer -> ``chunk_records`` -> the unit prefix.
``parse_unit`` calls it after convert + ``export_to_dict``, and the one pre-freeze re-chunk
(``scripts/rechunk_d037.py``) calls it on the saved export, so both run the same code.
``<unit>.json`` stays the raw Docling export; the fix log goes beside it as ``<unit>.rowfix.json``.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import logging
import os
import re
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pdfplumber
from docling.backend.docling_parse_v4_backend import DoclingParseV4DocumentBackend
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.transforms.chunker.hierarchical_chunker import ChunkingDocSerializer
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.transforms.serializer.base import BaseDocSerializer, BaseSerializerProvider
from docling_core.transforms.serializer.markdown import MarkdownTableSerializer
from docling_core.types.doc import DoclingDocument, TableItem

from ledger.config import Config, load_config
from ledger.ingest.manifest import ManifestRow, active_rows, read_manifest, write_manifest
from ledger.ingest.rows import fix_document

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


class MarkdownTableSerializerProvider(BaseSerializerProvider):
    """D-037: the library's chunking serializer with the markdown table serializer selected —
    nothing else changed. It must stay a ``ChunkingDocSerializer``: ``HybridChunker.segment()``
    takes the header-repeat path only for that class. ``compact_tables`` reaches the table
    serializer through the doc serializer's params (merged into the item kwargs)."""

    def __init__(self, compact_tables: bool) -> None:
        self.compact_tables = compact_tables

    def get_serializer(self, doc: DoclingDocument) -> BaseDocSerializer:
        params = ChunkingDocSerializer.model_fields["params"].default.model_copy(
            update={"compact_tables": self.compact_tables}
        )
        return ChunkingDocSerializer(
            doc=doc, table_serializer=MarkdownTableSerializer(), params=params
        )


def build_chunker(cfg: Config) -> HybridChunker:
    """Tokenizer only — no embedding weights are loaded (D-032). The table serializer is the
    pinned markdown one (D-037); ``markdown_compact_tables`` must be set by the owner first."""
    compact = cfg.chunking.markdown_compact_tables
    if compact is None:
        raise RuntimeError(
            "chunking.markdown_compact_tables is null: padded vs compact markdown columns change "
            "tokens per row and so slice counts, and D-037 does not pin it - the owner sets it "
            "before anything is chunked (D-037; guard at the use site, the D-020 pattern)"
        )
    tokenizer = HuggingFaceTokenizer.from_pretrained(
        model_name=cfg.embedding.model, max_tokens=cfg.chunking.max_tokens
    )
    return HybridChunker(
        tokenizer=tokenizer,
        merge_peers=cfg.chunking.merge_peers,
        repeat_table_header=cfg.chunking.repeat_table_header,
        omit_header_on_overflow=cfg.chunking.omit_header_on_overflow,
        serializer_provider=MarkdownTableSerializerProvider(compact),
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


# rows.fix_document's per-table status -> the record's ``parse_path`` (D-040's sampling rule keys
# on ``fallback``)
PARSE_PATH = {
    "rebuilt": "rebuilt",
    "fallback": "fallback",
    "not fired": "not fired",
    "out of scope (D-039)": "out of scope",
}


def _table_index(key: str) -> int:
    return int(key.split("-", 1)[1])


def parse_path_of(table_keys: list[str], fix_log: dict[int, dict]) -> str | None:
    """One chunk's parse path. A chunk holding tables with different paths is ``fallback`` if any
    of them is (the conservative side of D-040's rule), else the first table's path."""
    paths = [PARSE_PATH[fix_log[_table_index(k)]["status"]] for k in table_keys]
    if not paths:
        return None
    return "fallback" if "fallback" in paths else paths[0]


def chunk_records(
    unit: ManifestRow,
    chunks: list[Any],
    chunker: HybridChunker,
    cfg: Config,
    fix_log: dict[int, dict] | None = None,
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
        table_keys = sorted({item_key(it.self_ref) for it in tbl}, key=_table_index)
        parse_path = (
            parse_path_of(table_keys, fix_log) if fix_log is not None and is_table else None
        )
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
                # the chunker's own segment is the last ``body_chars`` characters of ``text``
                # (contextualize and the unit prefix only ever prepend)
                "body_chars": len(ch.text),
                "parse_path": parse_path,
                "parse_path_by_table": (
                    {k: PARSE_PATH[fix_log[_table_index(k)]["status"]] for k in table_keys}
                    if fix_log is not None and is_table
                    else None
                ),
                "prefix": None,
                "prefix_source": None,
                "prefix_title_source": None,
            }
        )
    return out


def body_of(rec: dict) -> str:
    """The chunker's segment text of a record, without headings or the unit prefix."""
    return rec["text"][len(rec["text"]) - rec["body_chars"] :]


# ---- the unit prefix (D-037 item 3) -------------------------------------------------------------

# a text item whose whole text is one square-bracketed phrase: "[Percent of nominal GDP]"
BRACKETED = re.compile(r"^\[[^\[\]]+\]$")
TITLE_LABELS = {"section_header", "title"}


def _label(it: Any) -> str:
    return str(getattr(getattr(it, "label", ""), "value", getattr(it, "label", "")))


def _page(it: Any) -> int | None:
    prov = getattr(it, "prov", None) or []
    return int(prov[0].page_no) if prov else None


def _unit_kind(it: Any) -> str | None:
    """``caption`` | ``bracketed-unit`` | None — D-037 item 3's two kinds of source item."""
    if isinstance(it, TableItem) or _label(it) == "table":
        return None
    if _label(it) == "caption":
        return "caption"
    text = str(getattr(it, "text", "") or "").strip()
    if text and BRACKETED.match(text):
        return "bracketed-unit"
    return None


def _ref(it: Any) -> dict:
    return {
        "ref": str(it.self_ref),
        "label": _label(it),
        "text": str(getattr(it, "text", "") or ""),
        "page": _page(it),
    }


def prefix_sources(doc: DoclingDocument) -> dict[str, dict]:
    """Per table (``tbl-N``): D-037 item 3 read literally. Reading order is the document's
    (``iterate_items``, body layer); only items on the table's own page are considered.

    * ``unit``: the nearest preceding caption item or bracketed-unit text item on the page;
    * ``title``: the nearest preceding title / section-header item on the page;
    * ``category``: caption | bracketed-unit | title only | nothing;
    * flags: (i) ``table_between`` — another table lies between the unit item and this table;
      (ii) ``no_title_on_page`` — the page holds no title item at all (a continuation);
      (iii) ``unit_after_title_only`` — a caption / bracketed-unit item follows the page's title
      but none precedes the table.

    Nothing here changes the document; nothing found means no unit line (no fallback)."""
    items = [it for it, _lvl in doc.iterate_items()]
    by_page: dict[int, list[tuple[int, Any]]] = {}
    for i, it in enumerate(items):
        if _page(it) is not None:
            by_page.setdefault(_page(it), []).append((i, it))
    out: dict[str, dict] = {}
    for pos, tbl in enumerate(items):
        if not isinstance(tbl, TableItem):
            continue
        page = _page(tbl)
        on_page = by_page.get(page, []) if page is not None else []
        unit = title = None
        table_between = False
        for _i, it in reversed([(i, it) for i, it in on_page if i < pos]):
            kind = _unit_kind(it)
            if unit is None and kind:
                unit = (it, kind)
            if title is None and _label(it) in TITLE_LABELS:
                title = it
            if unit is None and isinstance(it, TableItem):
                table_between = True
            if unit and title:
                break
        titles = [(i, it) for i, it in on_page if _label(it) in TITLE_LABELS]
        title_pos = next((i for i, it in titles if it is title), titles[0][0] if titles else None)
        unit_after_title = (
            unit is None
            and title_pos is not None
            and any(_unit_kind(it) for i, it in on_page if i > title_pos and it is not tbl)
        )
        category = unit[1] if unit else ("title only" if title else "nothing")
        out[item_key(str(tbl.self_ref))] = {
            "page": page,
            "unit": _ref(unit[0]) if unit else None,
            "title": _ref(title) if title else None,
            "category": category,
            "flags": {
                "table_between": bool(unit) and table_between,
                "no_title_on_page": not titles,
                "unit_after_title_only": unit_after_title,
            },
        }
    return out


def apply_prefix(
    records: list[dict], sources: dict[str, dict], chunker: HybridChunker
) -> list[dict]:
    """Prefix every table slice with its title line and unit/caption line, each the source item's
    text verbatim. A text transform on finished records: ids, slice boundaries and the chunker's
    segment are untouched. A slice whose table has no unit item gets no unit line and
    ``prefix_source: null``."""
    out = []
    for rec in records:
        rec = dict(rec)
        if rec["chunk_type"] == "table":
            key = (
                rec["item"] if rec["item"] in sources else min(rec["table_refs"], key=_table_index)
            )
            src = sources.get(key)
            lines = []
            if src and src["title"] and src["title"]["text"].strip():
                lines.append(src["title"]["text"])
                rec["prefix_title_source"] = src["title"]["ref"]
            if src and src["unit"] and src["unit"]["text"].strip():
                lines.append(src["unit"]["text"])
                rec["prefix_source"] = src["unit"]["ref"]
            if lines:
                rec["prefix"] = "\n".join(lines)
                rec["text"] = rec["prefix"] + "\n" + rec["text"]
                rec["n_tokens"] = chunker.tokenizer.count_tokens(rec["text"])
        out.append(rec)
    return out


# ---- D-037 item 4: output assertions ------------------------------------------------------------

SEPARATOR_ROW = re.compile(r"^\|(\s*:?-+:?\s*\|)+\s*$")


def table_headers(doc: DoclingDocument, chunker: HybridChunker) -> dict[str, dict]:
    """Per table: the header lines the markdown serializer emits (what every slice must start
    with), and the D-037 blank-header test from the column_header flags."""
    ser = chunker.serializer_provider.get_serializer(doc=doc)
    out = {}
    for it, _lvl in doc.iterate_items():
        if not isinstance(it, TableItem):
            continue
        text = ser.serialize(item=it).text
        header_lines, _ = ser.table_serializer.get_header_and_body_lines(table_text=text)
        flags = [c for c in it.data.table_cells if c.column_header]
        out[item_key(str(it.self_ref))] = {
            "header": "".join(header_lines),
            # D-037: blank when column_header flags exist but none starts on row 0
            "blank_by_flags": bool(flags) and not any(c.start_row_offset_idx == 0 for c in flags),
        }
    return out


def _header_cells(header: str) -> list[str]:
    first = header.splitlines()[0] if header else ""
    return [c.strip() for c in first.strip().strip("|").split("|")] if first else []


def d037_output_checks(records: list[dict], headers: dict[str, dict]) -> dict:
    """D-037 item 4 on finished records: every table slice starts with the header row; every
    table slice contains the prefix; every body line starts with ``|``; blank or partial repeated
    headers counted across all tables. Returns the violations (empty lists = pass) and counts."""
    starts, prefix, pipes = [], [], []
    for rec in records:
        if rec["chunk_type"] != "table":
            continue
        key = rec["item"] if rec["item"] in headers else min(rec["table_refs"], key=_table_index)
        header = headers.get(key, {}).get("header", "")
        body = body_of(rec)
        if not header or not body.startswith(header):
            starts.append(rec["chunk_id"])
        if not (rec.get("prefix_source") and rec.get("prefix") and rec["prefix"] in rec["text"]):
            prefix.append(rec["chunk_id"])
        rest = body[len(header) :] if header and body.startswith(header) else body
        bad = [ln for ln in rest.splitlines() if not ln.startswith("|")]
        if bad:
            pipes.append({"chunk_id": rec["chunk_id"], "lines": len(bad)})
    blank = sorted(
        k
        for k, h in headers.items()
        if h["blank_by_flags"] or (h["header"] and not any(_header_cells(h["header"])))
    )
    partial = sorted(
        k
        for k, h in headers.items()
        if k not in blank and h["header"] and not all(_header_cells(h["header"]))
    )
    return {
        "table_slices": sum(1 for r in records if r["chunk_type"] == "table"),
        "header_row_missing": starts,
        "prefix_missing": prefix,
        "body_line_not_pipe": pipes,
        "blank_headers": blank,
        "partial_headers": partial,
    }


# ---- the one chunking path (D-037) ---------------------------------------------------------------


def apply_row_fix(
    doc_dict: dict, pdf_path: Path, row: ManifestRow, cfg: Config
) -> tuple[dict, dict[int, dict]]:
    """The row fix on a copy of the raw Docling export (the export itself is never changed)."""
    fixed = copy.deepcopy(doc_dict)
    with pdfplumber.open(pdf_path) as pdf:
        log = fix_document(fixed, pdf, row.source, cfg.parser.row_fix)
    return fixed, log


@dataclass
class ChunkedUnit:
    records: list[dict]
    fix_log: dict[int, dict]
    doc: DoclingDocument


def chunk_document(
    doc_dict: dict,
    pdf_path: Path,
    row: ManifestRow,
    cfg: Config,
    *,
    chunker: HybridChunker,
    prefix: bool = True,
) -> ChunkedUnit:
    """Raw Docling export -> row fix -> DoclingDocument -> HybridChunker (markdown tables) ->
    chunk records -> unit prefix. ``parse_unit`` and the D-037 re-chunk both call this."""
    fixed, log = apply_row_fix(doc_dict, pdf_path, row, cfg)
    doc = DoclingDocument.model_validate(fixed)
    records = chunk_records(row, list(chunker.chunk(dl_doc=doc)), chunker, cfg, fix_log=log)
    if prefix:
        records = apply_prefix(records, prefix_sources(doc), chunker)
    return ChunkedUnit(records, log, doc)


def rowfix_json(unit_id: str, fix_log: dict[int, dict]) -> str:
    """``<unit>.rowfix.json``: the same bytes as the port gate's emit log
    (``scripts/a1_diag/rung1b/port_parity.py``), so the two can be compared by hash."""
    return json.dumps({"unit": unit_id, "tables": fix_log})


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
    reused: bool = False  # already on disk from an earlier run; never re-parsed


# ---- durable per-unit output (resumability) ---------------------------------------------------


def unit_paths(cfg: Config, repo: Path, unit_id: str) -> tuple[Path, Path, Path]:
    """(docling document json, chunk records jsonl, parse provenance json) for one unit."""
    d = repo / cfg.paths.parsed_dir
    return d / f"{unit_id}.json", d / f"{unit_id}.chunks.jsonl", d / f"{unit_id}.meta.json"


def rowfix_path(cfg: Config, repo: Path, unit_id: str) -> Path:
    """The row fix's per-table log, beside the raw export (D-037; D-040 keys on it)."""
    return repo / cfg.paths.parsed_dir / f"{unit_id}.rowfix.json"


def already_parsed(cfg: Config, repo: Path, unit_id: str) -> bool:
    """A unit counts as parsed only when BOTH the document and its chunk records are on disk and
    non-empty. Interrupted units leave neither (writes are atomic), so a resumed run re-does only
    the unit that was in flight."""
    doc, chunks, _ = unit_paths(cfg, repo, unit_id)
    return doc.exists() and doc.stat().st_size > 0 and chunks.exists() and chunks.stat().st_size > 0


def _atomic_write(path: Path, text: str) -> None:
    """Write via a temp file in the same directory then ``os.replace`` (atomic on Windows and
    POSIX), so an interrupted parse never leaves a half-written document or chunk file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def parse_provenance(cfg: Config, *, backend: str, seconds: float, n_chunks: int) -> dict:
    """What produced this parse. Units parsed on different devices or library versions must be
    tellable apart later (D-032), so this travels with the unit and onto the manifest row."""
    try:
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        torch_v = torch.__version__
    except Exception:  # noqa: BLE001
        device, torch_v = "cpu", None
    return {
        "docling": version("docling"),
        "docling_core": version("docling-core"),
        "docling_ibm_models": version("docling-ibm-models"),
        "docling_parse": version("docling-parse"),
        "torch": torch_v,
        "backend": backend,
        "table_mode": cfg.parser.table_mode,
        "do_ocr": cfg.parser.do_ocr,
        "device": device,
        "max_tokens": cfg.chunking.max_tokens,
        "seconds": round(seconds, 2),
        "n_chunks": n_chunks,
        "parsed_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
    }


def provenance_note(p: dict) -> str:
    return (
        f"parse: docling {p['docling']} backend={p['backend']} table_mode={p['table_mode']} "
        f"do_ocr={p['do_ocr']} device={p['device']} {p['seconds']}s chunks={p['n_chunks']} "
        f"at {p['parsed_at']}"
    )


def parse_unit(
    cfg: Config,
    repo: Path,
    row: ManifestRow,
    *,
    converter=None,
    chunker=None,
    backend: str | None = None,
) -> UnitParse:
    backend_name = backend or cfg.parser.pdf_backend
    converter = converter or build_converter(cfg, backend=backend_name)
    chunker = chunker or build_chunker(cfg)
    doc_path, chunks_path, meta_path = unit_paths(cfg, repo, row.unit_id)
    pdf = repo / cfg.paths.raw_dir / row.source / f"{row.unit_id}.pdf"
    t0 = time.perf_counter()
    try:
        result = converter.convert(pdf)
        doc_dict = result.document.export_to_dict()
        unit = chunk_document(doc_dict, pdf, row, cfg, chunker=chunker)
        records = unit.records
        seconds = time.perf_counter() - t0
        prov = parse_provenance(cfg, backend=backend_name, seconds=seconds, n_chunks=len(records))
        # Document first, then chunks: `already_parsed` requires both, so a crash between the two
        # leaves the unit un-parsed rather than half-parsed. `<unit>.json` is the RAW export.
        _atomic_write(doc_path, json.dumps(doc_dict, ensure_ascii=False))
        _atomic_write(rowfix_path(cfg, repo, row.unit_id), rowfix_json(row.unit_id, unit.fix_log))
        _atomic_write(
            chunks_path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
        )
        _atomic_write(meta_path, json.dumps(prov, ensure_ascii=False, indent=1))
    except Exception as exc:  # noqa: BLE001 - a failed unit is data, not a crash
        return UnitParse(row.unit_id, row.pages or 0, 0, 0, 0, time.perf_counter() - t0, str(exc))
    row.notes = [n for n in row.notes if not n.startswith("parse:")] + [provenance_note(prov)]
    tables = {t for r in records if r["chunk_type"] == "table" for t in r["table_refs"]}
    return UnitParse(
        unit_id=row.unit_id,
        pages=row.pages or 0,
        n_chunks=len(records),
        n_table_chunks=sum(1 for r in records if r["chunk_type"] == "table"),
        distinct_tables=len(tables),
        seconds=seconds,
        records=records,
    )


def load_parsed_unit(cfg: Config, repo: Path, row: ManifestRow) -> UnitParse:
    """Rebuild a UnitParse from disk for an already-parsed unit — no Docling call."""
    _, chunks_path, _ = unit_paths(cfg, repo, row.unit_id)
    records = [
        json.loads(ln) for ln in chunks_path.read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    tables = {t for r in records if r["chunk_type"] == "table" for t in r["table_refs"]}
    return UnitParse(
        unit_id=row.unit_id,
        pages=row.pages or 0,
        n_chunks=len(records),
        n_table_chunks=sum(1 for r in records if r["chunk_type"] == "table"),
        distinct_tables=len(tables),
        seconds=0.0,
        records=records,
        reused=True,
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
        "reused": up.reused,
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

    @property
    def reused(self) -> list[str]:
        return [u.unit_id for u in self.parsed if u.reused]

    @property
    def fresh(self) -> list[UnitParse]:
        return [u for u in self.parsed if not u.reused]


def eligible_rows(rows: list[ManifestRow]) -> tuple[list[ManifestRow], list[str]]:
    """(parseable, skipped-unfetchable). A row without sha256 was never fetched (D-034)."""
    parseable = [r for r in rows if r.sha256]
    skipped = [r.unit_id for r in rows if not r.sha256]
    return parseable, skipped


def d001_stop_reached(rows: list[ManifestRow], done: int, skipped: int, cfg: Config) -> bool:
    """D-001: the stop fires once every row up to confirm_after_units is parsed or skipped."""
    return (done + skipped) >= min(cfg.ingest.confirm_after_units, len(rows))


def write_chunks(path: Path, parses: list[UnitParse]) -> int:
    """Rebuild the combined chunk file from what is on disk, in manifest order. The per-unit
    ``<unit>.chunks.jsonl`` files are the durable record; this is a convenience concatenation, so
    an interrupted run never leaves it inconsistent with the units that completed."""
    n = 0
    lines: list[str] = []
    for up in parses:
        for rec in up.records:
            lines.append(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    _atomic_write(path, "".join(lines))
    return n


def _progress(line: str) -> None:
    """One line per unit, timestamped, flushed — the owner reads these from a log file.

    ASCII only: an unattended run logs to a Windows console whose encoding is often cp1252, and
    a non-encodable character there is a crash or mojibake in the middle of a 2.7-hour parse.
    """
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {line}".encode("ascii", "replace").decode("ascii"), flush=True)


def run_parse(
    cfg: Config,
    repo: Path,
    *,
    config_path: str,
    limit: int | None = None,
    all_: bool = False,
    workers: int | None = None,
) -> ParseResult:
    header, rows = read_manifest(repo / cfg.paths.manifest)
    # D-040: EXCLUDED rows are never parsed or chunked (their parse moved to
    # data/parsed_excluded/, so "already parsed" would otherwise re-parse them); the manifest is
    # still written back with every row
    active = active_rows(rows)
    parseable, skipped = eligible_rows(active)
    if limit:
        parseable = parseable[:limit]
    if not all_:
        budget = max(cfg.ingest.confirm_after_units - len(skipped), 0)
        parseable = parseable[:budget]
    n_workers = workers if workers is not None else pool_size(cfg)

    todo = [r for r in parseable if not already_parsed(cfg, repo, r.unit_id)]
    done_already = [r for r in parseable if already_parsed(cfg, repo, r.unit_id)]
    _progress(
        f"parse start: {len(parseable)} units in scope | {len(done_already)} already parsed "
        f"(reused) | {len(todo)} to parse | {len(skipped)} unfetchable skipped | "
        f"workers={n_workers} | backend={cfg.parser.pdf_backend} "
        f"table_mode={cfg.parser.table_mode} do_ocr={cfg.parser.do_ocr}"
    )
    for r in done_already:
        _progress(f"REUSED  {r.unit_id} | already parsed, not re-parsed (resumable)")

    t0 = time.perf_counter()
    fresh: list[UnitParse] = []
    if n_workers > 1 and len(todo) > 1:
        fresh = parse_pool(cfg, repo, todo, config_path=config_path, workers=n_workers)
        for u in fresh:
            _progress(
                f"{'FAILED ' if u.error else 'PARSED '} {u.unit_id} | {u.pages}p | "
                f"{u.seconds:.1f}s | chunks={u.n_chunks}" + (f" | {u.error}" if u.error else "")
            )
    else:
        converter = chunker = None
        for i, r in enumerate(todo, 1):
            if converter is None:
                converter, chunker = build_converter(cfg), build_chunker(cfg)
            u = parse_unit(cfg, repo, r, converter=converter, chunker=chunker)
            fresh.append(u)
            rate = (u.pages / u.seconds) if u.seconds and u.pages else 0.0
            _progress(
                f"{'FAILED ' if u.error else 'PARSED '} [{i}/{len(todo)}] {u.unit_id} | "
                f"{u.pages}p | {u.seconds:.1f}s | {rate:.3f} p/s | chunks={u.n_chunks}"
                + (f" | {u.error}" if u.error else "")
            )
    seconds = time.perf_counter() - t0

    # parse_unit set the provenance note on each row object it parsed; persist the manifest so
    # units parsed on different devices or library versions stay tellable apart (D-032 status).
    write_manifest(repo / cfg.paths.manifest, header, rows)

    parses = [load_parsed_unit(cfg, repo, r) for r in done_already] + fresh
    order = {r.unit_id: i for i, r in enumerate(parseable)}
    parses.sort(key=lambda u: order.get(u.unit_id, 0))
    n_chunks = write_chunks(repo / cfg.paths.chunks, parses)
    stopped = not all_ and d001_stop_reached(active, len(parses), len(skipped), cfg)
    _progress(
        f"parse done: {len(parses)} units on disk ({len(fresh)} parsed now, "
        f"{len(done_already)} reused) | {n_chunks} chunks | {seconds:.1f}s this run"
    )
    return ParseResult(parses, skipped, stopped, seconds, n_workers)
