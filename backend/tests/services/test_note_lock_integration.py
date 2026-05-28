"""Sprint A.6.1 / CI-13 — 锁集成 helper 单测.

CI-13: 锁释放必触发（context manager __aexit__ 保证）

覆盖：
1. 正常退出 → release 被调用
2. 异常退出 → release 仍被调用（CI-13 铁律）
3. acquire 失败 → 抛 HTTPException 409
4. 批量锁：全部成功 → yield → 全部释放
5. 批量锁：中途失败 → 已获取的释放 + 抛 409
6. release 失败不抛（只 warning）
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.note_lock_integration import note_batch_lock, note_section_lock


def _mock_lock_service(acquire_ok=True, active_locks=None):
    svc = MagicMock()
    svc.acquire_lock = AsyncMock(return_value=acquire_ok)
    svc.release_lock = AsyncMock(return_value=True)
    svc.get_active_locks = AsyncMock(return_value=active_locks or [])
    return svc


@pytest.mark.asyncio
async def test_normal_exit_releases_lock():
    """CI-13: 正常退出 → release 被调用."""
    svc = _mock_lock_service(acquire_ok=True)
    db = MagicMock()

    with patch("app.services.note_section_lock_service.NoteSectionLockService", return_value=svc):
        async with note_section_lock(db, uuid4(), 2025, "sec_1", uuid4()):
            pass  # 正常退出

    svc.release_lock.assert_awaited_once()


@pytest.mark.asyncio
async def test_exception_exit_still_releases():
    """CI-13: 异常退出 → release 仍被调用."""
    svc = _mock_lock_service(acquire_ok=True)
    db = MagicMock()

    with patch("app.services.note_section_lock_service.NoteSectionLockService", return_value=svc):
        with pytest.raises(ValueError):
            async with note_section_lock(db, uuid4(), 2025, "sec_1", uuid4()):
                raise ValueError("模拟异常")

    svc.release_lock.assert_awaited_once()


@pytest.mark.asyncio
async def test_acquire_fail_raises_409():
    """acquire 失败 → HTTPException 409."""
    svc = _mock_lock_service(acquire_ok=False, active_locks=[
        {"section_id": "sec_1", "user_name": "张三"},
    ])
    db = MagicMock()

    with patch("app.services.note_section_lock_service.NoteSectionLockService", return_value=svc):
        with pytest.raises(HTTPException) as exc_info:
            async with note_section_lock(db, uuid4(), 2025, "sec_1", uuid4()):
                pass

    assert exc_info.value.status_code == 409
    assert "张三" in exc_info.value.detail


@pytest.mark.asyncio
async def test_batch_lock_all_success_then_release():
    """批量锁：全部成功 → yield → 全部释放."""
    svc = _mock_lock_service(acquire_ok=True)
    db = MagicMock()

    with patch("app.services.note_section_lock_service.NoteSectionLockService", return_value=svc):
        async with note_batch_lock(db, uuid4(), 2025, ["s1", "s2", "s3"], uuid4()):
            pass

    assert svc.acquire_lock.await_count == 3
    assert svc.release_lock.await_count == 3


@pytest.mark.asyncio
async def test_batch_lock_partial_fail_releases_acquired():
    """批量锁：第 2 个失败 → 释放第 1 个 + 抛 409."""
    svc = MagicMock()
    svc.acquire_lock = AsyncMock(side_effect=[True, False])
    svc.release_lock = AsyncMock(return_value=True)
    db = MagicMock()

    with patch("app.services.note_section_lock_service.NoteSectionLockService", return_value=svc):
        with pytest.raises(HTTPException) as exc_info:
            async with note_batch_lock(db, uuid4(), 2025, ["s1", "s2"], uuid4()):
                pass

    assert exc_info.value.status_code == 409
    # s1 已获取 → 释放
    svc.release_lock.assert_awaited_once()


@pytest.mark.asyncio
async def test_release_failure_does_not_propagate():
    """release 失败不抛（只 warning，CI-13 尽力释放）."""
    svc = _mock_lock_service(acquire_ok=True)
    svc.release_lock = AsyncMock(side_effect=RuntimeError("DB down"))
    db = MagicMock()

    with patch("app.services.note_section_lock_service.NoteSectionLockService", return_value=svc):
        # 不应抛异常
        async with note_section_lock(db, uuid4(), 2025, "sec_1", uuid4()):
            pass

    svc.release_lock.assert_awaited_once()
