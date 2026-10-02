# Overnight pass 2026-10-01 (run 2026-10-02 UTC): D-037 code + probes, listing fixes

OVERNIGHT START 2026-10-02T04:08:05Z (hard stop 2026-10-02T10:08:05Z)
OVERNIGHT STOP  2026-10-02T04:33Z (all parts done; total ≈ 25 min of the 6 h)

No re-chunk of the pilot. `ledger ingest` was not run. No `table_chunk_share` was computed.
Nothing under `data/parsed/`, `data/raw*/` or `data/chunks.jsonl` was written: sha256 of all
40 files was taken at the start and at the end, and the two manifests are identical
(`reports/overnight_20261001_data_sha256.json`). No decision was logged beyond the Part 0 owner text.

---

## OWNER RULINGS NEEDED

1. **`chunking.markdown_compact_tables`** (`configs/base.yaml`, now `null`; `build_chunker` raises
   until it is set). On the one smoke unit, `govinfo-ERP-2026-table4` (fixed document), the item-4
   checks are green under both values:

   | | padded (`false`, library default) | compact (`true`) |
   |---|---|---|
   | table slices (tbl-0 + tbl-1) | 46 (23 + 23) | 32 (16 + 16) |
   | max table-slice tokens (prefix + headings included) | 481 | 518 |
   | unfixed saved document, in memory | **39** (20 + 19), the 2026-09-26 figure | 34 (18 + 16) |

   Wide rows (1.6 D) are 0 under both values on all 13 units, so wide rows do not decide this.
   The 2026-09-26 "39" was evidently measured with the padded library default (see 1.7).
2. **Wide rows: no ruling needed.** 1.6 D is 0 under both values. One related finding needs a
   ruling instead: `cbo-62735` `tbl-1` (p2, 12×14) has a **header row that is by itself
   ≥ max_tokens** (631 tokens padded, 590 compact). The flattened multi-row header repeats
   "Table 1. Estimated Budgetary Effects of H.R. 8052 – By Fiscal Year, Millions of Dollars – …"
   in every column. In that case `line_chunker.py:82-97,107-111,160-165` emits the header once,
   as its own chunk(s), and **does not repeat it**. That table's slices will fail D-037 item 4
   "every slice starts with the header row" at the re-chunk. No handling was added.
3. **The prefix, per category and flag** (1.6 C, 740 tables). The questions:
   - **"title" definition.** I read it as the nearest preceding `section_header`/`title` item on
     the same page. Many "title only" hits are section headings, not table titles: STEO
     "Overview", AEO "Table of Contents", CBO bill titles. ERP's real titles sit elsewhere:
     table4 p1 has the title in the furniture layer (`page_header` "B-4. Percentage shares…")
     plus a body text item "Table". On p2 the title is a `caption` item ("Table B-4. … Continued"),
     but the `[Percent of nominal GDP]` text item is nearer, so it wins and the caption is not used.
   - **Duplication.** When the title is a section header it is usually also the chunk's last
     heading, and `contextualize` already prepends headings. The prefix then repeats it
     (seen on synthetic data).
   - **Placement.** I put the prefix lines (title, then unit) **before** the headings:
     `text = prefix + "\n" + contextualize(chunk)`.
   - **Literal "bracketed"** means square brackets only. 127 BUDGET "title only" tables have a
     parenthesised unit item ("(In millions of dollars)"-style) earlier on the page. The literal
     rule does not use it.
   - Per category / flag: rule on caption (15), bracketed-unit (3), title only (584),
     nothing (138), and flags (i) 1, (ii) 57, (iii) 23. Tables and examples are below.
4. **`fetch.image_only_page_max_words`** (now `null`; `image_only_pages` raises until it is set).
   sec7's table-image pages are 5–6 images / 12–13 words. The same signature appears on non-table
   pages: covers and back pages (STEO p1 7 words, BALANCES pp1–2 18, FCS pp1, 3 17, DOD p114 12,
   CROSSCUT p98 12) and AEO figure pages (pp12, 16, 23, 30: 11–14 words). Any words-only threshold
   that flags sec7 will flag those as well. FCS / CROSSCUT low `text_layer_ratio` comes from
   **blank** pages (0 images, 0 words; FCS 10, CROSSCUT 8), not image pages.

