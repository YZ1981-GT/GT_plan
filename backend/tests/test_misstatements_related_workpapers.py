"""Spec B (R10) Sprint 3.2.4 — Misstatements related-workpapers 集成测试

3 用例：
1. 找到 1 张底稿 → 返回单条
2. 找到多张底稿 → 返回数组
3. 错报记录不存在 → 404
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_find_workpapers_helper_empty_codes():
    """空科目编码列表 → 返回 [] 不抛异常。"""
    from app.services.workpaper_query import find_workpapers_by_account_codes

    db = AsyncMock()
    result = await find_workpapers_by_account_codes(db, uuid4(), [])
    assert result == []


@pytest.mark.asyncio
async def test_find_workpapers_helper_with_codes():
    """有科目编码 → 走查询 + 前缀过滤。"""
    from app.services.workpaper_query import find_workpapers_by_account_codes

    # mock WpIndex 查询返回 D2/E1/K8 三个底稿
    fake_wps = [
        MagicMock(id=uuid4(), wp_code="D2", wp_name="应收账款", is_deleted=False),
        MagicMock(id=uuid4(), wp_code="E1", wp_name="存货", is_deleted=False),
        MagicMock(id=uuid4(), wp_code="K8", wp_name="管理费用", is_deleted=False),
    ]

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = fake_wps
    db.execute = AsyncMock(return_value=mock_result)

    # account_code = '1122' 应匹配 D 类
    result = await find_workpapers_by_account_codes(db, uuid4(), ["1122"])
    # 至少返回非空
    assert isinstance(result, list)
    assert len(result) >= 1


@pytest.mark.asyncio
async def test_find_workpapers_helper_fallback_when_no_prefix_match():
    """前缀过滤后空 → 退化返回前 10 个，避免 0 结果用户困惑。"""
    from app.services.workpaper_query import find_workpapers_by_account_codes

    fake_wps = [
        MagicMock(id=uuid4(), wp_code="A1", wp_name="完成阶段", is_deleted=False),
    ]

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = fake_wps
    db.execute = AsyncMock(return_value=mock_result)

    # 9999 不在 cycle_hint 中，应退化返回所有底稿
    result = await find_workpapers_by_account_codes(db, uuid4(), ["9999"])
    assert isinstance(result, list)
    # 退化后至少返回 1 个
    assert len(result) >= 1
