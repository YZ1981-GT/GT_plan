# Feature: custom-workpaper-formula-binding — 组⑤任务 8.2
"""WPExecutor 单元格地址分支（^[A-Z]+\\d+$）与列名分支向后兼容。"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.formula_engine import WPExecutor


@pytest.mark.anyio
async def test_wp_executor_cell_address_from_html_data():
    project_id = uuid.uuid4()
    parsed = {
        "html_data": {
            "审定表": {
                "cells": {
                    "A5": "货币资金",
                    "B5": 12345.67,
                }
            }
        }
    }

    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = parsed
    db.execute = AsyncMock(return_value=result)

    val = await WPExecutor.execute(db, project_id, "D1-1", "B5")
    assert val == Decimal("12345.67")


@pytest.mark.anyio
async def test_wp_executor_cell_missing_returns_zero():
    project_id = uuid.uuid4()
    parsed = {"html_data": {"Sheet1": {"cells": {"A1": 1}}}}

    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = parsed
    db.execute = AsyncMock(return_value=result)

    val = await WPExecutor.execute(db, project_id, "D1-1", "Z99")
    assert val == Decimal("0")


@pytest.mark.anyio
async def test_wp_executor_column_name_audited_amount():
    project_id = uuid.uuid4()
    parsed = {"audited_amount": 999, "unadjusted_amount": 1000}

    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = parsed
    db.execute = AsyncMock(return_value=result)

    val = await WPExecutor.execute(db, project_id, "E1-1", "审定数")
    assert val == Decimal("999")
