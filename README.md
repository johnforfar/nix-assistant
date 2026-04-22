# nix-assistant

An open-source Nix config reviewer for the whole Nix community — paste any flake, NixOS config, home-manager module, or derivation and get structured lint findings + LLM prose advice.

**Live:** deployed on a sovereign Openmesh Xnode (xnode-1) at port 8080.

## How it works

```
Your Nix config
      │
      ▼
statix + deadnix ──→ deterministic lint findings
      │
      ▼
numpy cosine RAG ──→ top-5 similar nixpkgs/options docs
      │
      ▼
hermes3:3b (Ollama) ──→ prose review with line-level comments
```

- **Corpus**: 98k nixpkgs packages + 16k NixOS options scraped from nixpkgs unstable
- **Embeddings**: nomic-embed-text (768-dim) via Ollama, stored as numpy arrays
- **Model**: hermes3:3b running on shared Ollama instance (no second Ollama)
- **Lint**: statix + deadnix run deterministically before the LLM
- **Backend**: Flask on port 5000, proxied by nginx on port 8080

## Layout

```
nix-assistant/
├── flake.nix             # NixOS module — deploys to any xnode via om CLI
├── assistant/
│   ├── server.py         # Flask API — POST /api/review, GET /health
│   ├── review.py         # full pipeline: lint → retrieve → llm
│   ├── retrieve.py       # cosine RAG over numpy embeddings
│   ├── lint.py           # statix + deadnix runner
│   └── embed.py          # build the numpy vector index from corpus.db
├── scrape/
│   ├── scrape_nixpkgs.py # scrape nixpkgs packages into corpus.db
│   ├── scrape_options.py # scrape NixOS options into corpus.db
│   └── export_hf.py      # export corpus.db → parquet shards for HF Hub
└── frontend/
    └── index.html        # cyberpunk UI (Tron/NixOS blue)
```

## Deploy

```bash
# one-time: add to xnode
om --profile hermes app deploy nix-assistant --flake "github:johnforfar/nix-assistant/v0.1.1"

# push data after first deploy
scp scrape/data/corpus.db       <xnode>:/var/lib/nix-assistant/
scp -r assistant/data/embeddings <xnode>:/var/lib/nix-assistant/
```

Requires `om` CLI authenticated against an Openmesh Xnode.
The xnode must have a shared `hermes-ollama` container running `hermes3:3b` and `nomic-embed-text`.

## Build embeddings locally

```bash
# scrape (takes ~10 min)
python scrape/scrape_nixpkgs.py
python scrape/scrape_options.py

# embed (requires Ollama with nomic-embed-text, resumable)
python -m assistant.embed --db scrape/data/corpus.db --out assistant/data/embeddings
```

## API

```
POST /api/review
  { "source": "<nix config string>" }
  → { "comments": [{ "line": int, "severity": "error|warning|hint", "message": str }] }

GET /health
  → { "status": "ok", "model": "hermes3:3b" }
```

## Pre-built data

Embedding index (nomic-embed-text 768-dim, ~320MB) is published as a GitHub Release:

**[github.com/johnforfar/nix-assistant/releases/tag/data-v1](https://github.com/johnforfar/nix-assistant/releases/tag/data-v1)**

The NixOS service downloads it automatically on first boot via `ExecStartPre`. You don't need to push anything manually.

## Roadmap

- [ ] Export corpus to HuggingFace Hub (`OpenxAILabs/nix-corpus`)
- [ ] Scrape nixpkgs community flakes for broader coverage
- [ ] Upgrade to qwen2.5-coder:3b for better code understanding
- [ ] PR diff mode — review only changed files
