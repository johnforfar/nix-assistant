#!/usr/bin/env bash
# Ship v0.1: upload GGUF + adapter to HF, tag the repo, deploy to xnode.
#
# Requires:
#   HF_TOKEN in env (export HF_TOKEN=hf_...)
#   logged-in to your xnode: `om wallet status` + `om login ...` done earlier
#   cwd = /c/Users/johnny/Documents/nix-assistant
set -euo pipefail

: "${HF_TOKEN:?set HF_TOKEN before running. get one at https://huggingface.co/settings/tokens (needs write)}"

MODEL_REPO="OpenxAILabs/nix-reviewer-1.5b"
GGUF_REPO="OpenxAILabs/nix-reviewer-1.5b-GGUF"
DATASET_REPO="OpenxAILabs/nix-reviewer-training"
TAG="v0.1.0"

echo "=== 1/5  upload LoRA adapter (+ config, tokenizer) to $MODEL_REPO ==="
huggingface-cli upload "$MODEL_REPO" data/lora_v0.1 . \
  --repo-type=model --commit-message="v0.1 LoRA adapter"
# Also upload the merged fp16 weights for reproducibility
huggingface-cli upload "$MODEL_REPO" data/merged_v0.1 merged \
  --repo-type=model --commit-message="v0.1 merged fp16 weights"
huggingface-cli upload "$MODEL_REPO" repo/MODEL_CARD.md README.md \
  --repo-type=model

echo "=== 2/5  upload GGUF (f16 + Q4_K_M) to $GGUF_REPO ==="
huggingface-cli upload "$GGUF_REPO" data/nix-reviewer-1.5b-f16.gguf nix-reviewer-1.5b-f16.gguf \
  --repo-type=model
# Q4_K_M must be extracted from Ollama's store since ollama-create quantized it in place.
# Find it:
OLLAMA_STORE="$USERPROFILE/.ollama/models"
Q4_BLOB=$(find "$OLLAMA_STORE/blobs" -name 'sha256-*' -size +900M -size -1200M | head -1)
if [ -n "$Q4_BLOB" ]; then
  cp "$Q4_BLOB" data/nix-reviewer-1.5b-Q4_K_M.gguf
  huggingface-cli upload "$GGUF_REPO" data/nix-reviewer-1.5b-Q4_K_M.gguf nix-reviewer-1.5b-Q4_K_M.gguf \
    --repo-type=model
else
  echo "[warn] Q4_K_M GGUF not located in Ollama store; upload manually" >&2
fi

echo "=== 3/5  upload training dataset ==="
huggingface-cli upload "$DATASET_REPO" data/train_pairs.jsonl train_pairs.jsonl \
  --repo-type=dataset

echo "=== 4/5  commit + tag the repo ==="
cd repo
git add flake.nix LICENSE NOTICE CREDITS.md MODEL_CARD.md
git commit -m "v0.1: fine-tuned nix-reviewer-1.5b

Base: Qwen/Qwen2.5-Coder-1.5B-Instruct
Method: LoRA (r=16, alpha=32, target q/k/v/o_proj)
Training data: 445 synthesized pairs, Docker Nix oracle as ground truth
Benchmark: beats v0 baselines on every accuracy metric at 3x lower latency

See MODEL_CARD.md for the full table."
git tag -a "$TAG" -m "nix-reviewer v0.1 — first fine-tuned release"
git push origin main
git push origin "$TAG"
cd ..

echo "=== 5/5  deploy to xnode ==="
om --format json app deploy nix-assistant --flake "github:johnforfar/nix-assistant/$TAG"

echo
echo "=== done ==="
echo "  model : https://huggingface.co/$MODEL_REPO"
echo "  gguf  : https://huggingface.co/$GGUF_REPO"
echo "  data  : https://huggingface.co/datasets/$DATASET_REPO"
echo "  live  : https://nix-assistant.build.openmesh.cloud"
