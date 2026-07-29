"""Characterization tests for _lmn_tb_helper.

Covers:
- Property 1: 负债类 closing 取值正确 (fetch_tb_for_balance)
- Property 2: 损益类方向正确 (fetch_tb_for_income: debit - credit)
- Property 3: 灰度 OFF 全 0
- Property 4: 异常不崩 (fail-open)
- Property 9: get_active_filter 统一口径调用
"""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import sqlalchemy as sa


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(project_id="proj-001", year=2025):
    """Build a minimal RenderContext-like object with mocked db."""
    ctx = SimpleNamespace()
    ctx.db = MagicMock()
    ctx.db.execute = AsyncMock()
    ctx.project_id = project_id
    ctx.year = year
    return ctx


def _mock_row(**kwargs):
    """Create a mock row object with attribute access."""
    row = SimpleNamespace(**kwargs)
    return row


# ---------------------------------------------------------------------------
# Property 1: 负债类 closing 取值正确
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_balance_exact_code_returns_closing(monkeypatch):
    """Exact code match returns closing_balance as end_balance, opening as begin_balance."""
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._lmn_tb_helper.settings",
        SimpleNamespace(LMN_FOUR_TABLE_EXTRACTION_ENABLED=True),
    )
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._lmn_tb_helper.get_active_filter",
        AsyncMock(return_value=sa.true()),
    )

    from app.routers.wp_render_strategies._lmn_tb_helper import fetch_tb_for_balance

    ctx = _make_ctx()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [
        _mock_row(begin_balance=1000, end_balance=5000, debit_amount=2000, credit_amount=1500)
    ]
    ctx.db.execute.return_value = mock_result

    result = await fetch_tb_for_balance(ctx, "2001")

    assert result["end_balance"] == 5000
    assert result["begin_balance"] == 1000
    assert result["debit_amount"] == 2000
    assert result["credit_amount"] == 1500
    assert result["account_code"] == "2001"


# ---------------------------------------------------------------------------
# Property 2: 损益类方向正确 (debit - credit = end_balance)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_income_direction_debit_minus_credit(monkeypatch):
    """Income function: end_balance = debit_amount - credit_amount."""
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._lmn_tb_helper.settings",
        SimpleNamespace(LMN_FOUR_TABLE_EXTRACTION_ENABLED=True),
    )
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._lmn_tb_helper.get_active_filter",
        AsyncMock(return_value=sa.true()),
    )

    from app.routers.wp_render_strategies._lmn_tb_helper import fetch_tb_for_income

    ctx = _make_ctx()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [
        _mock_row(debit_amount=8000, credit_amount=3000)
    ]
    ctx.db.execute.return_value = mock_result

    result = await fetch_tb_for_income(ctx, "6603")

    assert result["end_balance"] == 5000  # 8000 - 3000
    assert result["debit_amount"] == 8000
    assert result["credit_amount"] == 3000
    assert result["account_code"] == "6603"


