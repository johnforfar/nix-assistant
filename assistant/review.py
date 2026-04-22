"""Full review pipeline: lint → retrieve → prompt → LLM → structured comments.

review(nix_source) → list[Comment]
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field

from . import lint, retrieve

OLLAMA_URL = "http://localhost:11434"
# On the Xnode: pull qwen2.5-coder:3b  (2.5GB, fits alongside support-agent)
# For local dev: use whatever small model is available
LLM_MODEL = "llama3.2:1b"

SYSTEM_PROMPT = """\
You are nix-assistant, a code reviewer specialising in Nix and NixOS configurations.
You receive:
  1. A snippet of a Nix config file
  2. Lint findings from statix and deadnix (may be empty)
  3. Relevant context retrieved from the nixpkgs corpus

Your job: write clear, actionable inline review comments.
Rules:
- One comment per distinct issue. Be concise (1-3 sentences).
- Always reference the line number if known.
- Prefer specific fixes over vague advice.
- If there are no issues, say "No issues found." and stop.
- Output ONLY a JSON array of objects: [{\"line\": int, \"severity\": \"error\"|\"warning\"|\"hint\", \"message\": str}]
- No markdown, no explanations outside the JSON."""

FEW_SHOT = [
    {
        "role": "user",
        "content": json.dumps({
            "config": "{ config, pkgs, ... }:\n{\n  services.openssh.enable = false;\n  environment.systemPackages = with pkgs; [ vim ];\n}\n",
            "findings": [{"tool": "statix", "rule": "redundant_with_default", "line": 3, "message": "value is the same as the default"}],
            "context": [],
        }),
    },
    {
        "role": "assistant",
        "content": '[{"line": 3, "severity": "hint", "message": "services.openssh.enable = false is the NixOS default — remove this line to reduce noise."}]',
    },
    {
        "role": "user",
        "content": json.dumps({
            "config": "{ pkgs, ... }:\nlet\n  unused = pkgs.hello;\nin {\n  environment.systemPackages = [ pkgs.vim ];\n}\n",
            "findings": [{"tool": "deadnix", "rule": "dead_code", "line": 3, "message": "unused binding: unused"}],
            "context": [],
        }),
    },
    {
        "role": "assistant",
        "content": '[{"line": 3, "severity": "warning", "message": "unused is defined but never referenced — remove it or use it in systemPackages."}]',
    },
]


@dataclass
class Comment:
    line: int
    severity: str
    message: str


def _build_user_message(
    nix_source: str,
    findings: list[lint.Finding],
    hits: list[retrieve.Hit],
) -> str:
    return json.dumps({
        "config": nix_source,
        "findings": [
            {
                "tool": f.tool,
                "rule": f.rule,
                "line": f.line,
                "message": f.message,
                **({"suggestion": f.suggestion} if f.suggestion else {}),
            }
            for f in findings
        ],
        "context": [{"id": h.id, "text": h.text} for h in hits],
    })


def _call_llm(messages: list[dict], ollama_url: str = OLLAMA_URL) -> str:
    body = json.dumps({
        "model": LLM_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 2048},
        "think": False,  # disable reasoning mode on Qwen3/thinking models
    }).encode()
    req = urllib.request.Request(
        f"{ollama_url}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    content = data["message"].get("content", "")
    # Fallback: some Ollama builds surface thinking-only responses differently
    if not content.strip():
        content = data["message"].get("thinking", "")
    return content


def _parse_comments(raw: str) -> list[Comment]:
    # Strip <think>...</think> blocks that Qwen3 emits in reasoning mode
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    # Extract first JSON array from the response
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return [Comment(line=0, severity="hint", message=raw.strip()[:500])]
    try:
        items = json.loads(m.group())
        return [
            Comment(
                line=int(item.get("line", 0)),
                severity=item.get("severity", "warning"),
                message=item.get("message", ""),
            )
            for item in items
            if isinstance(item, dict)
        ]
    except (json.JSONDecodeError, TypeError):
        return [Comment(line=0, severity="hint", message=raw.strip()[:500])]


def review(
    nix_source: str,
    ollama_url: str = OLLAMA_URL,
    llm_model: str = LLM_MODEL,
) -> list[Comment]:
    """Run the full review pipeline on a Nix source string."""
    global LLM_MODEL
    LLM_MODEL = llm_model

    # 1. Lint
    findings = lint.run(nix_source)

    # 2. Retrieve — build queries from findings + first few words of config
    queries = [f"{f.rule} {f.message}" for f in findings[:5]]
    # Also query for any attr paths referenced in the config
    attr_refs = re.findall(r'[\w.]+\.\w+', nix_source)[:5]
    queries.extend(attr_refs)
    hits = retrieve.search_multi(queries[:8], top_k=3, ollama_url=ollama_url) if queries else []

    # 3. Prompt
    user_msg = _build_user_message(nix_source, findings, hits)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *FEW_SHOT,
        {"role": "user", "content": user_msg},
    ]

    # 4. LLM
    raw = _call_llm(messages, ollama_url)

    # 5. Parse
    return _parse_comments(raw)
