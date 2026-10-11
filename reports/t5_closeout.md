# T5 close-out record

What no other tracked file holds. Facts only; each carries its source. "(owner)" marks a statement
made by the owner that no file in the repository records. Written 2026-10-11 at HEAD f523f8f; no
number here is new, no T5 result was re-scored.

## a. Artifacts outside git

| artifact | SHA-256 | what it is |
|---|---|---|
| `s3://ledger-vkm-2026/t5/t5-retrieval.tar.gz` | `67254567ce962015d9f4f6fdb05ab13e8a85b455403e458898fa2238a27a0afa` | retrieval output of both arms (from `t5_return.sh`) |
| `s3://ledger-vkm-2026/t5/t5-batch-results.zip` | `44b0500df72a7135b914844657556021caddf976082e508b5e36867814c01eb1` | the three `results/t5_baseline_r*` folders (`1.jsonl` each), `t5_jobs.jsonl`, `t5_batch_sidecar.jsonl`, `t5_traced.txt`, `contexts.jsonl` (at the zip's root, taken from `results/t5/`); uploaded through the S3 console (owner) |
| `s3://ledger-vkm-2026/t5/t5_verifier_probe.md` | not recorded | the probe report as it came off the GPU box (the tracked copy is `reports/t5_verifier_probe.md`) |

Recheck on 2026-10-11, on the laptop: `sha256sum` of `%USERPROFILE%\t5-batch-results.zip` gives
`44b0500d…01eb1`, **matches** the hash above; its entries are the seven files listed.
`sha256sum` of `t5-retrieval.tar.gz` in the repository root (untracked, gitignored) gives
`67254567…a0afa`, **matches**. The zip is a copy of the gitignored `results/` files named above.

## b. GPU session 2026-10-11 (UTC about 05:00–05:15)

- The box was at dec71ff and was brought to d65787b with `git pull`. The pull was refused until the
  box's untracked `data/chunk_ids.lock` and `data/index_meta.json` were moved aside; they were
  byte-identical to the tracked files (`8760715f…` and `3e9d5b7c…`) and are kept in
  `~/pre_pull_backup` on the box. Untracked `data-qdrant.tar.gz` and its `.sha256` remain in
  `~/LEDGER` on the box.
- Retrieval ran for both arms over 33 questions (34 lines including the header, per file).
- The verifier probe wrote "stops: none" (see c: that line was printed although the MiniCheck
  README example did not reproduce; fixed in the code, not rerun).

## c. Verifier probe (`reports/t5_verifier_probe.md`)

Environment: torch 2.14.0+cu130, transformers 5.17.0, NVIDIA L40S.

- **Granite Guardian 3.3 8B:** 16 of 16 on the mechanical digit-sensitivity claims (4 supported and
  4 altered, at one-chunk and five-chunk context); call shape, polarity and score parsing
  confirmed against the pinned model card. Sixteen mechanical claims are not an error-rate
  estimate.
- **Bespoke-MiniCheck-7B:** the README example is **not reproduced**: got `[0, 0]` where the
  README gives `[0.984, 0.011]` (tolerance ±0.02). P(yes) is 0.000 on all 16 claims. Its 8 of 8
  on altered claims means nothing: it said "not supported" to everything (supported claims 0 of 8).
- Observation, mechanism not verified: `probe.support_prob` sums `exp(logprob)` over the top-5
  decoded first-position tokens whose lower-cased text is `yes`, and returns the integer 0 when none
  is. A result of exactly 0 therefore means "yes" never appeared among the top five. The probe did
  not record those five tokens. The code now writes them (repr of the token, with its logprob) for
  every MiniCheck call, and treats a non-reproduced example as a stop for that verifier; the probe
  has not been rerun.

## d. Tracing

- a5 probe trace `f01eecef8f0aea8f168474a70de50ed8` and retrieval trace
  `6b68e0b2aa1a8b193c433857ed6b68e8`: not checked in Phoenix (owner, 2026-10-11). The results are
  in files and in S3; nothing is lost.
- Harness check: Phoenix was stopped, the export failed, and the report was written first
  (`reports/t5_harness_check.md`).
- Batch collection: Phoenix was running; the run printed "spans emitted for 93 collected results"
  and no export error; not checked in the UI.

## e. Controls

Decided by the owner on 2026-10-11 after a planning-chat reading of each candidate against the
rule (the `procedure` field of `data/controls_accepted.json` says so). The five accepted controls
are c001–c005; c006 and c007 were not selected. Four of the five (c001, c002, c004, c005) are tagged
`near_miss`.

Disclosure carried from the owner check: old c04 (and arguably c09) were rejected before
retrieval on near-answer reasoning, so the set may lean clean; four near-miss controls out of five
partly offsets that. All 5 abstained in run 1 (`reports/t5_controls.md`): a gross-failure check on
5 questions, not a rate.

## f. Thinking tokens

0 on all 93 Batch requests (counted from the `usage` of the three `1.jsonl` files) and on all 3
harness-check calls (`reports/t5_harness_check.md`, thinking column): requests carried
`thinking: between_tools`, effort `high`, no tools. Recorded as observed; D-043 ruling 1 asks only
that they be recorded.

## g. Scope and dependence (carried by every T5 number)

- D-043 status 2026-10-10 (findings): the 25 questions cover only those whose gold chunk carries
  its own unit, label and period.
- D-043 status 2026-10-10 (item 1): the drafts were written by the model that answers them and the
  owner's check was assisted by Claude chats, so recall and answer match are likely optimistic and
  the unsupported-claim rate likely low (direction only, not measured).
- The 11 `short_phrase` items are lexical containment only (31 of 33 answers contain the phrase),
  not correctness.
- Whether a matched number is attached to the right period, entity or unit was not checked
  (D-043 status 2026-10-10, answer matching).
- Digit-level disagreement is 2 of 25 by the committed definition (`reports.py:19`); read by hand,
  both are trailing-comma tokens with identical values (D-043 status 2026-10-11). Both readings are
  given wherever the number is cited.

## h. Owed before T6 (not done here)

- **MiniCheck** (c): needs a GPU session; first the top-5 tokens now written by the probe.
- **Claim yield:** run 1 has 24 sentences in 23 non-abstaining answers (about 26 projected for 25
  answers, `reports/t5_claim_yield.md`) against about 125 claims that `docs/evaluation.md` §6 expects
  from decomposing 25 answers. The decomposition yield is the open question.
- **The D-007 judge model** is not chosen.
- **T6 owner labels** with no model in the loop and committed before any verifier output on those
  claims (D-043 status 2026-10-10, item 1).

## i. Operations notes

- The owner's laptop has no AWS CLI; the S3 console was used. A console download saved
  `t5-retrieval.tar.gz` as `t5-retrieval.tar`; it was renamed after its hash matched.
- A pre-existing laptop 6006 rule was found on `ledger-phoenix-sg` and deleted along with the GPU
  rule (owner).
- The API key was rotated on 2026-10-11 after collection: new key verified, old key deleted in the
  console (owner). A persistent User-scope `ANTHROPIC_API_KEY` and two PSReadLine history lines
  were removed (owner).

## j. Parse defects seen at the owner check — not fixed, T7/v2

Recorded only; nothing was changed. Each is from the owner's reading of the candidates.

- Merged cells in a Budget P&F slice (t14, lines 4060/4070/4080).
- U+FFFD in "U.S." in ERP table42 headers.
- Garbled stacked ERP headers.
- OBJCLASS prints "Table 1" with no agency in the chunk.
- CBO slices lose the section label (cbo-61959 s9).
- "Unit lost on continuation slices" (t03, t14): the mechanism is **unverified**; look at the chunks
  before designing a fix.

## k. Owner-check outcome by stratum

Counted from `data/questions_draft_candidates.jsonl` (latest line per candidate id; 79 candidates).
"Not reached" means the owner stopped once enough were accepted; `accept` is still null.

| stratum | accepted | rejected | not reached |
|---|---|---|---|
| prose | 12 | 5 (including p02: a JSON parse failure, the model declined in prose) | 13 |
| table | 13 | 14 | 5 |
| supplement | 1 | 1 | 5 |
| control | 7 | 3 | 0 |

The `t5_draft.py` change in this pass keeps the stop reason and raw reply on a failure and lets
the drafter skip a chunk in a structured form; neither affects the committed candidates.
