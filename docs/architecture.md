# docs/architecture.md — LEDGER pipeline specification and design record

Read on demand. Sources: Stage 1 landscape scan (2026-09-11), Stage 2 ideas + blind-spot audit, Stage 3 head-to-head, Phase 2 plan (2026-09-12), `docs/decisions.md` D-001…D-014. Every section carries a **Rejected** block. Numbered D-references are Phase 2 decisions; hyphenated D-0xx are `docs/decisions.md` entries.

---

## 0. What this system is, in one paragraph

A retrieval-augmented question-answering loop over 100–150 born-digital US federal PDFs whose answers live in table cells. Each answer is decomposed into atomic claims; a small local verifier checks each claim against the retrieved evidence; unsupported claims are repaired by one of three fixed actions — delete, rewrite, or re-retrieve — and the loop stops when every claim is supported or a budget is hit. The measured contribution is not the loop (it is a textbook pattern) but the measurement: the verifier is calibrated against human labels, decomposition error is bounded, retained content is reported beside every faithfulness number, and re-retrieve is treated as a repair action rather than a fixed stage.

---

## 1. Why this project — idea-level rationale (not in the Phase 2 plan)

Five ideas were generated in Stage 2, each traced to a Stage 1 finding, and audited across thirteen RAG stages for what each idea built, held constant, or silently dropped.

**Idea 2 (this project) — claim-verify-repair with a calibrated local verifier.** Chosen because it is *hireable*: its README numbers (unsupported-claim rate with CI, verifier–human κ, decomposition error, delete/rewrite/re-retrieve tradeoff) map onto literal phrases in three of four Stage 1 job postings ("citation or source-grounding patterns, validation, confidence thresholds, output schemas, fallback handling"; "high faithfulness"; "evaluation pipelines"). It fits 60 hours at the midpoint estimate (48–67 h) and is a loop with a loop-back edge in its base form.

**Rejected at idea level:**
- **Idea 1 — evidence-gated stopping for a search agent on BrowseComp-Plus.** Stage 1 had called stopping criteria "thin"; the Stage 2 prior-art check found four papers in eleven months (Stop-RAG, Adaptive Stopping, TASR, the S2G judge). Its convenience choice — BrowseComp-Plus for free labels and evidence sets — deleted four of thirteen stages as side effects, and open 7B reasoners score ~4% on that benchmark, so stop-policy differences sit inside noise. **What survives:** only its metric, `evidence_recall@STOP` — is the gold chunk in context at the moment the loop stops — grafted into this project (D22), because it is cheap (3–4 h) and turns the stop rule into a measured quantity.
- **Idea 3 — poison-resilient retrieval with provenance tiers and traceback.** The most distinct and the cleanest audit sheet (eight stages built, nothing a side effect). Lost on hours: its trimmed v1 estimated at 51–77 h with zero query-time decisions — a pipeline — and 6–8 more hours to make it agentic. Stage 2 also missed RAGShield (Apr 2026) and TriShieldRAG (Jul 2026), which occupy its provenance-tier ground; RAGShield's Proposition 1 states provenance-only defenses fail against insiders. **What survives:** a v2 borrow — cross-source support count per claim plus a 20-document numeric-manipulation set — deferred because **a faithfulness verifier is not a poisoning defense**: it will mark a claim "supported" by a poisoned passage. Only a cross-source consistency check is a defense, and that costs 5–7 h the 60-hour window does not have (D-011 budget, §5 kill list).
- **Idea 4 — per-document routing between parsed-text and visual (ColQwen) retrieval on degraded scans.** Strongest engineering-judgment signal; resolves a live disagreement in the literature (*Lost in OCR Translation?* finds OCR wins overall while being cited as showing visual is more robust to degradation). Lost on timeline (assembling a corpus plus 200 hand-labelled queries is the whole window) and on agentic surface (a router is one decision).
- **Idea 5 — version-aware agent over an evolving corpus, measured by staleness.** Hollowed out by its convenience trace: git diffs give free version labels and remove the hard case (in-place revision without markers) that VersionRAG and the legal temporal-misgrounding benchmark identify as where systems fail.

**Stage 3 corrections carried forward.** Headline risk does not decide first place once repairs are applied (both ideas convert their failure mode into a reported bound). The 200 claim labels are split 100 baseline / 100 post-repair, paired on the same questions (D-010), because measuring the post-repair rate with the verifier that drives the repair loop is the verifier grading its own work.

---

## 2. Data layer

