# nix-assistant

An open-source assistant that helps anyone get their Nix config to work — flakes, NixOS configurations, home-manager, dev shells, derivations.

**Positioning:** for the whole Nix community, not Xnode-specific. Hosted on a sovereign Openmesh Xnode as proof of decentralised inference; the assistant itself is general-purpose.

**Master plan:** see [ENGINEERING/OPENXAI-NIX-RAG-PLAN.md](../ENGINEERING/OPENXAI-NIX-RAG-PLAN.md) for the full scope, phases, schema, and decision log.

## Layout (builds out as phases complete)

```
nix-assistant/
├── README.md
├── scrape/       # Phase 0 — SQLite-backed nixpkgs + community flake scraper (resumable)
├── dataset/      # Phase 1 + 2 — HF dataset export + (intent, answer) pair generation
├── train/        # Phase 3 — LoRA training + eval harness
└── serve/        # Phase 4 — RAG chatbot (sibling to openmesh-support-agent)
```

Nothing built yet. Current status: planning doc awaiting decisions (§12 of the plan).

## Artefacts (planned)

| Phase | Artefact | Home |
|---|---|---|
| 1 | `OpenxAILabs/nix-corpus` | HF dataset |
| 2 | `OpenxAILabs/nix-instruction-pairs` | HF dataset |
| 3 | `OpenxAILabs/nix-assistant-*` | HF model (base + per-channel LoRAs) |
| 4 | chat site | Xnode (sibling to `openmesh-support-agent`) |
