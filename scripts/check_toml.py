#!/usr/bin/env python3
"""TOML lint helper for local CI.

Tries `taplo check` first. If taplo crashes on some macOS environments,
falls back to Python's stdlib `tomllib` syntax parsing for pyproject.toml.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path


def _run_taplo() -> int:
    result = subprocess.run(
        ["taplo", "check", "pyproject.toml"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return 0

    stderr = (result.stderr or "").strip()
    stdout = (result.stdout or "").strip()
    combined = f"{stdout}\n{stderr}".strip()

    # Known taplo panic on some macOS runners:
    # "Attempted to create a NULL object."
    if "Attempted to create a NULL object." in combined:
        return 2

    if combined:
        print(combined)
    return result.returncode


def _run_tomllib_fallback() -> int:
    path = Path("pyproject.toml")
    try:
        with path.open("rb") as f:
            tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        print(f"TOML parse error: {exc}")
        return 1
    print("taplo crashed; fallback tomllib parse passed.")
    return 0


def main() -> int:
    taplo_result = _run_taplo()
    if taplo_result == 2:
        return _run_tomllib_fallback()
    return taplo_result


if __name__ == "__main__":
    sys.exit(main())
