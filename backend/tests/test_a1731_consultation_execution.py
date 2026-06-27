"""Unit tests for A17-3-1 业务咨询结果执行情况记录 render strategy.

Tests: normal flow, A17-3 reference loading, empty data, project context auto-fill.
"""

from __future__ import annotations

from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.wp_render_strategies._a1731_consultation_execution import render


# ─── Mock helpers ─────────────────────────────────────────────────────────────

ChecklistRow = namedtuple("ChecklistRow", ["item_id", "conclusion", "remark"])
ProjectRow = namedtuple("ProjectRow", ["client_name", "audit_year"])


def _make_ctx(wp_id="wp-001", project_id="proj-001", checklist_rows=None, ref_rows=None, project_row=None):
    """Build a minimal mock RenderContext."""
    ctx = MagicMock()
    ctx.wp_id = wp_id
    ctx.project_id = project_id

    db = AsyncMock()

    # Mock results for sequential execute calls:
    # 1st = checklist_responses (a1731-%)
    # 2nd = a173 reference (a173-sec1-%)
    # 3rd = project context
    checklist_result = MagicMock()
    checklist_result.fetchall.return_value = checklist_rows or []

    ref_result = MagicMock()
    ref_result.fetchall.return_value = ref_rows or []

    proj_result = MagicMock()
    proj_result.fetchone.return_value = project_row

    db.execute = AsyncMock(side_effect=[checklist_result, ref_result, proj_result])
    ctx.db = db

    return ctx


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestA1731RenderNormal:
    """Normal flow with saved data."""

    @pytest.mark.asyncio
    async def test_returns_saved_sections(self):
        """Saved checklist_responses are returned in sections dict."""
        rows = [
            ChecklistRow("a1731-sec1-supplementary", None, "补充说明内容"),
            ChecklistRow("a1731-sec2-execution_details", None, "执行情况详细描述"),
            ChecklistRow("a1731-sec3-results", None, "咨询结果已落实"),
            ChecklistRow("a1731-sec4-follow_up", None, "后续跟进事项"),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("测试公司", 2025))

        result = await render(ctx)

        assert result is not None
        assert result["sections"]["1"]["supplementary"] == "补充说明内容"
        assert result["sections"]["2"]["execution_details"] == "执行情况详细描述"
        assert result["sections"]["3"]["results"] == "咨询结果已落实"
        assert result["sections"]["4"]["follow_up"] == "后续跟进事项"

    @pytest.mark.asyncio
    async def test_returns_saved_meta(self):
        """Saved meta fields are returned."""
        rows = [
            ChecklistRow("a1731-meta-executor", "张三", None),
            ChecklistRow("a1731-meta-execution_date", "2026-06-20", None),
            ChecklistRow("a1731-meta-review_date", "2026-06-25", None),
            ChecklistRow("a1731-meta-reviewer", "李四", None),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("测试公司", 2025))

        result = await render(ctx)

        assert result["meta_info"]["executor"] == "张三"
        assert result["meta_info"]["execution_date"] == "2026-06-20"
        assert result["meta_info"]["review_date"] == "2026-06-25"
        assert result["meta_info"]["reviewer"] == "李四"


class TestA1731RenderA173Reference:
    """A17-3 reference loading."""

    @pytest.mark.asyncio
    async def test_loads_a173_reference_data(self):
        """A17-3 section 1 data is loaded into a173_reference."""
        ref_rows = [
            ChecklistRow("a173-sec1-overview", None, "客户从事制造业"),
            ChecklistRow("a173-sec1-background", None, "收入确认时点问题"),
        ]
        ctx = _make_ctx(ref_rows=ref_rows, project_row=ProjectRow("测试公司", 2025))

        result = await render(ctx)

        assert result["a173_reference"]["overview"] == "客户从事制造业"
        assert result["a173_reference"]["background"] == "收入确认时点问题"

    @pytest.mark.asyncio
    async def test_no_a173_data_returns_empty_reference(self):
        """Missing A17-3 data returns empty strings."""
        ctx = _make_ctx(ref_rows=[], project_row=ProjectRow("测试公司", 2025))

        result = await render(ctx)

        assert result["a173_reference"]["overview"] == ""
        assert result["a173_reference"]["background"] == ""


class TestA1731RenderEmpty:
    """Empty/missing data scenarios."""

    @pytest.mark.asyncio
    async def test_empty_responses_returns_defaults(self):
        """No saved data returns empty strings for all sections."""
        ctx = _make_ctx(checklist_rows=[], ref_rows=[], project_row=None)

        result = await render(ctx)

        assert result is not None
        assert all(v == "" for sec in result["sections"].values() for v in sec.values())
        assert all(v == "" for v in result["meta_info"].values())

    @pytest.mark.asyncio
    async def test_no_project_returns_empty_context(self):
        """Missing project returns empty context strings."""
        ctx = _make_ctx(checklist_rows=[], ref_rows=[], project_row=None)

        result = await render(ctx)

        assert result["project_context"]["client_name"] == ""
        assert result["project_context"]["period"] == ""

    @pytest.mark.asyncio
    async def test_project_context_populated(self):
        """Project context is correctly populated from DB."""
        proj = ProjectRow("大华会计师事务所", 2025)
        ctx = _make_ctx(checklist_rows=[], ref_rows=[], project_row=proj)

        result = await render(ctx)

        assert result["project_context"]["client_name"] == "大华会计师事务所"
        assert result["project_context"]["period"] == "2025年12月31日"


class TestA1731RenderStructure:
    """Response structure validation."""

    @pytest.mark.asyncio
    async def test_response_has_four_top_keys(self):
        """Response always has exactly 4 top-level keys."""
        ctx = _make_ctx(checklist_rows=[], ref_rows=[], project_row=None)

        result = await render(ctx)

        assert set(result.keys()) == {"meta_info", "sections", "a173_reference", "project_context"}

    @pytest.mark.asyncio
    async def test_meta_info_has_4_keys(self):
        """meta_info always has exactly 4 keys."""
        ctx = _make_ctx(checklist_rows=[], ref_rows=[], project_row=None)

        result = await render(ctx)

        assert len(result["meta_info"]) == 4
        assert set(result["meta_info"].keys()) == {
            "executor", "execution_date", "review_date", "reviewer"
        }

    @pytest.mark.asyncio
    async def test_sections_has_4_entries(self):
        """sections always has exactly 4 entries."""
        ctx = _make_ctx(checklist_rows=[], ref_rows=[], project_row=None)

        result = await render(ctx)

        assert len(result["sections"]) == 4
        assert set(result["sections"].keys()) == {"1", "2", "3", "4"}

    @pytest.mark.asyncio
    async def test_a173_reference_has_2_keys(self):
        """a173_reference always has exactly 2 keys."""
        ctx = _make_ctx(checklist_rows=[], ref_rows=[], project_row=None)

        result = await render(ctx)

        assert set(result["a173_reference"].keys()) == {"overview", "background"}
