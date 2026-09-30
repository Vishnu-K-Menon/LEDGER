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

| # | table | page | row label (printed) | period | expected | page prints on that line, in the cell's band | owner: provably != page? |
|---|---|---|---|---|---|---|---|
| 1 | 3.7b | 22 | September | Propane Consumed by the Industrial Sector (Thousand Barrels per Day) | 447 | 400 | |
| 2 | 3.7a | 21 | March | Motor Gasoline Consumed by the Commercial Sector (Thousand Barrels per Day) | 171 | 172 | |
| 3 | 3.3a | 7 | October | Petroleum Imports as Share of Products Supplied (Percent) | 35.8 | 36.0 | |
| 4 | 3.31 | 13 | November | Petroleum Exports to Canada (Thousand Barrels per Day) | 835 | 834 | |
| 5 | 3.7c | 23 | October | Lubricants Consumed by the Transportation Sector (Thousand Barrels per Day) | 52 | 50 | |
| 6 | 3.7a | 21 | September | Distillate Fuel Oil Consumed by the Commercial Sector (Thousand Barrels per Day) | 102 | 101 | |
| 7 | 1.4c | 13 | 2025 January | Biomass Net Imports (Quadrillion Btu) | -0.034 | -.030 | |
| 8 | 1.13a | 26 | May | Natural Gas Non-Combustion Consumption (Billion Cubic Feet) | 74 | 75 | |
| 9 | 3.8b | 27 | November | Petroleum Coke Consumed by the Industrial Sector (Trillion Btu) | 20 | 19 | |
| 10 | 3.3e | 12 | June | Jet Fuel Exports (Thousand Barrels per Day) | 251 | 252 | |
| 11 | 3.7b | 22 | October | Residual Fuel Oil Consumed by the Industrial Sector (Thousand Barrels per Day) | 20 | 19 | |
| 12 | 3.8c | 28 | April | Jet Fuel Consumed by the Transportation Sector (Trillion Btu) | 304 | 300 | |
| 13 | 3.7a | 21 | February ••••••••••••••••• | Propane Consumed by the Commercial Sector (Thousand Barrels per Day) | 220 | 208 | |
| 14 | 1.4c | 13 | September | Petroleum Products, Excluding Biofuels, Net Imports (Quadrillion Btu) | -0.653 | -.637 | |
| 15 | 1.12 | 25 | February | Cooling Degree-Days, Pacific (Number) | 8 | Ra | |
| 16 | 3.7c | 23 | August | Residual Fuel Oil Consumed by the Transportation Sector (Thousand Barrels per Day) | 222 | 219 | |
| 17 | 1.13b | 27 | March | Other Petroleum Non-Combustion Consumption (Quadrillion Btu) | 0.016 | .015 | |
| 18 | 3.1 | 3 | 2025 January | Petroleum Adjustments (Thousand Barrels per Day) | -10 | -260 | |
| 19 | 3.8b | 27 | 2025 January | Asphalt and Road Oil Consumed by the Industrial Sector (Trillion Btu) | 47 | 46 | |
| 20 | 3.5 | 17 | June | Propane/Propylene Product Supplied (Thousand Barrels per Day) | 862 | 794 | |
| 21 | 1.13b | 27 | 2025 January | Hydrocarbon Gas Liquids Non-Combustion Consumption (Quadrillion Btu) | 0.311 | .310 | |
| 22 | 3.6 | 19 | May | Propane Product Supplied (Trillion Btu) | 70 | 65 | |
| 23 | 3.4 | 15 | June | Jet Fuel Stocks (Million Barrels) | 45 | 44 | |
| 24 | 1.13a | 26 | October | Lubricants Non-Combustion Consumption (Thousand Barrels per Day) | 100 | 96 | |
| 25 | 3.7a | 21 | February | Propane Consumed by the Commercial Sector (Thousand Barrels per Day) | 227 | 215 | |
| 26 | 1.13a | 26 | March | Special Naphthas Non-Combustion Consumption (Thousand Barrels per Day) | 34 | 36 | |
| 27 | 3.3b | 9 | June | Propane/Propylene Imports (Thousand Barrels per Day) | 106 | 105 | |
| 28 | 1.2 | 5 | May | Total Renewable Energy Production (Quadrillion Btu) | 0.799 | .797 | |
| 29 | 3.8a | 26 | February | Residual Fuel Oil Consumed by the Commercial Sector (Trillion Btu) | 1 | (s) | |
| 30 | 3.3e | 12 | August | Jet Fuel Exports (Thousand Barrels per Day) | 202 | 200 | |
