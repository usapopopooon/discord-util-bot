#!/usr/bin/env python3
"""CI チェックをローカルで実行するスクリプト。

CI ワークフローで実行されるテスト以外のチェックを順番に実行する。
全てのチェックが通れば CI も通る。

Usage:
    python scripts/ci_check.py        # テスト以外の全チェック
    python scripts/ci_check.py --all  # テストも含めて実行
"""

import subprocess
import sys
from typing import NamedTuple


class Check(NamedTuple):
    """チェック項目の定義。"""

    name: str
    command: list[str]
    is_test: bool = False


# CI で実行されるチェック (ci.yml の順序に合わせる)
CHECKS: list[Check] = [
    Check("Requirements sync", ["python", "scripts/sync_requirements.py", "--check"]),
    Check("Spell check (cspell)", ["npm", "run", "lint:spell"]),
    Check("JSON lint", ["npm", "run", "lint:json"]),
    Check("YAML lint", ["yamllint", "-s", "."]),
    Check("TOML lint", ["taplo", "check", "pyproject.toml"]),
    Check("Ruff format", ["ruff", "format", "--check", "."]),
    Check("Ruff check", ["ruff", "check", "src", "tests"]),
    Check("mypy", ["mypy", "src"]),
    Check("pytest", ["pytest", "--cov", "--cov-report=term-missing"], is_test=True),
]


def run_check(check: Check) -> bool:
    """チェックを実行し、成功したかどうかを返す。"""
    print(f"\n{'=' * 60}")
    print(f"  {check.name}")
    print("=" * 60)

    result = subprocess.run(check.command, capture_output=False)
    success = result.returncode == 0

    if success:
        print(f"  \033[32m✓ {check.name} passed\033[0m")
    else:
        print(f"  \033[31m✗ {check.name} failed\033[0m")

    return success


def main() -> int:
    """メイン関数。"""
    include_tests = "--all" in sys.argv

    print("\n" + "=" * 60)
    print("  CI Check Script")
    print("=" * 60)

    if include_tests:
        print("  Running all checks including tests")
    else:
        print("  Running checks (excluding tests)")
        print("  Use --all to include tests")

    failed_checks: list[str] = []

    for check in CHECKS:
        if check.is_test and not include_tests:
            continue

        if not run_check(check):
            failed_checks.append(check.name)

    # 結果サマリー
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)

    total = len([c for c in CHECKS if include_tests or not c.is_test])
    passed = total - len(failed_checks)

    if failed_checks:
        print(f"\n  \033[31m{passed}/{total} checks passed\033[0m")
        print("\n  Failed checks:")
        for name in failed_checks:
            print(f"    - {name}")
        print()
        return 1
    else:
        print(f"\n  \033[32m{passed}/{total} checks passed\033[0m")
        print("\n  All checks passed! CI should succeed.")
        print()
        return 0


if __name__ == "__main__":
    sys.exit(main())
