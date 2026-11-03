"""S2 Task 1：CheckOutcome 五态契约 — 工厂函数 + AST 守卫。

AST 守卫：``passed(`` 不得在 ``except`` 块内调用（同母 spec 模式）。
自检：违规样本必须让守卫打红。
"""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

from app.models.phase14_enums import CheckStatus
from app.services.check_outcome import (
    CheckOutcome,
    STATUS_LABEL,
    passed,
    failed,
    not_executed,
    not_applicable,
    error,
)

# ── 路径 ──
_SRC = Path(__file__).resolve().parents[1] / "app" / "services" / "check_outcome.py"


# ════════════════════════════════════════════
# 工厂函数单元测试
# ════════════════════════════════════════════


class TestFactoryFunctions:
    def test_passed(self):
        o = passed("R-01", "xr")
        assert o.status == CheckStatus.passed
        assert o.label == "通过"
        assert o.severity == "info"
        assert o.rule_id == "R-01"
        assert o.source == "xr"

    def test_failed_with_values(self):
        o = failed("R-02", "cross_check", reason="差额超限",
                    left=100.0, right=90.0, diff=10.0, severity="blocking")
        assert o.status == CheckStatus.failed
        assert o.label == "未通过"
        assert o.left == 100.0
        assert o.right == 90.0
        assert o.diff == 10.0
        assert o.severity == "blocking"
        assert o.reason == "差额超限"

    def test_not_executed(self):
        o = not_executed("R-03", "gate", reason="数据库异常")
        assert o.status == CheckStatus.not_executed
        assert o.label == "未执行（原因）"
        assert o.severity == "warning"

    def test_not_applicable(self):
        o = not_applicable("R-04", "gate", reason="表不存在")
        assert o.status == CheckStatus.not_applicable
        assert o.label == "不适用"
        assert o.severity == "info"

    def test_error(self):
        o = error("R-05", "note", reason="除零错误")
        assert o.status == CheckStatus.error
        assert o.label == "检查异常"
        assert o.severity == "warning"

    def test_to_dict_minimal(self):
        o = passed("R-01", "xr")
        d = o.to_dict()
        assert d["status"] == "passed"
        assert d["label"] == "通过"
        assert "left" not in d  # None 不输出
        assert "diff" not in d

    def test_to_dict_with_values(self):
        o = failed("R-02", "xr", left=1.0, right=2.0, diff=1.0)
        d = o.to_dict()
        assert d["left"] == 1.0
        assert d["right"] == 2.0
        assert d["diff"] == 1.0

    def test_all_five_statuses_have_labels(self):
        for s in CheckStatus:
            assert s in STATUS_LABEL or s.value in STATUS_LABEL, f"{s} 缺中文标签"


# ════════════════════════════════════════════
# AST 守卫：passed() 不得在 except 块内
# ════════════════════════════════════════════


def _find_passed_in_except(source_text: str) -> list[int]:
    """扫描源码，返回在 except 块内调用 passed() 的行号列表。"""
    tree = ast.parse(source_text)
    violations: list[int] = []
    except_depth = [0]

    class Visitor(ast.NodeVisitor):
        def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
            except_depth[0] += 1
            self.generic_visit(node)
            except_depth[0] -= 1

        def visit_Call(self, node: ast.Call) -> None:
            if except_depth[0] > 0:
                func = node.func
                name = None
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name == "passed":
                    violations.append(node.lineno)
            self.generic_visit(node)

    Visitor().visit(tree)
    return violations


class TestPassedNotInExceptGuard:
    """AST 守卫 + 违规样本自检"""

    def test_check_outcome_source_clean(self):
        """check_outcome.py 中 passed() 不得出现在 except 块内"""
        src = _SRC.read_text("utf-8")
        violations = _find_passed_in_except(src)
        assert violations == [], f"check_outcome.py 行 {violations} 在 except 内调用 passed()"

    def test_violating_sample_detected(self):
        """自检：构造一段在 except 内调用 passed() 的代码，守卫必须检测到"""
        bad_code = textwrap.dedent("""\
            try:
                x = 1
            except Exception:
                result = passed("bad", "test")
        """)
        violations = _find_passed_in_except(bad_code)
        assert len(violations) == 1, "守卫未检测到 except 块内的 passed() 调用"

    def test_passed_outside_except_ok(self):
        """正常代码中的 passed() 不应被标记"""
        good_code = textwrap.dedent("""\
            result = passed("ok", "test")
            try:
                x = 1
            except Exception:
                result = failed("bad", "test")
        """)
        violations = _find_passed_in_except(good_code)
        assert violations == []
