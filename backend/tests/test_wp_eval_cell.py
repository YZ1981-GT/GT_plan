# Feature: custom-workpaper-formula-binding — 组⑤任务 8.2
# formula-hub 任务 23-1 更新：单元格分支改调 resolve_wp_cell
"""WPExecutor 单元格地址分支（^[A-Z]+\\d+$）与列名分支向后兼容。"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.formula_engine import WPExecutor
from app.services.wp_cell_reader import WpCellRead


@pytest.mark.anyio
async def test_wp_executor_cell_address_from_html_data():
    """单元格分支经 resolve_wp_cell 取值（ADR-FHIC-06 第 2 点）。"""
    project_id = uuid.uuid4()
    wp_id = uuid.uuid4()

    # 列名分支仍需 db.execute 返回 parsed_data（用于判断底稿是否存在 + 后续 col 不是单元格的情况）
    parsed = {
        "html_data": {
            "审定表": {"cells": {"B5": 12345.67}},
        },
    }
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = parsed
    db.execute = AsyncMock(return_value=result)

    # mock 在源模块上（函数体内 from ... import 取的是模块属性）
    read_ok = WpCellRead("ok", Decimal("12345.67"), None, wp_id, "审定表", matches=1)
    with patch("app.services.wp_cell_reader.resolve_wp_cell", new_callable=AsyncMock, return_value=read_ok):
        val = await WPExecutor.execute(db, project_id, "D1-1", "B5")
    assert val == Decimal("12345.67")


@pytest.mark.anyio
async def test_wp_executor_cell_missing_returns_zero():
    """单元格取不到值时 WPExecutor 返回 D("0")。"""
    project_id = uuid.uuid4()

    parsed = {"html_data": {"Sheet1": {"cells": {"A1": 1}}}}
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = parsed
    db.execute = AsyncMock(return_value=result)

    read_miss = WpCellRead("missing", None, "单元格未录入", None, None)
    with patch("app.services.wp_cell_reader.resolve_wp_cell", new_callable=AsyncMock, return_value=read_miss):
        val = await WPExecutor.execute(db, project_id, "D1-1", "Z99")
    assert val == Decimal("0")


@pytest.mark.anyio
async def test_wp_executor_cell_blocked_returns_zero():
    """blocked 状态也映射回 D("0") 保持向后兼容。"""
    project_id = uuid.uuid4()

    parsed = {}
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = parsed
    db.execute = AsyncMock(return_value=result)

    read_blocked = WpCellRead("blocked", None, "底稿记录有歧义", None, None)
    with patch("app.services.wp_cell_reader.resolve_wp_cell", new_callable=AsyncMock, return_value=read_blocked):
        val = await WPExecutor.execute(db, project_id, "D1-1", "C5")
    assert val == Decimal("0")


@pytest.mark.anyio
async def test_wp_executor_column_name_audited_amount():
    """列名分支不走 resolve_wp_cell，直接从 parsed_data 顶层键取。"""
    project_id = uuid.uuid4()
    parsed = {"audited_amount": 999, "unadjusted_amount": 1000}

    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = parsed
    db.execute = AsyncMock(return_value=result)

    val = await WPExecutor.execute(db, project_id, "E1-1", "审定数")
    assert val == Decimal("999")
