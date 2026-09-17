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
**Status 2026-09-16.** Pairing rule confirmed by the owner as written (E5); branch recorded per pair, 3a/3b split, pre-committed interpretation rule, and the open T12 successor-matching requirement are in **D-027**. Body above unedited.

## D-011 · 2026-09-12 · FIXED · Environment: AWS with $220 credits

**Decision.** AWS preferred, not mandatory. Planned: g6e.xlarge (L40S) for embedder, reranker, verifier and the local judge; S3 for corpus, parsed output and `results/*.jsonl`; a self-hosted tracing backend so tracing survives CPU-only sessions.
**Facts verified 2026-09-12.** g6e.xlarge on-demand $1.861/h us-east-1; spot $0.87–1.40/h with >20% interruption (third-party pricing mirrors); the L40S reports 44.7 GiB usable, not 48 GB — plan against 44.7. Instance has 250 GB local NVMe; use it for the Qdrant file and model cache, sync to S3.
**Budget shape (estimate).** GPU-on hours ≈ 30–35 across the four weeks (parse is CPU; generation is the API) → $56–65 on-demand. Root EBS ~$8/month while stopped. S3 negligible. That leaves ~$140 of the $220 for the tracing host and slack — **stale; recomputed in D-015** (D-013 is superseded by D-014).
**Non-AWS option that is clearly better for one component.** Week-1 GPU: if the G-family quota (below) is not approved by day 4, run the κ pilot on an hourly L40S/A100 from a non-AWS provider that has no quota step, then move to AWS. The pilot is a 2-hour job with no state that has to live on AWS.
**Status 2026-09-14.** G-family quota **approved: 8 vCPU, us-east-1**, effective immediately. That is exactly one g6e.xlarge (4 vCPU) with **no room for a concurrent second GPU instance and no headroom to step up to g6e.2xlarge (8 vCPU) if A8 comes back tight** — a second quota request would be needed first. Every GPU task in the plan is sequential, so 8 vCPU is sufficient. The day-4 non-AWS pilot fallback below is **moot** (kept, not deleted). Billing alarm at $50 set; credits confirmed for EC2 and S3 in us-east-1. Idle auto-stop pending until the g6e launches at T4. **Budget: the D-015 figures are superseded by D-023 §7 (actuals for the tracing host).**
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

## D-018 · 2026-09-14 · FIXED · OpenInference pins corrected — revises D-017 (pins only)

**What changed.** D-017 pinned `openinference-semantic-conventions==0.1.29` from a conda-forge feed and asked for confirmation on PyPI at T1. Verified 2026-09-14 on PyPI: latest is **0.1.37** (2026-09-10); 0.1.29 dates from 2026-04-22.
**Evidence.** (1) The 0.1.29 wheel has **no `evaluations` attribute constant** (`SpanAttributes.EVALUATIONS` absent; `EVALUATOR` span kind present) — the inline-verdict mechanism D-017 rests on does not exist in it. (2) No `openinference-instrumentation` release that ships `get_evaluation_attributes` accepts 0.1.29: 0.1.57 (2026-08-07) floors at `semantic-conventions>=0.1.31`, 0.1.58–0.1.62 at `>=0.1.33`, 0.1.63 (2026-09-10) at `>=0.1.37`. The D-017 pair `==0.1.29` + `>=0.1.57` cannot resolve.
**Decision.** Pin `openinference-semantic-conventions==0.1.37` and `openinference-instrumentation==0.1.63` (exact, so the attribute keys the tests assert against cannot drift under a floor). Verified in the 0.1.37 / 0.1.63 wheels: `evaluations.<i>.evaluation.{name,score,label,explanation,annotator_kind,identifier,metadata}`, `OpenInferenceSpanKindValues.EVALUATOR`, `OpenInferenceAnnotatorKindValues.{HUMAN,LLM,CODE}`, `llm.token_count.prompt_details.cache_{read,write}`, `reranker.top_k`, `retrieval.documents`, `tool.name`, `openinference.project.name`, and `get_evaluation_attributes(evaluations=[...], scope="span")`. The rest of D-017 is unchanged.
**Rejected.** Keeping 0.1.29 (mechanism absent; unresolvable with the instrumentation floor). Leaving instrumentation as a floor `>=0.1.57` (resolves to 0.1.63 today but lets a later release move attribute keys under the tests).
**Code.** `pyproject.toml` pins; `ledger/tracing/otel.py` imports the keys from the package, never spells them from memory. References corrected in `docs/plan.md` A5, `docs/architecture.md` D29, `CLAUDE.md` pitfalls.
**Validation.** `uv.lock` resolves; `tests/test_otel.py` asserts the flattened keys and the one-Span-Link carrier; A5 (a)(b)(c) still pending on the Phoenix endpoint — `arize-phoenix` server version to be recorded then (PyPI latest on 2026-09-14: 20.12.0).

## D-019 · 2026-09-14 · FIXED · Sampling parameters removed from the API — "seed" is an independent run at default sampling; seed count OPEN pending a variance probe

