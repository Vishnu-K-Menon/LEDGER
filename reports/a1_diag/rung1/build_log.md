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
- **05:03-05:12Z headers, trims, guard v2.** (a) Header-region words over no band go to the
  stub column's header cell; stub-only lines between the column-header block and the first body
  line are section rows (they were dropped). (b) The minus split applies only with a decimal or
  comma on either side (account codes "097-0118-0-1-051" and year ranges stay whole). (c) Trim:
  below the last numeric line only the footer block (Source / Note / footnote marker / legend
  "X =") is cut; text rows are kept (CBO summary tables' "Contains ... mandate? No"); a CBO "*"
  followed by a digit is a value placeholder, not a footnote. (d) Header cells are span-aware
  (TableFormer spans kept via the column->band map; page-derived cells span the failing bands
  they cover), so a spanning word is written once. (e) **Guard correction v2, second part:** the
  A4 conservation measure reads page words through the frozen trigger tokenizer, which drops
  explicit space characters and fuses words on these PDFs ("CharacteristicsofSubsidyReestimates"),
  so correctly split words counted as excess. v2 reads page words with the space-aware tokenizer.
  v1 (as committed at f54ac57) and v2 are both reported. Tuning unchanged at 96.7 %. Fired
  BUDGET/CBO: 47 fallbacks; conservation worse v1 8 tables / v2 1 table (cbo-60786: its
  "* = between zero and $500,000" footnote is cut by the owner's trim rule); label-number pairs
  changed on 104 tables (v1 17,827 pairs, v2 13,085).
- **05:13-05:19Z.** Centred-column guard (bands whose x-extents overlap > 50 % of the narrower one
  merge); emitter word-break threshold 0.15 x size (DOD's condensed font sets words 0.24-0.27 x
  size apart with no space character: "Operatingforces"). New diagnostic `pairs_audit.py`
  (report only, not a gate): each changed label-number pair on the fired BUDGET/CBO tables checked
  against the printed line. 102 changed tables: 745 TableFormer mispairings dropped, 1,421 right
  pairs gained, 5,303 relabelled (same number, placed right both times, label text differs),
  146 "right pairs lost" (read on DOD t123/t456: TableFormer's line codes "0004"/"0799" parsed as
  values, which the audit's wrapped-label window lets pass; artefacts, dropped correctly), 2 rung-1
  mispairings. Clause 4 read literally (C4) still FAILs on 102 tables.
