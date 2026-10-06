"""D-037: markdown table serializer, the one chunking path, the unit prefix, item 4's output
assertions. Synthetic documents built here only (no pilot data, no network: the tokenizer is the
cached embedder tokenizer, as in test_parse.py). Every test runs under both values of
``chunking.markdown_compact_tables`` — the owner has not chosen one."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml
from docling_core.types.doc import (
    BoundingBox,
    CoordOrigin,
    DocItemLabel,
    DoclingDocument,
    ProvenanceItem,
    Size,
    TableCell,
    TableData,
)
from pydantic import ValidationError
from pypdf import PdfWriter

from ledger.config import Config, load_config
from ledger.ingest.manifest import ManifestHeader, ManifestRow, write_manifest
from ledger.ingest.parse import (
    FFFD_IN_NUMBER,
    apply_prefix,
    body_of,
    build_chunker,
    chunk_document,
    d037_output_checks,
    mark_fffd_bars,
    parse_unit,
    prefix_sources,
    strip_leader_runs,
    table_headers,
    unit_paths,
)

pytestmark = pytest.mark.parse

REPO = Path(__file__).resolve().parents[1]
TITLE = "Table B-4. Percent changes in real gross domestic product"
UNIT = "[Percent change, fourth quarter to fourth quarter]"


# ---- fixtures ----------------------------------------------------------------------------------


@pytest.fixture(scope="module", params=[False, True], ids=["padded", "compact"])
def cfg(base_config_path: Path, request) -> Config:
    base = load_config(base_config_path)
    return base.model_copy(
        update={
            "chunking": base.chunking.model_copy(update={"markdown_compact_tables": request.param})
        }
    )


@pytest.fixture(scope="module")
def chunker(cfg):
    return build_chunker(cfg)


@pytest.fixture(scope="module")
def pdf(tmp_path_factory) -> Path:
    """A blank page: the row fix finds no text-layer lines (an in-scope table falls back)."""
    p = tmp_path_factory.mktemp("pdf") / "blank.pdf"
    w = PdfWriter()
    w.add_blank_page(612, 792)
    w.add_blank_page(612, 792)
    w.write(str(p))
    return p


def _row(uid: str = "u1", source: str = "cbo_manual") -> ManifestRow:
    return ManifestRow(
        unit_id=uid,
        source=source,
        parent_series="X",
        unit_kind="report",
        fetch_method="direct",
        title="t",
        date_issued=None,
        url="https://example.invalid/x.pdf",
        sha256="a" * 64,
        snapshot_date="2026-10-01",
    )


def _prov(page: int = 1) -> ProvenanceItem:
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(l=50, t=700, r=550, b=100, coord_origin=CoordOrigin.BOTTOMLEFT),
        charspan=(0, 0),
    )


def _table(
    rows: int,
    *,
    header_row: int | None = 0,
    blank_cell: bool = False,
    wide: int = 0,
    header_words: int = 0,
) -> TableData:
    cells = []
    for r in range(rows):
        for c in range(4):
            if r == 0 and header_words:
                text = f"H{c} " + "word " * header_words
            elif r == 0:
                text = "" if (blank_cell and c == 2) else ("Year" if c == 0 else f"Q{c}")
            else:
                text = f"{1990 + r}" if c == 0 else f"{r}.{c}"
            if wide and r == 3 and c == 1:
                text = "word " * wide
            cells.append(
                TableCell(
                    text=text,
                    row_span=1,
                    col_span=1,
                    start_row_offset_idx=r,
                    end_row_offset_idx=r + 1,
                    start_col_offset_idx=c,
                    end_col_offset_idx=c + 1,
                    column_header=(header_row is not None and r == header_row),
                )
            )
    return TableData(num_rows=rows, num_cols=4, table_cells=cells)


def _doc(
    rows: int = 300,
    *,
    title: str | None = TITLE,
    unit: str | None = UNIT,
    caption: str | None = None,
    unit_page: int = 1,
    table_page: int = 1,
    unit_after_table: bool = False,
    **table_kw,
) -> DoclingDocument:
    doc = DoclingDocument(name="synthetic")
    doc.add_page(page_no=1, size=Size(width=612, height=792))
    doc.add_page(page_no=2, size=Size(width=612, height=792))
    if title:
        doc.add_heading(text=title, prov=_prov(1))
    if unit and not unit_after_table:
        doc.add_text(label=DocItemLabel.TEXT, text=unit, prov=_prov(unit_page))
    kw = {}
    if caption:
        kw["caption"] = doc.add_text(label=DocItemLabel.CAPTION, text=caption, prov=_prov(1))
    doc.add_table(data=_table(rows, **table_kw), prov=_prov(table_page), **kw)
    if unit and unit_after_table:
        doc.add_text(label=DocItemLabel.TEXT, text=unit, prov=_prov(unit_page))
    return doc


def _chunk(doc, pdf, cfg, chunker, *, source="cbo_manual", prefix=True):
    return chunk_document(
        doc.export_to_dict(), pdf, _row(source=source), cfg, chunker=chunker, prefix=prefix
    )


def _checks(unit, chunker):
    """chunk_document computes the item-4 checks; recomputing them must agree."""
    again = d037_output_checks(unit.records, table_headers(unit.doc, chunker), unit.sources)
    assert again == unit.checks
    return unit.checks


def _tables(records):
    return [r for r in records if r["chunk_type"] == "table"]


# ---- 1.2 config ----------------------------------------------------------------------------------


def test_table_serializer_pinned_to_markdown(base_config_path: Path):
    data = yaml.safe_load(base_config_path.read_text("utf-8"))
    assert data["chunking"]["table_serializer"] == "markdown"
    data["chunking"]["table_serializer"] = "triplet"
    with pytest.raises(ValidationError, match="D-037"):
        Config.model_validate(data)


def test_compact_tables_owner_value_and_null_guard(base_config_path: Path):
    """D-037 status 2026-10-02 (ruling 1): false. A null still loads and build_chunker raises at
    the use site, naming D-037 (the D-020 pattern)."""
    cfg = load_config(base_config_path)
    assert cfg.chunking.markdown_compact_tables is False
    null = cfg.model_copy(
        update={"chunking": cfg.chunking.model_copy(update={"markdown_compact_tables": None})}
    )
    with pytest.raises(RuntimeError, match="D-037"):
        build_chunker(null)


def test_compact_tables_reaches_the_chunker_table_path(pdf, cfg, chunker):
    """The setting is visible in what the chunker emits (padded vs minimal separator row)."""
    unit = _chunk(_doc(), pdf, cfg, chunker)
    body = body_of(_tables(unit.records)[1])
    sep = body.splitlines()[1]
    if cfg.chunking.markdown_compact_tables:
        assert sep == "| - | - | - | - |"
    else:
        assert sep.startswith("|---") and " - " not in sep


# ---- 1.4 item 4: each assertion passes on a clean table and fails on a fixture -------------------


def test_item4_all_pass_on_a_clean_titled_unit_table(pdf, cfg, chunker):
    unit = _chunk(_doc(), pdf, cfg, chunker)
    c = _checks(unit, chunker)
    assert c["table_slices"] > 1
    assert c["header_row_missing"] == [] and c["header_not_repeated"] == []
    assert c["unit_line_missing"] == [] and c["prefix_integrity"] == []
    assert c["title_printed_by_prefix"] == {"slices": 0, "tables": []}
    assert c["body_line_not_pipe"] == []
    assert c["blank_headers"] == [] and c["partial_headers"] == []


def test_item4_header_row_fails_when_a_caption_preamble_leads_slice_0(pdf, cfg, chunker):
    """Fixture that fails 'every table slice starts with the header row': with a caption the
    chunker puts the caption before the header in slice 0 and strips it from slices 1..n
    (hybrid_chunker.py segment(), the preamble path). Recorded, not handled."""
    unit = _chunk(_doc(caption="Table 7. In millions of dollars"), pdf, cfg, chunker)
    tables = _tables(unit.records)
    c = _checks(unit, chunker)
    assert c["header_row_missing"] == [tables[0]["chunk_id"]]
    assert body_of(tables[0]).startswith("Table 7. In millions of dollars")


def test_unit_line_missing_lists_a_title_only_table_while_integrity_holds(pdf, cfg, chunker):
    """D-037 status 2026-10-02, ruling 3 (3): the original reading is reported, not required;
    prefix_integrity (the found title is in the text, via the headings) has no violation."""
    unit = _chunk(_doc(unit=None), pdf, cfg, chunker)
    tables = _tables(unit.records)
    assert all(r["prefix_source"] is None for r in tables)
    c = _checks(unit, chunker)
    assert c["unit_line_missing"] == [r["chunk_id"] for r in tables]
    assert c["prefix_integrity"] == []


def test_prefix_integrity_fails_when_a_found_item_is_absent(pdf, cfg, chunker):
    unit = _chunk(_doc(), pdf, cfg, chunker)
    rec = dict(_tables(unit.records)[1])
    rec["text"] = rec["text"].replace(UNIT, "")  # the unit line lives in the prefix, not the body
    c = d037_output_checks([rec], table_headers(unit.doc, chunker), unit.sources)
    assert c["prefix_integrity"] == [{"chunk_id": rec["chunk_id"], "missing": ["unit"]}]
    rec["text"] = rec["text"].replace(TITLE, "")
    c = d037_output_checks([rec], table_headers(unit.doc, chunker), unit.sources)
    assert c["prefix_integrity"] == [{"chunk_id": rec["chunk_id"], "missing": ["unit", "title"]}]


def test_item4_body_line_check_fails_on_a_non_pipe_line(pdf, cfg, chunker):
    unit = _chunk(_doc(), pdf, cfg, chunker)
    rec = dict(_tables(unit.records)[1])
    extra = ("" if rec["text"].endswith("\n") else "\n") + "stray text"
    rec["text"] += extra
    rec["body_chars"] += len(extra)
    c = d037_output_checks([rec], table_headers(unit.doc, chunker), unit.sources)
    assert c["body_line_not_pipe"] == [{"chunk_id": rec["chunk_id"], "lines": 1}]


def test_item4_blank_header_counted(pdf, cfg, chunker):
    """D-037: blank when column_header flags exist but none starts on row 0."""
    unit = _chunk(_doc(rows=30, header_row=1), pdf, cfg, chunker)
    c = _checks(unit, chunker)
    assert c["blank_headers"] == ["tbl-0"]


def test_item4_partial_header_counted(pdf, cfg, chunker):
    unit = _chunk(_doc(rows=30, blank_cell=True), pdf, cfg, chunker)
    c = _checks(unit, chunker)
    assert c["partial_headers"] == ["tbl-0"] and c["blank_headers"] == []


def test_wide_row_with_header_kept_is_recorded_not_handled(pdf, cfg, chunker):
    """D-033's open question: a single row wider than max_tokens with the header kept. RECORDS
    what the pinned docling-core 2.97.1 emits (line_chunker.py chunk_text: the row is cut at the
    token limit, ``"\\n" + take`` closes the slice, the next slice is the header + the rest of the
    row). No handling is added; a library change flips this test."""
    unit = _chunk(_doc(rows=10, wide=700), pdf, cfg, chunker)
    tables = _tables(unit.records)
    c = _checks(unit, chunker)
    assert len(tables) >= 2
    assert c["header_row_missing"] == []  # the header is kept on every slice
    assert c["body_line_not_pipe"], "the cut row continues on a line that is not a table row"
    header = table_headers(unit.doc, chunker)["tbl-0"]["header"]
    cont = body_of(tables[1])[len(header) :]
    assert not cont.startswith("|")  # slice 1 resumes mid-row under the repeated header
    assert all(chunker.tokenizer.count_tokens(body_of(r)) <= 512 for r in tables)


# ---- 1.3 the prefix ----------------------------------------------------------------------------


def test_prefix_is_verbatim_and_sourced(pdf, cfg, chunker):
    unit = _chunk(_doc(), pdf, cfg, chunker)
    src = prefix_sources(unit.doc)["tbl-0"]
    assert src["category"] == "bracketed-unit"
    for r in _tables(unit.records):
        assert r["prefix"] == UNIT  # the title equals the last heading: not printed again
        assert r["text"].startswith(r["prefix"] + "\n")
        assert r["prefix_source"] == src["unit"]["ref"] and src["unit"]["text"] == UNIT
        assert r["prefix_title_source"] == src["title"]["ref"]
        assert r["prefix_category"] == "bracketed-unit" and r["title_own"] and r["own_source"]


def test_title_equal_to_the_last_heading_appears_once(pdf, cfg, chunker):
    """D-037 status 2026-10-02, ruling 3 (2): the chunker already prepends the heading."""
    unit = _chunk(_doc(), pdf, cfg, chunker)
    for r in _tables(unit.records):
        assert r["headings"][-1] == TITLE
        assert r["text"].count(TITLE) == 1 and r["prefix_title_printed"] is False


def test_a_title_that_differs_from_the_last_heading_is_printed(chunker):
    rec = {
        "chunk_id": "u::p1::tbl-0::s0",
        "chunk_type": "table",
        "item": "tbl-0",
        "table_refs": ["tbl-0"],
        "headings": ["Section 2"],
        "text": "Section 2\n| a |\n| - |\n| 1 |",
        "n_tokens": 0,
        "body_chars": 19,
        "prefix": None,
        "prefix_source": None,
        "prefix_title_source": None,
    }
    title = {"ref": "#/texts/9", "label": "title", "text": "Table 9. Outlays", "page": 1}
    src = {
        "page": 1,
        "unit": None,
        "title": title,
        "category": "title only",
        "flags": {},
        "title_own": True,
        "own_source": True,
    }
    out = apply_prefix([rec], {"tbl-0": src}, chunker)[0]
    assert out["prefix"] == "Table 9. Outlays" and out["prefix_title_printed"] is True
    assert out["text"] == "Table 9. Outlays\n" + rec["text"]
    assert body_of(out) == body_of(rec)


def test_prefix_on_off_leaves_ids_boundaries_and_body_identical(pdf, cfg, chunker):
    on = _chunk(_doc(), pdf, cfg, chunker, prefix=True).records
    off = _chunk(_doc(), pdf, cfg, chunker, prefix=False).records
    assert [r["chunk_id"] for r in on] == [r["chunk_id"] for r in off]
    assert [r["body_chars"] for r in on] == [r["body_chars"] for r in off]
    assert [body_of(r) for r in on] == [body_of(r) for r in off]
    for a, b in zip(on, off, strict=True):
        assert a["text"] == (a["prefix"] + "\n" + b["text"] if a["prefix"] else b["text"])


def test_prefix_caption_item_is_a_unit_source(pdf, cfg, chunker):
    unit = _chunk(_doc(unit=None, caption="Table 7. In millions of dollars"), pdf, cfg, chunker)
    src = prefix_sources(unit.doc)["tbl-0"]
    assert src["category"] == "caption"
    assert src["unit"]["text"] == "Table 7. In millions of dollars"


def test_prefix_parenthesised_unit_is_not_bracketed(pdf, cfg, chunker):
    """Read literally: only square-bracketed text items qualify; nothing is invented."""
    unit = _chunk(_doc(unit="(In millions of dollars)"), pdf, cfg, chunker)
    src = prefix_sources(unit.doc)["tbl-0"]
    assert src["category"] == "title only" and src["unit"] is None
    assert all(r["prefix_source"] is None for r in _tables(unit.records))
    assert all(r["prefix"] is None for r in _tables(unit.records))  # title = last heading


def test_prefix_never_carries_over_from_another_page(pdf, cfg, chunker):
    unit = _chunk(_doc(title=None, unit_page=1, table_page=2), pdf, cfg, chunker)
    src = prefix_sources(unit.doc)["tbl-0"]
    assert src["category"] == "nothing" and src["flags"]["no_title_on_page"]
    assert all(r["prefix"] is None and r["prefix_source"] is None for r in _tables(unit.records))


def test_prefix_flag_unit_after_title_only(pdf, cfg, chunker):
    unit = _chunk(_doc(unit_after_table=True), pdf, cfg, chunker)
    src = prefix_sources(unit.doc)["tbl-0"]
    assert src["category"] == "title only"
    assert src["flags"]["unit_after_title_only"]


def test_a_unit_item_with_a_table_between_is_not_used(pdf, cfg, chunker):
    """D-037 status 2026-10-02, ruling 3 (1); the title with a table between is not the second
    table's own (clause 4): no own source -> barred."""
    doc = _doc(rows=8)
    doc.add_table(data=_table(8), prov=_prov(1))
    srcs = prefix_sources(doc)
    first, second = srcs["tbl-0"], srcs["tbl-1"]
    assert first["unit"]["text"] == UNIT and first["title_own"] and first["own_source"]
    assert not first["flags"]["table_between"]
    assert second["unit"] is None and second["category"] == "title only"
    assert second["flags"]["table_between"] and second["flags"]["title_table_between"]
    assert not second["title_own"] and not second["own_source"]
    unit = _chunk(doc, pdf, cfg, chunker)
    recs = [r for r in _tables(unit.records) if r["item"] == "tbl-1"]
    assert recs and all(r["prefix_source"] is None for r in recs)
    assert all(r["question_source_barred"]["reasons"] == ["no_own_title"] for r in recs)


