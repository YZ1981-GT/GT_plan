"""守卫：check 脚本不得把 active spec 路径写死，否则 spec 归档后恒红。

背景（铁律：归档必须同步守卫 + ㉗ 永红门禁等于门禁失效）：
    守卫脚本若在模块级把 `.kiro/specs/<具体名>/...` 写死，spec 一归档到
    `.kiro/specs/_archive/<nn>-xxx/<name>/`，active 路径就不存在，守卫对任何
    clean checkout 恒红，且报的是误导性的"文件不存在"而非 spec 真实状态。

    正确做法：通过 `backend/scripts/check/_spec_dir.resolve_spec_dir(name, ...)`
    解析目录（active 优先、回退 _archive/**）。

    本守卫用 AST（禁文本 in 匹配——docstring/注释会骗过）扫 backend/scripts/check/
    下所有 .py：若某文件在**非 docstring 位置**出现 `.kiro/specs/<具体名>` 形态的
    字符串字面量，却**没有** import resolve_spec_dir，即判违规。

    这同时覆盖了"将来新建守卫又犯同样错误"的回归场景。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_CHECK_DIR = Path(__file__).resolve().parents[1] / "scripts" / "check"

# 命中"具体 spec 名"的字面量：.kiro/specs/<name> 其中 <name> 是具体名
# （不是 _archive、不含通配符 * 或 f-string 占位 {}）。
_SPEC_LITERAL = re.compile(r"\.kiro/specs/(?!_archive)([a-z0-9][a-z0-9-]*)")


def _check_scripts() -> list[Path]:
    return sorted(p for p in _CHECK_DIR.glob("*.py") if p.name != "_spec_dir.py")


def _docstring_nodes(tree: ast.Module) -> set[int]:
    """收集所有 docstring 字符串常量的 id()，用于从违规判定中排除。"""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                    ids.add(id(first.value))
    return ids


def _module_imports_resolver(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "_spec_dir":
            if any(a.name == "resolve_spec_dir" for a in node.names):
                return True
    return False


def _hardcoded_spec_literals(tree: ast.Module, docstring_ids: set[int]) -> list[str]:
    """返回非 docstring 位置、硬编码具体 spec 名的字符串字面量列表。"""
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstring_ids:
                continue
            m = _SPEC_LITERAL.search(node.value)
            if m:
                hits.append(node.value.strip()[:120])
    return hits


class TestSpecDirArchiveResilience:
    def test_no_check_script_hardcodes_active_spec_path(self):
        violations: list[str] = []
        for script in _check_scripts():
            try:
                tree = ast.parse(script.read_text(encoding="utf-8"))
            except (SyntaxError, OSError):
                continue
            docstring_ids = _docstring_nodes(tree)
            literals = _hardcoded_spec_literals(tree, docstring_ids)
            if not literals:
                continue
            # 文件里确实有具体 spec 路径字面量：必须也 import 了 resolve_spec_dir。
            if not _module_imports_resolver(tree):
                violations.append(
                    f"  {script.name}: 硬编码 spec 路径但未用 resolve_spec_dir -> {literals[:3]}"
                )

        if violations:
            pytest.fail(
                "以下 check 脚本把 active spec 路径写死，spec 归档后会恒红。\n"
                "请改用 backend/scripts/check/_spec_dir.resolve_spec_dir(name, require_files=[...]):\n"
                + "\n".join(violations)
            )

    def test_resolve_spec_dir_falls_back_to_archive(self):
        """require_files 回退语义：空壳 active 不合格时回退含该文件的 archive。"""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_spec_dir_under_test", _CHECK_DIR / "_spec_dir.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # formula-runtime-convergence 已完全归档：require tasks.md 必落 _archive
        d = mod.resolve_spec_dir("formula-runtime-convergence", require_files=["tasks.md"])
        assert d.exists(), f"应解析到存在的归档目录，实际: {d}"
        assert "_archive" in str(d), f"应回退到 _archive，实际: {d}"
        assert (d / "tasks.md").exists(), "回退目录应含要求的 tasks.md"

        # 不存在的 spec：返回 active 路径且不 raise（让下游报清晰错误）
        missing = mod.resolve_spec_dir("a-definitely-missing-spec-zzz", require_files=["tasks.md"])
        assert "_archive" not in str(missing)
        assert not missing.exists()
