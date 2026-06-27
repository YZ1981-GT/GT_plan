"""Unit tests for A17-3 业务咨询记录 render strategy.

Tests: normal flow, empty responses, JSON file tag failure, project context auto-fill.
"""

from __future__ import annotations

import json
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.wp_render_strategies._a173_consultation_record import render


# ─── Mock helpers ─────────────────────────────────────────────────────────────

ChecklistRow = namedtuple("ChecklistRow", ["item_id", "conclusion", "remark"])
ProjectRow = namedtuple("ProjectRow", ["client_name", "audit_year"])


def _make_ctx(wp_id="wp-001", project_id="proj-001", checklist_rows=None, project_row=None):
    """Build a minimal mock RenderContext."""
    ctx = MagicMock()
    ctx.wp_id = wp_id
    ctx.project_id = project_id

    db = AsyncMock()

    checklist_result = MagicMock()
    checklist_result.fetchall.return_value = checklist_rows or []

    proj_result = MagicMock()
    proj_result.fetchone.return_value = project_row

    db.execute = AsyncMock(side_effect=[checklist_result, proj_result])
    ctx.db = db

    return ctx


# ─── Tests: Normal flow ──────────────────────────────────────────────────────


class TestA173RenderNormal:
    """Normal flow with saved data."""

    @pytest.mark.asyncio
    async def test_returns_saved_meta(self):
        """Saved meta fields are returned in meta_info dict."""
        rows = [
            ChecklistRow("a173-meta-department", "审计一部", None),
            ChecklistRow("a173-meta-consult_type", "会计处理", None),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert result["meta_info"]["department"] == "审计一部"
        assert result["meta_info"]["consult_type"] == "会计处理"

    @pytest.mark.asyncio
    async def test_returns_saved_sections(self):
        """Saved section fields are returned correctly."""
        rows = [
            ChecklistRow("a173-sec1-overview", None, "客户从事制造业"),
            ChecklistRow("a173-sec1-background", None, "关于收入确认时点问题"),
            ChecklistRow("a173-sec2-opinion", None, "项目组认为应按时点确认"),
            ChecklistRow("a173-sec3-standards", None, "CAS 14第10条"),
            ChecklistRow("a173-sec3-reply", None, "同意项目组意见"),
            ChecklistRow("a173-sec4-opinion", None, "技术委员会批准"),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert result["sections"]["1"]["overview"] == "客户从事制造业"
        assert result["sections"]["1"]["background"] == "关于收入确认时点问题"
        assert result["sections"]["2"]["opinion"] == "项目组认为应按时点确认"
        assert result["sections"]["3"]["standards"] == "CAS 14第10条"
        assert result["sections"]["3"]["reply"] == "同意项目组意见"
        assert result["sections"]["4"]["opinion"] == "技术委员会批准"

    @pytest.mark.asyncio
    async def test_returns_file_tags_from_json(self):
        """File tags are parsed from JSON remark field."""
        file_list = ["合同.pdf", "邮件记录.eml", "准则原文.pdf"]
        rows = [
            ChecklistRow("a173-sec1-files", "3", json.dumps(file_list, ensure_ascii=False)),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert result["sections"]["1"]["files"] == file_list

    @pytest.mark.asyncio
    async def test_project_context_populated(self):
        """Project context is correctly populated from DB."""
        proj = ProjectRow("大华公司", 2025)
        ctx = _make_ctx(checklist_rows=[], project_row=proj)

        result = await render(ctx)

        assert result["project_context"]["client_name"] == "大华公司"
        assert result["project_context"]["period"] == "2025年12月31日"


class TestA173RenderEmpty:
    """Empty/missing data scenarios."""

    @pytest.mark.asyncio
    async def test_empty_responses_returns_defaults(self):
        """No saved data returns empty strings for all fields."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert result is not None
        assert result["meta_info"]["department"] == ""
        assert result["meta_info"]["consult_type"] == ""
        assert result["sections"]["1"]["overview"] == ""
        assert result["sections"]["1"]["files"] == []
        assert result["sections"]["2"]["opinion"] == ""
        assert result["sections"]["3"]["standards"] == ""
        assert result["sections"]["4"]["opinion"] == ""

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
            ChecklistRow("a173-meta-client_name", "手动输入公司", None),
            ChecklistRow("a173-meta-period", "2023年6月30日", None),
        ]
        proj = ProjectRow("自动填充公司", 2024)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert result["meta_info"]["client_name"] == "手动输入公司"
        assert result["meta_info"]["period"] == "2023年6月30日"


class TestA173RenderJsonFailure:
    """JSON parse failure scenarios."""

    @pytest.mark.asyncio
    async def test_invalid_json_returns_empty_files(self):
        """Invalid JSON in files remark returns empty list."""
        rows = [
            ChecklistRow("a173-sec1-files", "2", "not valid json!"),
        ]
        proj = ProjectRow("公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert result["sections"]["1"]["files"] == []

    @pytest.mark.asyncio
    async def test_non_list_json_returns_empty_files(self):
        """Non-list JSON (dict) returns empty list."""
        rows = [
            ChecklistRow("a173-sec1-files", "0", '{"not": "a list"}'),
        ]
        proj = ProjectRow("公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert result["sections"]["1"]["files"] == []


class TestA173RenderStructure:
    """Response structure validation."""

    @pytest.mark.asyncio
    async def test_response_has_three_top_keys(self):
        """Response always has exactly 3 top-level keys."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert set(result.keys()) == {"meta_info", "sections", "project_context"}

    @pytest.mark.asyncio
    async def test_meta_info_has_4_keys(self):
        """meta_info always has exactly 4 keys."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert set(result["meta_info"].keys()) == {
            "department", "client_name", "consult_type", "period"
        }

    @pytest.mark.asyncio
    async def test_sections_has_4_keys(self):
        """sections always has keys '1' through '4'."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert set(result["sections"].keys()) == {"1", "2", "3", "4"}

    @pytest.mark.asyncio
    async def test_section1_has_3_fields_plus_files(self):
        """Section 1 has overview, background, files."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert set(result["sections"]["1"].keys()) == {"overview", "background", "files"}
