#!/usr/bin/env bash
# GPU box bootstrap (T4). Target: AWS Deep Learning Base OSS Nvidia Driver GPU AMI, Ubuntu 24.04,
# 150 GB EBS root. Usage:  scripts/gpu_bootstrap.sh <bucket>
# Idempotent: every step is safe to rerun. Writes no key; reads none.
set -euo pipefail

BUCKET="${1:?usage: gpu_bootstrap.sh <bucket>}"
REPO_URL="https://github.com/Vishnu-K-Menon/LEDGER.git"
REPO_DIR="$HOME/LEDGER"
PHOENIX_PRIVATE="http://172.31.68.230:6006"   # the PRIVATE address (D-023); the Elastic IP is dropped silently in-VPC

echo "== NVIDIA driver"
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader

# D-011 status 2026-10-07: Qdrant file and model cache live on the EBS root, never the
# instance-store NVMe (wiped on every stop). Refuse if $HOME is on it.
if [ -d /opt/dlami/nvme ]; then
  home_dev="$(df --output=source "$HOME" | tail -n1)"
  nvme_dev="$(df --output=source /opt/dlami/nvme | tail -n1)"
  if [ "$home_dev" = "$nvme_dev" ] || [[ "$(readlink -f "$HOME")" == /opt/dlami/nvme* ]]; then
    echo "REFUSING: $HOME is on the instance store (/opt/dlami/nvme); it is wiped on stop." >&2
    exit 1
  fi
fi

command -v aws >/dev/null || { echo "REFUSING: aws CLI not found" >&2; exit 1; }

echo "== uv"
export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
uv --version

echo "== repo"
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$REPO_DIR"
fi
cd "$REPO_DIR"
git log --oneline -1

echo "== uv sync"
uv sync
uv run python -c "import torch; print('cuda available:', torch.cuda.is_available()); \
print('device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"

# HF cache on the EBS root, outside the repo.
export HF_HOME="$HOME/LEDGER-cache"
mkdir -p "$HF_HOME"
grep -qxF "export HF_HOME=$HF_HOME" "$HOME/.bashrc" || echo "export HF_HOME=$HF_HOME" >> "$HOME/.bashrc"
echo "HF_HOME=$HF_HOME"

echo "== corpus (chunks.jsonl only; manifest.jsonl comes from the clone)"
mkdir -p data
aws s3 cp "s3://$BUCKET/corpus/chunks.jsonl" data/chunks.jsonl
echo "sha256: $(sha256sum data/chunks.jsonl | cut -d' ' -f1)"
echo "lines:  $(wc -l < data/chunks.jsonl)"

echo
echo "Next, in this shell:"
echo "  export HF_HOME=$HF_HOME"
echo "  export OTEL_EXPORTER_OTLP_ENDPOINT=$PHOENIX_PRIVATE"
