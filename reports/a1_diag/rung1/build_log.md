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
- **04:50-05:00Z step 6 (BUDGET/CBO, fired tables only; not held-out).** First run: 151 fired
  BUDGET/CBO tables, 78 fell back, 73 changed tables, 13,795 changed label-number pairs. Causes,
  all in my code: (1) these PDFs encode spaces as zero-gap space characters, which the tokenizer
  (reused from the frozen trigger) dropped, fusing words ("Militarypersonnel") - the emitter now
  has its own tokenizer (the trigger stays frozen; the same dropping affects its BUDGET counts,
  reported as a finding); (2) BUDGET's leader glyphs decode as runs of U+FFFD with a U+0008 prefix
  from Docling - neither the emitter nor the A4 guard normaliser (`guards.norm_words`, committed at
  f54ac57) treated them as leaders. **Guard correction (v2):** the leader class now includes U+FFFD
  runs and U+0008, applied identically to baseline and rung 1; the report gives clause 4 and word
  conservation under both v1 (as committed) and v2. (3) Numbers outside the body (bill numbers in
  titles, footnote markers, function codes in stubs) formed thin bands: body lines are now defined
  by dense bands (>= max(2, 10 %) tokens), a thin band right of the first dense band is kept only
  when a header sits above it (a sparse column), prose lines are not body. (4) Wrap vs section
  header: a text-only line ending ":" is a section header; a wrap needs a continuation sign.
  Tuning unchanged at 96.7 % after each. Now: 47 fallbacks, 104 changed tables. Many changes are
  corrections (TableFormer welded section headers onto stubs: "252 Space flight...: NASA" ->
  "NASA"); the literal clause-4 guard counts them as FAIL (C4) - not worked around.
