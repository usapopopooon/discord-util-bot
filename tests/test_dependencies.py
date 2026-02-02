"""Tests for dependency synchronization between pyproject.toml and requirements.txt."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


def _extract_package_name(dependency_spec: str) -> str:
    """依存関係の指定からパッケージ名を抽出する。

    例: "discord.py~=2.6.0" -> "discord.py"
         "uvicorn[standard]~=0.34.0" -> "uvicorn"
    """
    # extras を除去 (例: uvicorn[standard] -> uvicorn)
    spec = re.sub(r"\[.*?\]", "", dependency_spec)
    # バージョン指定子を除去
    for separator in ["~=", ">=", "<=", "==", "!=", ">", "<", "@"]:
        if separator in spec:
            spec = spec.split(separator)[0]
    return spec.strip().lower()


def _normalize_package_name(name: str) -> str:
    """パッケージ名を正規化する。

    PEP 503 に従い、アンダースコア・ハイフン・ドットを統一。
    """
    return re.sub(r"[-_.]+", "-", name.lower())


def _get_pyproject_dependencies(pyproject_path: Path) -> list[str]:
    """pyproject.toml から dependencies を取得する。"""
    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)
    project = data.get("project", {})
    deps = project.get("dependencies", [])
    return list(deps) if isinstance(deps, list) else []


def _get_requirements_dependencies(requirements_path: Path) -> list[str]:
    """requirements.txt から依存関係を取得する。"""
    content = requirements_path.read_text()
    deps: list[str] = []
    for line in content.splitlines():
        line = line.strip()
        # コメント行と空行をスキップ
        if not line or line.startswith("#"):
            continue
        deps.append(line)
    return deps


class TestDependencySynchronization:
    """pyproject.toml と requirements.txt の依存関係同期テスト。"""

    def test_all_pyproject_dependencies_in_requirements(self) -> None:
        """pyproject.toml の全ての依存関係が requirements.txt に存在する。

        Heroku は requirements.txt を使用してデプロイするため、
        pyproject.toml に追加した依存関係が requirements.txt にも
        存在することを確認する。
        """
        project_root = Path(__file__).parent.parent
        pyproject_path = project_root / "pyproject.toml"
        requirements_path = project_root / "requirements.txt"

        # pyproject.toml から依存関係を抽出
        pyproject_deps = _get_pyproject_dependencies(pyproject_path)
        pyproject_packages = {
            _normalize_package_name(_extract_package_name(dep))
            for dep in pyproject_deps
        }

        # requirements.txt から依存関係を抽出
        requirements_deps = _get_requirements_dependencies(requirements_path)
        requirements_packages = {
            _normalize_package_name(_extract_package_name(dep))
            for dep in requirements_deps
        }

        # pyproject.toml の依存関係が全て requirements.txt に存在するか確認
        missing = pyproject_packages - requirements_packages
        assert not missing, (
            f"pyproject.toml にあるが requirements.txt にない: {missing}\n"
            "Heroku デプロイ用に requirements.txt を更新してください。"
        )

    def test_requirements_has_no_extra_packages(self) -> None:
        """requirements.txt に pyproject.toml にないパッケージが存在しない。

        requirements.txt は pyproject.toml から生成されるべきなので、
        余分なパッケージが含まれていないことを確認する。
        """
        project_root = Path(__file__).parent.parent
        pyproject_path = project_root / "pyproject.toml"
        requirements_path = project_root / "requirements.txt"

        # pyproject.toml から依存関係を抽出
        pyproject_deps = _get_pyproject_dependencies(pyproject_path)
        pyproject_packages = {
            _normalize_package_name(_extract_package_name(dep))
            for dep in pyproject_deps
        }

        # requirements.txt から依存関係を抽出
        requirements_deps = _get_requirements_dependencies(requirements_path)
        requirements_packages = {
            _normalize_package_name(_extract_package_name(dep))
            for dep in requirements_deps
        }

        # requirements.txt にのみ存在するパッケージがないか確認
        extra = requirements_packages - pyproject_packages
        assert not extra, (
            f"requirements.txt に存在するが pyproject.toml にないパッケージ: {extra}\n"
            "pyproject.toml の依存関係を確認してください。"
        )

    def test_version_specifiers_match(self) -> None:
        """バージョン指定子が一致している。

        pyproject.toml と requirements.txt でバージョン指定が一致していることを確認。
        """
        project_root = Path(__file__).parent.parent
        pyproject_path = project_root / "pyproject.toml"
        requirements_path = project_root / "requirements.txt"

        # pyproject.toml から依存関係を抽出
        pyproject_deps = _get_pyproject_dependencies(pyproject_path)
        pyproject_versions: dict[str, str] = {}
        for dep in pyproject_deps:
            name = _normalize_package_name(_extract_package_name(dep))
            pyproject_versions[name] = dep

        # requirements.txt から依存関係を抽出
        requirements_deps = _get_requirements_dependencies(requirements_path)
        requirements_versions: dict[str, str] = {}
        for dep in requirements_deps:
            name = _normalize_package_name(_extract_package_name(dep))
            requirements_versions[name] = dep

        # バージョン指定が一致しているか確認
        mismatches: list[str] = []
        for name, pyproject_spec in pyproject_versions.items():
            if name in requirements_versions:
                req_spec = requirements_versions[name]
                # extras を除去して比較
                pyproject_normalized = re.sub(r"\[.*?\]", "", pyproject_spec)
                req_normalized = re.sub(r"\[.*?\]", "", req_spec)
                if pyproject_normalized != req_normalized:
                    mismatches.append(
                        f"  {name}: pyproject.toml='{pyproject_spec}' vs "
                        f"requirements.txt='{req_spec}'"
                    )

        assert not mismatches, "バージョン指定が一致しないパッケージ:\n" + "\n".join(
            mismatches
        )
