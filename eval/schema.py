"""Validate review output against the nix-assistant specialist contract.

Contract: output is a JSON array of `{line: int >= 0, severity: str in {error,warning,hint},
message: non-empty str}` objects. That's it.

This is the minimum schema an MoE router can depend on.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

VALID_SEVERITIES = {"error", "warning", "hint"}


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]
    parsed: list[dict[str, Any]] | None


def validate(raw: Any) -> ValidationResult:
    """Accepts a JSON string OR an already-parsed list (e.g. response['comments'])."""
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return ValidationResult(False, [f"not valid JSON: {e}"], None)
    else:
        data = raw

    if not isinstance(data, list):
        return ValidationResult(False, ["top-level must be a JSON array"], None)

    errors: list[str] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"item {i}: not an object")
            continue
        line = item.get("line")
        if not isinstance(line, int) or isinstance(line, bool):
            errors.append(f"item {i}: line must be int, got {type(line).__name__}")
        elif line < 0:
            errors.append(f"item {i}: line must be >= 0")
        if item.get("severity") not in VALID_SEVERITIES:
            errors.append(f"item {i}: severity must be one of {sorted(VALID_SEVERITIES)}")
        msg = item.get("message")
        if not isinstance(msg, str) or not msg.strip():
            errors.append(f"item {i}: message must be non-empty string")

    return ValidationResult(not errors, errors, data)