### D1 Corpus — LOCKED
100–150 born-digital PDFs: GAO reports, CBO cost estimates and outlooks, EIA outlooks. Provisional mix EIA 50 / CBO 40 / GAO 30, adjusted only on the remaining ingest after 20 documents are parsed and `table_chunk_share` is measured; 50–70% table chunks is in band (D-001). Manifest per document: source URL, SHA-256, agency, publication date, page count. Hard because answers are cells in multi-header tables and the unit and fiscal period sit in captions and headers.
**Rejected:** FinanceBench — the Stage 2 audit showed it erodes the differentiator (FinGround already occupies finance) and hands over the hard-question distribution (150 questions, many "not answerable").
**No external source:** US government works as public domain (17 U.S.C. §105) is an inference; confirm per agency page.

### D2 Parser — GATED on A1
**Choice:** Docling (IBM, MIT), TableFormer accurate mode, PDF text-layer backend, `HybridChunker` for D3.
**Reason:** the corpus is born-digital, so the text layer contains the exact digits; a VLM parser re-OCRs a rendered page, and its residual text error (edit distance 0.035 for PaddleOCR-VL-1.5) *is* the numeric-transcription risk this project measures. Docling copies digits; only table structure is at risk, which is what the A1 audit measures.
**Rejected:** PaddleOCR-VL-1.5 (Baidu, Apache-2.0, 0.9B; Table TEDS 92.76 on OmniDocBench v1.5 — the highest published; kept as the A1 fallback via `parser: paddleocr_vl`). MinerU2.5 (AGPL-3.0; TEDS 88.22 v1.5). MinerU2.5-Pro (AGPL-3.0; v1.6 score disputed — see §8). dots.ocr (TEDS 86.78). Marker (GPL-3.0 code + RAIL-M weights; TEDS 57.88). VLM-native parsing via Gemini/GPT (per-page API cost on a constant stage).
**Validation:** A1 — 10 tables across agencies, ≥150 cells, ≥95% cells correct with header association. Parser sweep on this corpus is v2.

### D3 Chunking — DECIDED, held constant
Docling `HybridChunker`, run at ingest on CPU with the embedder's tokenizer only (D-032): section headings and captions prepended (`contextualize`); tables are never mixed with prose (`merge_peers: false`) and are **split by rows when they exceed `max_tokens`, with the header row repeated on every slice** (`repeat_table_header: true`, `omit_header_on_overflow: false`; all three pinned — D-033); chunk IDs carry a slice index; `max_tokens: 512`; no overlap. **`max_tokens` is the main lever on A6 difficulty** under row-splitting (smaller → tighter gold slice, more near-identical siblings; larger → fewer siblings, more irrelevant rows); v1 holds 512; the chunking sweep is v2.
**Reason:** retrieval is a held-constant, retrieval-equalized stage — the comparison is between repair arms, not retrievers — so the budget should not buy retrieval gains. Heading-prepending is a free, deterministic slice of the "context" benefit.
**Rejected:** Anthropic contextual retrieval (−35% top-20 retrieval failure, −49% with BM25, vendor-run; ~30k LLM calls ≈ $15–40 of the $200 API budget on a constant stage). Jina late chunking. Fixed-size recursive splitting. Proposition chunking. Chunking sweep is v2 (kill list).
**No external source:** 512 tokens is a convention, not a measured optimum. Say so in the README.

### D4 Embedding — DECIDED, size gated on A8
**Choice:** Qwen3-Embedding-4B (Apache-2.0, 2560-d, 32k context; MTEB multilingual 69.45), bf16, no Matryoshka truncation.
**Reason:** best open quality that leaves room for the co-resident verifier; the 8B's +1.1 points buys nothing in a retrieval-equalized design.
**Rejected:** Qwen3-Embedding-8B (70.58; 2× VRAM). Qwen3-Embedding-0.6B (64.34; the A8 fallback). BGE-M3. NV-Embed-v2 (CC-BY-NC). API embedders (Gemini Embedding 2, voyage) — external dependency on a constant stage. Matryoshka truncation — v2.

### D5 Vector store — DECIDED
**Choice:** Qdrant in local (embedded) file mode; sparse BM25 vector configured but disabled; payload filters `doc_id`, `is_table`. Client constructed in exactly one place behind `vector_store.mode` (D-002).
**Rejected:** pgvector (an extra Postgres service in a 60-hour project; most-named in postings — the swap is one adapter). LanceDB, Chroma, Milvus (equivalent at ~30k vectors). Qdrant as a Docker service — v2/demo.

