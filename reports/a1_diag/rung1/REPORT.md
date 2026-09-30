# Rung 1 of D-038 — morning report (2026-09-30, unattended run)

**The owner rules on PASS/FAIL. No decision is logged; the only `docs/decisions.md` write is the A6 status line.**

## Verdict, line by line

The rung-1 output is `data/parsed_rung1/`. It was scored once, by the unchanged scorers, against the frozen oracle.

| D-038 pass rule | result | line |
|---|---|---|
| Strict ≥ 95 % per family, with header association | MER held-out **88.7 %** (from 50.1) · ERP **92.5 %** (from 55.1) · STEO **95.8 %** (from 86.5), but STEO header association **78.6 %** (from 94.7) | **FAIL** (MER, ERP below 95. STEO passes on strict but its header association regressed; no threshold was set, and I read a regression as not "asserted": choice C11) |
| Flip matrix ≤ 0.5 % per family (value flips) | MER 9 (0.05 %) · ERP 0 (0.00 %) · STEO 36 (0.28 %) | **PASS** |
| Census EIA/ERP ≤ 1.0 % merged body cells | EIA **1.72 %** (from 12.41) · ERP **2.34 %** (from 19.18) | **FAIL** |
| BUDGET/CBO census unchanged | BUDGET 0.97 → 0.55 % · CBO 0.23 → 0.00 % | **FAIL** (read literally: changed, both downward, i.e. fewer merged cells) |
| BUDGET/CBO word conservation unchanged (C5) | v1 (as committed at A4): 11 tables worse · v2 (corrected): 1 table worse (cbo-60786, whose "* = between zero and $500,000" footnote the trim rule cuts) | **FAIL** under both |

| A1-regression guard (ruling a; weaker than a cell check on BUDGET/CBO) | result | clause |
|---|---|---|
| (1) Number recall unchanged, and ceiling not below baseline, on each of the eight A1 PDF tables | Ceiling reaches 100 % on all eight (sec3 45.9 → 100, sec4 51.1 → 100, sec11 74.4 → 100, STEO t10 82.0 → 100, DOD t446 88.8 → 100). Recall is unchanged on six tables, but sec3 falls 100 → **99.55 %** (4 numbers) and sec11 100 → **99.70 %** (2) | **FAIL** (see finding F1) |
| (2) ERP through the oracle | 55.1 → **92.5 %** strict, 0 value flips. A1's own `erp_compare.py` (index pairing): 55.7 → 77.6 %; A1 PDF ceiling 73.6 → 100 %; combined 67.4 → 92.5 % | **PASS** (C6) |
| (3) Every BUDGET/CBO table where the trigger did not fire keeps an identical table dict | 553 tables (BUDGET 550, CBO 3): **0 changed** | **PASS** |
| (4) Any changed label–number pair on a fired BUDGET/CBO table = FAIL | 105 tables (v1) / 104 (v2) changed | **FAIL**, table list in `evaluation.json` → `bc.v1/v2.clause4_changed_tables` |
| (5) BUDGET/CBO fire count | BUDGET 148 / 698 fired (103 rebuilt, 45 fell back) · CBO 3 / 6 (2 rebuilt, 1 fell back) | reported |

**Overall: FAIL.** The failing lines are:
- MER and ERP strict are below 95 %.
- STEO header association regressed.
- EIA/ERP census is above 1.0 %.
- BUDGET/CBO census and conservation changed.
- Clause 1 fails on two recall dips.
- Clause 4 fails.

Against that, measured on the same frozen oracle:
- MER strict went from 50.1 to 88.7 %, ERP from 55.1 to 92.5 %, STEO from 86.5 to 95.8 %.
- Merged body cells fell from 12.4 to 1.7 % (EIA) and from 19.2 to 2.3 % (ERP).
- Value flips were ≤ 0.28 % in every family.

