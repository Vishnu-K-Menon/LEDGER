# T5 supplement items (reported separately)

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

Coverage supplement (D-043 item 1): answered and reported beside the 25; no count, rate or kappa on the 25 includes them.

Validity over 3 supplement requests: stop `end_turn` 3/3, pydantic 3/3, citations among the five supplied 3/3.

| question | source | run | gold cited | answer |
|---|---|---|---|---|
| s001 | cbo_manual | 1 | True | CBO states that S. 284, the Congressional Award Program Reauthorization Act, would increase direct spending by $1 million over the 2026-2035 |
| s001 | cbo_manual | 2 | True | CBO estimates that S. 284, the Congressional Award Program Reauthorization Act, would increase direct spending by $1 million over the 2026-2 |
| s001 | cbo_manual | 3 | True | CBO's table states that S. 284, the Congressional Award Program Reauthorization Act, would increase direct spending by $1 million over the 2 |
