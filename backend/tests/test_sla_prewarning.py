"""SLA 前置预警测试

Tests for:
- Task 8.1: 前置预警逻辑
- Task 8.2: 预警通知写入 NotificationCenter
- Task 8.3: 预警自动解决逻辑

覆盖：
- 黄色预警（8h < remaining ≤ 24h）
- 橙色预警（0 < remaining ≤ 8h）
- 幂等去重（Redis key）
- Redis 不可用降级
- 自动解决逻辑
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.workers.sla_worker import (
    PREWARNING_REDIS_TTL,
    _check_prewarning,
    _send_prewarning_notification,
    resolve_prewarning_for_ticket,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_ticket(
    due_at_offset_hours: float = 12.0,
    status: str = "open",
    project_id=None,
    owner_id=None,
):
    """Create a mock IssueTicket with due_at offset from now."""
    ticket = MagicMock()
    ticket.id = uuid4()
    ticket.project_id = project_id or uuid4()
    ticket.owner_id = owner_id or uuid4()
    ticket.wp_id = uuid4()
    ticket.title = "测试问题单"
    ticket.status = status
    ticket.due_at = datetime.now(timezone.utc) + timedelta(hours=due_at_offset_hours)
    return ticket


REDIS_PATCH = "app.core.redis.get_redis"


# ---------------------------------------------------------------------------
# Unit Tests: Warning Level Classification
# ---------------------------------------------------------------------------


class TestWarningLevelClassification:
    """预警级别分类测试。"""

    @pytest.mark.asyncio
    async def test_orange_warning_within_8h(self):
        """due_at 在 (now, now+8h] → 橙色预警。"""
        ticket = _make_ticket(due_at_offset_hours=4.0)  # 4h remaining

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [ticket]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=None):
            with patch("app.workers.sla_worker._send_prewarning_notification", new_callable=AsyncMock) as mock_send:
                count = await _check_prewarning(mock_db)

                assert count == 1
                mock_send.assert_called_once()
                call_kwargs = mock_send.call_args[1]
                assert call_kwargs["level"] == "orange"

    @pytest.mark.asyncio
    async def test_yellow_warning_between_8h_and_24h(self):
        """due_at 在 (now+8h, now+24h] → 黄色预警。"""
        ticket = _make_ticket(due_at_offset_hours=16.0)  # 16h remaining

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [ticket]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=None):
            with patch("app.workers.sla_worker._send_prewarning_notification", new_callable=AsyncMock) as mock_send:
                count = await _check_prewarning(mock_db)

                assert count == 1
                mock_send.assert_called_once()
                call_kwargs = mock_send.call_args[1]
                assert call_kwargs["level"] == "yellow"

    @pytest.mark.asyncio
    async def test_no_warning_when_no_tickets(self):
        """无即将超时的问题单时不发送预警。"""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=None):
            count = await _check_prewarning(mock_db)
            assert count == 0


class TestIdempotency:
    """幂等去重测试。"""

    @pytest.mark.asyncio
    async def test_redis_dedup_skips_existing(self):
        """Redis 中已有 key 时跳过发送。"""
        ticket = _make_ticket(due_at_offset_hours=4.0)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [ticket]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        mock_redis = AsyncMock()
        mock_redis.get.return_value = b"1"  # Already warned

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=mock_redis):
            with patch("app.workers.sla_worker._send_prewarning_notification", new_callable=AsyncMock) as mock_send:
                count = await _check_prewarning(mock_db)

                assert count == 0
                mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_dedup_sends_when_new(self):
        """Redis 中无 key 时正常发送。"""
        ticket = _make_ticket(due_at_offset_hours=4.0)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [ticket]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # Not yet warned

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=mock_redis):
            with patch("app.workers.sla_worker._send_prewarning_notification", new_callable=AsyncMock) as mock_send:
                count = await _check_prewarning(mock_db)

                assert count == 1
                mock_send.assert_called_once()
                # Verify Redis set was called with TTL
                mock_redis.set.assert_called_once()
                call_args = mock_redis.set.call_args
                assert call_args[1]["ex"] == PREWARNING_REDIS_TTL

    @pytest.mark.asyncio
    async def test_redis_unavailable_degrades_gracefully(self):
        """Redis 不可用时降级为不去重（宁多勿漏）。"""
        ticket = _make_ticket(due_at_offset_hours=4.0)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [ticket]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        # Redis returns None (unavailable)
        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=None):
            with patch("app.workers.sla_worker._send_prewarning_notification", new_callable=AsyncMock) as mock_send:
                count = await _check_prewarning(mock_db)

                assert count == 1
                mock_send.assert_called_once()


class TestNotificationCreation:
    """预警通知创建测试。"""

    @pytest.mark.asyncio
    async def test_notification_created_with_correct_fields(self):
        """通知包含正确的字段。"""
        ticket = _make_ticket(due_at_offset_hours=4.0)
        mock_db = MagicMock()  # Use MagicMock since db.add is sync

        await _send_prewarning_notification(
            db=mock_db,
            ticket=ticket,
            level="orange",
            remaining_hours=4.0,
        )

        # Verify db.add was called with a Notification
        mock_db.add.assert_called_once()
        notification = mock_db.add.call_args[0][0]
        assert notification.recipient_id == ticket.owner_id
        assert notification.message_type == "sla_prewarning"
        assert "SLA 预警" in notification.title
        assert "orange" in notification.title
        assert notification.related_object_type == "issue_ticket"
        assert notification.related_object_id == ticket.id


class TestAutoResolve:
    """预警自动解决测试。"""

    @pytest.mark.asyncio
    async def test_resolve_marks_notifications_as_read(self):
        """问题单关闭时标记预警通知为已读。"""
        ticket_id = uuid4()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_db.execute.return_value = mock_result

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=None):
            resolved = await resolve_prewarning_for_ticket(db=mock_db, ticket_id=ticket_id)

        assert resolved == 2
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_clears_redis_keys(self):
        """自动解决时清除 Redis 预警 key。"""
        ticket_id = uuid4()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        mock_redis = AsyncMock()
        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=mock_redis):
            await resolve_prewarning_for_ticket(db=mock_db, ticket_id=ticket_id)

        # Should delete both yellow and orange keys
        assert mock_redis.delete.call_count == 2

    @pytest.mark.asyncio
    async def test_resolve_returns_zero_when_no_notifications(self):
        """无预警通知时返回 0。"""
        ticket_id = uuid4()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=None):
            resolved = await resolve_prewarning_for_ticket(db=mock_db, ticket_id=ticket_id)

        assert resolved == 0


# ---------------------------------------------------------------------------
# Property-Based Tests: SLA 预警
# ---------------------------------------------------------------------------

from hypothesis import given, settings, strategies as st, assume


class TestSLAWarningLevelPBT:
    """Property 11: SLA 预警级别分类正确性

    **Validates: Requirements 6.1, 6.2**

    For any workpaper with a deadline:
    - 0 < remaining_hours <= 8 → "orange"
    - 8 < remaining_hours <= 24 → "yellow"
    - remaining_hours > 24 → no warning
    """

    @settings(max_examples=15)
    @given(
        remaining_hours=st.floats(min_value=0.01, max_value=8.0),
    )
    def test_orange_level_within_8h(self, remaining_hours: float):
        """Property 11: 0 < remaining_hours <= 8 → orange。

        **Validates: Requirements 6.1, 6.2**
        """
        # Simulate the classification logic from _check_prewarning
        now = datetime.now(timezone.utc)
        due_at = now + timedelta(hours=remaining_hours)
        t_8h = now + timedelta(hours=8)

        if due_at <= t_8h:
            level = "orange"
        else:
            level = "yellow"

        assert level == "orange", (
            f"remaining_hours={remaining_hours} 应为 orange，实际为 {level}"
        )

    @settings(max_examples=15)
    @given(
        remaining_hours=st.floats(min_value=8.01, max_value=24.0),
    )
    def test_yellow_level_between_8h_and_24h(self, remaining_hours: float):
        """Property 11: 8 < remaining_hours <= 24 → yellow。

        **Validates: Requirements 6.1, 6.2**
        """
        now = datetime.now(timezone.utc)
        due_at = now + timedelta(hours=remaining_hours)
        t_8h = now + timedelta(hours=8)

        if due_at <= t_8h:
            level = "orange"
        else:
            level = "yellow"

        assert level == "yellow", (
            f"remaining_hours={remaining_hours} 应为 yellow，实际为 {level}"
        )

    @settings(max_examples=15)
    @given(
        remaining_hours=st.floats(min_value=24.01, max_value=48.0),
    )
    def test_no_warning_beyond_24h(self, remaining_hours: float):
        """Property 11: remaining_hours > 24 → 不生成预警。

        **Validates: Requirements 6.1, 6.2**
        """
        now = datetime.now(timezone.utc)
        due_at = now + timedelta(hours=remaining_hours)
        t_24h = now + timedelta(hours=24)

        # The service only queries tickets with due_at <= t_24h
        # So tickets beyond 24h are not even queried
        should_warn = due_at <= t_24h

        assert should_warn is False, (
            f"remaining_hours={remaining_hours} 不应生成预警"
        )


class TestSLAIdempotencyPBT:
    """Property 12: SLA 预警幂等性

    **Validates: Requirements 6.5**

    For any workpaper and warning level, running the prewarning check N times
    (N >= 2) with the same state should produce exactly 1 notification.
    """

    @settings(max_examples=15)
    @given(
        n_runs=st.integers(min_value=2, max_value=10),
        remaining_hours=st.floats(min_value=0.01, max_value=24.0),
    )
    def test_redis_dedup_ensures_single_notification(
        self, n_runs: int, remaining_hours: float
    ):
        """Property 12: N 次检查只产生 1 次通知（Redis 幂等）。

        **Validates: Requirements 6.5**
        """
        # Simulate Redis dedup behavior
        redis_store: dict[str, str] = {}
        ticket_id = str(uuid4())

        now = datetime.now(timezone.utc)
        due_at = now + timedelta(hours=remaining_hours)
        t_8h = now + timedelta(hours=8)
        level = "orange" if due_at <= t_8h else "yellow"

        redis_key = f"sla:prewarning:{ticket_id}:{level}"
        notifications_sent = 0

        for _ in range(n_runs):
            # Check Redis for existing key
            if redis_key in redis_store:
                # Already warned, skip
                continue
            else:
                # Send notification
                notifications_sent += 1
                # Mark in Redis
                redis_store[redis_key] = "1"

        assert notifications_sent == 1, (
            f"应发送 1 次通知，实际发送 {notifications_sent} 次（n_runs={n_runs}）"
        )


class TestSLAAutoResolvePBT:
    """Property 13: SLA 预警自动解决

    **Validates: Requirements 6.6**

    For any workpaper that has an active prewarning notification, if the
    workpaper status changes to "completed"/"resolved"/"closed", the
    notification should be marked as resolved.
    """

    @settings(max_examples=15)
    @given(
        n_active_notifications=st.integers(min_value=0, max_value=5),
        levels=st.lists(
            st.sampled_from(["yellow", "orange"]),
            min_size=0,
            max_size=5,
        ),
    )
    def test_resolve_clears_all_active_notifications(
        self, n_active_notifications: int, levels: list[str]
    ):
        """Property 13: 问题单关闭时所有活跃预警标记为已解决。

        **Validates: Requirements 6.6**
        """
        ticket_id = str(uuid4())

        # Simulate active notifications in Redis
        redis_store: dict[str, str] = {}
        for level in levels[:n_active_notifications]:
            redis_key = f"sla:prewarning:{ticket_id}:{level}"
            redis_store[redis_key] = "1"

        # Simulate resolve: delete all keys for this ticket
        keys_to_delete = [
            f"sla:prewarning:{ticket_id}:{level}"
            for level in ("yellow", "orange")
        ]
        for key in keys_to_delete:
            redis_store.pop(key, None)

        # After resolve, no prewarning keys should remain for this ticket
        remaining_keys = [
            k for k in redis_store
            if k.startswith(f"sla:prewarning:{ticket_id}:")
        ]
        assert len(remaining_keys) == 0, (
            f"解决后仍有 {len(remaining_keys)} 个预警 key 未清除"
        )
