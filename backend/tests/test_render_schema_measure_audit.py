"""
test_render_schema_measure_audit.py

render schema `reached_by` 离线审计工具的守卫
（spec platform-global-display-settings-closure 6A / design §18 H1②）。

判据：
1. **幂等**：`--check` 必须与磁盘文件逐值一致（生成类产物的 `--check` 约定）。
2. **不空转**：内置工作包注册表非空（否则「无核心项」是假结论）。
3. **不连库**：工具不得 import AsyncSession / `get_db`（离线可跑）。
4. **路径口径**：schema 目录必须是 `data/ledger_adapters/wp_render_schema`
   （不是 `data/wp_render_schema` —— 本轮实测过这个猜错的坑）。
5. **核心清单自洽**：`render_schema_core.json` 的 `entries` 里每个 schema
   都必须真有 `reached_by`（空 `reached_by` 不能算核心项）。
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_SCRIPT = _BACKEND / "scripts" / "analyze" / "render_schema_measure_audit.py"
_CORE = _BACKEND / "data" / "render_schema_core.json"


class TestScriptExists:
    def test_script_exists(self) -> None:
        assert _SCRIPT.exists(), f"审计脚本不存在：{_SCRIPT}"

    def test_core_file_exists(self) -> None:
        assert _CORE.exists(), f"核心清单不存在：{_CORE}（先跑 --write）"


class TestOfflineOnly:
    def test_no_async_db_dependency(self) -> None:
        """工具必须能离线跑：不得 import AsyncSession / get_db。"""
        tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    assert alias.name != "AsyncSession", "工具 import 了 AsyncSession，无法离线跑"
            if isinstance(node, ast.Await):
                pytest.fail("工具含 await，说明依赖异步 IO，无法离线跑")


class TestSchemaDirPath:
    def test_schema_dir_points_to_ledger_adapters(self) -> None:
        """schema 目录必须是 `data/ledger_adapters/wp_render_schema`。

        🔴 本轮实测：我第一版写成 `data/wp_render_schema`（按命名习惯猜），
        目录不存在 ⇒ 全部「无 schema 文件」、`entries: []` 看起来像「确实没有」。
        """
        source = _SCRIPT.read_text(encoding="utf-8")
        assert '"ledger_adapters"' in source, (
            "未出现 ledger_adapters 段；真实 schema 目录是 "
            "`backend/data/ledger_adapters/wp_render_schema`"
        )

    def test_schema_dir_really_exists(self) -> None:
        from scripts.analyze.render_schema_measure_audit import _schema_dir

        path = _schema_dir()
        assert path.is_dir(), f"schema 目录不存在：{path}"
        yaml_count = len(list(path.glob("*.yaml")))
        assert yaml_count > 0, f"{path} 下没有 yaml 文件"


class TestBuiltinPackagesNonEmpty:
    def test_packages_are_non_empty(self) -> None:
        """空注册表 ⇒ reached_by 恒空 ⇒ 判据恒绿。"""
        from scripts.analyze.render_schema_measure_audit import _load_builtin_packages

        packages = _load_builtin_packages()
        assert len(packages) > 0
        # 每个包至少一个 sheet
        for code, sheets in packages.items():
            assert sheets, f"{code} 没有 sheet"


class TestCoreFileSelfConsistent:
    def test_entries_have_non_empty_reached_by(self) -> None:
        """核心项的 reached_by 不得为空（空 reached_by 不能算核心）。"""
        data = json.loads(_CORE.read_text(encoding="utf-8"))
        for entry in data.get("entries") or []:
            assert entry.get("reached_by"), (
                f"核心项 {entry.get('schema')} 的 reached_by 为空"
            )

    def test_schema_version_present(self) -> None:
        data = json.loads(_CORE.read_text(encoding="utf-8"))
        assert data.get("schema_version") == 1
        assert data.get("_source", "").endswith("render_schema_measure_audit.py")

    def test_offline_limitations_are_documented(self) -> None:
        """design §18 H1②：两类离线算不到的路由必须写进产物的 criteria。"""
        data = json.loads(_CORE.read_text(encoding="utf-8"))
        excludes = data.get("criteria", {}).get("excludes") or []
        assert len(excludes) >= 2, "离线算不到的两类路由未登记"


class TestCheckIsIdempotent:
    def test_check_passes_on_committed_file(self) -> None:
        """`--check` 必须与磁盘一致（生成类产物的幂等约定）。

        🔴 断言 stdout 有内容：只判 returncode 会漏掉「解码失败 ⇒ stdout=None」
        导致的假绿（memory ㉗⑦）。
        """
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.analyze.render_schema_measure_audit", "--check"],
            cwd=str(_BACKEND), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=600,
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        )
        assert proc.stdout is not None and proc.stdout.strip(), (
            f"无输出（stderr={proc.stderr!r}）"
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
        assert "reached_by" in proc.stdout