# ---------------------------------------------------------------------------
# Property 3: 灰度 OFF 全 0
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_grayscale_off_returns_zero(monkeypatch):
    """When LMN_FOUR_TABLE_EXTRACTION_ENABLED is False, all numeric fields are 0."""
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._lmn_tb_helper.settings",
        SimpleNamespace(LMN_FOUR_TABLE_EXTRACTION_ENABLED=False),
    )

    from app.routers.wp_render_strategies._lmn_tb_helper import (
        fetch_tb_for_balance,
        fetch_tb_for_income,
    )

    ctx = _make_ctx()

    balance_result = await fetch_tb_for_balance(ctx, "2001")
    assert balance_result["begin_balance"] == 0
    assert balance_result["end_balance"] == 0
    assert balance_result["debit_amount"] == 0
    assert balance_result["credit_amount"] == 0
    assert balance_result["account_code"] == "2001"

    income_result = await fetch_tb_for_income(ctx, "6603")
    assert income_result["begin_balance"] == 0
    assert income_result["end_balance"] == 0
    assert income_result["debit_amount"] == 0
    assert income_result["credit_amount"] == 0
    assert income_result["account_code"] == "6603"

    # db.execute should never be called when grayscale is off
    ctx.db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Property 4: 异常不崩 (fail-open)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_db_exception_failopen(monkeypatch):
    """DB exception returns zero result without raising."""
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._lmn_tb_helper.settings",
        SimpleNamespace(LMN_FOUR_TABLE_EXTRACTION_ENABLED=True),
    )
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._lmn_tb_helper.get_active_filter",
        AsyncMock(return_value=sa.true()),
    )

    from app.routers.wp_render_strategies._lmn_tb_helper import (
        fetch_tb_for_balance,
        fetch_tb_for_income,
    )

    ctx = _make_ctx()
    ctx.db.execute = AsyncMock(side_effect=Exception("DB down"))

    # Should NOT raise
    balance_result = await fetch_tb_for_balance(ctx, "2001")
    assert balance_result["end_balance"] == 0
    assert balance_result["begin_balance"] == 0
    assert balance_result["account_code"] == "2001"

    income_result = await fetch_tb_for_income(ctx, "6603")
    assert income_result["end_balance"] == 0
    assert income_result["debit_amount"] == 0
    assert income_result["account_code"] == "6603"


# ---------------------------------------------------------------------------
# Property 1 + 9: 叶子聚合防父子双算 + get_active_filter 调用
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_leaf_aggregation_no_double_count(monkeypatch):
    """Prefix query: only leaf codes are summed (parent excluded).

    Also verifies get_active_filter is called with correct args (Property 9).
    """
    mock_get_active_filter = AsyncMock(return_value=sa.true())
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._lmn_tb_helper.settings",
        SimpleNamespace(LMN_FOUR_TABLE_EXTRACTION_ENABLED=True),
    )
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._lmn_tb_helper.get_active_filter",
        mock_get_active_filter,
    )

    from app.routers.wp_render_strategies._lmn_tb_helper import (
        fetch_tb_for_balance,
        _is_leaf,
    )

    # Verify _is_leaf logic directly
    all_codes = ["2001", "200101", "200102"]
    assert _is_leaf("2001", all_codes) is False  # parent: 200101 starts with 2001
    assert _is_leaf("200101", all_codes) is True
    assert _is_leaf("200102", all_codes) is True

    # Test via fetch_tb_for_balance: exact query returns empty, prefix returns parent + children
    ctx = _make_ctx(project_id="proj-002", year=2025)

    call_count = [0]

    async def mock_execute(stmt):
        call_count[0] += 1
        mock_result = MagicMock()
        if call_count[0] == 1:
            # First call: exact match returns empty
            mock_result.fetchall.return_value = []
        else:
            # Second call: prefix LIKE returns parent + 2 children
            mock_result.fetchall.return_value = [
                _mock_row(account_code="2001", begin_balance=1000, end_balance=1000, debit_amount=500, credit_amount=500),
                _mock_row(account_code="200101", begin_balance=600, end_balance=600, debit_amount=300, credit_amount=200),
                _mock_row(account_code="200102", begin_balance=400, end_balance=400, debit_amount=200, credit_amount=300),
            ]
        return mock_result

    ctx.db.execute = mock_execute

    result = await fetch_tb_for_balance(ctx, "2001")

    # Only leaves (200101 + 200102) should be summed, NOT parent 2001
    assert result["end_balance"] == 1000  # 600 + 400 (not 2000 which would include parent)
    assert result["begin_balance"] == 1000  # 600 + 400
    assert result["debit_amount"] == 500  # 300 + 200
    assert result["credit_amount"] == 500  # 200 + 300

    # Property 9: verify get_active_filter was called with correct signature
    from app.models.audit_platform_models import TbBalance
    mock_get_active_filter.assert_called_once_with(
        ctx.db, TbBalance.__table__, "proj-002", 2025
    )