### D6 Index freshness — DECIDED out of scope
Frozen snapshot pinned by manifest hash; nothing changes during the experiment; full rebuild is minutes. Converted from a Stage 2 "deleted by side effect" to an explicit decision. Incremental ingestion is v2.

### D7 Provenance — LOCKED single tier
All documents are agency-published; provenance metadata (agency, URL, date) is stored on every chunk and surfaced in citations. Trust weighting is the Idea 3 borrow, v2.

---

## 3. Retrieval layer (held constant, retrieval-equalized)

### D8 Search + rerank — GATED on the recall gate
**Choice:** dense top-30 → Qwen3-Reranker-0.6B (Apache-2.0) → top-5 into context. Hybrid dense + BM25 (RRF) only if the gate fails.
**Reason:** the reranker's job is to make top-5 recall high enough that the unsupported-claim rate reflects generation, not retrieval misses; 0.6B costs 1.2 GB. Integration caveat: Qwen3-Reranker is a yes/no LM scorer, not a drop-in cross-encoder.
**Rejected:** Qwen3-Reranker-4B (VRAM). BGE-reranker-v2-m3 (Apache-2.0; classic cross-encoder — fine, marginally behind on open leaderboards, all vendor-run). No reranker.
**Gate:** recall@5 of the gold chunk ≥ 0.85 on the 200-question set (checked first on 25 drafts, A6); < 0.85 → enable hybrid; < 0.75 after hybrid → top-k 8.
**No external source:** top-30 → top-5 is a convention.

### D9 Metadata filtering — none at query time in v1. Filters exist for the demo and failure analysis.
### D10 Query rewriting — none on the first pass. The only rewriting is claim → query inside the re_retrieve arm; it is the treatment.

---

## 4. Generation layer

### D11 Generator — DECIDED, gated on A3 / A7
**Choice:** Claude Sonnet 5 via the Batch API ($2 / $10 per MTok; Batch $1 / $5; verified 2026-09-12) for generate, decompose, rewrite. Local models for embed, rerank, verify, judge. Budget: ~39k tokens/query across arms including the ~30% tokenizer overhead × 150 questions × 3 seeds ≈ $25 per full matrix on Batch; ≈ $45 with dev iteration; ≈ $90 without Batch.
**Rejected:** Haiku 4.5 ($1 / $5 — a weaker generator inflates the baseline unsupported rate; kept as the A3 fallback). Opus 5 ($5 / $25 — over budget). A local 8B generator (free; a weaker decomposer, and decomposition is the one step whose errors contaminate everything).

### D12 Grounding stance — STRICT, decided
Answer only from the retrieved chunks; cite every sentence by chunk ID; if the chunks do not contain the answer, return the abstention schema; copy numbers verbatim with unit and period as printed.
**Rejected:** permissive (parametric knowledge allowed and labelled) — confounds "unsupported" with "true but not in context"; faithfulness ≠ correctness (Stage 1 T4).
**Measured by:** abstention on 20 unanswerable controls (≥ 90%) and on answerable questions (≤ 5%); parametric-leakage rate on the labelled subset.

### D13 Structured output — DECIDED, output mode gated on A4
pydantic schemas `Answer`, `Claim`, `Verdict`; validation failure → one retry with the error appended → fallback (sentence-split decomposition, or `delete` repair) with `fallback=true` logged and counted as decomposition error. **Rejected:** free-text answers parsed by regex.

### D14 Hallucination modes and mitigations
| Mode | Mitigation | Measured where |
|---|---|---|
| Numeric transcription (wrong cell / row–column slip) | text-layer parser (D2); table slices that carry the header row (D3/D-033) — column identity on every slice, fewer rows per slice; a needed row in an unretrieved slice is counted as retrieval (`evidence_recall@STOP`, R) or as aggregation-not-present, not as transcription | labels; numeric exact match |
| Unit / period confusion | claims carry `qualifiers{unit, period}`; strict "copy as printed" | decomposition audit; labels |
| Parametric leakage | strict stance; abstention schema | leakage rate on labelled subset |
| Aggregation not literally present | verifier marks unsupported; rewrite must cite constituents | repair-arm results |
| Wrong citation | two-level verification (D16) | citation accuracy |

