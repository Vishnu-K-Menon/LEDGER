# Rung-1b evaluator output - mode `burned`

Baseline `data/parsed` (scored first) · candidate `data/parsed` · pilot candidate `data/parsed` · bootstrap {'B': 10000, 'seed': 20260930, 'ci': '95 % two-sided percentile, table-level'}.

| family | tables | cells (plain / conservative) | strict base -> cand | conservative strict | 95 % CI | header base -> cand | flips | census base -> cand (rebuilt / not) | D-039 | D-038 |
|---|---|---|---|---|---|---|---|---|---|---|
| MER held-out | 45 | 18,246 / 18,246 | 50.14 -> **50.14** | **50.14** | [46.07, 54.12] | 85.15 -> 85.15 | 0 (0.0 %) | 17.73 -> 17.73 (None / 17.73) | **FAIL** | FAIL |
| ERP | 4 | 2,764 / 2,764 | 55.07 -> **55.07** | **55.07** | [46.21, 67.39] | 93.18 -> 93.18 | 0 (0.0 %) | 19.18 -> 19.18 (None / 19.18) | **FAIL** | FAIL |
| STEO | 26 | 13,046 / 13,046 | 86.46 -> **86.46** | **86.46** | [77.77, 93.93] | 94.65 -> 94.65 | 0 (0.0 %) | 3.01 -> 3.01 (None / 3.01) | **FAIL** | FAIL |
| tuning | 2 | 1,515 / 1,515 | 45.35 -> **45.35** | **45.35** | [42.02, 48.36] | 86.21 -> 86.21 | 0 (0.0 %) | 20.51 -> 20.51 (None / 20.51) | **FAIL** | FAIL |

## MER held-out

- D-039 · strict >= 95 % (conservative): FAIL
- D-039 · header association >= in-run baseline: PASS
- D-039 · flips <= 0.5 %: PASS
- D-039 · census <= 1.0 %: FAIL
- D-039 · BUDGET/CBO manifest identical: PASS
- D-039 · clause-1 recall unchanged: PASS
- D-038 · plain strict >= 95 %: False
- D-038 · flips <= 0.5 %: True
- D-038 · census <= 1.0 %: False
- D-038 · BUDGET/CBO census and word conservation unchanged (byte-identical tables): True
- D-038 · header association (no threshold in D-038; reported): 85.15

| section | cells | forced | strict | conservative strict |
|---|---|---|---|---|
| eia-pdf-sec1 | 6822 | 0 | 54.57 | 54.57 |
| eia-pdf-sec11 | 3353 | 0 | 63.53 | 63.53 |
| eia-pdf-sec13 | 0 | 0 | None | None |
| eia-pdf-sec3 | 5131 | 0 | 35.67 | 35.67 |
| eia-pdf-sec4 | 2235 | 0 | 44.79 | 44.79 |
| eia-pdf-sec8 | 705 | 0 | 65.96 | 65.96 |

## ERP

- D-039 · strict >= 95 % (plain): FAIL
- D-039 · header association >= in-run baseline: PASS
- D-039 · flips <= 0.5 %: PASS
- D-039 · census <= 1.0 %: FAIL
- D-039 · BUDGET/CBO manifest identical: PASS
- D-039 · clause-1 recall unchanged: PASS
- D-038 · plain strict >= 95 %: False
- D-038 · flips <= 0.5 %: True
- D-038 · census <= 1.0 %: False
- D-038 · BUDGET/CBO census and word conservation unchanged (byte-identical tables): True
- D-038 · header association (no threshold in D-038; reported): 93.18

## STEO

- D-039 · strict >= 95 % (plain): FAIL
- D-039 · header association >= in-run baseline: PASS
- D-039 · flips <= 0.5 %: PASS
- D-039 · census <= 1.0 %: FAIL
- D-039 · BUDGET/CBO manifest identical: PASS
- D-039 · clause-1 recall unchanged: PASS
- D-038 · plain strict >= 95 %: False
- D-038 · flips <= 0.5 %: True
- D-038 · census <= 1.0 %: False
- D-038 · BUDGET/CBO census and word conservation unchanged (byte-identical tables): True
- D-038 · header association (no threshold in D-038; reported): 94.65

## tuning

- D-039 · strict >= 95 % (plain): FAIL
- D-039 · header association >= in-run baseline: PASS
- D-039 · flips <= 0.5 %: PASS
- D-039 · census <= 1.0 %: FAIL
- D-039 · BUDGET/CBO manifest identical: PASS
- D-039 · clause-1 recall unchanged: PASS
- D-038 · plain strict >= 95 %: False
- D-038 · flips <= 0.5 %: True
- D-038 · census <= 1.0 %: False
- D-038 · BUDGET/CBO census and word conservation unchanged (byte-identical tables): True
- D-038 · header association (no threshold in D-038; reported): 86.21

