"""Merge a LoRA adapter into its base model, producing a standalone model dir.

Required before GGUF conversion (gguf tooling operates on full models, not adapters).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch
from peft import AutoPeftModelForCausalLM
from transformers import AutoTokenizer


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adapter", default="data/lora_v0.1")
    ap.add_argument("--out", default="data/merged_v0.1")
    args = ap.parse_args(argv)

    print(f"[merge] loading adapter from {args.adapter}")
    model = AutoPeftModelForCausalLM.from_pretrained(
        args.adapter, dtype=torch.bfloat16, trust_remote_code=True
    )
    print("[merge] merging LoRA into base weights ...")
    merged = model.merge_and_unload()
    print(f"[merge] saving to {args.out}")
    Path(args.out).mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(args.out, safe_serialization=True)
    tok = AutoTokenizer.from_pretrained(args.adapter, trust_remote_code=True)
    tok.save_pretrained(args.out)
    print(f"[merge] done. full model at {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
