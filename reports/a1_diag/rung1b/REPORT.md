# Rung 1b (D-039) — report

Protocol: D-039 status 2026-10-01 (owner; rung-1b evaluation protocol), `docs/decisions.md:530`.
Evaluator output (written once, atomically): `reports/a1_diag/rung1b/evaluation/evaluation.{json,md}`.

## Verdict (D-039 reading; the D-038 reading beside it, never deciding)

| family | strict (gate) | header assoc. vs in-run baseline | flips | census (rebuilt / not) | BUDGET/CBO manifest | clause-1 recall | **D-039** | D-038 reading |
|---|---|---|---|---|---|---|---|---|
| MER | conservative **94.95 %** (13,061 / 13,756) — FAIL · plain 95.12 % (13,061 / 13,731) | 84.33 → 90.88 — PASS | 15 = 0.11 % — PASS | **1.26 %** (0.12 / 11.66) — FAIL | identical — PASS | unchanged — PASS | **FAIL** | FAIL (plain strict passes; census fails) |
| ERP | **100.0 %** (5,017 / 5,017) — PASS | 90.79 → 97.37 — PASS | 0 — PASS | 0.00 % (0.00 / —) — PASS | identical — PASS | unchanged — PASS | **PASS** | PASS |
| STEO | **94.44 %** (1,206 / 1,277) — FAIL | 95.40 → 97.70 — PASS | 0 — PASS | 0.56 % (0.00 / 1.26) — PASS | identical — PASS | unchanged — PASS | **FAIL** | FAIL |

Baseline (unmodified Docling parse of the fresh set, scored first in the same run) strict: MER 53.98 % plain
(conservative 53.88 %), ERP 30.50 %, STEO 89.19 %. Table-bootstrap 95 % percentile CI (B = 10,000,
seed 20260930, tables resampled with replacement, cells pooled): MER conservative [90.73, 98.24]
(36 tables), plain [90.95, 98.35]; ERP [100.0, 100.0] over 6 granules — **reported as unreliable,
not interpreted**; STEO [82.24, 100.0] (19 tables). The gate is the point estimate.

MER strict per section (plain / conservative): sec2 98.33 / 98.23 · sec5 100.0 / 100.0 · sec6
85.00 / 84.87 · sec9 99.94 / 99.87 · sec10 91.68 / 91.38 · sec12 98.28 / 98.12.

**Pre-registered failure branch (D-039, decisions.md "Failure branch"), stated, not started:** MER
below 95 % → rung 2 for MER (D-038 item 4); ERP passes; STEO below 95 % → "STEO stays on
rung-1/1b output" (D-039 gives STEO no rung-2 path). No rung 2, port or re-chunk was started.

## Clock

RUNG-1B START 2026-10-01T22:25:12Z

RUNG-1B STOP 2026-10-01T23:35:23Z — reason: the closed fix list is exhausted (every item built and
measured on the burned tables; residuals are outside the list or have no parameter-free fix — see
"Part B"). Hours 1.17 of 3 (22:25:12Z → 23:35:23Z). Emitter frozen: `emitter_freeze.json`
(emit.py, run_rung1.py, trigger.py).

Not charged to the box: Part A (Step 0 → START) and Part C (emitter run 23:38Z, evaluation
23:41:39Z → 23:42:36Z).

## Part A (before the clock)

- **Step 0** — the owner's D-039 and D-035 status lines inserted verbatim (D-039 after its last status
  line, decisions.md:530; D-035 after its Validation line); plan.md rung-1b line gains "dry-run +
  one-evaluation rule (status 2026-10-01)"; cut 3 and the D-035 cut-list line ticked — c4a119f.
- **A1** — `run_rung1.py` gains `--manifest --raw --parsed --out` (pilot defaults), `--fired
  pinned|live`, `--covered pilot|none`; `emit.py` / `trigger.py` gain a path-only `RAW` constant.
  Default-path run (`--out` scratch) on the 10 pilot EIA/ERP units: **20/20 files byte-identical** to
  `data/parsed_rung1/` (`a1_refactor_identity.json`); `oracle.py`, `f5_sizing.py`, `fresh_oracle.py`,
  `freeze.json` byte-identical before/after; `freeze.py --check` OK — 3b38f12.
- **A2** — `scripts/a1_diag/rung1b/evaluate_1b.py` (assert_frozen first; eval_freeze check; baseline
  first; one atomic write; type + file:line on a crash) — 10ce944.
