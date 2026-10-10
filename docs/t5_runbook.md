# T5 runbook — draw, drafts, GPU retrieval, join, Batch, reports

Decisions behind this: D-041 (generator pins), D-042 (query instruction, two arms), D-043 (protocol),
D-033 status 2026-10-09 (how A6 is read). Bucket: `ledger-vkm-2026`. Nothing here is run by the
build pass; every command below is the owner's.

## 0. Order, and what each step needs

| # | where | step | needs |
|---|---|---|---|
| 1 | laptop | `scripts/t5_draw.py` | nothing (no key, no S3, no Phoenix) |
| 2 | laptop | `scripts/t5_draft.py` (~51 sync Sonnet calls) | `ANTHROPIC_API_KEY`; Phoenix optional |
| 3 | laptop, by hand | owner checks the candidates in draw order (logging every rejection), then `scripts/t5_finalize_questions.py`, then commit + push `data/questions_draft.jsonl`, `data/questions_draft_draw.json` and `data/questions_draft_draw_run1.json` | nothing |
| 4 | laptop | `scripts/t5_dry_run.py` (2 sync calls) | `ANTHROPIC_API_KEY`; Phoenix optional |
| 5 | GPU | retrieval for both arms, `t5_return.sh`, verifier probe | AWS role (S3), Phoenix optional; **no Claude key** except the one traced a5 probe |
| 6 | laptop | `scripts/t5_join.py` (verifies + extracts, then asks for the controls file), `scripts/t5_report.py` (A6 only at this point) | S3 download |
| 7 | owner | reads `reports/t5_a6.md` (**the 10 control candidates' top-5**), writes `data/controls_accepted.json` (5 ids), reads `reports/t5_output_mode.md` and the dry-run output; rules on the output mode as a status line on D-043; sets `generator.output_mode` in `configs/base.yaml`; reruns `scripts/t5_join.py` | |
| 8 | laptop | `scripts/t5_batch.py` (one Batch: 90 core requests + the supplement items x 3), re-run until collected | `ANTHROPIC_API_KEY`; Phoenix optional |
| 9 | laptop | `scripts/t5_report.py` (A4, variance, A7, claim yield) | nothing |

The key is never typed into a prompt or a chat. On the laptop, set it in PowerShell before
launching Claude Code / the script (`$env:ANTHROPIC_API_KEY = ...`) and check it with
`[bool]$env:ANTHROPIC_API_KEY` only. On the GPU box use `read -rs` (below).

## 1. Phoenix and tracing: what the laptop steps need

Steps 2, 4 and 8 (draft, dry run, Batch) emit spans. To see them:

1. Start the `ledger-phoenix` instance (us-east-1) and wait for the UI.
2. Add an inbound TCP 6006 rule on `ledger-phoenix-sg` for **your current public IP /32**
   (`curl https://checkip.amazonaws.com`). Never 0.0.0.0/0. Delete the rule when you stop.
3. `$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://54.160.244.106:6006"` — the **base** URL (the
   exporter appends `/v1/traces`; the banner's `/v1/traces` form belongs in the other variable).

**If you skip this, or the export fails, nothing is lost.** Spans are exported from a background
thread; an unreachable endpoint only logs warnings. The scripts wrap tracing init and shutdown so
an exporter exception is printed to stderr and swallowed, and every result file is written
*before* tracing is shut down (drafts: appended per reply; dry run: printed as it arrives; Batch:
written by the job ledger as results are collected). What you lose is the spans of that run; a
dead endpoint can add up to ~40 s at shutdown while the exporter gives up. The runs remain
reproducible from the files.

## 2. Laptop: draw

```powershell
conda deactivate          # CLAUDE.md: conda base must not be active
uv sync
uv run python scripts/t5_draw.py
```
Verifies `data/chunks.jsonl` against the lock header and writes `data/questions_draft_draw.json`
(D-043 item 1, reworded 2026-10-10): the sampling unit is the **chunk**; each stratum (table,
prose) is one seeded random order (`draw_seed` 20261009); a table chunk is skipped when its table
already has a candidate. It lists, in draw order, 26 primary table candidates (+6 reserve), 24
primary prose candidates (+6 reserve), and the **coverage supplement**: for each source that holds
eligible tables and has no primary table candidate, one further table item from that source in the
same order (+6 reserve). Composition by source and unit is printed and stored. Running it twice
gives identical bytes. The first (table-sampled) draw is kept in
`data/questions_draft_draw_run1.json` as the deviation record.

## 3. Laptop: drafts, owner check, finalize

```powershell
$env:ANTHROPIC_API_KEY = "..."      # set in PowerShell BEFORE launching anything that needs it
uv run python scripts/t5_draft.py
```
Appends to `data/questions_draft_candidates.jsonl` (gitignored), resumable: primary and reserve
candidates of both strata, the supplement candidates, and 10 control candidates. Check them **in
draw order** (`order_index`). For each line set `accept` to `true`/`false`, fill `checked_by`, and
fix `question`/`gold_answer` by hand if needed — **the gold answer must be an exact substring of the
gold chunk**.

* **Rejection and replacement:** a rejected candidate gets `accept: false` and the reason in
  `notes`; it is replaced by the next candidate in the same stratum's order (the reserve). Nothing
  is chosen by hand: the finalizer refuses unless the accepted items are the first 13 table, first
  12 prose (and the first supplement item per supplement source) after the logged rejections.
* **Controls:** accept every control candidate you consider a well-formed unanswerable question
  (at least 5); you choose the final 5 later, after reading their top-5.

```powershell
uv run python scripts/t5_finalize_questions.py
git add data/questions_draft.jsonl data/questions_draft_draw.json data/questions_draft_draw_run1.json
git commit -m "T5: owner-checked draft questions" ; git push
```
It writes `set: "draft"` (13 table + 12 prose, ids q001-q025), `set: "supplement"` (ids s001...) and
`set: "control_candidate"` (c001...). It refuses on: wrong counts, an out-of-order choice, a
rejection without a reason, a gold answer that is not an exact substring of its chunk, two
questions from one table (core and supplement together), a gold ID outside the lock, or an empty
`checked_by`. The 10 control candidates are all retrieved on the GPU, so rejecting one later needs
no second retrieval.

## 4. Laptop: sync dry run

```powershell
uv run python scripts/t5_dry_run.py
```
One question, once per output mode (`structured_output`, `strict_tool`), with the exact body the
Batch will carry. Prints stop_reason, input/output/thinking tokens, validation result, cited IDs.
The context is the gold chunk plus four same-unit chunks, **not** retrieved (retrieval has not run
yet); it tests the request shape and the parser, not answer quality. Look for: a 400 on either
shape (especially `output_config` with both `effort` and `format` under `thinking: between_tools`),
`thinking=0`, validation OK, cited IDs among the supplied five. The `input` token difference
between the two modes is the measured overhead `reports/t5_output_mode.md` could not state.

## 5. GPU session (one session: retrieval, upload, verifier probe)

Start Phoenix first (§1 step 1) if you want traces. Then:

1. Start the g6e instance (us-east-2b). Note its **new public IP** (released on stop).
2. Add inbound 6006 on `ledger-phoenix-sg` for `<that IP>/32` (§1 step 2).
3. Connect with EC2 Instance Connect as `ubuntu`, then `tmux new -s t5`.
4. Exports:
   ```bash
   export AWS_DEFAULT_REGION=us-east-1
   export HF_HOME=/home/ubuntu/LEDGER-cache
   export OTEL_EXPORTER_OTLP_ENDPOINT=http://54.160.244.106:6006
   cd ~/LEDGER && git pull --ff-only
   ```
   Confirm the idle alarm exists for this instance id (t4_runbook §3) before any GPU work.
   If `data/qdrant` or `data/chunks.jsonl` are missing (new instance), run
   `bash scripts/gpu_bootstrap.sh ledger-vkm-2026` and restore the index from
   `s3://ledger-vkm-2026/index/data-qdrant.tar.gz` (check its `.sha256`) — see t4_runbook §2/§7.
   Nothing may be running against `data/qdrant` (one process at a time).
5. The traced a5 probe (needs the key, for this one process only):
   ```bash
   read -rs K && ANTHROPIC_API_KEY="$K" uv run python scripts/a5_probe.py ; unset K
   ```
   Find its trace in Phoenix (project `ledger`). **No trace → stop before any GPU job** (wrong
   endpoint form). This is the only step on the box that touches a key.
6. Retrieval, both arms (no key read, no flag):
   ```bash
   uv run python scripts/t5_retrieve.py
   bash scripts/t5_return.sh ledger-vkm-2026
   ```
   Writes `results/t5/retrieval_primary.jsonl` and `retrieval_card.jsonl`, then uploads
   `t5-retrieval.tar.gz` and its `.sha256` to `s3://ledger-vkm-2026/t5/`. Note the printed sha.
7. Verifier probe (one verifier resident at a time; stops for a verifier whose pinned template
   cannot be found, and says so in the report):
   ```bash
   uv run python scripts/t5_verifier_probe.py
   aws s3 cp reports/t5_verifier_probe.md s3://ledger-vkm-2026/t5/t5_verifier_probe.md
   ```
   The probe fetches its templates at run time from the pinned sources listed in the report
   (github.com/Liyan06/MiniCheck at commit `b58b9fa69acbd1015ec970fa65dd752413a053d2`; the two
   models' READMEs at the revisions in `verifier.pilot_pins`) and records each file's sha256.
   It needs outbound HTTPS to raw.githubusercontent.com and huggingface.co.
8. Stop the instance (do not rely on the alarm), delete the 6006 /32 rule, stop Phoenix.
   **Keep idle stretches under ~50 minutes** (alarm: CPU < 5 % for 12 x 5 min).

## 6. Laptop: extract, A6, controls, join

```powershell
aws s3 cp s3://ledger-vkm-2026/t5/t5-retrieval.tar.gz .
aws s3 cp s3://ledger-vkm-2026/t5/t5-retrieval.tar.gz.sha256 .
aws s3 cp s3://ledger-vkm-2026/t5/t5_verifier_probe.md reports\t5_verifier_probe.md
uv run python scripts/t5_join.py --tarball t5-retrieval.tar.gz     # verifies + extracts, then stops (exit 3)
uv run python scripts/t5_report.py                                  # A6 only at this point
```
`t5_join.py` verifies the tarball's sha256 and extracts it; with `data/controls_accepted.json` not
yet written it stops there with exit code 3 and says what to do. `reports/t5_a6.md` has the
composition by source and unit in its header, the 25 drafts' recall@5 (Wilson interval), MRR and
the cause of every miss, the supplement items **separately**, and **all 10 control candidates'
top-5**. Per D-033 status 2026-10-09 the hybrid build is triggered only by recall@5 < 0.75 on the
drafts (7 or more misses of 25); otherwise A6 is descriptive.

Read the control candidates' top-5; keep the 5 whose top-5 contains no answer. Write
`data/controls_accepted.json` (tracked; commit it):
```json
{"checked_by": "<your name>", "question_ids": ["c001", "c003", "c004", "c007", "c009"]}
```
Then rerun `uv run python scripts/t5_join.py --tarball t5-retrieval.tar.gz`: it verifies the run
against this questions file and the lock, joins every text, verifies it against the lock, and
writes `results/t5/contexts.jsonl` for the 25 drafts, the supplement items and the 5 accepted
controls only (unaccepted candidates are never generated or reported). Rerun `t5_report.py` to
get the A6 report with the 5 accepted controls.

## 7. Owner: rule on the output mode

Read `reports/t5_output_mode.md` and the dry-run output; write the ruling as a status line on
D-043; set `generator.output_mode` in `configs/base.yaml`. Until then `t5_batch.py` and the
reports that need generation output refuse.

## 8. Laptop: the Batch of 90

```powershell
$env:ANTHROPIC_API_KEY = "..."
uv run python scripts/t5_batch.py        # one Batch: cells t5_baseline_r1..r3 at seed 1;
                                         # (25 + 5 + supplement items) x 3 runs
# wait (minutes to hours), then re-run the same command to collect:
uv run python scripts/t5_batch.py
uv run python scripts/t5_report.py       # A4, variance, claim yield on the 90 core requests;
                                         # A7 on all requests; t5_supplement.md separately
```
Safe to re-run at any point: the job ledger (`results/t5_jobs.jsonl`) never resubmits a recorded
batch. If a run died between the API accepting the batch and the ledger recording its id,
`find_batch` looks for it (sidecar `results/t5_batch_sidecar.jsonl`, batches created in the last
10 minutes plus the local-clock margin, matched on request count and custom IDs); if two batches
match it stops with `AmbiguousBatch` and you resolve by hand — never delete the ledger to "fix"
it. Run 1 (`t5_baseline_r1`) is the baseline of record and the input to T6.
