# docs/decisions.md — decision log

Running log of decisions and what changed when one is revisited. Newest at the bottom. Every entry: **id · date · status · decision · reason · what it changes in code · how it is validated.** When a decision is revisited, add a new entry that names the old id and says what changed and why; never edit the old entry.

Statuses: `FIXED` (follow unless the owner changes it) · `RESOLVES-ON-DATA` (a week-1 measurement selects the branch; report the number and confirm before proceeding) · `OPEN` (owner must decide; do not guess).

Rule for the build (from the owner, 2026-09-12): when you reach the code that implements one of these, say which decision you are applying and why, in one line. If evidence during the build contradicts a decision — a measurement, a library constraint, a license change — stop and report the evidence and the options. Do not work around it and do not revise it yourself.

---

## D-001 · 2026-09-12 · RESOLVES-ON-DATA · Agency mix and document count

**Decision.** Start with roughly EIA 50 / CBO 40 / GAO 30. Parse 20 documents in week 1 and measure the actual table-chunk vs prose-chunk ratio before ingesting the rest. Adjust the *remaining* ingest, not the corpus already parsed. Tolerance: 50–70% table chunks is acceptable; the 60/40 in D24 is design intent, not a threshold. Inside the band, stop tuning and move on.
**Reason.** Table density is what makes the corpus hard (D1, D14); it cannot be known until documents are parsed, and re-parsing to hit a number is wasted hours.
**Code.** `ingest/manifest.py` records agency per document; `ingest/stats.py` prints `table_chunk_share` after the first 20; the ingest CLI refuses to continue past 20 documents until the share has been reported and the owner has confirmed.
**Validation.** Week 1, T3–T4: report `table_chunk_share` and which branch (in band / below / above) it selects. Confirm before ingesting documents 21+.

## D-002 · 2026-09-12 · FIXED · Qdrant in local file mode

**Decision.** Local (embedded) file mode for v1. Docker is a v2/demo concern only.
**Reason.** ~30k vectors; zero extra services in a 60-hour project (D5).
**Code.** The Qdrant client is constructed in exactly one place, `retrieval/store.py::make_client(cfg)`, behind `vector_store.mode` in config. Nothing else imports `QdrantClient`. The swap to Docker is a one-line config change, not a search-and-replace.
**Validation.** A unit test asserts `QdrantClient` is referenced only in `retrieval/store.py`.

## D-003 · 2026-09-12 · FIXED · Partial support is a third label, collapsed for the headline

**Decision.** Human labels are three-class — SUPPORTED / PARTIAL / UNSUPPORTED — in both the κ pilot and week 3. Report: (primary) binary κ with PARTIAL folded into UNSUPPORTED — this is the README number and stays comparable between pilot and week 3; (secondary) the partial rate itself, and a three-class κ, with an explicit note that the three-class figure is **not** comparable to the binary one.
**Reason.** The repair loop is binary: route sends unsupported claims to repair and there is no third branch, so a three-class headline would be a label the system cannot act on. The partial rate feeds the D15 decomposition analysis — a high rate means claims are too coarse to verify cleanly.
**Code.** Label schema `Label ∈ {SUPPORTED, PARTIAL, UNSUPPORTED}` in `eval/labels.py`; `eval/kappa.py` computes both κ's and always emits the binary one first with the fold rule stated in the output; verifier verdicts stay binary (D13/D16 unchanged).
**Validation.** `eval/kappa.py --pilot` output includes `kappa_binary`, `kappa_3class`, `partial_rate`, and the fold note.

## D-004 · 2026-09-12 · RESOLVES-ON-DATA · Verifier input granularity, with a pre-committed tie-break

