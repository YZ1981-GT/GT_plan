"""A1 — 合并报表公式求值统一（report_engine 安全求值器复用）测试.

Phase 1（ADR-CONSOL-101/106）把 consol_report_service 的裸 `_execute_formula`
重构掉，统一改为复用 `report_engine.evaluate_formula(resolver=ConsolTrialResolver)`
+ `_safe_eval_expr`（ast 安全求值）。本测试直接验证统一后的求值语义：

- 基础算术正确（+−×÷ 括号）
- ABS/IF/ROUND/MAX/MIN 函数可用（与单体引擎语义一致 = A1 修复核心）
- 危险表达式不执行（去 eval 反模式，安全）
- ROW token 经 evaluate_formula 的 row_cache 替换后求值正确

`_safe_eval_expr` 是纯函数；ROW 路径用 evaluate_formula + 一个不取数的
resolver（ROW 只读 row_cache，不触发 resolve_tb），均不依赖 DB。

注：consol_report_service 不再有 `_execute_formula`（Phase 1 已删，
合并/单体公式现共用同一 evaluate_formula，仅注入的 resolver 不同），
故本测试改测统一后的真实求值入口。
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.report_engine import _safe_eval_expr, evaluate_formula


class _NoopResolver:
    """不取数的 AmountResolver 替身：本测试只走 ROW + 纯表达式路径（不触发 resolve_tb）。

    evaluate_formula 会用 resolver.db/project_id/year 构造 ReportFormulaParser，
    ROW token 只读 row_cache 不查 DB，故 db 给 MagicMock 即可。
    """

    def __init__(self):
        self.db = MagicMock()
        self.project_id = uuid4()
        self.year = 2025

    async def resolve_tb(self, account_code: str, column_name: str) -> Decimal:
        return Decimal("0")

    async def resolve_sum_tb(self, prefix: str, column_name: str) -> Decimal:
        return Decimal("0")


# ===========================================================================
# _safe_eval_expr 纯函数求值（与单体引擎共用，A1 语义一致核心）
# ===========================================================================


class TestSafeEvalExpr:
    def test_empty_and_blank_returns_zero(self):
        assert _safe_eval_expr("") == Decimal("0")
        assert _safe_eval_expr("  ") == Decimal("0")

    def test_basic_arithmetic(self):
        assert _safe_eval_expr("1 + 2 * 3") == Decimal("7")
        assert _safe_eval_expr("(10 - 4) / 2") == Decimal("3")

    def test_abs_function_supported(self):
        """A1 核心：合并引擎复用后支持 ABS（旧裸 eval 只支持 +−×÷）。"""
        assert _safe_eval_expr("ABS(-500)") == Decimal("500")

    def test_if_function_supported(self):
        """A1 核心：支持 IF（与单体引擎语义一致）：cond!=0 取 a 否则 b。"""
        assert _safe_eval_expr("IF(1, 100, 200)") == Decimal("100")
        assert _safe_eval_expr("IF(0, 100, 200)") == Decimal("200")

    def test_round_max_min_supported(self):
        assert _safe_eval_expr("ROUND(3.14159, 2)") == Decimal("3.14")
        assert _safe_eval_expr("MAX(3, 9)") == Decimal("9")
        assert _safe_eval_expr("MIN(3, 9)") == Decimal("3")

    def test_division_by_zero_returns_zero(self):
        assert _safe_eval_expr("10 / 0") == Decimal("0")

    def test_dangerous_expression_not_executed(self):
        """去 eval 反模式：未知函数/属性访问等 AST 节点返回 0，不执行。"""
        assert _safe_eval_expr("__import__('os')") == Decimal("0")
        assert _safe_eval_expr("os.system('rm -rf /')") == Decimal("0")


# ===========================================================================
# evaluate_formula ROW token 替换（统一引擎，合并经注入 resolver）
# ===========================================================================


class TestEvaluateFormulaRowToken:
    @pytest.mark.asyncio
    async def test_empty_formula_returns_zero(self):
        result = await evaluate_formula(None, resolver=_NoopResolver(), row_cache={})
        assert result == Decimal("0")

    @pytest.mark.asyncio
    async def test_row_token_substitution(self):
        cache = {"R1": Decimal("100.50"), "R2": Decimal("200.00")}
        result = await evaluate_formula(
            "ROW('R1') + ROW('R2')", resolver=_NoopResolver(), row_cache=cache
        )
        assert result == Decimal("300.50")

    @pytest.mark.asyncio
    async def test_abs_of_row_token(self):
        """ROW token 替换后再过 ABS（合并报表行公式常见形态）。"""
        cache = {"R1": Decimal("-500")}
        result = await evaluate_formula(
            "ABS(ROW('R1'))", resolver=_NoopResolver(), row_cache=cache
        )
        assert result == Decimal("500")

    @pytest.mark.asyncio
    async def test_missing_row_defaults_zero(self):
        """row_cache 无该 row_code → 默认 0（不报错）。"""
        result = await evaluate_formula(
            "ROW('UNKNOWN')", resolver=_NoopResolver(), row_cache={}
        )
        assert result == Decimal("0")
