"""Tests for KAM stale detection."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.a17_kam_push_service import (
    _format_kam_for_report,
    _write_kam_to_report_body,
    check_kam_stale,
    compute_kam_source_hash,
)


class TestComputeKamSourceHash:
    def test_stable_hash(self):
        items = [{"matter": "收入确认", "response": "截止测试"}]
        h1 = compute_kam_source_hash(items)
        h2 = compute_kam_source_hash(items)
        assert h1 == h2
        assert len(h1) == 64


@pytest.mark.asyncio
async def test_no_kam_entries_not_stale():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    result = await check_kam_stale(db, uuid.uuid4(), uuid.uuid4())
    assert result["stale"] is False
    assert "无 KAM" in result["message"]


@pytest.mark.asyncio
async def test_hash_mismatch_is_stale():
    """When report hash differs from current source hash, stale=True."""
    db = AsyncMock()
    project_id = uuid.uuid4()
    wp_id = uuid.uuid4()

    kam_row = MagicMock()
    kam_row.item_id = "A17-2-1-KAM-001"
    kam_row.conclusion = "收入确认"
    kam_row.remark = json.dumps({"situation": "A", "reason": "B", "response": "C"})
    kam_row.wp_ref = "D4"
    mock_kam_result = MagicMock()
    mock_kam_result.fetchall.return_value = [kam_row]

    items = _format_kam_for_report(
        [(kam_row.item_id, kam_row.conclusion, kam_row.remark, kam_row.wp_ref)]
    )
    current_hash = compute_kam_source_hash(items)

    mock_report = MagicMock()
    mock_report.report_body_json = {
        "sections": [
            {
                "section_id": "kam",
                "items": [{"matter": "old", "response": "old"}],
                "pushed_from": "A17-2-1",
                "source_hash": "deadbeef" * 8,
            }
        ]
    }
    mock_report_result = MagicMock()
    mock_report_result.scalar_one_or_none.return_value = mock_report

    db.execute = AsyncMock(side_effect=[mock_kam_result, mock_report_result])

    result = await check_kam_stale(db, project_id, wp_id)
    assert result["stale"] is True
    assert result["source_hash"] == current_hash
    assert result["report_hash"] == "deadbeef" * 8
    assert "未同步" in result["message"]


@pytest.mark.asyncio
async def test_matching_hash_not_stale():
    db = AsyncMock()
    project_id = uuid.uuid4()
    wp_id = uuid.uuid4()

    kam_row = MagicMock()
    kam_row.item_id = "A17-2-1-KAM-001"
    kam_row.conclusion = "商誉减值"
    kam_row.remark = ""
    kam_row.wp_ref = ""
    mock_kam_result = MagicMock()
    mock_kam_result.fetchall.return_value = [kam_row]

    items = _format_kam_for_report(
        [(kam_row.item_id, kam_row.conclusion, kam_row.remark, kam_row.wp_ref)]
    )
    source_hash = compute_kam_source_hash(items)

    class FakeReport:
        report_body_json = None

    mock_report = FakeReport()
    _write_kam_to_report_body(mock_report, items, source_hash=source_hash)
    mock_report_result = MagicMock()
    mock_report_result.scalar_one_or_none.return_value = mock_report

    db.execute = AsyncMock(side_effect=[mock_kam_result, mock_report_result])

    result = await check_kam_stale(db, project_id, wp_id)
    assert result["stale"] is False
    assert result["source_hash"] == source_hash
    assert result["report_hash"] == source_hash


@pytest.mark.asyncio
async def test_missing_pushed_from_is_stale():
    db = AsyncMock()
    wp_id = uuid.uuid4()

    kam_row = MagicMock()
    kam_row.item_id = "A17-2-1-KAM-001"
    kam_row.conclusion = "收入"
    kam_row.remark = ""
    kam_row.wp_ref = ""
    mock_kam_result = MagicMock()
    mock_kam_result.fetchall.return_value = [kam_row]

    items = [{"matter": "收入", "response": ""}]
    source_hash = compute_kam_source_hash(items)

    class FakeReport:
        report_body_json = {
            "sections": [{"section_id": "kam", "items": items, "source_hash": source_hash}]
        }

    mock_report = FakeReport()
    mock_report_result = MagicMock()
    mock_report_result.scalar_one_or_none.return_value = mock_report

    db.execute = AsyncMock(side_effect=[mock_kam_result, mock_report_result])

    result = await check_kam_stale(db, uuid.uuid4(), wp_id)
    assert result["stale"] is True
    assert "推送来源" in result["message"]
