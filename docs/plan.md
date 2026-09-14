# docs/plan.md — LEDGER build order (tick in-repo)

60 h = 15 h/week × 4. Hours are Stage 3 estimates. Sources: Phase 2 §4–§6, `docs/decisions.md`. Tick `[x]` when done; write the measured number next to every gate.

## Day 1 — before any GPU hour (D-011, D-014)
- [ ] Request the "Running On-Demand G and VT instances" vCPU quota — the long pole. No approval by day 4 → κ pilot on an hourly non-AWS L40S/A100, then move to g6e.xlarge.
- [ ] Billing alarm at $50; confirm credits apply to EC2 and S3 in the chosen region.
- [ ] Idle auto-stop on the g6e.xlarge (idle ~153 h/week).
- [ ] Phoenix on a t3.medium (D-015): container up, `OTEL_EXPORTER_OTLP_ENDPOINT` set in the environment (never in code).
- [ ] Confirm the D-010 pairing rule (`docs/evaluation.md` §7).
- [ ] Repo exists at https://github.com/Vishnu-K-Menon/LEDGER — remaining: wire the remote, enable Actions (prerequisite for D28). **If Actions setup exceeds ~1 h on day 1, defer CI to v2** (it is cut #5); the κ pilot is the week-1 milestone and CI survives postponement.

## Week 1 — index, baseline, go/no-go (15 h)
- [x] **T1 · 2 h** CLI skeleton (`uv run ledger --help`); pydantic config + YAML (D31); OTLP exporter via `tracing/otel.py` with OpenInference (D29/D-014); first traced call visible with token counts.
  - [ ] **A5 · 0.5 h** — with `openinference-semantic-conventions==0.1.37` and `openinference-instrumentation==0.1.63` pinned (D-018) (record `arize-phoenix` version: ___), on the first traced call: (a) spans render in Phoenix with token counts; (b) an inline `evaluations.*` verdict shows in the verify span's Evaluations panel; (c) a post-hoc `EVALUATOR` carrier with one Span Link renders against the linked verify span (D-017). (a) false → OTLP to Langfuse Cloud Core, same instrumentors. (c) false → D-017 successor: keep the wire form, add a Phoenix-side display import. Decide this week.
- [ ] **T2 · 3 h** Corpus: EIA 50 / CBO 40 / GAO 30 provisional; manifest URL · SHA-256 · agency · date (D1, D-001).
- [ ] **T3 · 3 h** Docling parse (TableFormer accurate) on the first 20 documents; then the rest after A9.
  - [ ] **A1 · 1.0 h** — ≥ 95% of cells correct on 10 tables (≥ 150 cells). If false → `parser: paddleocr_vl`, re-audit. Measured: ___
  - [ ] **A9 · 0.3 h** — `table_chunk_share` after 20 documents inside 50–70%. If false → adjust the remaining ingest only; never re-parse. Report and confirm before document 21 (D-001). Measured: ___
- [ ] **T4 · 3 h** HybridChunker (tables atomic, headings, 512 tok); Qwen3-Embedding-4B bf16; Qdrant local file via the single `make_client` (D-002); **freeze chunk IDs** (`data/chunk_ids.lock`).
  - [ ] **A8 · 0.2 h** — embedder 4B + reranker 0.6B + verifier 8B, all bf16, resident on the L40S (44.7 GiB); one verify call; `nvidia-smi`. If false → 0.6B embedder, then separate stages; never quantize (D-012). Measured GiB: ___
- [ ] **T5 · 2 h** Single-shot baseline: strict prompt (D12), JSON schema (D13), Batch client; 25 draft questions.
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

## Week 3 — the loop, the labels (15 h)
- [ ] **T12 · 6 h** LangGraph graph + checkpoints (D20); `re_retrieve` arm; stop rule and caps (D22); `stop_reason`; `evidence_recall@STOP` (the Idea 1 graft).
- [ ] **T13 · 8 h** Claim labels: 100 baseline + 100 post-`re_retrieve(1)`, paired on the same 100 questions, seed 1; three-class (D-010, D-003).
- [ ] **T14 · 1 h** Matrix runner: `experiments/matrix.yaml` → Batch jobs, one seed at a time (D-009) → `results/<cell>/<seed>.jsonl`.
  - [ ] **D-016 revisit** — after the matrix runner has been run by hand twice: if the run → eval → annotate sequence is still being typed out each session, log a successor to D-016 and build a `/eval-run` slash command; otherwise tick this and move on.
- [ ] **If week 3 runs over → apply the cut list below, in order.**

## Week 4 — runs, numbers, README (15 h)
- [ ] **T15 · 4 h** `ledger matrix --seed 1` for all 10 cells; inspect outputs and ledgers; then seeds 2 and 3 with `--confirm-seed-1-inspected`; local verification + local judge over all outputs; decomposition audit, 25 post-repair answers.
- [ ] **T16 · 5 h** Analysis: D26 table with CIs; paired κ on 200; decomposition error; citation accuracy; `evidence_recall@STOP` by `max_iter`; failure taxonomy on every disagreement (D27); human labels emitted as post-hoc `EVALUATOR` carrier spans linked to their verify spans via `eval/trace_annotate.py` (D-017).
- [ ] **T17 · 4 h** README with the numbers and caveats (fixed arms; 512 convention; OpenInference-not-gen_ai with the Aug 2026 date; judge/question-writer family note); CLI or notebook demo; `docs/decisions.md` updated; `ledger smoke` in CI (D28).
- [ ] **T18 · 2 h** Slack. The Idea 3 borrow needs ≥ 5 h; it will not fit — v2.

## Cut list — only if week 3 runs over; apply in this order (§5)
- [ ] 1. Graft cells `max_iter` 2 and 3 → keep `re_retrieve(1)`. Saves ~3 h, ~$3. `evidence_recall@STOP` still reported at `max_iter = 1`.
- [ ] 2. Sentence-split decomposition **arm** → 5 cells. Saves ~2 h. The decomposition **audit** stays.
- [ ] 3. Seeds 3 → 2. Saves ~1 h, ~$10. CIs widen — say so in the README.
- [ ] 4. Claim labels 200 → 150 (75 / 75, still paired). Saves ~2 h. κ CI widens from ≈ ±0.10 to ≈ ±0.12 (estimate).
- [ ] 5. Smoke-eval CI → v2 (unit tests stay). Saves ~1 h.
- [ ] 6. `rewrite` arm → keep `delete` and `re_retrieve`. Saves ~2 h.

## Never cut
- `no-repair` and `delete-all` rows (mandate 3)
- the decomposition audit (mandate 1)
- κ — verifier–human calibration
- tracing from commit one (mandate 5)
- the 20 unanswerable strict-stance controls (D12/D24)
