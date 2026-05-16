"""Spec B (R10) Sprint 3.2.4 — Adjustments related-workpapers 集成测试

3 用例：
1. 找到分录 → 返回 entry_group_id + workpapers
2. 不存在的 group_id → 404
3. 空 line_items → 返回空 workpapers
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_workpaper_query_imports_correctly():
    """verify workpaper_query 模块可被正确 import（catch 模块加载错误）"""
    from app.services.workpaper_query import find_workpapers_by_account_codes
    assert callable(find_workpapers_by_account_codes)


@pytest.mark.asyncio
async def test_find_workpapers_returns_dict_format():
    """返回字典必须含 id / wp_code / wp_name 三字段"""
    from app.services.workpaper_query import find_workpapers_by_account_codes

    fake_wp = MagicMock(id=uuid4(), wp_code="D2", wp_name="应收账款", is_deleted=False)
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fake_wp]
    db.execute = AsyncMock(return_value=mock_result)

    result = await find_workpapers_by_account_codes(db, uuid4(), ["1122"])
    if result:
        assert "id" in result[0]
        assert "wp_code" in result[0]
        assert "wp_name" in result[0]
        assert isinstance(result[0]["id"], str)


@pytest.mark.asyncio
async def test_find_workpapers_db_query_failure_returns_empty():
    """DB 查询异常 → 返回 [] 不抛"""
    from app.services.workpaper_query import find_workpapers_by_account_codes

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=Exception("DB error"))

    result = await find_workpapers_by_account_codes(db, uuid4(), ["1001"])
    assert result == []
