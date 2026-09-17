# docs/plan.md — LEDGER build order (tick in-repo)

60 h = 15 h/week × 4. Hours are Stage 3 estimates. Sources: Phase 2 §4–§6, `docs/decisions.md`. Tick `[x]` when done; write the measured number next to every gate.

## Day 1 — before any GPU hour (D-011, D-014)
- [x] Request the "Running On-Demand G and VT instances" vCPU quota — the long pole. **Approved 2026-09-14: 8 vCPU us-east-1 = one g6e.xlarge, no headroom for a second GPU instance or a g6e.2xlarge (D-011 status).** ~~No approval by day 4 → κ pilot on an hourly non-AWS L40S/A100, then move to g6e.xlarge.~~ (moot; branch kept)
- [x] Billing alarm at $50; confirm credits apply to EC2 and S3 in the chosen region. (done 2026-09-14, us-east-1)
- [ ] **E3** Idle auto-stop on the g6e.xlarge (idle ~153 h/week). Blocked until the instance exists; the g6e is not launched until T4 (T2/T3 are CPU). **Done in the same sitting as the first g6e launch, before the first run** — it is the one hard constraint in CLAUDE.md with no code guard.
- [x] **E4** Phoenix up — on a **t3.small** (D-023, revises D-015): `i-0af5e7bc04d2667bf`, Elastic IP `54.160.244.106`, private IP `172.31.68.230`, image `arizephoenix/phoenix:20.12.0` pinned, `--restart unless-stopped`, data on `/home/ec2-user/phoenix-data` (persistence verified). `OTEL_EXPORTER_OTLP_ENDPOINT=http://54.160.244.106:6006` at User scope on the laptop (base URL, no path). Done 2026-09-16.
  - [ ] **Next session (D-023 §2)** `cat /home/ec2-user/phoenix-mem.log` — confirm the 5-min cron is writing samples. If empty or full of errors, check **permissions first**: cron runs without the interactive shell's group membership, so `ec2-user` may not be effectively in the `docker` group and `docker stats` fails into the log. Not the schedule.
  - [ ] **Next session (D-023 §2)** `systemctl is-enabled docker` → `enabled`; `systemctl is-enabled crond` → `enabled`. If not, enable and note it in D-023. `--restart unless-stopped` only helps if Docker itself starts at boot; the week-3 resize is a stop/start.
  - [x] **Now (D-026)** take EBS snapshot #1 of the `ledger-phoenix` root volume (hot is fine — nothing is writing). Snapshot id: `snap-0e63c11aa44fca5f6` · Volume id: `vol-06d56753ddf4149a0` · 2026-09-16
- [x] **E5** Confirm the D-010 pairing rule (`docs/evaluation.md` §7). Confirmed 2026-09-16 as written, Option B (branch recorded per pair, 3a/3b split) — D-027.
- [ ] **E6 (half)** Repo exists at https://github.com/Vishnu-K-Menon/LEDGER — remote wired and pushing (2026-09-16); Actions **not** enabled. Actions gates only `pytest` + `ruff` (D-028; smoke never runs in CI). **If Actions setup exceeds ~1 h, defer it** — deferral costs no measurement; the κ pilot is the week-1 milestone.

## Week 1 — index, baseline, go/no-go (15 h)
- [x] **T1 · 2 h** CLI skeleton (`uv run ledger --help`); pydantic config + YAML (D31); OTLP exporter via `tracing/otel.py` with OpenInference (D29/D-014); first traced call visible with token counts.
  - [x] **A5 · 0.5 h** — **PASSED 2026-09-16 on `ledger-phoenix` (t3.small, D-023): Arize Phoenix v20.12.0** (server, pinned image; PyPI happened to match). Sync trace `fd24cb3bde5d321dbb78e88eb03f1c83`: (a) pass, (b) pass, (c) pass under the amended criterion. Batch trace `9bff4c724852c3cc2363df2df2475b9e` (`msgbatch_01PrjXG9p42ngysQqywneaFv`): usage fields populated on the LLM span, `(rates: batch)`, cost `0.000036` = exactly half the sync `0.000072` on identical usage (16 in / 4 out) — D26's cost column will not be 2× wrong. Phoenix's project Total Cost shows $0: its own pricing table lacks `claude-sonnet-5`; cosmetic, `rag.cost_usd` is on the root span (D30). Criterion as run — with `openinference-semantic-conventions==0.1.37` and `openinference-instrumentation==0.1.63` pinned (D-018), on the first traced call: (a) spans render in Phoenix with token counts; (b) an inline `evaluations.*` verdict shows in the verify span's Evaluations panel; (c) a post-hoc `EVALUATOR` carrier stores all `evaluations.*` attributes and exactly one Span Link; **rendering as a separate root trace is expected and accepted (D-022)** — Phoenix does not resolve Span Links; the carrier carries `rag.record_type` for filtering. (a) false → OTLP to Langfuse Cloud Core, same instrumentors. **Local smoke test 2026-09-14 (Phoenix 20.12.0): (a) pass, (b) pass, (c) as accepted — that local run did not tick A5; A5 is the t3.small host `ledger-phoenix` (D-023) and passed there as recorded above.**
