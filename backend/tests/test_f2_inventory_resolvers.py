"""F2 存货 auto_data resolver 注册与逻辑测试."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.auto_data_resolvers import get_registered_sources, resolve_auto_data_source


@pytest.mark.asyncio
async def test_f2_resolvers_registered():
    registered = set(get_registered_sources())
    expected = {"f2_tb_inventory", "f2_detail_aggregation", "f2_aging_distribution"}
    assert expected <= registered


@pytest.mark.asyncio
async def test_f2_detail_aggregation_sums_closing():
    pid = uuid.uuid4()
    rows = json.dumps([
        {"openingAmt": 100, "closingAmt": 130, "agingLt1": 130, "aging1to2": 0, "aging2to3": 0, "agingGt3": 0},
        {"openingAmt": 50, "closingAmt": 70, "agingLt1": 70, "aging1to2": 0, "aging2to3": 0, "agingGt3": 0},
    ])

    mock_row = MagicMock()
    mock_row.item_id = "F2-3-rows"
    mock_row.remark = rows

    mock_result = MagicMock()
    mock_result.fetchall.return_value = [mock_row]

    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)

    result = await resolve_auto_data_source(db, pid, 2025, "f2_detail_aggregation")
    assert result is not None
    assert result["closing_total"] == 200.0
    assert result["opening_total"] == 150.0
    assert len(result["categories"]) == 1


@pytest.mark.asyncio
async def test_f2_aging_distribution_segments():
    pid = uuid.uuid4()
    rows = json.dumps([
        {"agingLt1": 100, "aging1to2": 20, "aging2to3": 5, "agingGt3": 3},
    ])

    mock_row = MagicMock()
    mock_row.remark = rows
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [mock_row]

    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)

    result = await resolve_auto_data_source(db, pid, 2025, "f2_aging_distribution")
    assert result is not None
    assert result["lt1"] == 100.0
    assert result["y1to2"] == 20.0
    assert result["total"] == 128.0
