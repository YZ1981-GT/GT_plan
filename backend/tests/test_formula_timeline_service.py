"""公式版本时间轴测试（spec: formula-management-deep-optimization · R6）。

验证 build_timeline 的聚合逻辑和事件类型元数据。
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.formula_timeline_service import (
    EVENT_TYPES,
    build_timeline,
    _formula_changed_summary,
    _safe_payload,
)


class TestEventTypes:
    """事件类型元数据。"""

    def test_all_types_have_required_fields(self):
        for etype, meta in EVENT_TYPES.items():
            assert "icon" in meta, f"{etype} 缺 icon"
            assert "label" in meta, f"{etype} 缺 label"
            assert "color" in meta, f"{etype} 缺 color"

    def test_five_types(self):
        assert len(EVENT_TYPES) == 5


class TestFormulaChangedSummary:
    def test_with_module_and_row_code(self):
        entry = MagicMock()
        entry.payload = {"module": "report", "row_code": "R001", "action": "update"}
        result = _formula_changed_summary(entry)
        assert "report" in result
        assert "R001" in result

    def test_empty_payload(self):
        entry = MagicMock()
        entry.payload = {}
        result = _formula_changed_summary(entry)
        assert "公式变更" in result

    def test_none_payload(self):
        entry = MagicMock()
        entry.payload = None
        result = _formula_changed_summary(entry)
        assert "公式变更" in result


class TestSafePayload:
    def test_dict(self):
        entry = MagicMock()
        entry.payload = {"key": "value"}
        assert _safe_payload(entry) == {"key": "value"}

    def test_none(self):
        entry = MagicMock()
        entry.payload = None
        assert _safe_payload(entry) == {}

    def test_non_dict(self):
        entry = MagicMock()
        entry.payload = "string"
        assert _safe_payload(entry) == {}


class TestBuildTimelineStructure:
    """build_timeline 返回结构。"""

    @pytest.mark.asyncio
    async def test_returns_expected_keys(self):
        """返回 dict 包含全部必要键。"""
        db = AsyncMock()
        # mock 所有查询返回空结果
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalars.return_value.first.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        pid = uuid.uuid4()
        result = await build_timeline(db, pid, 2025)

        assert "project_id" in result
        assert "year" in result
        assert "total" in result
        assert "events" in result
        assert "event_types" in result
        assert result["year"] == 2025

    @pytest.mark.asyncio
    async def test_empty_events_on_no_data(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalars.return_value.first.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await build_timeline(db, uuid.uuid4(), 2025)
        assert result["total"] == 0
        assert result["events"] == []

    @pytest.mark.asyncio
    async def test_graceful_on_db_error(self):
        """DB 查询出错时不抛异常，返回部分结果。"""
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("DB down"))

        result = await build_timeline(db, uuid.uuid4(), 2025)
        # 各子查询独立 try/except，总 events 为空但不抛异常
        assert "events" in result
        assert isinstance(result["events"], list)
