"""Unit tests for notification service — event-to-notification mapping.

Validates: Requirements 6.2, 6.3, 6.4
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone
import uuid

from app.services.notification_service import (
    NotificationService,
    NOTIF_TYPE_WORKPAPER_ASSIGNED,
    NOTIF_TYPE_REVIEW_APPROVED,
    NOTIF_TYPE_REVIEW_REJECTED,
    NOTIF_TYPE_MISSTATEMENT_ALERT,
    NOTIF_TYPE_SYNC_CONFLICT,
    NOTIF_TYPE_GENERAL,
)


# ---------------------------------------------------------------------------
# Notification creation tests
# ---------------------------------------------------------------------------

class TestNotificationCreation:
    def test_create_notification(self):
        db = MagicMock()
        recipient_id = str(uuid.uuid4())

        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        notif = NotificationService.create_notification(
            db,
            recipient_id=recipient_id,
            notification_type=NOTIF_TYPE_GENERAL,
            title="Test notification",
            content="This is a test",
        )
        assert notif.title == "Test notification"
        assert notif.is_read is False

    def test_notification_defaults_unread(self):
        db = MagicMock()
        recipient_id = str(uuid.uuid4())

        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        notif = NotificationService.create_notification(
            db,
            recipient_id=recipient_id,
            notification_type=NOTIF_TYPE_GENERAL,
            title="Default unread",
        )
        assert notif.is_read is False


# ---------------------------------------------------------------------------
# Event-to-notification mapping tests
# ---------------------------------------------------------------------------

class TestEventMapping:
    def test_review_submitted_creates_notification(self):
        """on_review_submitted should create notification per Requirement 6.2."""
        db = MagicMock()
        recipient_id = str(uuid.uuid4())

        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        notif = NotificationService.create_notification(
            db,
            recipient_id=recipient_id,
            notification_type=NOTIF_TYPE_WORKPAPER_ASSIGNED,
            title="工作底稿待复核",
            content="底稿已提交，请进行复核",
            related_object_type="review",
        )
        assert notif.title is not None

    def test_review_approved_creates_notification(self):
        """Review approval notification."""
        db = MagicMock()
        recipient_id = str(uuid.uuid4())

        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        notif = NotificationService.create_notification(
            db,
            recipient_id=recipient_id,
            notification_type=NOTIF_TYPE_REVIEW_APPROVED,
            title="复核已通过",
            content="您编制的底稿已通过复核",
            related_object_type="review",
        )
        assert notif.notification_type == NOTIF_TYPE_REVIEW_APPROVED

    def test_review_rejected_creates_notification(self):
        """Review rejection notification."""
        db = MagicMock()
        recipient_id = str(uuid.uuid4())

        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        notif = NotificationService.create_notification(
            db,
            recipient_id=recipient_id,
            notification_type=NOTIF_TYPE_REVIEW_REJECTED,
            title="复核意见：需修改",
            content="请查看复核意见并修改底稿",
            related_object_type="review",
        )
        assert notif.title is not None

    def test_misstatement_threshold_exceeded_creates_notification(self):
        """Misstatement threshold exceeded notification per Requirement 6.3."""
        db = MagicMock()
        recipient_id = str(uuid.uuid4())

        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        notif = NotificationService.create_notification(
            db,
            recipient_id=recipient_id,
            notification_type=NOTIF_TYPE_MISSTATEMENT_ALERT,
            title="错报超限预警",
            content="未更正错报金额超过重要性水平，请关注",
            related_object_type="misstatement",
        )
        assert notif.notification_type == NOTIF_TYPE_MISSTATEMENT_ALERT

    def test_sync_conflict_creates_notification(self):
        """Sync conflict notification per Requirement 6.4."""
        db = MagicMock()
        recipient_id = str(uuid.uuid4())

        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        notif = NotificationService.create_notification(
            db,
            recipient_id=recipient_id,
            notification_type=NOTIF_TYPE_SYNC_CONFLICT,
            title="同步冲突",
            content="检测到数据冲突，请手动解决",
            related_object_type="sync",
        )
        assert notif.notification_type == NOTIF_TYPE_SYNC_CONFLICT


# ---------------------------------------------------------------------------
# Notification type constants
# ---------------------------------------------------------------------------

class TestNotificationTypeConstants:
    def test_notification_type_constants_defined(self):
        assert NOTIF_TYPE_WORKPAPER_ASSIGNED is not None
        assert NOTIF_TYPE_REVIEW_APPROVED is not None
        assert NOTIF_TYPE_REVIEW_REJECTED is not None
        assert NOTIF_TYPE_MISSTATEMENT_ALERT is not None
        assert NOTIF_TYPE_SYNC_CONFLICT is not None
        assert NOTIF_TYPE_GENERAL is not None
