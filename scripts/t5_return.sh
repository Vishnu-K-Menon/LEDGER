#!/usr/bin/env bash
# Package the T5 retrieval files and copy them off the GPU box. Usage:  scripts/t5_return.sh <bucket>
#   s3://<bucket>/t5/t5-retrieval.tar.gz  and its .sha256   (results/t5/retrieval_*.jsonl)
# Runs on the box with the instance role (the gpu_return.sh pattern). Reads no key, writes no key.
set -euo pipefail

BUCKET="${1:?usage: t5_return.sh <bucket>}"
cd "$HOME/LEDGER"

for arm in primary card; do
  [ -f "results/t5/retrieval_${arm}.jsonl" ] || { echo "missing results/t5/retrieval_${arm}.jsonl; run scripts/t5_retrieve.py first" >&2; exit 1; }
done

tar -C results -czf t5-retrieval.tar.gz t5/retrieval_primary.jsonl t5/retrieval_card.jsonl
sha="$(sha256sum t5-retrieval.tar.gz | cut -d' ' -f1)"
echo "$sha  t5-retrieval.tar.gz" > t5-retrieval.tar.gz.sha256
aws s3 cp t5-retrieval.tar.gz "s3://$BUCKET/t5/t5-retrieval.tar.gz"
aws s3 cp t5-retrieval.tar.gz.sha256 "s3://$BUCKET/t5/t5-retrieval.tar.gz.sha256"
echo "tar sha256: $sha"