### D15 Decomposition — DECIDED, a measured stage
**Choice:** Claimify-style extraction — atomic, decontextualized claims tied to a source sentence, carrying `qualifiers{entity, unit, period}`. **Baseline arm:** sentence-split (one sentence = one claim, no decontextualization).
**Reason:** Claimify ships the evaluation criteria (entailment, coverage, decontextualization) the audit needs.
**Rejected:** FActScore atomic facts (no decontextualization). VeriScore (verifiable-only). DnDScore (joint decontextualization; informs the audit rubric, not used as the method). TriQua hyperrelational facts (Aug 2026, too new).
**Measured by:** the 50-answer audit in `docs/evaluation.md` §4. The PARTIAL-label rate (D-003) feeds this analysis.

### D16 Citation generation vs verification
Generate per-sentence chunk-ID citations, then verify at two levels: claim vs cited chunk (`cited_support`) and claim vs full context (`support`). Citation accuracy = P(cited_support | support). Citations are chunk IDs, not spans (D-005): a table cell has no containing sentence. **Rejected:** sentence-span citations (v2, prose-only).

### D17 Context engineering
Context = top-5 chunks (~2.5k tokens) + question; re-retrieval appends new chunks only (dedup by chunk ID) up to 12; no pruning in v1; no chain-of-thought requested (numbers are copied, not reasoned). **Rejected:** stuffing more chunks (Chroma's context-rot result); LLM-summarized context (adds a generation step to a constant stage).

### D18 → D-012 Precision
Embedder bf16; verifier bf16, always, on the L40S. The 24 GB / AWQ-int4 branch from the original D18 was removed when the environment became a 48 GB card. **Rejected:** any quantized verifier (a quantized verifier is a different verifier; the κ pilot would not transfer).

### D19 Fine-tuning — not required
The chosen verifier family reaches GPT-4-level grounded-factuality accuracy off the shelf; fine-tuning on the 200 labels in v1 would destroy the κ measurement (test-on-train). v2.

---

## 5. Agent layer

### D20 Workflow shape and framework — DECIDED
Single agent, conditional-iterative graph in **LangGraph**, state = the claim ledger (typed dict), checkpointed per node. Nodes: `retrieve → generate → decompose → verify → route`; route → `emit` or the arm's repair node; `re_retrieve` loops back to `retrieve`; `rewrite` re-enters at `decompose`.
**Reason:** the graph is the loop; checkpoints give resumable runs; LangGraph is named in three of four Stage 1 postings; ~2 h overhead.
**Rejected:** plain Python loop (fewer hours, full control — would have won on hours alone). Pydantic AI. LlamaIndex Workflows. Multi-agent (Stage 2: context fragmentation and harder tracing for no benefit on a single-question loop).
**README honesty:** in v1 the repair action is a fixed arm per experiment cell, not a runtime choice. The agentic content is the loop-back edge, the stop rule, and the externalized ledger.

### D21 Tools and ledger
`retrieve(query, k) -> [Chunk]`; `verify(claim, evidence) -> Verdict` (local); `rewrite_query(claim)` and `regenerate(question, chunks, ledger)` are LLM calls. Ledger row: `claim_id, text, source_sentence_idx, citations, qualifiers, verdict, score, evidence_ids, iter_first_seen, iter_resolved, action_taken, replaces`.

### D22 Stop rule and budgets — DECIDED
Stop when (a) every ledger claim is SUPPORTED, (b) `iter == max_iter`, or (c) no progress — re-retrieval returned no chunk not already in context. On (b)/(c) apply the arm's terminal action (delete) with a per-claim "could not verify" flag; log `stop_reason`. Caps: `max_iter` (arm value; v1 = 1; graft cells 2 and 3), `max_tool_calls 12`, `max_context_chunks 12`, `max_tokens_per_query 60000`. Measured by `evidence_recall@STOP` (the Idea 1 graft), `stop_reason` mix, mean iterations.
**Rejected:** a learned stop policy (v2); a fixed iteration count with no sufficiency check (the pre-2025 default).
**No external source:** the cap values are estimates.

### D23 Error handling
Schema failures per D13; verifier failure → retry once → `UNVERIFIED` → terminal action; retrieval returning < 3 chunks → proceed and flag; caps exceeded → `budget_exhausted=true`. No human escalation in v1.

### Repair arms — LOCKED
`none` (no-repair row) · `delete` (drop unsupported claims; visible `[unverified claim removed]` marker excluded from retained content, D-008) · `rewrite` (regenerate unsupported sentences from the identical context — no re-fetch, D-006, so the arms differ on one dimension) · `re_retrieve` (claim → query → retrieve → regenerate → re-verify). `delete-all` is a derived trivial-baseline row.

---

## 6. Evaluation layer — summary (full spec in `docs/evaluation.md`)

D24 eval set: 200 questions from a local, different-family model, 60% table chunks, filters, 50 hand-validated, 20 unanswerable controls, chunk IDs frozen first. D25 metrics: retrieval recall/MRR; unsupported-claim rate (verifier and human); paired κ on 100/100 claims (D-010) with three-class labels and a binary primary (D-003); decomposition error; citation accuracy; retained content; correctness; agentic metrics; abstention. D26 results table with `no-repair` and `delete-all` rows and a retained-content column; three sampled runs, seed 1 first (D-009). D27 failure taxonomy. D28 CI: unit tests on push, 20-question smoke eval on demand.
**Rejected:** RAGAS as the primary metric (83.5% null-result rate on numerical finance QA in a third-party study; one comparison row allowed if < 1 h). LLM-as-judge as the faithfulness ground truth (contested reliability; detectors near 50% on hard cases — hence the κ pilot).

---

## 7. Operations layer

### D29 Tracing — REVISED by D-014
**Choice:** OpenTelemetry over OTLP with **OpenInference** semantic conventions, exported to **Arize Phoenix self-hosted on a t3.small** (2 vCPU / 2 GiB + 2 GiB swap — D-023 revises D-015's t3.medium; resize check at end of week 3; single container, image pinned `arizephoenix/phoenix:20.12.0`). Endpoint from `OTEL_EXPORTER_OTLP_ENDPOINT`; instrumentation behind `tracing/otel.py` so the convention set is swappable.
**Span plan (shape retained, names mapped):**
- Root span per query, kind `AGENT`: `input.value` = question; attributes `rag.question_id`, `rag.arm`, `rag.seed`, `rag.iter`, `rag.stop_reason`, `rag.cost_usd`.
- One `LLM`-kind span per generate / decompose / rewrite: `llm.provider`, `llm.model_name`, `llm.invocation_parameters`, `llm.input_messages`, `llm.output_messages`, `llm.token_count.prompt`, `llm.token_count.completion` (cache tokens under `llm.token_count.prompt_details.*` — verify the key against the pinned `openinference-semantic-conventions`).
- One `RETRIEVER`-kind span per `retrieve`: `input.value` = query, `retrieval.documents.{i}.document.{id,score}`; then a `RERANKER`-kind span with `reranker.top_k` and output ids.
- One `TOOL`-kind span per verify: `tool.name="verify"`, `rag.claim_id`, `output.value` = Verdict JSON.
- One evaluation record per verdict, **inline on the open verify span** as `evaluations.0.evaluation.*` (`name="claim_support"`, label, score, explanation = evidence_ids JSON, `annotator_kind="LLM"`, identifier = verifier@revision, metadata = {claim_id, input_mode, threshold, cited_support}) — D-017. Human labels and re-scoring are **post-hoc `EVALUATOR` carrier spans** with exactly one Span Link to the target verify span, emitted over OTLP by `eval/trace_annotate.py`; no Phoenix client. `PROMPT` span kind not adopted in v1.
**Pins:** `openinference-semantic-conventions==0.1.37`, `openinference-instrumentation==0.1.63` (D-018, verified on PyPI 2026-09-14; D-017's 0.1.29 lacked the `evaluations` constant).
**Instance (D-015 → D-023):** D-015 chose a t3.medium on a prediction (bursty Batch-result ingest plus the week-4 UI). D-023 built a t3.small with 2 GiB swap and a cron memory log instead and **deferred the t3.medium to the end-of-week-3 measurement** (peak `MemPerc` from the log; resize is a stop/start with data and address preserved).
**Rejected (D-017):** Phoenix client `add_span_annotation` / `log_span_annotations` — a proprietary write path that would have made the D-014 escape hatch cost a rewrite of `eval/trace_annotate.py`; the `gen_ai.evaluation.result` event (rejected convention; translatable from the OpenInference form anyway).
**Rejected — note the direction:** `gen_ai.*` was the *original* D29 choice and is now the rejected option: it moved to `open-telemetry/semantic-conventions-genai` on Jun 12 2026 and has no tagged release as of Aug 21 2026 — pinning it means pinning an unreleased spec. Langfuse Cloud Hobby (hard 50k-unit cap; the matrix alone is ~90k units). Langfuse Cloud Core ($29/mo real money). Langfuse self-hosted (six containers, ~$60/mo of credits). Opik. LangSmith. Jaeger. Reasons in D-014.
**Escape hatch:** if Phoenix fails A5, point the OTLP endpoint at Langfuse Cloud Core and keep the OpenInference instrumentors. Decide in week 1.

### D30 Metrics tracked in the backend
Per query: retriever latency, chunks in context, verifier latency, tokens, cost (from usage fields), iterations, stop reason. Per run: the D26 table.

### Process decisions (logged on the same rule, D-016 onward)
No project skills or slash commands in v1 (D-016): the eval workflow is five `ledger` subcommands and the instrumentation convention is one rule plus `tracing/otel.py`; revisit at T14. Instance sizing and budget live in D-015. The CLI is `ledger`; the claim-ledger data structure lives at `ledger/claims/ledger.py` (`ClaimLedger`) to avoid a `ledger/ledger.py` collision.

### D31 Config
All parameters in `configs/*.yaml` validated by pydantic; `experiments/matrix.yaml` expands the 10 cells × 3 seeds; `run_matrix.py` submits one seed at a time. Also: `vector_store.mode`, `verifier.input_mode`, `judge.model` + `judge.revision` (pinned hash). **Rejected:** Hydra (multirun is nice; the learning cost is not worth it at 60 h — convention, no source).

---

## 8. Security layer — DECIDED out of scope for v1
Single writer, frozen snapshot of agency-published PDFs, no untrusted ingestion path, so corpus poisoning and injection via retrieved documents have no attack surface to measure. Converted from a Stage 2 "deleted by side effect" to an explicit decision. First security row in v2 = the Idea 3 borrow (§1).

---

## 9. Recorded disagreements (do not cite only the convenient side)

- **OmniDocBench vendor conflicts.** PaddleOCR-VL-1.5's 92.76 Table TEDS is Baidu-run on v1.5; MinerU2.5-Pro's 95.69 overall is OpenDataLab-run on v1.6, while TII's Falcon-OCR card lists MinerU2.5-Pro at 85.15 TEDS on v1.6. v1.5 and v1.6 are not comparable. LlamaIndex (vendor) argues the benchmark is saturated and misses complex financial-report tables. Docling is absent from it entirely — the A1 audit is the only table score this project has.
- **Contextual retrieval vs late chunking.** Anthropic's contextual-retrieval numbers (vendor-run) and Jina's late-chunking paper (vendor-authored) were never run on the same set. The third-party comparison (arXiv:2504.19754) finds contextual retrieval more coherent but ~120× costlier to index and late chunking cheaper but less complete; a June 2026 legal-retrieval paper argues the cost critique is overstated because indexing is one-time. No settled winner; D3 chose neither.
- **Embedding leaderboards.** An aggregator lists Qwen3-Embedding as "early 2026, Tongyi license, 75.1"; the model card says June 2025, Apache-2.0, 70.58. The primary source wins.
- **Verifier leaderboards.** Bespoke-MiniCheck-7B tops the public LLM-AggreFact mirror (77.4); Paladin-mini claims 79.31 in a single-vendor paper and is not on the mirror; Granite Guardian's 76.5 is IBM-run. FaithBench shows all detectors near 50% on hard cases — which is why κ is measured here rather than taken from any of them.
- **LLM-as-judge.** TREC 2024 found GPT-4o agreeing with human assessors 56–72%; other work finds judges unreliable on numeric and multi-hop reasoning. The project uses a local judge only for secondary metrics and never as faithfulness ground truth.

## 10. Decisions resting on no external source (stated so they are not mistaken for evidence)

`chunking.max_tokens: 512` · dense top-30 → top-5 · three sampled runs (at the model's default sampling — `temperature` was removed from the API, D-019; the count is provisional pending the T5 variance probe and the T9/T11 decision) · `max_tool_calls 12`, `max_context_chunks 12`, `max_tokens_per_query 60000` · A1 threshold ≥ 95% cells · recall gate 0.85 / 0.75 · A3 threshold ≥ 8% baseline unsupported · κ branches 0.6 / 0.5 · A4 ≥ 98% schema-valid · A7 ≤ $120 · the D-001 band 50–70% · the D-004 tie-break 0.05 · the D-010 pairing rule for repaired/deleted claims · Qdrant over pgvector · Hydra rejection · all hour estimates in `docs/plan.md`. Each is a convention or an owner/Claude estimate; each is in config so it can be swept later.
