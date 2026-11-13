"""S2 任务4（ADR-CCN-07）：门禁规则 check() 的异常分支不得放行。

AST 守卫：gate_rules*.py 里 `check()` 内、捕获 `Exception` 的处理块中，不得出现 `return None`
（含裸 `return`）。异常必须返回 `self.not_executed(reason)`（命中，不放行）；结构性不适用
返回 `self.not_applicable(reason)`。业务上「已通过 / 无违规」的 `return None` 不在本守卫范围内
（只看异常分支）。

自检：守卫对违规样本必须报出，对合规样本必须不报；防止守卫本身静默失效（假绿）。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SERVICES = Path(__file__).resolve().parents[1] / "app" / "services"
_GATE_RULE_FILES = sorted(_SERVICES.glob("gate_rules*.py"))


def _catches_exception(handler: ast.ExceptHandler) -> bool:
    """`except Exception` 或 `except (…, Exception, …)`。"""
    t = handler.type
    if isinstance(t, ast.Name):
        return t.id == "Exception"
    if isinstance(t, ast.Tuple):
        return any(isinstance(e, ast.Name) and e.id == "Exception" for e in t.elts)
    return False


def _returns_none(node: ast.Return) -> bool:
    return node.value is None or (isinstance(node.value, ast.Constant) and node.value.value is None)


def find_return_none_in_check_except(source_text: str) -> list[dict]:
    """返回 check() 内 `except Exception` 块里 `return None` / 裸 `return` 的位置。"""
    tree = ast.parse(source_text)
    violations: list[dict] = []
    for fn in ast.walk(tree):
        if not (isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == "check"):
            continue
        for handler in ast.walk(fn):
            if not (isinstance(handler, ast.ExceptHandler) and _catches_exception(handler)):
                continue
            stack: list[ast.AST] = list(handler.body)
            while stack:
                node = stack.pop()
                # 嵌套函数 / 类里的 return 不属于这个异常分支
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                    continue
                if isinstance(node, ast.Return) and _returns_none(node):
                    violations.append({"check_def_line": fn.lineno, "lineno": node.lineno})
                stack.extend(ast.iter_child_nodes(node))
    return violations


class TestGateRulesNoReturnNoneInExcept:
    @pytest.mark.parametrize("path", _GATE_RULE_FILES, ids=lambda p: p.name)
    def test_check_except_branches_do_not_return_none(self, path: Path):
        violations = find_return_none_in_check_except(path.read_text(encoding="utf-8"))
        assert violations == [], (
            f"{path.name} 的 check() 异常分支仍有 return None（应改为 self.not_executed(reason)）：{violations}"
        )

    def test_gate_rule_files_found(self):
        assert len(_GATE_RULE_FILES) >= 7, f"只找到 {len(_GATE_RULE_FILES)} 个 gate_rules*.py"


class TestGuardSelfCheck:
    """守卫自检：违规样本必须报出，合规样本必须不报（否则守卫是假绿）。"""

    def test_bare_return_none_in_check_except_is_flagged(self):
        bad = """
class R:
    async def check(self, db, ctx):
        try:
            pass
        except Exception as e:
            return None
"""
        assert len(find_return_none_in_check_except(bad)) == 1

    def test_bare_return_without_value_is_flagged(self):
        bad = """
class R:
    async def check(self, db, ctx):
        try:
            pass
        except Exception:
            return
"""
        assert len(find_return_none_in_check_except(bad)) == 1

    def test_tuple_with_exception_is_flagged(self):
        bad = """
class R:
    async def check(self, db, ctx):
        try:
            pass
        except (ValueError, Exception):
            return None
"""
        assert len(find_return_none_in_check_except(bad)) == 1

    def test_not_executed_is_not_flagged(self):
        good = """
class R:
    async def check(self, db, ctx):
        try:
            pass
        except Exception as e:
            return self.not_executed(str(e))
"""
        assert find_return_none_in_check_except(good) == []

    def test_business_return_none_outside_except_is_not_flagged(self):
        good = """
class R:
    async def check(self, db, ctx):
        if not ctx:
            return None
        try:
            pass
        except Exception as e:
            return self.not_applicable(str(e))
"""
        assert find_return_none_in_check_except(good) == []

    def test_non_check_method_is_out_of_scope(self):
        good = """
class R:
    async def _load(self, db):
        try:
            pass
        except Exception:
            return None
"""
        assert find_return_none_in_check_except(good) == []

    def test_specific_exception_type_is_out_of_scope(self):
        good = """
class R:
    async def check(self, db, ctx):
        try:
            pass
        except ValueError:
            return None
"""
        assert find_return_none_in_check_except(good) == []
