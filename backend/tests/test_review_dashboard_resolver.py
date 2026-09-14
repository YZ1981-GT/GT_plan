"""Unit tests for review_dashboard_status auto_data_resolver.

验证 resolver 输出结构、sign_status 逻辑、progress 计算。
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.auto_data_resolvers._completion import _resolve_review_dashboard_status

# The resolver uses a local import inside the function body,
# so we must patch at the source module level
_TEMPLATES_PATCH = "app.services.a21_a25_version_selector.get_applicable_review_templates"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_project_id() -> uuid.UUID:
    return uuid.uuid4()


class FakeRow:
    """模拟 SA Row 对象，支持属性访问。"""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeResult:
    """模拟 SA execute() 返回的 result proxy。"""
    def __init__(self, rows: list):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def scalar(self):
        return self._rows[0] if self._rows else None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_project_returns_empty_levels():
    """无适用复核模板时返回空 levels。"""
    db = AsyncMock()
    project_id = _make_project_id()

    with patch(_TEMPLATES_PATCH, new_callable=AsyncMock, return_value=[]):
        result = await _resolve_review_dashboard_status(db, project_id, 2026)

    assert result == {"levels": []}


@pytest.mark.asyncio
async def test_not_started_status():
    """无任何 response 时 sign_status='not_started'。"""
    db = AsyncMock()
    project_id = _make_project_id()

    templates = [{"wp_code": "A21-1", "applicable": True}]

    # Mock DB queries: no wp rows, no assignments, no sign, no progress, no responses
    db.execute = AsyncMock(side_effect=[
        FakeResult([]),  # wp_info_rows
        FakeResult([]),  # assignment_rows
        FakeResult([]),  # sign_rows
        FakeResult([]),  # progress_rows
        FakeResult([]),  # response_exists_rows
    ])

    with patch(_TEMPLATES_PATCH, new_callable=AsyncMock, return_value=templates):
        result = await _resolve_review_dashboard_status(db, project_id, 2026)

    assert len(result["levels"]) == 1
    level = result["levels"][0]
    assert level["wp_code"] == "A21-1"
    assert level["level"] == "A21"
    assert level["level_label"] == "现场负责人"
    assert level["sign_status"] == "not_started"
    assert level["reviewer_name"] is None
    assert level["progress"] == {"completed": 0, "total": 0}


@pytest.mark.asyncio
async def test_pass_status_with_signer():
    """签字 pass 时返回 signer_name 和 signed_at。"""
    db = AsyncMock()
    project_id = _make_project_id()
    wp_id = uuid.uuid4()

    templates = [{"wp_code": "A22", "applicable": True}]

    remark_json = json.dumps({"signer_name": "李四", "signer_id": str(uuid.uuid4())})

    db.execute = AsyncMock(side_effect=[
        FakeResult([FakeRow(wp_code="A22", wp_id=str(wp_id))]),  # wp_info
        FakeResult([FakeRow(role="manager", name="李四")]),  # assignments
        FakeResult([FakeRow(wp_code="A22", conclusion="pass", remark=remark_json, updated_at="2026-01-15T10:30:00")]),  # sign
        FakeResult([FakeRow(wp_code="A22", total=10, completed=8)]),  # progress
        FakeResult([FakeRow(wp_code="A22", cnt=8)]),  # response_exists
    ])

    with patch(_TEMPLATES_PATCH, new_callable=AsyncMock, return_value=templates):
        result = await _resolve_review_dashboard_status(db, project_id, 2026)

    level = result["levels"][0]
    assert level["sign_status"] == "pass"
    assert level["signer_name"] == "李四"
    assert level["signed_at"] == "2026-01-15T10:30:00"
    assert level["reviewer_name"] == "李四"
    assert level["progress"] == {"completed": 8, "total": 10}


@pytest.mark.asyncio
async def test_reject_status():
    """签字 reject 时 sign_status='reject'。"""
    db = AsyncMock()
    project_id = _make_project_id()

    templates = [{"wp_code": "A23", "applicable": True}]

    db.execute = AsyncMock(side_effect=[
        FakeResult([]),  # wp_info
        FakeResult([FakeRow(role="signing_partner", name="王五")]),  # assignments
        FakeResult([FakeRow(wp_code="A23", conclusion="reject", remark=None, updated_at=None)]),  # sign
        FakeResult([]),  # progress
        FakeResult([]),  # response_exists
    ])

    with patch(_TEMPLATES_PATCH, new_callable=AsyncMock, return_value=templates):
        result = await _resolve_review_dashboard_status(db, project_id, 2026)

    level = result["levels"][0]
    assert level["sign_status"] == "reject"
    assert level["reviewer_name"] == "王五"


@pytest.mark.asyncio
async def test_in_progress_status():
    """有响应但无签字时 sign_status='in_progress'。"""
    db = AsyncMock()
    project_id = _make_project_id()

    templates = [{"wp_code": "A21-1", "applicable": True}]

    db.execute = AsyncMock(side_effect=[
        FakeResult([]),  # wp_info
        FakeResult([FakeRow(role="senior", name="张三")]),  # assignments
        FakeResult([]),  # sign (no sign record)
        FakeResult([FakeRow(wp_code="A21-1", total=15, completed=5)]),  # progress
        FakeResult([FakeRow(wp_code="A21-1", cnt=5)]),  # response_exists (has responses)
    ])

    with patch(_TEMPLATES_PATCH, new_callable=AsyncMock, return_value=templates):
        result = await _resolve_review_dashboard_status(db, project_id, 2026)

    level = result["levels"][0]
    assert level["sign_status"] == "in_progress"
    assert level["reviewer_name"] == "张三"
    assert level["progress"] == {"completed": 5, "total": 15}


@pytest.mark.asyncio
async def test_multiple_levels():
    """多级别同时返回正确结构。"""
    db = AsyncMock()
    project_id = _make_project_id()

    templates = [
        {"wp_code": "A21-1", "applicable": True},
        {"wp_code": "A22-1", "applicable": True},
        {"wp_code": "A23-1", "applicable": True},
        {"wp_code": "A24-1", "applicable": False},  # not applicable
    ]

    db.execute = AsyncMock(side_effect=[
        FakeResult([]),  # wp_info
        FakeResult([]),  # assignments
        FakeResult([]),  # sign
        FakeResult([]),  # progress
        FakeResult([]),  # response_exists
    ])

    with patch(_TEMPLATES_PATCH, new_callable=AsyncMock, return_value=templates):
        result = await _resolve_review_dashboard_status(db, project_id, 2026)

    # Only applicable codes should appear
    assert len(result["levels"]) == 3
    codes = [lvl["wp_code"] for lvl in result["levels"]]
    assert codes == ["A21-1", "A22-1", "A23-1"]


@pytest.mark.asyncio
async def test_output_structure_has_required_fields():
    """输出每个 level 包含所有必需字段。"""
    db = AsyncMock()
    project_id = _make_project_id()

    templates = [{"wp_code": "A25", "applicable": True}]

    db.execute = AsyncMock(side_effect=[
        FakeResult([]),
        FakeResult([]),
        FakeResult([]),
        FakeResult([]),
        FakeResult([]),
    ])

    with patch(_TEMPLATES_PATCH, new_callable=AsyncMock, return_value=templates):
        result = await _resolve_review_dashboard_status(db, project_id, 2026)

    required_fields = {"wp_code", "level", "level_label", "reviewer_name", "sign_status", "signed_at", "signer_name", "progress"}
    level = result["levels"][0]
    assert required_fields.issubset(set(level.keys()))
    assert level["sign_status"] in ("pass", "reject", "in_progress", "not_started")
    assert isinstance(level["progress"], dict)
    assert "completed" in level["progress"]
    assert "total" in level["progress"]
    assert level["progress"]["completed"] <= level["progress"]["total"]
