"""Docker-based Nix evaluation oracle.

Runs `nix eval --json` in a fresh `nixos/nix` container per call (~600 ms).
`--json` forces deep evaluation so lazy `with pkgs; [...]` lists actually
try to resolve each element.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


NIXPKGS_MOUNT_HOST = "/c/Users/johnny/Documents/nix-assistant/data/nixpkgs"
DEFAULT_IMAGE = "nixos/nix:latest"
DEFAULT_TIMEOUT_S = 30

# Parse Nix stderr. Errors nest (outer wrapper + inner cause); prefer the
# innermost one pointing at /work/ (user source).
ERROR_WITH_LOC_RE = re.compile(
    r"error:\s+(?P<msg>[^\n]+?)\s+at\s+(?P<path>\S+):(?P<line>\d+):(?P<col>\d+)",
    re.MULTILINE,
)
ERROR_NO_LOC_RE = re.compile(r"error:\s+(?P<msg>[^\n]+)")
USER_MOUNT_PREFIX = "/work/"


@dataclass
class OracleResult:
    ok: bool
    stdout: str
    stderr: str
    exit_code: int
    error: dict | None
    latency_ms: float


def parse_nix_error(stderr: str) -> dict | None:
    stderr = stderr.strip()
    if not stderr:
        return None
    located = list(ERROR_WITH_LOC_RE.finditer(stderr))
    if located:
        user_hits = [m for m in located if m["path"].startswith(USER_MOUNT_PREFIX)]
        m = user_hits[-1] if user_hits else located[-1]
        return {"line": int(m["line"]), "col": int(m["col"]), "message": m["msg"].strip()}
    m = ERROR_NO_LOC_RE.search(stderr)
    if m:
        return {"line": 0, "col": 0, "message": m["msg"].strip()}
    return None


def _docker_run_args(strategy, source_path, nixpkgs_host, image):
    mount_src = f"{nixpkgs_host}:/nixpkgs:ro"
    mount_source = f"{source_path.parent}:/work:ro"

    if strategy == "expr":
        # Apply the source as a function if it is one (typical module shape);
        # otherwise use its value directly. Access `.environment` if present
        # so module-style configs actually evaluate their body.
        expr = (
            f"let "
            f"  pkgs = import /nixpkgs {{}}; "
            f"  lib = pkgs.lib; "
            f"  src = import /work/{source_path.name}; "
            f"  applied = if builtins.isFunction src "
            f"            then src {{ inherit pkgs lib; config = {{}}; }} "
            f"            else src; "
            f"in applied"
        )
    elif strategy == "module":
        expr = (
            f"let lib = (import /nixpkgs {{}}).lib; "
            f"in (lib.evalModules {{ "
            f"  modules = [ /work/{source_path.name} "
            f"              {{ nixpkgs.hostPlatform = \"x86_64-linux\"; }} ]; "
            f"  specialArgs = {{ modulesPath = \"/nixpkgs/nixos/modules\"; }}; "
            f"}}).config"
        )
    elif strategy == "callPackage":
        expr = f"(import /nixpkgs {{}}).callPackage /work/{source_path.name} {{}}"
    else:
        raise ValueError(f"unknown strategy: {strategy}")

    shell_cmd = (
        f"nix --extra-experimental-features nix-command "
        f"eval --impure --json --expr '{expr}'"
    )
    return [
        "docker", "run", "--rm",
        "-v", mount_src,
        "-v", mount_source,
        image, "sh", "-c", shell_cmd,
    ]


def eval_source(
    source: str,
    strategy: str = "expr",
    timeout_s: int = DEFAULT_TIMEOUT_S,
    nixpkgs_host: str = NIXPKGS_MOUNT_HOST,
    image: str = DEFAULT_IMAGE,
) -> OracleResult:
    with tempfile.NamedTemporaryFile(
        suffix=".nix", mode="w", encoding="utf-8", delete=False
    ) as tmp:
        tmp.write(source)
        tmp_path = Path(tmp.name)

    try:
        args = _docker_run_args(strategy, tmp_path, nixpkgs_host, image)
        env = {"MSYS_NO_PATHCONV": "1"}
        t0 = time.monotonic()
        try:
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=timeout_s,
                env={**env, **_inherit_env()},
            )
            latency_ms = (time.monotonic() - t0) * 1000
            return OracleResult(
                ok=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                error=parse_nix_error(result.stderr) if result.returncode != 0 else None,
                latency_ms=latency_ms,
            )
        except subprocess.TimeoutExpired as e:
            latency_ms = (time.monotonic() - t0) * 1000
            return OracleResult(
                ok=False,
                stdout=e.stdout.decode("utf-8", "replace") if e.stdout else "",
                stderr=e.stderr.decode("utf-8", "replace") if e.stderr else "",
                exit_code=-1,
                error={"line": 0, "col": 0, "message": f"timeout after {timeout_s}s"},
                latency_ms=latency_ms,
            )
    finally:
        tmp_path.unlink(missing_ok=True)


def _inherit_env():
    import os
    keep = ("PATH", "USERPROFILE", "HOME", "TEMP", "TMP",
            "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH")
    return {k: os.environ[k] for k in keep if k in os.environ}
