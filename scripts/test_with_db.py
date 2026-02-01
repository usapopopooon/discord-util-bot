#!/usr/bin/env python3
"""ローカルで PostgreSQL を使ったテストを実行するスクリプト (クロスプラットフォーム版).

使い方:
    python scripts/test_with_db.py              # 全テストを実行
    python scripts/test_with_db.py -v           # verbose モードで実行
    python scripts/test_with_db.py -k bump      # bump 関連のテストのみ実行
    python scripts/test_with_db.py --keep       # テスト後コンテナを停止しない

Windows, macOS, Linux で動作します。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


def run_command(
    cmd: list[str],
    *,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """コマンドを実行する."""
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture_output,
        text=True,
    )


def wait_for_postgres(max_retries: int = 30) -> bool:
    """PostgreSQL が準備完了するまで待機する."""
    for _ in range(max_retries):
        result = run_command(
            [
                "docker",
                "compose",
                "-f",
                "docker-compose.test.yml",
                "exec",
                "-T",
                "test-db",
                "pg_isready",
                "-U",
                "test_user",
                "-d",
                "discord_util_bot_test",
            ],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0:
            return True
        time.sleep(1)
    return False


def get_python_path() -> str:
    """venv の Python パスを取得する."""
    if sys.platform == "win32":
        venv_python = Path(".venv/Scripts/python.exe")
    else:
        venv_python = Path(".venv/bin/python")

    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def main() -> int:
    """メイン処理."""
    # --keep オプションをチェック
    keep_container = "--keep" in sys.argv
    pytest_args = [arg for arg in sys.argv[1:] if arg != "--keep"]

    # プロジェクトルートに移動
    project_dir = Path(__file__).parent.parent
    os.chdir(project_dir)

    try:
        # テスト用 PostgreSQL コンテナを起動
        print("\033[36mStarting test PostgreSQL container...\033[0m")
        run_command(["docker", "compose", "-f", "docker-compose.test.yml", "up", "-d"])

        # PostgreSQL が準備完了するまで待機
        print("\033[36mWaiting for PostgreSQL to be ready...\033[0m")
        if not wait_for_postgres():
            print("\033[31mPostgreSQL did not become ready in time\033[0m")
            return 1
        print("\033[32mPostgreSQL is ready!\033[0m")

        # 環境変数を設定
        env = os.environ.copy()
        env["DISCORD_TOKEN"] = "test-token"
        env["TEST_DATABASE_URL"] = (
            "postgresql+asyncpg://test_user:test_pass@localhost:5432/discord_util_bot_test"
        )
        env["TEST_DATABASE_URL_SYNC"] = (
            "postgresql://test_user:test_pass@localhost:5432/discord_util_bot_test"
        )

        # テスト実行
        print("\033[36mRunning tests...\033[0m")
        python_path = get_python_path()
        result = subprocess.run(
            [python_path, "-m", "pytest", *pytest_args],
            env=env,
        )
        return result.returncode

    finally:
        # コンテナを停止 (--keep オプションがない場合)
        if not keep_container:
            print("\033[36mStopping test PostgreSQL container...\033[0m")
            run_command(
                ["docker", "compose", "-f", "docker-compose.test.yml", "down"],
                check=False,
            )


if __name__ == "__main__":
    sys.exit(main())
