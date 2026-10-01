# Rung-1b evaluator output - mode `burned`

Baseline `data/parsed` (scored first) · candidate `data/parsed_rung1` · pilot candidate `data/parsed_rung1` · bootstrap {'B': 10000, 'seed': 20260930, 'ci': '95 % two-sided percentile, table-level'}.

| family | tables | cells (plain / conservative) | strict base -> cand | conservative strict | 95 % CI | header base -> cand | flips | census base -> cand (rebuilt / not) | D-039 | D-038 |
|---|---|---|---|---|---|---|---|---|---|---|
| MER held-out | 45 | 18,246 / 18,246 | 50.14 -> **88.72** | **88.72** | [83.07, 93.34] | 85.15 -> 89.48 | 9 (0.05 %) | 17.73 -> 2.11 (0.07 / 14.36) | **FAIL** | FAIL |
| ERP | 4 | 2,764 / 2,764 | 55.07 -> **92.51** | **92.51** | [75.18, 100.0] | 93.18 -> 97.73 | 0 (0.0 %) | 19.18 -> 2.34 (0.0 / 10.65) | **FAIL** | FAIL |
| STEO | 26 | 13,046 / 13,046 | 86.46 -> **95.76** | **95.76** | [88.13, 99.72] | 94.65 -> 78.61 | 36 (0.28 %) | 3.01 -> 0.94 (0.01 / 1.76) | **FAIL** | PASS |
| tuning | 2 | 1,515 / 1,515 | 45.35 -> **96.77** | **96.77** | [93.62, 99.62] | 86.21 -> 96.55 | 0 (0.0 %) | 20.51 -> 2.53 (0.14 / 15.44) | **FAIL** | FAIL |

## MER held-out

- D-039 · strict >= 95 % (conservative): FAIL
- D-039 · header association >= in-run baseline: PASS
- D-039 · flips <= 0.5 %: PASS
- D-039 · census <= 1.0 %: FAIL
- D-039 · BUDGET/CBO manifest identical: PASS
- D-039 · clause-1 recall unchanged: FAIL
- D-038 · plain strict >= 95 %: False
- D-038 · flips <= 0.5 %: True
- D-038 · census <= 1.0 %: False
- D-038 · BUDGET/CBO census and word conservation unchanged (byte-identical tables): True
- D-038 · header association (no threshold in D-038; reported): 89.48

| section | cells | forced | strict | conservative strict |
|---|---|---|---|---|
| eia-pdf-sec1 | 6822 | 0 | 93.65 | 93.65 |
| eia-pdf-sec11 | 3353 | 0 | 88.22 | 88.22 |
| eia-pdf-sec13 | 0 | 0 | None | None |
| eia-pdf-sec3 | 5131 | 0 | 82.34 | 82.34 |
| eia-pdf-sec4 | 2235 | 0 | 85.46 | 85.46 |
| eia-pdf-sec8 | 705 | 0 | 100.0 | 100.0 |

## ERP

- D-039 · strict >= 95 % (plain): FAIL
- D-039 · header association >= in-run baseline: PASS
- D-039 · flips <= 0.5 %: PASS
- D-039 · census <= 1.0 %: FAIL
- D-039 · BUDGET/CBO manifest identical: PASS
- D-039 · clause-1 recall unchanged: FAIL
- D-038 · plain strict >= 95 %: False
- D-038 · flips <= 0.5 %: True
- D-038 · census <= 1.0 %: False
- D-038 · BUDGET/CBO census and word conservation unchanged (byte-identical tables): True
- D-038 · header association (no threshold in D-038; reported): 97.73

## STEO

- D-039 · strict >= 95 % (plain): PASS
- D-039 · header association >= in-run baseline: FAIL
- D-039 · flips <= 0.5 %: PASS
- D-039 · census <= 1.0 %: PASS
- D-039 · BUDGET/CBO manifest identical: PASS
- D-039 · clause-1 recall unchanged: FAIL
- D-038 · plain strict >= 95 %: True
- D-038 · flips <= 0.5 %: True
- D-038 · census <= 1.0 %: True
- D-038 · BUDGET/CBO census and word conservation unchanged (byte-identical tables): True
- D-038 · header association (no threshold in D-038; reported): 78.61

