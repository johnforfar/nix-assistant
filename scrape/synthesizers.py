"""Per-pattern synthesizers: given a pattern id, emit N original broken Nix configs.

These are not scraped from forums — they're *generated* from the structural
pattern definitions in `eval.patterns`. Each synthesizer picks from pools of
package names, option paths, formatting variants, etc. so the resulting
configs are diverse enough to train on but never copy any specific user's code.

Contract: each synthesizer returns a list of `SynthesizedCase` with a
`source` (Nix text), a `strategy` ("expr" / "module" / "callPackage") telling
the oracle how to evaluate it, and a `label` describing the intended bug in
human-readable form (for the review-comment template later).
"""
from __future__ import annotations

import random
from dataclasses import dataclass


# Real packages that exist in nixpkgs — the valid reference we mutate away
# from. Kept deliberately mainstream so typos are unambiguous.
_REAL_PKGS = [
    "vim", "neovim", "emacs", "git", "curl", "wget", "jq", "tmux", "ripgrep",
    "fd", "bat", "htop", "btop", "firefox", "chromium", "vlc", "gimp",
    "gcc", "python3", "nodejs", "rustc", "go", "openssh", "nmap",
    "cowsay", "fortune", "tree", "unzip", "zip", "rsync", "tldr", "fzf",
    "jhead", "hexdump", "neofetch", "mpv", "imagemagick", "ffmpeg",
]


def _typo(name: str, rng: random.Random) -> str:
    """Introduce a plausible typo: doubled letter, missing letter, swapped letters, or trailing char."""
    if len(name) < 3:
        return name + rng.choice("oae")
    variant = rng.randrange(4)
    i = rng.randrange(1, len(name) - 1)
    if variant == 0:   # double a letter
        return name[:i] + name[i] + name[i:]
    if variant == 1:   # drop a letter
        return name[:i] + name[i + 1 :]
    if variant == 2:   # swap adjacent
        return name[:i] + name[i + 1] + name[i] + name[i + 2 :]
    return name + rng.choice("oae")  # append plausible letter


@dataclass
class SynthesizedCase:
    source: str               # the broken Nix source (what the model will review)
    strategy: str             # "expr" | "module" | "callPackage" — for the oracle
    pattern_id: str           # matches eval.patterns.PATTERNS[pattern_id]
    label: dict               # template args for the ideal review comment
    expected_error_contains: list[str]  # keywords we expect in the Nix error (sanity check)


def synth_package_attr_path_drift(n: int, seed: int = 0) -> list[SynthesizedCase]:
    """Generate N configs where one package name has a typo (a la `vvim` instead of `vim`).

    The error Nix produces is `undefined variable '<typo>'` — a clean hit for
    our parser. This is the simplest mutation pattern and lets us validate the
    full pipeline before adding module-level patterns.
    """
    rng = random.Random(seed)
    cases: list[SynthesizedCase] = []
    for _ in range(n):
        # Pick a small set of real packages, then corrupt one of them.
        pool = rng.sample(_REAL_PKGS, k=rng.randint(2, 4))
        victim_idx = rng.randrange(len(pool))
        victim = pool[victim_idx]
        typo = _typo(victim, rng)
        # Avoid the pathological case where the "typo" lands on another real package.
        while typo in _REAL_PKGS or typo == victim:
            typo = _typo(victim, rng)
        pool[victim_idx] = typo

        # Vary surrounding context to avoid overfitting:
        #   style 0: minimal module fragment
        #   style 1: named config function
        #   style 2: let-in wrapped
        style = rng.randrange(3)
        pkgs_listed = "\n    ".join(pool)
        if style == 0:
            source = (
                "{ pkgs, ... }:\n"
                "{\n"
                "  environment.systemPackages = with pkgs; [\n"
                f"    {pkgs_listed}\n"
                "  ];\n"
                "}\n"
            )
        elif style == 1:
            source = (
                "{ config, pkgs, ... }:\n"
                "{\n"
                "  environment.systemPackages = with pkgs; [\n"
                f"    {pkgs_listed}\n"
                "  ];\n"
                "}\n"
            )
        else:
            source = (
                "{ pkgs, lib, ... }:\n"
                "let tools = with pkgs; [\n"
                f"  {pkgs_listed}\n"
                "];\n"
                "in {\n"
                "  environment.systemPackages = tools;\n"
                "}\n"
            )

        cases.append(
            SynthesizedCase(
                source=source,
                strategy="expr",
                pattern_id="package_attr_path_drift",
                label={
                    "old_path": typo,
                    "new_path": victim,
                    "hint": f"`{typo}` is not a nixpkgs attribute — did you mean `{victim}`?",
                },
                expected_error_contains=["undefined variable", typo],
            )
        )
    return cases


