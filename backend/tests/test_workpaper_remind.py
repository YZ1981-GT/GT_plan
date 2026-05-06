"""底稿催办端点单元测试 — Round 2 需求 4

测试覆盖：
1. 正常催办成功（创建 IssueTicket + Notification）
2. 底稿不存在返回 404
3. 底稿未分配编制人返回 400
4. 7 天内催办 3 次后返回 429
5. 消息模板使用"已创建 X 天尚未完成"措辞
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.workpaper_remind_service import (
    MAX_REMIND_COUNT,
    REMIND_WINDOW_DAYS,
    WorkpaperRemindService,
)


@pytest.fixture
def service():
    return WorkpaperRemindService()


@pytest.fixture
def mock_db():
    """模拟 AsyncSession"""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_wp_and_index():
    """模拟 WorkingPaper + WpIndex 查询结果"""
    wp = MagicMock()
    wp.id = uuid.uuid4()
    wp.project_id = uuid.uuid4()
    wp.assigned_to = uuid.uuid4()
    wp.created_at = datetime.utcnow() - timedelta(days=10)
    wp.is_deleted = False

    wp_index = MagicMock()
    wp_index.wp_code = "D-01"
    wp_index.wp_name = "银行存款"
    wp_index.assigned_to = wp.assigned_to
    wp_index.created_at = wp.created_at

    return wp, wp_index


@pytest.mark.asyncio
async def test_remind_success(service, mock_db, mock_wp_and_index):
    """正常催办成功：创建 IssueTicket + Notification"""
    wp, wp_index = mock_wp_and_index
    project_id = wp.project_id
    wp_id = wp.id
    operator_id = uuid.uuid4()

    # Mock DB query
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, idx: [wp, wp_index][idx]
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = mock_row
    mock_db.execute = AsyncMock(return_value=mock_result)

    # Mock Redis (0 previous reminders)
    with patch.object(service, "_get_remind_count", return_value=0), \
         patch.object(service, "_increment_remind_count", return_value=1), \
         patch("app.services.workpaper_remind_service.NotificationService") as MockNotifSvc:

        mock_notif_instance = AsyncMock()
        mock_notif_instance.send_notification = AsyncMock(return_value={
            "id": str(uuid.uuid4()),
            "recipient_id": str(wp.assigned_to),
            "message_type": "workpaper_reminder",
            "title": "底稿催办提醒",
            "content": "test",
        })
        MockNotifSvc.return_value = mock_notif_instance

        result = await service.remind(
            db=mock_db,
            project_id=project_id,
            wp_id=wp_id,
            operator_id=operator_id,
        )

    assert result["ticket_id"] is not None
    assert result["notification_id"] is not None
    assert result["remind_count"] == 1
    assert result["allowed_next"] == "now"
    # Verify IssueTicket was added
    mock_db.add.assert_called_once()


@pytest.mark.asyncio
async def test_remind_workpaper_not_found(service, mock_db):
    """底稿不存在返回 404"""
    from fastapi import HTTPException

    mock_result = MagicMock()
    mock_result.one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(HTTPException) as exc_info:
        await service.remind(
            db=mock_db,
            project_id=uuid.uuid4(),
            wp_id=uuid.uuid4(),
            operator_id=uuid.uuid4(),
        )

    assert exc_info.value.status_code == 404
    assert "WORKPAPER_NOT_FOUND" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_remind_no_assignee(service, mock_db, mock_wp_and_index):
    """底稿未分配编制人返回 400"""
    from fastapi import HTTPException

    wp, wp_index = mock_wp_and_index
    wp.assigned_to = None
    wp_index.assigned_to = None

    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, idx: [wp, wp_index][idx]
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = mock_row
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(HTTPException) as exc_info:
        await service.remind(
            db=mock_db,
            project_id=wp.project_id,
            wp_id=wp.id,
            operator_id=uuid.uuid4(),
        )

    assert exc_info.value.status_code == 400
    assert "尚未分配编制人" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_remind_rate_limit_exceeded(service, mock_db, mock_wp_and_index):
    """7 天内催办 3 次后返回 429"""
    from fastapi import HTTPException

    wp, wp_index = mock_wp_and_index

    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, idx: [wp, wp_index][idx]
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = mock_row
    mock_db.execute = AsyncMock(return_value=mock_result)

    # Mock Redis: already 3 reminders
    with patch.object(service, "_get_remind_count", return_value=3):
        with pytest.raises(HTTPException) as exc_info:
            await service.remind(
                db=mock_db,
                project_id=wp.project_id,
                wp_id=wp.id,
                operator_id=uuid.uuid4(),
            )

    assert exc_info.value.status_code == 429
    assert "已连续催办 3 次" in str(exc_info.value.detail["message"])


@pytest.mark.asyncio
async def test_remind_message_uses_created_days(service, mock_db, mock_wp_and_index):
    """消息模板使用"已创建 X 天尚未完成"措辞，不使用"逾期" """
    wp, wp_index = mock_wp_and_index
    # 设置创建时间为确定的 15 天前（使用 date.today 保持一致）
    created_date = date.today() - timedelta(days=15)
    wp.created_at = datetime(created_date.year, created_date.month, created_date.day, 12, 0, 0)
    wp_index.created_at = wp.created_at

    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, idx: [wp, wp_index][idx]
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = mock_row
    mock_db.execute = AsyncMock(return_value=mock_result)

    captured_ticket = None

    def capture_add(obj):
        nonlocal captured_ticket
        captured_ticket = obj

    mock_db.add = capture_add

    with patch.object(service, "_get_remind_count", return_value=0), \
         patch.object(service, "_increment_remind_count", return_value=1), \
         patch("app.services.workpaper_remind_service.NotificationService") as MockNotifSvc:

        mock_notif_instance = AsyncMock()
        mock_notif_instance.send_notification = AsyncMock(return_value={
            "id": str(uuid.uuid4()),
            "recipient_id": str(wp.assigned_to),
            "message_type": "workpaper_reminder",
            "title": "test",
            "content": "test",
        })
        MockNotifSvc.return_value = mock_notif_instance

        await service.remind(
            db=mock_db,
            project_id=wp.project_id,
            wp_id=wp.id,
            operator_id=uuid.uuid4(),
        )

    # Verify the ticket description uses "已创建 X 天" and NOT "逾期"
    assert captured_ticket is not None
    assert "已创建 15 天尚未完成" in captured_ticket.description
    assert "逾期" not in captured_ticket.description


@pytest.mark.asyncio
async def test_remind_custom_message(service, mock_db, mock_wp_and_index):
    """自定义催办消息"""
    wp, wp_index = mock_wp_and_index
    custom_msg = "请尽快完成此底稿，项目即将结项。"

    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, idx: [wp, wp_index][idx]
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = mock_row
    mock_db.execute = AsyncMock(return_value=mock_result)

    captured_ticket = None

    def capture_add(obj):
        nonlocal captured_ticket
        captured_ticket = obj

    mock_db.add = capture_add

    with patch.object(service, "_get_remind_count", return_value=0), \
         patch.object(service, "_increment_remind_count", return_value=1), \
         patch("app.services.workpaper_remind_service.NotificationService") as MockNotifSvc:

        mock_notif_instance = AsyncMock()
        mock_notif_instance.send_notification = AsyncMock(return_value={
            "id": str(uuid.uuid4()),
            "recipient_id": str(wp.assigned_to),
            "message_type": "workpaper_reminder",
            "title": "test",
            "content": "test",
        })
        MockNotifSvc.return_value = mock_notif_instance

        await service.remind(
            db=mock_db,
            project_id=wp.project_id,
            wp_id=wp.id,
            operator_id=uuid.uuid4(),
            message=custom_msg,
        )

    assert captured_ticket is not None
    assert captured_ticket.description == custom_msg


@pytest.mark.asyncio
async def test_remind_allowed_next_none_when_maxed(service):
    """达到上限时 allowed_next 返回 None"""
    result = service._compute_allowed_next(MAX_REMIND_COUNT)
    assert result is None


@pytest.mark.asyncio
async def test_remind_allowed_next_now_when_under_limit(service):
    """未达上限时 allowed_next 返回 'now'"""
    result = service._compute_allowed_next(1)
    assert result == "now"