## tuning

- D-039 · strict >= 95 % (plain): PASS
- D-039 · header association >= in-run baseline: PASS
- D-039 · flips <= 0.5 %: PASS
- D-039 · census <= 1.0 %: FAIL
- D-039 · BUDGET/CBO manifest identical: PASS
- D-039 · clause-1 recall unchanged: FAIL
- D-038 · plain strict >= 95 %: True
- D-038 · flips <= 0.5 %: True
- D-038 · census <= 1.0 %: False
- D-038 · BUDGET/CBO census and word conservation unchanged (byte-identical tables): True
- D-038 · header association (no threshold in D-038; reported): 96.55

## Per table

| family | table | page | unit | emit | cells | forced | strict base | strict | cons. strict | header (base) | row NF | col NF | note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MER held-out | 1.1 | 3 | `eia-pdf-sec1` | rebuilt | 483 | 0 | 51.76 | 98.76 | 98.76 | 12/12 (10/12) | 0 | 0 |  |
| MER held-out | 1.2 | 5 | `eia-pdf-sec1` | fallback | 569 | 0 | 47.8 | 47.8 | 47.8 | 10/13 (10/13) | 0 | 49 |  |
| MER held-out | 1.3 | 7 | `eia-pdf-sec1` | rebuilt | 603 | 0 | 42.79 | 99.5 | 99.5 | 12/12 (10/12) | 0 | 0 |  |
| MER held-out | 1.4a | 9 | `eia-pdf-sec1` | rebuilt | 444 | 0 | 57.88 | 99.1 | 99.1 | 9/9 (7/9) | 0 | 0 |  |
| MER held-out | 1.4b | 11 | `eia-pdf-sec1` | rebuilt | 410 | 0 | 60.73 | 97.56 | 97.56 | 9/9 (8/9) | 0 | 0 |  |
| MER held-out | 1.4c | 13 | `eia-pdf-sec1` | rebuilt | 414 | 0 | 54.83 | 97.58 | 97.58 | 9/9 (8/9) | 0 | 0 |  |
| MER held-out | 1.5 | 15 | `eia-pdf-sec1` | rebuilt | 519 | 0 | 74.76 | 100.0 | 100.0 | 10/10 (10/10) | 0 | 0 |  |
| MER held-out | 1.6 | 17 | `eia-pdf-sec1` | rebuilt | 192 | 0 | 53.12 | 97.4 | 97.4 | 7/7 (7/7) | 0 | 0 |  |
| MER held-out | 1.7 | 19 | `eia-pdf-sec1` | rebuilt | 497 | 0 | 61.57 | 100.0 | 100.0 | 9/10 (9/10) | 0 | 0 |  |
| MER held-out | 1.8 | 21 | `eia-pdf-sec1` | rebuilt | 587 | 0 | 64.74 | 99.15 | 99.15 | 8/12 (12/12) | 0 | 0 |  |
| MER held-out | 1.9 | 22 | `eia-pdf-sec1` | not fired | 30 | 0 | 100.0 | 100.0 | 100.0 | 5/5 (5/5) | 0 | 0 |  |
| MER held-out | 1.10 | 23 | `eia-pdf-sec1` | not fired | 64 | 0 | 85.94 | 85.94 | 85.94 | 6/6 (6/6) | 0 | 0 |  |
| MER held-out | 1.11 | 24 | `eia-pdf-sec1` | rebuilt | 488 | 0 | 48.77 | 99.18 | 99.18 | 10/10 (8/10) | 0 | 0 |  |
| MER held-out | 1.12 | 25 | `eia-pdf-sec1` | rebuilt | 518 | 0 | 48.26 | 98.46 | 98.46 | 10/10 (8/10) | 0 | 0 |  |
| MER held-out | 1.13a | 26 | `eia-pdf-sec1` | rebuilt | 450 | 0 | 45.11 | 92.22 | 92.22 | 6/10 (3/10) | 0 | 0 |  |
| MER held-out | 1.13b | 27 | `eia-pdf-sec1` | rebuilt | 554 | 0 | 46.57 | 93.32 | 93.32 | 11/12 (9/12) | 0 | 0 |  |
| MER held-out | 11.1 | 3 | `eia-pdf-sec11` | rebuilt | 644 | 0 | 65.06 | 96.43 | 96.43 | 12/14 (12/14) | 0 | 0 |  |
| MER held-out | 11.2 | 5 | `eia-pdf-sec11` | not fired | 339 | 0 | 74.34 | 74.34 | 74.34 | 6/8 (6/8) | 6 | 0 |  |
| MER held-out | 11.3 | 6 | `eia-pdf-sec11` | rebuilt | 431 | 0 | 77.73 | 98.38 | 98.38 | 6/11 (9/11) | 0 | 0 |  |
| MER held-out | 11.4 | 7 | `eia-pdf-sec11` | rebuilt | 592 | 0 | 59.97 | 95.61 | 95.61 | 11/14 (12/14) | 0 | 0 |  |
| MER held-out | 11.5 | 8 | `eia-pdf-sec11` | not fired | 436 | 0 | 55.05 | 55.05 | 55.05 | 9/11 (9/11) | 0 | 0 |  |
| MER held-out | 11.6 | 9 | `eia-pdf-sec11` | rebuilt | 347 | 0 | 58.21 | 84.73 | 84.73 | 7/8 (8/8) | 0 | 0 |  |
| MER held-out | 11.7 | 10 | `eia-pdf-sec11` | rebuilt | 564 | 0 | 57.98 | 99.47 | 99.47 | 8/11 (5/11) | 0 | 0 |  |
| MER held-out | 3.1 | 3 | `eia-pdf-sec3` | fallback | 172 | 0 | 23.84 | 23.84 | 23.84 | 12/13 (12/13) | 0 | 0 |  |
| MER held-out | 3.2 | 5 | `eia-pdf-sec3` | rebuilt | 328 | 0 | 22.26 | 92.07 | 92.07 | 12/14 (11/14) | 0 | 0 |  |
| MER held-out | 3.3a | 7 | `eia-pdf-sec3` | rebuilt | 263 | 0 | 21.29 | 92.78 | 92.78 | 12/12 (12/12) | 0 | 0 |  |
| MER held-out | 3.3b | 9 | `eia-pdf-sec3` | rebuilt | 279 | 0 | 26.16 | 84.23 | 84.23 | 10/11 (11/11) | 0 | 0 |  |
| MER held-out | 3.3c | 10 | `eia-pdf-sec3` | rebuilt | 238 | 0 | 9.66 | 20.59 | 20.59 | 2/9 (2/9) | 0 | 0 |  |
| MER held-out | 3.3d | 11 | `eia-pdf-sec3` | rebuilt | 254 | 0 | 61.42 | 98.82 | 98.82 | 11/11 (11/11) | 0 | 0 |  |
| MER held-out | 3.3e | 12 | `eia-pdf-sec3` | not fired | 161 | 0 | 37.27 | 37.27 | 37.27 | 9/9 (9/9) | 0 | 0 |  |
| MER held-out | 3.31 | 13 | `eia-pdf-sec3` | not fired | 233 | 0 | 51.5 | 51.5 | 51.5 | 12/12 (12/12) | 10 | 0 |  |
| MER held-out | 3.4 | 15 | `eia-pdf-sec3` | rebuilt | 346 | 0 | 31.5 | 91.33 | 91.33 | 13/13 (10/13) | 0 | 0 |  |
| MER held-out | 3.5 | 17 | `eia-pdf-sec3` | rebuilt | 313 | 0 | 25.88 | 87.54 | 87.54 | 13/15 (13/15) | 0 | 0 |  |
| tuning | 3.6 | 19 | `eia-pdf-sec3` | rebuilt | 721 | 0 | 42.02 | 93.62 | 93.62 | 14/15 (11/15) | 0 | 0 |  |
| MER held-out | 3.7a | 21 | `eia-pdf-sec3` | rebuilt | 225 | 0 | 24.44 | 82.67 | 82.67 | 11/11 (9/11) | 0 | 0 |  |
| MER held-out | 3.7b | 22 | `eia-pdf-sec3` | rebuilt | 277 | 0 | 26.35 | 83.39 | 83.39 | 10/13 (10/13) | 0 | 0 |  |
| MER held-out | 3.7c | 23 | `eia-pdf-sec3` | rebuilt | 295 | 0 | 37.29 | 92.54 | 92.54 | 13/13 (13/13) | 0 | 0 |  |
| MER held-out | 3.8a | 26 | `eia-pdf-sec3` | rebuilt | 476 | 0 | 39.5 | 92.23 | 92.23 | 11/11 (10/11) | 0 | 0 |  |
| MER held-out | 3.8b | 27 | `eia-pdf-sec3` | rebuilt | 630 | 0 | 45.4 | 92.22 | 92.22 | 11/13 (12/13) | 0 | 0 |  |
| MER held-out | 3.8c | 28 | `eia-pdf-sec3` | rebuilt | 641 | 0 | 50.86 | 97.19 | 97.19 | 13/13 (13/13) | 0 | 0 |  |
| MER held-out | 4.1 | 3 | `eia-pdf-sec4` | fallback | 538 | 0 | 47.58 | 47.58 | 47.58 | 10/11 (10/11) | 0 | 0 |  |
| MER held-out | 4.2a | 4 | `eia-pdf-sec4` | rebuilt | 751 | 0 | 41.41 | 98.67 | 98.67 | 13/14 (11/14) | 0 | 0 |  |
| tuning | 4.2b | 5 | `eia-pdf-sec4` | rebuilt | 794 | 0 | 48.36 | 99.62 | 99.62 | 14/14 (14/14) | 0 | 0 |  |
| MER held-out | 4.3 | 6 | `eia-pdf-sec4` | rebuilt | 519 | 0 | 43.16 | 93.64 | 93.64 | 11/11 (10/11) | 0 | 0 |  |
| MER held-out | 4.4 | 7 | `eia-pdf-sec4` | rebuilt | 427 | 0 | 49.18 | 100.0 | 100.0 | 8/8 (7/8) | 0 | 0 |  |
| MER held-out | 8.1 | 3 | `eia-pdf-sec8` | rebuilt | 274 | 0 | 65.33 | 100.0 | 100.0 | 5/5 (5/5) | 0 | 0 |  |
| MER held-out | 8.2 | 5 | `eia-pdf-sec8` | rebuilt | 431 | 0 | 66.36 | 100.0 | 100.0 | 10/10 (9/10) | 0 | 0 |  |
| ERP | table22 sheet0 | 1 | `govinfo-ERP-2026-table22` | not fired | 566 | 0 | 63.43 | 63.43 | 63.43 | 10/10 (10/10) | 0 | 0 |  |
| ERP | table22 sheet1 | 2 | `govinfo-ERP-2026-table22` | rebuilt | 590 | 0 | 71.19 | 100.0 | 100.0 | 9/10 (10/10) | 0 | 0 |  |
| ERP | table4 sheet0 | 1 | `govinfo-ERP-2026-table4` | rebuilt | 804 | 0 | 43.41 | 100.0 | 100.0 | 12/12 (10/12) | 0 | 0 |  |
| ERP | table4 sheet1 | 2 | `govinfo-ERP-2026-table4` | rebuilt | 804 | 0 | 49.0 | 100.0 | 100.0 | 12/12 (11/12) | 0 | 0 |  |
| STEO | 1 | 31 | `eia-pdf-steo_full` | rebuilt | 330 | 0 | 90.91 | 100.0 | 100.0 | 9/15 (15/15) | 0 | 0 |  |
| STEO | 2 | 32 | `eia-pdf-steo_full` | rebuilt | 396 | 0 | 100.0 | 100.0 | 100.0 | 6/15 (14/15) | 0 | 0 |  |
| STEO | 3a | 33 | `eia-pdf-steo_full` | not fired | 465 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 3b | 34 | `eia-pdf-steo_full` | not fired | 412 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 3c | 35 | `eia-pdf-steo_full` | not fired | 332 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 3d | 36 | `eia-pdf-steo_full` | not fired | 357 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 3e | 37 | `eia-pdf-steo_full` | rebuilt | 357 | 0 | 100.0 | 89.92 | 89.92 | 9/15 (12/15) | 21 | 0 |  |
| STEO | 4a | 38 | `eia-pdf-steo_full` | rebuilt | 810 | 0 | 66.54 | 100.0 | 100.0 | 9/15 (15/15) | 0 | 0 |  |
| STEO | 4b | 39 | `eia-pdf-steo_full` | rebuilt | 645 | 0 | 66.05 | 100.0 | 100.0 | 9/15 (15/15) | 0 | 0 |  |
| STEO | 4c | 40 | `eia-pdf-steo_full` | fallback | 210 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 4d | 41 | `eia-pdf-steo_full` | rebuilt | 615 | 0 | 90.41 | 100.0 | 100.0 | 9/15 (15/15) | 0 | 0 |  |
| STEO | 5a | 42 | `eia-pdf-steo_full` | rebuilt | 495 | 0 | 100.0 | 100.0 | 100.0 | 9/15 (15/15) | 0 | 0 |  |
| STEO | 5b | 43 | `eia-pdf-steo_full` | not fired | 465 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 6 | 44 | `eia-pdf-steo_full` | not fired | 465 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 7a | 45 | `eia-pdf-steo_full` | rebuilt | 600 | 0 | 88.5 | 100.0 | 100.0 | 6/15 (15/15) | 0 | 0 |  |
| STEO | 7b | 46 | `eia-pdf-steo_full` | not fired | 660 | 0 | 89.55 | 89.55 | 89.55 | 15/15 (15/15) | 30 | 0 |  |
| STEO | 7c | 47 | `eia-pdf-steo_full` | not fired | 600 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 7d | 48 | `eia-pdf-steo_full` | rebuilt | 825 | 0 | 58.18 | 100.0 | 100.0 | 9/15 (14/15) | 0 | 0 |  |
| STEO | 7d | 49 | `eia-pdf-steo_full` | rebuilt | 810 | 0 | 80.74 | 100.0 | 100.0 | 6/15 (8/15) | 0 | 0 |  |
| STEO | 7e | 50 | `eia-pdf-steo_full` | not fired | 315 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 8 | 51 | `eia-pdf-steo_full` | not fired | 510 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 9a | 52 | `eia-pdf-steo_full` | fallback | 495 | 0 | 94.55 | 94.55 | 94.55 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 9b | 53 | `eia-pdf-steo_full` | rebuilt | 675 | 0 | 85.19 | 100.0 | 100.0 | 9/15 (12/15) | 0 | 0 |  |
| STEO | 9c | 54 | `eia-pdf-steo_full` | not fired | 600 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 10a | 55 | `eia-pdf-steo_full` | fallback | 448 | 0 | 7.59 | 7.59 | 7.59 | 2/7 (2/7) | 210 | 0 |  |
| STEO | 10b | 56 | `eia-pdf-steo_full` | not fired | 154 | 0 | 95.45 | 95.45 | 95.45 | 7/7 (7/7) | 7 | 0 |  |