- **A3** dry-run, burned tables only (`dryrun.log`, outputs in `dryrun/`), **all checks pass** — 10ce944:

  | check | result |
  |---|---|
  | (a) identity (`data/parsed` both sides) | flips 0 / character-level 0; header 85.15 = 85.15, 93.18 = 93.18, 94.65 = 94.65 |
  | (b) step 0 (±0.1 pp), oracle as at c6c8724 (cells.jsonl sha256 d7c13b52…), split 45 / 4 / 26 + tuning 2 | strict 50.14 / 55.07 / 86.46 · header 85.15 / 93.18 / 94.65 |
  | (c) rung 1 output (±0.1 pp vs 158029a) | strict 88.72 / 92.51 / 95.76 · header 89.48 / 97.73 / 78.61 · value flips 9 / 0 / 36 (0.05 / 0.00 / 0.28 %) · census EIA 1.72 / ERP 2.34 · clause-1 recall sec3 99.55 / sec11 99.70 · bootstrap deterministic (second run byte-identical) |
  | (d) altered freeze.json | refused; real file untouched and passing |

  Extra (not required): the evaluator's FRESH code path rehearsed on burned data rewritten into the
  fresh file format (`rehearse_1b.py`, `dryrun/rehearsal.log`) reproduces the burned path exactly.
  It caught one evaluator defect before the freeze: the bootstrap depended on table-list order
  (fixed: tables sorted by key) — all A3 runs were redone on the final evaluator.
- **eval_freeze.json** — sha256 of all 48 files of `data/parsed_fresh/`, the 12 evaluator modules
  (incl. `trigger.py` via `guards.py`, so the trigger rule could not change unnoticed), seed
  20260930, B 10,000, 95 % percentile — committed with the START line, ff3b1b0.
- **A4** — the D-039 status line contains no "___".

## Part B — build (burned tables only; `board.py`, live trigger path; `build_log.md`)

Every checkpoint ran `run_rung1.py --fired live --covered none` (the Part-C path, owner requirement)
into `data/parsed_rung1b/` and scored the 77 burned tables (MER 47 = held-out 45 + tuning 2; ERP 4;
STEO 26) against rung 1's output. At every checkpoint: BUDGET/CBO pins identical (704), no burned
table's strict fell vs rung 1.

| fix-list item | change | burned before → after |
|---|---|---|
| F1 (32e3560) | a revision flag fused to its number is emitted with the page's space ("R 1,358"), for flags fused by `merge_flags` and for flags the tokenizer fuses (raised "E" beside the number); body / stub / section cells, never header text | clause-1 recall sec3 99.55 → 100, sec11 99.70 → 100 (all 8 unchanged); strict unchanged |
| F2 spanning-header extent (71fea77, cf29435) | a header phrase takes the bands whose centres lie in its gap tile (midpoints to its neighbours on the line) when it is centred on them; a lone group head takes TableFormer's span for the same words when centred on it; otherwise physical overlap. Used by the band check and the page cells | header STEO 78.61 → 97.59, MER 89.88 → 91.83, ERP 97.73 → 95.45 (step-0 baselines 94.65 / ~85 / 93.18) |
| trigger false negatives (80428a3) | rung-1b live rule (in `run_rung1.py`; `trigger.py` untouched): fire iff TableFormer holds a merged body cell OR numeric-line count ≠ TableFormer rows; a band-count mismatch alone no longer fires | newly fired and rebuilt: 1.10 85.9 → 90.6, 3.3e 37.3 → 91.3, 3.31 51.5 → 88.4, 11.2 74.3 → 99.4, 11.5 55.1 → 95.9, ERP table22 p1 63.4 → 100, STEO 7b 89.6 → 100; no longer fired: STEO 2, 3e (89.92 → 100.0), 4c, 5a (all 100 at baseline) |
| fallback causes: safety (32f496d, 48b0d00) | split numbers ("3 .349", "11 ,459") rejoined in cell text; numbers inside a closed parenthetical ("(billion chained 2017 dollars - SAAR)") are label text | MER fallbacks 1.2 / 3.1 / 4.1 → rebuilt; STEO 9a → rebuilt; burned strict MER 91.55 → 94.74, STEO 96.57 → 96.77 |
| fallback causes: band assertion on continuation pages | **not built** — no EIA/ERP burned instance (the remaining EIA/ERP fallbacks are 10a, excluded, and the AEO narrative table, no oracle); rung 1's instances were BUDGET, now out of scope | — |
| 11.6 (0d60b32) | a no-data placeholder right of a line's first value is band evidence (`oracle.read_page`'s own rule), so a column printed "NA"/"(s)" gets its band | 11.6 84.73 → 99.42 %; burned MER 94.74 → 95.00 |

Final burned scoreboard (frozen emitter, all 19 units): strict MER 95.00 · ERP 100.0 · STEO 96.77;
header MER 91.83 · ERP 95.45 · STEO 97.59; fired MER 41 → 46, ERP 3 → 4, STEO 14 → 11; fell back:
STEO 10a only; census on the burned pilot output EIA 0.31 % (rebuilt 0.08 / not 1.33), ERP 0.00 %.

