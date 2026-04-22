"""Vector retrieval over the embedded corpus.

Loads index files lazily on first call and caches in memory.
"""
from __future__ import annotations

import json
import urllib.request
import os
from pathlib import Path
from typing import NamedTuple

import numpy as np

ROOT = Path(__file__).resolve().parent
EMB_DIR = Path(os.environ.get("NIX_ASSISTANT_DATA", str(ROOT / "data"))) / "embeddings"
OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"

_INDEX: dict[str, tuple[np.ndarray, list[dict]]] = {}


class Hit(NamedTuple):
    id: str
    text: str
    score: float


def _load(table: str) -> tuple[np.ndarray, list[dict]]:
    if table not in _INDEX:
        if table == "packages":
            npy = EMB_DIR / "packages.npy"
            meta_path = EMB_DIR / "packages_meta.json"
        else:
            npy = EMB_DIR / "nixos_options.npy"
            meta_path = EMB_DIR / "nixos_options_meta.json"
        if not npy.exists():
            raise FileNotFoundError(
                f"Embedding index not found: {npy}\n"
                "Run: python embed.py"
            )
        arr = np.load(str(npy))
        # Normalize rows for cosine similarity via dot product
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1
        arr = arr / norms
        with meta_path.open() as f:
            meta = json.load(f)
        _INDEX[table] = (arr, meta)
    return _INDEX[table]


def _embed_query(text: str, ollama_url: str = OLLAMA_URL) -> np.ndarray:
    body = json.dumps({"model": EMBED_MODEL, "input": [text]}).encode()
    req = urllib.request.Request(
        f"{ollama_url}/api/embed",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    vec = np.array(data["embeddings"][0], dtype=np.float32)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


def search(
    query: str,
    table: str = "packages",
    top_k: int = 5,
    ollama_url: str = OLLAMA_URL,
) -> list[Hit]:
    """Embed query and return top-k hits from the specified table."""
    arr, meta = _load(table)
    qvec = _embed_query(query, ollama_url)
    scores = arr @ qvec
    top_idx = np.argpartition(scores, -top_k)[-top_k:]
    top_idx = top_idx[np.argsort(scores[top_idx])[::-1]]
    return [Hit(meta[i]["id"], meta[i]["text"], float(scores[i])) for i in top_idx]


def search_multi(
    queries: list[str],
    top_k: int = 3,
    ollama_url: str = OLLAMA_URL,
) -> list[Hit]:
    """Search both tables with multiple queries, deduplicated by id."""
    seen: dict[str, Hit] = {}
    for query in queries:
        for table in ("packages", "nixos-options"):
            try:
                hits = search(query, table=table, top_k=top_k, ollama_url=ollama_url)
            except (FileNotFoundError, Exception):
                continue
            for h in hits:
                if h.id not in seen or h.score > seen[h.id].score:
                    seen[h.id] = h
    return sorted(seen.values(), key=lambda h: h.score, reverse=True)[:top_k * 2]
