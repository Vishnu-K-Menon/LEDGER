# D-039 item 1 - A6 clause-(b) sizing on the burned pilot MER tables

Admitted MER cells (A6: the value is printed somewhere in the table bbox), checked against the raw text layer: is the value printed on its own row label's line? Method: `scripts/a1_diag/rung1b/f5_sizing.py` docstring. Sizes only; nothing is fixed.

**19,761 admitted MER cells on 47 tables (all burned).**

| outcome | cells | share |
|---|---|---|
| on the line | 19,093 | 96.62% |
| on the line only with a revision flag | 58 | 0.29% |
| not on the line | 610 | 3.09% |
| row line not found | 0 | 0.00% |

| stratum | on the line | flag only | not on the line | row not found |
|---|---|---|---|---|
| row year <= 2023 | 8,684 | 7 | 9 | 0 |
| row year >= 2024 | 10,409 | 51 | 601 | 0 |

Whitespace-tolerant strip measured read-only: 96 cells on the line → flag only; not-on-the-line set identical (610); admitted under the owner fill 19,151 under both. The checker keeps its committed single-token strip (D-039 status 2026-09-30).

## Strata of the 610 not-on-the-line cells (D-039 status 2026-09-30)

Band class per cell: the 23 anomalous cells from the diagnosis (`F5_dump.md`, crops checked); a single numeric band token after the R / E / RE strip (attached or whitespace-separated) = numeric-but-different; NA / (s) = placeholder.

