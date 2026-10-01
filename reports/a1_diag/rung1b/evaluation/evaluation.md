# Rung-1b evaluator output - mode `fresh`

Baseline `data/parsed_fresh` (scored first) · candidate `data/parsed_fresh_rung1b` · pilot candidate `data/parsed_rung1b` · bootstrap {'B': 10000, 'seed': 20260930, 'ci': '95 % two-sided percentile, table-level'}.

| family | tables | cells (plain / conservative) | strict base -> cand | conservative strict | 95 % CI | header base -> cand | flips | census base -> cand (rebuilt / not) | D-039 | D-038 |
|---|---|---|---|---|---|---|---|---|---|---|
| MER | 45 | 13,731 / 13,756 | 53.98 -> **95.12** | **94.95** | [90.73, 98.24] | 84.33 -> 90.88 | 15 (0.11 %) | 14.7 -> 1.26 (0.12 / 11.66) | **FAIL** | FAIL |
| ERP | 6 | 5,017 / 5,017 | 30.5 -> **100.0** | **100.0** | [100.0, 100.0] (unreliable) | 90.79 -> 97.37 | 0 (0.0 %) | 28.02 -> 0.0 (0.0 / None) | **PASS** | PASS |
| STEO | 19 | 1,277 / 1,277 | 89.19 -> **94.44** | **94.44** | [82.24, 100.0] | 95.4 -> 97.7 | 0 (0.0 %) | 2.71 -> 0.56 (0.0 / 1.26) | **FAIL** | FAIL |

## MER

- D-039 · strict >= 95 % (conservative): FAIL
- D-039 · header association >= in-run baseline: PASS
- D-039 · flips <= 0.5 %: PASS
- D-039 · census <= 1.0 %: FAIL
- D-039 · BUDGET/CBO manifest identical: PASS
- D-039 · clause-1 recall unchanged: PASS
- D-038 · plain strict >= 95 %: True
- D-038 · flips <= 0.5 %: True
- D-038 · census <= 1.0 %: False
- D-038 · BUDGET/CBO census and word conservation unchanged (byte-identical tables): True
- D-038 · header association (no threshold in D-038; reported): 90.88

| section | cells | forced | strict | conservative strict |
|---|---|---|---|---|
| eia-pdf-sec10 | 4603 | 15 | 91.68 | 91.38 |
| eia-pdf-sec12 | 1223 | 2 | 98.28 | 98.12 |
| eia-pdf-sec2 | 4850 | 5 | 98.33 | 98.23 |
| eia-pdf-sec5 | 256 | 0 | 100.0 | 100.0 |
| eia-pdf-sec6 | 1227 | 2 | 85.0 | 84.87 |
| eia-pdf-sec9 | 1572 | 1 | 99.94 | 99.87 |

## ERP

- D-039 · strict >= 95 % (plain): PASS
- D-039 · header association >= in-run baseline: PASS
- D-039 · flips <= 0.5 %: PASS
- D-039 · census <= 1.0 %: PASS
- D-039 · BUDGET/CBO manifest identical: PASS
- D-039 · clause-1 recall unchanged: PASS
- D-038 · plain strict >= 95 %: True
- D-038 · flips <= 0.5 %: True
- D-038 · census <= 1.0 %: True
- D-038 · BUDGET/CBO census and word conservation unchanged (byte-identical tables): True
- D-038 · header association (no threshold in D-038; reported): 97.37

## STEO

- D-039 · strict >= 95 % (plain): FAIL
- D-039 · header association >= in-run baseline: PASS
- D-039 · flips <= 0.5 %: PASS
- D-039 · census <= 1.0 %: PASS
- D-039 · BUDGET/CBO manifest identical: PASS
- D-039 · clause-1 recall unchanged: PASS
- D-038 · plain strict >= 95 %: False
- D-038 · flips <= 0.5 %: True
- D-038 · census <= 1.0 %: True
- D-038 · BUDGET/CBO census and word conservation unchanged (byte-identical tables): True
- D-038 · header association (no threshold in D-038; reported): 97.7

## Per table