**Decision.** In the κ pilot, score the 50 claims under both input modes for each candidate verifier: (a) concatenated top-k context, (b) per-chunk scoring with max over chunks. **Tie-break, committed here before the pilot runs and not to be revised after seeing results: if the two modes are within 0.05 κ, take concatenated** (simpler, fewer verifier calls).
**Reason.** The two modes can plausibly differ on table-heavy context; the tie-break is fixed in advance so the choice cannot be fitted to the result.
**Code.** `verifier.input_mode ∈ {concatenated, per_chunk_max}` in config; `verify/run.py` implements both; the pilot script scores 2 verifiers × 2 modes = 4 κ values.
**Validation.** Week 1, T6: report the four κ values, apply the rule, state which branch it selects, confirm before week 2.

## D-005 · 2026-09-12 · FIXED · Citation granularity is the chunk ID

**Decision.** Citations are chunk IDs. Sentence spans are v2, prose-only.
**Reason.** The corpus is chosen because answers live in table cells, and D3 keeps tables atomic so the header row travels with the number. A cell has no containing sentence, so span citation would fail on exactly the chunks that are the point of the project. Chunk IDs also keep D16's citation accuracy — P(cited_support | support) — a clean set-membership check with no alignment tolerance to defend.
**Code.** `Claim.citations: list[ChunkId]`; no span offsets anywhere in v1 schemas.
**Validation.** Schema tests.

## D-006 · 2026-09-12 · FIXED · The rewrite arm sees the same context only

**Decision.** `rewrite` regenerates unsupported sentences from the identical retrieved context. It may not re-fetch cited chunks at full length.
**Reason.** Experimental validity, not preference: re-fetching would give rewrite more evidence than delete and less than re_retrieve, so the arms would differ on two dimensions instead of one.
**Code.** `repair/rewrite.py` receives the frozen `context` object from the ledger and has no retriever handle; a test asserts it makes no retrieval call.
**Validation.** Trace check: rewrite cells contain no `retrieval` span after iteration 0.

## D-007 · 2026-09-12 · OPEN (ask in week 1) · Local judge model

**Decision.** Not chosen yet. **At the κ pilot, stop and ask the owner** to check Hugging Face for the current Qwen 3.x 8B-class instruct model. Constraints: permissive license; a **different family** from both Sonnet 5 (generator) and whichever verifier the pilot selects. Once chosen, **pin the exact revision hash** in `judge.revision` and never change it mid-project — the judge runs across all week-4 outputs, so swapping it midway makes cells incomparable.
**Watch item.** If the pilot selects a Qwen-family verifier, the judge must move to a third family. (Neither pilot candidate is Qwen-based as of Stage 1 — Bespoke-MiniCheck-7B is InternLM-derived, Granite Guardian is IBM Granite — but confirm on the model cards.)
**Second watch item (Claude's flag, not the owner's).** D24 generates questions with Qwen3-8B and the plan's default judge is also Qwen3-8B. Gold answers are copied strings and numeric items use exact match, so the overlap is mild; it is recorded here so it is a choice, not an accident. Say so in the README.
**Code.** `judge.model`, `judge.revision` in config; the judge loader raises if `judge.revision` is empty.
**Validation.** Owner confirmation in week 1; revision hash present in every `results/*.jsonl` header.

## D-008 · 2026-09-12 · FIXED · Delete emits a visible marker, excluded from retained content

**Decision.** The `delete` arm emits `[unverified claim removed]` in the answer text where a claim was dropped. The marker is excluded from the retained-content measurement.
**Reason.** A silently truncated answer looks complete, which flatters the delete arm and hides the tradeoff being measured (mandate 3).
**Code.** `repair/delete.py` inserts the marker; `eval/retained.py` strips it before counting claims and tokens.
**Validation.** Unit test: retained-content of an answer with N markers equals that of the same answer with markers stripped.

## D-009 · 2026-09-12 · FIXED · One seed first, always

**Decision.** Run seed 1 for every cell, inspect outputs and ledgers, then submit seeds 2 and 3.
**Reason.** Cost is identical either way; the risk is not. A harness bug caught after three seeds costs 3× the spend and 3× the wall clock.
**Code.** `run_matrix.py --seed 1` is the only invocation that runs without `--confirm-seed-1-inspected`; seeds 2–3 require the flag.
**Validation.** The flag is logged in the results header.

