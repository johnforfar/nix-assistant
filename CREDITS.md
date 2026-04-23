# Credits

`nix-assistant` is an Apache-2.0-licensed open-source Nix config reviewer.
Built on the shoulders of several excellent projects.

## Authors

- **John Forfar** — lead author, training pipeline, evaluation harness,
  Openmesh deployment
- **OpenxAI / Openmesh** — infrastructure (Sovereign Xnode, `hermes-ollama`
  inference host), organizational home for the Hugging Face org
  (`OpenxAILabs`)

## Upstream

- **Qwen team at Alibaba Cloud** for
  [Qwen2.5-Coder-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct),
  the base model fine-tuned for this project.
- **NixOS contributors** for [`nixpkgs`](https://github.com/NixOS/nixpkgs) —
  the evaluator that acts as the ground-truth oracle for our training data,
  and the module corpus this reviewer is designed to understand.
- **@oppiliappan** ([statix](https://github.com/oppiliappan/statix)) and
  **@astro** ([deadnix](https://github.com/astro/deadnix)) for the
  deterministic linters we invoke before the LLM.
- **Georgi Gerganov** and the
  [llama.cpp](https://github.com/ggerganov/llama.cpp) contributors for
  GGUF quantization tooling.
- **Jeffrey Morgan** and the [Ollama](https://ollama.com) team for the
  inference runtime.
- **Intel** for `torch-xpu`, which made LoRA fine-tuning on an Arc iGPU
  tractable.

## Community

Thanks to the broader NixOS community — Discourse contributors, nixpkgs
maintainers, and forum moderators — whose public documentation, bug reports,
and solutions shaped the pattern catalog used to generate the training data.
We've tried hard not to make the kind of AI-generated Nix advice the
community has, rightly, expressed frustration with. If we've missed, please
file an issue.

## Contributions welcome

Issues and pull requests are welcomed at
[johnforfar/nix-assistant](https://github.com/johnforfar/nix-assistant)
under inbound-=-outbound licensing (Apache-2.0, no separate CLA).