**What happened.** `scripts/a5_probe.py` raised `TypeError: Messages.create() got an unexpected keyword argument 'temperature'` (anthropic 1.5.0).
**Evidence (verified 2026-09-14).** (1) SDK: `inspect.signature(Anthropic().messages.create)` in anthropic 1.5.0 has no `temperature`/`top_p`/`top_k` and no `**kwargs`; the removal is anthropic 1.0.0 (2026-08-20), MIGRATION.md "Removed request parameters". (2) **Batch path**: `messages.batches.create` takes `requests=[Request(custom_id, params=MessageCreateParamsNonStreaming)]`; the `params` TypedDict has no sampling keys either, **but a TypedDict is not enforced at runtime and the SDK forwards unknown keys** — a batch request can put `temperature` on the wire. (3) API: Claude Sonnet 5 returns 400 for any non-default `temperature`/`top_p`/`top_k`; Opus 4.7+ rejects the field outright. The Messages API reference still documents `temperature` with default 1.0 — the docs lag the SDK and the model behaviour; the SDK and the 400 win. (4) The same removal applies on Bedrock, Vertex and Foundry — not recoverable by changing provider.
**Scope.** Both the sync path and the Batch path (T14's matrix runner is Batch-only). Because the batch path forwards unknown keys, the block must be ours: it lives in config validation, not in the SDK.
**Decision.**
1. `generator.temperature` removed from `configs/base.yaml`; `a5_probe.py` sends no sampling parameter.
2. `ledger/config.py` raises an **explicit** `ValueError` naming D-019 if `temperature`, `top_p` or `top_k` appears anywhere in the config tree — before `extra="forbid"` could turn it into a "field not permitted" error that a later session would read as a missing schema field and "fix" by adding the key. The message says the parameter was removed from the API, not from our config.
3. **"Seed" is redefined**: an independent sampled run at the model's default adaptive sampling — not `temperature: 0.3`. `docs/evaluation.md` §3, `docs/architecture.md` §10 and the README wording are corrected. The three-seed design in D26 rested on a parameter that no longer exists.
4. **Seed count and the D26 table are NOT changed in this entry.** A variance probe is added to T5 (3 runs × 25 draft questions; numeric exact-match agreement, digit-level disagreement as its own line, abstention consistency, citation-set stability, answer-token spread). The seed decision waits for the first run where unsupported-claim rate exists (T9/T11) — a successor entry records it.
**Why the digit line is separate.** D12 tells the generator to copy numbers verbatim and D14 lists numeric transcription as a hallucination mode; `temperature: 0.3` was implicitly part of that mitigation. If digits drift between runs at default sampling that is a D12/D14 problem, not a seed-count problem, and must not be averaged into a variance figure.
**Rejected.** `extra_body={"temperature": 0.3}` (Sonnet 5 400s on non-default values; it only works on models this project does not use). Switching to a 4.6-line model to keep temperature (D11 chose Sonnet 5 for generator quality; a weaker generator inflates the baseline rate). Silently dropping to one seed now (the budget/validity question needs the measured spread first).
**Code.** `ledger/config.py::_reject_sampling_keys` + `Config._no_sampling_parameters`; tests `test_sampling_parameters_rejected_explicitly`, `test_base_config_has_no_sampling_keys`.
**Validation.** T5 variance probe numbers in `docs/plan.md`; successor entry at T9/T11 fixes the seed count.

## D-020 · 2026-09-14 · FIXED · D-007's "judge loader raises" means the use site, not config loading

**Question.** D-007 says "the judge loader raises if `judge.revision` is empty". Read literally as the *config* loader, every command would fail while D-007 is open — including `ledger pilot`, which selects the verifier that determines which family the judge may come from. That is a deadlock.
**Decision.** `load_config` accepts empty `judge.model` / `judge.revision`. `JudgeConfig.require_pinned()` raises (naming D-007) and is called by whatever loads the judge model (T15/T16), never earlier. The revision hash is still pinned once and never changed.
**Rejected.** Raising in `load_config` (the deadlock above). A default placeholder revision (would let a run proceed with an unpinned judge, which is what D-007 exists to prevent).
**Code.** `ledger/config.py::JudgeConfig.require_pinned`; test `test_judge_requires_pinned_revision`.
**Validation.** Every `results/*.jsonl` header carries the revision (D-007 unchanged).

## D-021 · 2026-09-14 · FIXED · CLI flag rule restated as a principle: run-scoping flags only

**Question.** CLAUDE.md's command block showed `ledger questions --n 200 --controls 20` while its rule said "nothing numeric on the command line except `--seed`, `--n`, `--limit`". One flag falsified the sentence.
**Decision.** The rule's intent is *no tuning parameters on the command line*. Restated: "Only run-scoping flags are passed on the command line (`--seed`, `--n`, `--limit`, `--controls`). Every tuning parameter lives in config." `--controls` is registered as in the block; `questions.controls: 20` is the config default the flag overrides. A future run-scoping flag extends the list; a tuning value never becomes a flag.
**Rejected.** Dropping `--controls` (the block is the contract later sessions copy from). Leaving the sentence as an enumeration (the next flag falsifies it again).
**Code.** `ledger/cli.py` (`questions --n --controls`); CLAUDE.md rule text.
**Validation.** `tests/test_cli.py::test_all_subcommands_registered`, `test_bodies_not_implemented`.

## D-022 · 2026-09-14 · FIXED · Phoenix does not resolve Span Links: post-hoc carriers render as separate root traces — accepted; qualifies D-017

**Observed (local smoke test, arize-phoenix 20.12.0, not A5).** Checks (a) and (b) pass: the query→generate→verify trace renders with usage-derived cost, and the inline `evaluations.0.evaluation.*` verdict appears on the verify span with all fields. Check (c) is **partial**: the `EVALUATOR` carrier stores every `evaluations.*` attribute and exactly one Span Link correctly on the wire, but Phoenix shows it as a **separate root trace** — "Annotations 0" on the carrier, no Links tab, the `human_label` column empty on the query trace. Phoenix does not resolve OpenTelemetry Span Links into annotations.
**Decision.** Accept (c) as observed. The wire form stays as D-017 specifies (standard carrier, one Span Link, over OTLP, no `phoenix` import). No Phoenix-side display import.
**Why it is cheap, not lossy.** Human labels are read by `eval/kappa.py` from label files, so κ, the paired analysis and the D26 table are unaffected. What keeps the two record kinds separable in any query without link resolution is `annotator_kind`: inline verdicts are `LLM`, carriers are `HUMAN` (or `CODE` for re-scoring). Carriers additionally carry `rag.record_type` (`human_label` / `code_label`; root query spans carry `query`) so root-trace lists can filter them out.
**Cost, stated for week 4.** D27 triage loses one convenience: the human label is not shown beside the verifier verdict on the verify span. Week 3 emits ~200 carriers as root traces into the same list as ~150 query traces; the triage view filters on `rag.record_type = "query"` and looks the label up by `(trace_id, span_id)` from the ledger row / label file. This is the degradation being conceded.
**Cosmetic, also accepted.** Phoenix's "Total Cost" column shows $0 because it derives cost from its own model-pricing table, which does not know `claude-sonnet-5`. D30's cost is `rag.cost_usd` on the AGENT root span, computed from API usage fields × config price (batch-aware, unit-tested). No Phoenix pricing config is added.
**Rejected.** Phoenix's annotations API (`add_span_annotation` / `log_span_annotations`) — would spend D-017's no-`phoenix`-import property and with it D-014's one-line escape hatch. A second TracerProvider routing carriers to a separate project (evaluated at the owner's request, see the session report; not adopted: it is more than a config change and splits labels from verdicts across projects, which is a tradeoff the `rag.record_type` filter avoids).
**Re-check triggers (two).** (1) Taking the D-014 escape hatch to Langfuse Cloud Core — re-run the probe there; Langfuse may resolve Span Links. (2) Any `arize-phoenix` version upgrade — link resolution is backend behaviour and may land in a later release. Either way the wire form does not change; only the rendering caveat does.
**Code.** `ledger/tracing/otel.py`: `RAG_RECORD_TYPE`, `RECORD_TYPE_QUERY`, `RECORD_TYPE_BY_ANNOTATOR`; tests `test_carrier_record_type`, `test_cost_lands_on_root_query_span`, `test_verdict_metadata_is_json_string_on_the_wire`.
**Validation.** A5 on the t3.medium uses the amended (c) criterion in `docs/plan.md`.
**Status 2026-09-16.** A5 ran and passed on the **t3.small** host `ledger-phoenix` (D-023), Phoenix v20.12.0, under the amended (c) criterion. Body above unedited.

