# CLAUDE.md — LEDGER v1 (Loop with Evidence-Decomposed Grounding and Error Repair)

Loaded every session. Rationale lives in `docs/` and is referenced by path, never imported.

## Read on demand (not imported)
- `docs/decisions.md` — every decision with reason; the D-numbered entries govern the rules below. Process decisions (tooling, sizing, workflow) are logged there on the same rule as pipeline decisions.
- `docs/architecture.md` — pipeline spec, alternatives and why each was rejected, idea-level rationale
- `docs/evaluation.md` — eval set, metrics, results table, κ pilot protocol, decomposition audit, failure taxonomy
- `docs/plan.md` — build order as checkboxes; tick tasks and gates as you complete them

## How to treat decisions
- When implementing a logged decision, say which one you are applying and why, in one line. Never comply silently.
- If a measurement, library constraint, or license contradicts a decision: **stop and report the evidence and the options.** Do not work around it; do not revise it yourself.
- D-001, D-003, D-004, D-007 resolve against week-1 data. When the number arrives: report it, state the branch it selects, get confirmation before proceeding.
- D-005, D-006, D-008, D-009 are fixed. If one looks wrong, say so once, then follow it.
- A decision enters `docs/decisions.md` when it is the one being built under, not when proposed. Rejected options go in the winner's "Rejected" section, not as their own entries. A revisited decision gets a new entry naming the old id.

## Commands (the contract, built incrementally across T1–T14; T1 creates the CLI skeleton and `--help`)
Console entry point `ledger = "ledger.cli:main"` in `pyproject.toml`. **Paths in this file (`tracing/otel.py`, `eval/kappa.py`, `retrieval/store.py`, …) are relative to the `ledger/` package** — never create a top-level `tracing/`, `eval/` or `retrieval/`. **Naming:** `ledger` is the project, the CLI, and a data structure. The Python package is `ledger/`; the claim-ledger data structure lives at `ledger/claims/ledger.py` exporting `ClaimLedger`. Never create a top-level `ledger/ledger.py`.
```
uv sync                                   # Python 3.12, deps from pyproject.toml / uv.lock
uv run pytest -q                          # unit tests: schemas, ledger invariants, stop rule, config, D-002/D-006 guards
uv run ruff check . && uv run ruff format --check .

uv run ledger ingest --stage list            # T2: frames -> granule gate -> seeded draw -> data/manifest.jsonl; downloads NOTHING (D-034)
uv run ledger ingest --stage fetch --draw-confirmed   # T2: fetch the confirmed draw; hashes, pages (pypdf), text-layer ratio
uv run ledger ingest --stage parse --limit 20        # T3: parse + chunk the 20-unit pilot (CPU), print table_chunk_share, STOP (D-001, D-032)
uv run ledger ingest --stage parse --all --confirmed # continue past 20 units only after the owner confirmed the share
uv run ledger audit-tables --n 10            # A1: 10-table cell-integrity audit, writes reports/a1_tables.md
uv run ledger index                          # embed (bf16) the ingested chunks, build the Qdrant file, FREEZE chunk IDs
uv run ledger loadtest                       # A8: embedder + reranker + verifier resident, one verify call, nvidia-smi
uv run ledger baseline --questions data/questions_draft.jsonl   # single-shot run; also A4/A6/A7 numbers
uv run ledger questions --n 200 --controls 20                   # D24 generation + filters
uv run ledger pilot --labels data/labels_pilot.jsonl            # A2: 2 verifiers × 2 input modes → κ table (D-003/D-004)
uv run ledger matrix --seed 1                # runs every cell for seed 1 via Batch (D-009)
uv run ledger matrix --seed 2 --confirm-seed-1-inspected        # seeds 2–3 require the flag
uv run ledger eval results/                  # D26 table with CIs → reports/results.md
uv run ledger kappa --labels data/labels_week3.jsonl            # paired 100/100 κ (D-010)
uv run ledger audit-decomp --answers <run> --n 25               # D15 decomposition audit sheet
uv run ledger smoke                          # 20-question regression eval (D28), ~$0.50; centre = seed 1, after post-seed-1 code changes + before README (D-029); gate rule D-030
```
Every command reads `configs/base.yaml` plus an optional `--config` override. Only run-scoping flags are passed on the command line (`--seed`, `--n`, `--limit`, `--controls`). Every tuning parameter lives in config. (D-021)

