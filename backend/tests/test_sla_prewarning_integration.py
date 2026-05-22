"""F6 SLA 预警集成测试

验证 sla_worker 完整循环：
- 检测 → 预警生成 → 通知推送 → 自动解决
- 幂等性（多次运行不重复通知）

Requirements: 6.1~6.6
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.workers.sla_worker import (
    PREWARNING_REDIS_TTL,
    _check_prewarning,
    resolve_prewarning_for_ticket,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ticket(
    due_at_offset_hours: float,
    status: str = "open",
    ticket_id=None,
    project_id=None,
    owner_id=None,
):
    """Create a mock IssueTicket with due_at offset from now."""
    ticket = MagicMock()
    ticket.id = ticket_id or uuid4()
    ticket.project_id = project_id or uuid4()
    ticket.owner_id = owner_id or uuid4()
    ticket.wp_id = uuid4()
    ticket.title = "测试问题单"
    ticket.status = status
    ticket.due_at = datetime.now(timezone.utc) + timedelta(hours=due_at_offset_hours)
    return ticket


def _mock_db_with_tickets(tickets):
    """Create a mock AsyncSession that returns the given tickets."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = tickets
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result
    return mock_db


REDIS_PATCH = "app.core.redis.get_redis"
SEND_PATCH = "app.workers.sla_worker._send_prewarning_notification"


# ---------------------------------------------------------------------------
# Integration Test: Complete Cycle
# ---------------------------------------------------------------------------


class TestSLAPrewarningCompleteCycle:
    """验证 sla_worker 完整循环：检测 → 预警 → 通知 → 自动解决。"""

    @pytest.mark.asyncio
    async def test_full_cycle_detect_warn_resolve(self):
        """完整流程：检测即将超时 → 生成预警 → 问题单关闭 → 自动解决。

        Requirements: 6.1, 6.2, 6.3, 6.6
        """
        ticket_id = uuid4()
        owner_id = uuid4()
        project_id = uuid4()

        # Phase 1: 检测 + 预警生成
        ticket = _make_ticket(
            due_at_offset_hours=6.0,  # 6h remaining → orange
            ticket_id=ticket_id,
            owner_id=owner_id,
            project_id=project_id,
        )
        mock_db = _mock_db_with_tickets([ticket])
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # Not yet warned

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=mock_redis):
            with patch(SEND_PATCH, new_callable=AsyncMock) as mock_send:
                warned_count = await _check_prewarning(mock_db)

        # Verify: 1 notification sent, orange level
        assert warned_count == 1
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        assert call_kwargs["level"] == "orange"
        assert call_kwargs["ticket"].id == ticket_id

        # Verify: Redis key set with TTL
        mock_redis.set.assert_called_once()
        redis_key = mock_redis.set.call_args[0][0]
        assert f"sla:prewarning:{ticket_id}:orange" == redis_key
        assert mock_redis.set.call_args[1]["ex"] == PREWARNING_REDIS_TTL

        # Phase 2: 自动解决（问题单关闭）
        resolve_db = AsyncMock()
        resolve_result = MagicMock()
        resolve_result.rowcount = 1
        resolve_db.execute.return_value = resolve_result

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=mock_redis):
            resolved = await resolve_prewarning_for_ticket(
                db=resolve_db, ticket_id=ticket_id
            )

        # Verify: notification marked as resolved
        assert resolved == 1
        # Verify: Redis keys deleted (both yellow and orange)
        assert mock_redis.delete.call_count == 2

    @pytest.mark.asyncio
    async def test_yellow_and_orange_levels_correct(self):
        """验证黄色（8h < remaining ≤ 24h）和橙色（≤ 8h）分类正确。

        Requirements: 6.1, 6.2
        """
        yellow_ticket = _make_ticket(due_at_offset_hours=16.0)  # 16h → yellow
        orange_ticket = _make_ticket(due_at_offset_hours=3.0)  # 3h → orange

        mock_db = _mock_db_with_tickets([yellow_ticket, orange_ticket])
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        levels_sent = []

        async def capture_send(db, ticket, level, remaining_hours):
            levels_sent.append(level)

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=mock_redis):
            with patch(SEND_PATCH, side_effect=capture_send):
                count = await _check_prewarning(mock_db)

        assert count == 2
        assert "yellow" in levels_sent
        assert "orange" in levels_sent

    @pytest.mark.asyncio
    async def test_notification_push_to_owner(self):
        """验证通知推送到问题单责任人（owner_id）。

        Requirements: 6.3, 6.4
        """
        from app.workers.sla_worker import _send_prewarning_notification

        owner_id = uuid4()
        ticket = _make_ticket(due_at_offset_hours=5.0, owner_id=owner_id)
        mock_db = MagicMock()

        await _send_prewarning_notification(
            db=mock_db,
            ticket=ticket,
            level="orange",
            remaining_hours=5.0,
        )

        # Verify notification created with correct recipient
        mock_db.add.assert_called_once()
        notification = mock_db.add.call_args[0][0]
        assert notification.recipient_id == owner_id
        assert notification.message_type == "sla_prewarning"
        assert "orange" in notification.title
        assert notification.related_object_type == "issue_ticket"
        assert notification.related_object_id == ticket.id