- [ ] **T2 · 3 h** Corpus: EIA 50 / CBO 40 / GAO 30 provisional; manifest URL · SHA-256 · agency · date (D1, D-001).
- [ ] **T3 · 3 h** Docling parse (TableFormer accurate) on the first 20 documents; then the rest after A9.
  - [ ] **A1 · 1.0 h** — ≥ 95% of cells correct on 10 tables (≥ 150 cells). If false → `parser: paddleocr_vl`, re-audit. Measured: ___
  - [ ] **A9 · 0.3 h** — `table_chunk_share` after 20 documents inside 50–70%. If false → adjust the remaining ingest only; never re-parse. Report and confirm before document 21 (D-001). Measured: ___
- [ ] **T4 · 3 h** HybridChunker (tables atomic, headings, 512 tok); Qwen3-Embedding-4B bf16; Qdrant local file via the single `make_client` (D-002); **freeze chunk IDs** (`data/chunk_ids.lock`).
  - [ ] **g6e launch checklist (D-023 §6) — same sitting, in this order:**
    - [ ] launch the g6e.xlarge in `vpc-0f3297a449901c109` (same VPC as `ledger-phoenix`, or the SG reference cannot match)
    - [ ] attach `ledger-gpu-sg` to the g6e at launch
    - [ ] **E3**: configure idle auto-stop before the first run
    - [ ] set `OTEL_EXPORTER_OTLP_ENDPOINT` on the g6e to the **PRIVATE** address `http://172.31.68.230:6006` — NOT the Elastic IP (SG-to-SG matches private traffic only; the public route is dropped silently)
    - [ ] verify with one traced call **from the g6e** (`uv run python scripts/a5_probe.py`) and see it in the `ledger` project before starting T6
  - [ ] **A8 · 0.2 h** — embedder 4B + reranker 0.6B + verifier 8B, all bf16, resident on the L40S (44.7 GiB); one verify call; `nvidia-smi`. If false → 0.6B embedder, then separate stages; never quantize (D-012). Measured GiB: ___
- [ ] **T5 · 2 h** Single-shot baseline: strict prompt (D12), JSON schema (D13), Batch client; 25 draft questions. No sampling parameters (D-019). Investigate `output_config` (native structured output in anthropic 1.5.0) against D13's retry-once-then-fallback and A4.
  - [ ] **T5 variance probe · 0.5 h (D-019)** — same prompt, 3 runs × 25 draft questions at default sampling. Report: numeric exact-match agreement vs gold ___ · **digit-level disagreement (own line; a D12/D14 problem if non-zero, not a seed question)** ___ · abstention consistency ___ · citation-set stability ___ · answer-token spread ___. **This number does not decide the seed count** — that waits for the first run with an unsupported-claim rate (T9/T11) and gets a D-019 successor entry.
  - [ ] **A4 · 0.5 h** — ≥ 98% schema-valid JSON on 25 draft calls. If false → forced tool-use schema + retry policy. Measured: ___
  - [ ] **A6 · 0.5 h** — recall@5 of the gold chunk ≥ 0.85 on the 25 drafts. If false → hybrid BM25; < 0.75 after → `k_final: 8` (D8). Measured: ___
  - [ ] **A7 · 0.2 h** — full matrix ≤ $120 projected from measured tokens/query. If false → Batch-only; cut graft cells. Projected: ___
- [ ] **T6 · 2 h** κ pilot per `docs/evaluation.md` §6: 50 claims, three-class labels; Bespoke-MiniCheck-7B and Granite Guardian 3.3 × {concatenated, per_chunk_max}, bf16.
  - [ ] **A3 · 0.3 h** — ≥ 4 of 50 pilot claims UNSUPPORTED (baseline rate ≥ 8%). If false → harden questions; still < 5% → Haiku 4.5, say why. Measured: ___
  - [ ] **A2 · 2.0 h (inside T6)** — best binary κ ≥ 0.6 GO · 0.5–0.6 GO + tune threshold on pilot · both < 0.5 → inspect 10 disagreements, relabel once if labeller error, else **switch to Idea 3** (≈ 11 h salvaged). Four κ values: ___ / ___ / ___ / ___ · branch: ___
  - [ ] **D-004** input-mode rule applied (tie within 0.05 → concatenated): mode chosen: ___
  - [ ] **D-007** stop and ask the owner for the judge model; pin `judge.revision`: ___

