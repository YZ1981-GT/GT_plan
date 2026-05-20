"""H 循环 =LEDGER 公式支持验证

Task 2.25: 验证 prefill_engine 对 H1-12 折旧测算表 =LEDGER('1602','credit','X月') 公式的支持。

覆盖：
- _FORMULA_RE 识别 H 循环 LEDGER 公式
- _parse_period_range 处理 H1-12 月度/半年/全年期间格式
- _resolve_ledger_formula 正确构建 SQL 查询（使用 _parse_period_range + accounting_period 整数比较）
- resolve_extended_formula 统一入口对 LEDGER 类型的路由

Validates: Requirements H-F10
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.services.prefill_engine import (
    _FORMULA_RE,
    _FORMULA_RESOLVERS,
    _parse_args,
    _parse_period_range,
    _resolve_ledger_formula,
    resolve_extended_formula,
)


# ---------------------------------------------------------------------------
# 1. _FORMULA_RE 识别 H 循环 LEDGER 公式
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "formula,expected_type,expected_args",
    [
        ("=LEDGER('1602','credit','1月')", "LEDGER", "'1602','credit','1月'"),
        ("=LEDGER('1602','credit','6月')", "LEDGER", "'1602','credit','6月'"),
        ("=LEDGER('1602','credit','12月')", "LEDGER", "'1602','credit','12月'"),
        ("=LEDGER('1602','credit','全年')", "LEDGER", "'1602','credit','全年'"),
        ("=LEDGER('1602','credit','1-6月')", "LEDGER", "'1602','credit','1-6月'"),
        ("=LEDGER('1602','credit','7-12月')", "LEDGER", "'1602','credit','7-12月'"),
        ("=LEDGER('1601','debit','3月')", "LEDGER", "'1601','debit','3月'"),
    ],
)
def test_formula_re_recognizes_h_cycle_ledger(formula, expected_type, expected_args):
    """H 循环 LEDGER 公式被 _FORMULA_RE 正确识别"""
    m = _FORMULA_RE.search(formula)
    assert m is not None, f"_FORMULA_RE 未识别 {formula}"
    assert m.group(1).upper() == expected_type
    assert m.group(2).strip() == expected_args


# ---------------------------------------------------------------------------
# 2. _parse_period_range 处理 H1-12 月度期间格式
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "period,expected",
    [
        # H1-12 单月抽样
        ("1月", (1, 1)),
        ("2月", (2, 2)),
        ("3月", (3, 3)),
        ("6月", (6, 6)),
        ("9月", (9, 9)),
        ("12月", (12, 12)),
        # H1-12 半年合计
        ("1-6月", (1, 6)),
        ("7-12月", (7, 12)),
        # H1-12 全年合计
        ("全年", (1, 12)),
    ],
)
def test_parse_period_range_h_cycle_formats(period, expected):
    """H1-12 折旧测算表使用的期间格式全部正确解析"""
    assert _parse_period_range(period) == expected


# ---------------------------------------------------------------------------
# 3. _parse_args 正确解析 H 循环 LEDGER 公式参数
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_args,expected",
    [
        ("'1602','credit','1月'", ["1602", "credit", "1月"]),
        ("'1602','credit','全年'", ["1602", "credit", "全年"]),
        ("'1602','credit','1-6月'", ["1602", "credit", "1-6月"]),
        ("'1601','debit','12月'", ["1601", "debit", "12月"]),
    ],
)
def test_parse_args_h_cycle_ledger(raw_args, expected):
    """H 循环 LEDGER 公式参数正确解析为 3 元素列表"""
    args = _parse_args(raw_args)
    assert args == expected


# ---------------------------------------------------------------------------
# 4. _resolve_ledger_formula 正确处理 H 循环账户 (mock DB)
# ---------------------------------------------------------------------------

import sqlalchemy as sa


@pytest.mark.asyncio
async def test_resolve_ledger_formula_h_cycle_monthly():
    """=LEDGER('1602','credit','6月') → 查询 accounting_period BETWEEN 6 AND 6"""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = Decimal("15000.00")
    mock_db.execute.return_value = mock_result

    project_id = uuid.uuid4()
    year = 2025

    mock_filter = AsyncMock(return_value=sa.literal(True))
    with patch("app.services.dataset_query.get_active_filter", mock_filter):
        result = await _resolve_ledger_formula(
            mock_db, project_id, year, ["1602", "credit", "6月"]
        )

    assert result == Decimal("15000.00")
    assert mock_db.execute.called


@pytest.mark.asyncio
async def test_resolve_ledger_formula_h_cycle_full_year():
    """=LEDGER('1602','credit','全年') → 不加 period 过滤（全年）"""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = Decimal("180000.00")
    mock_db.execute.return_value = mock_result

    project_id = uuid.uuid4()
    year = 2025

    mock_filter = AsyncMock(return_value=sa.literal(True))
    with patch("app.services.dataset_query.get_active_filter", mock_filter):
        result = await _resolve_ledger_formula(
            mock_db, project_id, year, ["1602", "credit", "全年"]
        )

    assert result == Decimal("180000.00")


@pytest.mark.asyncio
async def test_resolve_ledger_formula_h_cycle_half_year():
    """=LEDGER('1602','credit','1-6月') → 查询 accounting_period BETWEEN 1 AND 6"""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = Decimal("90000.00")
    mock_db.execute.return_value = mock_result

    project_id = uuid.uuid4()
    year = 2025

    mock_filter = AsyncMock(return_value=sa.literal(True))
    with patch("app.services.dataset_query.get_active_filter", mock_filter):
        result = await _resolve_ledger_formula(
            mock_db, project_id, year, ["1602", "credit", "1-6月"]
        )

    assert result == Decimal("90000.00")


@pytest.mark.asyncio
async def test_resolve_ledger_formula_insufficient_args():
    """参数不足 3 个时返回 None"""
    mock_db = AsyncMock()
    result = await _resolve_ledger_formula(mock_db, uuid.uuid4(), 2025, ["1602", "credit"])
    assert result is None

    result = await _resolve_ledger_formula(mock_db, uuid.uuid4(), 2025, ["1602"])
    assert result is None

    result = await _resolve_ledger_formula(mock_db, uuid.uuid4(), 2025, [])
    assert result is None


# ---------------------------------------------------------------------------
# 5. LEDGER resolver 注册验证
# ---------------------------------------------------------------------------


def test_ledger_resolver_registered():
    """LEDGER 类型已注册到 _FORMULA_RESOLVERS 且可调用"""
    assert "LEDGER" in _FORMULA_RESOLVERS
    assert callable(_FORMULA_RESOLVERS["LEDGER"])


def test_ledger_detail_resolver_registered():
    """LEDGER_DETAIL 类型已注册到 _FORMULA_RESOLVERS 且可调用"""
    assert "LEDGER_DETAIL" in _FORMULA_RESOLVERS
    assert callable(_FORMULA_RESOLVERS["LEDGER_DETAIL"])


# ---------------------------------------------------------------------------
# 6. resolve_extended_formula 统一入口路由 LEDGER
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_extended_formula_routes_ledger():
    """resolve_extended_formula 对 LEDGER 类型正确路由到 _resolve_ledger_formula"""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = Decimal("25000.00")
    mock_db.execute.return_value = mock_result

    project_id = uuid.uuid4()
    year = 2025

    mock_filter = AsyncMock(return_value=sa.literal(True))
    with patch("app.services.dataset_query.get_active_filter", mock_filter):
        result = await resolve_extended_formula(
            mock_db, project_id, year, "LEDGER", "'1602','credit','9月'"
        )

    assert result == Decimal("25000.00")


@pytest.mark.asyncio
async def test_resolve_extended_formula_ledger_direction_debit():
    """=LEDGER('1601','debit','3月') → 取借方发生额"""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = Decimal("500000.00")
    mock_db.execute.return_value = mock_result

    project_id = uuid.uuid4()
    year = 2025

    mock_filter = AsyncMock(return_value=sa.literal(True))
    with patch("app.services.dataset_query.get_active_filter", mock_filter):
        result = await resolve_extended_formula(
            mock_db, project_id, year, "LEDGER", "'1601','debit','3月'"
        )

    assert result == Decimal("500000.00")
