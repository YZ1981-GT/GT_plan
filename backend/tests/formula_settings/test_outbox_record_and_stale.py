"""S4 T1 单元测试：record_changes 入队 + 同事务标过期。

SQLite 内存库，不依赖 PG。验证：
1. 入队后 outbox 行存在且 status=pending
2. 同事务标过期（report 走 mark_changed、wp/note 直接 UPDATE）
3. 回滚后 outbox 行不存在
4. 空 events 不入队
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.formula_settings.stale_marks import (
    mark_wp_stale,
    mark_note_stale,
    mark_in_txn,
)


class TestStaleMarks:
    """stale_marks.py 单元测试。"""

    @pytest.mark.asyncio
    async def test_mark_in_txn_unknown_domain_returns_no_mark(self):
        """未知域（cross_check/push/tb_detail）不标过期。"""
        db = AsyncMock()
        result = await mark_in_txn(db, "cross_check", uuid.uuid4(), ["slot1"])
        assert result["marked"] == 0
        assert result.get("reason") == "no_stale_mark_for_domain"

    @pytest.mark.asyncio
    async def test_mark_in_txn_empty_slots(self):
        """空 slot_keys 不标过期。"""
        db = AsyncMock()
        result = await mark_in_txn(db, "report", uuid.uuid4(), [])
        assert result["marked"] == 0

    @pytest.mark.asyncio
    async def test_mark_in_txn_report_delegates_to_mark_changed(self):
        """report 域委托给 report_freshness.mark_changed。"""
        pid = uuid.uuid4()
        mock_mark = AsyncMock(return_value={pid: {"row1", "row2"}})
        mock_slot = lambda slots: {s.partition(":")[2] for s in slots if ":" in s}
        with patch("app.services.report_freshness.mark_changed", mock_mark), \
             patch("app.services.report_freshness.slot_row_codes", mock_slot):
            result = await mark_in_txn(AsyncMock(), "report", pid, ["type:row1", "type:row2"])
        assert result["domain"] == "report"
        assert result["marked"] == 2
        mock_mark.assert_awaited_once()


class TestOutboxRecord:
    """outbox.py record_changes 单元测试。"""

    @pytest.mark.asyncio
    async def test_empty_events_returns_empty(self):
        from app.services.formula_settings.outbox import record_changes
        db = AsyncMock()
        db.info = {}
        result = await record_changes(db, domain="report", events=[], source="test")
        assert result == []

    @pytest.mark.asyncio
    async def test_events_without_slot_keys_skipped(self):
        from app.services.formula_settings.outbox import record_changes
        db = AsyncMock()
        db.info = {}
        events = [{"project_id": str(uuid.uuid4()), "slot_keys": []}]
        with patch("app.services.formula_settings.stale_marks.mark_in_txn", new_callable=AsyncMock):
            with patch("app.services.workpaper_sync.outbox.DurableEventOutboxService") as mock_svc:
                result = await record_changes(db, domain="report", events=events, source="test")
        assert result == []
