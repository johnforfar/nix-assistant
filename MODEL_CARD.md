---
license: apache-2.0
base_model: Qwen/Qwen2.5-Coder-1.5B-Instruct
tags:
  - nix
  - nixos
  - code-review
  - lora
  - fine-tuned
language:
  - en
pipeline_tag: text-generation
---

# nix-reviewer-1.5b (v0.1)

**A specialist 1.5B model fine-tuned to review Nix / NixOS / home-manager configurations.**

Given a broken Nix config, it emits a strict JSON array of review comments:

```json
[{"line": 4, "severity": "error",
  "message": "`vvim` is not a nixpkgs attribute — did you mean `vim`?"}]
```

The design goal is **non-slop**: every option path it cites is verified against
the real nixpkgs module tree, every line number comes from an actual Nix
evaluation, and format discipline is strict. "The first AI that can't lie
about Nix — because Nix itself is in the loop."

## Quick start

Via Ollama (Q4_K_M, ~1 GB):

```bash
ollama pull hf.co/OpenxAILabs/nix-reviewer-1.5b-GGUF:Q4_K_M
ollama run hf.co/OpenxAILabs/nix-reviewer-1.5b-GGUF:Q4_K_M '{ pkgs, ... }:
{
  environment.systemPackages = with pkgs; [ vim vvim ];
}'
```

Via transformers + the LoRA adapter (full precision):

```python
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

base = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-Coder-1.5B-Instruct", dtype=torch.bfloat16
)
model = PeftModel.from_pretrained(base, "OpenxAILabs/nix-reviewer-1.5b")
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-Coder-1.5B-Instruct")
```

## Benchmark (v0.1)

Test set: 25 hand-written cases across 5 mutation classes + 5 negative (non-Nix) inputs.
Tested on the exact same set: the live `nix-assistant.build.openmesh.cloud` deployment
using `hermes3:3b`, the base Qwen2.5-Coder-1.5B-Instruct, and this fine-tune.

| metric | v0 live `hermes3:3b` | v0 base Qwen 1.5B | **v0.1 LoRA** (this) |
|---|---:|---:|---:|
| schema_valid (output parses as `[{line, severity, message}]`) | 96% | 100% ¹ | 96% |
| **line_exact** (top finding points at real bug) | 20% | 0% | **90%** |
| **severity_match** | 45% | 20% | **75%** |
| **message_keywords_hit** (mentions the actual bug) | 25% | 0% | **45%** |
| **no_hallucinated_options** (cites only real NixOS options) | 88.9% | n/a ² | **100%** |
| empty_on_negative (returns `[]` for non-Nix input) | 0% | 0% | 0% ³ |
| dialect_awareness (respects NixOS vs. home-manager scope) | 100% | 100% | 100% |
| avg latency | 18 s | 5.5 s | **3.3 s** ⁴ |

¹ Base Qwen's 100% is illusory — every output triggered the review pipeline's
  escape-hatch fallback (no real review emitted, valid shape by coincidence).
² Base Qwen emitted no option-like paths, so the metric was not applicable.
³ Known gap — the training set had no negative (non-Nix) examples. Fixed in v0.2.
⁴ On Intel Arc 140T via `torch-xpu` + fp16 adapter. Quantized Q4_K_M on xnode CPU: ~5 s.

**Headline finding**: v0.1 never fabricates a NixOS option path (0 of 20 applicable
cases had a hallucinated path). Every cited `services.*` / `programs.*` / `environment.*`
exists in the nixpkgs module tree. The review pipeline also wraps this behavior at the
inference layer so even a hallucinated output would be rejected before reaching the user.

## Training

