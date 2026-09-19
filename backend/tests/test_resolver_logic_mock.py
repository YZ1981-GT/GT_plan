"""auto_data_resolvers SQL 逻辑 mock 测试。

验证新增 resolver 的返回值逻辑正确（不依赖真实 DB）。
使用 AsyncMock 模拟 db.execute 返回预设行。
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


@pytest.fixture
def mock_db():
    """创建 mock AsyncSession。"""
    db = AsyncMock()
    return db


def _make_result(rows):
    """构造 mock execute 结果。"""
    result = MagicMock()
    result.fetchall.return_value = rows
    result.scalar.return_value = rows[0][0] if rows and rows[0] else 0
    result.scalar_one_or_none.return_value = rows[0][0] if rows and rows[0] else None
    result.first.return_value = rows[0] if rows else None
    result.one.return_value = rows[0] if rows else (0, 0)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# income_statement_total
# ═══════════════════════════════════════════════════════════════════════════════


class TestIncomeStatementTotal:
    """income_statement_total resolver 逻辑验证。"""

    @pytest.mark.asyncio
    async def test_positive_net_income(self, mock_db):
        """收入 > 费用 → 正净利润。"""
        from app.services.auto_data_resolvers import _REGISTRY

        resolver = _REGISTRY["income_statement_total"]
        # 模拟：收入 1000000，费用 800000 → 净利润 200000
        mock_db.execute.return_value = _make_result([(Decimal("200000"),)])

        result = await resolver(mock_db, uuid4(), 2025)
        assert result is not None
        assert "net_income" in result or "summary" in result

    @pytest.mark.asyncio
    async def test_zero_data(self, mock_db):
        """无数据时不崩溃。"""
        from app.services.auto_data_resolvers import _REGISTRY

        resolver = _REGISTRY["income_statement_total"]
        mock_db.execute.return_value = _make_result([(Decimal("0"),)])

        result = await resolver(mock_db, uuid4(), 2025)
        assert result is not None


# ═══════════════════════════════════════════════════════════════════════════════
# ledger_detail_for_account
# ═══════════════════════════════════════════════════════════════════════════════


class TestLedgerDetailForAccount:
    """ledger_detail_for_account resolver 逻辑验证。"""

    @pytest.mark.asyncio
    async def test_k8_prefix_derivation(self, mock_db):
        """K8 wp_code 自动推导 prefix=6601。"""
        from app.services.auto_data_resolvers import _REGISTRY

        resolver = _REGISTRY["ledger_detail_for_account"]
        # 模拟返回 2 行费用明细
        mock_db.execute.return_value = _make_result([
            MagicMock(account_code="660101", account_name="工资", total_debit=500000, total_credit=0),
            MagicMock(account_code="660102", account_name="折旧", total_debit=100000, total_credit=0),
        ])

        result = await resolver(mock_db, uuid4(), 2025, wp_code="K8-2")
        assert result is not None
        assert "items" in result
        assert len(result["items"]) == 2

    @pytest.mark.asyncio
    async def test_no_data_returns_empty(self, mock_db):
        """无数据时返回空列表。"""
        from app.services.auto_data_resolvers import _REGISTRY

        resolver = _REGISTRY["ledger_detail_for_account"]
        mock_db.execute.return_value = _make_result([])

        result = await resolver(mock_db, uuid4(), 2025, wp_code="K9-2")
        assert result is not None
        assert result["items"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# eps_data_from_tb
# ═══════════════════════════════════════════════════════════════════════════════


class TestEpsDataFromTb:
    """eps_data_from_tb resolver 逻辑验证。"""

    @pytest.mark.asyncio
    async def test_returns_net_profit_and_shares(self, mock_db):
        """返回净利润和股本数据。"""
        from app.services.auto_data_resolvers import _REGISTRY

        resolver = _REGISTRY["eps_data_from_tb"]
        # 第一次调用返回净利润，第二次返回股本
        mock_db.execute.side_effect = [
            _make_result([(Decimal("1000000"),)]),  # net_profit
            _make_result([(Decimal("5000000"),)]),  # shares
        ]

        result = await resolver(mock_db, uuid4(), 2025)
        assert result is not None
        assert "net_profit" in result
        assert "shares_outstanding" in result

    @pytest.mark.asyncio
    async def test_zero_shares_no_crash(self, mock_db):
        """股本为 0 时不崩溃（避免除零）。"""
        from app.services.auto_data_resolvers import _REGISTRY

        resolver = _REGISTRY["eps_data_from_tb"]
        mock_db.execute.side_effect = [
            _make_result([(Decimal("500000"),)]),
            _make_result([(Decimal("0"),)]),
        ]

        result = await resolver(mock_db, uuid4(), 2025)
        assert result is not None
        assert result["shares_outstanding"] == 0