## D-010 · 2026-09-12 · FIXED · The 200 claim labels are 100 baseline / 100 post-re-retrieve, paired

**Decision.** The Phase 2 §9 disagreement is accepted: 100 baseline / 100 post-re-retrieve, not 150/50. Refinement: draw both halves from **the same 100 questions, paired**.
**Reason.** The headline X→Y needs both endpoints human-measured; precision on X alone is precision where it does the least good. Pairing cancels between-question variance and tightens the CI on X−Y, which is the number actually reported.
**Code (Claude's implementation detail — confirm).** Sample 100 questions stratified table/prose. For each question: one baseline claim chosen at random; the post-repair claim is the descendant of that claim if it survived repair unchanged (same `claim_id`), the claim recorded as its replacement if it was repaired (`replaces: claim_id` in the ledger), or a random claim from the post-repair answer if it was deleted. Post-repair answers come from the `re_retrieve(1)` × `claimify` cell, **seed 1**. Paired analysis: per-question unsupported indicator difference, bootstrap over questions.
**Validation.** `eval/labels.py` refuses a label set whose two halves do not share the same 100 question ids.

## D-011 · 2026-09-12 · FIXED · Environment: AWS with $220 credits

**Decision.** AWS preferred, not mandatory. Planned: g6e.xlarge (L40S) for embedder, reranker, verifier and the local judge; S3 for corpus, parsed output and `results/*.jsonl`; a self-hosted tracing backend so tracing survives CPU-only sessions.
**Facts verified 2026-09-12.** g6e.xlarge on-demand $1.861/h us-east-1; spot $0.87–1.40/h with >20% interruption (third-party pricing mirrors); the L40S reports 44.7 GiB usable, not 48 GB — plan against 44.7. Instance has 250 GB local NVMe; use it for the Qdrant file and model cache, sync to S3.
**Budget shape (estimate).** GPU-on hours ≈ 30–35 across the four weeks (parse is CPU; generation is the API) → $56–65 on-demand. Root EBS ~$8/month while stopped. S3 negligible. That leaves ~$140 of the $220 for the tracing host and slack — **stale; recomputed in D-015** (D-013 is superseded by D-014).
**Non-AWS option that is clearly better for one component.** Week-1 GPU: if the G-family quota (below) is not approved by day 4, run the κ pilot on an hourly L40S/A100 from a non-AWS provider that has no quota step, then move to AWS. The pilot is a 2-hour job with no state that has to live on AWS.
**Day-1 blockers to raise with the owner (from the owner's own list).** (1) "Running On-Demand G and VT instances" vCPU quota is often 0 on new accounts and approval can take days; the κ pilot is week 1 day 6 — request the quota on day 1, and on day 4 without approval take the non-AWS pilot path. (2) Billing alarm at $50; confirm credits apply to EC2 + S3 in the chosen region before the first GPU hour. (3) Auto-stop on idle (CloudWatch alarm on CPU/GPU util → stop) — the instance is idle ~153 h/week.

## D-012 · 2026-09-12 · FIXED · D18 revised — verifier runs bf16; the quantized path is removed

**What changed.** Phase 2 D18 said bf16 on a 40 GB card, AWQ-int4 on 24 GB. With the 48 GB L40S there is no 24 GB branch.
**Decision.** The verifier runs bf16 in the pilot and the matrix. The AWQ-int4 code path is not written. A8 still runs in week 1 as a load test: embedder 4B bf16 (~8 GB) + reranker 0.6B (~1.2 GB) + verifier 8B bf16 (~16 GB) ≈ 25 GB on 44.7 GiB. If A8 fails, the fallback order is 0.6B embedder, then separate stages — never quantization.
**Code.** `verifier.precision` is fixed to `bf16` and validated; any other value raises.
**Validation.** A8: load all three, run one verify call, read `nvidia-smi`, record the number in `docs/plan.md`.

## D-013 · 2026-09-12 · OPEN (owner decides) · Tracing backend hosting

**Evidence.** The Phase 2 plan assumed Langfuse self-hosted via docker-compose on "a small instance." Langfuse v3 self-hosting runs six containers — web, worker, Postgres, ClickHouse, Redis, MinIO — and the vendor's own low-scale guidance plus practitioner sizing put it at ≥4 vCPU / 8 GB RAM (t3.large class, ≈$60/month on-demand). That is a quarter of the $220 for a component that does not affect a single measurement.
**Options.** (a) **Langfuse Cloud, Hobby plan** — free, no credit card, zero ops, same OTLP endpoint and `gen_ai.*` mapping as self-hosted; traces survive CPU-only sessions trivially. Check the current Hobby cap against ~10k traces / ~100k observations for the whole project. (b) **Arize Phoenix on a t3.small** (~$15/month) — single container, self-hosted, but OpenInference conventions rather than `gen_ai.*`, which changes D29's span plan. (c) **Langfuse self-hosted on t3.large** — as planned, ≈$60/month.
**Claude's recommendation.** (a). It is the clearly better non-AWS option: it costs nothing, keeps D29 intact, and removes an instance to manage. Data leaves your account, which for public-domain PDFs and your own traces is not a concern. If you want everything self-hosted, (b).
**Blocked until decided.** T1 (Langfuse endpoint in the OTLP exporter). Choose before day 1.

## D-014 · 2026-09-12 · FIXED · Tracing backend — supersedes D-013

**What changed.** D-013 recommended Langfuse Cloud Hobby (free). That was
wrong: Hobby is 50k units/month with a HARD CAP and no overage — tracing
stops when the limit is hit. A unit is every trace, observation, and score.
**Unit math (estimate, not measured).** ~15 units/query on the cheapest arm,
25–35 on re_retrieve arms. Matrix = 10 cells × 3 seeds × 150 questions =
4,500 query-runs ≈ 90k units, ~135k with dev iteration, concentrated in
week 4. Hobby would cut out mid-matrix and silently lose stop_reason,
evidence-recall@STOP, and failure-taxonomy data.
**Decision.** Arize Phoenix, self-hosted on a t3.small (~$15/mo from AWS
credits), single container, no usage cap. Instrument with OpenInference
conventions over OTLP.
**Key insight that made this cheap.** Backend and instrumentation are
separable. Both Phoenix and Langfuse ingest OTLP, and Langfuse recognizes
OpenInference natively — migrating between them is an endpoint + auth-header
change, not re-instrumentation. So this is a reversible one-line decision.
**D29 is revised.** Span attributes move from gen_ai.* to OpenInference
(llm.*). Rationale: gen_ai.* is still Development status with no tagged
release as of Aug 2026, so pinning it means pinning an unreleased spec;
OpenInference is versioned and stable. Retain the span SHAPE from D29 —
invoke_agent root, chat spans for generate/decompose/rewrite, retrieval span
per retrieve, execute_tool span per verify, one evaluation record per verdict
— and map attribute names to OpenInference equivalents.
**Rejected.** Langfuse Hobby (hard cap, fails mid-matrix — see unit math).
Langfuse Cloud Core, $29/mo (real money for a component that affects no
measurement, when credits cover a free uncapped alternative). Langfuse
self-hosted (six containers, ~$60/mo of credits, 2–3 h setup). Opik
(Apache-2.0 and a fine choice, but more containers than Phoenix for no gain
here).
**Known limitation, accepted.** Phoenix rates lowest among these tools on
scheduled scoring of live production traces and on alerting — both live in
the paid Arize AX product. Irrelevant here: evals run offline in eval/*.py
and there is no production traffic to alert on.
**Vendor note.** Dynatrace announced an agreement to acquire Arize in Aug
2026; Phoenix continues as today. Too recent to be settled — but the swap
cost is one endpoint change, so this is a cheap bet.
**Escape hatch.** If Phoenix's UI proves inadequate during week 1, switch the
OTLP endpoint to Langfuse Core. Keep the OpenInference instrumentors.
**Code.** OTEL_EXPORTER_OTLP_ENDPOINT from environment; no hardcoded
endpoint. Instrumentation lives behind one module so the convention set is
swappable.
**Validation.** A5, week 1: first traced call renders in Phoenix with token
counts. If OpenInference attributes don't render as expected, that is the
signal to take the escape hatch — decide in week 1, not week 4.

## D-013 · status 2026-09-13 · SUPERSEDED by D-014 (tracing backend is Phoenix self-hosted, OpenInference over OTLP — instance size per D-015; the D-013 recommendation of Langfuse Cloud Hobby was withdrawn because of its hard 50k-unit cap). Original entry left unedited.

## D-015 · 2026-09-13 · FIXED · Phoenix instance sizing and corrected budget — revises D-014 (instance) and D-011 (budget)

**Decision.** Phoenix runs on a **t3.medium** (2 vCPU / 4 GiB), not the t3.small named in D-014.
**Reason.** Phoenix idles around half a gigabyte and its SQLite store handles ~135k spans on disk without trouble, but ingest is bursty — Batch results land in blocks and the exporter flushes thousands of spans at once. 2 GiB leaves no headroom for the week-4 UI loading traces alongside that burst. The swap-plus-memory-alarm alternative was rejected: it spends week-2 attention on a $15 question.
**Rejected.** t3.small with swap + a 20 GB gp3 volume + an 80% memory alarm.
**Budget, recomputed (all estimates; prices are on-demand us-east-1).** GPU: 30–35 h on g6e.xlarge at $1.861/h (verified 2026-09-12) → $56–65. g6e root EBS (~100 GB gp3) while stopped, ~4 weeks → $8–10. t3.medium at ~$0.0416/h (from memory, unverified) × 24 h × ~28 days → $28–30, plus its ~20 GB gp3 → ~$2. S3 (corpus, parsed output, results) → under $1. **Committed ≈ $95–107. Remaining slack ≈ $113–125 of $220.** The API generation spend (≈ $45–90) is the separate $200 API budget and is not in these figures. The non-AWS κ-pilot fallback (D-011), if used, costs $3–5 outside AWS.
**Code.** None; infrastructure only. Recorded in the tracker's environment panel.
**Validation.** CloudWatch memory metric on the t3.medium during week 4; if it exceeds 80% the entry gets a successor, not an edit.

## D-016 · 2026-09-13 · FIXED · No project skills or slash commands in v1

**Decision.** None built for v1.
**Reason.** The eval workflow is already five CLI subcommands (`matrix`, `eval`, `kappa`, `audit-decomp`, `smoke`); a slash command wrapping them before they exist would encode guesses about a sequence nobody has run. The instrumentation convention is one rule plus one module (`tracing/otel.py`), already in CLAUDE.md — a skill would restate it and cost context every session.
**Revisit trigger.** At T14, after the matrix runner has been run by hand twice. If the run → eval → annotate sequence is still being typed out each session, a slash command earns its place then; that revisit is a `docs/plan.md` checkbox.
**Rejected.** Building the command now (premature). An instrumentation skill (duplicates CLAUDE.md).
**Rule this entry establishes.** Process decisions — tooling, sizing, workflow — are logged on the same rule as pipeline decisions: a decision is not made until it is in this file.

## D-017 · 2026-09-13 · FIXED · Evaluation records use the OpenInference annotations/evaluations mechanism, not the Phoenix client — revises D29 (evaluation transport) and strengthens D-014

**Question.** D29 said per-verdict evaluation records are "Phoenix span evaluations, written in batch by `eval/trace_annotate.py`" — a Phoenix-proprietary write path that would make D-014's escape hatch cost a rewrite. Can the standard OpenInference mechanism carry the same payload (name, label, score, explanation = evidence_ids) attached to the verify span?
**Finding (spec fetched 2026-09-13, https://arize-ai.github.io/openinference/spec/annotations.html).** Yes. Span-scoped feedback is `evaluations.<i>.evaluation.{name, score, label, explanation, annotator_kind, identifier, metadata}` (`annotations.*` is the equivalent form; consumers SHOULD treat both as equivalent). Two transports are defined: **inline** — set on the target span while it is open; **post-hoc** — ended spans are immutable, so feedback goes on a new carrier span with `openinference.span.kind = "EVALUATOR"` and **exactly one OpenTelemetry Span Link** to the target span, one carrier per target; parentage must not be used to identify the target. `openinference-instrumentation` ships `get_evaluation_attributes(...)` to flatten these (documented on the 0.1.57 PyPI page).
**Decision.**
1. **Verifier verdicts are inline.** The verify span is open when the verdict exists, so `tracing/otel.py::record_verdict` sets `evaluations.0.evaluation.*` on it at verdict time: `name="claim_support"`, `label` (SUPPORTED/UNSUPPORTED), `score`, `explanation` = JSON list of `evidence_ids`, `annotator_kind="LLM"`, `identifier` = `<verifier model>@<revision>`, `metadata` = `{claim_id, input_mode, threshold, cited_support}`. There is no batch step for verdicts any more.
2. **Human labels and any re-scoring are post-hoc carriers.** `eval/trace_annotate.py` emits one `EVALUATOR` span per target verify span with one Span Link to it, `annotator_kind="HUMAN"` (week-3 labels, three-class per D-003) or `"CODE"`, over OTLP only. The ledger row gains `trace_id` and `span_id` so targets can be linked without a backend query.
3. **`PROMPT` span kind is not adopted in v1** — prompts are versioned in `configs/`; nothing is gained by tracing template invocations separately.
**Why it matters for D-014.** The escape hatch (endpoint → Langfuse Cloud Core) is now an endpoint change for evaluation records too, not just spans. `eval/trace_annotate.py` has no Phoenix dependency.
**Rejected.** Phoenix client `add_span_annotation` / `log_span_annotations` (proprietary write path; breaks the reversibility claim — the caveat the user asked to surface if we had kept it). The `gen_ai.evaluation.result` event (gen_ai.* is the rejected convention per D-014; the spec notes gateways can translate it from the OpenInference form anyway, so nothing is lost).
**Known risk, tested at A5.** The spec fixes the *producer* form; whether the backend *renders* it is backend behaviour. A5 now checks two things on the first traced call: (a) an inline `evaluations.*` verdict appears in Phoenix's Evaluations panel on the verify span; (b) a post-hoc `EVALUATOR` carrier with a Span Link appears against the *linked* verify span, not merely as a stray span. If (b) fails in Phoenix, the successor entry keeps the standard carrier form on the wire and adds a Phoenix-side import for display only — the data stays portable; the caveat is confined to the UI.
**Pins.** `openinference-semantic-conventions==0.1.29` (latest per the conda-forge feed, ~1 Sep 2026 — confirm on PyPI at T1 and correct here if different); `openinference-instrumentation>=0.1.57` (for `get_evaluation_attributes`); `arize-phoenix` version recorded at T1 in `docs/plan.md` A5.
**Code.** `tracing/otel.py`: `record_verdict(span, verdict)`, `emit_posthoc_evaluation(target: (trace_id, span_id), annotation)`; ledger row `+trace_id, +span_id`; `eval/trace_annotate.py` imports nothing from `phoenix`. Unit tests: a carrier has exactly one link; verdict attributes are present on the verify span before it ends; `import phoenix` is absent from `eval/` and `tracing/`.
**Validation.** A5 (a) and (b); the D28 import test.

