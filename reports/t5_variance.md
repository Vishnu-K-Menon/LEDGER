# T5 variance probe (plan.md:41)

- git commit: `b5b37e236d0347847406e3eba6c58e876a752515`
- questions sha256: `05bc4e4a8ea34cc6ff19882b5ea3598be9210d06f72ff4534b7410b790abc4c0`
- chunks.jsonl sha256 (LF): `a42243a0f30e81e02b372f49d39d1d4f7f70f78d4bff137665485e6556cfd8c3`
- controls_accepted.json sha256: `d5feaa3a007af856ef1ac7ec47b82b2651919e00b98832f44ffc8f337973ab73`
- contexts sha256: `746ecc3fcbdc13397032f7c708720b939de4e870d7ea498084f399b88b8365e1`
- output_mode: `structured_output`
- model: `claude-sonnet-5-5`
- thinking / effort: `between_tools / high`
- core requests: `90`
- supplement requests: `3`

## Composition by source and unit

**25 drafts (core)**: cbo_manual 2 (cbo-59853 x1, cbo-61099 x1); eia 2 (eia-pdf-steo_full x2); govinfo_budget 13 (govinfo-BUDGET-2025-CLIMATE x1, govinfo-BUDGET-2026-DOD x7, govinfo-BUDGET-2027-BALANCES x1, govinfo-BUDGET-2027-FCS x1, govinfo-BUDGET-2027-PER x3); govinfo_crpt 4 (govinfo-CRPT-118hrpt468 x4); govinfo_erp 4 (govinfo-ERP-2026-table19 x2, govinfo-ERP-2026-table22 x1, govinfo-ERP-2026-table42 x1)

**supplement (beside the 25)**: cbo_manual 1 (cbo-61720 x1)

Sources not exercised by the 25 drafts: none.
Sources not exercised by drafts plus supplement: none.
Controls: 5 accepted; supplement results are reported separately and enter no count on the 25.

Same prompt, repeat runs at default sampling (D-019). **This does not decide the seed count**: that waits for the first run with an unsupported-claim rate (T9/T11).

## Answer match (D-043 status 2026-10-10)

Numeric items (14) x runs = 42 runs, all in the denominator. Normalisation: whitespace runs to one space; U+2212, U+2013 and ASCII `-` directly before a digit to one minus sign; nothing else. Correct = the gold occurs in the answer text and is not part of a longer number. Abstained and invalid runs (no usable answer: failed validation, stop_reason other than end_turn, errored/expired/canceled/missing) are counted as such and not matched.

- hits 36, misses 0, abstained 6, invalid 0 (sum 42 of 42); hit rate 36/42 = 0.857
- hits that needed the minus mapping: 0
- run 1: hits 12, misses 0, abstained 2, invalid 0 (of 14)
- run 2: hits 12, misses 0, abstained 2, invalid 0 (of 14)
- run 3: hits 12, misses 0, abstained 2, invalid 0 (of 14)
- **Not checked at T5:** whether the matched number is attached to the right period, entity or unit.

### Misses (gold and answer text)

None.

### short_phrase items (11): lexical containment, NOT correctness

Not scored at T5: correctness waits for the D-007 judge (evaluation.md section 3). Reported only: gold phrase present after whitespace collapse and case-folding, with the same longer-number guard.

- contained 31, not contained 2, abstained 0, invalid 0 (sum 33 of 33)

### Other probes

- **digit-level disagreement: 2 of 25 answerable questions** (runs cite different digit strings): q013, q018
  - q013: differing tokens ['02', '1,']
  - q018: differing tokens ['22,']
- **differing tokens that occur in none of the run's five supplied chunk texts: 2** (this line, not the one above, is the D12/D14 reading; scale-word and period swaps between runs are not measured here)
  - q013: ['1,']
  - q018: ['22,']
- abstention consistency: 30/30 = 1.000 questions with the same abstention decision in every run
- citation-set stability: mean pairwise Jaccard 1.000; identical set in every run for 30/30 = 1.000
- answer-token spread: mean max-min output tokens per question 5.2, largest 17; overall output tokens mean 120.4, sd 29.0
