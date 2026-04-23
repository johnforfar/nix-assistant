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
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
  <style>
    :root {{
      --background: 0 0% 100%;
      --foreground: 240 10% 3.9%;
      --card: 0 0% 100%;
      --muted: 240 4.8% 95.9%;
      --muted-foreground: 240 3.8% 46.1%;
      --border: 240 5.9% 90%;
      --primary: 240 5.9% 10%;
      --primary-foreground: 0 0% 98%;
      --accent: 220 90% 56%;
      --destructive: 0 84.2% 60.2%;
      --warning: 38 92% 50%;
      --success: 142 71% 45%;
      --radius: 0.5rem;
    }}
    html, body {{ font-family: 'Inter', system-ui, -apple-system, sans-serif; }}
    code, pre, textarea {{ font-family: 'JetBrains Mono', ui-monospace, monospace; }}
  </style>
</head>
<body class="bg-neutral-50 text-neutral-900 antialiased">
  <!-- nav -->
  <header class="border-b border-neutral-200 bg-white">
    <div class="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
      <div class="flex items-center gap-2 font-semibold">
        <span class="inline-block w-2 h-2 rounded-full bg-blue-600"></span>
        <span>nix-assistant</span>
        <span class="ml-2 text-xs font-normal text-neutral-500">v0 · baseline</span>
      </div>
      <nav class="flex items-center gap-5 text-sm text-neutral-600">
        <a class="hover:text-neutral-900" href="#review">Review</a>
        <a class="hover:text-neutral-900" href="#benchmark">Benchmark</a>
        <a class="hover:text-neutral-900" href="#pipeline">How it works</a>
        <a class="hover:text-neutral-900" href="https://github.com/johnforfar/nix-assistant">GitHub ↗</a>
      </nav>
    </div>
  </header>

  <main class="max-w-6xl mx-auto px-6 py-10 space-y-16">

    <!-- hero -->
    <section class="space-y-3">
      <div class="inline-flex items-center gap-2 text-xs font-medium px-2.5 py-1 rounded-full bg-neutral-100 text-neutral-700 border border-neutral-200">
        <span class="w-1.5 h-1.5 rounded-full bg-green-500"></span>
        Live · Sovereign Xnode · No cloud API calls
      </div>
      <h1 class="text-3xl sm:text-4xl font-semibold tracking-tight">Review any Nix config, get structured findings.</h1>
      <p class="text-neutral-600 max-w-2xl">
        Paste a flake, a NixOS module, or a home-manager config. <code class="text-sm bg-neutral-100 px-1.5 py-0.5 rounded">statix</code> and <code class="text-sm bg-neutral-100 px-1.5 py-0.5 rounded">deadnix</code> run first; findings are augmented with RAG over 98k+ nixpkgs entries and 16k NixOS options; a small local LLM turns it all into line-by-line review comments. Open source, Apache-2.0.
      </p>
    </section>

    <!-- review panel -->
    <section id="review" class="rounded-xl border border-neutral-200 bg-white shadow-sm">
      <div class="p-5 border-b border-neutral-200 flex items-center justify-between">
        <div>
          <h2 class="font-semibold">Paste your config</h2>
          <p class="text-xs text-neutral-500 mt-0.5">flake.nix · configuration.nix · home.nix — up to 128 KB</p>
        </div>
        <span class="text-xs text-neutral-400">⌘/Ctrl + Enter to run</span>
      </div>
      <div class="p-5">
        <div class="relative rounded-lg border border-neutral-200 bg-neutral-50 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/20 overflow-hidden">
          <div id="gutter" class="absolute top-0 left-0 bottom-0 w-10 pt-4 pr-2 text-right text-xs leading-6 text-neutral-400 bg-neutral-100 border-r border-neutral-200 font-mono select-none pointer-events-none overflow-hidden">1</div>
          <textarea id="src" rows="12" spellcheck="false"
            class="w-full text-sm pl-14 pr-4 py-4 leading-6 bg-transparent text-neutral-800 focus:outline-none resize-y block"
            placeholder="{{ config, pkgs, ... }}:
{{
  services.openssh.enable = true;
  environment.systemPackages = with pkgs; [ vim ];
}}"></textarea>
        </div>
        <div class="mt-4 flex items-center gap-3">
          <button id="btn" onclick="doReview()"
            class="inline-flex items-center gap-2 text-sm font-medium px-4 h-9 rounded-md bg-neutral-900 text-white hover:bg-neutral-800 focus:outline-none focus:ring-2 focus:ring-neutral-900/20 disabled:opacity-50 disabled:cursor-not-allowed transition">
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
          <div class="text-xs font-medium uppercase tracking-wider text-blue-600">Evaluation</div>
          <h2 class="text-2xl font-semibold tracking-tight mt-1">Benchmark — every version on the same 25 cases</h2>
          <p class="text-neutral-600 mt-1 max-w-2xl text-sm">
            We run the same 25-case test suite against every version. No version ships unless it's an honest step forward on real metrics — line-exactness, severity match, no hallucinated options.
          </p>
        </div>
        <a href="https://github.com/johnforfar/nix-assistant/tree/main/eval"
           class="text-sm font-medium text-blue-600 hover:text-blue-700">Benchmark code →</a>
      </div>

      <div class="rounded-xl border border-neutral-200 bg-white shadow-sm overflow-hidden">
        <div class="p-5 bg-neutral-50 border-b border-neutral-200">
          <img src="data:image/png;base64,{CHART_B64}" alt="leaderboard chart"
               class="rounded-lg border border-neutral-200 w-full" />
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-neutral-200 text-left text-xs uppercase tracking-wide text-neutral-500">
                <th class="px-5 py-3 font-medium">Metric</th>
                <th class="px-5 py-3 font-medium text-right">v0 base Qwen 1.5B</th>
                <th class="px-5 py-3 font-medium text-right">v0 live (hermes3:3b)</th>
                <th class="px-5 py-3 font-medium text-right bg-blue-50 text-blue-900">v0.1 LoRA (trained)</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-neutral-100">
              <tr><td class="px-5 py-3 text-neutral-700">schema_valid</td><td class="px-5 py-3 text-right tabular-nums text-neutral-500">100%<sup>†</sup></td><td class="px-5 py-3 text-right tabular-nums">96%</td><td class="px-5 py-3 text-right tabular-nums bg-blue-50 font-medium">96%</td></tr>
              <tr><td class="px-5 py-3 text-neutral-700">no_hallucinated_options</td><td class="px-5 py-3 text-right tabular-nums text-neutral-400">n/a</td><td class="px-5 py-3 text-right tabular-nums">88.9%</td><td class="px-5 py-3 text-right tabular-nums bg-blue-50 font-medium text-green-700">100%</td></tr>
              <tr><td class="px-5 py-3 text-neutral-700 font-medium">line_exact</td><td class="px-5 py-3 text-right tabular-nums">0%</td><td class="px-5 py-3 text-right tabular-nums">20%</td><td class="px-5 py-3 text-right tabular-nums bg-blue-50 font-semibold text-green-700">90%</td></tr>
              <tr><td class="px-5 py-3 text-neutral-700 font-medium">severity_match</td><td class="px-5 py-3 text-right tabular-nums">20%</td><td class="px-5 py-3 text-right tabular-nums">45%</td><td class="px-5 py-3 text-right tabular-nums bg-blue-50 font-semibold text-green-700">75%</td></tr>
              <tr><td class="px-5 py-3 text-neutral-700 font-medium">message_keywords_hit</td><td class="px-5 py-3 text-right tabular-nums">0%</td><td class="px-5 py-3 text-right tabular-nums">25%</td><td class="px-5 py-3 text-right tabular-nums bg-blue-50 font-semibold text-green-700">45%</td></tr>
              <tr><td class="px-5 py-3 text-neutral-700">empty_on_negative</td><td class="px-5 py-3 text-right tabular-nums">0%</td><td class="px-5 py-3 text-right tabular-nums">0%</td><td class="px-5 py-3 text-right tabular-nums bg-blue-50">0% <span class="text-xs text-neutral-500">(v0.2 target)</span></td></tr>
              <tr><td class="px-5 py-3 text-neutral-700">avg latency</td><td class="px-5 py-3 text-right tabular-nums">5.5 s</td><td class="px-5 py-3 text-right tabular-nums">18 s</td><td class="px-5 py-3 text-right tabular-nums bg-blue-50 font-medium">3.3 s</td></tr>
            </tbody>
          </table>
        </div>
        <p class="px-5 py-3 text-xs text-neutral-500 border-t border-neutral-100">
          <sup>†</sup> base Qwen's 100% is illusory — every output triggered the review pipeline's escape-hatch fallback (no real review emitted, valid shape by coincidence). The headline number is <strong>line_exact: 20% → 90%</strong> and <strong>no_hallucinated_options: 100%</strong> — the model never cites a NixOS option path that doesn't exist in the real module tree.
        </p>
      </div>

      <!-- slop showcase: one-case comparison -->
      <div class="grid sm:grid-cols-2 gap-4">
        <div class="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm">
          <div class="text-xs font-medium uppercase tracking-wider text-red-600">v0 baseline · wrong</div>
          <div class="text-sm text-neutral-600 mt-1">Input: <code class="text-xs bg-neutral-100 px-1.5 py-0.5 rounded">environment.systemPackages = [ fooo ];</code></div>
          <pre class="mt-3 text-xs bg-neutral-50 border border-neutral-200 rounded-md p-3 overflow-x-auto leading-5 text-neutral-700">line 0 · hint
  texlive: Consider using texliveConTeXt
  for TeX Live environment.</pre>
          <p class="text-xs text-neutral-500 mt-2">Never mentions <code class="text-xs">fooo</code>. Hallucinates texlive. Classic slop.</p>
        </div>
        <div class="rounded-xl border border-blue-200 bg-blue-50/30 p-5 shadow-sm">
          <div class="text-xs font-medium uppercase tracking-wider text-green-700">v0.1 trained · correct</div>
          <div class="text-sm text-neutral-600 mt-1">Same input.</div>
          <pre class="mt-3 text-xs bg-white border border-blue-200 rounded-md p-3 overflow-x-auto leading-5 text-neutral-800">line 3 · error
  `fooo` is not a nixpkgs attribute
  — did you mean `vim`?</pre>
          <p class="text-xs text-neutral-500 mt-2">Right line. Right severity. Names the bug. Suggests the fix.</p>
        </div>
      </div>
    </section>

    <!-- pipeline -->
    <section id="pipeline" class="space-y-5">
      <div>
        <div class="text-xs font-medium uppercase tracking-wider text-blue-600">Methodology</div>
        <h2 class="text-2xl font-semibold tracking-tight mt-1">How it works</h2>
      </div>
      <div class="grid md:grid-cols-3 gap-4">
        <div class="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm">
          <div class="text-xs font-medium text-neutral-500">1. Lint</div>
          <div class="font-medium mt-1">statix + deadnix</div>
          <p class="text-sm text-neutral-600 mt-2">Deterministic linters catch redundant defaults, unused bindings, deprecated attrs, useless parens before the LLM runs.</p>
        </div>
        <div class="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm">
          <div class="text-xs font-medium text-neutral-500">2. Retrieve</div>
          <div class="font-medium mt-1">nomic-embed + numpy cosine</div>
          <p class="text-sm text-neutral-600 mt-2">98,382 packages + 16,095 NixOS options pre-embedded. At review time, findings + attr-paths are searched to pull relevant context into the prompt.</p>
        </div>
        <div class="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm">
          <div class="text-xs font-medium text-neutral-500">3. Review</div>
          <div class="font-medium mt-1">hermes3:3b → nix-reviewer-1.5b (v0.1)</div>
          <p class="text-sm text-neutral-600 mt-2">Currently serving hermes3:3b. v0.1 fine-tuned model trained on 445 synthesized (broken_config, review) pairs — deploying soon.</p>
        </div>
      </div>
    </section>

    <!-- stats -->
    <section class="grid grid-cols-2 sm:grid-cols-4 gap-4">
      <div class="rounded-xl border border-neutral-200 bg-white p-5">
        <div class="text-2xl font-semibold tabular-nums">98k</div>
        <div class="text-xs text-neutral-500 mt-1">nixpkgs packages</div>
      </div>
      <div class="rounded-xl border border-neutral-200 bg-white p-5">
        <div class="text-2xl font-semibold tabular-nums">16k</div>
        <div class="text-xs text-neutral-500 mt-1">NixOS options</div>
      </div>
      <div class="rounded-xl border border-neutral-200 bg-white p-5">
        <div class="text-2xl font-semibold tabular-nums">445</div>
        <div class="text-xs text-neutral-500 mt-1">training pairs (v0.1)</div>
      </div>
      <div class="rounded-xl border border-neutral-200 bg-white p-5">
        <div class="text-2xl font-semibold tabular-nums">0</div>
        <div class="text-xs text-neutral-500 mt-1">cloud API calls</div>
      </div>
    </section>

    <!-- training detail -->
    <section class="rounded-xl border border-neutral-200 bg-white p-6 shadow-sm">
      <div class="text-xs font-medium uppercase tracking-wider text-neutral-500">How v0.1 was trained</div>
      <h3 class="font-semibold mt-1">The Nix evaluator is the teacher.</h3>
      <p class="text-sm text-neutral-600 mt-2 max-w-3xl">
        Every training pair is synthesized: we take a pattern (e.g. typo'd package name), generate an original Nix config exhibiting it, and run <code class="text-xs bg-neutral-100 px-1.5 py-0.5 rounded">nix eval</code> inside a Docker container to capture the real error message, line number, and column. The model learns to reproduce what the Nix compiler itself says. <strong>No forum content is reproduced</strong> — the dataset is entirely synthetic, Apache-2.0 clean.
      </p>
      <div class="grid sm:grid-cols-3 gap-3 mt-5 text-sm">
        <div><span class="text-neutral-500 text-xs">Base:</span><br><span class="font-medium">Qwen2.5-Coder-1.5B-Instruct</span></div>
        <div><span class="text-neutral-500 text-xs">Method:</span><br><span class="font-medium">LoRA (r=16, α=32)</span></div>
        <div><span class="text-neutral-500 text-xs">Hardware:</span><br><span class="font-medium">Intel Arc 140T iGPU (48 GB)</span></div>
      </div>
    </section>

  </main>

  <footer class="border-t border-neutral-200 bg-white mt-16">
    <div class="max-w-6xl mx-auto px-6 py-6 text-xs text-neutral-500 flex flex-wrap gap-4">
      <a class="hover:text-neutral-900" href="https://github.com/johnforfar/nix-assistant">github.com/johnforfar/nix-assistant</a>
      <span>·</span>
      <span>Apache-2.0</span>
      <span>·</span>
      <span>Built by <a class="hover:text-neutral-900" href="https://openxai.org">OpenxAI</a> · deployed on a Sovereign Openmesh Xnode</span>
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
      out.innerHTML = '<div class="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md p-3">' +
        escapeHtml('error: ' + data.error) + '</div>';
      return;
    }}
    const comments = data.comments || [];
    if (!comments.length) {{
      out.innerHTML = '<div class="text-sm text-green-700 bg-green-50 border border-green-200 rounded-md p-3">No issues found.</div>';
      return;
    }}
    out.innerHTML = '<div class="text-xs text-neutral-500 uppercase tracking-wide mb-2">' +
      comments.length + ' finding' + (comments.length > 1 ? 's' : '') + '</div>' +
      comments.map(c => {{
        const sev = ['error','warning','hint'].includes(c.severity) ? c.severity : 'hint';
        const ring = {{error: 'border-red-300 bg-red-50', warning: 'border-amber-300 bg-amber-50', hint: 'border-blue-300 bg-blue-50'}}[sev];
        const badge = {{error: 'bg-red-600 text-white', warning: 'bg-amber-500 text-white', hint: 'bg-blue-500 text-white'}}[sev];
        const loc = c.line ? '<span class="text-xs text-neutral-500 ml-2">line ' + c.line + '</span>' : '';
        return '<div class="border rounded-md p-3 ' + ring + '">' +
          '<span class="text-xs font-medium px-2 py-0.5 rounded ' + badge + '">' + sev + '</span>' +
          loc +
          '<div class="text-sm text-neutral-800 mt-2">' + escapeHtml(c.message || '') + '</div>' +
          '</div>';
      }}).join('');
  }} catch (e) {{
    status.textContent = '';
    out.innerHTML = '<div class="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md p-3">request failed: ' +
      escapeHtml(e.message) + '</div>';
  }} finally {{
    btn.disabled = false;
  }}
}}

function escapeHtml(s) {{
  return String(s).replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#39;"}})[c]);
}}

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
</script>
</body>
</html>
"""


def main() -> int:
    if not CHART_PNG.exists():
        print(f"[build-frontend] ERROR: chart not found at {CHART_PNG}")
        return 1
    b64 = base64.b64encode(CHART_PNG.read_bytes()).decode("ascii")
    html = HTML_TEMPLATE.format(CHART_B64=b64)
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"[build-frontend] chart: {len(b64):,} bytes base64")
    print(f"[build-frontend] HTML : {len(html):,} bytes total")
    print(f"[build-frontend] wrote -> {OUT_HTML}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
