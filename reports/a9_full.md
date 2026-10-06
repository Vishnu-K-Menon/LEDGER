# A9 — full corpus (D-001, D-036, D-037; owner 2026-10-06)

Source: `data/chunks.jsonl`, 9678 chunks. Read-only; nothing re-parsed or re-chunked. Counting rule D-036.

**Chunk-count share = 0.434** (4,197 / 9,678); **token-weighted share = 0.804**; 38 units, 5 sources, 1041 pages. Band 0.50–0.70.

## Step 1 — the 11 CBO units

| unit | in sources.csv | sha256 on manifest | chunks |
|---|---|---|---|
| cbo-61071 | True | True | 124 |
| cbo-59842 | True | True | 13 |
| cbo-61099 | True | True | 189 |
| cbo-61720 | True | True | 14 |
| cbo-62771 | True | True | 6 |
| cbo-61118 | True | True | 46 |
| cbo-62774 | True | True | 13 |
| cbo-59828 | True | True | 7 |
| cbo-61934 | True | True | 6 |
| cbo-59853 | True | True | 6 |
| cbo-61964 | True | True | 7 |

Pending: none

## A9 (chunk-count), per source and per unit


`table_chunk_share` = **0.434** · band 0.50–0.70 · **BELOW BAND**


**Counting rule: D-036.** `chunk_type = table` iff the chunk holds ≥ 1 table item and every other doc item is a caption or footnote — Docling emits the caption as its own item, so D-033's literal wording counted every unsplit table as prose. Primary above is that rule: **0.434**. The literal reading, printed once for comparison: **0.432** (4181 of 9678 chunks). The difference is **16 caption-only chunks**. Nothing is re-chunked either way — this is a counting rule (D-032).

## Per source

| scope | units | pages | chunks | table slices | distinct tables | prose chunks | table share |
|---|---|---|---|---|---|---|---|
| cbo_manual | 15 | 41 | 521 | 130 | 25 | 391 | 0.250 |
| eia | 2 | 89 | 956 | 455 | 30 | 501 | 0.476 |
| govinfo_budget | 8 | 829 | 6156 | 3145 | 875 | 3011 | 0.511 |
| govinfo_crpt | 1 | 65 | 1511 | 0 | 0 | 1511 | 0.000 |
| govinfo_erp | 12 | 17 | 534 | 467 | 17 | 67 | 0.875 |
| **TOTAL** | 38 | 1041 | 9678 | 4197 | 947 | 5481 | 0.434 |

## Per unit

