"""T3 parse/chunk tests (D-032, D-033). No network, no model download: the chunker is built
from the tokenizer only, and documents are constructed in memory."""

import re
from pathlib import Path

import pytest
from docling_core.types.doc import DoclingDocument, TableCell, TableData, TableItem

from ledger.config import load_config
from ledger.ingest.manifest import ManifestHeader, ManifestRow, write_manifest
from ledger.ingest.parse import (
    build_chunker,
    chunk_records,
    d001_stop_reached,
    eligible_rows,
    item_key,
)

pytestmark = pytest.mark.parse


def _row(uid: str, sha: str | None = "a" * 64) -> ManifestRow:
    return ManifestRow(
        unit_id=uid,
        source="govinfo_erp",
        parent_series="ERP",
        unit_kind="granule",
        fetch_method="govinfo",
        title=f"T {uid}",
        date_issued="2026-04-01",
        url="https://api.govinfo.gov/x",
        sha256=sha,
        snapshot_date="2026-09-20",
    )


def _doc_with_table(
    name: str, rows: int, cols: int = 4, *, heading: str = "Section 1"
) -> DoclingDocument:
    doc = DoclingDocument(name=name)
    doc.add_heading(text=heading)
    doc.add_text(label="text", text="Prose paragraph about the table that follows. " * 3)
    cells = []
    for r in range(rows):
        for c in range(cols):
            cells.append(
                TableCell(
                    text=(f"Year {1990 + c}" if r == 0 else f"{r}.{c}"),
                    row_span=1,
                    col_span=1,
                    start_row_offset_idx=r,
                    end_row_offset_idx=r + 1,
                    start_col_offset_idx=c,
                    end_col_offset_idx=c + 1,
                    column_header=(r == 0),
                )
            )
    data = TableData(num_rows=rows, num_cols=cols, table_cells=cells)
    doc.add_table(
        data=data, caption=doc.add_text(label="caption", text="Table 1. In millions of dollars")
    )
    return doc


@pytest.fixture(scope="module")
def cfg(base_config_path: Path):
    return load_config(base_config_path)


@pytest.fixture(scope="module")
def chunker(cfg):
    return build_chunker(cfg)


def test_chunker_switches_read_back(chunker, cfg):
    """D-033: the three pinned switches are what the constructed chunker actually carries."""
    assert chunker.repeat_table_header is cfg.chunking.repeat_table_header is True
    assert chunker.omit_header_on_overflow is cfg.chunking.omit_header_on_overflow is False
    assert chunker.merge_peers is cfg.chunking.merge_peers is False
    assert chunker.tokenizer.get_max_tokens() == cfg.chunking.max_tokens == 512


def test_item_key_is_content_derived():
    assert item_key("#/tables/2") == "tbl-2"
    assert item_key("#/texts/15") == "txt-15"


def test_no_chunk_mixes_table_and_prose(chunker, cfg):
    """merge_peers=false: a chunk never carries a table item and an unrelated prose item.
    A table's own caption item does travel with it (D3 'caption attached')."""
    doc = _doc_with_table("mix", rows=6)
    recs = chunk_records(_row("u1"), list(chunker.chunk(dl_doc=doc)), chunker, cfg)
    assert recs, "expected chunks"
    assert not any(r["mixed_items"] for r in recs)
    assert {r["chunk_type"] for r in recs} <= {"table", "prose"}
    assert any(r["chunk_type"] == "table" for r in recs)
    prose = [r for r in recs if r["chunk_type"] == "prose"]
    assert all(not r["table_refs"] for r in prose)


def test_table_item_identity_is_not_isinstance(chunker, cfg):
    """A table small enough not to split arrives with base ``DocItem`` instances; identity has
    to come from self_ref/label or every small table is counted as prose (A9)."""
    from ledger.ingest.parse import is_table_item

    doc = _doc_with_table("small", rows=6)
    chunks = list(chunker.chunk(dl_doc=doc))
    tbl_chunk = next(c for c in chunks if any(is_table_item(i) for i in c.meta.doc_items))
    assert any(
        not isinstance(i, TableItem) and is_table_item(i) for i in tbl_chunk.meta.doc_items
    ), "expected a table doc item that isinstance() does not recognise"


