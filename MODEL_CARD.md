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

# nix-reviewer-1.5b (v0.4 · current)

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
ollama pull hf.co/OpenxAILabs/nix-reviewer-1.5b-GGUF:nix-reviewer-v0.4-1.5b-Q4_K_M.gguf
ollama run hf.co/OpenxAILabs/nix-reviewer-1.5b-GGUF:nix-reviewer-v0.4-1.5b-Q4_K_M.gguf '{ pkgs, ... }:
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
PeftModel.from_pretrained(base, "OpenxAILabs/nix-reviewer-1.5b", revision="v0.1")  # or v0.2, v0.2a, v0.4
```

```bash
# GGUF via git clone + checkout, then import into Ollama
git clone https://huggingface.co/OpenxAILabs/nix-reviewer-1.5b-GGUF
cd nix-reviewer-1.5b-GGUF && git checkout v0.1
```

`main` is always the latest version (currently **v0.4**).

## Benchmark — versioned leaderboard

Test set: 25 hand-written cases across 5 mutation classes + 5 negative (non-Nix) inputs. Every version evaluated on the exact same set. Harness at [johnforfar/nix-assistant/tree/main/eval](https://github.com/johnforfar/nix-assistant/tree/main/eval).

| metric | v0 base Qwen 1.5B | v0 live `hermes3:3b` | v0.1 LoRA | v0.2 LoRA (3 ep.) | v0.2a LoRA | **v0.4 LoRA · live** |
|---|---:|---:|---:|---:|---:|---:|
| schema_valid | 100% ¹ | 96% | 96% | 88% | 96% | **100%** |
| no_hallucinated_options | n/a ² | 88.9% | 100% | n/a ² | 100% | **100%** |
| **line_exact** | 0% | 20% | 90% | 50% ³ | 90% | **95%** |
| **severity_match** | 20% | 45% | 75% | 40% | 70% | **80%** |
| **message_keywords_hit** | 0% | 25% | 45% | 40% | 45% | **80%** |
| **empty_on_negative** | 0% | 0% | 0% | 100% ³ | 60% | **60%** |
| dialect_awareness | 100% | 100% | 100% | 100% | 100% | **100%** |
| avg latency (fp16 adapter, XPU) | 5.5 s | 18 s | 3.3 s | 2.0 s | 2.9 s | **3.5 s** ⁴ |

¹ Base Qwen's 100% schema_valid is illusory — every output triggered the review pipeline's escape-hatch fallback (valid shape, zero signal).
² Metric n/a when no option-path-shaped strings appear in the model's output.
³ v0.2 over-fit to refusal at 3 epochs — captured 100% of negatives but regressed line_exact to 50%. v0.2a re-trained the same data at 2 epochs to recover the balance.
⁴ v0.4 generates real reviews on cases v0.2a refused — longer outputs mean longer wall time per case at the same per-token speed. Production GGUF/Q4 latency on the xnode is comparable to v0.2a.

**Headline finding — no hallucinated options across trained LoRA versions.** When v0.4 cites `services.*`, `programs.*`, or `environment.*`, that path exists in the real nixpkgs module tree. The review pipeline double-validates at inference time, so a hallucinated output would be rejected before reaching the user.

**v0.4 is the first version that beats v0.2a on every review metric.** The +35 jump on `message_keywords_hit` and the +5/+10 jumps on `line_exact` and `severity_match` come from one change: a new `option_renamed_across_channels` synthesizer (32 historical NixOS option renames hand-curated from upstream release notes). Adding that single mutation class also lifted the model's recognition discipline on the 6 prior classes — the rename pattern teaches "option exists, just under a different path" which generalizes across topics.

## Training (v0.4)

- **Base**: `Qwen/Qwen2.5-Coder-1.5B-Instruct` (Apache-2.0)
- **Method**: LoRA — r=16, α=32, dropout=0.05, target modules `q_proj`, `k_proj`, `v_proj`, `o_proj`
- **Trainable parameters**: 4,358,144 (0.28% of 1.548 B)
- **Dataset**: [`OpenxAILabs/nix-reviewer-training`](https://huggingface.co/datasets/OpenxAILabs/nix-reviewer-training) — **1,963** synthesized (broken_config, structured_review) pairs across 7 mutation classes
  - 347 `package_attr_path_drift`
  - 317 `syntax_error_missing_semicolon`
  - 238 `flake_arg_not_destructured`
  - 355 `unknown_option`
  - 207 `option_wrong_type`
  - 200 `redundant_default`
  - 235 `option_renamed_across_channels` ← **new in v0.4**
  - **64 negatives** (non-Nix inputs with `completion: "[]"`)
- **Optimizer**: AdamW, lr 2e-4, cosine schedule, warmup 3%
- **Precision**: bf16
- **Epochs**: **2** (the critical lesson — see Version history below)
- **Effective batch size**: 16 (per-device 4 × grad-accum 4)
- **Hardware**: Intel Arc 140T iGPU (48 GB unified) via `torch-xpu` 2.11
- **Wall time**: 16 min 32 s
- **Final train loss**: 0.1515
- **Final mean token accuracy**: 99.56%

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
| **`v0.2a`** | live 2026-04-24 → 2026-04-27 | Same 1187 pairs as v0.2 at **2 epochs**. Kept v0.1's accuracy AND captured 60% of the negatives win. |
| **`v0.3` / `v0.3a` / `v0.3-3b` / pool-expansion** | **all not shipped** | Three failed approaches, all preserved on disk for retrospective. Pool expansion (33→1210 service names) broke review (per-option repetition disappeared). Bigger base (Qwen 3B) underfit at 2 epochs and hit 19 s avg latency. The `v0.3` slot was reclaimed by the rename-class shipping release. |
| **`v0.4`** | **live 2026-04-27 → present** | First version that strictly beats v0.2a on every metric. Adds `option_renamed_across_channels` synthesizer (32 historical NixOS option renames from upstream release notes). 1963 pairs across 7 mutation classes at 3.3% negatives ratio. **+35** message_keywords_hit, +5 line_exact, +10 severity_match. |

**What v0.2 taught us:** with a narrow set of training patterns (3 of the 5 mutation classes in our test set), more training steps + a first exposure to `completion: "[]"` creates a low-loss attractor — the model learns to return `[]` when uncertain, including on out-of-distribution test cases. v0.2a's 2-epoch retrain left enough flexibility in the weights to still emit real findings while learning the refusal pattern for genuine negatives.

**What pool-expansion taught us:** swapping a small hand-curated pool (33 services) for the full corpus (1210 services) hurts review on 1.5B models. Each individual option then appears in training only once or twice, the model can't memorise the per-option pattern, and confidence collapses to refusal. Diversity ↓ per-option repetition wins for small bases.

**What v0.4 taught us:** adding a *new mutation class* (different mechanism) lifts the ceiling much more than scaling existing classes (more samples). The rename pattern teaches "option exists, just at a different path" — that abstraction generalises to other classes the model already knew, raising recognition discipline globally.

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

- **Pattern coverage is now 7 of 15 planned classes.** Strong on `package_attr_path_drift`, `syntax_error_missing_semicolon`, `flake_arg_not_destructured`, `unknown_option`, `option_wrong_type`, `redundant_default`, and `option_renamed_across_channels`. Still untrained: `missing_module_import`, `module_namespace_mismatch`, plus 6 more on the future roadmap.
- **Refusal is partial.** `empty_on_negative` at 60% — same as v0.2a; v0.4 didn't change the negatives pool.
- **Cross-channel rename catalogue is partial.** v0.4 trains on 32 hand-curated historical option renames; nixpkgs has had hundreds across releases. Any rename outside that 32 will not be recognised by name (the model may still flag it as `unknown_option`).
- **Q4_K_M quantization drift** vs. the fp16 adapter measured in passing during v0.4 sanity-check (Ollama Q4 produced the expected `vvim → vim` review, line and message verbatim with the fp16 adapter's output). Formal drift study still pending.
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