Tried and reverted (measured worse on burned tables, logged in `build_log.md`): gap tile restricted to
lines with ≥ 2 phrases (MER header 91.83 → 91.63); gap tile only when TableFormer also spans the
head (STEO header 97.59 → 95.19); TableFormer-subset words for a lone head (no effect — TableFormer
maps table22's columns onto one band). Earlier F2 variants (subset-span check; span-midpoint check)
were superseded within the item (78.61 → 92.25 → 91.71 → 97.59).

Not on the list, left: vertical-rule glyphs decoded as "I" and fused into header words (11.3 "IK
erosene", 11.4 "Kero- I Lubri-"); rebuild quality on fired tables still < 95 % (1.10, 3.3e, 3.31,
3.3b); 10a and 3.3c (excluded).

## Part C — the one evaluation

- Frozen emitter (hashes re-checked) on the 15 scored units, one call per unit, into
  `data/.parsed_fresh_rung1b.tmp/`, renamed to `data/parsed_fresh_rung1b/`; **no emitter crash**;
  sha256 manifest (45 files) committed and pushed before the evaluator — 86442fa.
- Evaluator: one run, no crash, no rerun. Before scoring it passed `assert_frozen()`, the
  eval_freeze module hashes, the `data/parsed_fresh/` manifest and the candidate manifest, and the
  pre-registered denominators (MER conservative 13,756, forced misses 25, plain 13,731; ERP
  table33 / table59 in no denominator; 0 sec7 rows). Every STEO oracle page mapped to exactly one
  TableItem.
- Emission on the fresh set: MER rebuilt 38 / fallback 3 scored (6.2 p4 band assertion 12 vs 9;
  10.4b and 10.4c "text column" safety) — fallback causes with no instance on the burned EIA tables;
  ERP 6/6 rebuilt; STEO 13 rebuilt, 2 fallbacks (10a and an uncovered table, band assertion), 16
  not fired.

## Choices made unattended (conservative option; for the owner)

Owner answers at planning (2026-10-01), not written into decisions.md: table lists from the
freeze-pinned `admission/tables.json` + `steo/cells.jsonl` (freeze.json holds hashes only — the
protocol's "table list from freeze.json", D-039 status (3), does not match `freeze.py:24-45`); B =
10,000 / 95 % percentile; pilot build output in a new `data/parsed_rung1b/`
(`tests/test_budget_cbo_pinned.py` parametrize extended).

1. **Census read per family** (all tables of the family's units, rebuilt / not split by the
   candidate's `_emit_log`), ERP table33 / table59 excluded ("in no denominator"). By source the
   EIA census is 393 / 39,280 = **1.0005 %** (also > 1.0), ERP 0.0 %.
2. **Header association** counts the oracle columns of the plain-strict cell set (MER: clause-(b)
   admitted); flips are counted over the plain cells (forced misses can never flip).
3. **Page geometry** for MER/ERP scoring is read from the BASELINE parse's TableItem (the bbox the
   oracle's bands were measured in) and shared by both sides; A3(c) shows it reproduces rung 1.
4. **STEO table mapping**: the parse TableItem on the oracle page (lowest index if several — none
   had several); printed rows re-derived by the frozen rule and asserted equal to the frozen cells.
5. **"Bootstrap included" in A3(c)** = it runs and is deterministic; rung 1 reported no CI.
6. **trigger.py's rule untouched**; the rung-1b trigger lives in `run_rung1.py --fired live`.
   This changes the D-038 trigger's band clause on the rung-1b path (a band mismatch alone no
   longer fires) — inside the fix-list item, but a change to a pre-registered rule, so flagged.
7. **Emitter stdout discarded** in Part C; crash capture was exception type only (none occurred).

## Anything that looked wrong

- **Planning-time read (deviation-adjacent):** during planning an exploration subagent opened
  `reports/a1_diag/rung1b/fresh_admission.md`, `fresh_steo_admission.md` and
  `data/oracle/fresh/admission/tables.json` (oracle admission counts — the 13,756 / 25 / ERP-0
  facts; no parse output or score existed). Nothing else with a fresh number was opened before Part C.
- **STEO fails on 10a alone.** All 71 STEO misses are 10a (27.55 %, a fallback, 21 rows not found);
  the other 18 tables are 100 %. 10a was excluded from debugging and kept in the score, as ruled.
- **MER misses by 8 cells** (94.948 % conservative; plain 95.12 % passes); its census fails on the
  13 not-rebuilt tables (11.66 %), driven by fallback causes that the burned set never exhibited.
- **Clause-1 recall on 11.4 (sec11, burned)** is unchanged by count, but one route is compensation:
  the emitter still drops a superscript header "8" while its emitted "R 8" adds an "8" that the page
  word "R8" does not count.
- The census guard and flips use the rung-1 definitions; the BUDGET/CBO clause is satisfied by
  construction (byte-identical tables) and verified by the 704 pins on `data/parsed_rung1b/`.
- `docs/plan.md`'s rung-1b line still has its "___" blanks; I did not fill them (the protocol did not
  ask, and the verdict is the owner's to record).

## Hashes

c4a119f (Step 0) · 3b38f12 (A1) · 10ce944 (A2/A3) · ff3b1b0 (eval_freeze, START) · 32e3560, 71fea77,
80428a3, 32f496d, 48b0d00, 0d60b32, cf29435, a1f2f68 (Part B) · 255eef6 (STOP, emitter freeze) ·
86442fa (candidate manifest) · this report and the evaluation output: see the final commit.
