# T4 runbook — GPU box: A8 load test, index build, lock

Run order matters: A8 runs **before** `ledger index` (D-012 status 2026-10-07: its first fallback
changes the embedder). The Qdrant file and model cache live on the EBS root, never on the
instance-store NVMe (D-011 status 2026-10-07). Bucket: `ledger-vkm-2026`.

The Qdrant folder (`data/qdrant`) admits **one process at a time**: do not run `ledger index`
while anything else (a Python shell, a probe, `loadtest`) holds it, and do not copy or tar the
folder while a process is running.

## 1. Laptop — record the corpus hash

```powershell
(Get-FileHash data\chunks.jsonl -Algorithm SHA256).Hash.ToLower()
```
Note it. (A CRLF checkout would differ from the S3 copy; `chunks.jsonl` is produced by ingest with
LF endings, and `scripts/verify_lock.py` normalises CRLF before hashing in any case.)

## 2. GPU box — inside tmux

```bash
tmux new -s t4        # reattach after a dropped connection: tmux attach -t t4
git clone https://github.com/Vishnu-K-Menon/LEDGER.git ~/LEDGER   # first time only; the script also clones
bash ~/LEDGER/scripts/gpu_bootstrap.sh ledger-vkm-2026
```
Compare the `sha256:` line it prints for `data/chunks.jsonl` with the laptop's. **Stop on any
difference**, and check the `lines:` count against the laptop's `data/chunks.jsonl`.

### GPU outside us-east-1 (D-011 status 2026-10-08)

- `export AWS_DEFAULT_REGION=us-east-1` before the bootstrap: the bucket is in us-east-1.
- The bootstrap prints the private Phoenix address; ignore it. Export
  `OTEL_EXPORTER_OTLP_ENDPOINT=http://54.160.244.106:6006` (Phoenix's public address) instead.
- At each start, add a 6006 rule on `ledger-phoenix-sg` for that start's public IP /32; delete it
  at each stop (the address is released on stop). Never 0.0.0.0/0.
- A stopped instance starts only in its own zone. On a capacity error, retry the start, or
  launch a new instance elsewhere and bootstrap it: nothing on the box is irreplaceable once the
  return step (7) has run.

## 3. Confirm the idle alarm exists for THIS instance id (CLAUDE.md: the one hard constraint)

The instance role's only policy grants S3 on the bucket, so `aws cloudwatch describe-alarms` is
not permitted from the box. Check the alarm in the console instead: EC2 -> the instance -> Status
and alarms. Alarm rule: average CPUUtilization < 5 % for 12 consecutive 5-minute periods -> stop
(D-011 status 2026-10-08). Print the instance id to match it:

```bash
curl -s -H "X-aws-ec2-metadata-token: $(curl -s -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" http://169.254.169.254/latest/meta-data/instance-id; echo
```
No alarm shown for that instance id -> **do not start GPU work.** In us-east-1 also confirm the
instance is in `vpc-0f3297a449901c109` (the private Phoenix address only works inside it).

## 4. Tracing endpoint and the A5 probe

```bash
cd ~/LEDGER
export HF_HOME=$HOME/LEDGER-cache
export OTEL_EXPORTER_OTLP_ENDPOINT=http://172.31.68.230:6006   # us-east-1 only: PRIVATE address (D-023), base only
# GPU box in us-east-2: use http://54.160.244.106:6006 instead (see "GPU outside us-east-1")
read -rs K && ANTHROPIC_API_KEY="$K" uv run python scripts/a5_probe.py ; unset K
```
`read -rs` keeps the key out of the prompt, the shell history and the environment of later
commands: it is set for the one probe process only, never `export`ed. Find the probe's trace in
Phoenix (project `ledger`). No trace after the probe → wrong endpoint form; stop (the in-VPC
Elastic IP fails silently).

## 5. A8

```bash
uv run ledger loadtest
```
Writes `reports/a8.md`. Read it: PASS needs nvidia-smi peak at the verify call ≤ 44.7 GiB.
GATED / NOT LOADED are not passes. If no candidate passes, **stop and report** — D-012's fallback
is the owner's call. Find the `ledger.loadtest` trace id (printed) in Phoenix.

## 6. Index

```bash
uv run ledger index
```
Refuses (listing offenders) on bad inputs or a lock mismatch; otherwise writes `data/qdrant`,
`data/index_meta.json`, and, last, `data/chunk_ids.lock`. Find the printed trace id in Phoenix.
A rerun after a failure is safe (the collection is dropped and rebuilt); once the lock exists, a
rerun rebuilds only if every chunk id and text hash equals it, and never rewrites the lock.

## 7. Return the artefacts

```bash
bash scripts/gpu_return.sh ledger-vkm-2026
```
Copies `chunk_ids.lock`, `index_meta.json`, `a8.md` to `s3://ledger-vkm-2026/lock/` and a tar of
`data/qdrant` plus its sha256 to `s3://ledger-vkm-2026/index/`. Then stop the instance (the idle
alarm is the backstop, not the plan).

## 8. Laptop

```powershell
aws s3 cp s3://ledger-vkm-2026/lock/chunk_ids.lock data\chunk_ids.lock
aws s3 cp s3://ledger-vkm-2026/lock/index_meta.json data\index_meta.json
aws s3 cp s3://ledger-vkm-2026/lock/a8.md reports\a8.md
uv run python scripts/verify_lock.py
```
If the laptop has no AWS CLI, download the three files from the S3 console, keeping their names,
and put them in `data\` and `reports\`. Never open the lock in an editor.
`verify_lock.py` exits non-zero on any difference in a chunk id, a chunk text hash, the record
count, or the hash of `chunks.jsonl` / `manifest.jsonl`. `.gitattributes` keeps the lock and meta
byte-exact (`-text`), so do not let an editor rewrite line endings.

The close-out pass (not this one) commits: `data/chunk_ids.lock` and `data/index_meta.json`
(both un-ignored), `reports/a8.md` (copied to a tracked location or force-added by the owner's
call, since `reports/*` is ignored), the decision entries for the A8 outcome and the index, the
`docs/plan.md` ticks, and `embedding`/`verifier` config values the results fix. The Qdrant tar
stays in S3.