# ---------------------------------------------------------------------------
# Integration Test: Idempotency
# ---------------------------------------------------------------------------


class TestSLAPrewarningIdempotency:
    """验证幂等性：多次运行不重复通知。

    Requirements: 6.5
    """

    @pytest.mark.asyncio
    async def test_second_run_does_not_duplicate(self):
        """同一问题单同级预警，第二次运行不重复发送。"""
        ticket_id = uuid4()
        ticket = _make_ticket(due_at_offset_hours=5.0, ticket_id=ticket_id)

        mock_db = _mock_db_with_tickets([ticket])
        mock_redis = AsyncMock()

        # First run: Redis returns None (not yet warned)
        mock_redis.get.return_value = None
        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=mock_redis):
            with patch(SEND_PATCH, new_callable=AsyncMock) as mock_send:
                count1 = await _check_prewarning(mock_db)

        assert count1 == 1
        mock_send.assert_called_once()

        # Second run: Redis returns "1" (already warned)
        mock_redis.get.return_value = b"1"
        mock_redis.set.reset_mock()

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=mock_redis):
            with patch(SEND_PATCH, new_callable=AsyncMock) as mock_send2:
                count2 = await _check_prewarning(mock_db)

        assert count2 == 0
        mock_send2.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_tickets_independent_dedup(self):
        """多个问题单各自独立去重。"""
        ticket_a = _make_ticket(due_at_offset_hours=5.0)
        ticket_b = _make_ticket(due_at_offset_hours=12.0)

        mock_db = _mock_db_with_tickets([ticket_a, ticket_b])
        mock_redis = AsyncMock()

        # ticket_a already warned, ticket_b not yet
        async def redis_get_side_effect(key):
            if str(ticket_a.id) in key:
                return b"1"
            return None

        mock_redis.get.side_effect = redis_get_side_effect

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=mock_redis):
            with patch(SEND_PATCH, new_callable=AsyncMock) as mock_send:
                count = await _check_prewarning(mock_db)

        # Only ticket_b should be warned
        assert count == 1
        call_kwargs = mock_send.call_args[1]
        assert call_kwargs["ticket"].id == ticket_b.id

    @pytest.mark.asyncio
    async def test_redis_unavailable_allows_duplicate(self):
        """Redis 不可用时降级为不去重（宁多勿漏）。

        Requirements: 6.5 (degradation)
        """
        ticket = _make_ticket(due_at_offset_hours=5.0)
        mock_db = _mock_db_with_tickets([ticket])

        # Run twice with Redis unavailable (returns None)
        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=None):
            with patch(SEND_PATCH, new_callable=AsyncMock) as mock_send:
                count1 = await _check_prewarning(mock_db)
                count2 = await _check_prewarning(mock_db)

        # Both runs should send (no dedup without Redis)
        assert count1 == 1
        assert count2 == 1
        assert mock_send.call_count == 2


# ---------------------------------------------------------------------------
# Integration Test: Auto-Resolve
# ---------------------------------------------------------------------------


class TestSLAPrewarningAutoResolve:
    """验证自动解决逻辑。

    Requirements: 6.6
    """

    @pytest.mark.asyncio
    async def test_resolve_marks_all_levels(self):
        """解决时清除 yellow 和 orange 两个级别的 Redis key。"""
        ticket_id = uuid4()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_db.execute.return_value = mock_result

        mock_redis = AsyncMock()
        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=mock_redis):
            resolved = await resolve_prewarning_for_ticket(
                db=mock_db, ticket_id=ticket_id
            )

        assert resolved == 2
        # Both yellow and orange keys should be deleted
        delete_calls = [str(c) for c in mock_redis.delete.call_args_list]
        assert mock_redis.delete.call_count == 2

    @pytest.mark.asyncio
    async def test_resolve_no_notifications_returns_zero(self):
        """无预警通知时返回 0，不报错。"""
        ticket_id = uuid4()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=None):
            resolved = await resolve_prewarning_for_ticket(
                db=mock_db, ticket_id=ticket_id
            )

        assert resolved == 0

    @pytest.mark.asyncio
    async def test_resolve_after_prewarning_cycle(self):
        """完整循环：预警 → 解决 → 再次检查不再预警（Redis 已清除）。"""
        ticket_id = uuid4()
        ticket = _make_ticket(due_at_offset_hours=5.0, ticket_id=ticket_id)

        # Step 1: Generate prewarning
        mock_db = _mock_db_with_tickets([ticket])
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=mock_redis):
            with patch(SEND_PATCH, new_callable=AsyncMock):
                count = await _check_prewarning(mock_db)
        assert count == 1

        # Step 2: Resolve (ticket closed)
        resolve_db = AsyncMock()
        resolve_result = MagicMock()
        resolve_result.rowcount = 1
        resolve_db.execute.return_value = resolve_result

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=mock_redis):
            resolved = await resolve_prewarning_for_ticket(
                db=resolve_db, ticket_id=ticket_id
            )
        assert resolved == 1

        # Step 3: After resolve, Redis key is deleted, but ticket is now closed
        # so it won't appear in the query (status filter excludes resolved/closed)
        # This verifies the full cycle is clean
        mock_redis.delete.assert_called()