def test_prefix_never_changes_the_document(pdf, cfg, chunker):
    doc = _doc()
    before = json.dumps(doc.export_to_dict(), sort_keys=True)
    unit = _chunk(doc, pdf, cfg, chunker)
    assert json.dumps(unit.doc.export_to_dict(), sort_keys=True) == before
    assert all(not t.captions for t in unit.doc.tables)


# ---- 1.1 parse_path and the one path -------------------------------------------------------------


def test_parse_path_from_the_fix_log(pdf, cfg, chunker):
    """BUDGET/CBO pass through (D-039); an in-scope table that cannot be rebuilt is ``fallback``
    (a blank page has no body lines)."""
    out = _chunk(_doc(rows=30), pdf, cfg, chunker, source="cbo_manual")
    assert {r["parse_path"] for r in _tables(out.records)} == {"out of scope"}
    assert out.fix_log == {0: {"status": "out of scope (D-039)"}}
    fb = _chunk(_doc(rows=30), pdf, cfg, chunker, source="eia")
    assert {r["parse_path"] for r in _tables(fb.records)} == {"fallback"}
    assert all(r["parse_path"] is None for r in fb.records if r["chunk_type"] == "prose")


def test_header_not_repeated_lists_a_table_whose_header_alone_exceeds_max_tokens(pdf, cfg, chunker):
    """D-037 status 2026-10-02, ruling 2 (cbo-62735 tbl-1's case): line_chunker.py emits a header
    >= max_tokens once and does not repeat it; the table is listed and barred, nothing handled."""
    unit = _chunk(_doc(rows=40, header_words=160), pdf, cfg, chunker)
    header = table_headers(unit.doc, chunker)["tbl-0"]["header"]
    assert chunker.tokenizer.count_tokens(header) >= 512
    c = _checks(unit, chunker)
    assert c["header_not_repeated"] == ["tbl-0"] and c["header_row_missing"]
    for r in _tables(unit.records):
        assert "header_not_repeated" in r["question_source_barred"]["reasons"]


