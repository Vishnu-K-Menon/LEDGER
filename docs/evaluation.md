# docs/evaluation.md — LEDGER evaluation specification

Read on demand. Sources: Phase 2 plan D8, D15, D24–D28, §6, §7; `docs/decisions.md` D-001, D-003, D-004, D-007, D-008, D-009, D-010. Nothing here is a suggestion; thresholds are conventions unless a source is named (see `docs/architecture.md` §10).

---

## 1. Eval-set construction (D24, D-001)

**Generator of questions.** A local model of a *different family* from the answer generator (Sonnet 5) and from the verifier — Qwen3-8B by default, subject to D-007's judge choice (the judge and question-writer may share a family; gold answers are copied strings, so the overlap is mild — say so in the README).

**Sampling.** 200 questions from randomly sampled chunks: 60% table chunks, 40% prose chunks. The 60/40 is design intent; the corpus-level tolerance is 50–70% table chunks (D-001). Each item:
```json
{"question_id": "q041", "question": "...", "gold_answer": "1,022", "gold_chunk_id": "cbo-2026-01-outlook::p24::tbl-1-1::s0",
 "answer_type": "number|short_phrase", "chunk_type": "table|prose", "unanswerable": false}
```
**Automatic filters.** Gold answer string present verbatim in the gold chunk; numeric answers copyable as printed (unit and period must be recoverable from the same chunk); no near-duplicates (embedding cosine > 0.9 to any accepted question); **at most 3 questions from any one distinct table** (D-034 — under row-splitting, table chunks from few tables look diverse and are not; a convention, revisable at A9; the per-unit cap is set at A9); question length 8–40 words.
**Human validation.** 50 items checked by hand: answerable, gold correct, unambiguous. Rejection rate is recorded.
**Controls.** 20 deliberately unanswerable questions — absent **entities** or **out-of-range periods** (D-034: "periods absent from the corpus" is impractical against compendia spanning decades); accepted only if retrieval top-5 does not contain the answer; all 20 human-checked. They measure both directions of the strict stance (D12).
**Use.** 150 answerable + 20 controls in every run; spares held back. **Chunk IDs are frozen before generation** (`data/chunk_ids.lock`); re-chunking afterwards invalidates `evidence_recall@STOP`.

## 2. Retrieval gate (D8, A6)

Fixed retriever for every arm: dense top-30 (Qwen3-Embedding-4B) → Qwen3-Reranker-0.6B → top-5. **Gate:** recall@5 of the gold chunk ≥ 0.85 (first on the 25 draft questions in week 1, then on all 200). Report MRR alongside. Below 0.85 → enable hybrid dense + BM25 (RRF) in config; below 0.75 after hybrid → `k_final: 8`, re-check. Re-retrieval inside the loop reuses this exact retriever with a claim-derived query, so all arms see the same retriever.

## 3. Metrics (D25)

| Metric | Definition | Source of truth |
|---|---|---|
| recall@5, MRR | gold chunk in / rank in the top-5 | question set |
| unsupported-claim rate (verifier) | share of ledger claims with verdict UNSUPPORTED at emit, per arm | local verifier |
| unsupported-claim rate (human) | same, on the 200 labelled claims | human labels |
| κ (primary) | Cohen's κ, verifier vs human, **binary** (PARTIAL → UNSUPPORTED), on 100 baseline + 100 post-repair claims, paired | labels + verifier |
| κ (secondary) | three-class κ; partial rate — reported separately, marked **not comparable** to the binary κ | labels |
| verifier FP / FN, AUROC | vs human labels, on the verifier score | labels |
| decomposition error | per-claim share failing entailed ∧ decontextualized; per-answer coverage (§4) | audit |
| citation accuracy | P(cited_support \| support) | verifier two-level |
| retained content | claims retained / baseline claims; answer tokens ratio; gold-answer coverage by judge — **`[unverified claim removed]` markers stripped first (D-008)** | ledger, judge |
| correctness | numeric exact match vs gold for `number` items; local-judge rubric score for `short_phrase` | gold, judge |
| evidence_recall@STOP | share of questions whose gold chunk is in context at STOP, by `max_iter` | ledger |
| iterations, tool calls, stop_reason mix | per query | ledger |
| tokens, $ per query | from API usage fields, never estimates | traces |
| abstention rate | on controls (target ≥ 90%) and on answerables (target ≤ 5%) | answers |
| parametric leakage | unsupported claims judged world-true, on the labelled subset | labels + judge |

Every rate carries a 95% CI: bootstrap over questions (paired bootstrap for the X−Y difference, D-010), plus mean ± sd over three sampled runs. **"Seed" means an independent sampled run at the model's default adaptive sampling** — the API has no seed parameter, and `temperature`/`top_p`/`top_k` were removed from the API (anthropic SDK 1.0.0, 2026-08-20; Sonnet 5 returns 400 for non-default values — D-019). The earlier `temperature: 0.3` no longer exists; the README must say so. **The seed count (three) is provisional**: the T5 variance probe (3 runs × 25 draft questions: numeric exact-match agreement, digit-level disagreement reported on its own line, abstention consistency, citation-set stability, answer-token spread) measures the run-to-run spread, and the seed decision is taken only once unsupported-claim rate exists (T9/T11) — never on the T5 number alone.

