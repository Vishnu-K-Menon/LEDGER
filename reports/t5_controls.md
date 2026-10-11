# T5 controls: abstention, run 1

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

A check for gross failure, **not a rate** (5 of 5 has a 95 % lower bound of 0.48). k = runs that returned a valid abstention; n = all run-1 requests for the accepted controls (an invalid run stays in n and is counted in the last column). Exact (Clopper-Pearson) 95 % interval. Nothing gates on this number.

| group | abstained | 95 % interval | invalid |
|---|---|---|---|
| all accepted controls | 5 of 5 | [0.48, 1.00] | 0 |
| kind: absent_entity | 1 of 1 | [0.03, 1.00] | 0 |
| kind: out_of_range_period | 4 of 4 | [0.40, 1.00] | 0 |
| tag: near_miss | 4 of 4 | [0.40, 1.00] | 0 |
| tag: none | 1 of 1 | [0.03, 1.00] | 0 |

### Per control

- c001 (absent_entity, tag near_miss): abstained
- c002 (out_of_range_period, tag near_miss): abstained
- c003 (out_of_range_period, tag none): abstained
- c004 (out_of_range_period, tag near_miss): abstained
- c005 (out_of_range_period, tag near_miss): abstained
