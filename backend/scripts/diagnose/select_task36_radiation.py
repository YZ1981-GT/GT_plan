# -*- coding: utf-8 -*-
"""Task 36 辐射面选取：**AST** 导入/符号分析，不用裸词搜索。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 36

═══ 为什么必须用 AST ═══

本 spec 的 docstring 大量逐字引用类名与文件名（`RepresentationService`、
`materialize_coordinator.py`、`excel_entry_gate.py` …）。裸词搜索会把「文档提到」当成
「代码依赖」—— Task 31 用词搜索得到 67 个假阳性。

═══ 三类真实辐射（本任务只新增文件，不改既有生产文件）═══

1. **直接导入**：`import`/`from ... import` 里出现 `excel_entry_gate`；
2. **目录级扫描**：测试对 `app/services/workpaper_sync/` 做 `glob`/`rglob`/`iterdir`
   —— 新增一个模块文件会进入它们的集合，这是「只加文件也可能打红」的唯一途径；
3. **契约目录清册**：测试断言 `workpaper_sync_contracts/` 的文件集合（本任务不往生产
   契约目录写文件，但必须实测证明没写）。

用法::

    py -3 backend/scripts/diagnose/select_task36_radiation.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_TESTS = _REPO / "backend" / "tests"
_NEW_MODULE = "excel_entry_gate"
_SYNC_PKG_TOKENS = ("workpaper_sync",)
_DIR_SCAN_CALLS = {"glob", "rglob", "iterdir", "walk", "listdir", "scandir"}


def _imports_new_module(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(_NEW_MODULE in alias.name for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if _NEW_MODULE in (node.module or ""):
                return True
            if any(_NEW_MODULE in alias.name for alias in node.names):
                return True
    return False


def _scans_a_directory(tree: ast.AST) -> bool:
    """是否对某个路径做目录枚举（`glob`/`rglob`/`iterdir`/`os.walk`…）。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = (
            node.func.attr
            if isinstance(node.func, ast.Attribute)
            else node.func.id
            if isinstance(node.func, ast.Name)
            else ""
        )
        if name in _DIR_SCAN_CALLS:
            return True
    return False


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """所有 docstring 的 `Constant` 节点 id。

    🔴 必须剔除：本 spec 的 docstring 逐字引用包名与文件名。首轮实测
    `test_wopi_working_paper_qc_review.py` 只因 docstring 里写了一句
    `backend/tests/workpaper_sync/test_task19_writer_migration_pg.py`（真库）
    就被算进辐射面，带进 14 条与本任务无关的既存失败 —— 正是「词搜索式选取」的假阳性。
    """
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                out.add(id(body[0].value))
    return out


def _mentions_sync_package_path(tree: ast.AST) -> bool:
    """**非 docstring** 的字符串常量里出现 `workpaper_sync` 作为路径段。"""
    skip = _docstring_nodes(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in skip:
                continue
            if any(
                token == node.value or token in node.value.split("/")
                for token in _SYNC_PKG_TOKENS
            ):
                return True
    return False


def main() -> int:
    direct: list[Path] = []
    dir_scanners: list[Path] = []
    broken: list[tuple[Path, str]] = []
    for path in sorted(_TESTS.rglob("test_*.py")):
        try:
            tree = ast.parse(path.read_bytes().decode("utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:  # noqa: PERF203
            broken.append((path, str(exc)))
            continue
        if _imports_new_module(tree):
            direct.append(path)
            continue
        if _scans_a_directory(tree) and _mentions_sync_package_path(tree):
            dir_scanners.append(path)

    rel = lambda p: str(p.relative_to(_REPO)).replace("\\", "/")  # noqa: E731
    print(f"扫描测试文件 {len(list(_TESTS.rglob('test_*.py')))} 个")
    print(f"\n① 直接导入 `{_NEW_MODULE}` 的测试（{len(direct)}）：")
    for p in direct:
        print(f"   {rel(p)}")
    print(f"\n② 对 workpaper_sync 包做目录枚举的测试（{len(dir_scanners)}）：")
    for p in dir_scanners:
        print(f"   {rel(p)}")
    if broken:
        print(f"\n[WARN] {len(broken)} 个文件解析失败（不计入辐射面）：")
        for p, msg in broken[:5]:
            print(f"   {rel(p)}: {msg}")

    selected = direct + dir_scanners
    print(f"\n辐射面合计 {len(selected)} 个文件")
    print("\n跑法：")
    print("  py -3 -m pytest " + " ".join(rel(p) for p in selected) + " -q -rfE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
