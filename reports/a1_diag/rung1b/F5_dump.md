# D-039 clause (b): the 23 anomalous cells, diagnosed (burned MER tables)

Chars per cell in `F5_dump.json`; crops in `f5_crops/`. `preclass` = the automatic reading of the char dump; `class` = confirmed on the crop by eye (the committed outcomes).

| # | table | page | row | expected | band text | band chars [font,size] | preclass | **class** | the page shows | crop |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1.8 | 21 | A:2006 | 17.8 | `17.!;!` | 1[Helvetica,6.9] 7[Helvetica,6.9] .[Helvetica,6.9] ![Helvetica,6.9] ;[ | no-digit-at-position | **no-digit-at-position** | prints 17.8 (= expected); the 8 decodes as '!;!' | `01_1.8_A-2006.png` |
| 2 | 1.8 | 21 | A:2007 | 17.1 | `b17.1` | 1[Helvetica,6.9] 7[Helvetica,6.9] .[Helvetica,6.9] 1[Helvetica,6.9]  [ | no-digit-at-position | **footnote-fused** | prints superscript b + 17.1 (= expected) | `02_1.8_A-2007.png` |
| 3 | 1.12 | 25 | M:2025-02 | 8 | `Ra` | R[Helvetica,7.6] a[Helvetica,7.6]  [Helvetica,7.6] | no-digit-at-position | **no-digit-at-position** | prints superscript R + 8 (= expected); the 8 decodes as 'a' | `03_1.12_M-2025-02.png` |
| 4 | 11.6 | 9 | A:2023 | 6 | `(nothing in the band)` | 9[Helvetica-Bold,6.6]  [Helvetica-Bold,6.6] 9[Helvetica-Bold,6.6]  [He | digit-on-other-line | **digit-on-other-line** | bold annual row; the band digits are grouped onto another line | `04_11.6_A-2023.png` |
| 5 | 11.6 | 9 | A:2023 | 5 | `(nothing in the band)` | 4[Helvetica-Bold,6.6] 6[Helvetica-Bold,6.6] 5[Helvetica-Bold,6.6] | digit-on-other-line | **digit-on-other-line** | bold annual row; the band digits are grouped onto another line | `05_11.6_A-2023.png` |
| 6 | 3.3b | 9 | M:2026-06 | 105 | `EgQ` | E[Helvetica,5.9] g[Helvetica,5.9] Q[Helvetica,5.9]  [Helvetica,5.9] | no-digit-at-position | **no-digit-at-position** | prints superscript E + 90 (!= expected 105); 90 decodes as 'gQ' | `06_3.3b_M-2026-06.png` |
| 7 | 3.3b | 9 | M:2026-06 | 103 | `E13Q` | 1[Helvetica,5.9] 3[Helvetica,5.9] Q[Helvetica,5.9] | digit-on-other-line | **no-digit-at-position** | prints superscript E + 130 (!= expected 103); the 0 decodes as 'Q' | `07_3.3b_M-2026-06.png` |
| 8 | 3.3d | 11 | M:2025-01 | 1 | `(nothing in the band)` | (none) | digit-on-other-line | **digit-on-other-line** | prints 1 (= expected) on the row; the glyph grouped onto another line | `08_3.3d_M-2025-01.png` |
| 9 | 3.3d | 11 | M:2026-01 | 1070 | `1,Q70` | 1[Helvetica,6.9] ,[Helvetica,6.9] Q[Helvetica,6.9] 7[Helvetica,6.9] 0[ | no-digit-at-position | **no-digit-at-position** | prints 1,070 (= expected); the 0 decodes as 'Q' | `09_3.3d_M-2026-01.png` |
| 10 | 3.4 | 15 | M:2025-01 | 1 | `(nothing in the band)` | (none) | digit-on-other-line | **digit-on-other-line** | prints 1 (= expected) on the row; the glyph grouped onto another line | `10_3.4_M-2025-01.png` |
| 11 | 3.4 | 15 | M:2025-02 | 1 | `(nothing in the band)` | (none) | digit-on-other-line | **digit-on-other-line** | prints 1 (= expected) on the row; the glyph grouped onto another line | `11_3.4_M-2025-02.png` |
| 12 | 3.4 | 15 | M:2025-03 | 1 | `(nothing in the band)` | (none) | value-on-line-but-band-empty | **digit-on-other-line** | prints 1 (= expected) on the row; the glyph grouped onto another line | `12_3.4_M-2025-03.png` |
| 13 | 3.4 | 15 | M:2025-04 | 1 | `(nothing in the band)` | (none) | value-on-line-but-band-empty | **digit-on-other-line** | prints 1 (= expected) on the row; the glyph grouped onto another line | `13_3.4_M-2025-04.png` |
| 14 | 3.4 | 15 | M:2025-05 | 1 | `(nothing in the band)` | (none) | value-on-line-but-band-empty | **digit-on-other-line** | prints 1 (= expected) on the row; the glyph grouped onto another line | `14_3.4_M-2025-05.png` |
| 15 | 3.4 | 15 | M:2025-06 | 1 | `(nothing in the band)` | (none) | value-on-line-but-band-empty | **digit-on-other-line** | prints 1 (= expected) on the row; the glyph grouped onto another line | `15_3.4_M-2025-06.png` |
| 16 | 3.4 | 15 | M:2025-07 | 1 | `(nothing in the band)` | (none) | value-on-line-but-band-empty | **digit-on-other-line** | prints 1 (= expected) on the row; the glyph grouped onto another line | `16_3.4_M-2025-07.png` |
| 17 | 3.4 | 15 | M:2025-08 | 1 | `(nothing in the band)` | (none) | value-on-line-but-band-empty | **digit-on-other-line** | prints 1 (= expected) on the row; the glyph grouped onto another line | `17_3.4_M-2025-08.png` |
| 18 | 3.4 | 15 | M:2025-09 | 1 | `(nothing in the band)` | (none) | value-on-line-but-band-empty | **digit-on-other-line** | prints 1 (= expected) on the row; the glyph grouped onto another line | `18_3.4_M-2025-09.png` |
| 19 | 3.4 | 15 | M:2025-10 | 1 | `(nothing in the band)` | (none) | value-on-line-but-band-empty | **digit-on-other-line** | prints 1 (= expected) on the row; the glyph grouped onto another line | `19_3.4_M-2025-10.png` |
| 20 | 3.5 | 17 | M:2026-06 | 14 | `RF4` | R[Helvetica,6.7] F[Helvetica,6.7] 4[Helvetica,6.7]  [Helvetica,6.7] | digit-on-other-line | **outside** | prints superscript RF + 4 (!= expected 14): flag 'RF' is not in the R/E/RE strip | `20_3.5_M-2026-06.png` |
| 21 | 3.7a | 21 | M:2026-05 | 225 | `21 3` | 2[Helvetica,6.9] 1[Helvetica,6.9] 3[Helvetica,6.9]  [Helvetica,6.9] | split-token, joined != value (numeric-but-different) | **split-token, joined != value (numeric-but-different)** | prints 213 (!= expected 225) | `21_3.7a_M-2026-05.png` |
| 22 | 3.8c | 28 | A:2010 | 5 | `d5` | d[Helvetica,6.8] 5[Helvetica,6.8]  [Helvetica,6.8] | footnote-fused | **footnote-fused** | prints superscript d + 5 (= expected) | `22_3.8c_A-2010.png` |
| 23 | 3.8c | 28 | M:2024-02 | 2017 | `2,01 7` | 2[Helvetica,6.8] ,[Helvetica,6.8] 0[Helvetica,6.8] 1[Helvetica,6.8] 7[ | split-token, joined == value | **split-token, joined == value** | prints 2,017 (= expected); x-gap split '2,01 7' | `23_3.8c_M-2024-02.png` |

Classes: no-digit-at-position 5, footnote-fused 2, digit-on-other-line 13, outside 1, split-token, joined != value (numeric-but-different) 1, split-token, joined == value 1