## D-023 · 2026-09-16 · FIXED · Tracing host as built — revises D-015 (instance, budget); qualifies D-014 (endpoint per host) and D-022 (pinned server)

**Host.** EC2 `ledger-phoenix`, `i-0af5e7bc04d2667bf`, us-east-1, default VPC `vpc-0f3297a449901c109`, Amazon Linux 2023, 20 GB gp3 root, credit specification **Standard** (not Unlimited — no burst overage billing). Docker 25.0.16. Container: `docker run -d --name phoenix --restart unless-stopped -p 6006:6006 -p 4317:4317 -v /home/ec2-user/phoenix-data:/root/.phoenix arizephoenix/phoenix:20.12.0`. Phoenix runs with **authentication disabled and TLS disabled**; the security group is the only access control.

**1. Sizing — t3.small, not the t3.medium D-015 chose; deferred to a measurement.** D-015's argument (bursty exporter flushes when Batch results land in week 4; 2 GiB leaves no headroom for the UI) was a prediction, not a measurement; neither side had data. Mitigations applied before Docker: 2 GiB swapfile (`/swapfile`, `chmod 600`, `mkswap`, `swapon`, fstab `/swapfile none swap sw 0 0` — survives reboot; `free -h`: Mem 1.9 Gi, Swap 2.0 Gi). **Measured idle baseline: 524 MiB / 1.865 GiB = 27.44 %, 0.29 % CPU** — matches the ~0.5 GiB prediction; ~1.3 GiB headroom before swap. This is the comparison point. **Resize trigger:** at end of week 3, before the T15 matrix run, read `/home/ec2-user/phoenix-mem.log` and report the peak `MemPerc`; near the ceiling → stop instance, change type to t3.medium, start (~5 min; EBS volume and all trace data preserved; the Elastic IP means the address and `OTEL_EXPORTER_OTLP_ENDPOINT` do not change). Checkbox lives in `docs/plan.md` end of week 3. Cost ~$15/mo vs ~$30; the saving is not the point, not guessing is.

