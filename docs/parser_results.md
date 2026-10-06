# Parser results: the detail behind the README

The README carries the short version of the table-parser result. This page holds what a reader checking the work will want: the full scoreboard, what happened to each failing family, the evidence for the likely cause, what is not measured, and the slips on record.

Every number here comes from a tracked file, named at the end of each section. Nothing here is a decision; decisions live in [`decisions.md`](decisions.md) (D-038, D-039, D-040).

## 1. The one-shot test

The second version of the fix was scored once, on tables it had never seen, with the pass rule fixed beforehand. A family passes only if all of these hold:

- at least 95% of cells exactly right
- header-to-column matching no worse than unmodified Docling in the same run
- at most 0.5% of cells going from right to wrong
- at most 1.0% of body cells merged
- every Budget and CBO table byte-identical to before
- number recall unchanged on the eight tables of the first audit

Families are never averaged together.

| | ERP | MER | STEO |
|---|---|---|---|
| Cells scored | 5,017 | 13,731 | 1,277 |
| Tables resampled for the interval | 6 | 36 | 19 |
| Docling alone, exact cells | 30.50% | 53.98% | 89.19% |
| With the fix, exact cells | 100.0% | 95.12% | 94.44% |
| With the fix, stricter count | 100.0% | 94.95% | 94.44% |
| 95% interval (tables resampled) | [100.0, 100.0], reported as unreliable | [90.73, 98.24] on the stricter count | [82.24, 100.0] |
| Header matching, before → after | 90.79% → 97.37% | 84.33% → 90.88% | 95.40% → 97.70% |
| Cells right before, wrong after | 0 | 15 (0.11%) | 0 |
| Merged body cells after the fix | 0.00% | 1.26% | 0.56% |
| Verdict | **Pass** | **Fail** | **Fail** |

The stricter count applies to MER only. It adds 25 cells whose answer-key value is not on the printed row and counts each as a miss, so its denominator is 13,756.

MER by section, exact cells: section 2 98.33%, section 5 100.0%, section 6 85.00%, section 9 99.94%, section 10 91.68%, section 12 98.28%.

Sources: [`reports/a1_diag/rung1b/REPORT.md`](../reports/a1_diag/rung1b/REPORT.md), [`reports/a1_diag/rung1b/evaluation/evaluation.json`](../reports/a1_diag/rung1b/evaluation/evaluation.json).

## 2. What happened to each failing family

### MER (EIA Monthly Energy Review): removed from version 1

MER missed the 95% mark by 8 cells on the stricter count and also failed the merged-cell limit. The decision log attributes the misses to three tables where the fix fell back to Docling's output for reasons that never came up during development (tables 6.2, 10.4b and 10.4c).

The plan written before the test said a failing family would be loaded from the publisher's spreadsheets instead. That was not done, for three reasons on record:

- The export carries no revision flags and stores values as 6-decimal floats, so it cannot reproduce numbers exactly as printed.
- Scoring a spreadsheet ingest against an answer key built from the same spreadsheets would pass by construction.
- Its cost exceeded the remaining budget.

Removing MER is therefore logged as a **deviation from the pre-registered plan**, not as compliance with it. It is not a gate override: MER's parse is never used, and its failure is reported in the same table as the pass. The consequence is that version 1 excludes the densest table family, which may understate how hard the task is.

The planned route back is a spreadsheet ingest checked against the printed page, scored once on a later edition, since every September-edition MER section has now been seen.

### STEO (EIA Short-Term Energy Outlook): kept, with one known-bad table

All 71 STEO misses are in table 10a, which scored 27.55%. The other 18 tables scored 100%. Table 10a had been excluded from debugging effort before the test and kept in the score.

The test ran on the **August 2026** edition, scored against the answer key frozen from September's data. Rows revised between the two editions drop out by rule. The corpus holds the **September 2026** edition.

A rule fixed before any test question exists covers the weak tables: a table whose parse fell back to Docling's output, or that scored below 95%, can be retrieved but is never used to write a test question or a label. The rule works by criterion, never by table name.

Sources: [`decisions.md`](decisions.md) (D-039 status lines of 2026-10-01; D-040), [`reports/a1_diag/rung1b/REPORT.md`](../reports/a1_diag/rung1b/REPORT.md).

## 3. Evidence for the likely cause

Docling's table model, TableFormer, resizes each table image to 448×448 pixels. On dense pages set in small type with no space between lines, that leaves about 6 pixels per text line, and neighbouring rows merge. The decision log records this mechanism as **consistent with the evidence, not proven**.

What supports it:

- **The half-page test.** Parsing a failing page half at a time, so each row gets twice the pixels:

  | Page | Exact cells, whole page | Exact cells, half page | Merged cells, whole → half |
  |---|---|---|---|
  | MER section 3, page 19 | 42.0% | 88.5% | 197 → 6 |
  | MER section 4, page 5 | 48.4% | 99.4% | 163 → 1 |
  | ERP table 4, page 2 | 49.0% | 84.6% | 179 → 37 |