**Week 1 milestone:** a reported κ table, a branch selection, a verifier and input mode fixed, a judge chosen — not working loop code.

## Week 2 — questions, decomposition, verifier, two arms (15 h)
- [ ] **T7 · 3 h** 200 questions from the local model (D24); filters; 50 hand-validated; 20 unanswerable controls; recall gate on all 200 (D8). Measured recall@5: ___
- [ ] **T8 · 4 h** Decomposition node (Claimify-style structured output) + sentence-split baseline; decomposition audit, first 25 answers (D15).
- [ ] **T9 · 3 h** Verifier node: two-level verification (D16), verdict schema; verdict written inline on the verify span as `evaluations.0.evaluation.*` via `tracing/otel.py::record_verdict` (D-017); ledger row stores `trace_id`, `span_id`; threshold fixed from the pilot.
- [ ] **T10 · 4 h** `delete` (with marker, D-008) and `rewrite` (same context only, D-006) arms; ledger invariants + unit tests (D21, D28).
- [ ] **T11 · 1 h** `delete-all` trivial baseline from the no-repair run; retained-content metric with markers stripped (D26).
  - [ ] **Seed-count decision (D-019 successor)** — first run where unsupported-claim rate exists: report its run-to-run spread beside the T5 probe numbers; decide 3 seeds vs fewer; log the successor entry. Until then D26 stays at 10 cells × 3 seeds.

## Week 3 — the loop, the labels (15 h)
- [ ] **T12 · 6 h** LangGraph graph + checkpoints (D20); `re_retrieve` arm; stop rule and caps (D22); `stop_reason`; `evidence_recall@STOP` (the Idea 1 graft).
  - [ ] **Successor matching (D-027, open requirement):** define how a claim that survives `regenerate` keeps its `claim_id` and how `replaces` is populated for a repaired one; unit tests (D-027, D-029): an unchanged claim keeps its `claim_id`; a regenerated claim carries `replaces`; a regenerated claim about a **different entity** is not matched; **one-to-one** (two baseline claims cannot both map to one regenerated claim); and — **open T12 decision, test required** — a claim whose unit/period was **corrected** is matched as branch 2 without admitting unrelated same-entity claims (do NOT add "qualifier changed → not matched": that pushes every D14/D15 qualifier repair into 3b). Without matching, D-010 branches 1–2 cannot occur and branch 3 → 100. Candidates and failure modes: 2026-09-16/17 session reports.
    - **Candidate 4 — lineage by construction:** `re_retrieve` regenerates only the sentences holding unsupported claims. Supported claims in OTHER sentences carry forward untouched (branch 1 by construction across sentences); a supported claim sharing a sentence with an unsupported one is regenerated with it and still needs matching within that sentence. The loop knows which `claim_id` triggered each re-retrieval (`replaces` known, not inferred); matching is needed only within a regenerated sentence (`source_sentence_idx`), which removes the cross-sentence same-entity cases; same-sentence multi-period claims (e.g. "rose from $X in FY2025 to $Y in FY2026") remain the residual hard case.
    - **Open scope question (owner decides at T12, before the matcher):** is `re_retrieve`'s regeneration whole-answer or sentence-scope? Evidence for whole-answer: `architecture.md:125` (D20) — `re_retrieve` loops back to `retrieve`, i.e. through `generate`, while `rewrite` re-enters at `decompose`; and D21's `regenerate(question, chunks, ledger)`. Whole-answer → `rewrite` and `re_retrieve` differ on regeneration scope as well as evidence: a second confound, not covered by D-006, that would need a successor naming D20/D21 and `architecture.md:142`. Sentence-scope (candidate 4) → also a successor naming D20/D21, narrowing `re_retrieve`'s regeneration. D-006 is unchanged in both cases.
- [ ] **T13 · 8 h** Claim labels: 100 baseline + 100 post-`re_retrieve(1)`, paired on the same 100 questions, seed 1; three-class (D-010, D-003).
- [ ] **T14 · 1 h** Matrix runner: `experiments/matrix.yaml` → Batch jobs, one seed at a time (D-009) → `results/<cell>/<seed>.jsonl`. **Resumable across sittings (D-025):** submit → persist batch ids → exit; a later invocation polls and collects.
  - [ ] **Resumability unit test (D-025, D28):** per `(cell, seed, question_id)` — completed → skip · submitted with a recorded batch id → poll, never resubmit · expired or errored → resubmit only those. Double-submission spends budget twice; that is the failure guarded. Take batch processing and result-expiry windows from Anthropic's batch docs, not memory.
  - [ ] **D-016 revisit** — after the matrix runner has been run by hand twice: if the run → eval → annotate sequence is still being typed out each session, log a successor to D-016 and build a `/eval-run` slash command; otherwise tick this and move on.
