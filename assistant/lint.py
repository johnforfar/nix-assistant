"""Run statix and deadnix over a Nix file and return structured findings.

Both tools are invoked via `nix run nixpkgs#<tool>` if not on PATH.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class Finding:
    tool: Literal["statix", "deadnix"]
    rule: str
    message: str
    file: str
    line: int
    col: int
    severity: Literal["error", "warning", "hint"] = "warning"
    suggestion: str | None = None


def _find_tool(name: str) -> list[str]:
    """Return command prefix to invoke tool, preferring PATH over nix run."""
    import shutil
    if shutil.which(name):
        return [name]
    return ["nix", "run", f"nixpkgs#{name}", "--"]


def _run_statix(nix_file: Path) -> list[Finding]:
    # statix requires -s (stdin mode) to reliably stream JSON to stdout
    source = nix_file.read_text(encoding="utf-8")
    cmd = _find_tool("statix") + ["check", "-s", "-o", "json"]
    result = subprocess.run(
        cmd, input=source, capture_output=True, text=True, timeout=60
    )
    if not result.stdout.strip():
        return []
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    # JSON shape: {"file": str, "report": [{"note": str, "code": int, "severity": str,
    #               "diagnostics": [{"at": {"from": {"line", "column"}}, "message": str,
    #                                "suggestion": {"fix": str}}]}]}
    findings = []
    fname = data.get("file", str(nix_file))
    for report in data.get("report", []):
        rule = f"W{report.get('code', '?'):02}"
        severity = _statix_severity(report.get("severity", "Warn"))
        for diag in report.get("diagnostics", []):
            pos = diag.get("at", {}).get("from", {})
            suggestion = diag.get("suggestion", {})
            findings.append(Finding(
                tool="statix",
                rule=rule,
                message=diag.get("message", report.get("note", "")),
                file=fname,
                line=pos.get("line", 0),
                col=pos.get("column", 0),
                severity=severity,
                suggestion=suggestion.get("fix") if isinstance(suggestion, dict) else None,
            ))
    return findings


def _run_deadnix(nix_file: Path) -> list[Finding]:
    cmd = _find_tool("deadnix") + ["--output-format", "json", str(nix_file)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if not result.stdout.strip():
        return []
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    # JSON shape: {"file": str, "results": [{"line": int, "column": int,
    #               "endColumn": int, "message": str}]}
    fname = data.get("file", str(nix_file))
    findings = []
    for item in data.get("results", []):
        findings.append(Finding(
            tool="deadnix",
            rule="dead_code",
            message=item.get("message", "unused binding"),
            file=fname,
            line=item.get("line", 0),
            col=item.get("column", 0),
            severity="warning",
        ))
    return findings


def _statix_severity(s: str) -> Literal["error", "warning", "hint"]:
    s = s.lower()
    if "error" in s:
        return "error"
    if "hint" in s or "info" in s:
        return "hint"
    return "warning"


def run(nix_source: str) -> list[Finding]:
    """Lint a Nix source string. Returns findings from both statix and deadnix."""
    with tempfile.NamedTemporaryFile(
        suffix=".nix", mode="w", encoding="utf-8", delete=False
    ) as tmp:
        tmp.write(nix_source)
        tmp_path = Path(tmp.name)

    try:
        findings: list[Finding] = []
        for runner in (_run_statix, _run_deadnix):
            try:
                findings.extend(runner(tmp_path))
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass
        return sorted(findings, key=lambda f: (f.line, f.col))
    finally:
        tmp_path.unlink(missing_ok=True)
