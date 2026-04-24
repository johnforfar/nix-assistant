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

# nix-reviewer-1.5b (v0.2a · current)

**A specialist 1.5B model fine-tuned to review Nix / NixOS / home-manager configurations.**

**Try it live:** [nix-assistant.build.openmesh.cloud](https://nix-assistant.build.openmesh.cloud) — paste any flake, NixOS module, or home-manager config and get structured findings with line-level fixes.

**Source:** [github.com/johnforfar/nix-assistant](https://github.com/johnforfar/nix-assistant) · **Dataset:** [OpenxAILabs/nix-reviewer-training](https://huggingface.co/datasets/OpenxAILabs/nix-reviewer-training) · **GGUF:** [OpenxAILabs/nix-reviewer-1.5b-GGUF](https://huggingface.co/OpenxAILabs/nix-reviewer-1.5b-GGUF)

---

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

Via Ollama (Q4_K_M, ~986 MB, CPU-friendly):

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

### Pinning a specific version

Every released version is a git tag on the HF repo. To pin:

```python
# fp16 LoRA adapter
PeftModel.from_pretrained(base, "OpenxAILabs/nix-reviewer-1.5b", revision="v0.1")  # or v0.2, v0.2a
```

```bash
# GGUF via git clone + checkout, then import into Ollama
git clone https://huggingface.co/OpenxAILabs/nix-reviewer-1.5b-GGUF
cd nix-reviewer-1.5b-GGUF && git checkout v0.1
```

`main` is always the latest version (currently **v0.2a**).

## Benchmark — versioned leaderboard

Test set: 25 hand-written cases across 5 mutation classes + 5 negative (non-Nix) inputs. Every version evaluated on the exact same set. Harness at [johnforfar/nix-assistant/tree/main/eval](https://github.com/johnforfar/nix-assistant/tree/main/eval).

| metric | v0 base Qwen 1.5B | v0 live `hermes3:3b` | v0.1 LoRA | v0.2 LoRA (3 ep.) | **v0.2a LoRA · live** |
|---|---:|---:|---:|---:|---:|
| schema_valid | 100% ¹ | 96% | 96% | 88% | **96%** |
| no_hallucinated_options | n/a ² | 88.9% | 100% | n/a ² | **100%** |
| **line_exact** | 0% | 20% | 90% | 50% ³ | **90%** |
| **severity_match** | 20% | 45% | 75% | 40% | **70%** |
| **message_keywords_hit** | 0% | 25% | 45% | 40% | **45%** |
| **empty_on_negative** | 0% | 0% | 0% | 100% ³ | **60%** |
| dialect_awareness | 100% | 100% | 100% | 100% | **100%** |
| avg latency (fp16 adapter, XPU) | 5.5 s | 18 s | 3.3 s | 2.0 s | **2.9 s** |

¹ Base Qwen's 100% schema_valid is illusory — every output triggered the review pipeline's escape-hatch fallback (valid shape, zero signal).
² Metric n/a when no option-path-shaped strings appear in the model's output.
³ v0.2 over-fit to refusal at 3 epochs — captured 100% of negatives but regressed line_exact to 50%. v0.2a re-trained the same data at 2 epochs to recover the balance.

**Headline finding — no hallucinated options across trained LoRA versions.** When v0.2a cites `services.*`, `programs.*`, or `environment.*`, that path exists in the real nixpkgs module tree. The review pipeline double-validates at inference time, so a hallucinated output would be rejected before reaching the user.

## Training (v0.2a)

- **Base**: `Qwen/Qwen2.5-Coder-1.5B-Instruct` (Apache-2.0)
- **Method**: LoRA — r=16, α=32, dropout=0.05, target modules `q_proj`, `k_proj`, `v_proj`, `o_proj`
- **Trainable parameters**: 4,358,144 (0.28% of 1.548 B)
- **Dataset**: [`OpenxAILabs/nix-reviewer-training`](https://huggingface.co/datasets/OpenxAILabs/nix-reviewer-training) — **1,187** synthesized (broken_config, structured_review) pairs
  - 471 `package_attr_path_drift`
  - 397 `syntax_error_missing_semicolon`
  - 282 `flake_arg_not_destructured`
  - **37 negatives** (non-Nix inputs with `completion: "[]"`)
- **Optimizer**: AdamW, lr 2e-4, cosine schedule, warmup 3%
- **Precision**: bf16
- **Epochs**: **2** (the critical lesson — see Version history below)
- **Effective batch size**: 16 (per-device 4 × grad-accum 4)
- **Hardware**: Intel Arc 140T iGPU (48 GB unified) via `torch-xpu` 2.11
- **Wall time**: 9 min 10 s
- **Final train loss**: 0.1788
- **Final mean token accuracy**: 99.9%

## Training data provenance

All pairs are **synthesized, not scraped**:

1. Pattern identified — e.g. "module body references `inputs.X` without destructuring `inputs` from function args".
2. N configurations generated exhibiting the pattern, varying surrounding context, package choices, signature variants.
3. Each synthesized config fed to `nix eval --json` inside a `nixos/nix` Docker container to capture the ground-truth error message, line number, and column.
4. Ideal review composed from the pattern's template + the oracle's real line/message.
5. For negative samples (non-Nix inputs), the oracle step is skipped and the completion is hardcoded to `[]`.
6. Pair rejected if (a) Nix produced no error where one was expected, (b) the error class differed from the pattern, or (c) the source hashed to an existing pair.

**No verbatim content from any forum thread, issue, chat log, or third-party
source appears in the dataset.** Pattern selection was informed by qualitative
analysis of public NixOS community discussions; that analysis did not produce
any text, config, or comment that entered the dataset.

## Version history

| tag | shipped? | highlight |
|---|---|---|
| **`v0.1`** | live 2026-04-23 → 2026-04-24 | First fine-tune. 445 pairs, 3 epochs. `line_exact` 20→90%. |
| **`v0.2`** | **not shipped** | 1187 pairs + first 37 negatives, 3 epochs. Hit 100% on refusal but over-fit — `line_exact` regressed to 50%. Published on HF at tag `v0.2` for reproducibility. |
| **`v0.2a`** | **live 2026-04-24 → present** | Same 1187 pairs as v0.2 at **2 epochs**. Kept v0.1's accuracy AND captured 60% of the negatives win. Best overall. |

**What v0.2 taught us:** with a narrow set of training patterns (3 of the 5 mutation classes in our test set), more training steps + a first exposure to `completion: "[]"` creates a low-loss attractor — the model learns to return `[]` when uncertain, including on out-of-distribution test cases. v0.2a's 2-epoch retrain left enough flexibility in the weights to still emit real findings while learning the refusal pattern for genuine negatives.

The v0.3 plan follows the lesson: add the missing 3 mutation-class synthesizers (`unknown_option`, `option_wrong_type`, `redundant_default`) + a full NixOS-module eval oracle **before** scaling data. All test-set classes become in-distribution; then larger data becomes leverage instead of a trap.

## Intended use

Review submitted Nix / NixOS / home-manager configurations at
[nix-assistant.build.openmesh.cloud](https://nix-assistant.build.openmesh.cloud).
The model is **narrow by design** — a specialist for an MoE swarm, not a
general-purpose chat model. It expects the system prompt:

```
You are nix-assistant. Review the Nix config and output ONLY a JSON array: [{"line":int,"severity":"error"|"warning"|"hint","message":str}]
```

Other prompts will work but output-shape reliability drops.

## Limitations and known failure modes

- **Pattern coverage is 3 of 15 planned classes.** Good on `package_attr_path_drift`, `syntax_error_missing_semicolon`, and `flake_arg_not_destructured`. On out-of-distribution classes (unknown_option, option_wrong_type, redundant_default), v0.2a usually returns `[]` — technically safer than hallucinating, but not helpful. v0.3 closes this gap.
- **Refusal is partial.** `empty_on_negative` at 60% — the model refuses Python, YAML, bash most of the time but occasionally hallucinates findings on prose or ambiguous inputs. Expanding the negatives pool in v0.3 targets this.
- **No cross-version awareness.** v0.2a doesn't know that `programs.git.settings` exists on unstable but not on 25.05. A `option_renamed_across_channels` pattern is on the v0.3+ roadmap.
- **Q4_K_M quantization drift** vs. the fp16 adapter is not yet precisely measured. Expected <3% on the benchmark but to be verified in v0.3.
- **Single context, single turn.** The model reviews one config at a time. It does not remember prior calls or conversation history.

## Evaluation code

The full benchmark harness is reproducible from the repo:
[johnforfar/nix-assistant](https://github.com/johnforfar/nix-assistant) →
`eval/` directory. Every row in the table above can be re-run via:

```bash
python -m eval.run --runner local_adapter \
  --dataset eval/dataset/v0_seed.jsonl \
  --out eval/results/v0.2a_qwen_1.5b_lora.json \
  --version v0.2a_qwen_1.5b_lora
```

Previous versions are replayable. The 25-case test set, the three baseline runners (`live_xnode`, `local_pipeline`, `local_adapter`), and the rescore utility all ship in the repo.

## Citation

```bibtex
@misc{nixreviewer2026,
  title        = {nix-reviewer-1.5b: A specialist Nix config reviewer},
  author       = {Forfar, John},
  year         = {2026},
  publisher    = {Hugging Face},
  howpublished = {\url{https://huggingface.co/OpenxAILabs/nix-reviewer-1.5b}},
  note         = {Apache-2.0. Fine-tuned from Qwen/Qwen2.5-Coder-1.5B-Instruct on synthetic (broken-config, review) pairs verified by the Nix evaluator.}
}
```

## License

Apache-2.0. See [LICENSE](https://github.com/johnforfar/nix-assistant/blob/main/LICENSE)
and [NOTICE](https://github.com/johnforfar/nix-assistant/blob/main/NOTICE) for full
attribution (upstream: Qwen2.5-Coder base model by Alibaba Cloud; nixpkgs training-pattern references by NixOS contributors).
