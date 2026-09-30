# A4 - A1-regression guard baselines and evaluation baselines (current parse, data/parsed)

Definitions: `scripts/a1_diag/rung1/guards.py` (flip normalisation, pairing loss, label-number
pairs C4, word conservation C5), committed with this file, before any rung-1 output exists.

**Hashes.** Full baseline (per-cell outcomes, 704 BUDGET/CBO table records) - 7.3 MB, kept local
at `data/parsed_rung1/_baseline/baseline_guards.json`, regenerable from `data/parsed/`:
sha256 `e2a8e12d1cf7787540b13a971591c53b7c5471c48cc537d8434b3aa38f9bcc0f`. Owner scripts'
`pdf_results.json` (baseline run `reports/a1_diag/repro/rung1base/`): sha256
`c193f5972c5c24d0547a706dbc998836fd86ae15b624f079d5bf0d344060141a`.

## Scorers with per-cell detail (C9) reproduce the baseline exactly

| family | strict | row not found | column not found |
|---|---|---|---|
| MER held-out (per-cell admission, later edition) | 9,149 / 18,246 = 50.1 % | 47 | 839 |
| ERP (same edition) | 1,522 / 2,764 = 55.1 % | 0 | 67 |
| STEO (whole-row admission, same edition) | 11,280 / 13,046 = 86.5 % | 742 | 45 |
| tuning (3.6, 4.2b) | 687 / 1,515 = 45.3 % | 0 | 57 |

STEO cells lost to repeated-label pairing at baseline: **274**. MER/ERP: n/a (period keys).

## Guard (1): number recall and merged-cell ceiling, the eight A1 PDF tables

| table | page | number recall | merged (body) | ceiling |
|---|---|---|---|---|
| govinfo-BUDGET-2026-DOD #/tables/446 | 94 | 100.0 % | 13 | 88.8 % |
| govinfo-BUDGET-2026-DOD #/tables/112 | 27 | 100.0 % | 1 | 99.0 % |
| govinfo-BUDGET-2026-CROSSCUT #/tables/45 | 56 | 100.0 % | 0 | 100.0 % |
| eia-pdf-steo_full #/tables/10 | 38 | 99.9 % | 67 | 82.0 % |
| cbo-61959 #/tables/0 | 1 | 100.0 % | 0 | 100.0 % |
| eia-pdf-sec3 #/tables/10 | 19 | 100.0 % | 197 | 45.9 % |
| eia-pdf-sec11 #/tables/3 | 7 | 100.0 % | 85 | 74.4 % |
| eia-pdf-sec4 #/tables/2 | 5 | 100.0 % | 163 | 51.1 % |

A1 reproduced: ERP strict 1,179 / 2,116 = 55.7 % · PDF ceiling 73.6 % · combined 67.4 %.

## Guard (2): ERP through the oracle - 55.1 % strict (table above).

## Guards (3)-(5) and the pass-rule census / conservation lines

- BUDGET/CBO: 704 tables (BUDGET 698, CBO 6); per-table sha256 of the table dict, label-number
  pairs (49,109 in all), word conservation (mean conserved share 0.778, excess 66,958 words).
- Census, merged body cells (`census.py --label rung1base`): EIA 12.4 % · ERP 19.2 % ·
  BUDGET 1.0 % · CBO 0.2 % · all 5.5 %.
- Trigger fires on BUDGET 148 / 698, CBO 3 / 6 (A1 dry-run).