| scope | units | pages | chunks | table slices | distinct tables | prose chunks | table share |
|---|---|---|---|---|---|---|---|
| cbo-59828 | 1 | 2 | 7 | 1 | 1 | 6 | 0.143 |
| cbo-59842 | 1 | 3 | 13 | 3 | 2 | 10 | 0.231 |
| cbo-59848 | 1 | 2 | 8 | 1 | 1 | 7 | 0.125 |
| cbo-59853 | 1 | 1 | 6 | 1 | 1 | 5 | 0.167 |
| cbo-60786 | 1 | 2 | 7 | 2 | 1 | 5 | 0.286 |
| cbo-61071 | 1 | 4 | 124 | 2 | 2 | 122 | 0.016 |
| cbo-61099 | 1 | 5 | 189 | 73 | 4 | 116 | 0.386 |
| cbo-61118 | 1 | 5 | 46 | 8 | 2 | 38 | 0.174 |
| cbo-61720 | 1 | 3 | 14 | 9 | 2 | 5 | 0.643 |
| cbo-61934 | 1 | 1 | 6 | 1 | 1 | 5 | 0.167 |
| cbo-61959 | 1 | 3 | 39 | 16 | 1 | 23 | 0.410 |
| cbo-61964 | 1 | 2 | 7 | 1 | 1 | 6 | 0.143 |
| cbo-62735 | 1 | 5 | 36 | 8 | 3 | 28 | 0.222 |
| cbo-62771 | 1 | 1 | 6 | 1 | 1 | 5 | 0.167 |
| cbo-62774 | 1 | 2 | 13 | 3 | 2 | 10 | 0.231 |
| eia-pdf-AEO_Narrative | 1 | 33 | 143 | 2 | 1 | 141 | 0.014 |
| eia-pdf-steo_full | 1 | 56 | 813 | 453 | 29 | 360 | 0.557 |
| govinfo-BUDGET-2025-CLIMATE | 1 | 133 | 433 | 103 | 42 | 330 | 0.238 |
| govinfo-BUDGET-2026-CROSSCUT | 1 | 98 | 730 | 534 | 86 | 196 | 0.732 |
| govinfo-BUDGET-2026-DOD | 1 | 114 | 1819 | 991 | 495 | 828 | 0.545 |
| govinfo-BUDGET-2027-BALANCES | 1 | 25 | 80 | 32 | 13 | 48 | 0.400 |
| govinfo-BUDGET-2027-BUD | 1 | 92 | 244 | 19 | 6 | 225 | 0.078 |
| govinfo-BUDGET-2027-FCS | 1 | 120 | 1082 | 998 | 104 | 84 | 0.922 |
| govinfo-BUDGET-2027-OBJCLASS | 1 | 89 | 289 | 205 | 80 | 84 | 0.709 |
| govinfo-BUDGET-2027-PER | 1 | 158 | 1479 | 263 | 49 | 1216 | 0.178 |
| govinfo-CRPT-118hrpt468 | 1 | 65 | 1511 | 0 | 0 | 1511 | 0.000 |
| govinfo-ERP-2026-table1 | 1 | 2 | 42 | 35 | 2 | 7 | 0.833 |
| govinfo-ERP-2026-table19 | 1 | 2 | 90 | 85 | 2 | 5 | 0.944 |
| govinfo-ERP-2026-table22 | 1 | 2 | 38 | 32 | 2 | 6 | 0.842 |
| govinfo-ERP-2026-table30 | 1 | 1 | 59 | 57 | 1 | 2 | 0.966 |
| govinfo-ERP-2026-table4 | 1 | 2 | 52 | 46 | 2 | 6 | 0.885 |
| govinfo-ERP-2026-table42 | 1 | 2 | 82 | 69 | 2 | 13 | 0.841 |
| govinfo-ERP-2026-table43 | 1 | 1 | 49 | 46 | 1 | 3 | 0.939 |
| govinfo-ERP-2026-table44 | 1 | 1 | 17 | 14 | 1 | 3 | 0.824 |
| govinfo-ERP-2026-table46 | 1 | 1 | 15 | 11 | 1 | 4 | 0.733 |
| govinfo-ERP-2026-table48 | 1 | 1 | 13 | 10 | 1 | 3 | 0.769 |
| govinfo-ERP-2026-table50 | 1 | 1 | 42 | 33 | 1 | 9 | 0.786 |
| govinfo-ERP-2026-table54 | 1 | 1 | 35 | 29 | 1 | 6 | 0.829 |

## Token-weighted share, per source

| source | token-weighted | chunk-count |
|---|---|---|
| cbo_manual | 0.757 | 0.250 |
| eia | 0.877 | 0.476 |
| govinfo_budget | 0.812 | 0.511 |
| govinfo_crpt | 0.000 | 0.000 |
| govinfo_erp | 0.992 | 0.875 |

Per unit (token-weighted / chunk-count):

