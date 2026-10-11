# T5 runbook — draw, drafts, GPU retrieval, join, Batch, reports

Decisions behind this: D-041 (generator pins), D-042 (query instruction, two arms), D-043 (protocol),
D-033 status 2026-10-09 (how A6 is read), and the D-043 status lines of 2026-10-10 (output mode,
answer matching, controls, what "checked" means). Bucket: `ledger-vkm-2026`. Nothing here is run by the
build pass; every command below is the owner's.

## 0. Order, and what each step needs

| # | where | step | needs |
|---|---|---|---|
| 1 | laptop | `scripts/t5_draw.py` | nothing (no key, no S3, no Phoenix) |
| 2 | laptop | `scripts/t5_draft.py` (~51 sync Sonnet calls) | `ANTHROPIC_API_KEY`; Phoenix optional |
| 3 | laptop, by hand | owner checks the candidates in draw order (logging every rejection), then `scripts/t5_finalize_questions.py`, then commit + push `data/questions_draft.jsonl`, `data/questions_draft_draw.json` and `data/questions_draft_draw_run1.json` | nothing |
| 4 | GPU | retrieval for both arms, `t5_return.sh`, verifier probe | AWS role (S3), Phoenix optional; **no Claude key** except the one traced a5 probe |
| 5 | laptop | `scripts/t5_join.py` (verifies + extracts, then asks for the controls file), `scripts/t5_report.py` (A6 only at this point) | S3 download |
| 6 | owner | reads `reports/t5_a6.md` (**the 7 control candidates' top-5**) and writes `data/controls_accepted.json` by the rule of D-043 status 2026-10-10 (item 2); reruns `scripts/t5_join.py` | |
| 7 | laptop | `scripts/t5_dry_run.py`: the **harness check**, writes `reports/t5_harness_check.md` | `ANTHROPIC_API_KEY`; Phoenix optional |
| 8 | laptop | commit + push `data/controls_accepted.json` and `reports/t5_harness_check.md` | nothing |
| 9 | laptop | `scripts/t5_batch.py` (one Batch: 90 core requests + the supplement items x 3), re-run until collected | `ANTHROPIC_API_KEY`; Phoenix optional |
| 10 | laptop | `scripts/t5_report.py` (A4, variance, controls, A7, claim yield) | nothing |

The output mode is already ruled (D-043 status 2026-10-10, item 5: `structured_output`, set in
`configs/base.yaml`); the owner no longer rules on it. If the harness check or A4 fails, the status
line says what follows.

The key is never typed into a prompt or a chat. On the laptop, set it in PowerShell before
launching Claude Code / the script, with a prompt that keeps it out of the shell history
(PowerShell 5; there is no `-MaskInput`):

```powershell
$s = Read-Host -AsSecureString "key"; $env:ANTHROPIC_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)); Remove-Variable s
```

and check it with `[bool]$env:ANTHROPIC_API_KEY` only. On the GPU box use `read -rs` (below).

## 1. Phoenix and tracing: what the laptop steps need

Steps 2, 7 and 9 (draft, harness check, Batch) emit spans. To see them:

1. Start the `ledger-phoenix` instance (us-east-1) and wait for the UI.
2. Add an inbound TCP 6006 rule on `ledger-phoenix-sg` for **your current public IP /32**
   (`curl https://checkip.amazonaws.com`). Never 0.0.0.0/0. Delete the rule when you stop.
3. `$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://54.160.244.106:6006"` — the **base** URL (the
   exporter appends `/v1/traces`; the banner's `/v1/traces` form belongs in the other variable).

**If you skip this, or the export fails, nothing is lost.** Spans are exported from a background
thread; an unreachable endpoint only logs warnings. The scripts wrap tracing init and shutdown so
an exporter exception is printed to stderr and swallowed, and every result file is written
*before* tracing is shut down (drafts: appended per reply; harness check: the report is written first; Batch:
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
# set the key BEFORE launching anything that needs it (see section 0):
$s = Read-Host -AsSecureString "key"; $env:ANTHROPIC_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)); Remove-Variable s
uv run python scripts/t5_draft.py
```
Appends to `data/questions_draft_candidates.jsonl` (gitignored), resumable: primary and reserve
candidates of both strata, the supplement candidates, and the control candidates (10 drafted; 3 were rejected before
retrieval by a corpus string search, so the questions file carries 7: c001-c007). Check them **in
draw order** (`order_index`). For each line set `accept` to `true`/`false`, fill `checked_by`, and
fix `question`/`gold_answer` by hand if needed — **the gold answer must be an exact substring of the
gold chunk**.

* **Rejection and replacement:** a rejected candidate gets `accept: false` and the reason in
  `notes`; it is replaced by the next candidate in the same stratum's order (the reserve). Nothing
  is chosen by hand: the finalizer refuses unless the accepted items are the first 13 table, first
  12 prose (and the first supplement item per supplement source) after the logged rejections.
* **Controls:** accept every control candidate you consider a well-formed unanswerable question
  (at least 5; 7 were kept); you choose the final 5 later, after reading their top-5 (section 5).

```powershell
uv run python scripts/t5_finalize_questions.py
git add data/questions_draft.jsonl data/questions_draft_draw.json data/questions_draft_draw_run1.json
git commit -m "T5: owner-checked draft questions" ; git push
```
It writes `set: "draft"` (13 table + 12 prose, ids q001-q025), `set: "supplement"` (ids s001...) and
`set: "control_candidate"` (c001...). It refuses on: wrong counts, an out-of-order choice, a
rejection without a reason, a gold answer that is not an exact substring of its chunk, two
questions from one table (core and supplement together), a gold ID outside the lock, or an empty
`checked_by`. All 7 control candidates are retrieved on the GPU, so rejecting one later needs
no second retrieval.

## 4. GPU session (one session: retrieval, upload, verifier probe)

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

## 5. Laptop: extract, A6, controls, join

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
the cause of every miss, the supplement items **separately**, and **all 7 control candidates'
top-5**. For each A6 miss it also says whether the gold string occurs in a top-5 chunk. Per D-033 status 2026-10-09 the hybrid build is triggered only by recall@5 < 0.75 on the
drafts (7 or more misses of 25); otherwise A6 is descriptive.

Read the control candidates' top-5 (primary arm, file order c001-c007) and apply the rule of
D-043 status 2026-10-10 (item 2): reject a candidate only if a top-5 chunk states the asked
quantity for the asked entity and the asked period, and record that chunk's ID. The same series for
another period, or the same quantity for another entity, does not reject: accept it and tag it
`near_miss`. The first five not rejected are the controls. If fewer than five pass, **T5 stops** for
a further status line; no candidate is drafted or picked by hand. Write
`data/controls_accepted.json` (tracked; all seven candidates listed):
```json
{
  "checked_by": "<your name>",
  "question_ids": ["c001", "c002", "c003", "c005", "c006"],
  "candidates": [
    {"id": "c001", "decision": "accept", "reason": "...", "tag": null},
    {"id": "c004", "decision": "reject", "reason": "...", "tag": null, "rejecting_chunk_id": "<chunk id>"},
    {"id": "c007", "decision": "accept", "reason": "same series, other period", "tag": "near_miss"}
  ]
}
```
(`tag` is `near_miss` or null; `rejecting_chunk_id` only on a rejection; keys other than
`question_ids` and `checked_by` are ignored by the join.) Then rerun
`uv run python scripts/t5_join.py --tarball t5-retrieval.tar.gz`: it verifies the run against this
questions file and the lock, joins every text, verifies it against the lock, and writes
`results/t5/contexts.jsonl` for the 25 drafts, the supplement items and the 5 accepted controls
only. Unaccepted candidates are not in the Batch or the reports; the harness check (section 6)
generates them. Rerun `t5_report.py` to get the A6 report with the 5 accepted controls.

## 6. Laptop: harness check (after the controls choice, before the Batch)

```powershell
uv run python scripts/t5_dry_run.py
```
Needs the retrieval output (`results/t5/retrieval_primary.jsonl`), `data/controls_accepted.json`
and `generator.output_mode` set; it refuses otherwise. It sends one sync call per question, in the
configured output mode only (D-043 status 2026-10-10, item 5), with the exact body the Batch will
carry, for **s001 and each control candidate not accepted** (derived from the controls file; with 7
candidates and 5 accepted, three calls). The contexts are the primary arm's retrieved top-5 with
texts checked against the lock; nothing is hand-built and it reads nothing from the 25 drafts or
the 5 accepted controls. It writes `reports/t5_harness_check.md`: per question stop_reason, request
accepted, parse result, abstained, cited IDs among the supplied five, and input / output / thinking
tokens. **PASS** only if every call was accepted, ended `end_turn` and parsed. Look for a 400 (a
rejected `output_config` under `thinking: between_tools`), a `max_tokens` stop or a parse failure.

## 7. Laptop: commit the controls and the harness check

```powershell
git add data/controls_accepted.json reports/t5_harness_check.md
git commit -m "T5: controls accepted, harness check" ; git push
```
Do not start the Batch before the harness check reads PASS.

## 8. Laptop: the Batch of 90

```powershell
$s = Read-Host -AsSecureString "key"; $env:ANTHROPIC_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)); Remove-Variable s
uv run python scripts/t5_batch.py        # one Batch: cells t5_baseline_r1..r3 at seed 1;
                                         # (25 + 5 + supplement items) x 3 runs
# wait (minutes to hours), then re-run the same command to collect:
uv run python scripts/t5_batch.py
uv run python scripts/t5_report.py       # A4, variance, claim yield on the 90 core requests;
                                         # A7 on all requests; t5_supplement.md and t5_controls.md separately
```
Safe to re-run at any point: the job ledger (`results/t5_jobs.jsonl`) never resubmits a recorded
batch. If a run died between the API accepting the batch and the ledger recording its id,
`find_batch` looks for it (sidecar `results/t5_batch_sidecar.jsonl`, batches created in the last
10 minutes plus the local-clock margin, matched on request count and custom IDs); if two batches
match it stops with `AmbiguousBatch` and you resolve by hand — never delete the ledger to "fix"
it. Run 1 (`t5_baseline_r1`) is the baseline of record and the input to T6.