- [ ] **End of week 3, before T15 (D-023 §1 resize check):** read `/home/ec2-user/phoenix-mem.log` (do not take a fresh sample — the burst is transient) and report the **peak** `MemPerc` and the distribution against the 27.44 % idle baseline. Peak: ___. Near the ceiling → stop `i-0af5e7bc04d2667bf`, change type to t3.medium, start (~5 min; data and Elastic IP preserved; endpoint unchanged). Decision: ___
- [ ] **Before T15 (D-026):** `docker stop phoenix` → EBS snapshot #2 of the `ledger-phoenix` root volume → `docker start phoenix`. Snapshot id: ___
- [ ] **If week 3 runs over → apply the cut list below, in order.**

## Week 4 — runs, numbers, README (15 h)
- [ ] **T15 · 4 h attention / ~3 days elapsed (D-025)** `ledger matrix --seed 1` for all 10 cells; inspect outputs and ledgers; then seeds 2 and 3 with `--confirm-seed-1-inspected`; local verification + local judge over all outputs; decomposition audit, 25 post-repair answers. **The 4 h is attention time.** D-009 makes this three sequential Batch waits (SLA ≤ 24 h each, no priority for small jobs; the single-request A5 batch already took materially longer than sync). Assumed elapsed window: 3 calendar days — submit at the start of a sitting, inspect at the next. A batch still in progress after 24 h → apply cut #1 then #3 before anything else; an expired result → resubmit, keyed by `(cell, seed, question_id)`. The T14 runner must be resumable across sittings (submit → persist batch ids → exit). The same conflation exists, one wait each, on T5, T8, T10, T12 and `ledger smoke`.
- [ ] **T16 · 5 h** Analysis: D26 table with CIs; paired κ on 200; decomposition error; citation accuracy; `evidence_recall@STOP` by `max_iter`; failure taxonomy on every disagreement (D27); human labels emitted as post-hoc `EVALUATOR` carrier spans linked to their verify spans via `eval/trace_annotate.py` (D-017).
- [ ] **T17 · 4 h** README with the numbers and caveats (fixed arms; 512 convention; OpenInference-not-gen_ai with the Aug 2026 date; judge/question-writer family note); CLI or notebook demo; `docs/decisions.md` updated; `ledger smoke` on demand — tolerance centred on seed 1's smoke results (width open, D-029); run after any post-seed-1 code change and once before the README numbers, **never in CI** and not before each seed (D-028, D-029; CI = `pytest` + `ruff`).
- [ ] **T18 · 2 h** Slack. The Idea 3 borrow needs ≥ 5 h; it will not fit — v2.

## Cut list — only if week 3 runs over; apply in this order (§5)
- [ ] 1. Graft cells `max_iter` 2 and 3 → keep `re_retrieve(1)`. Saves ~3 h, ~$3. `evidence_recall@STOP` still reported at `max_iter = 1`.
- [ ] 2. Sentence-split decomposition **arm** → 5 cells. Saves ~2 h. The decomposition **audit** stays.
- [ ] 3. Seeds 3 → 2. Saves ~1 h, ~$10. CIs widen — say so in the README.
- [ ] 4. Claim labels 200 → 150 (75 / 75, still paired). Saves ~2 h. κ CI widens from ≈ ±0.10 to ≈ ±0.12 (estimate).
- [x] 5. ~~Smoke-eval CI → v2 (unit tests stay). Saves ~1 h.~~ Moot: smoke never runs in CI by design (D-028); nothing to cut.
- [ ] 6. `rewrite` arm → keep `delete` and `re_retrieve`. Saves ~2 h.

## Teardown — after week 4, in this order (D-023, D-026; do not reconstruct from memory)
- [ ] terminate the g6e
- [ ] `docker stop phoenix` → EBS snapshot #3 of `/home/ec2-user/phoenix-data`'s volume **BEFORE** terminating `ledger-phoenix` (this is the project's evidence). Snapshot id: ___
- [ ] terminate `ledger-phoenix` (`i-0af5e7bc04d2667bf`)
- [ ] release `eipalloc-003a67ffced02e689` — billed hourly once detached
- [ ] delete `ledger-phoenix-sg` and `ledger-gpu-sg`
- [ ] empty and delete the S3 bucket
- [ ] confirm the $50 billing alarm shows no residual spend

## Never cut
- `no-repair` and `delete-all` rows (mandate 3)
- the decomposition audit (mandate 1)
- κ — verifier–human calibration
- tracing from commit one (mandate 5)
- the 20 unanswerable strict-stance controls (D12/D24)
