# Rung-1 build log (Part B; clock in clock.txt)

Only the two tuning tables (3.6 sec3 p19 t10, 4.2b sec4 p5 t2) and non-held-out BUDGET/CBO tables
are looked at during Part B.

- **04:48Z B1.** Naive emitter (rows from numeric lines, right-edge bands, TableFormer header rows
  by x-overlap; no wrap rule, no header check, no band assertion) on sec4 p5: **791 / 794 =
  99.6 % strict** -> **emitter path** (>= 80 %; owner fill (i)). sec3 p19 93.5 %; tuning
  1,465 / 1,515 = 96.7 % (baseline 45.3 %).
- **04:49Z B2 rows / wrap / columns / headers.** All switches on: strict unchanged (96.7 %);
  header association sec3 5/15 -> 13/15, sec4 12/14 -> 14/14 (the page-word check replaced
  TableFormer header text on 8 sec3 bands and 2 sec4 bands). Residual tuning misses, read on the
  two tuning tables only: 12 R/E-flagged cells (the page prints "E18"; flags stay in the cell,
  choice C3, and `canon()` rejects them), about 36 revision-window cells on sec3 and 3 on sec4
  where the page prints a different number from the admitted export value (A6 admits a value
  printed anywhere in the bbox: an oracle limit, not a parse error), one "( d)" footnote split.
