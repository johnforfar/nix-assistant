"""Generate repo/frontend/index.html with the leaderboard chart base64-embedded.

Run:  python3 train/build_frontend.py
Output: repo/frontend/index.html
"""
from __future__ import annotations

import base64
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHART_PNG = ROOT / "eval" / "chart" / "leaderboard.png"
OUT_HTML = ROOT / "repo" / "frontend" / "index.html"


HTML_TEMPLATE = """<!doctype html>
<html lang="en" class="h-full">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>nix-assistant — Nix config reviewer</title>
  <meta name="description" content="An open-source Nix config reviewer. Paste any flake, NixOS config, or home-manager module and get structured findings with line-level fixes." />
  <script>
    // FOUC-prevention: set dark class before body renders
    (function() {{
      var saved = localStorage.getItem('nix-assistant-theme');
      var prefers = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      var dark = saved ? saved === 'dark' : prefers;
      if (dark) document.documentElement.classList.add('dark');
    }})();
  </script>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <script>
    tailwind.config = {{ darkMode: 'class' }};
  </script>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
  <style>
    html, body {{ font-family: 'Inter', system-ui, -apple-system, sans-serif; }}
    code, pre, textarea {{ font-family: 'JetBrains Mono', ui-monospace, monospace; }}
  </style>
</head>
<body class="bg-neutral-50 text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100 antialiased">
  <!-- nav -->
  <header class="border-b border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900">
    <div class="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
      <div class="flex items-center gap-2 font-semibold">
        <span class="inline-block w-2 h-2 rounded-full bg-blue-600"></span>
        <span>nix-assistant</span>
        <span class="ml-2 text-xs font-normal text-neutral-500">v0.2a · live</span>
      </div>
      <nav class="flex items-center gap-5 text-sm text-neutral-600 dark:text-neutral-400">
        <a class="hover:text-neutral-900 dark:hover:text-neutral-100" href="#review">Review</a>
        <a class="hover:text-neutral-900 dark:hover:text-neutral-100" href="#benchmark">Benchmark</a>
        <a class="hover:text-neutral-900 dark:hover:text-neutral-100 hidden sm:inline" href="#pipeline">How it works</a>
        <a class="hover:text-neutral-900 dark:hover:text-neutral-100 hidden sm:inline" href="#run-locally">Run locally</a>
        <a class="hover:text-neutral-900 dark:hover:text-neutral-100 hidden sm:inline" href="#feedback">Feedback</a>
        <a class="hover:text-neutral-900 dark:hover:text-neutral-100" href="https://huggingface.co/OpenxAILabs">HuggingFace ↗</a>
        <a class="hover:text-neutral-900 dark:hover:text-neutral-100" href="https://github.com/johnforfar/nix-assistant">GitHub ↗</a>
        <button id="theme-toggle" aria-label="Toggle theme"
          class="flex items-center justify-center w-8 h-8 rounded-md border border-neutral-200 dark:border-neutral-800 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition">
          <!-- moon (shown in light mode) -->
          <svg class="w-4 h-4 dark:hidden" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
          </svg>
          <!-- sun (shown in dark mode) -->
          <svg class="w-4 h-4 hidden dark:block" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="4"/>
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>
          </svg>
        </button>
      </nav>
    </div>
  </header>

  <main class="max-w-6xl mx-auto px-6 py-10 space-y-16">

    <!-- hero -->
    <section class="space-y-3">
      <div class="inline-flex items-center gap-2 text-xs font-medium px-2.5 py-1 rounded-full bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 border border-neutral-200 dark:border-neutral-800">
        <span class="w-1.5 h-1.5 rounded-full bg-green-500"></span>
        Live · Sovereign Xnode · No cloud API calls
      </div>
      <h1 class="text-3xl sm:text-4xl font-semibold tracking-tight">Review any Nix config, get structured findings.</h1>
      <p class="text-neutral-600 dark:text-neutral-400 max-w-2xl">
        Paste a flake, a NixOS module, or a home-manager config. <code class="text-sm bg-neutral-100 dark:bg-neutral-800 px-1.5 py-0.5 rounded">statix</code> and <code class="text-sm bg-neutral-100 dark:bg-neutral-800 px-1.5 py-0.5 rounded">deadnix</code> run first; findings are augmented with RAG over 98k+ nixpkgs entries and 16k NixOS options; a small local LLM turns it all into line-by-line review comments. Open source, Apache-2.0.
      </p>
    </section>

    <!-- review panel -->
    <section id="review" class="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 shadow-sm">
      <div class="p-5 border-b border-neutral-200 dark:border-neutral-800 flex items-center justify-between">
        <div>
          <h2 class="font-semibold">Paste your config</h2>
          <p class="text-xs text-neutral-500 mt-0.5">flake.nix · configuration.nix · home.nix — up to 128 KB</p>
        </div>
        <span class="text-xs text-neutral-400 dark:text-neutral-500">⌘/Ctrl + Enter to run</span>
      </div>
      <div class="p-5">
        <div class="relative rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-950 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/20 overflow-hidden">
          <div id="gutter" class="absolute top-0 left-0 bottom-0 w-10 pt-4 pr-2 text-right text-xs leading-6 text-neutral-400 dark:text-neutral-500 bg-neutral-100 dark:bg-neutral-900 border-r border-neutral-200 dark:border-neutral-800 font-mono select-none pointer-events-none overflow-hidden">1</div>
          <textarea id="src" rows="12" spellcheck="false"
            class="w-full text-sm pl-14 pr-4 py-4 leading-6 bg-transparent text-neutral-800 dark:text-neutral-200 focus:outline-none resize-y block"
            placeholder="{{ config, pkgs, ... }}:
{{
  services.openssh.enable = true;
  environment.systemPackages = with pkgs; [ vim ];
}}"></textarea>
        </div>
        <div class="mt-4 flex items-center gap-3">
          <button id="btn" onclick="doReview()"
            class="inline-flex items-center gap-2 text-sm font-medium px-4 h-9 rounded-md bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900 hover:bg-neutral-800 dark:hover:bg-neutral-300 focus:outline-none focus:ring-2 focus:ring-neutral-900/20 disabled:opacity-50 disabled:cursor-not-allowed transition">
            Review
          </button>
          <span id="status" class="text-xs text-neutral-500"></span>
        </div>
        <div id="results" class="mt-5 space-y-2"></div>
      </div>
    </section>

    <!-- benchmark -->
    <section id="benchmark" class="space-y-5">
      <div class="flex items-end justify-between flex-wrap gap-4">
        <div>
          <div class="text-xs font-medium uppercase tracking-wider text-blue-600 dark:text-blue-400">Evaluation</div>
          <h2 class="text-2xl font-semibold tracking-tight mt-1">Benchmark — every version on the same 25 cases</h2>
          <p class="text-neutral-600 dark:text-neutral-400 mt-1 max-w-2xl text-sm">
            We run the same 25-case test suite against every version. No version ships unless it's an honest step forward on real metrics — line-exactness, severity match, no hallucinated options.
          </p>
        </div>
        <a href="https://github.com/johnforfar/nix-assistant/tree/main/eval"
           class="text-sm font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300">Benchmark code →</a>
      </div>

      <div class="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 shadow-sm overflow-hidden">
        <div class="p-5 bg-neutral-50 dark:bg-neutral-950 border-b border-neutral-200 dark:border-neutral-800">
          <div class="relative h-96">
            <canvas id="benchmark-chart"></canvas>
          </div>
          <p class="text-xs text-neutral-500 mt-3 text-center">Hover a point to see why that version shipped (or didn't).</p>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-neutral-200 dark:border-neutral-800 text-left text-xs uppercase tracking-wide text-neutral-500">
                <th class="px-5 py-3 font-medium">Metric</th>
                <th class="px-5 py-3 font-medium text-right">v0 base Qwen 1.5B</th>
                <th class="px-5 py-3 font-medium text-right">v0 live (hermes3:3b)</th>
                <th class="px-5 py-3 font-medium text-right">v0.1 LoRA</th>
                <th class="px-5 py-3 font-medium text-right">v0.2 LoRA (3 ep.)</th>
                <th class="px-5 py-3 font-medium text-right bg-blue-50 dark:bg-blue-950/40 text-blue-900 dark:text-blue-200">v0.2a LoRA · live</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-neutral-100 dark:divide-neutral-800">
              <tr><td class="px-5 py-3 text-neutral-700 dark:text-neutral-300">schema_valid</td><td class="px-5 py-3 text-right tabular-nums text-neutral-500">100%<sup>†</sup></td><td class="px-5 py-3 text-right tabular-nums">96%</td><td class="px-5 py-3 text-right tabular-nums">96%</td><td class="px-5 py-3 text-right tabular-nums">88%</td><td class="px-5 py-3 text-right tabular-nums bg-blue-50 dark:bg-blue-950/40 font-medium">96%</td></tr>
              <tr><td class="px-5 py-3 text-neutral-700 dark:text-neutral-300">no_hallucinated_options</td><td class="px-5 py-3 text-right tabular-nums text-neutral-400 dark:text-neutral-500">n/a</td><td class="px-5 py-3 text-right tabular-nums">88.9%</td><td class="px-5 py-3 text-right tabular-nums text-green-700 dark:text-green-400">100%</td><td class="px-5 py-3 text-right tabular-nums text-neutral-400 dark:text-neutral-500">n/a</td><td class="px-5 py-3 text-right tabular-nums bg-blue-50 dark:bg-blue-950/40 font-medium text-green-700 dark:text-green-400">100%</td></tr>
              <tr><td class="px-5 py-3 text-neutral-700 dark:text-neutral-300 font-medium">line_exact</td><td class="px-5 py-3 text-right tabular-nums">0%</td><td class="px-5 py-3 text-right tabular-nums">20%</td><td class="px-5 py-3 text-right tabular-nums text-green-700 dark:text-green-400">90%</td><td class="px-5 py-3 text-right tabular-nums">50%</td><td class="px-5 py-3 text-right tabular-nums bg-blue-50 dark:bg-blue-950/40 font-semibold text-green-700 dark:text-green-400">90%</td></tr>
              <tr><td class="px-5 py-3 text-neutral-700 dark:text-neutral-300 font-medium">severity_match</td><td class="px-5 py-3 text-right tabular-nums">20%</td><td class="px-5 py-3 text-right tabular-nums">45%</td><td class="px-5 py-3 text-right tabular-nums text-green-700 dark:text-green-400">75%</td><td class="px-5 py-3 text-right tabular-nums">40%</td><td class="px-5 py-3 text-right tabular-nums bg-blue-50 dark:bg-blue-950/40 font-semibold text-green-700 dark:text-green-400">70%</td></tr>
              <tr><td class="px-5 py-3 text-neutral-700 dark:text-neutral-300 font-medium">message_keywords_hit</td><td class="px-5 py-3 text-right tabular-nums">0%</td><td class="px-5 py-3 text-right tabular-nums">25%</td><td class="px-5 py-3 text-right tabular-nums">45%</td><td class="px-5 py-3 text-right tabular-nums">40%</td><td class="px-5 py-3 text-right tabular-nums bg-blue-50 dark:bg-blue-950/40 font-semibold">45%</td></tr>
              <tr><td class="px-5 py-3 text-neutral-700 dark:text-neutral-300">empty_on_negative</td><td class="px-5 py-3 text-right tabular-nums">0%</td><td class="px-5 py-3 text-right tabular-nums">0%</td><td class="px-5 py-3 text-right tabular-nums">0%</td><td class="px-5 py-3 text-right tabular-nums text-green-700 dark:text-green-400">100%<sup>‡</sup></td><td class="px-5 py-3 text-right tabular-nums bg-blue-50 dark:bg-blue-950/40 text-green-700 dark:text-green-400">60%</td></tr>
              <tr><td class="px-5 py-3 text-neutral-700 dark:text-neutral-300">avg latency</td><td class="px-5 py-3 text-right tabular-nums">5.5 s</td><td class="px-5 py-3 text-right tabular-nums">18 s</td><td class="px-5 py-3 text-right tabular-nums">3.3 s</td><td class="px-5 py-3 text-right tabular-nums">2.0 s</td><td class="px-5 py-3 text-right tabular-nums bg-blue-50 dark:bg-blue-950/40 font-medium">2.9 s</td></tr>
            </tbody>
          </table>
        </div>
        <p class="px-5 py-3 text-xs text-neutral-500 border-t border-neutral-100 dark:border-neutral-800">
          <sup>†</sup> base Qwen's 100% is illusory — every output triggered the review pipeline's escape-hatch fallback (no real review emitted, valid shape by coincidence). <sup>‡</sup> v0.2 achieved 100% on negatives but over-fit to refusal (3 epochs), regressing line_exact 90→50. v0.2a re-trained with 2 epochs kept the accuracy and captured 60% of the negatives win — <strong>live on xnode</strong>. Headline across the ladder: <strong>line_exact: 0% → 20% → 90%</strong> and <strong>no_hallucinated_options: 100%</strong> from the trained LoRA onward — the model never cites a NixOS option path that doesn't exist in the real module tree.
        </p>
      </div>

      <!-- slop showcase: one-case comparison -->
      <div class="grid sm:grid-cols-2 gap-4">
        <div class="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 shadow-sm">
          <div class="text-xs font-medium uppercase tracking-wider text-red-600 dark:text-red-400">v0 baseline · wrong</div>
          <div class="text-sm text-neutral-600 dark:text-neutral-400 mt-1">Input: <code class="text-xs bg-neutral-100 dark:bg-neutral-800 px-1.5 py-0.5 rounded">environment.systemPackages = [ fooo ];</code></div>
          <pre class="mt-3 text-xs bg-neutral-50 dark:bg-neutral-950 border border-neutral-200 dark:border-neutral-800 rounded-md p-3 overflow-x-auto leading-5 text-neutral-700 dark:text-neutral-300">line 0 · hint
  texlive: Consider using texliveConTeXt
  for TeX Live environment.</pre>
          <p class="text-xs text-neutral-500 mt-2">Never mentions <code class="text-xs">fooo</code>. Hallucinates texlive. Classic slop.</p>
        </div>
        <div class="rounded-xl border border-blue-200 dark:border-blue-900 bg-blue-50/30 dark:bg-blue-950/30 p-5 shadow-sm">
          <div class="text-xs font-medium uppercase tracking-wider text-green-700 dark:text-green-400">v0.1 trained · correct</div>
          <div class="text-sm text-neutral-600 dark:text-neutral-400 mt-1">Same input.</div>
          <pre class="mt-3 text-xs bg-white dark:bg-neutral-900 border border-blue-200 dark:border-blue-900 rounded-md p-3 overflow-x-auto leading-5 text-neutral-800 dark:text-neutral-200">line 3 · error
  `fooo` is not a nixpkgs attribute
  — did you mean `vim`?</pre>
          <p class="text-xs text-neutral-500 mt-2">Right line. Right severity. Names the bug. Suggests the fix.</p>
        </div>
      </div>
    </section>

    <!-- pipeline -->
    <section id="pipeline" class="space-y-5">
      <div>
        <div class="text-xs font-medium uppercase tracking-wider text-blue-600 dark:text-blue-400">Methodology</div>
        <h2 class="text-2xl font-semibold tracking-tight mt-1">How it works</h2>
      </div>
      <div class="grid md:grid-cols-3 gap-4">
        <div class="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 shadow-sm">
          <div class="text-xs font-medium text-neutral-500">1. Lint</div>
          <div class="font-medium mt-1">statix + deadnix</div>
          <p class="text-sm text-neutral-600 dark:text-neutral-400 mt-2">Deterministic linters catch redundant defaults, unused bindings, deprecated attrs, useless parens before the LLM runs.</p>
        </div>
        <div class="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 shadow-sm">
          <div class="text-xs font-medium text-neutral-500">2. Retrieve</div>
          <div class="font-medium mt-1">nomic-embed + numpy cosine</div>
          <p class="text-sm text-neutral-600 dark:text-neutral-400 mt-2">98,382 packages + 16,095 NixOS options pre-embedded. At review time, findings + attr-paths are searched to pull relevant context into the prompt.</p>
        </div>
        <div class="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 shadow-sm">
          <div class="text-xs font-medium text-neutral-500">3. Review</div>
          <div class="font-medium mt-1">nix-reviewer-1.5b (v0.1)</div>
          <p class="text-sm text-neutral-600 dark:text-neutral-400 mt-2">Fine-tuned on 445 synthesized (broken_config, review) pairs. Base: Qwen2.5-Coder-1.5B-Instruct. Serves via Ollama on the xnode.</p>
        </div>
      </div>
    </section>

    <!-- stats -->
    <section class="grid grid-cols-2 sm:grid-cols-4 gap-4">
      <div class="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5">
        <div class="text-2xl font-semibold tabular-nums">98k</div>
        <div class="text-xs text-neutral-500 mt-1">nixpkgs packages</div>
      </div>
      <div class="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5">
        <div class="text-2xl font-semibold tabular-nums">16k</div>
        <div class="text-xs text-neutral-500 mt-1">NixOS options</div>
      </div>
      <div class="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5">
        <div class="text-2xl font-semibold tabular-nums">445</div>
        <div class="text-xs text-neutral-500 mt-1">training pairs (v0.1)</div>
      </div>
      <div class="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5">
        <div class="text-2xl font-semibold tabular-nums">0</div>
        <div class="text-xs text-neutral-500 mt-1">cloud API calls</div>
      </div>
    </section>

    <!-- training detail -->
    <section class="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-6 shadow-sm">
      <div class="text-xs font-medium uppercase tracking-wider text-neutral-500">How v0.1 was trained</div>
      <h3 class="font-semibold mt-1">The Nix evaluator is the teacher.</h3>
      <p class="text-sm text-neutral-600 dark:text-neutral-400 mt-2 max-w-3xl">
        Every training pair is synthesized: we take a pattern (e.g. typo'd package name), generate an original Nix config exhibiting it, and run <code class="text-xs bg-neutral-100 dark:bg-neutral-800 px-1.5 py-0.5 rounded">nix eval</code> inside a Docker container to capture the real error message, line number, and column. The model learns to reproduce what the Nix compiler itself says. <strong>No forum content is reproduced</strong> — the dataset is entirely synthetic, Apache-2.0 clean.
      </p>
      <div class="grid sm:grid-cols-3 gap-3 mt-5 text-sm">
        <div><span class="text-neutral-500 text-xs">Base:</span><br><span class="font-medium">Qwen2.5-Coder-1.5B-Instruct</span></div>
        <div><span class="text-neutral-500 text-xs">Method:</span><br><span class="font-medium">LoRA (r=16, α=32)</span></div>
        <div><span class="text-neutral-500 text-xs">Hardware:</span><br><span class="font-medium">Intel Arc 140T iGPU (48 GB)</span></div>
      </div>
    </section>

    <!-- run locally -->
    <section id="run-locally" class="space-y-5">
      <div>
        <div class="text-xs font-medium uppercase tracking-wider text-blue-600 dark:text-blue-400">Run locally</div>
        <h2 class="text-2xl font-semibold tracking-tight mt-1">Run the model on your own machine</h2>
        <p class="text-neutral-600 dark:text-neutral-400 mt-1 max-w-2xl text-sm">
          The <code class="text-xs bg-neutral-100 dark:bg-neutral-800 px-1.5 py-0.5 rounded">Q4_K_M</code> quantized build is ~986 MB and runs on CPU. If you have <a class="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300" href="https://ollama.com">Ollama</a> installed, it's two commands.
        </p>
      </div>

      <div class="grid md:grid-cols-2 gap-4">
        <div class="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 shadow-sm">
          <div class="text-xs font-medium uppercase tracking-wider text-neutral-500">1 · pull the model</div>
          <pre class="mt-3 text-xs bg-neutral-50 dark:bg-neutral-950 border border-neutral-200 dark:border-neutral-800 rounded-md p-3 overflow-x-auto leading-5 text-neutral-800 dark:text-neutral-200">ollama pull hf.co/OpenxAILabs/nix-reviewer-1.5b-GGUF:Q4_K_M</pre>
          <p class="text-xs text-neutral-500 mt-2">One-time download. ~986 MB.</p>
        </div>
        <div class="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 shadow-sm">
          <div class="text-xs font-medium uppercase tracking-wider text-neutral-500">2 · review a config</div>
          <pre class="mt-3 text-xs bg-neutral-50 dark:bg-neutral-950 border border-neutral-200 dark:border-neutral-800 rounded-md p-3 overflow-x-auto leading-5 text-neutral-800 dark:text-neutral-200">ollama run hf.co/OpenxAILabs/nix-reviewer-1.5b-GGUF:Q4_K_M \\
  '{{ pkgs, ... }}:
{{
  environment.systemPackages = with pkgs; [ vim vvim ];
}}'</pre>
          <p class="text-xs text-neutral-500 mt-2">Expected: <code class="text-xs bg-neutral-100 dark:bg-neutral-800 px-1.5 py-0.5 rounded">[{{"line": 4, "severity": "error", "message": "`vvim` is not..."}}]</code></p>
        </div>
      </div>

      <div class="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 shadow-sm">
        <div class="text-xs font-medium uppercase tracking-wider text-neutral-500">HTTP API (same shape as this site)</div>
        <pre class="mt-3 text-xs bg-neutral-50 dark:bg-neutral-950 border border-neutral-200 dark:border-neutral-800 rounded-md p-3 overflow-x-auto leading-5 text-neutral-800 dark:text-neutral-200">curl http://localhost:11434/api/chat -d '{{
  "model": "hf.co/OpenxAILabs/nix-reviewer-1.5b-GGUF:Q4_K_M",
  "stream": false,
  "messages": [
    {{"role": "system", "content": "You are nix-assistant. Review the Nix config and output ONLY a JSON array: [{{\\"line\\":int,\\"severity\\":\\"error\\"|\\"warning\\"|\\"hint\\",\\"message\\":str}}]"}},
    {{"role": "user", "content": "{{ pkgs, ... }}: {{ environment.systemPackages = with pkgs; [ vim vvim ]; }}"}}
  ]
}}'</pre>
      </div>

      <div class="flex flex-wrap gap-3 text-sm">
        <a href="https://huggingface.co/OpenxAILabs/nix-reviewer-1.5b-GGUF" class="inline-flex items-center px-3 h-9 rounded-md border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 text-neutral-700 dark:text-neutral-300 hover:border-neutral-300 dark:hover:border-neutral-700">GGUF on HF ↗</a>
        <a href="https://huggingface.co/OpenxAILabs/nix-reviewer-1.5b" class="inline-flex items-center px-3 h-9 rounded-md border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 text-neutral-700 dark:text-neutral-300 hover:border-neutral-300 dark:hover:border-neutral-700">Model card + LoRA adapter ↗</a>
        <a href="https://huggingface.co/datasets/OpenxAILabs/nix-reviewer-training" class="inline-flex items-center px-3 h-9 rounded-md border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 text-neutral-700 dark:text-neutral-300 hover:border-neutral-300 dark:hover:border-neutral-700">Training dataset ↗</a>
        <a href="https://huggingface.co/OpenxAILabs" class="inline-flex items-center px-3 h-9 rounded-md border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 text-neutral-700 dark:text-neutral-300 hover:border-neutral-300 dark:hover:border-neutral-700">All OpenxAILabs models ↗</a>
      </div>
    </section>

    <!-- feedback -->
    <section id="feedback" class="space-y-5">
      <div>
        <div class="text-xs font-medium uppercase tracking-wider text-blue-600 dark:text-blue-400">Feedback</div>
        <h2 class="text-2xl font-semibold tracking-tight mt-1">Send a message</h2>
        <p class="text-neutral-600 dark:text-neutral-400 mt-1 max-w-2xl text-sm">
          Bug reports, misses, requests, or "your model hallucinated X" — all useful. Humans and AI agents both welcome. Text only (markdown fine), 2000 chars max, 3 submissions per hour per IP.
        </p>
      </div>

      <form id="fb-form" class="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 shadow-sm space-y-4">
        <div>
          <label class="block text-xs font-medium text-neutral-500 mb-1.5">Name or handle (optional)</label>
          <input id="fb-name" maxlength="80" autocomplete="off"
            class="w-full text-sm px-3 h-9 rounded-md border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-950 text-neutral-800 dark:text-neutral-200 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus:outline-none" />
        </div>

        <div>
          <label class="block text-xs font-medium text-neutral-500 mb-1.5">Your message</label>
          <textarea id="fb-msg" rows="5" maxlength="2000" required
            class="w-full text-sm px-3 py-2 rounded-md border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-950 text-neutral-800 dark:text-neutral-200 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus:outline-none resize-y leading-6"
            placeholder="Tell us what's on your mind..."></textarea>
          <div class="flex justify-between text-xs text-neutral-500 mt-1">
            <span>Plain text. HTML/script-ish content is rejected.</span>
            <span id="fb-count">0 / 2000</span>
          </div>
        </div>

        <div class="flex items-end gap-3 flex-wrap">
          <div class="flex-1 min-w-48">
            <label class="block text-xs font-medium text-neutral-500 mb-1.5">Quick puzzle (so bots bounce off)</label>
            <div class="flex items-center gap-2">
              <span id="fb-prompt" class="text-sm text-neutral-700 dark:text-neutral-300 tabular-nums">loading…</span>
              <input id="fb-answer" type="number" required min="-20" max="20" step="1"
                class="w-20 text-sm px-3 h-9 rounded-md border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-950 text-neutral-800 dark:text-neutral-200 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus:outline-none" />
            </div>
          </div>
          <button id="fb-btn" type="submit"
            class="inline-flex items-center gap-2 text-sm font-medium px-4 h-9 rounded-md bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900 hover:bg-neutral-800 dark:hover:bg-neutral-300 focus:outline-none focus:ring-2 focus:ring-neutral-900/20 disabled:opacity-50 disabled:cursor-not-allowed transition">
            Send
          </button>
        </div>

        <div id="fb-status" class="text-sm"></div>
      </form>
    </section>

  </main>

  <footer class="border-t border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 mt-16">
    <div class="max-w-6xl mx-auto px-6 py-6 text-xs text-neutral-500 flex flex-wrap gap-4">
      <a class="hover:text-neutral-900 dark:hover:text-neutral-100" href="https://github.com/johnforfar/nix-assistant">github.com/johnforfar/nix-assistant</a>
      <span>·</span>
      <a class="hover:text-neutral-900 dark:hover:text-neutral-100" href="https://huggingface.co/OpenxAILabs">huggingface.co/OpenxAILabs</a>
      <span>·</span>
      <span>Apache-2.0</span>
      <span>·</span>
      <span>Built by <a class="hover:text-neutral-900 dark:hover:text-neutral-100" href="https://openxai.org">OpenxAI</a> · deployed on a Sovereign Openmesh Xnode</span>
    </div>
  </footer>

<script>
async function doReview() {{
  const src = document.getElementById('src').value.trim();
  const btn = document.getElementById('btn');
  const status = document.getElementById('status');
  const out = document.getElementById('results');
  if (!src) return;
  btn.disabled = true;
  status.textContent = 'reviewing…';
  out.innerHTML = '';
  try {{
    const r = await fetch('/api/review', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ source: src }})
    }});
    const data = await r.json();
    status.textContent = '';
    if (data.error) {{
      out.innerHTML = '<div class="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 rounded-md p-3">' +
        escapeHtml('error: ' + data.error) + '</div>';
      return;
    }}
    const comments = data.comments || [];
    if (!comments.length) {{
      out.innerHTML = '<div class="text-sm text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-950/40 border border-green-200 dark:border-green-900 rounded-md p-3">No issues found.</div>';
      return;
    }}
    out.innerHTML = '<div class="text-xs text-neutral-500 uppercase tracking-wide mb-2">' +
      comments.length + ' finding' + (comments.length > 1 ? 's' : '') + '</div>' +
      comments.map(c => {{
        const sev = ['error','warning','hint'].includes(c.severity) ? c.severity : 'hint';
        const ring = {{
          error:   'border-red-300 dark:border-red-900 bg-red-50 dark:bg-red-950/40',
          warning: 'border-amber-300 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/40',
          hint:    'border-blue-300 dark:border-blue-900 bg-blue-50 dark:bg-blue-950/40',
        }}[sev];
        const badge = {{
          error: 'bg-red-600 text-white',
          warning: 'bg-amber-500 text-white',
          hint: 'bg-blue-500 text-white',
        }}[sev];
        const loc = c.line ? '<span class="text-xs text-neutral-500 ml-2">line ' + c.line + '</span>' : '';
        return '<div class="border rounded-md p-3 ' + ring + '">' +
          '<span class="text-xs font-medium px-2 py-0.5 rounded ' + badge + '">' + sev + '</span>' +
          loc +
          '<div class="text-sm text-neutral-800 dark:text-neutral-200 mt-2">' + escapeHtml(c.message || '') + '</div>' +
          '</div>';
      }}).join('');
  }} catch (e) {{
    status.textContent = '';
    out.innerHTML = '<div class="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 rounded-md p-3">request failed: ' +
      escapeHtml(e.message) + '</div>';
  }} finally {{
    btn.disabled = false;
  }}
}}

function escapeHtml(s) {{
  return String(s).replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#39;"}})[c]);
}}

// theme toggle
document.getElementById('theme-toggle').addEventListener('click', () => {{
  const isDark = document.documentElement.classList.toggle('dark');
  localStorage.setItem('nix-assistant-theme', isDark ? 'dark' : 'light');
}});

// line-number gutter sync
(function() {{
  const src = document.getElementById('src');
  const gutter = document.getElementById('gutter');
  function updateGutter() {{
    const count = (src.value.match(/\\n/g) || []).length + 1;
    let html = '';
    for (let i = 1; i <= count; i++) html += '<div>' + i + '</div>';
    gutter.innerHTML = html;
  }}
  src.addEventListener('input', updateGutter);
  src.addEventListener('scroll', () => {{ gutter.scrollTop = src.scrollTop; }});
  updateGutter();
}})();

document.getElementById('src').addEventListener('keydown', e => {{
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') doReview();
}});

// interactive benchmark chart (Chart.js)
const BENCH_VERSIONS = [
  'v0 base Qwen 1.5B',
  'v0 live (hermes3:3b)',
  'v0.1 LoRA',
  'v0.2 LoRA (3 epochs)',
  'v0.2a LoRA · live',
];
const BENCH_NOTES = [
  'Pretrained Qwen2.5-Coder-1.5B with no fine-tune. Emits prose, not JSON — the review pipeline\\'s escape-hatch fired on 100% of cases, producing valid shape but zero signal.',
  'The production baseline on xnode before we shipped v0.1. statix + deadnix + RAG + hermes3:3b. General chat model tries to review — often confidently mentions an option that isn\\'t even in the input.',
  'First fine-tune. 445 synthesized pairs across 3 mutation patterns, 3 epochs, Intel Arc XPU via torch-xpu. line_exact jumps 20→90%, no_hallucinated_options hits 100%. Shipped 2026-04-23.',
  '2.7× more data (1187 pairs) plus the first 37 negatives, 3 epochs. Hit 100% on refusing non-Nix input — but over-fit to refusal: line_exact regressed 90→50%. Kept on HF for reproducibility (tag v0.2); not shipped to xnode.',
  'Same 1187 pairs as v0.2, retrained at 2 epochs. Recovered v0.1\\'s accuracy AND retained 60% of the negatives win. Best overall. Live on xnode since 2026-04-24.',
];
const BENCH_METRICS = [
  {{ key: 'schema_valid',             color: '#06b6d4', data: [100,   96,   96,   88,   96] }},
  {{ key: 'no_hallucinated_options',  color: '#ef4444', data: [null, 88.9, 100, null, 100] }},
  {{ key: 'line_exact',               color: '#f97316', data: [  0,   20,   90,   50,   90] }},
  {{ key: 'severity_match',           color: '#eab308', data: [ 20,   45,   75,   40,   70] }},
  {{ key: 'message_keywords_hit',     color: '#3b82f6', data: [  0,   25,   45,   40,   45] }},
  {{ key: 'empty_on_negative',        color: '#22c55e', data: [  0,    0,    0,  100,   60] }},
  {{ key: 'dialect_awareness',        color: '#a3e635', data: [100,  100,  100,  100,  100] }},
];

let benchChart = null;
function renderBenchChart() {{
  const canvas = document.getElementById('benchmark-chart');
  if (!canvas || typeof Chart === 'undefined') return;
  const isDark = document.documentElement.classList.contains('dark');
  const grid   = isDark ? '#262626' : '#e5e5e5';
  const text   = isDark ? '#a3a3a3' : '#525252';

  if (benchChart) benchChart.destroy();
  benchChart = new Chart(canvas, {{
    type: 'line',
    data: {{
      labels: BENCH_VERSIONS,
      datasets: BENCH_METRICS.map(m => ({{
        label: m.key,
        data: m.data,
        borderColor: m.color,
        backgroundColor: m.color + '22',
        pointBackgroundColor: m.color,
        pointRadius: 5,
        pointHoverRadius: 9,
        borderWidth: 2.5,
        tension: 0.15,
        spanGaps: false,
      }})),
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ position: 'bottom', labels: {{ color: text, boxWidth: 14, boxHeight: 14 }} }},
        tooltip: {{
          backgroundColor: isDark ? '#0a0a0a' : '#ffffff',
          titleColor:      isDark ? '#fafafa' : '#171717',
          bodyColor:       isDark ? '#d4d4d4' : '#404040',
          footerColor:     isDark ? '#a3a3a3' : '#525252',
          borderColor:     isDark ? '#404040' : '#d4d4d4',
          borderWidth: 1,
          padding: 12,
          callbacks: {{
            title:     ctx => BENCH_VERSIONS[ctx[0].dataIndex],
            label:     ctx => `  ${{ctx.dataset.label}}: ${{ctx.parsed.y === null ? 'n/a' : ctx.parsed.y + '%'}}`,
            afterBody: ctx => ['', BENCH_NOTES[ctx[0].dataIndex]],
          }},
          footerFont: {{ weight: 'normal', style: 'italic' }},
          titleFont:  {{ weight: '600', size: 13 }},
          bodyFont:   {{ size: 12 }},
        }},
      }},
      scales: {{
        y: {{
          min: 0, max: 100,
          ticks: {{ color: text, callback: v => v + '%' }},
          grid:  {{ color: grid }},
          title: {{ display: true, text: 'pass rate (%)', color: text }},
        }},
        x: {{
          ticks: {{ color: text, autoSkip: false, maxRotation: 0 }},
          grid:  {{ color: grid, display: false }},
        }},
      }},
    }},
  }});
}}

// Render on load and re-render on theme toggle
if (document.readyState === 'loading') {{
  document.addEventListener('DOMContentLoaded', renderBenchChart);
}} else {{
  renderBenchChart();
}}
new MutationObserver(() => renderBenchChart())
  .observe(document.documentElement, {{ attributes: true, attributeFilter: ['class'] }});

// feedback form
(function() {{
  const form   = document.getElementById('fb-form');
  const msg    = document.getElementById('fb-msg');
  const name   = document.getElementById('fb-name');
  const answer = document.getElementById('fb-answer');
  const prompt = document.getElementById('fb-prompt');
  const btn    = document.getElementById('fb-btn');
  const status = document.getElementById('fb-status');
  const counter= document.getElementById('fb-count');

  let challengeId = null;

  async function loadChallenge() {{
    prompt.textContent = 'loading…';
    try {{
      const r = await fetch('/api/feedback/challenge');
      const d = await r.json();
      challengeId = d.id;
      prompt.textContent = d.prompt;
      answer.value = '';
    }} catch (e) {{
      prompt.textContent = '(failed to load challenge)';
    }}
  }}

  msg.addEventListener('input', () => {{
    counter.textContent = msg.value.length + ' / 2000';
  }});

  form.addEventListener('submit', async e => {{
    e.preventDefault();
    if (!challengeId) {{ status.textContent = 'challenge not loaded — reload the page'; return; }}
    status.textContent = '';
    btn.disabled = true;
    try {{
      const r = await fetch('/api/feedback', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          challenge_id: challengeId,
          answer: parseInt(answer.value, 10),
          name: name.value,
          message: msg.value,
        }}),
      }});
      const d = await r.json();
      if (d.error) {{
        status.innerHTML = '<span class="text-red-600 dark:text-red-400">' +
          escapeHtml('error: ' + d.error) + '</span>';
        loadChallenge();
      }} else {{
        status.innerHTML = '<span class="text-green-700 dark:text-green-400">thanks — feedback received.</span>';
        msg.value = '';
        counter.textContent = '0 / 2000';
        loadChallenge();
      }}
    }} catch (e) {{
      status.innerHTML = '<span class="text-red-600 dark:text-red-400">network error: ' +
        escapeHtml(e.message) + '</span>';
    }} finally {{
      btn.disabled = false;
    }}
  }});

  loadChallenge();
}})();
</script>
</body>
</html>
"""


def main() -> int:
    # Interactive Chart.js — no base64 PNG embedded in the HTML anymore.
    # eval/plot.py still writes eval/chart/leaderboard.png for the model card.
    html = HTML_TEMPLATE  # plain string, no .format() needed
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"[build-frontend] HTML : {len(html):,} bytes total (Chart.js interactive)")
    print(f"[build-frontend] wrote -> {OUT_HTML}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
