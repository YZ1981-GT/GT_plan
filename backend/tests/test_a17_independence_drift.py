"""Tests for A17-7 vs B3 independence period drift detection."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.a17_independence_drift import check_independence_drift


@pytest.mark.asyncio
async def test_empty_both_sides_no_drift():
    db = AsyncMock()

    # _get_wp_id for A17-7, A17-7A, B3 → all None
    empty_scalar = MagicMock()
    empty_scalar.scalar_one_or_none.return_value = None

    db.execute = AsyncMock(return_value=empty_scalar)

    result = await check_independence_drift(db, uuid.uuid4())
    assert result["has_drift"] is False
    assert "均无可用期间数据" in result["message"]
    assert result["a177"]["business_start"] is None
    assert result["b3"]["business_start"] is None


@pytest.mark.asyncio
async def test_only_a177_no_drift():
    db = AsyncMock()
    project_id = uuid.uuid4()
    a177_wp_id = str(uuid.uuid4())

    period_row = MagicMock()
    period_row.item_id = "a177-period-business-start"
    period_row.conclusion = ""
    period_row.remark = "2025-01-01"
    period_rows = MagicMock()
    period_rows.fetchall.return_value = [period_row]

    db.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=lambda: a177_wp_id),  # A17-7 wp
            period_rows,  # A17-7 periods
            MagicMock(scalar_one_or_none=lambda: None),  # A17-7A wp
            MagicMock(scalar_one_or_none=lambda: None),  # B3 wp
        ]
    )

    result = await check_independence_drift(db, project_id)
    assert result["has_drift"] is False
    assert "B3 期间相关字段未填写" in result["message"]


@pytest.mark.asyncio
async def test_matching_periods_no_drift():
    db = AsyncMock()
    project_id = uuid.uuid4()
    a177_wp_id = str(uuid.uuid4())
    b3_wp_id = str(uuid.uuid4())

    def _period_rows():
        rows = []
        for prefix, key, val in (
            ("a177-period-business-start", "start", "2025-01-01"),
            ("a177-period-business-end", "end", "2025-12-31"),
            ("a177-period-report-start", "rs", "2025-01-01"),
            ("a177-period-report-end", "re", "2025-12-31"),
        ):
            r = MagicMock()
            r.item_id = prefix
            r.conclusion = ""
            r.remark = val
            rows.append(r)
        result = MagicMock()
        result.fetchall.return_value = rows
        return result

    def _b3_rows():
        rows = []
        for item_id, val in (
            ("b3-period-business-start", "2025-01-01"),
            ("b3-period-business-end", "2025-12-31"),
            ("b3-period-report-start", "2025-01-01"),
            ("b3-period-report-end", "2025-12-31"),
        ):
            r = MagicMock()
            r.item_id = item_id
            r.conclusion = val
            r.remark = ""
            rows.append(r)
        result = MagicMock()
        result.fetchall.return_value = rows
        return result

    db.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=lambda: a177_wp_id),  # A17-7 wp
            _period_rows(),
            MagicMock(scalar_one_or_none=lambda: None),  # A17-7A wp
            MagicMock(scalar_one_or_none=lambda: b3_wp_id),  # B3 wp
            _b3_rows(),
        ]
    )

    result = await check_independence_drift(db, project_id)
    assert result["has_drift"] is False
    assert "一致" in result["message"]


@pytest.mark.asyncio
async def test_differing_periods_has_drift():
    db = AsyncMock()
    project_id = uuid.uuid4()
    a177_wp_id = str(uuid.uuid4())
    b3_wp_id = str(uuid.uuid4())

    a177_row = MagicMock()
    a177_row.item_id = "a177-period-business-start"
    a177_row.conclusion = ""
    a177_row.remark = "2025-01-01"
    a177_end = MagicMock()
    a177_end.item_id = "a177-period-business-end"
    a177_end.conclusion = ""
    a177_end.remark = "2025-12-31"
    a177_result = MagicMock()
    a177_result.fetchall.return_value = [a177_row, a177_end]

    b3_row = MagicMock()
    b3_row.item_id = "b3-period-business-start"
    b3_row.conclusion = "2024-01-01"
    b3_row.remark = ""
    b3_end = MagicMock()
    b3_end.item_id = "b3-period-business-end"
    b3_end.conclusion = "2024-12-31"
    b3_end.remark = ""
    b3_result = MagicMock()
    b3_result.fetchall.return_value = [b3_row, b3_end]

    db.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=lambda: a177_wp_id),
            a177_result,
            MagicMock(scalar_one_or_none=lambda: None),
            MagicMock(scalar_one_or_none=lambda: b3_wp_id),
            b3_result,
        ]
    )

    result = await check_independence_drift(db, project_id)
    assert result["has_drift"] is True
    assert "不一致" in result["message"]
