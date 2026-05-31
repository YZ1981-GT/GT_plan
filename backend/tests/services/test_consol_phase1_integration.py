"""consol-phase1-arch-lock 集成测试（任务 8）.

- 8.2 Q5 锁定全端点 423：check_consol_lock 对锁定项目（直接 project_id + 反查 wp_id/note_id）均抛 423
- 8.3 抵销审批 → ELIMINATION_APPROVED 事件 → worksheet + trial 重算 handler 调用链
- EH4 反查失败放行不误拦

Validates: Requirements 2.3, 3.3, 3.4, 3.5
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.deps import check_consol_lock


# ---------------------------------------------------------------------------
# 8.2 Q5 锁定全端点 423（check_consol_lock 行为参数化）
# ---------------------------------------------------------------------------

def _fake_db_returning(scalar_value):
    """构造 fake AsyncSession，execute().scalar_one_or_none() 返回指定值。"""
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_value
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_q5_locked_project_direct_project_id_raises_423():
    """锁定项目 + 直接传 project_id → 423。"""
    db = _fake_db_returning(True)  # consol_lock = True
    with pytest.raises(HTTPException) as exc:
        await check_consol_lock(project_id=uuid.uuid4(), db=db)
    assert exc.value.status_code == 423
    assert "合并锁定" in exc.value.detail


@pytest.mark.asyncio
async def test_q5_unlocked_project_passes():
    """未锁定项目 → 放行（不抛）。"""
    db = _fake_db_returning(False)
    await check_consol_lock(project_id=uuid.uuid4(), db=db)  # 不抛即通过


@pytest.mark.asyncio
async def test_q5_locked_via_wp_id_reverse_lookup_raises_423():
    """端点仅含 wp_id：反查 project_id → 锁定 → 423（5.2）。"""
    parent_pid = uuid.uuid4()
    # 第一次 execute（反查 WorkingPaper.project_id）返回 pid；第二次（Project.consol_lock）返回 True
    db = MagicMock()
    r1 = MagicMock(); r1.scalar_one_or_none.return_value = parent_pid
    r2 = MagicMock(); r2.scalar_one_or_none.return_value = True
    db.execute = AsyncMock(side_effect=[r1, r2])

    with pytest.raises(HTTPException) as exc:
        await check_consol_lock(wp_id=uuid.uuid4(), db=db)
    assert exc.value.status_code == 423


@pytest.mark.asyncio
async def test_q5_locked_via_note_id_reverse_lookup_raises_423():
    """端点仅含 note_id：反查 project_id → 锁定 → 423（5.2）。"""
    parent_pid = uuid.uuid4()
    db = MagicMock()
    r1 = MagicMock(); r1.scalar_one_or_none.return_value = parent_pid
    r2 = MagicMock(); r2.scalar_one_or_none.return_value = True
    db.execute = AsyncMock(side_effect=[r1, r2])

    with pytest.raises(HTTPException) as exc:
        await check_consol_lock(note_id=uuid.uuid4(), db=db)
    assert exc.value.status_code == 423


@pytest.mark.asyncio
async def test_eh4_reverse_lookup_miss_passes_not_raise():
    """EH4：wp_id 反查不到所属项目 → 放行不误拦（不抛 423）。"""
    db = _fake_db_returning(None)  # 反查 project_id 返回 None
    await check_consol_lock(wp_id=uuid.uuid4(), db=db)  # 不抛即通过


@pytest.mark.asyncio
async def test_eh4_no_identifiers_passes():
    """既无 project_id 也无资源 id → 放行（不误拦）。"""
    db = _fake_db_returning(None)
    await check_consol_lock(db=db)


# ---------------------------------------------------------------------------
# 8.3 抵销审批 → 事件 → worksheet + trial 重算 handler 调用链
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_q4_elimination_approved_triggers_both_recalcs():
    """ELIMINATION_APPROVED handler → recalc_full(worksheet) + recalculate_trial 均被调用。"""
    from app.services import consol_elimination_recalc_handler as h

    pid = uuid.uuid4()
    event = MagicMock(project_id=pid, year=2025)

    fake_db = MagicMock()
    fake_db.commit = AsyncMock()
    fake_db.rollback = AsyncMock()

    class _FakeSessionCtx:
        async def __aenter__(self):
            return fake_db
        async def __aexit__(self, *a):
            return False

    with patch("app.core.database.async_session", return_value=_FakeSessionCtx()), \
         patch("app.services.consol_worksheet_engine.recalc_full", new=AsyncMock()) as m_ws, \
         patch("app.services.consol_trial_service.recalculate_trial", new=AsyncMock()) as m_tr:
        await h.handle_elimination_approved(event)

    m_ws.assert_awaited_once()
    m_tr.assert_awaited_once()
    fake_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_eh3_recalc_failure_does_not_raise():
    """EH3：worksheet 重算抛异常 → handler 记 error 不抛（审批不被阻断）。"""
    from app.services import consol_elimination_recalc_handler as h

    event = MagicMock(project_id=uuid.uuid4(), year=2025)
    fake_db = MagicMock()
    fake_db.commit = AsyncMock()
    fake_db.rollback = AsyncMock()

    class _FakeSessionCtx:
        async def __aenter__(self):
            return fake_db
        async def __aexit__(self, *a):
            return False

    with patch("app.core.database.async_session", return_value=_FakeSessionCtx()), \
         patch("app.services.consol_worksheet_engine.recalc_full",
               new=AsyncMock(side_effect=RuntimeError("boom"))), \
         patch("app.services.consol_trial_service.recalculate_trial", new=AsyncMock()):
        # 不应抛异常
        await h.handle_elimination_approved(event)


@pytest.mark.asyncio
async def test_handler_missing_fields_noop():
    """事件缺 project_id/year → handler 静默返回，不调重算。"""
    from app.services import consol_elimination_recalc_handler as h

    event = MagicMock(project_id=None, year=None)
    with patch("app.services.consol_worksheet_engine.recalc_full", new=AsyncMock()) as m_ws:
        await h.handle_elimination_approved(event)
    m_ws.assert_not_awaited()
