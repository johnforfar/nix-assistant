"""Meta-pattern catalog for nix-assistant training-data synthesis.

Patterns extracted from internal research notes (ENGINEERING/research/patterns_v1.md).
Each pattern describes a class of real-world Nix-config failure observed in
the community, abstracted to its structural signature so we can synthesize
original test cases — our configs, our package choices, our comments — that
exhibit it.

The synthesizer in scrape/generate_pairs.py (Phase 2b) consumes these to
generate training data; synthesized configs are run through the Docker Nix
oracle to obtain ground-truth error messages. No verbatim content from any
forum thread is reproduced.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pattern:
    id: str
    name: str
    category: str
    difficulty: str  # trivial / medium / hard
    description: str
    signature: str                       # one-sentence structural description
    expected_error_keywords: tuple[str, ...]
    review_template: str                 # template for the ideal review comment


PATTERNS: dict[str, Pattern] = {
    "option_renamed_across_channels": Pattern(
        id="option_renamed_across_channels",
        name="Option renamed between NixOS channel versions",
        category="deprecation",
        difficulty="medium",
        description=(
            "A NixOS or home-manager option exists under one name on a newer "
            "channel but a different name on a stable channel (or vice versa). "
            "Users following unstable docs while running stable hit this often."
        ),
        signature=(
            "option_path is defined in channel X but not channel Y; the user's "
            "flake/config is pinned to the channel that lacks it"
        ),
        expected_error_keywords=("does not exist", "option"),
        review_template=(
            "`{option_path}` does not exist on this NixOS release. Use "
            "`{alternative}` instead, or switch the relevant flake input to "
            "the channel where `{option_path}` is defined."
        ),
    ),
    "flake_arg_not_destructured": Pattern(
        id="flake_arg_not_destructured",
        name="Flake passes an arg via specialArgs but module doesn't destructure it",
        category="flake_plumbing",
        difficulty="medium",
        description=(
            "A flake passes an argument — typically `inputs` — to a NixOS or "
            "home-manager module via `specialArgs` / `extraSpecialArgs`, but "
            "the module's function signature doesn't include that arg. The "
            "reference then fails with `undefined variable '<arg>'`."
        ),
        signature=(
            "module body references `{arg}.X` but function signature is "
            "`{{ config, pkgs, ... }}:` without `{arg}`"
        ),
        expected_error_keywords=("undefined variable",),
        review_template=(
            "`{arg}` is referenced but not destructured from the module's "
            "function args. Add `{arg}` to the signature — the flake passes "
            "it in via {spec_args_mechanism}."
        ),
    ),
    "package_attr_path_drift": Pattern(
        id="package_attr_path_drift",
        name="Package attribute path changed across nixpkgs releases",
        category="deprecation",
        difficulty="trivial",
        description=(
            "A package that lived at `pkgs.X.Y` was moved to `pkgs.Y` (or "
            "vice versa) in a nixpkgs refactor. `with pkgs; [ Y ]` no longer "
            "resolves because the attribute moved."
        ),
        signature=(
            "package attribute path has been flattened or nested across "
            "nixpkgs releases; user's config uses the old path"
        ),
        expected_error_keywords=("undefined variable",),
        review_template=(
            "`{old_path}` was moved; the package now lives at `{new_path}`. "
            "Update the attribute path."
        ),
    ),
    "module_namespace_mismatch": Pattern(
        id="module_namespace_mismatch",
        name="NixOS option set in home-manager scope (or vice versa)",
        category="namespace",
        difficulty="medium",
        description=(
            "A user sets a NixOS system-level option inside a home-manager "
            "config, or a home-manager-only option inside a NixOS module. "
            "NixOS and home-manager have disjoint `programs.*` / `services.*` "
            "namespaces; setting an option in the wrong scope errors with "
            "`option does not exist`."
        ),
        signature=(
            "NixOS-only option appears in home.nix, OR home-manager-only "
            "option appears in configuration.nix"
        ),
        expected_error_keywords=("does not exist",),
        review_template=(
            "`{option_path}` is defined by the {correct_scope} module system, "
            "not by {wrong_scope}. Move it to {correct_file}. NixOS and "
            "home-manager have separate, non-overlapping `{namespace}.*` "
            "namespaces."
        ),
    ),
    "missing_module_import": Pattern(
        id="missing_module_import",
        name="Options set without importing their defining module",
        category="flake_plumbing",
        difficulty="hard",
        description=(
            "User sets options under a prefix — e.g. `home-manager.*` — "
            "without first importing the module that defines them — e.g. "
            "`inputs.home-manager.nixosModules.home-manager`. The option "
            "tree does not exist at eval time, so every `home-manager.*` "
            "assignment reports `option does not exist`."
        ),
        signature=(
            "`{prefix}.*` options are set but `{defining_module}` is not in "
            "the flake's modules list"
        ),
        expected_error_keywords=("does not exist",),
        review_template=(
            "Setting `{prefix}.*` options requires importing `{defining_module}` "
            "into the system's modules list first. The `{prefix}` option tree "
            "does not exist until that import runs."
        ),
    ),
}


def by_category(category: str) -> list[Pattern]:
    return [p for p in PATTERNS.values() if p.category == category]


def by_difficulty(difficulty: str) -> list[Pattern]:
    return [p for p in PATTERNS.values() if p.difficulty == difficulty]