## Per table

| family | table | page | unit | emit | cells | forced | strict base | strict | cons. strict | header (base) | row NF | col NF | note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MER held-out | 1.1 | 3 | `eia-pdf-sec1` | ? | 483 | 0 | 51.76 | 51.76 | 51.76 | 10/12 (10/12) | 0 | 39 |  |
| MER held-out | 1.2 | 5 | `eia-pdf-sec1` | ? | 569 | 0 | 47.8 | 47.8 | 47.8 | 10/13 (10/13) | 0 | 49 |  |
| MER held-out | 1.3 | 7 | `eia-pdf-sec1` | ? | 603 | 0 | 42.79 | 42.79 | 42.79 | 10/12 (10/12) | 0 | 54 |  |
| MER held-out | 1.4a | 9 | `eia-pdf-sec1` | ? | 444 | 0 | 57.88 | 57.88 | 57.88 | 7/9 (7/9) | 0 | 46 |  |
| MER held-out | 1.4b | 11 | `eia-pdf-sec1` | ? | 410 | 0 | 60.73 | 60.73 | 60.73 | 8/9 (8/9) | 0 | 39 |  |
| MER held-out | 1.4c | 13 | `eia-pdf-sec1` | ? | 414 | 0 | 54.83 | 54.83 | 54.83 | 8/9 (8/9) | 0 | 39 |  |
| MER held-out | 1.5 | 15 | `eia-pdf-sec1` | ? | 519 | 0 | 74.76 | 74.76 | 74.76 | 10/10 (10/10) | 0 | 0 |  |
| MER held-out | 1.6 | 17 | `eia-pdf-sec1` | ? | 192 | 0 | 53.12 | 53.12 | 53.12 | 7/7 (7/7) | 0 | 0 |  |
| MER held-out | 1.7 | 19 | `eia-pdf-sec1` | ? | 497 | 0 | 61.57 | 61.57 | 61.57 | 9/10 (9/10) | 0 | 0 |  |
| MER held-out | 1.8 | 21 | `eia-pdf-sec1` | ? | 587 | 0 | 64.74 | 64.74 | 64.74 | 12/12 (12/12) | 0 | 0 |  |
| MER held-out | 1.9 | 22 | `eia-pdf-sec1` | ? | 30 | 0 | 100.0 | 100.0 | 100.0 | 5/5 (5/5) | 0 | 0 |  |
| MER held-out | 1.10 | 23 | `eia-pdf-sec1` | ? | 64 | 0 | 85.94 | 85.94 | 85.94 | 6/6 (6/6) | 0 | 0 |  |
| MER held-out | 1.11 | 24 | `eia-pdf-sec1` | ? | 488 | 0 | 48.77 | 48.77 | 48.77 | 8/10 (8/10) | 0 | 46 |  |
| MER held-out | 1.12 | 25 | `eia-pdf-sec1` | ? | 518 | 0 | 48.26 | 48.26 | 48.26 | 8/10 (8/10) | 9 | 47 |  |
| MER held-out | 1.13a | 26 | `eia-pdf-sec1` | ? | 450 | 0 | 45.11 | 45.11 | 45.11 | 3/10 (3/10) | 0 | 44 |  |
| MER held-out | 1.13b | 27 | `eia-pdf-sec1` | ? | 554 | 0 | 46.57 | 46.57 | 46.57 | 9/12 (9/12) | 0 | 52 |  |
| MER held-out | 11.1 | 3 | `eia-pdf-sec11` | ? | 644 | 0 | 65.06 | 65.06 | 65.06 | 12/14 (12/14) | 0 | 0 |  |
| MER held-out | 11.2 | 5 | `eia-pdf-sec11` | ? | 339 | 0 | 74.34 | 74.34 | 74.34 | 6/8 (6/8) | 6 | 0 |  |
| MER held-out | 11.3 | 6 | `eia-pdf-sec11` | ? | 431 | 0 | 77.73 | 77.73 | 77.73 | 9/11 (9/11) | 0 | 0 |  |
| MER held-out | 11.4 | 7 | `eia-pdf-sec11` | ? | 592 | 0 | 59.97 | 59.97 | 59.97 | 12/14 (12/14) | 0 | 0 |  |
| MER held-out | 11.5 | 8 | `eia-pdf-sec11` | ? | 436 | 0 | 55.05 | 55.05 | 55.05 | 9/11 (9/11) | 0 | 0 |  |
| MER held-out | 11.6 | 9 | `eia-pdf-sec11` | ? | 347 | 0 | 58.21 | 58.21 | 58.21 | 8/8 (8/8) | 0 | 0 |  |
| MER held-out | 11.7 | 10 | `eia-pdf-sec11` | ? | 564 | 0 | 57.98 | 57.98 | 57.98 | 5/11 (5/11) | 0 | 53 |  |
| MER held-out | 3.1 | 3 | `eia-pdf-sec3` | ? | 172 | 0 | 23.84 | 23.84 | 23.84 | 12/13 (12/13) | 0 | 0 |  |
| MER held-out | 3.2 | 5 | `eia-pdf-sec3` | ? | 328 | 0 | 22.26 | 22.26 | 22.26 | 11/14 (11/14) | 0 | 45 |  |
| MER held-out | 3.3a | 7 | `eia-pdf-sec3` | ? | 263 | 0 | 21.29 | 21.29 | 21.29 | 12/12 (12/12) | 0 | 0 |  |
| MER held-out | 3.3b | 9 | `eia-pdf-sec3` | ? | 279 | 0 | 26.16 | 26.16 | 26.16 | 11/11 (11/11) | 0 | 0 |  |
| MER held-out | 3.3c | 10 | `eia-pdf-sec3` | ? | 238 | 0 | 9.66 | 9.66 | 9.66 | 2/9 (2/9) | 0 | 0 |  |
| MER held-out | 3.3d | 11 | `eia-pdf-sec3` | ? | 254 | 0 | 61.42 | 61.42 | 61.42 | 11/11 (11/11) | 0 | 0 |  |
| MER held-out | 3.3e | 12 | `eia-pdf-sec3` | ? | 161 | 0 | 37.27 | 37.27 | 37.27 | 9/9 (9/9) | 0 | 0 |  |
| MER held-out | 3.31 | 13 | `eia-pdf-sec3` | ? | 233 | 0 | 51.5 | 51.5 | 51.5 | 12/12 (12/12) | 10 | 0 |  |
| MER held-out | 3.4 | 15 | `eia-pdf-sec3` | ? | 346 | 0 | 31.5 | 31.5 | 31.5 | 10/13 (10/13) | 0 | 0 |  |
| MER held-out | 3.5 | 17 | `eia-pdf-sec3` | ? | 313 | 0 | 25.88 | 25.88 | 25.88 | 13/15 (13/15) | 0 | 0 |  |
| tuning | 3.6 | 19 | `eia-pdf-sec3` | ? | 721 | 0 | 42.02 | 42.02 | 42.02 | 11/15 (11/15) | 0 | 57 |  |
| MER held-out | 3.7a | 21 | `eia-pdf-sec3` | ? | 225 | 0 | 24.44 | 24.44 | 24.44 | 9/11 (9/11) | 0 | 23 |  |
| MER held-out | 3.7b | 22 | `eia-pdf-sec3` | ? | 277 | 0 | 26.35 | 26.35 | 26.35 | 10/13 (10/13) | 0 | 20 |  |
| MER held-out | 3.7c | 23 | `eia-pdf-sec3` | ? | 295 | 0 | 37.29 | 37.29 | 37.29 | 13/13 (13/13) | 0 | 0 |  |
| MER held-out | 3.8a | 26 | `eia-pdf-sec3` | ? | 476 | 0 | 39.5 | 39.5 | 39.5 | 10/11 (10/11) | 4 | 30 |  |
| MER held-out | 3.8b | 27 | `eia-pdf-sec3` | ? | 630 | 0 | 45.4 | 45.4 | 45.4 | 12/13 (12/13) | 0 | 56 |  |
| MER held-out | 3.8c | 28 | `eia-pdf-sec3` | ? | 641 | 0 | 50.86 | 50.86 | 50.86 | 13/13 (13/13) | 0 | 0 |  |
| MER held-out | 4.1 | 3 | `eia-pdf-sec4` | ? | 538 | 0 | 47.58 | 47.58 | 47.58 | 10/11 (10/11) | 0 | 0 |  |
| MER held-out | 4.2a | 4 | `eia-pdf-sec4` | ? | 751 | 0 | 41.41 | 41.41 | 41.41 | 11/14 (11/14) | 13 | 56 |  |
| tuning | 4.2b | 5 | `eia-pdf-sec4` | ? | 794 | 0 | 48.36 | 48.36 | 48.36 | 14/14 (14/14) | 0 | 0 |  |
| MER held-out | 4.3 | 6 | `eia-pdf-sec4` | ? | 519 | 0 | 43.16 | 43.16 | 43.16 | 10/11 (10/11) | 0 | 0 |  |
| MER held-out | 4.4 | 7 | `eia-pdf-sec4` | ? | 427 | 0 | 49.18 | 49.18 | 49.18 | 7/8 (7/8) | 0 | 53 |  |
| MER held-out | 8.1 | 3 | `eia-pdf-sec8` | ? | 274 | 0 | 65.33 | 65.33 | 65.33 | 5/5 (5/5) | 5 | 0 |  |
| MER held-out | 8.2 | 5 | `eia-pdf-sec8` | ? | 431 | 0 | 66.36 | 66.36 | 66.36 | 9/10 (9/10) | 0 | 48 |  |
| ERP | table22 sheet0 | 1 | `govinfo-ERP-2026-table22` | ? | 566 | 0 | 63.43 | 63.43 | 63.43 | 10/10 (10/10) | 0 | 0 |  |
| ERP | table22 sheet1 | 2 | `govinfo-ERP-2026-table22` | ? | 590 | 0 | 71.19 | 71.19 | 71.19 | 10/10 (10/10) | 0 | 0 |  |
| ERP | table4 sheet0 | 1 | `govinfo-ERP-2026-table4` | ? | 804 | 0 | 43.41 | 43.41 | 43.41 | 10/12 (10/12) | 0 | 67 |  |
| ERP | table4 sheet1 | 2 | `govinfo-ERP-2026-table4` | ? | 804 | 0 | 49.0 | 49.0 | 49.0 | 11/12 (11/12) | 0 | 0 |  |
| STEO | 1 | 31 | `eia-pdf-steo_full` | ? | 330 | 0 | 90.91 | 90.91 | 90.91 | 15/15 (15/15) | 15 | 0 |  |
| STEO | 2 | 32 | `eia-pdf-steo_full` | ? | 396 | 0 | 100.0 | 100.0 | 100.0 | 14/15 (14/15) | 0 | 0 |  |
| STEO | 3a | 33 | `eia-pdf-steo_full` | ? | 465 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 3b | 34 | `eia-pdf-steo_full` | ? | 412 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 3c | 35 | `eia-pdf-steo_full` | ? | 332 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 3d | 36 | `eia-pdf-steo_full` | ? | 357 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 3e | 37 | `eia-pdf-steo_full` | ? | 357 | 0 | 100.0 | 100.0 | 100.0 | 12/15 (12/15) | 0 | 0 |  |
| STEO | 4a | 38 | `eia-pdf-steo_full` | ? | 810 | 0 | 66.54 | 66.54 | 66.54 | 15/15 (15/15) | 90 | 0 |  |
| STEO | 4b | 39 | `eia-pdf-steo_full` | ? | 645 | 0 | 66.05 | 66.05 | 66.05 | 15/15 (15/15) | 60 | 0 |  |
| STEO | 4c | 40 | `eia-pdf-steo_full` | ? | 210 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 4d | 41 | `eia-pdf-steo_full` | ? | 615 | 0 | 90.41 | 90.41 | 90.41 | 15/15 (15/15) | 15 | 0 |  |
| STEO | 5a | 42 | `eia-pdf-steo_full` | ? | 495 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 5b | 43 | `eia-pdf-steo_full` | ? | 465 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 6 | 44 | `eia-pdf-steo_full` | ? | 465 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 7a | 45 | `eia-pdf-steo_full` | ? | 600 | 0 | 88.5 | 88.5 | 88.5 | 15/15 (15/15) | 15 | 0 |  |
| STEO | 7b | 46 | `eia-pdf-steo_full` | ? | 660 | 0 | 89.55 | 89.55 | 89.55 | 15/15 (15/15) | 30 | 0 |  |
| STEO | 7c | 47 | `eia-pdf-steo_full` | ? | 600 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 7d | 48 | `eia-pdf-steo_full` | ? | 825 | 0 | 58.18 | 58.18 | 58.18 | 14/15 (14/15) | 180 | 0 |  |
| STEO | 7d | 49 | `eia-pdf-steo_full` | ? | 810 | 0 | 80.74 | 80.74 | 80.74 | 8/15 (8/15) | 120 | 0 |  |
| STEO | 7e | 50 | `eia-pdf-steo_full` | ? | 315 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 8 | 51 | `eia-pdf-steo_full` | ? | 510 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 9a | 52 | `eia-pdf-steo_full` | ? | 495 | 0 | 94.55 | 94.55 | 94.55 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 9b | 53 | `eia-pdf-steo_full` | ? | 675 | 0 | 85.19 | 85.19 | 85.19 | 12/15 (12/15) | 0 | 45 |  |
| STEO | 9c | 54 | `eia-pdf-steo_full` | ? | 600 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 10a | 55 | `eia-pdf-steo_full` | ? | 448 | 0 | 7.59 | 7.59 | 7.59 | 2/7 (2/7) | 210 | 0 |  |
| STEO | 10b | 56 | `eia-pdf-steo_full` | ? | 154 | 0 | 95.45 | 95.45 | 95.45 | 7/7 (7/7) | 7 | 0 |  |