- **The merges are vertical.** Of 464 merged cells on the ERP error rows, 415 join the same column across consecutive years, 20 are horizontal and 29 are other.
- **The model's authors name the limit** (arXiv 2203.01017, section 5.4).

Two alternatives were measured on the first audit and ruled out: Docling's fast mode scored 57.0% and TableFormer V2 scored 4.1%.

Source: [`decisions.md`](decisions.md) (D-038, "Measured" and "Step 0").

## 4. What is not measured

- **Budget and CBO tables have no answer key.** The fix runs only on EIA and ERP sources. All 704 Budget and CBO tables are pinned by SHA-256 hash, so their parsed output cannot change unnoticed. Their parse quality is unmeasured.
- **The Annual Energy Outlook has no answer key.**
- **Scope.** The result is "at least 95% on this family of layouts", not a claim about PDFs in general. The fix works because these PDFs are born-digital and carry their text inside the file.

Sources: [`decisions.md`](decisions.md) (D-039, D-040), [`configs/base.yaml`](../configs/base.yaml) (`parser.row_fix.sources`).

## 5. Two slips on record

1. **A planning step read the answer key's cell counts before the test.** While the test was being planned, an exploration step opened the files that list how many answer-key cells each fresh table has. No parse output and no score existed at that point.
2. **The rule that decides which tables get rebuilt changed during the build.** The rule was fixed beforehand; during the build it was narrowed so that a column-count mismatch alone no longer triggers a rebuild. The builder disclosed the change. A check afterwards, done by reading the per-table results and not by a script, found it could not have changed any verdict. The change was accepted and recorded with its label.

Source: [`reports/a1_diag/rung1b/REPORT.md`](../reports/a1_diag/rung1b/REPORT.md) ("Choices made unattended", "Anything that looked wrong"); [`decisions.md`](decisions.md) (D-039 status lines of 2026-10-01).

## 6. The first attempt

The first version of the fix failed its test:

| | MER | ERP | STEO |
|---|---|---|---|
| Docling alone, exact cells | 50.1% | 55.1% | 86.5% |
| First attempt, exact cells | 88.7% | 92.5% | 95.8% |

STEO cleared 95% on exact cells, but its header matching fell from 94.7% to 78.6%. Merged cells were 1.7% (EIA) and 2.3% (ERP) against the 1.0% limit. Building stopped 52 minutes into a 4-hour allowance.

The 77 tables with an answer key (75 test, 2 tuning) had now been seen, so they were retired: used for development only from then on, with any later number on them treated as after the fact.

Source: [`reports/a1_diag/rung1/REPORT.md`](../reports/a1_diag/rung1/REPORT.md); [`decisions.md`](decisions.md) (D-039).

## 7. Corpus detail

| Stage | PDF files | Pages | Chunks | Table chunks |
|---|---|---|---|---|
| Pilot, with MER | 19 | 659 | 11,621 | 59.2% |
| Pilot, MER removed and re-chunked | 13 | 527 | 6,358 | 49.0% |
| Full corpus, 6 October 2026 | 38 | 1,041 | 9,678 | 43.4% |

The pilot parse took 2.25 hours on a laptop CPU.

The design range for table chunks is 50–70%. The full corpus is below it. The decision log treats the range as design intent, not a pass mark: the share is reported, nothing was re-chunked to move it, and test questions will be drawn by stratified sampling.

Full corpus by source:

| Source | Files | Pages | Chunks | Table chunks |
|---|---|---|---|---|
| CBO cost estimates | 15 | 41 | 521 | 25.0% |
| EIA (STEO, Annual Energy Outlook) | 2 | 89 | 956 | 47.6% |
| Budget volumes | 8 | 829 | 6,156 | 51.1% |
| Congressional committee report | 1 | 65 | 1,511 | 0.0% |
| ERP table files | 12 | 17 | 534 | 87.5% |
| **Total** | 38 | 1,041 | 9,678 | 43.4% |

Notes:

- **The committee report** was drawn as a parser test and stays in the index. It has no tables and supplies 1,511 chunks.
- **CBO cost estimates are downloaded by hand**, because cbo.gov blocks scripts. Each file's source page and SHA-256 hash are in the manifest.
- **Left out:** the six MER sections; the Budget Historical Tables volume, which is published without a PDF; and the Mid-Session Review, excluded at fetch because 25% of its pages are images.

Sources: [`reports/a9_full.md`](../reports/a9_full.md), [`reports/rechunk_20261002.md`](../reports/rechunk_20261002.md), [`plan.md`](plan.md), [`data/manifest.jsonl`](../data/manifest.jsonl).
