"""Inference runner: base Qwen + LoRA adapter loaded directly via transformers.

No RAG, no lint — pure model signal. Used for benchmarking v0.1-trained
adapters against v0 baselines. Model + adapter load lazily on first call.

Env vars:
  NIX_ASSISTANT_BASE     default: C:/Users/johnny/models/Qwen2.5-Coder-1.5B-Instruct
  NIX_ASSISTANT_ADAPTER  default: data/lora_v0.1
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


_BASE = os.environ.get("NIX_ASSISTANT_BASE",
                       r"C:\Users\johnny\models\Qwen2.5-Coder-1.5B-Instruct")
_ADAPTER = os.environ.get("NIX_ASSISTANT_ADAPTER", "data/lora_v0.1")

SYSTEM_PROMPT = (
    "You are nix-assistant. Review the Nix config and output ONLY a JSON array: "
    "[{\"line\":int,\"severity\":\"error\"|\"warning\"|\"hint\",\"message\":str}]"
)

_model = None
_tokenizer = None


def _load():
    global _model, _tokenizer
    if _model is not None:
        return
    _tokenizer = AutoTokenizer.from_pretrained(_BASE, trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(_BASE, dtype=torch.bfloat16, trust_remote_code=True)
    _model = PeftModel.from_pretrained(base, _ADAPTER)
    if torch.xpu.is_available():
        _model = _model.to("xpu")
    _model.eval()


@dataclass
class RunResult:
    ok: bool
    http_status: int | None
    raw_response: str
    parsed_comments: list[dict] | None
    latency_ms: float
    error: str | None


def run_one(source: str) -> RunResult:
    _load()
    msgs = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": source},
    ]
    prompt = _tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inputs = _tokenizer(prompt, return_tensors="pt").to(_model.device)
    t0 = time.monotonic()
    with torch.no_grad():
        out = _model.generate(**inputs, max_new_tokens=512, do_sample=False,
                              pad_token_id=_tokenizer.eos_token_id)
    latency_ms = (time.monotonic() - t0) * 1000
    raw = _tokenizer.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)

    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return RunResult(False, None, raw, None, latency_ms, "no JSON array in output")
    try:
        parsed = json.loads(m.group())
        if not isinstance(parsed, list):
            return RunResult(False, None, raw, None, latency_ms, "not a JSON array")
    except json.JSONDecodeError as e:
        return RunResult(False, None, raw, None, latency_ms, f"JSON decode: {e}")

    return RunResult(True, 200, raw, parsed, latency_ms, None)
