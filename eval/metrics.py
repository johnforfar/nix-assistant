"""Per-case metrics. Each returns True / False / None.

None = not applicable (excluded from the metric's denominator in the aggregate).
True / False = pass / fail for that case.

Aggregate reporting handled by run.py / rescore.py.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from .schema import validate


# ── basic metrics (v0 original set) ────────────────────────────────────────

def schema_valid(parsed: Any) -> bool:
    return validate(parsed).valid


def line_exact(parsed: list[dict] | None, expected_line: int, tol: int = 1) -> bool:
    """Top finding's line matches expected (±tol). Tokenization off-by-one is tolerated."""
    if not parsed:
        return False
    first = parsed[0]
    got = first.get("line")
    if not isinstance(got, int) or isinstance(got, bool):
        return False
    return abs(got - expected_line) <= tol


def severity_match(parsed: list[dict] | None, expected: str) -> bool:
    if not parsed:
        return False
    return parsed[0].get("severity") == expected


def message_keywords_hit(parsed: list[dict] | None, keywords: list[str]) -> bool:
    """Any keyword present in top finding's message (case-insensitive)."""
    if not parsed:
        return False
    msg = (parsed[0].get("message") or "").lower()
    return any(kw.lower() in msg for kw in keywords)


def empty_on_negative(parsed: list[dict] | None) -> bool:
    """Model correctly returned zero findings for non-Nix input."""
    return parsed is not None and len(parsed) == 0


def looks_like_escape_hatch(parsed: list[dict] | None) -> bool:
    """Heuristic for review.py's fallback path: one hint with line=0.

    When the model's output fails to parse as a clean JSON array, review.py
    dumps the raw string into a single {line: 0, severity: 'hint'} comment.
    """
    if not parsed or len(parsed) != 1:
        return False
    c = parsed[0]
    return c.get("line") == 0 and c.get("severity") == "hint"


# ── non-slop metrics (added post-v0) ───────────────────────────────────────

# First-token whitelist: path must start with one of these to be treated as
# a candidate NixOS option reference. Filters out `pkgs.vim`, `lib.mkIf`,
# `builtins.readFile`, etc. — which look like option paths but aren't.
_OPTION_FIRST_TOKENS = {
    "environment", "services", "programs", "networking", "systemd",
    "boot", "hardware", "fileSystems", "users", "nix", "nixpkgs",
    "security", "system", "time", "sound", "virtualisation", "xdg",
    "home", "wayland", "console", "fonts", "i18n", "location",
    "powerManagement", "zramSwap", "swapDevices", "documentation",
    "assertions", "warnings", "imports", "specialisation", "gtk",
    "qt", "appstream", "dconf", "containers",
}

_PATH_RE = re.compile(r'\b([a-zA-Z][a-zA-Z0-9_-]*(?:\.[a-zA-Z0-9_-]+)+)\b')


def extract_option_paths(text: str) -> list[str]:
    """Extract candidate NixOS option paths from a message.

    Filters by first-token whitelist to avoid false positives on package
    attribute paths (`pkgs.vim`) and library calls (`lib.mkIf`).
    """
    out = []
    for p in _PATH_RE.findall(text):
        head = p.split(".")[0]
        if head in _OPTION_FIRST_TOKENS:
            out.append(p)
    return out


def load_option_prefix_set(corpus_db_path: Path) -> set[str]:
    """Return every prefix of every real NixOS option path.

    E.g. from `services.openssh.enable` add
    {`services`, `services.openssh`, `services.openssh.enable`}.
    Allows O(1) "is this path a prefix of a real option?" check.
    """
    db = sqlite3.connect(str(corpus_db_path))
    try:
        paths = [r[0] for r in db.execute("SELECT option_path FROM nixos_options")]
    finally:
        db.close()
    prefixes: set[str] = set()
    for p in paths:
        parts = p.split(".")
        for i in range(1, len(parts) + 1):
            prefixes.add(".".join(parts[:i]))
    return prefixes


