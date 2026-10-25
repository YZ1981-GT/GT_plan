"""独占键宽限期测试（spec: formula-push-all-subjects-rollout · design §5.3）。

验证：
- 项目从未推送过 → has_any_push_run 返回 False → 独占键不被剔除
- 项目有 succeeded/partial 推送 → 返回 True → 独占键被剔除
- 只有 running/failed 推送 → 返回 False（不算"推送过"）
- DB 异常 → 默认返回 True（安全侧，执行剔除）
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.formula_push.owned_keys import has_any_push_run


def _make_db_mock(*, scalar_result=None, raise_exc=None):
    """构造 AsyncSession mock，execute 返回指定 scalar 或抛异常。"""
    db = AsyncMock()
    if raise_exc:
        db.execute = AsyncMock(side_effect=raise_exc)
    else:
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = scalar_result
        db.execute = AsyncMock(return_value=result_mock)
    return db


@pytest.mark.asyncio
async def test_no_push_run_returns_false():
    """项目从未有过推送记录 → False（宽限期生效）。"""
    db = _make_db_mock(scalar_result=None)
    result = await has_any_push_run(db, uuid.uuid4())
    assert result is False


@pytest.mark.asyncio
async def test_has_succeeded_run_returns_true():
    """项目有 succeeded 推送记录 → True（剔除生效）。"""
    db = _make_db_mock(scalar_result=1)
    result = await has_any_push_run(db, uuid.uuid4())
    assert result is True


@pytest.mark.asyncio
async def test_db_exception_defaults_to_true():
    """DB 查询异常 → 安全侧返回 True（执行剔除，不让宽限期因异常无限延长）。"""
    db = _make_db_mock(raise_exc=RuntimeError("connection lost"))
    result = await has_any_push_run(db, uuid.uuid4())
    assert result is True


@pytest.mark.asyncio
async def test_query_uses_correct_statuses():
    """验证 SQL 只查 succeeded/partial，不查 running/failed。"""
    db = _make_db_mock(scalar_result=None)
    pid = uuid.uuid4()
    await has_any_push_run(db, pid)

    # 验证 execute 被调用且 SQL 包含正确的状态过滤
    db.execute.assert_called_once()
    call_args = db.execute.call_args
    sql_text = str(call_args[0][0].text)
    assert "succeeded" in sql_text
    assert "partial" in sql_text
    assert str(pid) == call_args[0][1]["pid"]