| band class | cells | conservative-strict miss? |
|---|---|---|
| numeric-but-different | 579 | no - out of the denominator when clause (b) is applied |
| digit-on-other-line | 13 | yes (checker geometry) |
| placeholder (NA / (s)) | 8 | no - page != export; with numeric-but-different |
| no-digit-at-position | 5 | yes (decode defect) |
| footnote-fused | 2 | yes |
| outside | 1 | no - numeric-but-different (owner ruling 2026-09-30: #20, flag RF on a different number) |
| split-token, joined != value (numeric-but-different) | 1 | no - numeric-but-different |
| split-token, joined == value | 1 | yes (checker geometry) |

Conservative-strict miss set (decode / footnote-fused / empty-band checker geometry / split-token joined = value only): **21** cells = 0.11% of 19,761 (reference bound 0.5 %). #20 (`RF4`) ruled numeric-but-different; #6 / #7 (`EgQ`, `E13Q`) stay in the miss set by the rule's letter (owner, D-039 status 2026-09-30). Numeric-but-different and placeholder cells leave the denominator when clause (b) is applied to admission and are NOT in the miss set.

**Numeric decode (visually verified):** 3.5 p17 M:2026-05, Kerosene Product Supplied, expected 6: crop `f5_crops/20_3.5_M-2026-06.png` (the row above #20) shows "R 6"; the text layer reads `R5`, so the cell is classed numeric-but-different though the page prints the expected value. Decode defects can yield digits; the owner hand-check (29/30 page = text layer) bounds such cells at ≈ 0-10 % of the 579 numeric-but-different (estimate, ≤ ≈ 0.3 % of 19,761).

## Per table

| table | cells | not on the line | flag only | row not found |
|---|---|---|---|---|
| 1.1 p3 (eia-pdf-sec1) | 483 | 5 | 1 | 0 |
| 1.2 p5 (eia-pdf-sec1) | 569 | 5 | 0 | 0 |
| 1.3 p7 (eia-pdf-sec1) | 603 | 3 | 0 | 0 |
| 1.4a p9 (eia-pdf-sec1) | 444 | 2 | 2 | 0 |
| 1.4b p11 (eia-pdf-sec1) | 410 | 7 | 2 | 0 |
| 1.4c p13 (eia-pdf-sec1) | 414 | 9 | 1 | 0 |
| 1.5 p15 (eia-pdf-sec1) | 519 | 0 | 0 | 0 |
| 1.6 p17 (eia-pdf-sec1) | 192 | 5 | 0 | 0 |
| 1.7 p19 (eia-pdf-sec1) | 497 | 0 | 0 | 0 |
| 1.8 p21 (eia-pdf-sec1) | 587 | 2 | 0 | 0 |
| 1.9 p22 (eia-pdf-sec1) | 30 | 0 | 0 | 0 |
| 1.10 p23 (eia-pdf-sec1) | 64 | 0 | 1 | 0 |
| 1.11 p24 (eia-pdf-sec1) | 488 | 2 | 2 | 0 |
| 1.12 p25 (eia-pdf-sec1) | 518 | 1 | 6 | 0 |
| 1.13a p26 (eia-pdf-sec1) | 450 | 35 | 0 | 0 |
| 1.13b p27 (eia-pdf-sec1) | 554 | 37 | 0 | 0 |
| 11.1 p3 (eia-pdf-sec11) | 644 | 21 | 0 | 0 |
| 11.2 p5 (eia-pdf-sec11) | 339 | 1 | 0 | 0 |
| 11.3 p6 (eia-pdf-sec11) | 431 | 3 | 0 | 0 |
| 11.4 p7 (eia-pdf-sec11) | 592 | 15 | 1 | 0 |
| 11.5 p8 (eia-pdf-sec11) | 436 | 18 | 0 | 0 |
| 11.6 p9 (eia-pdf-sec11) | 347 | 2 | 0 | 0 |
| 11.7 p10 (eia-pdf-sec11) | 564 | 2 | 0 | 0 |
| 3.1 p3 (eia-pdf-sec3) | 172 | 25 | 0 | 0 |
| 3.2 p5 (eia-pdf-sec3) | 328 | 15 | 7 | 0 |
| 3.3a p7 (eia-pdf-sec3) | 263 | 15 | 1 | 0 |
| 3.3b p9 (eia-pdf-sec3) | 279 | 37 | 2 | 0 |
| 3.3c p10 (eia-pdf-sec3) | 238 | 12 | 12 | 0 |
| 3.3d p11 (eia-pdf-sec3) | 254 | 3 | 0 | 0 |
| 3.3e p12 (eia-pdf-sec3) | 161 | 9 | 0 | 0 |
| 3.31 p13 (eia-pdf-sec3) | 233 | 27 | 0 | 0 |
| 3.4 p15 (eia-pdf-sec3) | 346 | 22 | 5 | 0 |
| 3.5 p17 (eia-pdf-sec3) | 313 | 32 | 3 | 0 |
| 3.6 p19 (eia-pdf-sec3) | 721 | 37 | 8 | 0 |
| 3.7a p21 (eia-pdf-sec3) | 225 | 38 | 0 | 0 |
| 3.7b p22 (eia-pdf-sec3) | 277 | 46 | 0 | 0 |
| 3.7c p23 (eia-pdf-sec3) | 295 | 22 | 0 | 0 |
| 3.8a p26 (eia-pdf-sec3) | 476 | 30 | 1 | 0 |
| 3.8b p27 (eia-pdf-sec3) | 630 | 45 | 1 | 0 |
| 3.8c p28 (eia-pdf-sec3) | 641 | 17 | 0 | 0 |
| 4.1 p3 (eia-pdf-sec4) | 538 | 0 | 2 | 0 |
| 4.2a p4 (eia-pdf-sec4) | 751 | 0 | 0 | 0 |
| 4.2b p5 (eia-pdf-sec4) | 794 | 3 | 0 | 0 |
| 4.3 p6 (eia-pdf-sec4) | 519 | 0 | 0 | 0 |
| 4.4 p7 (eia-pdf-sec4) | 427 | 0 | 0 | 0 |
| 8.1 p3 (eia-pdf-sec8) | 274 | 0 | 0 | 0 |
| 8.2 p5 (eia-pdf-sec8) | 431 | 0 | 0 | 0 |

## Hand-check list: 30 not-on-the-line cells (seed 20260930)

For each: does the page print the expected value on this row's line? (owner hand-check)

| # | table | page | row key | row label (printed) | series (period column) | expected | page prints on that line, in the cell's band | band class | owner: provably != page? |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 3.7b | 22 | M:2025-09 | September | Propane Consumed by the Industrial Sector (Thousand Barrels per Day) | 447 | 400 | numeric-but-different | |
| 2 | 3.7a | 21 | M:2025-03 | March | Motor Gasoline Consumed by the Commercial Sector (Thousand Barrels per Day) | 171 | 172 | numeric-but-different | |
| 3 | 3.3a | 7 | M:2025-10 | October | Petroleum Imports as Share of Products Supplied (Percent) | 35.8 | 36.0 | numeric-but-different | |
| 4 | 3.31 | 13 | M:2025-11 | November | Petroleum Exports to Canada (Thousand Barrels per Day) | 835 | 834 | numeric-but-different | |
| 5 | 3.7c | 23 | M:2025-10 | October | Lubricants Consumed by the Transportation Sector (Thousand Barrels per Day) | 52 | 50 | numeric-but-different | |
| 6 | 3.7a | 21 | M:2025-09 | September | Distillate Fuel Oil Consumed by the Commercial Sector (Thousand Barrels per Day) | 102 | 101 | numeric-but-different | |
| 7 | 1.4c | 13 | M:2025-01 | 2025 January | Biomass Net Imports (Quadrillion Btu) | -0.034 | -.030 | numeric-but-different | |
| 8 | 1.13a | 26 | M:2025-05 | May | Natural Gas Non-Combustion Consumption (Billion Cubic Feet) | 74 | 75 | numeric-but-different | |
| 9 | 3.8b | 27 | M:2025-11 | November | Petroleum Coke Consumed by the Industrial Sector (Trillion Btu) | 20 | 19 | numeric-but-different | |
| 10 | 3.3e | 12 | M:2025-06 | June | Jet Fuel Exports (Thousand Barrels per Day) | 251 | 252 | numeric-but-different | |
| 11 | 3.7b | 22 | M:2025-10 | October | Residual Fuel Oil Consumed by the Industrial Sector (Thousand Barrels per Day) | 20 | 19 | numeric-but-different | |
| 12 | 3.8c | 28 | M:2025-04 | April | Jet Fuel Consumed by the Transportation Sector (Trillion Btu) | 304 | 300 | numeric-but-different | |
| 13 | 3.7a | 21 | M:2026-02 | February ••••••••••••••••• | Propane Consumed by the Commercial Sector (Thousand Barrels per Day) | 220 | 208 | numeric-but-different | |
| 14 | 1.4c | 13 | M:2025-09 | September | Petroleum Products, Excluding Biofuels, Net Imports (Quadrillion Btu) | -0.653 | -.637 | numeric-but-different | |
| 15 | 1.12 | 25 | M:2025-02 | February | Cooling Degree-Days, Pacific (Number) | 8 | Ra | no-digit-at-position | |
| 16 | 3.7c | 23 | M:2025-08 | August | Residual Fuel Oil Consumed by the Transportation Sector (Thousand Barrels per Day) | 222 | 219 | numeric-but-different | |
| 17 | 1.13b | 27 | M:2025-03 | March | Other Petroleum Non-Combustion Consumption (Quadrillion Btu) | 0.016 | .015 | numeric-but-different | |
| 18 | 3.1 | 3 | M:2025-01 | 2025 January | Petroleum Adjustments (Thousand Barrels per Day) | -10 | -260 | numeric-but-different | |
| 19 | 3.8b | 27 | M:2025-01 | 2025 January | Asphalt and Road Oil Consumed by the Industrial Sector (Trillion Btu) | 47 | 46 | numeric-but-different | |
| 20 | 3.5 | 17 | M:2025-06 | June | Propane/Propylene Product Supplied (Thousand Barrels per Day) | 862 | 794 | numeric-but-different | |
| 21 | 1.13b | 27 | M:2025-01 | 2025 January | Hydrocarbon Gas Liquids Non-Combustion Consumption (Quadrillion Btu) | 0.311 | .310 | numeric-but-different | |
| 22 | 3.6 | 19 | M:2025-05 | May | Propane Product Supplied (Trillion Btu) | 70 | 65 | numeric-but-different | |
| 23 | 3.4 | 15 | M:2025-06 | June | Jet Fuel Stocks (Million Barrels) | 45 | 44 | numeric-but-different | |
| 24 | 1.13a | 26 | M:2025-10 | October | Lubricants Non-Combustion Consumption (Thousand Barrels per Day) | 100 | 96 | numeric-but-different | |
| 25 | 3.7a | 21 | M:2025-02 | February | Propane Consumed by the Commercial Sector (Thousand Barrels per Day) | 227 | 215 | numeric-but-different | |
| 26 | 1.13a | 26 | M:2025-03 | March | Special Naphthas Non-Combustion Consumption (Thousand Barrels per Day) | 34 | 36 | numeric-but-different | |
| 27 | 3.3b | 9 | M:2025-06 | June | Propane/Propylene Imports (Thousand Barrels per Day) | 106 | 105 | numeric-but-different | |
| 28 | 1.2 | 5 | M:2025-05 | May | Total Renewable Energy Production (Quadrillion Btu) | 0.799 | .797 | numeric-but-different | |
| 29 | 3.8a | 26 | M:2025-02 | February | Residual Fuel Oil Consumed by the Commercial Sector (Trillion Btu) | 1 | (s) | placeholder (NA / (s)) | |
| 30 | 3.3e | 12 | M:2025-08 | August | Jet Fuel Exports (Thousand Barrels per Day) | 202 | 200 | numeric-but-different | |