| unit | token-weighted | chunk-count |
|---|---|---|
| cbo-59828 | 0.372 | 0.143 |
| cbo-59842 | 0.603 | 0.231 |
| cbo-59848 | 0.383 | 0.125 |
| cbo-59853 | 0.490 | 0.167 |
| cbo-60786 | 0.755 | 0.286 |
| cbo-61071 | 0.081 | 0.016 |
| cbo-61099 | 0.872 | 0.386 |
| cbo-61118 | 0.655 | 0.174 |
| cbo-61720 | 0.924 | 0.643 |
| cbo-61934 | 0.467 | 0.167 |
| cbo-61959 | 0.792 | 0.410 |
| cbo-61964 | 0.483 | 0.143 |
| cbo-62735 | 0.674 | 0.222 |
| cbo-62771 | 0.511 | 0.167 |
| cbo-62774 | 0.635 | 0.231 |
| eia-pdf-AEO_Narrative | 0.038 | 0.014 |
| eia-pdf-steo_full | 0.932 | 0.557 |
| govinfo-BUDGET-2025-CLIMATE | 0.418 | 0.238 |
| govinfo-BUDGET-2026-CROSSCUT | 0.969 | 0.732 |
| govinfo-BUDGET-2026-DOD | 0.889 | 0.545 |
| govinfo-BUDGET-2027-BALANCES | 0.732 | 0.400 |
| govinfo-BUDGET-2027-BUD | 0.164 | 0.078 |
| govinfo-BUDGET-2027-FCS | 0.993 | 0.922 |
| govinfo-BUDGET-2027-OBJCLASS | 0.967 | 0.709 |
| govinfo-BUDGET-2027-PER | 0.439 | 0.178 |
| govinfo-CRPT-118hrpt468 | 0.000 | 0.000 |
| govinfo-ERP-2026-table1 | 0.994 | 0.833 |
| govinfo-ERP-2026-table19 | 0.998 | 0.944 |
| govinfo-ERP-2026-table22 | 0.973 | 0.842 |
| govinfo-ERP-2026-table30 | 1.000 | 0.966 |
| govinfo-ERP-2026-table4 | 0.997 | 0.885 |
| govinfo-ERP-2026-table42 | 0.988 | 0.841 |
| govinfo-ERP-2026-table43 | 0.999 | 0.939 |
| govinfo-ERP-2026-table44 | 0.996 | 0.824 |
| govinfo-ERP-2026-table46 | 0.984 | 0.733 |
| govinfo-ERP-2026-table48 | 0.993 | 0.769 |
| govinfo-ERP-2026-table50 | 0.982 | 0.786 |
| govinfo-ERP-2026-table54 | 0.979 | 0.829 |

## D-037 outputs — whole corpus

| output | value |
|---|---|
| table slices / tables | 4197 / 947 |
| prefix_integrity (must be 0) | 0 |
| unit_line_missing (slices / tables) | 3598 / 903 |
| header_not_repeated tables | 111 |
| header_row_cause | {'header_over_max_tokens': 1, 'caption_on_slice0': 110} |
| body lines not `|` (slices) | 69 |
| blank / partial headers (tables) | 3 / 241 |
| U+FFFD removed (fffd_removed) | 426318 |
| U+FFFD kept, in table slices | 4678 |
| fffd_in_number (slices) | 51 |
| question_source_barred: slices / tables | 1679 / 319 |
|   slices by reason | {'no_own_title': 1396, 'header_not_repeated': 864, 'parse_path_fallback': 32, 'fffd_in_number': 51} |
|   tables by reason | {'no_own_title': 276, 'header_not_repeated': 111, 'parse_path_fallback': 3, 'fffd_in_number': 9} |
| caption-only chunks (table by D-036, prose by D-033 literal) | 16 |
| max contextualized table-slice length | 561 tokens / 32488 chars |
| max tokens, any chunk | 561 |

## D-037 outputs — the 25 units parsed since 2026-10-04 ({'govinfo_budget': 2445, 'govinfo_erp': 444, 'cbo_manual': 431} chunks by source)

| output | value |
|---|---|
| table slices / tables | 1082 / 209 |
| prefix_integrity (must be 0) | 0 |
| unit_line_missing (slices / tables) | 695 / 182 |
| header_not_repeated tables | 51 |
| header_row_cause | {'caption_on_slice0': 51} |
| body lines not `|` (slices) | 69 |
| blank / partial headers (tables) | 0 / 97 |
| U+FFFD removed (fffd_removed) | 57519 |
| U+FFFD kept, in table slices | 4662 |
| fffd_in_number (slices) | 40 |
| question_source_barred: slices / tables | 500 / 97 |
|   slices by reason | {'no_own_title': 398, 'header_not_repeated': 291, 'parse_path_fallback': 11, 'fffd_in_number': 40} |
|   tables by reason | {'no_own_title': 76, 'header_not_repeated': 51, 'parse_path_fallback': 1, 'fffd_in_number': 7} |
| caption-only chunks (table by D-036, prose by D-033 literal) | 13 |
| max contextualized table-slice length | 547 tokens / 32488 chars |
| max tokens, any chunk | 547 |

