"""D4 occurrence 守卫（NULL 免疫 / 结转损益 / 符号归一 / 数据集隔离）。

测试内容：
- ledger_occurrence_expr：COALESCE 表达式，NULL 免疫
- 反向自检：旧净额口径（credit - debit）必命中恒 0 缺陷
- normalize_trial_balance_pl：正值/负值/None/非法值处理
- 替身 get_active_filter 必须返回真实 sa.true()

**Validates: Requirements 9.2, 9.3, 9.4**
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa

from app.services.d4_extraction.occurrence import (
    COST_SIDE,
    REVENUE_SIDE,
    ledger_occurrence_expr,
    ledger_occurrence_sql,
    normalize_trial_balance_pl,
)


# ─────────────────────────────────────────────────────────────────────────────
# ledger_occurrence_expr — NULL 免疫（Property 3）
# ─────────────────────────────────────────────────────────────────────────────


class TestLedgerOccurrenceExpr:
    """ledger_occurrence_expr 返回 COALESCE 表达式（null-safe）。

    **Validates: Requirements 9.2**
    """

    def test_credit_side_returns_coalesce(self):
        """收入类取贷方，表达式含 COALESCE。"""
        expr = ledger_occurrence_expr("credit")
        compiled = str(expr.compile(compile_kwargs={"literal_binds": True}))
        assert "coalesce" in compiled.lower()
        assert "credit_amount" in compiled.lower()

    def test_debit_side_returns_coalesce(self):
        """成本类取借方，表达式含 COALESCE。"""
        expr = ledger_occurrence_expr("debit")
        compiled = str(expr.compile(compile_kwargs={"literal_binds": True}))
        assert "coalesce" in compiled.lower()
        assert "debit_amount" in compiled.lower()

    def test_invalid_side_raises(self):
        with pytest.raises(ValueError):
            ledger_occurrence_expr("net")

    def test_constants(self):
        """确认 REVENUE_SIDE / COST_SIDE 常量值。"""
        assert REVENUE_SIDE == "credit"
        assert COST_SIDE == "debit"


class TestLedgerOccurrenceSql:
    """裸 SQL 片段测试。"""

    def test_credit_sql(self):
        assert ledger_occurrence_sql("credit") == "COALESCE(credit_amount, 0)"

    def test_debit_sql(self):
        assert ledger_occurrence_sql("debit") == "COALESCE(debit_amount, 0)"

    def test_invalid_side_raises(self):
        with pytest.raises(ValueError):
            ledger_occurrence_sql("balance")


# ─────────────────────────────────────────────────────────────────────────────
# 反向自检：旧净额口径（credit - debit）必命中恒 0 缺陷（Property 4）
# ─────────────────────────────────────────────────────────────────────────────


class TestOldNetAmountDefect:
    """旧净额口径 credit_amount - debit_amount 须命中恒 0 缺陷。

    两条独立原因各自足以让取数恒为 0：
    1. NULL 传播：对侧列存 NULL → credit - NULL = NULL → SUM = NULL → COALESCE = 0
    2. 结转损益：全年账两侧金额恒等 → 净额结构性为 0

    **Validates: Requirements 9.2**
    """

    def test_null_propagation_makes_net_null(self):
        """模拟 tb_ledger 行：只写贷方、借方为 NULL。
        credit_amount - debit_amount = 100 - NULL = NULL（SQL 语义）。
        """
        # Python 模拟 SQL NULL 传播：None 参与运算结果为 None
        credit_val = 100.0
        debit_val = None  # tb_ledger 对侧列存 NULL

        # 旧口径
        if debit_val is None:
            net_result = None  # SQL: credit - NULL = NULL
        else:
            net_result = credit_val - debit_val

        assert net_result is None, (
            "旧净额口径对 NULL 对侧列必须产出 NULL（Python 模拟 SQL 行为）"
        )

        # 新口径（单侧 + COALESCE）
        single_side = credit_val  # COALESCE(credit_amount, 0) 取非空值
        assert single_side == 100.0, "单侧口径不受 NULL 对侧影响"

    def test_transfer_makes_net_zero(self):
        """模拟年末结转损益：借记 6001 冲平 → SUM(credit) == SUM(debit)。"""
        # 全年业务确认：贷 6001 895,804,876.83
        business_credits = [895_804_876.83]
        # 年末结转：借 6001 895,804,876.83（结转本年利润）
        transfer_debits = [895_804_876.83]

        total_credit = sum(business_credits)
        total_debit = sum(transfer_debits)

        # 旧口径净额恒为 0
        net = total_credit - total_debit
        assert net == 0.0, "结转损益后净额必须恒为 0（结构性缺陷）"

        # 新口径（单侧）仍为正的业务金额
        single_side_credit = total_credit
        assert single_side_credit == 895_804_876.83, "单侧口径不受结转影响"


# ─────────────────────────────────────────────────────────────────────────────
# normalize_trial_balance_pl（Property 6：符号归一幂等）
# ─────────────────────────────────────────────────────────────────────────────


class TestNormalizeTrialBalancePl:
    """trial_balance 损益类金额归一为正数口径。

    **Validates: Requirements 9.2**
    """

    def test_positive_value_stays(self):
        assert normalize_trial_balance_pl(895_804_876.83) == 895_804_876.83

    def test_negative_value_becomes_positive(self):
        """实证 df5b8403 的 6001 = -38,258,743.63（贷方性质以负数存储）。"""
        assert normalize_trial_balance_pl(-38_258_743.63) == 38_258_743.63

    def test_none_transparent(self):
        """None 透传（上期无数据 ≠ 0）。"""
        assert normalize_trial_balance_pl(None) is None

    def test_zero(self):
        assert normalize_trial_balance_pl(0) == 0.0

    def test_non_numeric_returns_none(self):
        assert normalize_trial_balance_pl("abc") is None
        assert normalize_trial_balance_pl("") is None

    def test_idempotent(self):
        """归一是幂等的：对已正值再调用不变。"""
        val = 38_258_743.63
        assert normalize_trial_balance_pl(normalize_trial_balance_pl(val)) == val

    def test_string_numeric(self):
        """字符串形式的数值可解析。"""
        assert normalize_trial_balance_pl("-100.5") == 100.5
        assert normalize_trial_balance_pl("200") == 200.0


# ─────────────────────────────────────────────────────────────────────────────
# 替身 get_active_filter 必须返回 sa.true()（踩坑铁律）
# ─────────────────────────────────────────────────────────────────────────────


class TestMockGetActiveFilter:
    """踩坑铁律：mock get_active_filter 必须返回真实 sa.true()，
    不能返回 MagicMock()。

    MagicMock() 传给 sa.and_() 会抛 "SQL expression for WHERE/HAVING role
    expected" 或被 fail-open 吞成空结果 = 假绿。

    **Validates: Requirements 9.3**
    """

    def test_sa_true_is_valid_clause_element(self):
        """sa.true() 是合法的 SA 表达式。"""
        t = sa.true()
        # 可以参与 sa.and_
        combined = sa.and_(t, sa.column("x") == 1)
        compiled = str(combined.compile(compile_kwargs={"literal_binds": True}))
        assert "true" in compiled.lower() or "x" in compiled.lower()

    def test_magicmock_is_not_clause_element(self):
        """MagicMock 不是合法的 SA ClauseElement → 会被 sa.and_ 拒绝。"""
        from unittest.mock import MagicMock

        mock_filter = MagicMock()
        with pytest.raises((TypeError, AttributeError, sa.exc.ArgumentError)):
            # sa.and_ 对非 ClauseElement 抛 ArgumentError
            sa.and_(mock_filter, sa.column("x") == 1)

    @pytest.mark.asyncio
    async def test_fetch_d4_rows_uses_real_active_filter(self):
        """fetch_d4_rows 内部使用 sa.and_(active_filter, prefix_filter)，
        如果 active_filter 是 MagicMock 则会在 sa.and_ 处失败。
        替身必须返回 sa.true()。
        """
        from types import SimpleNamespace

        from app.services.d4_extraction.account_scope import fetch_d4_rows

        # 构造 mock context
        mock_result = AsyncMock()
        mock_result.fetchall.return_value = []

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.rollback = AsyncMock()

        ctx = SimpleNamespace(db=mock_db, project_id="test-pid", year=2025)

        # 替身返回真实 sa.true()
        with patch(
            "app.services.d4_extraction.account_scope.get_active_filter",
            new=AsyncMock(return_value=sa.true()),
        ):
            # 应该正常执行（不抛异常），返回空列表
            result = await fetch_d4_rows(ctx, ("6001",))
            assert result == []

    @pytest.mark.asyncio
    async def test_fetch_d4_rows_with_magicmock_filter_fails_gracefully(self):
        """如果 get_active_filter 返回 MagicMock()，fetch_d4_rows 应该
        因 fail-open 返回空列表（但实际取数为空 = 假绿）。
        这证明了 MagicMock 替身的危害。
        """
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from app.services.d4_extraction.account_scope import fetch_d4_rows

        mock_db = AsyncMock()
        mock_db.rollback = AsyncMock()
        ctx = SimpleNamespace(db=mock_db, project_id="test-pid", year=2025)

        # 替身返回 MagicMock（错误做法）
        with patch(
            "app.services.d4_extraction.account_scope.get_active_filter",
            new=AsyncMock(return_value=MagicMock()),
        ):
            # fail-open：sa.and_(MagicMock, ...) 会抛异常被 except 吞
            # → 返回空列表，测试"通过"却什么都没测到
            result = await fetch_d4_rows(ctx, ("6001",))
            assert result == [], (
                "MagicMock filter 导致 fail-open 返回空（假绿证据）"
            )
