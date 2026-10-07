#!/usr/bin/env bash
# Copy the T4 results off the GPU box. Usage:  scripts/gpu_return.sh <bucket>
#   s3://<bucket>/lock/   data/chunk_ids.lock, data/index_meta.json, reports/a8.md
#   s3://<bucket>/index/  data-qdrant.tar.gz and its sha256
# The Qdrant folder admits one process at a time: nothing may be running against it.
set -euo pipefail

BUCKET="${1:?usage: gpu_return.sh <bucket>}"
cd "$HOME/LEDGER"

for f in data/chunk_ids.lock data/index_meta.json reports/a8.md; do
  [ -f "$f" ] || { echo "missing $f; run ledger loadtest / ledger index first" >&2; exit 1; }
done
[ -d data/qdrant ] || { echo "missing data/qdrant" >&2; exit 1; }

aws s3 cp data/chunk_ids.lock "s3://$BUCKET/lock/chunk_ids.lock"
aws s3 cp data/index_meta.json "s3://$BUCKET/lock/index_meta.json"
aws s3 cp reports/a8.md "s3://$BUCKET/lock/a8.md"

tar -C data -czf data-qdrant.tar.gz qdrant
sha="$(sha256sum data-qdrant.tar.gz | cut -d' ' -f1)"
echo "$sha  data-qdrant.tar.gz" > data-qdrant.tar.gz.sha256
aws s3 cp data-qdrant.tar.gz "s3://$BUCKET/index/data-qdrant.tar.gz"
aws s3 cp data-qdrant.tar.gz.sha256 "s3://$BUCKET/index/data-qdrant.tar.gz.sha256"
echo "tar sha256: $sha"