def test_question_source_barred_carries_each_reason(pdf, cfg, chunker):
    """By criterion only: own source, header repeated, parse path. Prose records carry null."""
    clean = _chunk(_doc(rows=30), pdf, cfg, chunker, source="cbo_manual")
    assert all(
        r["question_source_barred"] == {"barred": False, "reasons": []}
        for r in _tables(clean.records)
    )
    assert all(
        r["question_source_barred"] is None for r in clean.records if r["chunk_type"] == "prose"
    )
    fb = _chunk(_doc(rows=30), pdf, cfg, chunker, source="eia")
    assert all(
        r["question_source_barred"] == {"barred": True, "reasons": ["parse_path_fallback"]}
        for r in _tables(fb.records)
    )
    bare = _chunk(_doc(rows=30, title=None, unit=None), pdf, cfg, chunker, source="cbo_manual")
    assert all(
        r["question_source_barred"]["reasons"] == ["no_own_title"] for r in _tables(bare.records)
    )
    both = _chunk(_doc(rows=30, title=None, unit=None), pdf, cfg, chunker, source="eia")
    assert all(
        r["question_source_barred"]["reasons"] == ["no_own_title", "parse_path_fallback"]
        for r in _tables(both.records)
    )


def _load_script():
    spec = importlib.util.spec_from_file_location("rechunk_d037", REPO / "scripts/rechunk_d037.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tmp_repo(tmp_path: Path, pdf: Path, row: ManifestRow) -> Path:
    repo = tmp_path / "repo"
    write_manifest(
        repo / "data" / "manifest.jsonl",
        ManifestHeader(selection_seed=1, snapshot_date="x", frames={}, pilot_composition={}),
        [row],
    )
    raw = repo / "data" / "raw" / row.source
    raw.mkdir(parents=True)
    (raw / f"{row.unit_id}.pdf").write_bytes(pdf.read_bytes())
    return repo


@pytest.mark.parametrize("source", ["cbo_manual", "eia"])
def test_parse_unit_and_rechunk_script_emit_identical_records(
    tmp_path: Path, pdf, cfg, chunker, source
):
    doc = _doc(rows=120)
    row = _row("u-same", source=source)
    repo = _tmp_repo(tmp_path, pdf, row)

    class _FakeConverter:
        def convert(self, _path):
            return type("R", (), {"document": doc})()

    up = parse_unit(cfg, repo, row, converter=_FakeConverter(), chunker=chunker)
    assert up.error is None, up.error
    doc_p, chunks_p, _ = unit_paths(cfg, repo, "u-same")
    assert json.loads(doc_p.read_text("utf-8")) == json.loads(
        json.dumps(doc.export_to_dict(), ensure_ascii=False)
    )  # <unit>.json is the raw export, never the fixed document

    body = _load_script().rechunk(
        cfg, tmp_path / "out", units=["u-same"], repo=repo, chunker=chunker
    )
    assert (tmp_path / "out" / "u-same.chunks.jsonl").read_bytes() == chunks_p.read_bytes()
    assert (tmp_path / "out" / "u-same.rowfix.json").read_bytes() == (
        repo / "data" / "parsed" / "u-same.rowfix.json"
    ).read_bytes()
    assert set(body["files"]) == {"u-same.chunks.jsonl", "u-same.rowfix.json"}
    assert (tmp_path / "out" / "MANIFEST.json").exists()


def test_rechunk_script_refuses_parsed_dir_and_drops_a_stale_manifest(
    tmp_path: Path, pdf, cfg, chunker
):
    row = _row("u-x")
    repo = _tmp_repo(tmp_path, pdf, row)
    mod = _load_script()
    for bad in (repo / "data" / "parsed", repo / "data" / "parsed" / "sub", repo / "data" / "raw"):
        with pytest.raises(SystemExit, match="refused"):
            mod.rechunk(cfg, bad, units=["u-x"], repo=repo, chunker=chunker)
    out = tmp_path / "out"
    out.mkdir()
    (out / "MANIFEST.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="not ACTIVE units"):
        mod.rechunk(cfg, out, units=["u-x"], repo=repo, chunker=chunker)  # no saved export
    assert not (out / "MANIFEST.json").exists()  # incomplete is visible as incomplete


# ---- item 5: U+FFFD leader strip, the fffd_in_number bar, header_row_cause ----------------------

LEADER = "�" * 40


def _fffd_doc(*, rows: int = 6) -> DoclingDocument:
    """Header row (with a U+FFFD run of its own), then body rows: a label run, a single U+FFFD in
    a label, a run in a value cell, and a sign+U+FFFD+digit value."""
    labels = [f"Defense {LEADER}", "Health �", "Energy", "Space", "Labor", "Veterans"]
    values = ["1,000", "2,000", "5��6", "–�2", "3", "4"]
    grid = [["Func��tion", "2024", "2025"]]
    grid += [[labels[i % 6], values[i % 6], "9"] for i in range(rows)]
    cells = [
        TableCell(
            text=t,
            row_span=1,
            col_span=1,
            start_row_offset_idx=r,
            end_row_offset_idx=r + 1,
            start_col_offset_idx=c,
            end_col_offset_idx=c + 1,
            column_header=(r == 0),
        )
        for r, row in enumerate(grid)
        for c, t in enumerate(row)
    ]
    doc = DoclingDocument(name="synthetic")
    doc.add_page(page_no=1, size=Size(width=612, height=792))
    doc.add_heading(text=TITLE, prov=_prov(1))
    doc.add_text(label=DocItemLabel.TEXT, text=UNIT, prov=_prov(1))
    doc.add_table(data=TableData(num_rows=len(grid), num_cols=3, table_cells=cells), prov=_prov(1))
    return doc


def _first_cells(rec: dict) -> list[str]:
    rows = [ln for ln in body_of(rec).splitlines() if ln.startswith("|")]
    return [ln.split("|")[1].strip() for ln in rows]


def test_item5_label_run_removed_everything_else_kept(pdf, cfg, chunker):
    """Runs of >= 2 go from every body cell (D-037 status 2026-10-06) except a digit-guarded one:
    the value-cell run between digits stays."""
    unit = _chunk(_fffd_doc(), pdf, cfg, chunker)
    (rec,) = _tables(unit.records)
    first = _first_cells(rec)
    assert first[0].startswith("Func��tion")  # header row untouched
    assert "Defense" in first[2] and "�" not in first[2]  # [1] is the separator
    assert "Health �" in first[3]  # a single U+FFFD in a label is kept
    assert "5��6" in body_of(rec)  # digit guard (2026-10-06): digits on both sides
    assert "–�2" in body_of(rec)  # sign + U+FFFD + digit in a value cell is kept
    assert rec["fffd_removed"] == 40 and rec["text"].count("�") == 2 + 1 + 2 + 1
    assert (
        rec["body_chars"]
        == len(body_of(rec))
        == len(rec["text"]) - len(rec["text"].split(body_of(rec))[0])
    )
    assert rec["n_tokens"] == chunker.tokenizer.count_tokens(rec["text"])


def test_item5_ids_slices_and_item4_outputs_unchanged(pdf, cfg, chunker, monkeypatch):
    doc = _fffd_doc(rows=60)
    after = _chunk(doc, pdf, cfg, chunker)
    from ledger.ingest import parse as parse_mod

    monkeypatch.setattr(parse_mod, "strip_leader_runs", lambda recs, _c: recs)
    before = _chunk(doc, pdf, cfg, chunker)
    assert [r["chunk_id"] for r in after.records] == [r["chunk_id"] for r in before.records]
    assert [r["chunk_type"] for r in after.records] == [r["chunk_type"] for r in before.records]
    assert len(_tables(after.records)) > 1
    for k in after.checks:
        assert after.checks[k] == before.checks[k], (
            k
        )  # prefix_integrity stays [], header checks same
    assert after.checks["prefix_integrity"] == []
    assert any(
        r["body_chars"] < b["body_chars"]
        for r, b in zip(after.records, before.records, strict=True)
    )
    # idempotent
    again = strip_leader_runs(after.records, chunker)
    assert [r["text"] for r in again] == [r["text"] for r in after.records]
    assert all(r["fffd_removed"] == 0 for r in _tables(again))


def test_item5_prefix_heading_and_prose_untouched(pdf, cfg, chunker):
    unit = _chunk(_fffd_doc(), pdf, cfg, chunker)
    (rec,) = _tables(unit.records)
    assert rec["prefix"] == UNIT and rec["text"].startswith(UNIT + "\n" + TITLE)
    prose = {"chunk_type": "prose", "text": "a " + LEADER + " b", "body_chars": 40}
    assert strip_leader_runs([prose], chunker) == [prose]


def test_item5_fffd_in_number_bar(pdf, cfg, chunker):
    assert FFFD_IN_NUMBER.search("| x | –�2 |")
    assert FFFD_IN_NUMBER.search("| 1�5 |") and FFFD_IN_NUMBER.search("-�1")
    assert FFFD_IN_NUMBER.search("−�7")
    assert not FFFD_IN_NUMBER.search("5��6")  # a run is not a number gap
    assert not FFFD_IN_NUMBER.search("Health � |")
    (rec,) = _tables(_chunk(_fffd_doc(), pdf, cfg, chunker).records)
    assert rec["question_source_barred"] == {"barred": True, "reasons": ["fffd_in_number"]}
    clean = _chunk(_doc(rows=30), pdf, cfg, chunker)
    assert all(r["question_source_barred"]["barred"] is False for r in _tables(clean.records))
    assert mark_fffd_bars(clean.records) == clean.records


def test_item5_header_row_cause(pdf, cfg, chunker):
    cap = _chunk(_doc(caption="Table 7. In millions of dollars"), pdf, cfg, chunker)
    assert cap.checks["header_not_repeated"] == ["tbl-0"]
    assert {r["header_row_cause"] for r in _tables(cap.records)} == {"caption_on_slice0"}
    big = _chunk(_doc(rows=40, header_words=160), pdf, cfg, chunker)
    assert {r["header_row_cause"] for r in _tables(big.records)} == {"header_over_max_tokens"}
    ok = _chunk(_doc(rows=30), pdf, cfg, chunker)
    assert {r["header_row_cause"] for r in _tables(ok.records)} == {None}
    assert all("header_row_cause" not in r for r in ok.records if r["chunk_type"] == "prose")


def _bs_doc() -> DoclingDocument:
    """A duplicated spanning label cell: U+0008 then a leader run in the SECOND cell (the
    BUDGET-2027-PER shape), a lone U+0008, and a lone U+0008 in a cell whose run is elsewhere."""
    grid = [["Item", "Label", "Value"]]
    grid += [["1", "Opportunity Zones " + "�" * 30, "3,080"]]
    grid += [["2", "Credit  " + "�" * 9, "7"]]
    grid += [["3", "Lone  backspace", "8"]]
    grid += [["4", "Other ", "�" * 5]]
    cells = [
        TableCell(
            text=t,
            row_span=1,
            col_span=1,
            start_row_offset_idx=r,
            end_row_offset_idx=r + 1,
            start_col_offset_idx=c,
            end_col_offset_idx=c + 1,
            column_header=(r == 0),
        )
        for r, row in enumerate(grid)
        for c, t in enumerate(row)
    ]
    doc = DoclingDocument(name="synthetic")
    doc.add_page(page_no=1, size=Size(width=612, height=792))
    doc.add_heading(text=TITLE, prov=_prov(1))
    doc.add_text(label=DocItemLabel.TEXT, text=UNIT, prov=_prov(1))
    doc.add_table(data=TableData(num_rows=len(grid), num_cols=3, table_cells=cells), prov=_prov(1))
    return doc


def test_item5_ext_second_cell_run_and_backspace_removed_through_chunk_document(
    pdf, cfg, chunker, monkeypatch
):
    from ledger.ingest import parse as parse_mod

    doc = _bs_doc()
    after = _chunk(doc, pdf, cfg, chunker)
    monkeypatch.setattr(parse_mod, "strip_leader_runs", lambda recs, _c: recs)
    before = _chunk(doc, pdf, cfg, chunker)
    (rec,) = _tables(after.records)
    body = body_of(rec)
    assert "Opportunity Zones" in body and "Credit" in body
    assert "�" not in body and "" not in body  # every U+0008 goes (2026-10-06)
    assert "Lone  backspace" in body and "Other " in body
    assert rec["fffd_removed"] == 30 + 9 + 5 and rec["u0008_removed"] == 2
    assert [r["chunk_id"] for r in after.records] == [r["chunk_id"] for r in before.records]
    assert after.checks["prefix_integrity"] == []
    assert after.checks == before.checks
    assert rec["n_tokens"] == chunker.tokenizer.count_tokens(rec["text"])


def test_item5_ext_backspace_removed_from_every_record_ids_unchanged(
    pdf, cfg, chunker, monkeypatch
):
    from ledger.ingest import parse as parse_mod

    doc = _bs_doc()
    after = _chunk(doc, pdf, cfg, chunker)
    monkeypatch.setattr(parse_mod, "remove_backspaces", lambda recs, _c: recs)
    before = _chunk(doc, pdf, cfg, chunker)
    assert [r["chunk_id"] for r in after.records] == [r["chunk_id"] for r in before.records]
    assert any("" in r["text"] for r in before.records)  # the transform has work to do
    assert all("" not in r["text"] for r in after.records)
    assert after.checks["prefix_integrity"] == [] and after.checks == before.checks
    for r in _tables(after.records):
        assert r["body_chars"] == len(body_of(r)) and r[
            "n_tokens"
        ] == chunker.tokenizer.count_tokens(r["text"])
