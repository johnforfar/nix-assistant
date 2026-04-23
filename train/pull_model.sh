#!/usr/bin/env bash
# Resumable HF model download. Re-run to continue from last byte.
#
# Usage:
#   bash train/pull_model.sh
#   bash train/pull_model.sh Qwen/Qwen2.5-Coder-3B-Instruct    # custom repo
set -euo pipefail

REPO="${1:-Qwen/Qwen2.5-Coder-1.5B-Instruct}"
DEST="C:/Users/johnny/models/${REPO##*/}"
mkdir -p "$DEST"

BASE="https://huggingface.co/${REPO}/resolve/main"
# Files required for LoRA training. Safetensors is the heavy one (~3GB on 1.5B).
FILES=(
  config.json
  tokenizer.json
  tokenizer_config.json
  vocab.json
  merges.txt
  generation_config.json
  model.safetensors
)

for f in "${FILES[@]}"; do
  echo "=== $f ==="
  curl -C - -L --fail -o "$DEST/$f" "$BASE/$f" || echo "[warn] $f failed or skipped"
done

echo
echo "done  -> $DEST"
du -sh "$DEST"
