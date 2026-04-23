"""LoRA fine-tune Qwen2.5-Coder-1.5B-Instruct on nix-assistant training pairs.

Targets Intel Arc iGPU via torch.xpu (torch 2.11+xpu, no ipex-llm needed).

Usage:
  python -m train.finetune              # full run, 3 epochs, 500 pairs
  python -m train.finetune --smoke      # 1 epoch on first 30 pairs (pipeline check)
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
)
from trl import SFTTrainer, SFTConfig


SYSTEM_PROMPT = (
    "You are nix-assistant. Review the Nix config and output ONLY a JSON array: "
    "[{\"line\":int,\"severity\":\"error\"|\"warning\"|\"hint\",\"message\":str}]"
)


def format_example(ex: dict) -> dict:
    """Turn a (prompt, completion) row into a Qwen-style chat-formatted text field."""
    return {
        "text": (
            f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
            f"<|im_start|>user\n{ex['prompt']}<|im_end|>\n"
            f"<|im_start|>assistant\n{ex['completion']}<|im_end|>"
        )
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=r"C:\Users\johnny\models\Qwen2.5-Coder-1.5B-Instruct")
    ap.add_argument("--data", default="data/train_pairs.jsonl")
    ap.add_argument("--out", default="data/lora_out")
    ap.add_argument("--epochs", type=float, default=3.0)
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--grad-accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--lora-alpha", type=int, default=32)
    ap.add_argument("--max-seq", type=int, default=1024)
    ap.add_argument("--smoke", action="store_true",
                    help="1 epoch on first 30 pairs; validates pipeline without wasting GPU time")
    args = ap.parse_args(argv)

    print(f"[train] torch {torch.__version__}  xpu.available={torch.xpu.is_available()}")
    if not torch.xpu.is_available():
        print("[train] WARN: XPU not available — will fall back to CPU (slow)")
    else:
        print(f"[train] xpu device: {torch.xpu.get_device_name(0)}")

    # Data ---------------------------------------------------------------
    ds = load_dataset("json", data_files=args.data, split="train").map(format_example)
    if args.smoke:
        ds = ds.select(range(min(30, len(ds))))
        epochs = 1.0
    else:
        epochs = args.epochs
    print(f"[train] dataset: {len(ds)} rows, epochs={epochs}")

    # Model + tokenizer --------------------------------------------------
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=torch.bfloat16, trust_remote_code=True
    )
    if torch.xpu.is_available():
        model = model.to("xpu")

    # LoRA adapter -------------------------------------------------------
    model = get_peft_model(
        model,
        LoraConfig(
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
        ),
    )
    model.print_trainable_parameters()

    # Train --------------------------------------------------------------
    training_args = SFTConfig(
        output_dir=args.out,
        num_train_epochs=epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        bf16=True,
        logging_steps=5,
        save_steps=200,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        report_to="none",
        dataset_text_field="text",
        max_length=args.max_seq,
    )

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=ds,
        args=training_args,
    )

    trainer.train()
    trainer.save_model(args.out)
    tokenizer.save_pretrained(args.out)
    print(f"[train] adapter saved -> {args.out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