def synth_syntax_error_missing_semicolon(n: int, seed: int = 0) -> list[SynthesizedCase]:
    """Drop a `;` from an attrset body. Produces a Nix parser error."""
    rng = random.Random(seed)
    cases: list[SynthesizedCase] = []
    for _ in range(n):
        # A handful of realistic attrset shapes; drop ; from one of them.
        attrs = rng.sample(
            [
                ("services.openssh.enable", "true"),
                ("networking.firewall.enable", "true"),
                ("networking.hostName", '"nixbox"'),
                ("time.timeZone", '"UTC"'),
                ("boot.tmp.useTmpfs", "true"),
                ("services.nginx.enable", "true"),
                ("programs.git.enable", "true"),
                ("programs.fish.enable", "true"),
            ],
            k=rng.randint(2, 4),
        )
        victim_idx = rng.randrange(len(attrs))
        lines = []
        for i, (k, v) in enumerate(attrs):
            sep = "" if i == victim_idx else ";"
            lines.append(f"  {k} = {v}{sep}")
        source = "{ config, ... }:\n{\n" + "\n".join(lines) + "\n}\n"
        victim_line = 3 + victim_idx  # header is 2 lines, then 1-indexed attr rows
        cases.append(
            SynthesizedCase(
                source=source,
                strategy="expr",
                pattern_id="syntax_error_missing_semicolon",
                label={
                    "line_hint": victim_line,
                    "hint": f"missing `;` at the end of line {victim_line}",
                },
                expected_error_contains=["syntax error"],
            )
        )
    return cases


def synth_flake_arg_not_destructured(n: int, seed: int = 0) -> list[SynthesizedCase]:
    """Module body references `inputs.X` but omits `inputs` from its function args."""
    rng = random.Random(seed)
    cases: list[SynthesizedCase] = []

    # Broader pool — realistic flake names actually used across the community.
    flake_refs = [
        ("nix-gaming",       "packages.${pkgs.system}.osu-lazer-bin"),
        ("nix-gaming",       "packages.${pkgs.system}.wine-tkg"),
        ("hyprland",         "packages.${pkgs.system}.hyprland"),
        ("hyprland",         "packages.${pkgs.system}.hyprlock"),
        ("agenix",           "nixosModules.default"),
        ("agenix",           "packages.${pkgs.system}.default"),
        ("neovim-nightly",   "packages.${pkgs.system}.default"),
        ("nixvim",           "packages.${pkgs.system}.default"),
        ("nixvim",           "homeManagerModules.nixvim"),
        ("home-manager",     "nixosModules.home-manager"),
        ("sops-nix",         "nixosModules.sops"),
        ("disko",            "nixosModules.default"),
        ("impermanence",     "nixosModules.impermanence"),
        ("stylix",           "nixosModules.stylix"),
        ("nix-darwin",       "darwinModules.default"),
        ("nixos-hardware",   "nixosModules.common-pc"),
        ("lanzaboote",       "nixosModules.lanzaboote"),
        ("chaotic",          "nixosModules.default"),
        ("nur",              "overlays.default"),
        ("nix-index-database", "nixosModules.nix-index"),
    ]
    # Where the reference lives — more realistic variation than "home.packages".
    body_variants = [
        ("home.packages = [\n    inputs.{name}.{attr}\n  ];",  4),  # (body, line_offset)
        ("imports = [\n    inputs.{name}.{attr}\n  ];",        4),
        ("environment.systemPackages = [\n    inputs.{name}.{attr}\n  ];", 4),
        ("nixpkgs.overlays = [\n    inputs.{name}.{attr}\n  ];", 4),
    ]
    sig_variants = [
        "{ config, pkgs, ... }:",
        "{ pkgs, lib, ... }:",
        "{ pkgs, ... }:",
        "{ config, pkgs, lib, ... }:",
        "{ config, ... }:",
    ]

    for _ in range(n):
        flake_name, attr = rng.choice(flake_refs)
        sig = rng.choice(sig_variants)
        body, err_line = rng.choice(body_variants)
        body_filled = body.format(name=flake_name, attr=attr)
        source = f"{sig}\n{{\n  {body_filled}\n}}\n"
        cases.append(
            SynthesizedCase(
                source=source,
                strategy="expr",
                pattern_id="flake_arg_not_destructured",
                label={
                    "arg": "inputs",
                    "hint": (
                        f"`inputs` is referenced but not in the module's function signature. "
                        f"Add it: `{sig.replace('...', 'inputs, ...')}`"
                    ),
                },
                expected_error_contains=["undefined variable", "inputs"],
            )
        )
    return cases


SYNTHESIZERS = {
    "package_attr_path_drift": synth_package_attr_path_drift,
    "syntax_error_missing_semicolon": synth_syntax_error_missing_semicolon,
    "flake_arg_not_destructured": synth_flake_arg_not_destructured,
}