## 4. Decomposition audit (D15, mandate 1)

**Sample.** 50 answers: 25 from the no-repair baseline, 25 from the `re_retrieve(1) × claimify` cell's final answers; stratified table/prose.
**Per claim.** *entailed* — the claim adds nothing beyond the answer text; *decontextualized* — the claim stands alone (entity, unit, period present when the source sentence had them). Failure = not (entailed ∧ decontextualized).
**Per answer.** *coverage* — every factual proposition in the answer appears in some claim (0–1).
**Same rubric for the sentence-split baseline.**
**Reported.** Per-claim decomposition error rate, per-answer coverage, both arms — printed beside every downstream faithfulness number. The PARTIAL-label rate from §3 is reported next to it: a high partial rate means claims are too coarse to verify cleanly (D-003).
**Budget.** 50 audits × ~4 min ≈ 3.5 h; 25 in week 2 (T8), 25 in week 4 (T15).

## 5. Results table (D26, mandate 3)

**Rows.** `no-repair` · `delete-all` (trivial: every claim removed → 0% unsupported, 0 retained; computed from the no-repair run, no extra API calls) · `delete` · `rewrite` · `re_retrieve(1)` · `re_retrieve(2)`* · `re_retrieve(3)`* — each × decomposition ∈ {claimify, sentence_split}, except the * graft cells (claimify only). 10 cells × 3 seeds = 30 runs; initial generation is shared within a seed across arms.
**Columns.** unsupported rate (verifier) · unsupported rate (human, where labelled) · **retained content** · correctness · citation accuracy · evidence_recall@STOP · mean iterations · stop_reason mix · tokens/query · $/query.
**Why the trivial rows exist.** `delete-all` scores 0% unsupported while retaining nothing: any arm's improvement must be read next to what it cost in retained content, or it isn't one. `no-repair` is the X in X→Y.
**Run order.** Seed 1 for every cell first; inspect outputs and ledgers; then seeds 2 and 3 (D-009).
**Method split.** Automated for rates; human labels for calibration; the local judge (D-007, pinned revision) only for correctness of `short_phrase` items and gold-answer coverage; no RAGAS in the core table (one comparison row allowed if < 1 h).

## 6. The κ pilot — week 1 go/no-go (§7, A2, D-003, D-004, D-007)

**What is labelled.** 50 `(claim, retrieved_context)` pairs from the single-shot baseline, labelled **SUPPORTED / PARTIAL / UNSUPPORTED** against the retrieved context only (faithfulness, not world truth). Free-text note per PARTIAL. ~2.5 min/claim ≈ 2 h.
**Sampling.** Baseline on 25 draft questions (13 table-derived, 12 prose). Decompose with the Claimify-style prompt (~125 claims). Stratified random sample of 50: 25 from table answers, 25 from prose; at most 3 per answer; **not** stratified by verifier score (that would bias κ). Fixed random seed; sample ids committed to `data/labels_pilot.jsonl`.
**What is scored.** Two candidate verifiers, bf16 (D-012): Bespoke-MiniCheck-7B (77.4 BAcc on LLM-AggreFact; non-commercial, commercial by agreement) and Granite Guardian 3.3 8B (76.5, IBM-run; Apache-2.0); MiniCheck-Flan-T5-Large (75.0) as CPU fallback. Each scored under **two input modes**: concatenated top-k context, and per-chunk with max over chunks (D-004). Output: a 2 × 2 table of binary κ at default thresholds, plus AUROC, plus the partial rate and three-class κ (secondary).
**Input-mode rule, committed before the pilot:** if the two modes are within 0.05 κ for the chosen verifier, take concatenated.
**Also at the pilot:** stop and ask the owner for the judge model (D-007). If the pilot selects a Qwen-family verifier, the judge must be a third family.
**Branches (on the best binary κ):**
- **κ ≥ 0.6** → GO. Use the higher-κ verifier at its default threshold; the 50 pilot labels join the 100 baseline labels in week 3.
- **0.5 ≤ κ < 0.6** → GO. Use the higher-κ verifier; tune the threshold on the pilot; report final κ only on the week-3 labels, never on the pilot.
- **both < 0.5** → inspect the 10 largest disagreements. If ≥ 5 are labeller errors, relabel once and recompute. Otherwise the local-verifier premise fails: execute the Stage 3 conditional switch to Idea 3, salvaging corpus, index, config and tracing (≈ 11 h).
- **Side check (A3):** if fewer than 4 of the 50 claims are UNSUPPORTED (binary), the effect is unmeasurable at n ≈ 750 — harden the question set before week 2 (multi-cell, cross-table); if still < 5% after hardening, switch the generator to Haiku 4.5 and say why.
**Report.** The four κ values, the rule applied, the branch selected, the verifier and input mode chosen, and the judge request — then confirm before week 2 (D-004 is RESOLVES-ON-DATA).

