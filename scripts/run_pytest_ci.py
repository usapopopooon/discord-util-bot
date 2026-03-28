#!/usr/bin/env python3
"""Run pytest for local CI with optional Docker-backed database.

If Docker daemon is available, run the project's DB-backed test service.
If Docker is unavailable, skip pytest with an explicit message so that
local lint/type/build checks can still complete.
"""

from __future__ import annotations

import subprocess
import sys


def _docker_available() -> bool:
    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def main() -> int:
    if not _docker_available():
        print("Skipping pytest: Docker daemon is not available in this environment.")
        return 0

    cmd = ["docker", "compose", "--profile", "dev", "run", "--rm", "test"]
    result = subprocess.run(cmd)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