def test_headings_and_captions_on_every_slice(chunker, cfg):
    """prepend_headings -> contextualize(): the heading travels with every slice (D3/D-033)."""
    doc = _doc_with_table("big", rows=400, heading="Appendix B")
    recs = chunk_records(_row("u2"), list(chunker.chunk(dl_doc=doc)), chunker, cfg)
    table_recs = [r for r in recs if r["chunk_type"] == "table"]
    assert len(table_recs) > 1, "a 400-row table must split at max_tokens"
    assert all("Appendix B" in r["text"] for r in table_recs)
    assert all(r["n_tokens"] <= cfg.chunking.max_tokens * 1.2 for r in table_recs)


def test_header_travels_with_every_overflowing_slice(chunker, cfg):
    """D-033's premise: the column header never leaves a slice. The default chunking serializer
    emits triplets (`<row label>, <column header> = <value>`), so each cell carries its own
    header — stronger than a repeated header line, and what makes D-005 chunk-ID citation sound."""
    doc = _doc_with_table("hdr", rows=400)
    recs = chunk_records(_row("u3"), list(chunker.chunk(dl_doc=doc)), chunker, cfg)
    table_recs = [r for r in recs if r["chunk_type"] == "table"]
    assert len(table_recs) > 1
    assert all(re.search(r"Year 199\d", r["text"]) for r in table_recs)


def test_chunk_ids_stable_and_slice_indexed(chunker, cfg):
    """D-032: ids come from content and position; a second unit cannot renumber the first."""
    doc = _doc_with_table("ids", rows=400)
    first = chunk_records(_row("u4"), list(chunker.chunk(dl_doc=doc)), chunker, cfg)
    again = chunk_records(_row("u4"), list(chunker.chunk(dl_doc=doc)), chunker, cfg)
    other = chunk_records(
        _row("u5"), list(chunker.chunk(dl_doc=_doc_with_table("x", 8))), chunker, cfg
    )
    assert [r["chunk_id"] for r in first] == [r["chunk_id"] for r in again]
    assert all(r["chunk_id"].startswith("u4::p") for r in first)
    assert all(r["chunk_id"].startswith("u5::p") for r in other)
    slices = [r["slice"] for r in first if r["chunk_type"] == "table"]
    assert slices == sorted(slices) and slices[0] == 0


def test_unfetchable_row_is_skipped_not_raised():
    rows = [_row("a"), _row("tab", sha=None), _row("b")]
    parseable, skipped = eligible_rows(rows)
    assert [r.unit_id for r in parseable] == ["a", "b"]
    assert skipped == ["tab"]


def test_d001_stop_counts_parsed_plus_skipped(cfg, tmp_path: Path):
    rows = [_row(f"u{i}") for i in range(19)] + [_row("tab", sha=None)]
    write_manifest(
        tmp_path / "m.jsonl",
        ManifestHeader(selection_seed=1, snapshot_date="x", frames={}, pilot_composition={}),
        rows,
    )
    assert not d001_stop_reached(rows, 18, 1, cfg)
    assert d001_stop_reached(rows, 19, 1, cfg)  # 19 parsed + 1 skipped = the 20-unit pilot


