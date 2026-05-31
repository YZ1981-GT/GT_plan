"""P1 — consol_trial_stale_handler 单元测试.

验证子公司 TB 变更 → 母公司合并 trial 标 stale 的事件链：
- mark_consol_trial_stale 正确 UPDATE
- handle_child_tb_updated 缺字段/无 parent 时静默不崩
- register_consol_trial_stale_handler 订阅 TRIAL_BALANCE_UPDATED
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.consol_trial_stale_handler import (
    handle_child_tb_updated,
    mark_consol_trial_stale,
    register_consol_trial_stale_handler,
)


class TestMarkConsolTrialStale:
    @pytest.mark.asyncio
    async def test_marks_rows_and_returns_count(self):
        """UPDATE consol_trial SET is_stale=true 返回 rowcount。"""
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        count = await mark_consol_trial_stale(uuid.uuid4(), 2025, mock_db)

        assert count == 3
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_zero_on_error(self):
        """DB 异常时返回 0 不抛（观测机制不阻断）。"""
        mock_db = AsyncMock()
        mock_db.execute.side_effect = RuntimeError("db error")

        count = await mark_consol_trial_stale(uuid.uuid4(), 2025, mock_db)

        assert count == 0


class TestHandleChildTbUpdated:
    @pytest.mark.asyncio
    async def test_missing_project_id_returns_silently(self):
        """缺 project_id 静默返回。"""
        event = MagicMock(project_id=None, year=2025)
        await handle_child_tb_updated(event)  # 不抛

    @pytest.mark.asyncio
    async def test_missing_year_returns_silently(self):
        """缺 year 静默返回。"""
        event = MagicMock(project_id=uuid.uuid4(), year=None)
        await handle_child_tb_updated(event)  # 不抛

    @pytest.mark.asyncio
    async def test_no_parent_no_side_effect(self):
        """无 parent 合并项目时不调用 mark（_find_consol_parents 返空）。"""
        child_id = uuid.uuid4()
        event = MagicMock(project_id=child_id, year=2025)

        mock_db = AsyncMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.core.database.async_session",
            return_value=mock_ctx,
        ), patch(
            "app.services.consol_note_stale_handler._find_consol_parents",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.services.consol_trial_stale_handler.mark_consol_trial_stale",
            new_callable=AsyncMock,
        ) as mock_mark:
            await handle_child_tb_updated(event)
            mock_mark.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_with_parents_marks_each(self):
        """有 parent 时对每个 parent 调 mark_consol_trial_stale。"""
        child_id = uuid.uuid4()
        parent1 = uuid.uuid4()
        parent2 = uuid.uuid4()
        event = MagicMock(project_id=child_id, year=2025)

        mock_db = AsyncMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.core.database.async_session",
            return_value=mock_ctx,
        ), patch(
            "app.services.consol_note_stale_handler._find_consol_parents",
            new_callable=AsyncMock,
            return_value=[parent1, parent2],
        ), patch(
            "app.services.consol_trial_stale_handler.mark_consol_trial_stale",
            new_callable=AsyncMock,
            return_value=2,
        ) as mock_mark:
            await handle_child_tb_updated(event)
            assert mock_mark.await_count == 2
            mock_db.commit.assert_awaited_once()


class TestRegister:
    def test_subscribes_to_trial_balance_updated(self):
        """注册到 EventBus 的 TRIAL_BALANCE_UPDATED。"""
        from app.models.audit_platform_schemas import EventType

        mock_bus = MagicMock()
        register_consol_trial_stale_handler(mock_bus)

        mock_bus.subscribe.assert_called_once_with(
            EventType.TRIAL_BALANCE_UPDATED, handle_child_tb_updated
        )
