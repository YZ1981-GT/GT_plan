"""审计日志装饰器单元测试

测试 @audit_log 装饰器的核心功能：
- compute_diff 差异计算
- snapshot_from_row ORM 行快照
- 装饰器参数提取
- 异步方法装饰

Validates: Requirements R7.5
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.core.audit_decorator import (
    _extract_param,
    _serialize_value,
    audit_log,
    compute_diff,
    snapshot_from_row,
    snapshot_from_rows,
)


# ---------------------------------------------------------------------------
# compute_diff 测试
# ---------------------------------------------------------------------------


class TestComputeDiff:
    def test_both_none(self):
        assert compute_diff(None, None) == []

    def test_before_none_creates_all_fields(self):
        after = {"status": "approved", "amount": 100}
        diff = compute_diff(None, after)
        assert len(diff) == 2
        assert {"field": "amount", "old": None, "new": 100} in diff
        assert {"field": "status", "old": None, "new": "approved"} in diff

    def test_after_none_removes_all_fields(self):
        before = {"status": "draft", "name": "test"}
        diff = compute_diff(before, None)
        assert len(diff) == 2
        assert {"field": "name", "old": "test", "new": None} in diff
        assert {"field": "status", "old": "draft", "new": None} in diff

    def test_no_changes(self):
        state = {"a": 1, "b": "x"}
        assert compute_diff(state, state) == []

    def test_changed_fields_only(self):
        before = {"status": "draft", "name": "test", "amount": 100}
        after = {"status": "approved", "name": "test", "amount": 200}
        diff = compute_diff(before, after)
        assert len(diff) == 2
        fields = {d["field"] for d in diff}
        assert fields == {"status", "amount"}

    def test_added_field(self):
        before = {"a": 1}
        after = {"a": 1, "b": 2}
        diff = compute_diff(before, after)
        assert diff == [{"field": "b", "old": None, "new": 2}]

    def test_removed_field(self):
        before = {"a": 1, "b": 2}
        after = {"a": 1}
        diff = compute_diff(before, after)
        assert diff == [{"field": "b", "old": 2, "new": None}]

    def test_diff_sorted_by_field_name(self):
        before = {"z": 1, "a": 2}
        after = {"z": 10, "a": 20}
        diff = compute_diff(before, after)
        assert diff[0]["field"] == "a"
        assert diff[1]["field"] == "z"


# ---------------------------------------------------------------------------
# _serialize_value 测试
# ---------------------------------------------------------------------------


class TestSerializeValue:
    def test_none(self):
        assert _serialize_value(None) is None

    def test_uuid(self):
        uid = uuid.uuid4()
        assert _serialize_value(uid) == str(uid)

    def test_datetime(self):
        dt = datetime(2025, 1, 15, 10, 30, 0)
        assert _serialize_value(dt) == dt.isoformat()

    def test_primitives(self):
        assert _serialize_value(42) == 42
        assert _serialize_value(3.14) == 3.14
        assert _serialize_value("hello") == "hello"
        assert _serialize_value(True) is True

    def test_enum_like(self):
        class FakeEnum:
            value = "draft"
        assert _serialize_value(FakeEnum()) == "draft"

    def test_fallback_to_str(self):
        assert _serialize_value([1, 2, 3]) == "[1, 2, 3]"


# ---------------------------------------------------------------------------
# snapshot_from_row 测试
# ---------------------------------------------------------------------------


class TestSnapshotFromRow:
    def test_none_returns_empty(self):
        assert snapshot_from_row(None) == {}

    def test_orm_like_object(self):
        """模拟 ORM 行对象的快照提取"""
        # 创建一个模拟的 mapper
        col1 = MagicMock()
        col1.key = "id"
        col2 = MagicMock()
        col2.key = "status"
        col3 = MagicMock()
        col3.key = "name"

        mapper = MagicMock()
        mapper.columns = [col1, col2, col3]

        row = MagicMock()
        row.__class__.__mapper__ = mapper
        row.id = uuid.uuid4()
        row.status = "draft"
        row.name = "test entry"

        result = snapshot_from_row(row)
        assert result["id"] == str(row.id)
        assert result["status"] == "draft"
        assert result["name"] == "test entry"


class TestSnapshotFromRows:
    def test_empty_list(self):
        assert snapshot_from_rows([]) == {}

    def test_multiple_rows(self):
        col = MagicMock()
        col.key = "val"
        mapper = MagicMock()
        mapper.columns = [col]

        row1 = MagicMock()
        row1.__class__.__mapper__ = mapper
        row1.val = 1

        row2 = MagicMock()
        row2.__class__.__mapper__ = mapper
        row2.val = 2

        result = snapshot_from_rows([row1, row2])
        assert result["count"] == 2
        assert len(result["rows"]) == 2


# ---------------------------------------------------------------------------
# _extract_param 测试
# ---------------------------------------------------------------------------


class TestExtractParam:
    def test_from_kwargs(self):
        import inspect
        def fn(self, project_id, entry_group_id): ...
        sig = inspect.signature(fn)
        assert _extract_param("project_id", (), {"project_id": "abc"}, sig) == "abc"

    def test_from_args(self):
        import inspect
        def fn(self, project_id, entry_group_id): ...
        sig = inspect.signature(fn)
        uid = uuid.uuid4()
        # args includes self at index 0, project_id at index 1
        assert _extract_param("project_id", ("self_placeholder", uid), {}, sig) == uid

    def test_missing_returns_none(self):
        import inspect
        def fn(self, project_id): ...
        sig = inspect.signature(fn)
        assert _extract_param("nonexistent", (), {}, sig) is None


# ---------------------------------------------------------------------------
# @audit_log 装饰器集成测试
# ---------------------------------------------------------------------------


class TestAuditLogDecorator:
    @pytest.mark.asyncio
    async def test_decorator_preserves_return_value(self):
        """装饰器不应改变原方法的返回值"""

        class FakeService:
            @audit_log(action="delete", object_type="test")
            async def do_something(self, project_id: UUID, entry_group_id: UUID):
                return {"message": "done"}

        svc = FakeService()
        with patch("app.core.audit_decorator._write_audit_log", new_callable=AsyncMock):
            result = await svc.do_something(uuid.uuid4(), uuid.uuid4())
        assert result == {"message": "done"}

    @pytest.mark.asyncio
    async def test_decorator_preserves_exceptions(self):
        """装饰器不应吞掉原方法的异常"""

        class FakeService:
            @audit_log(action="delete", object_type="test")
            async def do_something(self, project_id: UUID, entry_group_id: UUID):
                raise ValueError("test error")

        svc = FakeService()
        with pytest.raises(ValueError, match="test error"):
            with patch("app.core.audit_decorator._write_audit_log", new_callable=AsyncMock):
                await svc.do_something(uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_decorator_calls_write_audit_log(self):
        """装饰器应调用 _write_audit_log"""

        class FakeService:
            @audit_log(action="delete", object_type="test_obj")
            async def do_something(self, project_id: UUID, entry_group_id: UUID):
                return None

        svc = FakeService()
        pid = uuid.uuid4()
        eid = uuid.uuid4()

        with patch("app.core.audit_decorator._write_audit_log", new_callable=AsyncMock) as mock_write:
            await svc.do_something(pid, eid)

        mock_write.assert_called_once()
        call_kwargs = mock_write.call_args
        assert call_kwargs[1]["action"] == "delete"
        assert call_kwargs[1]["object_type"] == "test_obj"
        assert call_kwargs[1]["object_id"] == eid
        assert call_kwargs[1]["project_id"] == pid

    @pytest.mark.asyncio
    async def test_auto_detect_object_type_from_class_name(self):
        """object_type 为 None 时应从类名自动推断"""

        class MyEntityService:
            @audit_log(action="update")
            async def update(self, project_id: UUID, entry_group_id: UUID):
                return None

        svc = MyEntityService()
        with patch("app.core.audit_decorator._write_audit_log", new_callable=AsyncMock) as mock_write:
            await svc.update(uuid.uuid4(), uuid.uuid4())

        call_kwargs = mock_write.call_args
        assert call_kwargs[1]["object_type"] == "myentity"

    @pytest.mark.asyncio
    async def test_decorator_extracts_reviewer_id(self):
        """装饰器应能从 reviewer_id 参数提取 user_id"""

        class FakeService:
            @audit_log(action="review", object_type="test")
            async def review(self, project_id: UUID, entry_group_id: UUID, reviewer_id: UUID):
                return None

        svc = FakeService()
        pid = uuid.uuid4()
        eid = uuid.uuid4()
        rid = uuid.uuid4()

        with patch("app.core.audit_decorator._write_audit_log", new_callable=AsyncMock) as mock_write:
            await svc.review(pid, eid, rid)

        call_kwargs = mock_write.call_args
        assert call_kwargs[1]["user_id"] == rid

    @pytest.mark.asyncio
    async def test_decorator_extracts_wp_id(self):
        """装饰器应能从 wp_id 参数提取 object_id"""

        class FakeService:
            @audit_log(action="status_change", object_type="working_paper")
            async def update_status(self, db, wp_id: UUID, new_status: str, project_id: UUID = None):
                return {"status": new_status}

        svc = FakeService()
        wid = uuid.uuid4()
        pid = uuid.uuid4()

        with patch("app.core.audit_decorator._write_audit_log", new_callable=AsyncMock) as mock_write:
            result = await svc.update_status(None, wid, "approved", project_id=pid)

        assert result == {"status": "approved"}
        call_kwargs = mock_write.call_args
        assert call_kwargs[1]["object_id"] == wid
        assert call_kwargs[1]["project_id"] == pid