- **Base**: `Qwen/Qwen2.5-Coder-1.5B-Instruct` (Apache-2.0)
- **Method**: LoRA — r=16, α=32, dropout=0.05, target modules `q_proj`, `k_proj`, `v_proj`, `o_proj`
- **Trainable parameters**: 4,358,144 (0.28% of 1.548 B)
- **Dataset**: `OpenxAILabs/nix-reviewer-training` — 445 synthesized (broken_config, structured_review) pairs
- **Optimizer**: AdamW, lr 2e-4, cosine schedule, warmup 3%
- **Precision**: bf16
- **Epochs**: 3
- **Effective batch size**: 16 (per-device 4 × grad-accum 4)
- **Hardware**: Intel Arc 140T iGPU (48 GB unified) via `torch-xpu` 2.11
- **Wall time**: 5 min 4 s
- **Final train loss**: 0.2662
- **Final mean token accuracy**: 99.1%

## Training data provenance

All 445 training pairs are **synthesized, not scraped**:

1. Pattern identified — e.g. "`inputs.X` referenced in a module that didn't destructure `inputs` from its function args".
2. N configurations generated that exhibit the pattern, varying surrounding context, package choices, signature variants.
3. Each synthesized configuration fed to `nix eval` (via a `nixos/nix` Docker container) to capture the ground-truth error message, line number, and column.
4. Ideal review composed from the pattern's template + the oracle's real line/message.
5. Pair rejected if (a) Nix produced no error, (b) the error didn't match the pattern's expected class, or (c) the source hashed to an existing pair.

**No verbatim content from any forum thread, issue, chat log, or third-party
source appears in the dataset.** Pattern selection was informed by qualitative
analysis of public NixOS community discussions; that analysis did not produce
any text, config, or comment that entered the dataset.

Current patterns covered (3):

- `package_attr_path_drift` — typo or drift in a package attribute path (`vvim` for `vim`)
- `syntax_error_missing_semicolon` — missing `;` in an attrset body
- `flake_arg_not_destructured` — module references `inputs.X` without `inputs` in function args

v0.2 will add: `option_renamed_across_channels`, `module_namespace_mismatch`,
`missing_module_import`, and negative (non-Nix) examples.

## Intended use

Review submitted Nix / NixOS / home-manager configurations at
[nix-assistant.build.openmesh.cloud](https://nix-assistant.build.openmesh.cloud).
The model is **narrow by design** — a specialist for an MoE swarm, not a
general-purpose chat model.

## Limitations and known failure modes

- **Does not refuse non-Nix input.** Paste YAML, Python, or prose and v0.1 will
  still "review" it. v0.2 fixes this with negative training examples.
- **Pattern coverage is narrow in v0.1** (3 of 15 planned patterns). Errors
  outside these patterns will not surface correct line numbers; expect schema-
  valid but semantically weak reviews.
- **No cross-version awareness** — v0.1 doesn't detect "this option exists
  in NixOS 24.11 but was renamed in 25.05". v0.3 adds pin-aware review.
- **Q4_K_M quantization** introduces small quality drift vs. the fp16 adapter
  (not yet measured precisely; measured in the v0.2 benchmark).

## Evaluation code

The full benchmark harness is reproducible from the repo:
[johnforfar/nix-assistant](https://github.com/johnforfar/nix-assistant) →
`eval/` directory. Every metric computed by this table can be re-run via
`python -m eval.run --runner <name>`.

## Citation

```
@misc{nixreviewer2026,
  title        = {nix-reviewer-1.5b: A specialist Nix config reviewer},
  author       = {Forfar, John},
  year         = {2026},
  publisher    = {Hugging Face},
  howpublished = {\url{https://huggingface.co/OpenxAILabs/nix-reviewer-1.5b}},
  note         = {Apache-2.0. Fine-tuned from Qwen/Qwen2.5-Coder-1.5B-Instruct.}
}
```

## License

Apache-2.0. See [LICENSE](https://github.com/johnforfar/nix-assistant/blob/main/LICENSE)
and [NOTICE](https://github.com/johnforfar/nix-assistant/blob/main/NOTICE) for full
attribution.
