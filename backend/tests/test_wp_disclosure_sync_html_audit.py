"""审计日志写入验证 — US-3 Task 5.6

验证 C 类底稿 → 附注同步时审计日志正确写入。

**Validates: Requirements US-3 验收标准 5**
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from app.services.wp_disclosure_sync_service import WpDisclosureSyncService


# ─── Fake objects ────────────────────────────────────────────────────────────


class FakeNote:
    def __init__(self, note_section="五-1-1 应收账款"):
        self.id = uuid.uuid4()
        self.project_id = uuid.uuid4()
        self.note_section = note_section
        self.table_data = {}
        self.is_stale = True
        self.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.last_sync_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
        self.last_sync_source = None
        self.last_sync_wp_id = None
        self.last_sync_user_id = None
        self.updated_by = None
        self.is_deleted = False


class FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()


class FakeDB:
    def __init__(self):
        self.added = []
        self.committed = False

    async def execute(self, stmt):
        return MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass


# ─── Tests ───────────────────────────────────────────────────────────────────


class TestAuditLogWriteVerification:
    """验证同步操作写入审计日志"""

    @pytest.mark.asyncio
    async def test_sync_update_writes_audit_log(self):
        """同步更新现有附注时写入审计日志。

        **Validates: Requirements US-3 验收标准 5**
        """
        wp_id = uuid.uuid4()
        project_id = uuid.uuid4()
        section_id = "五-1-1 应收账款"

        existing_note = FakeNote(note_section=section_id)
        fake_db = FakeDB()
        user = FakeUser()
        service = WpDisclosureSyncService()

        mapping = {"section_id": section_id, "last_sync_at": existing_note.last_sync_at}
        audit_log_mock = AsyncMock()

        with patch.object(service, '_get_section_mapping', new=AsyncMock(return_value=mapping)), \
             patch.object(service, '_get_note', new=AsyncMock(return_value=existing_note)), \
             patch.object(service, '_write_audit_log', audit_log_mock), \
             patch.object(service, '_broadcast_synced', MagicMock()):
            result = await service.sync_from_html(
                fake_db, wp_id=wp_id, sheet_name="应收账款附注C",
                sub_table_data={"st1": [{"v": 1}]},
                project_id=project_id, user=user, force=True,
            )

        assert result["success"] is True
        audit_log_mock.assert_awaited_once()
        call_args = audit_log_mock.await_args[0]
        assert call_args[1] == "disclosure_sync_update"
        assert call_args[2] == wp_id
        assert call_args[3] == section_id
        assert call_args[4] is user

    @pytest.mark.asyncio
    async def test_no_mapping_skips_audit_log(self):
        """无映射时跳过同步，不写审计日志。

        **Validates: Requirements US-3 验收标准 5**
        """
        wp_id = uuid.uuid4()
        project_id = uuid.uuid4()

        fake_db = FakeDB()
        user = FakeUser()
        service = WpDisclosureSyncService()

        audit_log_mock = AsyncMock()

        with patch.object(service, '_get_section_mapping', new=AsyncMock(return_value=None)), \
             patch.object(service, '_write_audit_log', audit_log_mock):
            result = await service.sync_from_html(
                fake_db, wp_id=wp_id, sheet_name="无映射sheet",
                sub_table_data={"st1": [{"v": 1}]},
                project_id=project_id, user=user, force=True,
            )

        assert result["success"] is True
        assert result.get("synced") is False
        assert result.get("reason") == "no_mapping"
        audit_log_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_audit_log_contains_correct_payload(self):
        """审计日志 payload 包含 wp_id, section_id, source 字段。

        **Validates: Requirements US-3 验收标准 5**
        """
        wp_id = uuid.uuid4()
        project_id = uuid.uuid4()
        section_id = "五-2-1 存货"

        existing_note = FakeNote(note_section=section_id)
        fake_db = FakeDB()
        user = FakeUser()
        service = WpDisclosureSyncService()

        mapping = {"section_id": section_id, "last_sync_at": existing_note.last_sync_at}

        with patch.object(service, '_get_section_mapping', new=AsyncMock(return_value=mapping)), \
             patch.object(service, '_get_note', new=AsyncMock(return_value=existing_note)), \
             patch.object(service, '_broadcast_synced', MagicMock()), \
             patch('app.models.audit_log_models.AuditLogEntry') as MockEntry:
            MockEntry.return_value = MagicMock()
            result = await service.sync_from_html(
                fake_db, wp_id=wp_id, sheet_name="存货附注C",
                sub_table_data={"st1": [{"v": 1}]},
                project_id=project_id, user=user, force=True,
            )

        assert result["success"] is True
        MockEntry.assert_called_once()
        kwargs = MockEntry.call_args[1]
        assert kwargs["user_id"] == user.id
        assert kwargs["action_type"] == "disclosure_sync_update"
        assert kwargs["object_type"] == "disclosure_note"
        assert kwargs["payload"]["wp_id"] == str(wp_id)
        assert kwargs["payload"]["section_id"] == section_id
        assert kwargs["payload"]["source"] == "workpaper_html"

    @pytest.mark.asyncio
    async def test_audit_log_failure_does_not_block_sync(self):
        """审计日志写入失败不阻断同步主流程。

        **Validates: Requirements US-3 验收标准 5**
        """
        wp_id = uuid.uuid4()
        project_id = uuid.uuid4()
        section_id = "五-1-1 应收账款"

        existing_note = FakeNote(note_section=section_id)
        fake_db = FakeDB()
        user = FakeUser()
        service = WpDisclosureSyncService()

        mapping = {"section_id": section_id, "last_sync_at": existing_note.last_sync_at}

        async def _failing_audit(*args, **kwargs):
            raise RuntimeError("Audit log DB error")

        with patch.object(service, '_get_section_mapping', new=AsyncMock(return_value=mapping)), \
             patch.object(service, '_get_note', new=AsyncMock(return_value=existing_note)), \
             patch.object(service, '_write_audit_log', _failing_audit), \
             patch.object(service, '_broadcast_synced', MagicMock()):
            result = await service.sync_from_html(
                fake_db, wp_id=wp_id, sheet_name="应收账款附注C",
                sub_table_data={"st1": [{"v": 1}]},
                project_id=project_id, user=user, force=True,
            )

        assert result["success"] is True
        assert result["synced"] is True

    @pytest.mark.asyncio
    async def test_sse_broadcast_on_sync(self):
        """同步成功后发送 SSE 通知。

        **Validates: Requirements US-3 design §4.2 step 6**
        """
        wp_id = uuid.uuid4()
        project_id = uuid.uuid4()
        section_id = "五-1-1 应收账款"

        existing_note = FakeNote(note_section=section_id)
        fake_db = FakeDB()
        user = FakeUser()
        service = WpDisclosureSyncService()

        mapping = {"section_id": section_id, "last_sync_at": existing_note.last_sync_at}
        broadcast_mock = MagicMock()

        with patch.object(service, '_get_section_mapping', new=AsyncMock(return_value=mapping)), \
             patch.object(service, '_get_note', new=AsyncMock(return_value=existing_note)), \
             patch.object(service, '_write_audit_log', AsyncMock()), \
             patch.object(service, '_broadcast_synced', broadcast_mock):
            result = await service.sync_from_html(
                fake_db, wp_id=wp_id, sheet_name="应收账款附注C",
                sub_table_data={"st1": [{"v": 1}]},
                project_id=project_id, user=user, force=True,
            )

        assert result["success"] is True
        broadcast_mock.assert_called_once_with(project_id, section_id)
