# Overnight report 2026-10-04

OVERNIGHT START 2026-10-05T04:10:46Z
OVERNIGHT STOP  2026-10-05T04:30Z (about 20 min elapsed; both parts finished well inside the 6 h cap)

## OWNER DECISIONS NEEDED
1. Part A: none. Already reported at e1a9618.
2. D26 cells: none. Resolved from `docs/evaluation.md:58` (10 cells, seeds [1, 2] per D-035 status 2026-10-01).
3. Part B: nothing that could not be made offline. No test was weakened or deleted.

## Parts
| Part | Window (UTC, approx) | Status |
|---|---|---|
| B1 offline tests | 04:11-04:20 | done (07836f5) |
| B2 CI | 04:20-04:23 | done, run 1 green (07836f5) |
| C1 Batch docs | 04:24 | done |
| C2/C3/C4 runner, template, tests | 04:24-04:27 | done (142c2e8); no CLI wiring |

## Tests and ruff
- Normal run (HF cache present): **223 passed, 3 skipped** (the 3 skips are the pre-existing T4 skips in `tests/test_mer_absent.py`).
- HF cache hidden (`HF_HOME` = empty temp dir, `HF_HUB_OFFLINE=1`, that run only): **149 passed, 77 skipped, 0 failed**. 74 of the skips are tokenizer-gated, all with reason "embedder (Qwen3) tokenizer not in the Hugging Face cache (offline); needs the real tokenizer"; the other 3 are the T4 skips above.
- Before the change, the hidden-cache run had ~74 errors (`OSError` on tokenizer download) in `test_parse.py` and `test_d037.py`.
- Data-dependent failures seen while the parse ran: **none**.
- `ruff check .` and `ruff format --check .`: clean (117 files).
- Mechanism: marker `needs_hf_tokenizer`, registered in `tests/conftest.py` (`pytest_configure`). `pytest_collection_modifyitems` marks every test that requests the `chunker` fixture and skips marked tests when `try_to_load_from_cache(embedding.model, "tokenizer.json")` finds nothing. Tokenizer files are not vendored.
- `tests/test_offline_synthetic.py` adds 4 offline twins (padded/compact) of the tokenizer-agnostic logic tests (no table/prose mixing; chunk ids stable and slice-indexed), using a whitespace tokenizer injected by monkeypatching `HuggingFaceTokenizer.from_pretrained`. They add to the real-tokenizer tests; they replace nothing.

## CI
`.github/workflows/ci.yml` (push + pull_request; uv-managed Python 3.12; `uv sync`; ruff check; ruff format --check; `uv run pytest`; `HF_HUB_OFFLINE=1`; no secrets, no data, no smoke). `gh` is not authenticated here, so I read the run through the public API: run 1 on 07836f5, **conclusion: success**. Actions was evidently enabled on the repo (plan.md E6 said "not enabled"; the E6 checkbox is stale).

## Batch docs (C1)
URL: https://docs.claude.com/en/docs/build-with-claude/batch-processing (redirects to platform.claude.com/docs/en/build-with-claude/batch-processing; Firecrawl cache from 2026-10-04T08:01Z, quotes extracted in direct-quote mode):
- Processing window: "Batches expire if processing does not complete within 24 hours." and "You can access batch results when all messages have completed or after 24 hours, whichever comes first."
- Results availability: "Batch results are available for 29 days after creation. After that, you may still view the Batch, but its results will no longer be available for download."
- Per-request result types: succeeded, errored, canceled, expired.
Both match D-025 (24 h; 29 days). No discrepancy.

## What was built (C)
- `ledger/matrix/jobs.py`: `JobLedger` (append-only JSONL, fsynced) + `run_seed`. States pending, intended, submitted, completed, expired, errored. completed is skipped; submitted is polled, never resubmitted; expired/errored are resubmitted alone. Intent (deterministic token) is persisted before `submit`; a re-run finds an intent without a batch id and asks `client.find_batch(token)` rather than submitting again. One seed at a time (D-009); seeds after the first need `confirm_seed_1_inspected`. Results go to `results/<cell>/<seed>.jsonl`, one record per question with usage, idempotent by key, never aggregates (D-030).
- `ledger/matrix/cells.py` and `experiments/matrix.yaml`: pydantic loader; 10 cells + seeds [1, 2], commented with evaluation.md:58 and D-035.
- `tests/test_matrix_jobs.py`: 12 tests with a fake client and `tmp_path` only (four D-025 cases, crash between submit and persist, crash before the service accepted, partial expiry, out-of-order results keyed per question, idempotent writes, seed guards, no real client or sampling parameters in the source, the matrix template).
- No CLI wiring (C4): `ledger/cli.py` untouched, no `ledger matrix` command, no flag. No API call, no key.

## Conservative choices
- `custom_id` is a 40-char hash of the key, not the key itself: the Batch `custom_id` charset is `[A-Za-z0-9_-]{1,64}` and cell ids/question ids could collide with a separator. The ledger maps it back.
- Marked real-tokenizer tests via the `chunker` fixture rather than editing individual test bodies.
- The real-Batch adapter is not written. Note for it: the API has no obvious "find batch by token" call, so a real `find_batch` will need a design (e.g. list recent batches and match the first request's `custom_id`). The Protocol and the crash-safety tests are ready for it.
- Did not touch `ledger/ingest/`, `configs/`, `data/`, `pyproject.toml`, `uv.lock`, docs, or `ledger/cli.py`. Ran Python only as `uv run --no-sync`.

## Anything that looked wrong
- `docs/architecture.md:181` and `:200` still say 3 seeds / 10 cells x 3: stale after D-035. Not edited, per instruction.
- `docs/plan.md` E6 says Actions "not enabled"; CI ran green, so that line is stale. T14's "open item" (offline-clean pytest) is now done in code; plan.md was not edited tonight.
- A local Windows run emits CRLF warnings on add; harmless.

## Commits
- 07836f5: offline-clean pytest + CI workflow
- 142c2e8: T14 resumability core
- this report: see `git log` (final commit)

No decision was logged; `docs/decisions.md` was not edited.
