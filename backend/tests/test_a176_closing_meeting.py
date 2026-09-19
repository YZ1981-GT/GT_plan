"""Unit tests for A17-6 总结会会议纪要 render strategy.

Tests: normal flow, empty responses, project context auto-fill.
"""

from __future__ import annotations

from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.wp_render_strategies._a176_closing_meeting import render


# ─── Mock helpers ─────────────────────────────────────────────────────────────

ChecklistRow = namedtuple("ChecklistRow", ["item_id", "conclusion", "remark"])
ProjectRow = namedtuple("ProjectRow", ["client_name", "audit_year"])


def _make_ctx(wp_id="wp-001", project_id="proj-001", checklist_rows=None, project_row=None):
    """Build a minimal mock RenderContext."""
    ctx = MagicMock()
    ctx.wp_id = wp_id
    ctx.project_id = project_id

    db = AsyncMock()

    # Mock checklist_responses query
    checklist_result = MagicMock()
    checklist_result.fetchall.return_value = checklist_rows or []

    # Mock project query
    proj_result = MagicMock()
    proj_result.fetchone.return_value = project_row

    # Sequential execute calls: first = checklist, second = project
    db.execute = AsyncMock(side_effect=[checklist_result, proj_result])
    ctx.db = db

    return ctx


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestA176RenderNormal:
    """Normal flow with saved data."""

    @pytest.mark.asyncio
    async def test_returns_saved_fields(self):
        """Saved checklist_responses are returned in fields dict."""
        rows = [
            ChecklistRow("a176-meeting_time", None, "2026-06-20 14:00"),
            ChecklistRow("a176-attendees", None, "张三、李四、王五"),
            ChecklistRow("a176-minutes", None, "讨论了审计发现和总结"),
            ChecklistRow("a176-conclusion", None, "同意出具标准无保留意见"),
            ChecklistRow("a176-attachments", None, "签到表"),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert result is not None
        assert result["fields"]["meeting_time"] == "2026-06-20 14:00"
        assert result["fields"]["attendees"] == "张三、李四、王五"
        assert result["fields"]["minutes"] == "讨论了审计发现和总结"
        assert result["fields"]["conclusion"] == "同意出具标准无保留意见"
        assert result["fields"]["attachments"] == "签到表"

    @pytest.mark.asyncio
    async def test_returns_saved_meta(self):
        """Saved meta fields are returned."""
        rows = [
            ChecklistRow("a176-meta-preparer", "编制人A", None),
            ChecklistRow("a176-meta-reviewer", "复核人B", None),
            ChecklistRow("a176-meta-date", "2026-06-20", None),
        ]
        proj = ProjectRow("致同审计公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert result["meta_info"]["preparer"] == "编制人A"
        assert result["meta_info"]["reviewer"] == "复核人B"
        assert result["meta_info"]["date"] == "2026-06-20"

    @pytest.mark.asyncio
    async def test_project_context_populated(self):
        """Project context is correctly populated from DB."""
        proj = ProjectRow("大华会计师事务所", 2025)
        ctx = _make_ctx(checklist_rows=[], project_row=proj)

        result = await render(ctx)

        assert result["project_context"]["client_name"] == "大华会计师事务所"
        assert result["project_context"]["period"] == "2025年12月31日"


class TestA176RenderEmpty:
    """Empty/missing data scenarios."""

    @pytest.mark.asyncio
    async def test_empty_responses_returns_defaults(self):
        """No saved data returns empty strings for all fields."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert result is not None
        assert all(v == "" for v in result["fields"].values())
        assert result["meta_info"]["index_no"] == "A17-6"

    @pytest.mark.asyncio
    async def test_no_project_returns_empty_context(self):
        """Missing project returns empty context strings."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert result["project_context"]["client_name"] == ""
        assert result["project_context"]["period"] == ""

    @pytest.mark.asyncio
    async def test_auto_fill_meta_from_project(self):
        """Meta client_name/period auto-fill from project when not manually set."""
        proj = ProjectRow("自动填充公司", 2024)
        ctx = _make_ctx(checklist_rows=[], project_row=proj)

        result = await render(ctx)

        assert result["meta_info"]["client_name"] == "自动填充公司"
        assert result["meta_info"]["period"] == "2024年12月31日"

    @pytest.mark.asyncio
    async def test_manual_meta_overrides_auto_fill(self):
        """Manually saved meta values override auto-fill."""
        rows = [
            ChecklistRow("a176-meta-client_name", "手动输入公司", None),
            ChecklistRow("a176-meta-period", "2023年6月30日", None),
        ]
        proj = ProjectRow("自动填充公司", 2024)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert result["meta_info"]["client_name"] == "手动输入公司"
        assert result["meta_info"]["period"] == "2023年6月30日"


class TestA176RenderStructure:
    """Response structure validation."""

    @pytest.mark.asyncio
    async def test_response_has_three_top_keys(self):
        """Response always has exactly 3 top-level keys."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert set(result.keys()) == {"meta_info", "fields", "project_context"}

    @pytest.mark.asyncio
    async def test_meta_info_has_6_keys(self):
        """meta_info always has exactly 6 keys."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert len(result["meta_info"]) == 6
        assert set(result["meta_info"].keys()) == {
            "client_name", "period", "preparer", "reviewer", "date", "index_no"
        }

    @pytest.mark.asyncio
    async def test_fields_has_5_keys(self):
        """fields always has exactly 5 keys."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert len(result["fields"]) == 5
        assert set(result["fields"].keys()) == {
            "meeting_time", "attendees", "minutes", "conclusion", "attachments"
        }