| family | table | page | unit | emit | cells | forced | strict base | strict | cons. strict | header (base) | row NF | col NF | note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MER | 2.1a | 4 | `eia-pdf-sec2` | rebuilt | 627 | 0 | 48.8 | 99.2 | 99.2 | 13/15 (13/15) | 0 | 0 |  |
| MER | 2.1b | 5 | `eia-pdf-sec2` | rebuilt | 581 | 0 | 57.66 | 99.66 | 99.66 | 11/12 (11/12) | 0 | 0 |  |
| MER | 2.2 | 7 | `eia-pdf-sec2` | rebuilt | 599 | 1 | 51.92 | 99.17 | 99.0 | 11/13 (11/13) | 0 | 0 |  |
| MER | 2.3 | 9 | `eia-pdf-sec2` | rebuilt | 428 | 2 | 45.33 | 85.51 | 85.12 | 15/15 (13/15) | 0 | 0 |  |
| MER | 2.4 | 11 | `eia-pdf-sec2` | rebuilt | 630 | 1 | 44.44 | 99.21 | 99.05 | 13/15 (11/15) | 0 | 0 |  |
| MER | 2.5 | 13 | `eia-pdf-sec2` | rebuilt | 0 | 0 | None | None | None | 0/0 (0/0) | 0 | 0 |  |
| MER | 2.6 | 15 | `eia-pdf-sec2` | rebuilt | 727 | 1 | 52.13 | 99.72 | 99.59 | 13/13 (13/13) | 0 | 0 |  |
| MER | 2.7 | 16 | `eia-pdf-sec2` | rebuilt | 672 | 0 | 40.77 | 100.0 | 100.0 | 10/14 (6/14) | 0 | 0 |  |
| MER | 2.8 | 17 | `eia-pdf-sec2` | rebuilt | 586 | 0 | 69.45 | 100.0 | 100.0 | 10/12 (9/12) | 0 | 0 |  |
| MER | 2.5 | 22 | `eia-pdf-sec2` | ? | 0 | 0 | None | None | None | 0/0 (0/0) | 0 | 0 | no TableItem |
| MER | 5.1 | 3 | `eia-pdf-sec5` | rebuilt | 256 | 0 | 34.38 | 100.0 | 100.0 | 8/8 (8/8) | 0 | 0 |  |
| MER | 6.1 | 3 | `eia-pdf-sec6` | rebuilt | 449 | 0 | 69.04 | 100.0 | 100.0 | 8/8 (8/8) | 0 | 0 |  |
| MER | 6.2 | 4 | `eia-pdf-sec6` | fallback | 565 | 2 | 67.61 | 67.61 | 67.37 | 11/11 (11/11) | 0 | 0 |  |
| MER | 6.3 | 5 | `eia-pdf-sec6` | rebuilt | 213 | 0 | 43.66 | 99.53 | 99.53 | 8/8 (7/8) | 0 | 0 |  |
| MER | 6.2 | 9 | `eia-pdf-sec6` | ? | 0 | 0 | None | None | None | 0/0 (0/0) | 0 | 0 | no TableItem |
| MER | 6.3 | 10 | `eia-pdf-sec6` | ? | 0 | 0 | None | None | None | 0/0 (0/0) | 0 | 0 | no TableItem |
| MER | 9.1 | 3 | `eia-pdf-sec9` | rebuilt | 167 | 0 | 89.22 | 100.0 | 100.0 | 6/6 (6/6) | 0 | 0 |  |
| MER | 9.2 | 4 | `eia-pdf-sec9` | rebuilt | 83 | 0 | 80.72 | 100.0 | 100.0 | 3/4 (3/4) | 0 | 0 |  |
| MER | 9.3 | 5 | `eia-pdf-sec9` | rebuilt | 223 | 0 | 82.51 | 100.0 | 100.0 | 10/10 (10/10) | 0 | 0 |  |
| MER | 9.4 | 6 | `eia-pdf-sec9` | rebuilt | 0 | 0 | None | None | None | 0/0 (0/0) | 0 | 0 |  |
| MER | 9.5 | 7 | `eia-pdf-sec9` | rebuilt | 136 | 0 | 67.65 | 100.0 | 100.0 | 6/6 (6/6) | 0 | 0 |  |
| MER | 9.6 | 8 | `eia-pdf-sec9` | rebuilt | 189 | 0 | 71.43 | 100.0 | 100.0 | 7/7 (7/7) | 0 | 0 |  |
| MER | 9.7 | 9 | `eia-pdf-sec9` | rebuilt | 161 | 0 | 65.84 | 100.0 | 100.0 | 7/7 (7/7) | 0 | 0 |  |
| MER | 9.8 | 11 | `eia-pdf-sec9` | rebuilt | 150 | 0 | 34.67 | 100.0 | 100.0 | 4/5 (4/5) | 0 | 0 |  |
| MER | 9.9 | 13 | `eia-pdf-sec9` | rebuilt | 210 | 0 | 42.38 | 100.0 | 100.0 | 7/7 (7/7) | 0 | 0 |  |
| MER | 9.10 | 15 | `eia-pdf-sec9` | rebuilt | 253 | 1 | 30.83 | 99.6 | 99.21 | 9/9 (7/9) | 0 | 0 |  |
| MER | 9.1 | 18 | `eia-pdf-sec9` | ? | 0 | 0 | None | None | None | 0/0 (0/0) | 0 | 0 | no TableItem |
| MER | 10.1 | 3 | `eia-pdf-sec10` | rebuilt | 665 | 1 | 52.48 | 98.8 | 98.65 | 13/13 (13/13) | 0 | 0 |  |
| MER | 10.2a | 4 | `eia-pdf-sec10` | rebuilt | 596 | 1 | 38.76 | 99.83 | 99.66 | 13/13 (12/13) | 0 | 0 |  |
| MER | 10.2b | 5 | `eia-pdf-sec10` | rebuilt | 420 | 0 | 45.24 | 99.76 | 99.76 | 10/10 (8/10) | 0 | 0 |  |
| MER | 10.2c | 6 | `eia-pdf-sec10` | rebuilt | 657 | 2 | 38.2 | 96.19 | 95.9 | 13/13 (11/13) | 0 | 0 |  |
| MER | 10.3 | 7 | `eia-pdf-sec10` | rebuilt | 583 | 1 | 54.37 | 92.97 | 92.81 | 10/13 (7/13) | 0 | 0 |  |
| MER | 10.4a | 8 | `eia-pdf-sec10` | rebuilt | 517 | 1 | 67.12 | 96.13 | 95.95 | 11/13 (10/13) | 0 | 0 |  |
| MER | 10.4b | 9 | `eia-pdf-sec10` | fallback | 389 | 1 | 57.84 | 57.84 | 57.69 | 9/11 (9/11) | 0 | 0 |  |
| MER | 10.4c | 10 | `eia-pdf-sec10` | fallback | 311 | 8 | 60.45 | 60.45 | 58.93 | 4/11 (4/11) | 0 | 10 |  |
| MER | 10.5 | 11 | `eia-pdf-sec10` | rebuilt | 465 | 0 | 60.43 | 100.0 | 100.0 | 11/11 (10/11) | 0 | 0 |  |
| MER | 10.6 | 12 | `eia-pdf-sec10` | rebuilt | 0 | 0 | None | None | None | 0/0 (0/0) | 0 | 0 |  |
| MER | 10.4a | 20 | `eia-pdf-sec10` | ? | 0 | 0 | None | None | None | 0/0 (0/0) | 0 | 0 | no TableItem |
| MER | 10.4c | 22 | `eia-pdf-sec10` | ? | 0 | 0 | None | None | None | 0/0 (0/0) | 0 | 0 | no TableItem |
| MER | C1 | 22 | `eia-pdf-sec12` | rebuilt | 233 | 0 | 92.7 | 100.0 | 100.0 | 7/7 (7/7) | 0 | 0 |  |
| MER | E1 | 30 | `eia-pdf-sec12` | rebuilt | 4 | 0 | 25.0 | 100.0 | 100.0 | 1/2 (0/2) | 0 | 0 |  |
| MER | E2 | 31 | `eia-pdf-sec12` | rebuilt | 2 | 0 | 100.0 | 100.0 | 100.0 | 1/1 (1/1) | 0 | 0 |  |
| MER | E3 | 32 | `eia-pdf-sec12` | rebuilt | 2 | 0 | 100.0 | 100.0 | 100.0 | 1/1 (1/1) | 0 | 0 |  |
| MER | E4 | 33 | `eia-pdf-sec12` | rebuilt | 421 | 1 | 28.27 | 95.01 | 94.79 | 12/13 (12/13) | 0 | 0 |  |
| MER | F1 | 36 | `eia-pdf-sec12` | rebuilt | 561 | 1 | 68.09 | 100.0 | 99.82 | 13/14 (13/14) | 0 | 0 |  |
| ERP | ERP-2026-table43 sheet0 | 1 | `govinfo-ERP-2026-table43` | rebuilt | 804 | 0 | 38.68 | 100.0 | 100.0 | 11/12 (9/12) | 0 | 0 |  |
| ERP | ERP-2026-table52 sheet0 | 1 | `govinfo-ERP-2026-table52` | rebuilt | 713 | 0 | 4.21 | 100.0 | 100.0 | 12/12 (11/12) | 0 | 0 |  |
| ERP | ERP-2026-table7 sheet0 | 1 | `govinfo-ERP-2026-table7` | rebuilt | 737 | 0 | 60.11 | 100.0 | 100.0 | 11/11 (11/11) | 0 | 0 |  |
| ERP | ERP-2026-table28 sheet0 | 1 | `govinfo-ERP-2026-table28` | rebuilt | 897 | 0 | 43.92 | 100.0 | 100.0 | 12/13 (12/13) | 0 | 0 |  |
| ERP | ERP-2026-table10 sheet0 | 1 | `govinfo-ERP-2026-table10` | rebuilt | 871 | 0 | 40.41 | 100.0 | 100.0 | 13/13 (12/13) | 0 | 0 |  |
| ERP | ERP-2026-table14 sheet0 | 1 | `govinfo-ERP-2026-table14` | rebuilt | 995 | 0 | 0.0 | 100.0 | 100.0 | 15/15 (14/15) | 0 | 0 |  |
| STEO | 3a | 35 | `eia-archives-aug26` | not fired | 30 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 3b | 36 | `eia-archives-aug26` | rebuilt | 60 | 0 | 96.67 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 3c | 37 | `eia-archives-aug26` | rebuilt | 131 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 3d | 38 | `eia-archives-aug26` | rebuilt | 119 | 0 | 100.0 | 100.0 | 100.0 | 7/7 (7/7) | 0 | 0 |  |
| STEO | 3e | 39 | `eia-archives-aug26` | not fired | 18 | 0 | 100.0 | 100.0 | 100.0 | 14/15 (14/15) | 0 | 0 |  |
| STEO | 4b | 41 | `eia-archives-aug26` | rebuilt | 30 | 0 | 63.33 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 4d | 43 | `eia-archives-aug26` | rebuilt | 75 | 0 | 97.33 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 5a | 44 | `eia-archives-aug26` | not fired | 30 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 6 | 46 | `eia-archives-aug26` | not fired | 60 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 7a | 47 | `eia-archives-aug26` | rebuilt | 60 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 7b | 48 | `eia-archives-aug26` | rebuilt | 30 | 0 | 93.33 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 7d | 50 | `eia-archives-aug26` | rebuilt | 75 | 0 | 48.0 | 100.0 | 100.0 | 15/15 (14/15) | 0 | 0 |  |
| STEO | 7d | 51 | `eia-archives-aug26` | rebuilt | 45 | 0 | 80.0 | 100.0 | 100.0 | 15/15 (11/15) | 0 | 0 |  |
| STEO | 7e | 52 | `eia-archives-aug26` | not fired | 165 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 8 | 53 | `eia-archives-aug26` | not fired | 75 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 9b | 55 | `eia-archives-aug26` | rebuilt | 45 | 0 | 95.56 | 100.0 | 100.0 | 15/15 (14/15) | 0 | 0 |  |
| STEO | 9c | 56 | `eia-archives-aug26` | not fired | 75 | 0 | 100.0 | 100.0 | 100.0 | 15/15 (15/15) | 0 | 0 |  |
| STEO | 10a | 57 | `eia-archives-aug26` | fallback | 98 | 0 | 27.55 | 27.55 | 27.55 | 2/7 (2/7) | 21 | 0 |  |
| STEO | 10b | 58 | `eia-archives-aug26` | fallback | 56 | 0 | 100.0 | 100.0 | 100.0 | 7/7 (7/7) | 0 | 0 |  |
