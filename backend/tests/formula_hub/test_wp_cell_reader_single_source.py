"""AST 守卫：WPExecutor 单元格分支经共享读取函数（ADR-FHIC-06 第 2 点）。

扫描 ``formula_engine.py`` 的 ``WPExecutor.execute`` 方法体，断言调用了
``resolve_wp_cell``。变异 #11（恢复旧循环）时此守卫红。

若 ``wp_ref_strict.py`` 存在（任务 25 建），也扫描其中对 ``resolve_wp_cell`` 的引用。
"""
from __future__ import annotations

import ast
import importlib
import inspect
import textwrap
from pathlib import Path

import pytest


def _find_method_ast(source: str, class_name: str, method_name: str) -> ast.FunctionDef | None:
    """在源码中按类名 + 方法名找到 AST 节点。"""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                    return item
    return None


def _contains_name_ref(node: ast.AST, name: str) -> bool:
    """AST 子树里是否引用了 ``name``（Name.id 或 Attribute.attr）。"""
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == name:
            return True
        if isinstance(child, ast.Attribute) and child.attr == name:
            return True
    return False


class TestWPExecutorCallsResolveCellReader:
    """WPExecutor.execute 方法体必须引用 resolve_wp_cell（AST 级守卫）。"""

    def test_execute_body_references_resolve_wp_cell(self):
        """WPExecutor.execute 的方法体 AST 包含 resolve_wp_cell 引用。"""
        import app.services.formula_engine as mod

        src_path = Path(inspect.getfile(mod))
        source = src_path.read_text(encoding="utf-8")
        method_node = _find_method_ast(source, "WPExecutor", "execute")
        assert method_node is not None, "未找到 WPExecutor.execute 方法定义"
        assert _contains_name_ref(method_node, "resolve_wp_cell"), (
            "WPExecutor.execute 方法体未引用 resolve_wp_cell —— "
            "单元格分支必须经共享读取函数（ADR-FHIC-06 第 2 点）"
        )

    def test_execute_body_has_import_of_wp_cell_reader(self):
        """方法体包含 ``from app.services.wp_cell_reader import resolve_wp_cell`` 导入语句。"""
        import app.services.formula_engine as mod

        src_path = Path(inspect.getfile(mod))
        source = src_path.read_text(encoding="utf-8")
        method_node = _find_method_ast(source, "WPExecutor", "execute")
        assert method_node is not None

        has_import = False
        for child in ast.walk(method_node):
            if isinstance(child, ast.ImportFrom):
                if child.module and "wp_cell_reader" in child.module:
                    for alias in child.names:
                        if alias.name == "resolve_wp_cell":
                            has_import = True
                            break
        assert has_import, (
            "WPExecutor.execute 方法体缺少 wp_cell_reader 的 import —— "
            "应从 app.services.wp_cell_reader 导入 resolve_wp_cell"
        )


class TestWpRefStrictReferencesReader:
    """wp_ref_strict.py 若存在，须引用 resolve_wp_cell（任务 25 建）。"""

    def test_wp_ref_strict_references_resolve_wp_cell_if_exists(self):
        """wp_ref_strict.py 存在时，源码须包含 resolve_wp_cell 引用。"""
        try:
            spec = importlib.util.find_spec("app.services.wp_ref_strict")
        except (ModuleNotFoundError, ValueError):
            spec = None
        if spec is None or spec.origin is None:
            pytest.skip("wp_ref_strict.py 尚未建立（任务 25）")

        source = Path(spec.origin).read_text(encoding="utf-8")
        tree = ast.parse(source)
        assert _contains_name_ref(tree, "resolve_wp_cell"), (
            "wp_ref_strict.py 存在但未引用 resolve_wp_cell —— "
            "严格外部 WP 取值应经共享读取函数"
        )
