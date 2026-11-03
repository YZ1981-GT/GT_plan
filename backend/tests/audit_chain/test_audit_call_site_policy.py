"""AST 守卫：append_audit_log 调用方裁决策略校验。

ADR-ALC-07: 每个调用点必须登记；mandatory 不得被吞异常；
best_effort 须在 begin_nested 内被捕获；登记项须指向存在的函数。
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from app.services.audit_chain.call_sites import CALL_SITE_REGISTRY

_APP_DIR = Path(__file__).resolve().parents[2] / "app"


def _collect_call_sites() -> list[tuple[str, str, int]]:
    """收集 backend/app/ 下所有 append_audit_log( 调用 → (rel_path, func_name, lineno)。"""
    sites: list[tuple[str, str, int]] = []
    for root, _dirs, files in os.walk(_APP_DIR):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = Path(root) / fname
            rel = str(fpath.relative_to(_APP_DIR)).replace("\\", "/")
            try:
                source = fpath.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(fpath))
            except (SyntaxError, UnicodeDecodeError):
                continue
            _find_calls_in_module(tree, rel, sites)
    return sites


def _find_calls_in_module(
    tree: ast.Module, rel: str, out: list[tuple[str, str, int]]
) -> None:
    """在 AST 模块中递归找 append_audit_log( 调用。"""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        func_name = node.name
        if func_name == "append_audit_log":
            continue  # 定义本身
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            callee = child.func
            name = ""
            if isinstance(callee, ast.Name):
                name = callee.id
            elif isinstance(callee, ast.Attribute):
                name = callee.attr
            if name == "append_audit_log":
                out.append((rel, func_name, child.lineno))


def _is_inside_non_reraising_except(
    func_node: ast.AST, call_lineno: int
) -> bool:
    """检查调用是否在「不重抛的 except Exception」的 try 块内。

    如果调用在 try 块内、且对应的 except 不重抛 → 返回 True（被吞）。
    """
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Try):
            continue
        # 检查调用是否在 try body 内
        try_start = node.lineno
        # try body 的范围：node.lineno ~ 第一个 handler 的 lineno
        handlers = node.handlers
        if not handlers:
            continue
        try_end = handlers[0].lineno
        if not (try_start <= call_lineno < try_end):
            continue
        # 检查是否有捕获 Exception 且不重抛的 handler
        for handler in handlers:
            if handler.type is not None:
                if isinstance(handler.type, ast.Name) and handler.type.id != "Exception":
                    continue
            has_reraise = any(isinstance(stmt, ast.Raise) for stmt in ast.walk(handler))
            if not has_reraise:
                return True
    return False


def _is_inside_begin_nested(func_node: ast.AST, call_lineno: int) -> bool:
    """检查调用是否在 begin_nested() 上下文管理器内。"""
    for node in ast.walk(func_node):
        if not isinstance(node, ast.AsyncWith):
            continue
        for item in node.items:
            ctx = item.context_expr
            # 匹配 db.begin_nested() 的各种写法
            if isinstance(ctx, ast.Call):
                callee = ctx.func
                attr_name = ""
                if isinstance(callee, ast.Attribute):
                    attr_name = callee.attr
                if attr_name == "begin_nested":
                    w_start = node.lineno
                    w_end = node.end_lineno or node.lineno + 100
                    if w_start <= call_lineno <= w_end:
                        return True
    return False


def _get_func_node(
    tree: ast.Module, func_name: str, call_lineno: int
) -> ast.AST | None:
    """找到包含指定调用行号的函数节点。"""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == func_name:
                start = node.lineno
                end = node.end_lineno or start + 1000
                if start <= call_lineno <= end:
                    return node
    return None


class TestAuditCallSitePolicy:
    """append_audit_log 调用方裁决策略校验。"""

    def test_all_call_sites_registered(self):
        """全仓每个 append_audit_log( 调用都在登记表中。"""
        sites = _collect_call_sites()
        unregistered: list[str] = []
        for rel, func_name, lineno in sites:
            key = f"{rel}:{func_name}"
            if key not in CALL_SITE_REGISTRY:
                unregistered.append(f"{key} (line {lineno})")
        if unregistered:
            msg = "以下调用点未在 CALL_SITE_REGISTRY 登记:\n"
            for u in unregistered:
                msg += f"  {u}\n"
            pytest.fail(msg)

    def test_registry_entries_exist(self):
        """登记表里的函数在源码中必须存在。"""
        sites = _collect_call_sites()
        site_keys = {f"{rel}:{func}" for rel, func, _ in sites}
        phantom: list[str] = []
        for key in CALL_SITE_REGISTRY:
            if key not in site_keys:
                phantom.append(key)
        if phantom:
            msg = "登记表中以下条目在源码中找不到对应调用:\n"
            for p in phantom:
                msg += f"  {p}\n"
            pytest.fail(msg)

    def test_mandatory_not_swallowed(self):
        """mandatory 策略的调用不得在不重抛的 except Exception 内。"""
        violations: list[str] = []
        for key, entry in CALL_SITE_REGISTRY.items():
            if entry["policy"] != "mandatory":
                continue
            rel, func_name = key.split(":", 1)
            fpath = _APP_DIR / rel
            if not fpath.exists():
                continue
            try:
                source = fpath.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError):
                continue
            # Find the function and the call within it
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name != func_name:
                    continue
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        callee = child.func
                        name = ""
                        if isinstance(callee, ast.Name):
                            name = callee.id
                        elif isinstance(callee, ast.Attribute):
                            name = callee.attr
                        if name == "append_audit_log":
                            if _is_inside_non_reraising_except(node, child.lineno):
                                violations.append(f"{key} (line {child.lineno})")
                break
        if violations:
            msg = "mandatory 调用在不重抛的 except Exception 内:\n"
            for v in violations:
                msg += f"  {v}\n"
            pytest.fail(msg)

    def test_best_effort_in_begin_nested(self):
        """best_effort 策略的调用须在 begin_nested 内。"""
        violations: list[str] = []
        for key, entry in CALL_SITE_REGISTRY.items():
            if entry["policy"] != "best_effort":
                continue
            rel, func_name = key.split(":", 1)
            fpath = _APP_DIR / rel
            if not fpath.exists():
                continue
            try:
                source = fpath.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError):
                continue
            func_node = None
            call_lineno = None
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name != func_name:
                    continue
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        callee = child.func
                        name = ""
                        if isinstance(callee, ast.Name):
                            name = callee.id
                        elif isinstance(callee, ast.Attribute):
                            name = callee.attr
                        if name == "append_audit_log":
                            func_node = node
                            call_lineno = child.lineno
                            break
                if func_node:
                    break
            if func_node and call_lineno:
                if not _is_inside_begin_nested(func_node, call_lineno):
                    violations.append(f"{key} (line {call_lineno})")
        if violations:
            msg = "best_effort 调用不在 begin_nested 内:\n"
            for v in violations:
                msg += f"  {v}\n"
            pytest.fail(msg)

    def test_self_check_mandatory_shape(self):
        """自检：跳过 mandatory 形态检查 → 应有违规（模拟守卫失效）。

        构造一个假的 mandatory 函数内有不重抛 except，验证检测器能发现它。
        """
        code = (
            "async def fake_mandatory_func(db):\n"
            "    try:\n"
            "        await append_audit_log(db, {})\n"
            "    except Exception:\n"
            "        pass\n"
        )
        tree = ast.parse(code)
        func_node = None
        call_lineno = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                func_node = node
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        callee = child.func
                        name = ""
                        if isinstance(callee, ast.Name):
                            name = callee.id
                        if name == "append_audit_log":
                            call_lineno = child.lineno
                            break
                break
        assert func_node is not None
        assert call_lineno is not None
        assert _is_inside_non_reraising_except(func_node, call_lineno), (
            "自检失败：检测器未能发现吞异常的 mandatory 调用"
        )