def test_resumable_unit_is_reused_not_reparsed(cfg, chunker, tmp_path: Path, monkeypatch):
    """A unit whose document JSON and chunk records both exist is skipped and reused; the parse
    is never re-run (owner decision 2026-09-25, D-032)."""
    from ledger.ingest import parse as parse_mod
    from ledger.ingest.manifest import ManifestHeader, write_manifest
    from ledger.ingest.parse import already_parsed, load_parsed_unit, run_parse, unit_paths

    row = _row("u-res")
    write_manifest(
        tmp_path / "data" / "manifest.jsonl",
        ManifestHeader(selection_seed=1, snapshot_date="x", frames={}, pilot_composition={}),
        [row],
    )
    doc_p, chunks_p, _ = unit_paths(cfg, tmp_path, "u-res")
    doc_p.parent.mkdir(parents=True, exist_ok=True)
    doc_p.write_text('{"name": "u-res"}', encoding="utf-8")
    recs = chunk_records(row, list(chunker.chunk(dl_doc=_doc_with_table("r", 6))), chunker, cfg)
    chunks_p.write_text("".join(__import__("json").dumps(r) + "\n" for r in recs), encoding="utf-8")
    assert already_parsed(cfg, tmp_path, "u-res")
    assert load_parsed_unit(cfg, tmp_path, row).reused

    def _boom(*a, **k):  # any parse attempt is a failure of the resume rule
        raise AssertionError("parse_unit called for an already-parsed unit")

    monkeypatch.setattr(parse_mod, "parse_unit", _boom)
    monkeypatch.setattr(parse_mod, "build_converter", _boom)
    res = run_parse(cfg, tmp_path, config_path=str(base_cfg_path()), workers=1)
    assert res.reused == ["u-res"] and not res.fresh
    assert res.parsed[0].n_chunks == len(recs)


def base_cfg_path() -> Path:
    return Path(__file__).resolve().parent.parent / "configs" / "base.yaml"


def test_interrupted_unit_leaves_nothing_behind(cfg, tmp_path: Path, monkeypatch):
    """Atomic writes: a crash mid-write leaves no document, no chunk file and no .tmp, so the
    unit is not `already_parsed` and a resumed run redoes exactly it."""
    from ledger.ingest import parse as parse_mod
    from ledger.ingest.parse import already_parsed, parse_unit, unit_paths

    row = _row("u-crash")
    doc_p, chunks_p, meta_p = unit_paths(cfg, tmp_path, "u-crash")

    class _Boom:
        def convert(self, *a, **k):
            raise RuntimeError("interrupted mid-parse")

    up = parse_unit(cfg, tmp_path, row, converter=_Boom(), chunker=object())
    assert up.error and "interrupted" in up.error
    assert not doc_p.exists() and not chunks_p.exists() and not meta_p.exists()
    assert not already_parsed(cfg, tmp_path, "u-crash")

    # and a write that dies after the document but before the chunks is still not "parsed"
    doc_p.parent.mkdir(parents=True, exist_ok=True)
    parse_mod._atomic_write(doc_p, "{}")
    assert doc_p.exists() and not already_parsed(cfg, tmp_path, "u-crash")
    assert not list(doc_p.parent.glob("*.tmp"))


def test_provenance_recorded_on_unit_and_row(cfg):
    """D-032 status: docling version, backend, table_mode, do_ocr, device, seconds, chunks."""
    from ledger.ingest.parse import parse_provenance, provenance_note

    p = parse_provenance(cfg, backend="pypdfium2", seconds=1.5, n_chunks=3)
    assert p["docling"] and p["docling_core"] and p["docling_parse"] and p["docling_ibm_models"]
    assert p["backend"] == "pypdfium2"
    assert p["table_mode"] == cfg.parser.table_mode
    assert p["do_ocr"] is False
    assert p["device"] in {"cpu", "cuda"}
    assert p["seconds"] == 1.5 and p["n_chunks"] == 3 and p["parsed_at"]
    note = provenance_note(p)
    assert note.startswith("parse: docling ") and "device=" in note and "chunks=3" in note


def test_do_ocr_validator_refuses_true(base_config_path: Path):
    import yaml
    from pydantic import ValidationError

    from ledger.config import Config

    data = yaml.safe_load(base_config_path.read_text("utf-8"))
    data["parser"]["do_ocr"] = True
    with pytest.raises(ValidationError, match="do_ocr must be false"):
        Config.model_validate(data)