**2. Monitoring — cron, CloudWatch agent rejected.** `cronie` installed (absent on AL2023 by default), `crond` enabled; every 5 min: `*/5 * * * * /usr/bin/docker stats --no-stream --format '{{.MemUsage}} {{.MemPerc}} {{.CPUPerc}}' phoenix >> /home/ec2-user/phoenix-mem.log 2>&1`. Yields a peak and a distribution, not a snapshot; the burst that decides the resize is transient. **Rejected:** CloudWatch memory alarm at 80 % — EC2 publishes no memory metric natively; it needs the CloudWatch agent plus an IAM role (20–30 min) for one scheduled load event. Not done: logrotate (~60 B/sample every 5 min ≈ 500 KB over four weeks — negligible); and the cron has **not yet been confirmed writing**. Likely failure mode if the log is empty or full of errors: cron runs without the interactive shell's group membership, so `ec2-user` may not be effectively in the `docker` group — check that first, not the schedule. Also unverified against an actual reboot: `systemctl is-enabled docker` / `crond` (both `enable --now` were run). Checkboxes in `docs/plan.md`.

**3. Elastic IP.** `54.160.244.106`, allocation `eipalloc-003a67ffced02e689`, association `eipassoc-048ece2a610caf49a`, DNS `ec2-54-160-244-106.compute-1.amazonaws.com`, Amazon pool us-east-1. The original auto-assigned `44.200.40.244` is released and unrecoverable (both A5 runs were made against it; the endpoint was re-set afterwards and the 4 traces re-verified). **What it fixes:** the server's address survives stop/start, so the week-3 resize does not require re-setting the endpoint. **What it does NOT fix:** access. Inbound 6006 is "My IP"; if the owner's home IP changes Phoenix is unreachable and the fix is editing that rule — two different failure modes. **Teardown obligation:** an EIP not attached to a running instance is billed hourly; release is in the `docs/plan.md` teardown checklist.

**4. Image pin.** `arizephoenix/phoenix:20.12.0`, digest `sha256:440c03af939e775343788a4e9e0fed72df6fd87ee287c771e94494ab3037c790`. The tag resolved to the same digest as `:latest` — `latest` had not drifted, so the pin locks what was tested rather than changing it; nothing new was pulled. Container stopped, removed, recreated from the pinned tag; version re-confirmed v20.12.0 from `docker logs`. **Consequence:** changing the server version re-opens D-022's (c) acceptance (Span Link rendering is backend behaviour) and requires re-running A5.

**5. Persistence — verified as a result, not a step.** All 4 traces survived the destroy-and-recreate on the `/home/ec2-user/phoenix-data` volume mount and survived the IP change. This is the mechanism the whole week-4 dataset depends on; it was untested before 2026-09-16. Backup is D-026.

**6. Security posture.** `ledger-phoenix-sg` inbound, final: 22/tcp from My IP (`69.200.34.225/32`) and from prefix list `com.amazonaws.us-east-1.ec2-instance-connect`; 6006/tcp from My IP; 6006/tcp from **sg `ledger-gpu-sg`** (SG-to-SG). `ledger-gpu-sg` exists with no inbound rules; it is attached to the g6e at T4 and referenced as a source. Outbound default (all) on both — the g6e needs egress for HF, `uv sync`, the Anthropic API, S3 and Phoenix. Traces contain prompts and retrieved chunks: **never widen inbound to 0.0.0.0/0.** Why the SG-to-SG rule exists: from T4 the embedder, reranker and verifier run on the g6e, so every verify span in the κ pilot originates there; a My-IP-only rule would drop those exports silently — the same class of failure as the `/v1/traces/v1/traces` 405. **Correction that makes the rule sufficient:** an SG source reference matches only traffic arriving on **private** addresses inside the VPC. If the g6e pointed at the Elastic IP, packets would leave via the internet gateway and return with the g6e's public source address — matching neither rule — and be dropped silently (empty κ pilot). Therefore **the endpoint differs by host**: laptop → `http://54.160.244.106:6006` (Elastic IP); g6e → `http://172.31.68.230:6006` (**private IP**, stable across stop/start, so it survives the week-3 resize). The g6e must launch in `vpc-0f3297a449901c109` or the SG reference cannot match at all. This is exactly what D-014's "endpoint from environment, never hardcoded" protects: the same code emits to a different address depending on where it runs.

**7. Budget — supersedes D-015's ≈$95–107 committed / ≈$113–125 slack.** Instance rates are list prices (on-demand us-east-1; from memory, unverified against the pricing page — the same standing as D-015's t3.medium rate); everything else is an estimate. GPU: g6e.xlarge 30–35 h × $1.861/h → **$56–65**. g6e root EBS (~100 GB gp3) while stopped, ~4 weeks → **$8–10**. Tracing host: t3.small $0.0208/h × 24 h × 28–30 d → **$14–15**; its 20 GB gp3 at $0.08/GB-mo → **~$1.6**; public IPv4 $0.005/h × 24 × 28–30 d → **~$3.4**. S3 → **< $1**. EBS snapshots (D-026) → **< $1**. **Committed ≈ $84–96. Remaining slack ≈ $124–136 of $220.** The API generation spend (≈$45–90) is the separate $200 API budget. **The Elastic IP is not a new cost line:** AWS bills every public IPv4 address, auto-assigned included, so an EIP on a running instance costs the same as the address it replaced; the IPv4 line above is a correction to D-015 (which omitted it), not a regression caused by the EIP. The non-AWS κ-pilot fallback is moot (D-011 status).

