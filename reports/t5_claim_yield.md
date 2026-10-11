# T5 claim yield (run 1, the baseline of record)

- git commit: `b5b37e236d0347847406e3eba6c58e876a752515`
- questions sha256: `05bc4e4a8ea34cc6ff19882b5ea3598be9210d06f72ff4534b7410b790abc4c0`
- chunks.jsonl sha256 (LF): `a42243a0f30e81e02b372f49d39d1d4f7f70f78d4bff137665485e6556cfd8c3`
- controls_accepted.json sha256: `d5feaa3a007af856ef1ac7ec47b82b2651919e00b98832f44ffc8f337973ab73`
- contexts sha256: `746ecc3fcbdc13397032f7c708720b939de4e870d7ea498084f399b88b8365e1`
- output_mode: `structured_output`
- model: `claude-sonnet-5-5`
- thinking / effort: `between_tools / high`
- core requests: `90`
- supplement requests: `3`

## Composition by source and unit

**25 drafts (core)**: cbo_manual 2 (cbo-59853 x1, cbo-61099 x1); eia 2 (eia-pdf-steo_full x2); govinfo_budget 13 (govinfo-BUDGET-2025-CLIMATE x1, govinfo-BUDGET-2026-DOD x7, govinfo-BUDGET-2027-BALANCES x1, govinfo-BUDGET-2027-FCS x1, govinfo-BUDGET-2027-PER x3); govinfo_crpt 4 (govinfo-CRPT-118hrpt468 x4); govinfo_erp 4 (govinfo-ERP-2026-table19 x2, govinfo-ERP-2026-table22 x1, govinfo-ERP-2026-table42 x1)

**supplement (beside the 25)**: cbo_manual 1 (cbo-61720 x1)

Sources not exercised by the 25 drafts: none.
Sources not exercised by drafts plus supplement: none.
Controls: 5 accepted; supplement results are reported separately and enter no count on the 25.

Definitions: *sentences* = answer sentences; *citations* = (sentence, chunk ID) pairs; *numbers* = numeric tokens in the answer text (a proxy for atomic facts). The real claim count comes from decomposition at T6; T6 needs about 125 claims from 25 answers (evaluation.md:67).

| kind | answers | sentences (mean) | citations (mean) | numbers (mean) |
|---|---|---|---|---|
| table | 11 | 1.00 | 1.09 | 4.18 |
| prose | 12 | 1.08 | 1.33 | 1.75 |

All non-abstaining answers: 23; sentences 24, citations 28, numbers 67. Sentences per answer projected to 25 answers: 26 (a floor for the claim count, since decomposition splits sentences).

| question | kind | sentences | citations | numbers |
|---|---|---|---|---|
| q001 | table | 1 | 2 | 7 |
| q002 | table | 1 | 1 | 3 |
| q004 | table | 1 | 1 | 8 |
| q005 | table | 1 | 1 | 2 |
| q006 | table | 1 | 1 | 7 |
| q007 | table | 1 | 1 | 2 |
| q008 | table | 1 | 1 | 2 |
| q009 | table | 1 | 1 | 3 |
| q011 | table | 1 | 1 | 7 |
| q012 | table | 1 | 1 | 2 |
| q013 | table | 1 | 1 | 3 |
| q014 | prose | 1 | 1 | 1 |
| q015 | prose | 1 | 1 | 2 |
| q016 | prose | 1 | 2 | 2 |
| q017 | prose | 1 | 2 | 3 |
| q018 | prose | 1 | 1 | 4 |
| q019 | prose | 1 | 1 | 2 |
| q020 | prose | 1 | 1 | 0 |
| q021 | prose | 2 | 3 | 0 |
| q022 | prose | 1 | 1 | 1 |
| q023 | prose | 1 | 1 | 1 |
| q024 | prose | 1 | 1 | 1 |
| q025 | prose | 1 | 1 | 4 |