---

## Timeline (UTC; commit times)

| part | start | end | elapsed | status | commit |
|---|---|---|---|---|---|
| Part 0: decisions.md status lines | 04:08:05 | 04:09:05 | 1 min | done | `ada5adc` |
| Part 1.1–1.5: code + tests | 04:09 | 04:16:25 | 7 min | done | `873e8a0` |
| Part 1.6–1.7: probes + smoke | 04:16 | 04:22:22 | 6 min | done | `8d38f04` |
| Part 2: listing fixes | 04:22 | 04:27:45 | 5 min | done | `4f1e811` |
| Report | 04:28 | 04:33 | 5 min | done | (this commit) |

All parts finished well inside the first hour, so hourly checkpoints did not come up; there was a
commit and push after every part.

## Part 0: done (`ada5adc`)
The owner text was inserted verbatim as the last status line of D-039, D-040, D-001, D-032,
D-036 and D-038. The diff is 9 added lines (6 status lines plus blank separators that match each
entry's existing style). No body edited. CRLF working-tree line endings were preserved.

## Part 1: done

### 1.2 Config and the compact_tables path
- `chunking.table_serializer: markdown`. The validator rejects anything else and names D-037
  (`ledger/config.py`, `ChunkingConfig._markdown_tables`).
- `chunking.markdown_compact_tables: null`. `build_chunker` raises a `RuntimeError` naming D-037
  while it is null. `load_config` still loads (the D-020 pattern). Tests pass both values explicitly.
- The serializer is selected through a serializer provider (`parse.MarkdownTableSerializerProvider`).
  It returns the library's `ChunkingDocSerializer` with `table_serializer=MarkdownTableSerializer()`
  and the class's own default params with only `compact_tables` set. No chunker or serializer
  is patched or subclassed beyond that.
- **How the parameter reaches the table serializer on the chunker path** (installed docling-core
  2.97.1, `.venv/Lib/site-packages/docling_core/transforms/`):
  1. `serializer/markdown.py:180`: the `MarkdownParams.compact_tables` field.
  2. `chunker/hierarchical_chunker.py:205` and `chunker/hybrid_chunker.py:383`: the chunker takes
     its doc serializer from `serializer_provider.get_serializer(doc)`, i.e. our provider.
  3. `chunker/hierarchical_chunker.py:262`: it calls `my_doc_ser.serialize(item=…)`.
  4. `serializer/common.py:363-364`: `my_kwargs = {**self.params.model_dump(), **kwargs}`, so the
     doc serializer's params, including `compact_tables`, become kwargs.
  5. `serializer/common.py:451`: `self.table_serializer.serialize(item=…, **my_kwargs)`.
  6. `serializer/markdown.py:722`: `params = MarkdownParams(**kwargs)`.
  7. `serializer/markdown.py:780`: `if params.compact_tables: table_text = self._compact_table(…)`.
  8. Split: `chunker/hybrid_chunker.py:291` takes the header path only when
     `isinstance(doc_serializer, ChunkingDocSerializer)` (this is why the provider keeps that
     class). Line 295 calls `get_header_and_body_lines` on that text, and line 307 builds
     `LineBasedTokenChunker` with the header as prefix.

  Verified in output by `tests/test_d037.py::test_compact_tables_reaches_the_chunker_table_path`
  (separator `| - |` vs `|---`).

### 1.1 One shared path
`ledger/ingest/parse.py::chunk_document(doc_dict, pdf_path, row, cfg, *, chunker)` runs these
steps, and `parse_unit` calls it after `convert` + `export_to_dict()`:
1. `apply_row_fix`: deep copy, `pdfplumber`, then `rows.fix_document` for every unit. Only
   `parser.row_fix.sources` tables are rebuilt; BUDGET/CBO are logged "out of scope" and left unchanged.
2. `DoclingDocument.model_validate` on the fixed dict.
3. `HybridChunker` with the markdown table serializer.
4. `chunk_records`.
5. The prefix step.

`<unit>.json` stays the raw export. The fix log is written beside it as `<unit>.rowfix.json`,
**byte-for-byte the format of the port gate's `_emit_log/<unit>.json`**, so the two compare by hash.
Every table record gets `parse_path` (rebuilt | fallback | not fired | out of scope) and
`parse_path_by_table`. Prose records get `parse_path: null`. Every record also gets `body_chars`
(the chunker's segment is the last `body_chars` characters of `text`).

### 1.3 The prefix step
`prefix_sources(doc)` + `apply_prefix(records, sources, chunker)`. It is a text transform on
finished records: it never touches the document, `TableItem.captions`, or anything the chunker
reads (tested). Reading order is `doc.iterate_items()` (body layer), restricted to the table's page.
- Unit line: the nearest preceding `caption` item, or text item whose whole text is `[…]`.
- Title: the nearest preceding `section_header` / `title` item.

Each line is the source item's text verbatim. `prefix_source` holds the unit item's `self_ref`;
`prefix_title_source` holds the title's. When nothing is found there is no unit line and
`prefix_source: null`, with no fallback and no carry-over from another page (tested).

### 1.4 Tests (synthetic documents only; every D-037 test runs under compact false and true)
`tests/test_d037.py` (new) and `tests/test_parse.py` (fixture now parametrized over both values).
`test_chunker_switches_read_back`, D-033's switch read-back, is removed and replaced by D-037
item 4's output assertions (`parse.d037_output_checks`):

| item-4 assertion | passing fixture | failing fixture |
|---|---|---|
| every table slice starts with the header row | titled 300-row table | caption on the table: the chunker puts the caption **before** the header in slice 0 (`hybrid_chunker.py:315` strips it only from slices 1..n) |
| every table slice contains the prefix | same | page without a unit item |
| every body line starts with `\|` | same | a record with a stray non-row line |
| blank / partial repeated headers counted | same (0 / 0) | header flags only on row 1 → blank; one empty header cell → partial |

- **Wide row (D-033's open question), recorded, not handled:** a 700-word cell in row 3 with the
  header kept. `line_chunker.py:237-250` cuts the row at the token limit (`current += "\n" + take`)
  and closes the slice. The next slice is the repeated header plus the rest of the row, so the
  continuation line does not start with `|` (body-line check fires). The header is on every slice.
  The chunker's segment stays ≤ 512 tokens.
- Prefix on/off: chunk ids, `body_chars` and body text identical.
- `parse_unit` (fake converter, blank PDF) and `scripts/rechunk_d037.py::rechunk` emit
  byte-identical `chunks.jsonl` and `rowfix.json` for the same document, for an out-of-scope
  source and for an in-scope one (fallback).

### 1.5 `scripts/rechunk_d037.py` (one-off, not a CLI stage)
- Arguments: `out_dir`, `--units …`, and `--config` (the project's override convention).
- Reads `data/parsed/<unit>.json` and `data/raw/<source>/<unit>.pdf` read-only, ACTIVE rows only.
- Refuses an out_dir equal to or inside `data/parsed/`, and also `data/raw*` (tested).
- Deletes a stale `MANIFEST.json` first, writes per-unit files atomically, and writes
  `MANIFEST.json` **last**. The manifest holds sha256 and record count per file, config hash,
  git commit + dirty flag, tokenizer id/class/max_tokens, the item-4 checks per unit, and the
  max table/all token counts. It never computes a share.

### 1.6 Probes (read-only, no chunking)
Script: `scripts/probe_d037.py`; full output: `reports/overnight_20261001_probes.json`.

**A. Inventory.** 13 parsed ACTIVE units, asserted: cbo-59848, cbo-60786, cbo-61959, cbo-62735,
eia-pdf-AEO_Narrative, eia-pdf-steo_full, govinfo-BUDGET-2027-BALANCES, govinfo-BUDGET-2026-DOD,
govinfo-BUDGET-2027-FCS, govinfo-BUDGET-2026-CROSSCUT, govinfo-ERP-2026-table4,
govinfo-ERP-2026-table22, govinfo-CRPT-118hrpt468.
- Every unit has its saved export and raw PDF.
- `govinfo-BUDGET-2027-TAB` is ACTIVE with no parse, as expected.
- Tokenizer loads with `HF_HUB_OFFLINE=1`: `Qwen/Qwen3-Embedding-4B`, snapshot
  `5cf2132abc99cad020ac570b19d031efec650f2b`.
- Data sha256 manifests at start and end are identical (40 files).

**B. Parity through the new path: 13/13 IDENTICAL.**
- sha256(`json.dumps(fixed)`) equals `port_parity.json files.pilot["<unit>.json"].port` for every unit.
- Each fix log equals its `_emit_log` hash.
- 704/704 BUDGET/CBO pins are unchanged on the fixed documents.

Fix-log statuses:

| unit | statuses |
|---|---|
| cbo-59848 / -60786 / -61959 / -62735 | not fired 1 / 1 / 1 / 3 |
| eia-pdf-AEO_Narrative | fallback 1 |
| eia-pdf-steo_full | not fired 18 · rebuilt 10 · fallback 1 |
| BUDGET-2027-BALANCES | not fired 12 · out of scope 1 |
| BUDGET-2026-DOD | not fired 409 · out of scope 86 |
| BUDGET-2027-FCS | not fired 80 · out of scope 24 |
| BUDGET-2026-CROSSCUT | not fired 61 · out of scope 25 |
| ERP-2026-table4 / table22 | rebuilt 2 / rebuilt 2 |
| CRPT-118hrpt468 | not fired 2 |

**C. Prefix resolution per table.** Flags: (i) table between, (ii) no title on page,
(iii) unit item after the title only. "paren" = "title only" tables with a parenthesised item earlier
on the page (informational).

| source | tables | caption | bracketed-unit | title only | nothing | (i) | (ii) | (iii) | paren |
|---|---|---|---|---|---|---|---|---|---|
| cbo_manual | 6 | 0 | 0 | 4 | 2 | 0 | 1 | 0 | 0 |
| eia | 30 | 5 | 0 | 25 | 0 | 0 | 0 | 1 | 0 |
| govinfo_budget | 698 | 10 | 0 | 554 | 134 | 1 | 52 | 21 | 127 |
| govinfo_erp | 4 | 0 | 3 | 1 | 0 | 0 | 2 | 1 | 0 |
| govinfo_crpt | 2 | 0 | 0 | 0 | 2 | 0 | 2 | 0 | 0 |
| **total** | **740** | **15** | **3** | **584** | **138** | **1** | **57** | **23** | **127** |

| unit | tables | caption | bracketed | title only | nothing | (i) | (ii) | (iii) |
|---|---|---|---|---|---|---|---|---|
| cbo-59848 | 1 | | | 1 | | | | |
| cbo-60786 | 1 | | | | 1 | | 1 | |
| cbo-61959 | 1 | | | 1 | | | | |
| cbo-62735 | 3 | | | 2 | 1 | | | |
| eia-pdf-AEO_Narrative | 1 | | | 1 | | | | |
| eia-pdf-steo_full | 29 | 5 | | 24 | | | | 1 |
| BUDGET-2027-BALANCES | 13 | | | 12 | 1 | | 1 | |
| BUDGET-2026-DOD | 495 | 3 | | 451 | 41 | 1 | | 4 |
| BUDGET-2027-FCS | 104 | | | 71 | 33 | | 33 | 11 |
| BUDGET-2026-CROSSCUT | 86 | 7 | | 20 | 59 | | 18 | 6 |
| ERP-2026-table4 | 2 | | 2 | | | | 2 | |
| ERP-2026-table22 | 2 | | 1 | 1 | | | | 1 |
| CRPT-118hrpt468 | 2 | | | | 2 | | 2 | |

Examples (unit · page · table → unit item | title item):
- **caption:**
  - steo_full p39 tbl-11 → caption "Table 4b. U.S. Hydrocarbon Gas Liquids (HGL) and Petroleum Refinery B…" | no title
  - DOD p44 tbl-198 → caption "MISCELLANEOUS SPECIAL FUNDS" | section_header "Special and Trust Fund Receipts (in millions of dollars)"
  - CROSSCUT p52 tbl-41 → caption "Table 3-2. Direct Loan Subsidy Rates, Budget Authority, and Loan Level…" | none
  - steo_full p44 tbl-16 → "Table 6. U.S. Coal Supply, Consumption, and Inventories (million shor…"
  - steo_full p46 tbl-18 → "Table 7b. U.S. Regional Electricity Sales to Ultimate Customers (bil…"
- **bracketed-unit** (only 3 exist):
  - ERP-table4 p1 tbl-0 → "[Percent of nominal GDP]" | no title
  - ERP-table22 p2 tbl-1 → "[Monthly data seasonally adjusted, except as noted]" | section_header "B-22. Civilian labor force, 1929-2025Continued"
  - ERP-table4 p2 tbl-1 → "[Percent of nominal GDP]" | no title (the caption "Table B-4. … Continued" precedes the bracket item)
- **title only:**
  - cbo-59848 p1 tbl-0 | "S. 162, Smith River National Recreation Area Expansion Act"
  - cbo-61959 p1 tbl-0 | "Estimated Budgetary Effects of H.R. 6703, …"
  - cbo-62735 p1 tbl-0 | "H.R. 8052, Veteran Infection Prevention Act"
  - AEO_Narrative p3 tbl-0 | "Table of Contents"
  - steo_full p3 tbl-0 | "Overview"
- **nothing:** cbo-60786 p1 tbl-0; cbo-62735 p4 tbl-2; BALANCES p16 tbl-4; DOD p7 tbl-7; FCS p33 tbl-20.
- **(i) table between** (only 1): DOD p44 tbl-199 → caption "MISCELLANEOUS SPECIAL FUNDS", which belongs to tbl-198 | "Program and Financing (in millions of dollars)".
- **(ii) no title on page:** cbo-60786 p1 tbl-0; BALANCES p16 tbl-4; FCS p33 tbl-20; CROSSCUT p15 tbl-7; ERP-table4 p1 tbl-0 (title in the furniture layer).
- **(iii) unit after the title only:**
  - steo_full p5 tbl-2 | "Global oil prices"
  - DOD p44 tbl-194 | "Program and Financing -Continued"
  - FCS p51 tbl-38 | "Table 7. DIRECT LOANS: SUBSIDY REESTIMATES 1 - Continued"
  - CROSSCUT p13 tbl-5 | the page's title follows the table
  - ERP-table22 p1 tbl-0 | "Labor Market Indicators". Here the caption "Table B-22. Civilian labor force … [Monthly data seasonally adjusted, …]" comes **after** the table in Docling's reading order.

**D. Wide rows.** A row counts when its markdown line plus the repeated header lines exceeds
max_tokens, by the library's criterion `count(line) + prefix_len > max_tokens`.
**0 rows in every unit under both values** (17,925 body rows in total). Tables whose header alone
is ≥ max_tokens: 1 under both values (`cbo-62735 tbl-1`; ruling 2 above).

### 1.7 Smoke: `govinfo-ERP-2026-table4` only
`scripts/smoke_d037.py` ran `scripts/rechunk_d037.py` into `data/rechunk_smoke/compact_false/` and
`…/compact_true/` (gitignored; override yamls there). The unfixed saved document was chunked in memory.

| | compact_false | compact_true |
|---|---|---|
| chunks / table slices | 52 / 46 | 38 / 32 |
| parse_path | rebuilt | rebuilt |
| prefix_source | `#/texts/2` (p1), `#/texts/6` (p2) | same |
| header-row missing / prefix missing / non-`\|` body lines | 0 / 0 / 0 | 0 / 0 / 0 |
| blank / partial headers | 0 / 0 | 0 / 0 |
| max table-slice tokens | 481 | 518 |
| **unfixed document: table slices** | **39** | 34 |

**The "39 slices" record** is not in any tracked file or local report. It was found only in
a local Claude Code session log summary (2026-09-26/28 sessions): "markdown serializer in temp gave
ERP 90→39 slices and STEO 683→460". The setting it used is not stated there. The **unfixed document
under compact_false (the library default) gives exactly 39**; compact_true gives 34.
Full output: `reports/overnight_20261001_smoke.json`.

## Part 2: done (`4f1e811`)
- **Image-only MEASURE.** `ledger/ingest/fetch.py::page_measures` gives, per page, the embedded-image
  count (pypdf `len(page.images)`) and text-layer word count (pypdf `extract_text().split()`, the
  reader `text_layer_ratio` uses).
  - `image_only_pages(measures, cfg)` (≥ 1 image and ≤ the threshold) raises while
    `fetch.image_only_page_max_words` is null.
  - Test: sec7's measured values are asserted (skipped when the file is absent). No test asserts
    that any pilot unit is unflagged.
  - Data: `reports/overnight_20261001_image_pages.json`.
  - **sec7, per page (images/words):** 1:0/2 · 2:0/176 · 3:6/12 · 4:0/216 · 5:6/12 · 6:6/13 · 7:6/12 ·
    8:0/207 · 9:6/12 · 10:6/13 · 11:6/12 · 12:0/210 · 13:6/12 · 14:6/13 · 15:6/12 · 16:0/128 · 17:6/12 ·
    18:0/216 · 19:6/12 · 20:6/13 · 21:6/12 · 22:5/13 · 23:5/12 · 24:6/13 · 25:6/12 · 26:6/13 · 27:6/12 ·
    28:0/562 · 29:0/358 · 30:0/344 · 31:0/283 · 32:0/72.
  - **Pilot units** (pages · pages with images · image-page words · zero-word pages):

    | unit | pages | pages with images | image-page words | zero-word pages |
    |---|---|---|---|---|
    | cbo-59848 | 2 | 2 | 86, 320 | 0 |
    | cbo-60786 | 2 | 2 | 50, 270 | 0 |
    | cbo-61959 | 3 | 3 | 486–596 | 0 |
    | cbo-62735 | 5 | 5 | 78–446 | 0 |
    | AEO_Narrative | 33 | 26 | p1 6, p12 11, p16 11, p23 14, p30 12, rest 147–556 | 0 |
    | steo_full | 56 | 25 | p1 7, p30 48, rest 103–458 | 0 |
    | BALANCES | 25 | 3 | p1 18, p2 18, p25 12 | 0 |
    | DOD | 114 | 1 | p114 12 | 3 (pp2, 111, 113; no images) |
    | FCS | 120 | 3 | p1 17, p3 17, p120 12 | 10 (no images) |
    | CROSSCUT | 98 | 2 | p80 189, p98 12 | 8 (no images) |
    | ERP table4 / table22 | 2 / 2 | 0 / 0 | – | 0 |
    | CRPT-118hrpt468 | 65 | 2 | p22 32, 325 | 0 |

    (CBO pages all carry a logo image, hence images on every page.)
  - **FCS, page by page:** pages with 0 words and 0 images: 2, 4, 6, 8, 18, 26, 30, 76, 116, 119.
    Images: p1 1/17, p3 1/17, p120 1/12. All other pages have 0 images and 147–608 words.
  - **CROSSCUT, page by page:** pages with 0 words and 0 images: 2, 8, 44, 46, 90, 92, 96, 97.
    Low-word pages without images: p1 14, p3 14, p7 6, p45 8, p91 4. Images: p80 1/189, p98 1/12.
    All other pages have 0 images and 88–802 words.
    The full per-page lists are in the JSON.
- **Pre-draw pdfLink rule.** `ledger/ingest/listing.py::report_pdf_link` / `resolvable_reports`
  apply D-034 status 2026-09-20 (owner decisions closing T2), item (2), now `decisions.md:441`.
  - A report-level unit resolves via the package's pdfLink, or else the single granule's
    (package with exactly one granule, as `fetch.resolve_package_pdf` resolved CRPT-118hrpt468).
  - Packages without one are excluded **before** the draw. This applies in the report branch, to
    the granule-branch `pool_reports`, and to the CRPT filtered pool. Exclusions are listed in the
    outcome's `extra`.
  - `_pkg_row` now refuses `url=None`; this replaces the unchecked `url=p.pdf_link` that was at `listing.py:338`.
  - Tests (`tests/test_listing.py`, fake GovInfo client, `run_listing` end to end with EIA/CBO
    stubbed): BUDGET-2027-TAB's shape is excluded before the draw; a single-granule package
    resolves with a note; a CRPT pool member without a link is excluded.
- Nothing was listed or fetched.

## Tests / lint
- `uv run pytest`: **179 passed, 3 skipped, 1 xfailed**.
  - Skips: `test_mer_absent` lock / Qdrant / BM25, which do not exist yet.
  - xfail: `test_mer_absent_from_chunks`, the pre-re-chunk `chunks.jsonl`, by design.
- `uv run ruff check .`: all checks passed. `ruff format --check .`: 108 files already formatted.

## Conservative choices
1. `reports/*` is gitignored (`.gitignore:25`). This report and its JSON files were added with
   `git add -f` for those exact paths. `.gitignore` is unchanged.
2. The D-034 rule: four status lines share the date 2026-09-20 (`decisions.md:438-441`). I used the
   one matching the brief's description: owner decisions closing T2, item (2), at `:441`.
3. CRPT: the 40-package sample is drawn before any summary exists, so the pdfLink rule filters
   the passed pool before the unit draw, not the sample.
4. A chunk spanning tables with different paths gets `parse_path = fallback` if any of them is
   fallback (the safe side of D-040's sampling rule). `parse_path_by_table` keeps the detail.
5. Item 4 "starts with the header row" is evaluated on the chunker's segment, because
   contextualize prepends headings and the prefix goes before them.
6. Prefix: square brackets only; title = section_header/title label; body layer only.
   Flag (iii) uses the page's first title when none precedes the table.
7. `scripts/rechunk_d037.py` also refuses `data/raw*` as out_dir, and takes `--config` (the
   project's override convention) in addition to out_dir and units.
8. Probe D also reports tables whose header alone is ≥ max_tokens, because that is where the
   library stops repeating the header.

## Things that looked wrong (for the owner; nothing changed because of them)
- `cbo-62735 tbl-1`'s header alone is ≥ max_tokens, so its header will not be repeated (ruling 2).
- Captioned tables: the chunker puts a caption before the header in slice 0 only. Pilot
  `TableItem.captions` are empty (D-037 Defect), so the pilot should not hit this, but units parsed
  later could.
- The smoke manifests record `git.dirty: true`. The smoke ran on `873e8a0` with the probe and smoke
  scripts not yet committed; the chunking code itself was committed.
- The compact smoke's max table slice is 518 tokens (> 512) because the prefix and headings stack on
  top, as D-037 item 3 says. The maximum is logged in each MANIFEST.json.
- The report filename says 20261001 as instructed; the run was on 2026-10-02 UTC.

## Commits (all pushed to origin/main)
`ada5adc` Part 0 · `873e8a0` Part 1.1–1.5 · `8d38f04` Part 1.6–1.7 · `4f1e811` Part 2 · this report (next commit).

## Decisions written
None beyond Part 0. The six owner status lines were logged verbatim; no new D-id.
