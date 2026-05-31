"""P2/A1 — consol_report_service._execute_formula 公式求值统一测试.

验证合并引擎复用 report_engine 的 ast 安全求值器后：
- 基础算术正确（+−×÷ 括号）
- ABS/IF/ROUND/MAX/MIN 函数可用（与单体引擎语义一致 = A1 修复核心）
- 危险表达式不执行（去 eval 反模式，安全）
- ROW token 替换后求值正确

不依赖 DB：直接喂 row_cache + 形如纯算术/含函数的 formula。
TB/SUM_TB token 因需 DB 这里只测 ROW + 纯表达式路径（求值器本身是纯函数）。
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.services.consol_report_service import ConsolReportService


def _svc() -> ConsolReportService:
    # _execute_formula 不触 DB（只走 ROW token + 纯表达式路径），db 给 MagicMock 即可
    return ConsolReportService(MagicMock())


class TestConsolFormulaEval:
    def test_empty_formula_returns_zero(self):
        svc = _svc()
        assert svc._execute_formula(MagicMock(), 2025, None, {}) == Decimal("0")
        assert svc._execute_formula(MagicMock(), 2025, "  ", {}) == Decimal("0")

    def test_basic_arithmetic(self):
        svc = _svc()
        assert svc._execute_formula(MagicMock(), 2025, "1 + 2 * 3", {}) == Decimal("7")
        assert svc._execute_formula(MagicMock(), 2025, "(10 - 4) / 2", {}) == Decimal("3")

    def test_row_token_substitution(self):
        svc = _svc()
        cache = {"R1": Decimal("100.50"), "R2": Decimal("200.00")}
        result = svc._execute_formula(
            MagicMock(), 2025, "ROW('R1') + ROW('R2')", cache
        )
        assert result == Decimal("300.50")

    def test_abs_function_now_supported(self):
        """A1 修复核心：合并引擎现支持 ABS（旧裸 eval 只支持 +−×÷ 会失败）。"""
        svc = _svc()
        cache = {"R1": Decimal("-500")}
        result = svc._execute_formula(MagicMock(), 2025, "ABS(ROW('R1'))", cache)
        assert result == Decimal("500")

    def test_if_function_now_supported(self):
        """A1 修复核心：合并引擎现支持 IF（与单体引擎语义一致）。"""
        svc = _svc()
        # IF(cond, a, b)：cond != 0 取 a，否则 b
        cache = {"R1": Decimal("1")}
        assert svc._execute_formula(
            MagicMock(), 2025, "IF(ROW('R1'), 100, 200)", cache
        ) == Decimal("100")
        cache0 = {"R1": Decimal("0")}
        assert svc._execute_formula(
            MagicMock(), 2025, "IF(ROW('R1'), 100, 200)", cache0
        ) == Decimal("200")

    def test_division_by_zero_returns_zero(self):
        svc = _svc()
        assert svc._execute_formula(MagicMock(), 2025, "10 / 0", {}) == Decimal("0")

    def test_dangerous_expression_not_executed(self):
        """去 eval 反模式：非算术 AST 节点（函数名/属性访问）返回 0，不执行。"""
        svc = _svc()
        # __import__ 等危险调用：ast 求值器遇未知函数/节点返回 0
        assert svc._execute_formula(
            MagicMock(), 2025, "__import__('os')", {}
        ) == Decimal("0")