## Environment
- Python 3.12; `uv` for packages and venv; `ruff` for lint/format; `pytest`.
- Env vars: `ANTHROPIC_API_KEY` (generator, Batch API); `OTEL_EXPORTER_OTLP_ENDPOINT` (Phoenix, D-014) and `OTEL_EXPORTER_OTLP_HEADERS` if Phoenix auth is on; `AWS_PROFILE` / `AWS_DEFAULT_REGION` for S3; `HF_HOME` on the NVMe; `GOVINFO_API_KEY` (api.data.gov, D-034 — `DEMO_KEY` rate-limits within a few calls). No other keys.
- Services: none run locally. Qdrant is a local file (D-002). Phoenix is **self-hosted on a t3.small** (`ledger-phoenix`, D-023 — revises D-015's t3.medium; resize check end of week 3), image **pinned `arizephoenix/phoenix:20.12.0`**, auth and TLS off, security group is the only access control; the endpoint comes from the environment and is never hardcoded.
- GPU work runs on an AWS g6e.xlarge (L40S, **44.7 GiB usable**, 250 GB local NVMe). Qdrant file and model cache on the NVMe; corpus, parsed output and `results/*.jsonl` sync to S3.
- Generation, decomposition, rewrite: Claude Sonnet 5 via the **Batch API**. Never call the generator synchronously inside the matrix runner (unit-tested, D28).
- Do not start GPU jobs without confirming the instance has an idle auto-stop configured. **This is the one hard constraint with no code guard** — its violation shows up only on the bill.
- Host is **Windows / PowerShell**. Conda base must NOT be active — `uv`
  manages `.venv`, and a layered conda environment resolves imports from the
  wrong site-packages. Run `conda deactivate` (or set `auto_activate_base
  false`) before any `uv` command. Never suggest `conda install`.

## Conventions
- **`git push` is part of finishing a task, not a separate step.** The remote is the only backup of this work; a task is not done until origin has it. Report the pushed commit hash(es).
- Every decision made in a session — process, tooling, sizing, interpretation — goes in `docs/decisions.md`; end the session report with the ids written and a one-line summary of each.
- If a session instruction looks wrong — contradicts the docs or code, misreads an entry, or would cause harm later — do not carry out that part: stop, explain in the report with file:line evidence, and propose the alternative. Do not silently substitute your own version, and do not log a decision the owner has not made. Everything unaffected proceeds. This covers instructions; FIXED decision entries follow line 15 — say so once, then follow, until the owner writes a successor. (D-031)
- `ledger smoke` never runs in CI; CI is `pytest` + `ruff` (D-028). Its tolerance is centred on seed 1's results; it runs after post-seed-1 code changes and once before the README — not before each seed (D-029). Gate rule: D-030 (structural assertions; paired t on the share; exact McNemar on recall; 90 % two-sided; worse fails, better flags).

## Enforcement
CLAUDE.md is context, not enforced configuration. Anything that must be **blocked** rather than requested goes through a code guard or a PreToolUse hook. Most hard constraints already are code guards: ingest stops at 20 (D-001), the seed flag (D-009), the missing retriever handle in rewrite (D-006), the judge-revision raise (D-007), the bf16 validator (D-012), the `chunk_ids.lock` check (D24), the single-client test (D-002), and a unit test that the matrix runner never calls the generator synchronously (D28). The one uncovered candidate is the idle auto-stop above; if it is ever violated, a PreToolUse hook on GPU-launching commands is the mechanism.

## Rules that change how code is written
- **Qdrant client is constructed in exactly one place** (`retrieval/store.py::make_client`) behind `vector_store.mode`; nothing else imports `QdrantClient`. Local file mode in v1. (D-002)
- **Ingest stops at 20 documents** until `table_chunk_share` is printed and confirmed. Band 50–70% is acceptable; inside it, do not tune. Adjust remaining ingest only; never re-parse and **never re-chunk** — once ingest chunks, `chunking.max_tokens` moves the share directly, so tuning it to hit the band is the same violation. (D-001, D-032)
- **Human labels are three-class** (SUPPORTED / PARTIAL / UNSUPPORTED). Verifier verdicts stay binary. `eval/kappa.py` emits binary κ first (PARTIAL → UNSUPPORTED), then three-class κ and partial rate flagged "not comparable". (D-003)
- **Verifier input mode** is `verifier.input_mode ∈ {concatenated, per_chunk_max}`; both implemented; the pilot scores both; tie within 0.05 κ → concatenated. The rule is committed — do not re-derive it after seeing results. (D-004)
- **Citations are chunk IDs.** No span offsets in any v1 schema. (D-005)
- **`repair/rewrite.py` has no retriever handle.** It receives the frozen context from the ledger; a test asserts zero retrieval calls. (D-006)
- **The judge is not chosen yet.** `judge.model` / `judge.revision` stay empty until the owner picks one in week 1; the loader raises on an empty revision. Once set, the revision hash is pinned and never changed. Judge family must differ from Sonnet and from the pilot-selected verifier. (D-007)
- **`delete` inserts `[unverified claim removed]`**; `eval/retained.py` strips the marker before counting. (D-008)
- **Seeds run one at a time.** `--seed 1` runs freely; seeds 2–3 require `--confirm-seed-1-inspected`. (D-009)
- **Claim labels are paired**: 100 baseline + 100 post-repair from the same 100 questions, post-repair from the `re_retrieve(1) × claimify` cell, seed 1. `eval/labels.py` refuses unpaired halves. (D-010)
- **Verifier precision is bf16 and only bf16.** No quantized path; `verifier.precision` validates to `bf16`. If A8 fails: 0.6B embedder, then separate stages. Never quantize. (D-012)
- **Every parameter lives in `configs/*.yaml`** validated by pydantic; nothing numeric is hardcoded. Cost per query comes from API usage fields, never estimates. (D31)
- **No sampling parameters, anywhere.** `temperature`/`top_p`/`top_k` were removed from the Claude API (SDK 1.0.0, 2026-08-20; Sonnet 5 400s on non-default values, sync and Batch alike). The config validator raises explicitly on any of them — that error is not a missing schema field; do not add the key. A "seed" is an independent run at default sampling; the seed count is provisional until T9/T11. (D-019)
- **The judge guard is at the use site**: `load_config` accepts an empty `judge.revision`; `JudgeConfig.require_pinned()` raises where the judge is loaded. (D-020)
- **No project skills or slash commands in v1** (D-016). Revisit at T14 after two hand runs of the matrix; the trigger is in `docs/plan.md`.
- **Instrument from the first commit.** Every LLM call, retrieval, rerank and verify emits an OpenInference span over OTLP through `tracing/otel.py`; span kinds and attribute names per `docs/architecture.md` D29. Verifier verdicts go **inline** on the open verify span as `evaluations.0.evaluation.*`; human labels go **post-hoc** as `EVALUATOR` carrier spans with exactly one Span Link, over OTLP. **Nothing under `tracing/` or `eval/` imports `phoenix`** (unit-tested). (D29 as revised by D-014, D-017)
- **Tables are split by rows, never mixed with prose.** `HybridChunker` splits a table larger than `max_tokens` into row slices with the header row repeated on every slice; `repeat_table_header: true`, `omit_header_on_overflow: false`, `merge_peers: false` are pinned by config validators and a T3 test. `chunk_type` is `table` iff the chunk holds **≥ 1 table item and every other doc item is a caption or footnote** — Docling emits the caption as its own item, so the stricter reading counted every unsplit table as prose (D-036). `max_tokens` is the main lever on A6 difficulty (more slices = more near-identical siblings); v1 holds 512. (D3 as revised by D-033 and D-036)
- **Chunk IDs are assigned at ingest and frozen at index.** IDs derive from document content and position (`<doc_id>::p<page>::<item>::s<slice>`), never from a global counter, so ingesting later documents cannot renumber earlier ones; between assignment (T3) and freeze (T4) nothing re-chunks (D-032). **Frozen before question generation** (`ledger index` writes `data/chunk_ids.lock`; `ledger questions` refuses to run without it). Re-chunking after questions exist breaks `evidence_recall@STOP`. (D24)

## Known pitfalls
- Instrumentation is **OpenInference (`llm.*`), not `gen_ai.*`** — chosen *because* `gen_ai.*` is unreleased and still Development as of Aug 2026 (D-014). Do not "upgrade" to `gen_ai.*`; do not set `OTEL_SEMCONV_STABILITY_OPT_IN`. Pins: `openinference-semantic-conventions==0.1.37`, `openinference-instrumentation==0.1.63` (D-018; D-017's 0.1.29 lacked the `evaluations` constant). Verify attribute keys against the pinned package, not from memory.
- Qwen3-Reranker is a yes/no LM scorer, not a drop-in cross-encoder — use the official scoring snippet or scores are garbage.
- Sonnet 5's tokenizer produces ~30% more tokens than older models; budget projections must use measured usage from the API, not estimates.
- Docling is unmeasured on OmniDocBench; the A1 ten-table audit is the only table score this project has for it. Fail A1 → `parser: paddleocr_vl` in config, re-audit.
- The L40S reports 44.7 GiB, not 48. Plan residency against 44.7.
- Batch API results arrive out of order and hours later; the matrix runner must key everything by `(cell, seed, question_id)`, never by position.
- **OTLP endpoint trap.** Phoenix's startup banner prints `OTLP over HTTP http://localhost:6006/v1/traces`. That value belongs in `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`. `OTEL_EXPORTER_OTLP_ENDPOINT` takes the **base only** (`http://host:6006`); the HTTP exporter appends `/v1/traces` itself. Copying the banner into the base variable produces `/v1/traces/v1/traces` and a `405 Method Not Allowed` on export.
- **Sampling parameters are gone.** `temperature`, `top_p`, `top_k` are absent from anthropic ≥1.0 signatures (`TypeError`), and Sonnet 5 400s on non-default values. On the Batch path the `params` TypedDict is not enforced at runtime, so the key *can* reach the wire — which is why the block is in our config validator (D-019). The Messages API reference still documents `temperature`; trust the SDK and the 400.
- **A local Phoenix run is an instrumentation smoke test, not A5.** A5 verified the EC2 host, its security group, and that server's `arize-phoenix` version (v20.12.0, passed 2026-09-16). A green `scripts/a5_probe.py` against `localhost:6006` proves only the instrumentation.
- **The tracing endpoint differs by host** (D-023). Laptop → the Elastic IP `http://54.160.244.106:6006`. GPU instance → the **private** IP `http://172.31.68.230:6006`. The g6e's access is an SG-to-SG rule, which matches only traffic on private addresses inside the VPC; using the Elastic IP from inside the VPC routes out through the IGW and is dropped by the security group **silently** — no error, empty κ pilot. The g6e must be in `vpc-0f3297a449901c109`.
- **The Phoenix server version is pinned** (`arizephoenix/phoenix:20.12.0`, digest in D-023). Changing it re-opens D-022's (c) acceptance — Span Link rendering is backend behaviour — and requires re-running A5.