## 7. Week-3 labels (D-010)

100 questions, stratified table/prose. For each: one baseline claim chosen at random from the no-repair answer; the paired post-repair claim from the `re_retrieve(1) × claimify` cell, seed 1 — the same `claim_id` if it survived unchanged (**branch 1**), the claim recorded in `replaces` if it was repaired (**branch 2**), a random claim from the post-repair answer if the baseline claim has no successor (**branch 3**, split into **3a** terminal delete — still unsupported at STOP, D22 — and **3b** no successor found, lost in regeneration). Pairing rule confirmed (D-010, D-027). The branch is written on the label record **when the pair is selected** by `eval/labels.py` — a bookkeeping fact, not a labeller judgement — and the four counts are emitted. Three-class labels. `eval/labels.py` refuses a set whose halves do not share the same 100 question ids. **Analysis (pre-committed, D-027):** headline X→Y is the question-level paired bootstrap over all 100 pairs, always; the four branch counts are printed beside it; branch 3 ≤ 20 → claim-level README language, > 20 → answer-level language with n stated; 3b > 5 → reported as a successor-matching defect in the D27 discussion; branches 1+2 alone may appear as a secondary line labelled CONDITIONAL (selection-biased; never the effect). Successor matching (how a surviving claim keeps its `claim_id`, how `replaces` is populated across regeneration) is a T12 requirement with a unit test.

## 8. Failure taxonomy (D27)

Every verifier–human disagreement and every flagged query gets exactly one code:
`R` retrieval miss (gold chunk not in context) · `D` decomposition error · `V-FP` / `V-FN` verifier vs human · `G` generation unsupported with evidence present · `C` wrong citation (supported, but not by the cited chunk) · `P` repair regression (rewrite / regenerate introduced a new unsupported claim) · `S` stop-rule miss (stopped with unsupported claims and evidence available) · `B` budget exhausted.

## 9. Regression (D28)

Unit tests on every push: schemas, ledger invariants (a SUPPORTED claim cannot have empty `evidence_ids`; `iter_resolved ≥ iter_first_seen`), stop rule, config loading, the D-002 single-client guard, the D-006 no-retrieval guard, the D-008 marker-stripping identity, a test that the matrix runner never calls the generator synchronously (Batch only), a test that no module under `tracing/` or `eval/` imports `phoenix`, a test that every post-hoc evaluation carrier has exactly one Span Link (D-017), T12 successor-matching tests (D-027, D-029): an unchanged claim keeps its `claim_id`; a regenerated claim carries `replaces`; a regenerated claim about a **different entity** is not matched; **one-to-one** — two baseline claims cannot both map to one regenerated claim; and (open decision, test required) a claim whose unit/period was **corrected** is matched as branch 2 without admitting unrelated claims about the same entity — never a blanket "qualifier changed → not matched", and a **T14 matrix-runner resumability test** (D-025, D-028): per `(cell, seed, question_id)` — completed → skip; submitted with a recorded batch id → poll, never resubmit; expired or errored → resubmit only those. Double-submission is the failure guarded (it spends budget twice); batch processing and result-expiry windows are taken from Anthropic's batch docs at build time, not memory. **CI runs only these unit tests plus `ruff`; `ledger smoke` never runs in CI (D-028).** On demand: `ledger smoke` — 20 questions (~$0.50 via Batch) writing `reports/smoke.json`; compared against seed 1's results on the same 20 questions (D-029, D-030): **structural assertions fail outright** (verifier all-SUPPORTED or all-UNSUPPORTED; zero ledger claims; `rag.cost_usd` = 0; schema-valid < 0.98); **unsupported-claim share** — paired t-interval on the 20 per-question differences, 90 % two-sided, paired bootstrap (`eval.bootstrap_n`) as cross-check, disagreement is a flag; **`evidence_recall@STOP`** — exact McNemar on the discordant pairs, 90 % two-sided (not t or bootstrap: ~3 non-zero pairs); worse → **fail**, better → **flag for inspection**. Breakage only — MDEs (~14 pp, ~22 pp) are conditional on assumed spreads, to be replaced by T5-probe / seed-1 values. Clean-run P(fail) ≈ 10 %, P(fail or flag) ≈ 19 %. `reports/smoke.json` stores per-question unsupported share, per-claim verdicts and per-question gold-in-context — never aggregates. Runs **(a)** after any code change made after seed 1 and **(b)** once before the README numbers — not routinely before seeds: each run is its own Batch wait (D-025), and before seed 1 there is no centre (D-029).