## parse_path per table — the 12 ERP granules

| unit | tables:parse_path |
|---|---|
| govinfo-ERP-2026-table1 | ['tbl-0:rebuilt', 'tbl-1:rebuilt'] |
| govinfo-ERP-2026-table19 | ['tbl-0:rebuilt', 'tbl-1:rebuilt'] |
| govinfo-ERP-2026-table22 | ['tbl-0:rebuilt', 'tbl-1:rebuilt'] |
| govinfo-ERP-2026-table30 | ['tbl-0:rebuilt'] |
| govinfo-ERP-2026-table4 | ['tbl-0:rebuilt', 'tbl-1:rebuilt'] |
| govinfo-ERP-2026-table42 | ['tbl-0:rebuilt', 'tbl-1:rebuilt'] |
| govinfo-ERP-2026-table43 | ['tbl-0:rebuilt'] |
| govinfo-ERP-2026-table44 | ['tbl-0:rebuilt'] |
| govinfo-ERP-2026-table46 | ['tbl-0:fallback'] |
| govinfo-ERP-2026-table48 | ['tbl-0:rebuilt'] |
| govinfo-ERP-2026-table50 | ['tbl-0:rebuilt'] |
| govinfo-ERP-2026-table54 | ['tbl-0:rebuilt'] |

## ERP-2026-table43 and table30 (dropped-cell check)

**govinfo-ERP-2026-table43**
- fix-log status: `{"0": {"status": "rebuilt", "notes": ["header check: page words for bands [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]"]}}`
- parse_path: [('tbl-0', 'rebuilt')]; table slices 46; barred: ['[]']
- raw Docling export table: 67 rows x 13 cols, 677 cells (the row fix rebuilds from page words)
- PDF digit groups 2091; emitted 2767; PDF-only (absent from every emitted chunk of the unit): 4 = {'424': 1, '43': 1, '1967': 1, '2025': 1}

**govinfo-ERP-2026-table30**
- fix-log status: `{"0": {"status": "rebuilt", "notes": ["header check: page words for bands [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]"]}}`
- parse_path: [('tbl-0', 'rebuilt')]; table slices 57; barred: ["['fffd_in_number']", '[]']
- raw Docling export table: 5 rows x 15 cols, 41 cells (the row fix rebuilds from page words)
- PDF digit groups 1651; emitted 2108; PDF-only (absent from every emitted chunk of the unit): 9 = {'410': 1, '30': 1, '1980': 1, '2025': 3, '29': 1, '100': 2}

## MatchingPostProcessor dropped-cell warnings (both logs, UTF-16 LE decoded)

Total warnings: 6.

| unit | warnings |
|---|---|
| cbo-59828 | 1 — 4 of 87 cells, 6x5 grid |
| cbo-62774 | 1 — 4 of 84 cells, 6x5 grid |
| govinfo-BUDGET-2027-OBJCLASS | 3 — 3 of 245 cells, 32x5 grid; 2 of 253 cells, 41x6 grid; 2 of 257 cells, 41x5 grid |
| govinfo-ERP-2026-table30 | 1 — 25 of 1443 cells, 5x15 grid |

For BUDGET and CBO units (outside the row fix) the dropped cells are **absent from the corpus**: Docling dropped them before chunking and nothing restores them. Listed under "for the owner at T7"; whether such tables are barred as question sources is not decided here.

