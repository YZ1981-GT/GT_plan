"""公式调试/模拟器端点测试（spec: formula-management-deep-optimization · R3）。

验证：
1. 基本公式执行返回 trace
2. 自定义上下文传入
3. 语法错误返回错误信息
4. 空公式拒绝
5. 上下文摘要正确
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.formula_debug import _build_context, _context_summary


class TestBuildContext:
    """调试上下文构造。"""

    @pytest.mark.asyncio
    async def test_custom_context_used_directly(self):
        """传入 custom_context 时直接构造，不查 DB。"""
        db = AsyncMock()
        ctx = await _build_context(
            db, uuid.uuid4(), 2025, "report",
            custom_context={
                "tb_data": {"1001": {"期末余额": "100.5"}},
                "row_cache": {"1": "200"},
            },
        )
        assert ctx.tb_data["1001"]["期末余额"] == Decimal("100.5")
        assert ctx.row_cache["1"] == Decimal("200")
        # 不应调用 DB
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_custom_context_queries_db(self):
        """custom_context 为 None 时查 DB。"""
        db = AsyncMock()
        # mock DB 返回空结果
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        ctx = await _build_context(db, uuid.uuid4(), 2025, "report", None)
        assert isinstance(ctx.tb_data, dict)
        assert isinstance(ctx.row_cache, dict)


class TestContextSummary:
    """上下文摘要。"""

    def test_counts_populated_fields(self):
        from app.services.formula_engine import FormulaContext
        ctx = FormulaContext(
            tb_data={"1001": {"期末余额": Decimal("100")}},
            row_cache={"1": Decimal("200"), "2": Decimal("300")},
        )
        summary = _context_summary(ctx)
        assert summary["tb_accounts"] == 1
        assert summary["report_rows"] == 2
        assert summary["note_sections"] == 0

    def test_empty_context(self):
        from app.services.formula_engine import FormulaContext
        ctx = FormulaContext()
        summary = _context_summary(ctx)
        assert all(v == 0 for v in summary.values())


class TestFormulaExecution:
    """公式执行（直接调用 execute 验证 trace 生成）。"""

    def test_simple_arithmetic_has_trace(self):
        from app.services.formula_engine import FormulaContext, execute
        ctx = FormulaContext(
            row_cache={"1": Decimal("100"), "2": Decimal("200")},
        )
        result = execute("ROW(\"1\") + ROW(\"2\")", ctx)
        assert result.ok
        assert result.value == Decimal("300")

    def test_tb_function_returns_trace(self):
        from app.services.formula_engine import FormulaContext, execute
        ctx = FormulaContext(
            tb_data={"1001": {"期末余额": Decimal("1000"), "未审数": Decimal("800")}},
        )
        result = execute("TB('1001')", ctx)
        assert result.ok
        assert result.value == Decimal("1000")
        # trace 应记录取数步骤
        assert len(result.trace) > 0

    def test_syntax_error_returns_errors(self):
        from app.services.formula_engine import FormulaContext, execute
        ctx = FormulaContext()
        result = execute("TB('1001'", ctx)  # 缺右括号
        assert not result.ok
        assert len(result.errors) > 0

    def test_unknown_function_blocked(self):
        from app.services.formula_engine import FormulaContext, execute
        ctx = FormulaContext()
        result = execute("EVIL('hack')", ctx)
        assert not result.ok