**Rejected (this entry).** t3.medium now (a prediction, not a measurement — deferred, not overruled). Unlimited credit spec (burst overage billing). CloudWatch memory alarm (above). `:latest` image (untestable drift; D-022's acceptance is version-specific). Widening inbound to 0.0.0.0/0. Pointing the g6e at the Elastic IP (silently dropped by the SG-to-SG rule).
**Code.** None; `CLAUDE.md` environment + pitfalls (endpoint per host; pinned server version); `docs/architecture.md` D29 instance line.
**Status 2026-09-17 — §7 rates verified.** g6e.xlarge $1.8610/h and t3.small $0.0208/h (on-demand Linux us-east-1) retrieved from third-party pricing aggregators (DoiT, DevZero, Vantage, Holori), not AWS's own page; public IPv4 $0.005/h per AWS's announcement of the charge effective 2024-02-01, not re-checked against a current AWS page; gp3 $0.08/GB-month from the AWS Pricing Calculator (AWS primary; estimate `3d00189832a7d03fe497a22b4c16cb88a0fe12ce`: 1 × 20 GB × 730 h, no snapshots = $1.60/mo; `vol-06d56753ddf4149a0` is at the included 3,000 IOPS / 125 MB/s, no provisioned-performance charge). All match §7; **committed and slack unchanged.**
**Validation.** A5 **passed** on this host (Phoenix v20.12.0; sync trace `fd24cb3bde5d321dbb78e88eb03f1c83`, batch trace `9bff4c724852c3cc2363df2df2475b9e`; batch cost exactly half of sync on identical usage). Next-session checkboxes: mem log writing, docker/crond enabled. Week-3 resize check. First traced call from the g6e before T6.

## D-024 · 2026-09-16 · FIXED · Post-hoc carriers stay in the `ledger` project; no separate `ledger-labels` project — qualifies D-022

**Question (owner, 2026-09-14).** Route human-label carriers to a separate Phoenix project (e.g. `ledger-labels`) via the resource attribute, so they leave the root-trace list?
**Cost.** Phoenix routes by the resource attribute `openinference.project.name`, and a `Resource` is fixed per `TracerProvider`. A second project therefore means a second `TracerProvider` in `tracing/otel.py` — its own resource, exporter/processor and shutdown, plus a second tracer handle used only by `emit_posthoc_evaluation` (~15 lines). Not a config change. Small in code; the tradeoff is the objection.
**Tradeoff.** Labels would land in `ledger-labels` while the verdicts they qualify stay in `ledger`. Phoenix has no cross-project view, so D27 triage would need two tabs and a `(trace_id, span_id)` lookup — strictly worse than filtering one project on `rag.record_type`, which already removes carriers from the root-trace list (D-022). Splitting buys nothing the attribute filter does not.
**Decision.** Not adopted. One project, one provider; carriers are filtered by `rag.record_type` (`human_label` / `code_label`; query roots carry `query`).
**Rejected.** Second provider / separate project (above). A span processor that rewrites the resource per span (resources are immutable on `ReadableSpan`; would need exporter-level cloning — fragile, and still splits the projects).
**Re-check trigger.** The same two as D-022: Langfuse escape hatch, Phoenix upgrade — if either resolves Span Links, the question is moot; if either adds a cross-project view, revisit.

## D-025 · 2026-09-16 · FIXED · Batch wall-clock is a sequencing constraint: attention time ≠ elapsed time

**Evidence.** The single-request A5 batch probe (`msgbatch_01PrjXG9p42ngysQqywneaFv`) took materially longer than the sync call. Anthropic's Batch SLA is up to 24 h, most batches under 1 h, no priority for small jobs. Results expire after 29 days.
**Where it bites.** D-009 requires seed 1 → inspect → seeds 2 and 3, so **T15 is three sequential batch waits**; its "4 h" is attention time. Every other Batch-backed task carries one wait each: T5 (25 draft baseline), T8 (decomposition), T10 (rewrite arm), T12 (re_retrieve regeneration inside the loop), `ledger smoke` (D28, so a CI smoke gate would block on batch latency — one more reason it is cut #5).
**Decision.** `docs/plan.md` distinguishes attention hours from elapsed windows on T15 and notes the per-task wait elsewhere. **Assumed elapsed window for T15: 3 calendar days** (three waits at ≤ 24 h each, submitted at the start of a sitting, inspected at the next). **If a batch runs long:** a batch still `in_progress` after 24 h is escalated to the cut list — apply cut #1 (graft cells) and #3 (seeds 3 → 2) before touching anything else; an `expired` result is resubmitted, never re-keyed by position (`(cell, seed, question_id)` keys). The matrix runner (T14) must be resumable across sittings: submit → persist batch ids → exit; a later invocation polls and collects.
**Rejected.** Running seeds concurrently to save elapsed time (violates D-009). Synchronous calls in the matrix runner to avoid the wait (D28 guard; 2× cost).
**Validation.** T15 line in `docs/plan.md`; the T14 runner's resume path is a unit test at T14.

## D-026 · 2026-09-16 · FIXED · Trace dataset backup: EBS snapshots at three points — now, before T15, before teardown

**Problem.** `/home/ec2-user/phoenix-data` — by week 4 the evidence behind every README number — sits on one unsnapshotted EBS root volume.
**Options costed.** (a) **EBS snapshot**: one console action, no IAM role; $0.05/GB-month of *used* blocks, incremental after the first — a ~3–4 GB used root → ~$0.20/month per snapshot chain; restore = create volume from snapshot, ~minutes. (b) **Weekly `aws s3 sync`** of the directory: S3 storage negligible (~$0.023/GB-month) but needs an IAM instance profile with S3 write (the instance has none), a bucket, and a cron entry — ~20 min of setup and a second moving part; a sync of SQLite files mid-write can also capture an inconsistent state unless Phoenix is stopped first.
**Decision.** (a), the owner's inclination — confirmed. Snapshots at three points: **(1) now** — the four A5 traces plus the verified instrumentation are already worth more than the cents a snapshot costs, and the first snapshot is the one that establishes the chain; **(2) immediately before T15**, when the week-3 data becomes irreplaceable; **(3) before terminating `ledger-phoenix`** at teardown. Take the pre-T15 and teardown snapshots with the container stopped (`docker stop phoenix`, snapshot, `docker start phoenix`) so the SQLite files are quiescent; the "now" snapshot may be taken hot (nothing is being written).
**Rejected.** S3 sync (IAM + bucket + cron for no consistency benefit). A single snapshot only at teardown (leaves week 3 unprotected during the T15 burst that D-023 says may need a resize).
**Validation.** Snapshot ids recorded on the `docs/plan.md` checkboxes.

## D-027 · 2026-09-16 · FIXED · D-010 pairing rule confirmed (Option B: branch recorded per pair) with a pre-committed interpretation rule; successor matching is an open T12 requirement

**Confirmed (owner, E5).** The pairing rule as D-010 specified it: for each of 100 stratified questions, one random baseline claim from the no-repair answer; the post-repair claim from the `re_retrieve(1) × claimify` cell, seed 1, is (1) the same `claim_id` if the claim survived unchanged, (2) the claim recorded in `replaces` if it was repaired, (3) a random claim from the post-repair answer if the baseline claim has no successor. Initial generation is shared across arms within a seed (`docs/evaluation.md` §5), so baseline claim ids exist in the re_retrieve cell.
**Option B — the branch is recorded on the label record.** A `pair_branch` field is written **when the pair is selected**, by `eval/labels.py`, not by the labeller. Branch 3 is split: **3a** — terminal delete (the claim was still unsupported at STOP and the arm's terminal action removed it, D22): a real repair outcome; **3b** — no successor found (the claim was lost in regeneration): bookkeeping loss. `eval/labels.py` emits the four counts (1, 2, 3a, 3b).
**Pre-committed interpretation — fixed before the number exists.**
- Headline X→Y: question-level paired bootstrap over all 100 pairs, **always**. Pairing is on questions (§7) and holds under every branch.
- All four branch counts are printed next to X→Y in the D26 table.
- branch 3 (3a+3b) ≤ 20 → the README may use claim-level language ("unsupported claims were repaired").
- branch 3 > 20 → answer-level language only ("post-repair answers contain fewer unsupported claims"), with the branch-3 n stated.
- 3b > 5 → reported as a successor-matching defect in the D27 taxonomy discussion, regardless of the total.
- Branches 1+2 alone may appear as a secondary line labelled **CONDITIONAL**. It is selection-biased (deletion correlates with being unsupported) and is never presented as the effect.
**Open requirement on T12 — successor matching is specified nowhere.** `regenerate(question, chunks, ledger)` (D21) produces a new answer that is re-decomposed into new claims; neither D21 nor `claims/ledger.py` says how a surviving claim keeps its `claim_id` or how `replaces` is populated. Without a mechanism, branches 1–2 cannot occur and branch 3 approaches 100. **T12 must define successor matching, and a T12 unit test must show that an unchanged claim keeps its `claim_id` and a regenerated claim carries `replaces`.** The mechanism is not designed here; candidates and their failure modes are in the 2026-09-16 session report and are to be evaluated at T12.
**Rejected.** Switching the headline to an unpaired bootstrap when branch 3 is high — discards valid question-level pairing for no correctness gain. Letting the labeller judge the branch (introduces a judgement into what is a bookkeeping fact).
**Code.** `eval/labels.py`: `pair_branch ∈ {1, 2, 3a, 3b}` on every label record, written at selection; branch counts in its output; the D-010 refusal on unpaired halves unchanged. T12: successor matching + test.
**Validation.** Branch counts beside X→Y in `reports/results.md`; the T12 test.
**Status 2026-09-17.** The T12 test gains negative cases (different entity not matched; one-to-one) and an open qualifier-correction decision — **D-029**. Body above unedited.

## D-028 · 2026-09-16 · FIXED · `ledger smoke` never runs in CI; CI is the unit-test gate; wiring is covered by fake-client tests — amends D28

**Problem.** A CI gate that blocks on Batch latency is broken, not slow (D-025) — a correctness problem with D28, not one more reason for cut #5. And the docs already contradicted each other: `docs/evaluation.md` §9 said smoke runs on demand; `docs/plan.md` T17 said "`ledger smoke` in CI".
**Options.**
(a) **Smoke runs synchronously in CI.** Catches behavioural drift (unsupported rate, `evidence_recall@STOP`) on every push. Misses nothing the smoke measures, but: needs `ANTHROPIC_API_KEY` in GitHub secrets; sync = 2× the Batch rate, ~$1/run; ~50 pushes of dev iteration ≈ $50 of the $200 API budget; minutes of latency per push; and it makes the model's output the gate for a docs-only commit.
(b) **Smoke never runs in CI; unit tests are the whole gate; smoke stays on demand.** $0 per push, no key in GitHub. Misses behavioural drift between on-demand runs — which is what on-demand smoke before each matrix seed is for.
(c) **CI replays recorded API responses.** $0, no key, no latency; tests config → graph → spans → `rag.cost_usd` wiring. Misses behavioural drift entirely (a replay cannot see the model change). Costs a cassette harness for a multi-call Batch flow (create → poll → results) that goes stale with every prompt change.
**Decision.** (b), with (c)'s benefit obtained without cassettes: the wiring is already exercised by fake-client + `InMemorySpanExporter` unit tests (`tests/test_probe_and_cost.py`), and T14's resumability test extends that pattern to the matrix runner. CI = `pytest` + `ruff`. `ledger smoke` stays on demand — run before each matrix seed and before the README numbers — through the same Batch path as the matrix, so it exercises what the matrix uses; its wait is acceptable on demand.
**Consequences.** `docs/evaluation.md` §9 and `docs/plan.md` T17 now agree; cut-list item 5 ("Smoke-eval CI → v2") is moot because smoke-in-CI is not the design; E6's remaining Actions step gates only `pytest`/`ruff`, so if it exceeds ~1 h it is deferred at no loss to measurement.
**Rejected.** (a) and (c) as above. A manual `workflow_dispatch` smoke job (that is (b) with a button, plus a key in GitHub secrets for no gain).
**Validation.** No workflow file invokes `ledger smoke`; §9 and T17 read the same.
**Status 2026-09-17.** Smoke cadence revised: tolerance centre is seed 1; runs after post-seed-1 code changes and once before the README, not before each seed — **D-029**. Body above unedited.

## D-029 · 2026-09-17 · FIXED · Smoke cadence anchored on seed 1; T12 successor-matching test gains negative cases — revises D-028 (cadence) and D-027 (test)

**1. Smoke cadence — the hole in D-028.** D-028 said `ledger smoke` runs "before each matrix seed" and fails against "a tolerance set from the week-4 run". The seed-1 run *is* the week-4 run: before seed 1 there is no tolerance to fail against. And each smoke run is its own Batch wait (D-025), so before-every-seed turns T15's three waits into six and breaks the assumed 3-day window — D-028 was not checked against D-025.
**Decision.** The tolerance **centre** is seed 1's results on the 20 smoke questions (unsupported-claim rate, `evidence_recall@STOP`). Smoke runs **(a)** after any code change made after seed 1, and **(b)** once before the README numbers — not routinely before seeds. **Tolerance width is OPEN**: one seed gives no variance estimate; two candidate width rules are in the 2026-09-17 session report for the owner to choose; the chosen rule gets a status line here.
**Rejected.** Before-every-seed (no centre before seed 1; doubles the T15 waits). A width picked now (no variance to derive it from).

**2. T12 successor-matching test — negative cases.** D-027's 3b > 5 rule rewards an over-eager matcher: 3b falls, and the damage shows as *wrong pairs*, which nothing counts. The T12 test therefore adds: a regenerated claim about a **different entity** is not matched; **one-to-one** — two baseline claims cannot both map to one regenerated claim.
**Deliberately NOT added:** "unit or period changed → not matched". A repair that corrects a wrong unit or fiscal period — the D14/D15 qualifier-error class, the main failure this corpus exists to test — produces a **true successor whose qualifiers changed**. Forbidding that match would push every qualifier repair into 3b. **Open T12 decision, with a required test:** how a claim whose unit/period was corrected is matched as branch 2 without admitting unrelated claims about the same entity. Candidate 2 in the 2026-09-16 report keys on exactly `{entity, unit, period}`; the 2026-09-17 report states whether that changes the lean.
**Code.** `docs/plan.md` T12 and T17 lines; `docs/evaluation.md` §9; CLAUDE.md smoke comment.
**Validation.** T12 tests as listed; smoke tolerance centre recorded from seed 1 in `reports/smoke.json`.
**Status 2026-09-17.** The open width is closed by **D-030** (structural assertions; paired t + bootstrap on the unsupported share; exact McNemar on `evidence_recall@STOP`; 90 % two-sided; worse → fail, better → flag). Body above unedited.

## D-030 · 2026-09-17 · FIXED · Smoke gate rule: structural assertions, paired t-interval on the unsupported share, exact McNemar on evidence_recall@STOP, 90 % two-sided, asymmetric tails — closes D-029's open width

**Decision (owner, from the 2026-09-17 analysis with two corrections).** `ledger smoke` compares its 20 questions against seed 1's results on the same 20 (the centre, D-029). The gate is:
1. **Structural assertions — fail outright, no statistics:** verifier output all-SUPPORTED or all-UNSUPPORTED; zero ledger claims; `rag.cost_usd` = 0; schema-valid < 0.98 (A4's threshold, `eval.schema_valid_min`).
2. **Unsupported-claim share (continuous, per question):** paired t-interval on the 20 per-question differences (smoke − seed 1), 90 % two-sided; paired bootstrap over questions (`eval.bootstrap_n`) as cross-check; disagreement between the two is itself a flag (skewed differences).
3. **`evidence_recall@STOP` (binary per question):** **exact McNemar test on the discordant pairs, 90 % two-sided.** *Correction A:* not a t-interval or bootstrap — with ~3 of 20 pairs non-zero both are miscalibrated or degenerate. Consequence, stated so nobody is surprised: with k discordant pairs the exact two-sided p reaches 0.10 only at k ≥ 5 all in one direction (2·0.5⁵ = 0.0625), so this arm fires only when ≥ 5 questions flip the same way — consistent with the ~22 pp MDE and with "breakage only".
4. **Tails:** lower (worse) → **fail**; upper (better) → **flag for inspection, not fail** (an unexplained improvement — e.g. a verifier marking everything SUPPORTED — is caught by (1) directly and by the two metrics moving disjointly).
5. **Scope: breakage only.** Minimum detectable effects (~14 pp unsupported share, ~22 pp ≈ 4–5 questions for `evidence_recall@STOP`) are conditional on assumed spreads (paired-difference sd ≈ 0.25 and ≈ 0.39); **replace them with T5-probe / seed-1 values when those exist.** Drift below these is invisible; the README's regression claims never rest on smoke.
**False-alarm rate (Correction B).** Two metrics × two tails at 5 % each, assumed independent: on a clean run **P(fail) ≈ 10 %** (1 − 0.95², the two lower tails) and **P(fail or flag) ≈ 19 %** (1 − 0.95⁴). At the D-029 cadence (a handful of runs) the expected false alarms over the project are < 1 fail.
**Requirement.** `reports/smoke.json` stores **per-question unsupported share, per-claim verdicts, and per-question gold-in-context — not aggregates**; the gate is computed from those. On the T14 and T17 lines and in §9.
**Rejected.** Claim-level Wilson on ~100 claims (ignores clustering by question — claims in one answer share retrieval and generation). A fixed asserted band (±10 pp; no source, and one seed-1-vs-seed-2 aggregate difference is a single draw). t-interval or bootstrap on `evidence_recall@STOP` (Correction A). 95 % (raises the MDE ~15 % for nothing when a false alarm costs one inspection). One-sided (would miss an unexplained improvement as a breakage signal).
**Code.** `ledger smoke` (T17): structural checks, paired t + bootstrap on the share, exact McNemar on recall, fail/flag output; `reports/smoke.json` schema per the requirement.
**Validation.** Smoke output shows both intervals, the McNemar p, the discordant-pair count, and fail/flag per metric; the first post-seed-1 run's numbers recorded in `docs/plan.md`.
**Status 2026-09-17.** The ≈10 % / ≈19 % clean-run rates are conservative because the exact McNemar test is discrete — with ~3 discordant pairs its attained false-alarm rate per tail is far below the nominal 5 % — not because the metrics correlate "on a real breakage" (the 2026-09-17 report's reasoning): clean-run rates are about runs with no breakage. Conclusion unchanged; body unedited.

## D-031 · 2026-09-17 · FIXED · Stop-and-report convention for session instructions; fixed decisions follow the say-once-then-follow rule — reconciles CLAUDE.md:15 and CLAUDE.md:57

**What.** The convention added to CLAUDE.md in `b583195` without an entry (Conventions: every decision goes in `docs/decisions.md`): if a **session instruction** looks wrong — contradicts the docs or code, misreads an entry, or would cause harm later — do not carry out that part; stop, explain in the report with file:line evidence, propose the alternative; never silently substitute; never log a decision the owner has not made; everything unaffected proceeds.
**Conflict resolved.** CLAUDE.md:15 says FIXED decisions (D-005/6/8/9) are "say so once, then follow"; the convention as first written (CLAUDE.md:57, "any instruction") said "do not carry out that part". An instruction that implements a fixed decision fell under both. **Rule:** the convention covers *instructions*; FIXED decision entries follow line 15 — say so once, then follow, until the owner writes a successor. A wrong-looking fixed decision is flagged, not refused.
**Reason.** Instructions are one-off and cheap to re-issue; a fixed decision is the thing the build runs under, and refusing it mid-build is exactly the silent substitution the convention forbids. The owner's successor entry is the only path to changing a fixed decision.
**Rejected.** Leaving both lines as written (an implementation instruction for a fixed decision would be both refused and followed). Extending stop-and-report to fixed decisions (makes every fixed decision re-litigable per session, which line 15 exists to prevent).
**Code.** CLAUDE.md:57 wording; no code.
**Validation.** Session reports that invoke the convention cite file:line; fixed decisions are never refused in a report, only flagged.