**Attribution.** The warning is logged while a unit converts and before that unit's `PARSED` line. The 25-of-1443-cell warning sits between `PARSED [7/14] ERP-table43` and `PARSED [8/14] ERP-table30`, at 00:34:21 inside table30's 6.2 s window, and its grid (5x15) is table30's raw table (5 rows x 15 cols), not table43's (67 x 13). It belongs to **ERP-2026-table30**; table43 has no dropped-cell warning. The expected "ERP-table43 1" is therefore table30. Both ERP tables are `rebuilt` from page words; every PDF-only digit group in either unit is page-number, table label, year-range or footnote text, not a data cell (the 25 dropped Docling cells are present in the emitted tables).

## For the owner at T7

- Dropped-cell tables outside the row fix (not restored, absent from the corpus): govinfo-BUDGET-2027-OBJCLASS (3 warnings: 3, 2, 2 cells), cbo-62774 (4 cells), cbo-59828 (4 cells). Whether such tables are barred as question sources is not decided here.
- `parse_path = fallback`: ERP-2026-table46 (and the other fallback tables counted above) are barred by D-040's pre-T7 rule.
- `header_not_repeated` is overwhelmingly `caption_on_slice0`; `no_own_title` is the largest bar reason. Both shrink the usable table-question pool; D-040 handles the table-question share by stratified sampling.

## Method and limits

- The D-037 item-4 checks run inside `chunk_document` and are not persisted per unit; re-running it would re-chunk, so every output above is **recomputed from the stored records** (+ raw exports for the verbatim prefix check), not read from the in-parse values. `prefix_integrity` here = the recorded unit/title source text, taken from the raw Docling export, appears verbatim in the slice. It does not detect a unit or title that exists on the page but was never recorded as `prefix_source`.
- Header repetition is read from `header_row_cause` / `question_source_barred`; blank and partial headers from each table's slice-0 header row.

## Item-5 extension (D-037 status 2026-10-06; code and apply at b441584)

Applied to the installed records only (no chunking). Backup: `data/parsed_prefffd2_20261006/` (38 per-unit chunk files, `data/chunks.jsonl`, `SHA256_MANIFEST.json`; gitignored). Only `govinfo-BUDGET-2027-PER` changed: 87 records. Same 9,678 chunk ids in the same order; every `<unit>.json` and `<unit>.rowfix.json` sha256 unchanged; the prefix/heading region of every record byte-identical; `prefix_integrity` 0 (recomputed from the rewritten file).

| quantity | before | after |
|---|---|---|
| U+FFFD removed by this extension | | 3,536 |
| U+0008 removed (same cell, before a removed run) | | 147 |
| `fffd_removed` summed over the corpus | 426,318 | 429,854 |
| U+FFFD kept in table slices | 4,678 | 1,142 |
|   in header rows | 1,058 | 1,058 |
|   `fffd_in_number` singles | 83 | 83 |
|   other (single, elsewhere in a cell) | 3,537 | 1 |
|   prefix / heading lines | 0 | 0 |
| U+FFFD in prose chunks (unchanged; 438 in BUDGET-2027-PER) | 440 | 440 |
| token-weighted share | 0.80402 (1,759,433 / 2,188,300) | **0.80391** (1,758,211 / 2,187,078) |
| chunk-count share | 0.433664 (4,197 / 9,678) | 0.433664 (4,197 / 9,678) |
| max contextualized table slice | 561 tokens / 32,488 chars | 561 tokens / 32,488 chars (`BUDGET-2026-CROSSCUT::p56::tbl-45::s9`) |
| `question_source_barred` slices | 1,679 | 1,679 (reasons unchanged) |

Other D-037 outputs after the extension are unchanged: `unit_line_missing` 3,598 slices, `header_not_repeated` 111 tables, blank/partial headers 3 / 241, body lines not `|` 69, `fffd_in_number` 51 slices.

Observation (not acted on): 3,601 U+0008 remain in table slices. The earlier first-cell strip (f4b6a12 / 98688ad) removed first-cell runs but left their U+0008; the 2026-10-06 ruling removes a U+0008 only when a run follows it in the same cell, so those stay.