**Clause 4 in context** (diagnostic only, never a gate): `pairs_audit.py` on the final output checks each changed pair against the printed line. Of the 104 changed tables (v2):
- 744 TableFormer mispairings were dropped;
- 1,421 right pairs TableFormer lacked were gained;
- 5,338 pairs were relabelled (same number, placed correctly both times, label text differs);
- 147 "right pairs lost" (read on DOD t123/t456: TableFormer's line codes such as "0004"/"0799", parsed as values; artefacts);
- **1 rung-1 mispairing**.

The literal clause counts every change, corrections included, as its ruling says.

## Findings the owner needs (defects found at evaluation; building had stopped, so none is applied)
- **F1 — revision flags are fused without a space.** `emit.merge_flags` writes "R1,358" where the page prints the flag and number apart. The owner's `pdf_recall.py` `nums()` reads "R 1,358" but not "R1,358". This is all of the sec3 (4) and sec11 (2) recall loss behind clause 1, verified on sec3 (a tuning table). The fix is one line (join with a space). `canon()` rejects both forms, so strict is unaffected.
- **F2 — STEO header association regressed** from 94.7 to 78.6 %. Every rebuilt STEO table scores 9/15 or 6/15. 9/15 is exactly six failing columns out of 15 (12 quarters + 3 years). The likely mechanism: a one-word spanning header ("2025"), centred over its four quarter columns, physically overlaps only the middle two bands. The page-word check then displaces TableFormer's correctly spanned cell, so the Q1 and Q4 columns lose the year. I inferred this from the per-table pattern and did not verify it on held-out pages (hard rule). The candidate fix: take a spanning token's extent from the gap to its neighbours on the header line, or keep TableFormer's cell when its text equals the page phrase.
- **F3 — the frozen trigger drops explicit space characters.** BUDGET PDFs encode spaces as zero-gap characters, and `trigger.tokens_in` discards them, so adjacent tokens fuse. This probably affects the BUDGET fire count. The trigger stays frozen as ordered; the emitter has its own tokenizer.
- **F4 — the guard definitions committed at A4 had two defects**, found during Part B on BUDGET (not held-out):
  - leader glyphs that decode as U+FFFD runs (with Docling's U+0008) were not treated as leaders;
  - page words were read through the trigger tokenizer (F3), which fuses words.

  The v2 correction fixes both, is applied identically to baseline and rung 1, and is reported beside v1. Separately, v1 reproduces the committed baseline exactly (`bc_baseline_v1_reproduced: true`, sha256 e2a8e12d…).
- **F5 — the tuning residue is not the emitter's.** On tuning (96.8 %) the misses are 12 R/E-flagged cells, where `canon()` rejects the flag the owner's rule keeps with the number. The remaining ~37 are revision-window cells: the page prints a different number from the admitted export value, because A6 admits a value printed anywhere in the bbox. That is an oracle limit.
- **F6 — ten held-out MER tables stay far below 95 % because the rebuild never ran or ran without success:**
  - 3 fell back: 1.2, 3.1, 4.1;
  - 5 were not fired: 1.10, 3.3e, 3.31, 11.2, 11.5;
  - 2 rebuilt tables stayed low: 3.3c at 20.6 % strict / 88.7 % lenient (a column mapping, not read further under the hard rule), and 11.6 at 84.7 % strict / 99.4 % lenient.

  STEO 10a stays at 7.6 % (a fallback; excluded from debugging effort as ruled, kept in the score).

## What ran

- **B1 path: emitter.** The naive emitter on sec4 p5 scored 791 / 794 = 99.6 % strict (≥ 80 %; owner fill i).
- **A2:** 79 header misses (MER held-out 72, MER tuning 4, ERP 3). On MER held-out: dropped column 28 %, garbled/fused 40 %, body-caused 32 %. That selects **TableFormer headers**, with the page-word check.
- **A3:** STEO header-association baseline 354 / 374 = 94.7 %.
- **A4:** the baselines reproduce exactly through the per-cell scorer detail (50.1 / 55.1 / 86.5 / 45.3).
- **A5:** `.gitattributes` moot (the `data/oracle` index is already LF); `paddleocr_vl` retired in `configs/base.yaml`, `ledger/config.py`, `ledger/ingest/audit_tables.py`.
- **A6:** the D-038 status line (484979b).
- **Trigger** (frozen af06045; fired list sha256 c4373792…): at B5, re-run fresh per unit, it reproduced A1's list on all 19 units.
- **Emission** (`run_rung1.py`, emitter frozen at fb08884, `emit.py` sha256 b1ec56d5…), held-out families:
  - MER held-out: 36 rebuilt, 3 fallback, 6 not fired;
  - ERP: 3 rebuilt, 1 not fired;
  - STEO: 11 rebuilt, 3 fallback, 12 not fired;
  - tuning: 2 rebuilt.
- **Fallback reasons, all families:** band assertion 44 (mostly BUDGET continuation pages, whose column header is printed on the previous page), safety 7, no dense band 1, no body lines 1.

## Choices made unattended (conservative option taken; each with its reason)
- **C1 — trigger read like-for-like.** Numeric lines are compared with TableFormer rows that hold a numeric body cell; bands with columns ≥ 1 that hold one. Comparing raw rows would count header and section rows. The trigger was frozen before the dry-run.
- **C2 — rung 1 built under `scripts/a1_diag/rung1/`, not `ledger/ingest/rows.py`.** The character source is pdfplumber, which is not a project dependency, and `pyproject.toml` may not change. The production port, the `parser.row_fix` config key and D-038's unit tests wait for your verdict.
- **C3 — cell text copies the page.** Flags stay with their number (but see F1), U+FFFD decimals become ".", and leader dots are stripped.
- **C4 — clause 4 read literally**, on the (row-stub words, number) multiset.
- **C5 — word conservation defined as** conserved share ≥ baseline and excess ≤ baseline. F4 corrected it (v2); v1 is also reported.
- **C6 — ERP guard** = ERP strict ≥ baseline and ERP value flips ≤ 0.5 %.
- **C7 — the full corpus was emitted once, at B5.** During Part B only the tuning tables and non-held-out BUDGET/CBO tables were looked at.
- **C8 — "printed header-column count"** = bands with a header-region token over them (±2 pt).
- **C9 — scorers got an optional per-cell `detail` list** for the flip matrix. No count or denominator changed (baseline reproduced exactly).
- **C10 — building stopped at 05:39Z**, 52 min into the 4 h box. Tuning was at 96.8 %, every remaining tuning miss was F5, and further building would have needed a signal from held-out tables (forbidden) or tuning to BUDGET quirks that no oracle checks. So I stopped early, within the box, rather than build without a correctness signal. D-038 expected the 4 h to be used in full; this departs from that expectation, not from the hard stop.
- **C11 — a STEO header-association regression is read as failing "with header association"** (no threshold was set).
- **During the build:**
  - three safety fallbacks keep TableFormer's table: prose > 20 % of candidate lines, a text column, emitted cells with ≥ 2 numbers > 2 %;
  - the emitter's own tokenizer (the trigger stays frozen);
  - guard v2 (F4);
  - the robustness test on the 553 non-fired BUDGET/CBO tables (not held-out; they stay identical in the output) took rung-1 mispairings there from 136 to 0.

## Skipped or deferred
- **Skipped under the dissent clause:** nothing.
- **Deferred with reason:** the production port and D-038's unit tests (C2).
- **A5 `.gitattributes`:** not needed (moot).
- **"79 MER header misses":** these are 79 misses across MER held-out, MER tuning and ERP. All 79 were classified; the rule was applied to the MER held-out share.

## Hours (from `clock.txt` and commit times)
- **Part A:** 00:33 → 00:47 local (04:33 → 04:47Z) ≈ 0.25 h, outside the timebox.
- **Part B build:** 04:47:18 → 05:39:00Z = 52 min of 240 (C10).
- **B5 emission + one held-out evaluation:** 05:39 → 05:53Z ≈ 0.25 h. Scoring may run past the build; building may not.
- **Part C:** ≈ 0.25 h.
- **Rung 1's 4 h timebox:** 0.87 h used.

## Structural caveat
The emitter never emits spans in the body, so the census cannot see the emitter's own row errors. For rebuilt tables the census drop is structural. The flip matrix and strict carry the load there (strict ≥ 95 % not met on MER and ERP).

## Records
- **Build log:** `build_log.md`.
- **Numbers:** `evaluation.json` (per family and per table, flips, census, owner scripts, BUDGET/CBO guards v1 and v2).
- **Diagnostic:** `pairs_audit.json`.
- **Emission counts:** `emit_summary.json`.
- **Pre-work:** `A1_trigger_dryrun.md`, `A2_header_misses.md`, `A3_steo_header_baseline.md`, `A4_guard_baselines.md`.

---

## Per family and per table (generated by `evaluate.py`; baselines beside; never pooled)

### MER held-out (per-cell admission (A6), later edition)

| | strict | lenient | header assoc. | row not found | column not found |
|---|---|---|---|---|---|
| baseline | 50.14 % (9149/18246) | 75.17 % | 85.15 % | 47 | 839 |
| rung 1 | **88.72 %** (16187/18246) | 92.96 % | 89.48 % | 16 | 49 |

Flips (correct at baseline -> wrong after): value 9 (0.05 % of 18246), character-level (flag / fused negative) 31. Cells lost to repeated-label pairing: n/a (period keys).

| table | page | unit | trigger | cells | strict base | **strict** | lenient | header (base) | row NF | col NF |
|---|---|---|---|---|---|---|---|---|---|---|
| 1.1 | 3 | `eia-pdf-sec1` | rebuilt | 483 | 51.76 | **98.76** | 98.76 | 12/12 (10/12) | 0 | 0 |
| 1.2 | 5 | `eia-pdf-sec1` | fallback | 569 | 47.8 | **47.8** | 76.1 | 10/13 (10/13) | 0 | 49 |
| 1.3 | 7 | `eia-pdf-sec1` | rebuilt | 603 | 42.79 | **99.5** | 99.5 | 12/12 (10/12) | 0 | 0 |
| 1.4a | 9 | `eia-pdf-sec1` | rebuilt | 444 | 57.88 | **99.1** | 99.1 | 9/9 (7/9) | 0 | 0 |
| 1.4b | 11 | `eia-pdf-sec1` | rebuilt | 410 | 60.73 | **97.56** | 97.56 | 9/9 (8/9) | 0 | 0 |
| 1.4c | 13 | `eia-pdf-sec1` | rebuilt | 414 | 54.83 | **97.58** | 97.58 | 9/9 (8/9) | 0 | 0 |
| 1.5 | 15 | `eia-pdf-sec1` | rebuilt | 519 | 74.76 | **100.0** | 100.0 | 10/10 (10/10) | 0 | 0 |
| 1.6 | 17 | `eia-pdf-sec1` | rebuilt | 192 | 53.12 | **97.4** | 97.4 | 7/7 (7/7) | 0 | 0 |
| 1.7 | 19 | `eia-pdf-sec1` | rebuilt | 497 | 61.57 | **100.0** | 100.0 | 9/10 (9/10) | 0 | 0 |
| 1.8 | 21 | `eia-pdf-sec1` | rebuilt | 587 | 64.74 | **99.15** | 99.15 | 8/12 (12/12) | 0 | 0 |
| 1.9 | 22 | `eia-pdf-sec1` | not fired | 30 | 100.0 | **100.0** | 100.0 | 5/5 (5/5) | 0 | 0 |
| 1.10 | 23 | `eia-pdf-sec1` | not fired | 64 | 85.94 | **85.94** | 95.31 | 6/6 (6/6) | 0 | 0 |
| 1.11 | 24 | `eia-pdf-sec1` | rebuilt | 488 | 48.77 | **99.18** | 99.18 | 10/10 (8/10) | 0 | 0 |
| 1.12 | 25 | `eia-pdf-sec1` | rebuilt | 518 | 48.26 | **98.46** | 98.46 | 10/10 (8/10) | 0 | 0 |
| 1.13a | 26 | `eia-pdf-sec1` | rebuilt | 450 | 45.11 | **92.22** | 92.22 | 6/10 (3/10) | 0 | 0 |
| 1.13b | 27 | `eia-pdf-sec1` | rebuilt | 554 | 46.57 | **93.32** | 93.32 | 11/12 (9/12) | 0 | 0 |
| 11.1 | 3 | `eia-pdf-sec11` | rebuilt | 644 | 65.06 | **96.43** | 96.58 | 12/14 (12/14) | 0 | 0 |
| 11.2 | 5 | `eia-pdf-sec11` | not fired | 339 | 74.34 | **74.34** | 84.37 | 6/8 (6/8) | 6 | 0 |
| 11.3 | 6 | `eia-pdf-sec11` | rebuilt | 431 | 77.73 | **98.38** | 98.38 | 6/11 (9/11) | 0 | 0 |
| 11.4 | 7 | `eia-pdf-sec11` | rebuilt | 592 | 59.97 | **95.61** | 95.78 | 11/14 (12/14) | 0 | 0 |
| 11.5 | 8 | `eia-pdf-sec11` | not fired | 436 | 55.05 | **55.05** | 76.61 | 9/11 (9/11) | 0 | 0 |
| 11.6 | 9 | `eia-pdf-sec11` | rebuilt | 347 | 58.21 | **84.73** | 99.42 | 7/8 (8/8) | 0 | 0 |
| 11.7 | 10 | `eia-pdf-sec11` | rebuilt | 564 | 57.98 | **99.47** | 99.47 | 8/11 (5/11) | 0 | 0 |
| 3.1 | 3 | `eia-pdf-sec3` | fallback | 172 | 23.84 | **23.84** | 65.7 | 12/13 (12/13) | 0 | 0 |
| 3.2 | 5 | `eia-pdf-sec3` | rebuilt | 328 | 22.26 | **92.07** | 92.07 | 12/14 (11/14) | 0 | 0 |
| 3.3a | 7 | `eia-pdf-sec3` | rebuilt | 263 | 21.29 | **92.78** | 92.78 | 12/12 (12/12) | 0 | 0 |
| 3.3b | 9 | `eia-pdf-sec3` | rebuilt | 279 | 26.16 | **84.23** | 84.59 | 10/11 (11/11) | 0 | 0 |
| 3.3c | 10 | `eia-pdf-sec3` | rebuilt | 238 | 9.66 | **20.59** | 88.66 | 2/9 (2/9) | 0 | 0 |
| 3.3d | 11 | `eia-pdf-sec3` | rebuilt | 254 | 61.42 | **98.82** | 98.82 | 11/11 (11/11) | 0 | 0 |
| 3.3e | 12 | `eia-pdf-sec3` | not fired | 161 | 37.27 | **37.27** | 70.19 | 9/9 (9/9) | 0 | 0 |
| 3.31 | 13 | `eia-pdf-sec3` | not fired | 233 | 51.5 | **51.5** | 68.67 | 12/12 (12/12) | 10 | 0 |
| 3.4 | 15 | `eia-pdf-sec3` | rebuilt | 346 | 31.5 | **91.33** | 91.91 | 13/13 (10/13) | 0 | 0 |
| 3.5 | 17 | `eia-pdf-sec3` | rebuilt | 313 | 25.88 | **87.54** | 87.54 | 13/15 (13/15) | 0 | 0 |
| 3.7a | 21 | `eia-pdf-sec3` | rebuilt | 225 | 24.44 | **82.67** | 83.11 | 11/11 (9/11) | 0 | 0 |
| 3.7b | 22 | `eia-pdf-sec3` | rebuilt | 277 | 26.35 | **83.39** | 83.39 | 10/13 (10/13) | 0 | 0 |
| 3.7c | 23 | `eia-pdf-sec3` | rebuilt | 295 | 37.29 | **92.54** | 92.54 | 13/13 (13/13) | 0 | 0 |
| 3.8a | 26 | `eia-pdf-sec3` | rebuilt | 476 | 39.5 | **92.23** | 92.44 | 11/11 (10/11) | 0 | 0 |
| 3.8b | 27 | `eia-pdf-sec3` | rebuilt | 630 | 45.4 | **92.22** | 92.54 | 11/13 (12/13) | 0 | 0 |
| 3.8c | 28 | `eia-pdf-sec3` | rebuilt | 641 | 50.86 | **97.19** | 97.19 | 13/13 (13/13) | 0 | 0 |
| 4.1 | 3 | `eia-pdf-sec4` | fallback | 538 | 47.58 | **47.58** | 64.87 | 10/11 (10/11) | 0 | 0 |
| 4.2a | 4 | `eia-pdf-sec4` | rebuilt | 751 | 41.41 | **98.67** | 98.67 | 13/14 (11/14) | 0 | 0 |
| 4.3 | 6 | `eia-pdf-sec4` | rebuilt | 519 | 43.16 | **93.64** | 93.64 | 11/11 (10/11) | 0 | 0 |
| 4.4 | 7 | `eia-pdf-sec4` | rebuilt | 427 | 49.18 | **100.0** | 100.0 | 8/8 (7/8) | 0 | 0 |
| 8.1 | 3 | `eia-pdf-sec8` | rebuilt | 274 | 65.33 | **100.0** | 100.0 | 5/5 (5/5) | 0 | 0 |
| 8.2 | 5 | `eia-pdf-sec8` | rebuilt | 431 | 66.36 | **100.0** | 100.0 | 10/10 (9/10) | 0 | 0 |

### ERP (per-cell admission (A6), same edition)

| | strict | lenient | header assoc. | row not found | column not found |
|---|---|---|---|---|---|
| baseline | 55.07 % (1522/2764) | 79.59 % | 93.18 % | 0 | 67 |
| rung 1 | **92.51 %** (2557/2764) | 95.69 % | 97.73 % | 0 | 0 |

Flips (correct at baseline -> wrong after): value 0 (0.0 % of 2764), character-level (flag / fused negative) 0. Cells lost to repeated-label pairing: n/a (period keys).

| table | page | unit | trigger | cells | strict base | **strict** | lenient | header (base) | row NF | col NF |
|---|---|---|---|---|---|---|---|---|---|---|
| table22 sheet0 | 1 | `govinfo-ERP-2026-table22` | not fired | 566 | 63.43 | **63.43** | 78.98 | 10/10 (10/10) | 0 | 0 |
| table22 sheet1 | 2 | `govinfo-ERP-2026-table22` | rebuilt | 590 | 71.19 | **100.0** | 100.0 | 9/10 (10/10) | 0 | 0 |
| table4 sheet0 | 1 | `govinfo-ERP-2026-table4` | rebuilt | 804 | 43.41 | **100.0** | 100.0 | 12/12 (10/12) | 0 | 0 |
| table4 sheet1 | 2 | `govinfo-ERP-2026-table4` | rebuilt | 804 | 49.0 | **100.0** | 100.0 | 12/12 (11/12) | 0 | 0 |

### STEO (whole-row admission, same edition)

| | strict | lenient | header assoc. | row not found | column not found |
|---|---|---|---|---|---|
| baseline | 86.46 % (11280/13046) | 89.26 % | 94.65 % | 742 | 45 |
| rung 1 | **95.76 %** (12493/13046) | 96.08 % | 78.61 % | 268 | 0 |

Flips (correct at baseline -> wrong after): value 36 (0.28 % of 13046), character-level (flag / fused negative) 0. Cells lost to repeated-label pairing: baseline 274, rung 1 93.

| table | page | unit | trigger | cells | strict base | **strict** | lenient | header (base) | row NF | col NF |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 31 | `eia-pdf-steo_full` | rebuilt | 330 | 90.91 | **100.0** | 100.0 | 9/15 (15/15) | 0 | 0 |
| 2 | 32 | `eia-pdf-steo_full` | rebuilt | 396 | 100.0 | **100.0** | 100.0 | 6/15 (14/15) | 0 | 0 |
| 3a | 33 | `eia-pdf-steo_full` | not fired | 465 | 100.0 | **100.0** | 100.0 | 15/15 (15/15) | 0 | 0 |
| 3b | 34 | `eia-pdf-steo_full` | not fired | 412 | 100.0 | **100.0** | 100.0 | 15/15 (15/15) | 0 | 0 |
| 3c | 35 | `eia-pdf-steo_full` | not fired | 332 | 100.0 | **100.0** | 100.0 | 15/15 (15/15) | 0 | 0 |
| 3d | 36 | `eia-pdf-steo_full` | not fired | 357 | 100.0 | **100.0** | 100.0 | 15/15 (15/15) | 0 | 0 |
| 3e | 37 | `eia-pdf-steo_full` | rebuilt | 357 | 100.0 | **89.92** | 89.92 | 9/15 (12/15) | 21 | 0 |
| 4a | 38 | `eia-pdf-steo_full` | rebuilt | 810 | 66.54 | **100.0** | 100.0 | 9/15 (15/15) | 0 | 0 |
| 4b | 39 | `eia-pdf-steo_full` | rebuilt | 645 | 66.05 | **100.0** | 100.0 | 9/15 (15/15) | 0 | 0 |
| 4c | 40 | `eia-pdf-steo_full` | fallback | 210 | 100.0 | **100.0** | 100.0 | 15/15 (15/15) | 0 | 0 |
| 4d | 41 | `eia-pdf-steo_full` | rebuilt | 615 | 90.41 | **100.0** | 100.0 | 9/15 (15/15) | 0 | 0 |
| 5a | 42 | `eia-pdf-steo_full` | rebuilt | 495 | 100.0 | **100.0** | 100.0 | 9/15 (15/15) | 0 | 0 |
| 5b | 43 | `eia-pdf-steo_full` | not fired | 465 | 100.0 | **100.0** | 100.0 | 15/15 (15/15) | 0 | 0 |
| 6 | 44 | `eia-pdf-steo_full` | not fired | 465 | 100.0 | **100.0** | 100.0 | 15/15 (15/15) | 0 | 0 |
| 7a | 45 | `eia-pdf-steo_full` | rebuilt | 600 | 88.5 | **100.0** | 100.0 | 6/15 (15/15) | 0 | 0 |
| 7b | 46 | `eia-pdf-steo_full` | not fired | 660 | 89.55 | **89.55** | 91.82 | 15/15 (15/15) | 30 | 0 |
| 7c | 47 | `eia-pdf-steo_full` | not fired | 600 | 100.0 | **100.0** | 100.0 | 15/15 (15/15) | 0 | 0 |
| 7d | 48 | `eia-pdf-steo_full` | rebuilt | 825 | 58.18 | **100.0** | 100.0 | 9/15 (14/15) | 0 | 0 |
| 7d | 49 | `eia-pdf-steo_full` | rebuilt | 810 | 80.74 | **100.0** | 100.0 | 6/15 (8/15) | 0 | 0 |
| 7e | 50 | `eia-pdf-steo_full` | not fired | 315 | 100.0 | **100.0** | 100.0 | 15/15 (15/15) | 0 | 0 |
| 8 | 51 | `eia-pdf-steo_full` | not fired | 510 | 100.0 | **100.0** | 100.0 | 15/15 (15/15) | 0 | 0 |
| 9a | 52 | `eia-pdf-steo_full` | fallback | 495 | 94.55 | **94.55** | 96.77 | 15/15 (15/15) | 0 | 0 |
| 9b | 53 | `eia-pdf-steo_full` | rebuilt | 675 | 85.19 | **100.0** | 100.0 | 9/15 (12/15) | 0 | 0 |
| 9c | 54 | `eia-pdf-steo_full` | not fired | 600 | 100.0 | **100.0** | 100.0 | 15/15 (15/15) | 0 | 0 |
| 10a | 55 | `eia-pdf-steo_full` | fallback | 448 | 7.59 | **7.59** | 11.16 | 2/7 (2/7) | 210 | 0 |
| 10b | 56 | `eia-pdf-steo_full` | not fired | 154 | 95.45 | **95.45** | 95.45 | 7/7 (7/7) | 7 | 0 |

### tuning (per-cell admission (A6), later edition; tuning set, never held-out)

| | strict | lenient | header assoc. | row not found | column not found |
|---|---|---|---|---|---|
| baseline | 45.35 % (687/1515) | 72.54 % | 86.21 % | 0 | 57 |
| rung 1 | **96.77 %** (1466/1515) | 96.83 % | 96.55 % | 0 | 0 |

Flips (correct at baseline -> wrong after): value 0 (0.0 % of 1515), character-level (flag / fused negative) 0. Cells lost to repeated-label pairing: n/a (period keys).

| table | page | unit | trigger | cells | strict base | **strict** | lenient | header (base) | row NF | col NF |
|---|---|---|---|---|---|---|---|---|---|---|
| 3.6 | 19 | `eia-pdf-sec3` | rebuilt | 721 | 42.02 | **93.62** | 93.76 | 14/15 (11/15) | 0 | 0 |
| 4.2b | 5 | `eia-pdf-sec4` | rebuilt | 794 | 48.36 | **99.62** | 99.62 | 14/14 (14/14) | 0 | 0 |