def load_option_source_map(corpus_db_path: Path) -> dict[str, str]:
    """{option_path: first declaration file path, relative to nixpkgs root}."""
    db = sqlite3.connect(str(corpus_db_path))
    m: dict[str, str] = {}
    try:
        for path, decl_json in db.execute(
            "SELECT option_path, declarations_json FROM nixos_options "
            "WHERE declarations_json IS NOT NULL"
        ):
            try:
                decls = json.loads(decl_json)
            except (json.JSONDecodeError, TypeError):
                continue
            if decls and isinstance(decls, list) and isinstance(decls[0], str):
                m[path] = decls[0]
    finally:
        db.close()
    return m


def no_hallucinated_options(
    parsed: list[dict] | None, valid_prefix_set: set[str]
) -> bool | None:
    """True if every option-like path in every finding's message is real.

    A path is "real" if it equals or is a prefix of some known NixOS option
    path. Returns None if the finding set cites no option-like paths (nothing
    to check).
    """
    if not parsed:
        return None
    total_cited = 0
    for finding in parsed:
        msg = finding.get("message") or ""
        for path in extract_option_paths(msg):
            total_cited += 1
            if path not in valid_prefix_set:
                return False
    if total_cited == 0:
        return None
    return True


def receipts_available(
    parsed: list[dict] | None,
    option_source_map: dict[str, str],
    nixpkgs_root: Path,
) -> bool | None:
    """True iff every real option cited has a declaration file we can produce.

    Returns None if no real option paths were cited.
    """
    if not parsed:
        return None
    cited_real: list[str] = []
    for finding in parsed:
        msg = finding.get("message") or ""
        for path in extract_option_paths(msg):
            if path in option_source_map:
                cited_real.append(path)
    if not cited_real:
        return None
    for path in cited_real:
        src_rel = option_source_map[path]
        # declarations_json sometimes stores "nixpkgs/..." prefixed; strip it
        src_rel = src_rel.removeprefix("nixpkgs/")
        if not (nixpkgs_root / src_rel).exists():
            return False
    return True


# Dialect detection and awareness -------------------------------------------

_FLAKE_MARKERS = (
    re.compile(r'\boutputs\s*=\s*\{'),
    re.compile(r'\binputs\s*=\s*\{'),
)
_HOME_MANAGER_MARKERS = (
    re.compile(r'\bhome\.packages\b'),
    re.compile(r'\bhome\.username\b'),
    re.compile(r'\bhome\.stateVersion\b'),
    re.compile(r'\bprograms\.home-manager\b'),
)
_NIXOS_MODULE_MARKERS = (
    re.compile(r'\bservices\.'),
    re.compile(r'\bnetworking\.'),
    re.compile(r'\benvironment\.systemPackages\b'),
    re.compile(r'\bboot\.'),
    re.compile(r'\bsystem\.stateVersion\b'),
)


def detect_dialect(source: str) -> str | None:
    """Heuristic: is this source a flake, a home-manager module, a NixOS module, or unclear?

    Returns one of {"flake", "home_manager", "nixos_module", None}.
    """
    if not source:
        return None
    if any(m.search(source) for m in _FLAKE_MARKERS):
        return "flake"
    if any(m.search(source) for m in _HOME_MANAGER_MARKERS):
        return "home_manager"
    if any(m.search(source) for m in _NIXOS_MODULE_MARKERS):
        return "nixos_module"
    return None


# Forbidden prefixes: options that would be wrong advice for a given dialect.
_DIALECT_FORBIDDEN = {
    "flake": ("home.packages", "home.username", "home.stateVersion"),
    "nixos_module": ("home.packages", "home.username", "home.stateVersion"),
    "home_manager": ("boot.", "systemd.services.", "networking.firewall"),
}


def dialect_awareness(
    parsed: list[dict] | None, expected_dialect: str | None
) -> bool | None:
    """True if findings don't recommend dialect-wrong advice.

    E.g. if the input is a NixOS module, a finding that suggests `home.packages`
    is dialect-wrong. Returns None when dialect is unknown or no findings.
    """
    if expected_dialect is None or not parsed:
        return None
    forbidden = _DIALECT_FORBIDDEN.get(expected_dialect)
    if not forbidden:
        return None
    for finding in parsed:
        msg = (finding.get("message") or "").lower()
        for bad in forbidden:
            if bad.lower() in msg:
                return False
    return True
