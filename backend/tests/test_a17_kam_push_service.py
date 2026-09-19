"""Tests for a17_kam_push_service — KAM → 审计报告单向 push"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.a17_kam_push_service import (
    _format_kam_for_report,
    _parse_remark,
    _write_kam_to_report_body,
    push_kam_to_report,
)


# ─── Unit tests for helpers ─────────────────────────────────────────


class TestParseRemark:
    def test_valid_json(self):
        result = _parse_remark('{"situation": "收入虚增", "reason": "风险高"}')
        assert result == {"situation": "收入虚增", "reason": "风险高"}

    def test_empty_string(self):
        assert _parse_remark("") == {}

    def test_none(self):
        assert _parse_remark(None) == {}

    def test_invalid_json(self):
        assert _parse_remark("not json") == {}


class TestFormatKamForReport:
    def test_full_entry(self):
        entries = [
            (
                "A17-2-1-KAM-001",
                "收入确认",
                json.dumps({
                    "situation": "公司收入占比大",
                    "reason": "收入确认涉及重大判断",
                    "response": "我们执行了截止测试",
                    "refs": "D4-1",
                }),
                "D4,B50",
            )
        ]
        items = _format_kam_for_report(entries)
        assert len(items) == 1
        assert "收入确认" in items[0]["matter"]
        assert "公司收入占比大" in items[0]["matter"]
        assert "收入确认涉及重大判断" in items[0]["matter"]
        assert items[0]["response"] == "我们执行了截止测试"

    def test_minimal_entry(self):
        entries = [("A17-2-1-KAM-001", "商誉减值", "", "")]
        items = _format_kam_for_report(entries)
        assert len(items) == 1
        assert items[0]["matter"] == "商誉减值"
        assert items[0]["response"] == ""

    def test_empty_title_uses_item_id(self):
        entries = [("A17-2-1-KAM-002", "", "", "")]
        items = _format_kam_for_report(entries)
        assert items[0]["matter"] == "A17-2-1-KAM-002"

    def test_multiple_entries(self):
        entries = [
            ("A17-2-1-KAM-001", "收入确认", '{"response": "截止测试"}', "D4"),
            ("A17-2-1-KAM-002", "商誉减值", '{"response": "减值评估"}', "G2"),
        ]
        items = _format_kam_for_report(entries)
        assert len(items) == 2
        assert items[0]["response"] == "截止测试"
        assert items[1]["response"] == "减值评估"


class TestWriteKamToReportBody:
    def _make_report(self, body=None):
        report = MagicMock()
        report.report_body_json = body
        return report

    def test_none_body_creates_structure(self):
        report = self._make_report(None)
        items = [{"matter": "X", "response": "Y"}]
        _write_kam_to_report_body(report, items)
        body = report.report_body_json
        assert "sections" in body
        kam = next(s for s in body["sections"] if s["section_id"] == "kam")
        assert kam["items"] == items
        assert kam["pushed_from"] == "A17-2-1"

    def test_existing_kam_section_overwritten(self):
        existing_body = {
            "sections": [
                {"section_id": "opinion", "content": "无保留"},
                {
                    "section_id": "kam",
                    "section_name": "关键审计事项段",
                    "items": [{"matter": "old", "response": "old"}],
                    "content": "",
                },
            ]
        }
        report = self._make_report(existing_body)
        new_items = [{"matter": "new1", "response": "new1-r"}]
        _write_kam_to_report_body(report, new_items)
        body = report.report_body_json
        # Opinion section should be preserved
        assert any(s["section_id"] == "opinion" for s in body["sections"])
        kam = next(s for s in body["sections"] if s["section_id"] == "kam")
        assert kam["items"] == new_items
        assert len(kam["items"]) == 1

    def test_no_kam_section_appends_new(self):
        existing_body = {
            "sections": [
                {"section_id": "opinion", "content": "无保留"},
            ]
        }
        report = self._make_report(existing_body)
        items = [{"matter": "A", "response": "B"}]
        _write_kam_to_report_body(report, items)
        body = report.report_body_json
        assert len(body["sections"]) == 2
        kam = next(s for s in body["sections"] if s["section_id"] == "kam")
        assert kam["items"] == items


# ─── Integration-style test for push_kam_to_report ──────────────────


@pytest.mark.asyncio
async def test_push_no_entries_returns_failure():
    """When no KAM entries exist, push returns failure with helpful message."""
    db = AsyncMock()
    # Mock empty result
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    result = await push_kam_to_report(db, uuid.uuid4(), uuid.uuid4())
    assert result["success"] is False
    assert result["pushed_count"] == 0
    assert "未找到" in result["message"]


@pytest.mark.asyncio
async def test_push_no_report_returns_failure():
    """When audit report doesn't exist, push returns failure."""
    db = AsyncMock()
    project_id = uuid.uuid4()
    wp_id = uuid.uuid4()

    # First call: load KAM entries (returns data)
    kam_row = MagicMock()
    kam_row.item_id = "A17-2-1-KAM-001"
    kam_row.conclusion = "收入确认"
    kam_row.remark = '{"situation":"X","reason":"Y","response":"Z"}'
    kam_row.wp_ref = "D4"
    mock_kam_result = MagicMock()
    mock_kam_result.fetchall.return_value = [kam_row]

    # Second call: get audit report (returns None)
    mock_report_result = MagicMock()
    mock_report_result.scalar_one_or_none.return_value = None

    db.execute = AsyncMock(side_effect=[mock_kam_result, mock_report_result])

    result = await push_kam_to_report(db, project_id, wp_id)
    assert result["success"] is False
    assert "尚未创建审计报告" in result["message"]


@pytest.mark.asyncio
async def test_push_success():
    """When both KAM entries and report exist, push succeeds."""
    db = AsyncMock()
    project_id = uuid.uuid4()
    wp_id = uuid.uuid4()

    # First call: load KAM entries
    kam_row = MagicMock()
    kam_row.item_id = "A17-2-1-KAM-001"
    kam_row.conclusion = "收入确认"
    kam_row.remark = '{"situation":"公司收入大","reason":"重大判断","response":"执行截止测试"}'
    kam_row.wp_ref = "D4"
    mock_kam_result = MagicMock()
    mock_kam_result.fetchall.return_value = [kam_row]

    # Second call: get audit report
    mock_report = MagicMock()
    mock_report.report_body_json = {"sections": []}
    mock_report_result = MagicMock()
    mock_report_result.scalar_one_or_none.return_value = mock_report

    db.execute = AsyncMock(side_effect=[mock_kam_result, mock_report_result])
    db.flush = AsyncMock()

    result = await push_kam_to_report(db, project_id, wp_id)
    assert result["success"] is True
    assert result["pushed_count"] == 1
    assert "1 条" in result["message"]

    # Verify report_body_json was updated
    body = mock_report.report_body_json
    kam_section = next(s for s in body["sections"] if s["section_id"] == "kam")
    assert len(kam_section["items"]) == 1
    assert "收入确认" in kam_section["items"][0]["matter"]
    assert kam_section["items"][0]["response"] == "执行截止测试"
    assert kam_section["pushed_from"] == "A17-2-1"
    assert "source_hash" in kam_section
    assert "pushed_at" in kam_section
