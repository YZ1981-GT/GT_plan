"""Unit tests for A27-1 IT审计总结备忘录 render strategy.

Tests: normal flow, empty responses, partial cross-refs absent, team JSON parsing.
"""

from __future__ import annotations

import json
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.wp_render_strategies._a271_it_audit_memo import render


# ─── Mock helpers ─────────────────────────────────────────────────────────────

ChecklistRow = namedtuple("ChecklistRow", ["item_id", "conclusion", "remark"])
ProjectRow = namedtuple("ProjectRow", ["client_name", "audit_year"])
CrossRefRow = namedtuple("CrossRefRow", ["wp_code", "wp_id"])


def _make_ctx(
    wp_id="wp-a271",
    project_id="proj-001",
    checklist_rows=None,
    project_row=None,
    cross_ref_rows=None,
):
    """Build a minimal mock RenderContext for A27-1."""
    ctx = MagicMock()
    ctx.wp_id = wp_id
    ctx.project_id = project_id

    db = AsyncMock()

    # Build sequential execute results:
    # 1st call: checklist_responses (a271-%)
    # 2nd call: project context
    # 3rd call: cross-reference wp_ids
    cr_result = MagicMock()
    cr_result.fetchall.return_value = checklist_rows or []

    proj_result = MagicMock()
    proj_result.fetchone.return_value = project_row

    xref_result = MagicMock()
    xref_result.fetchall.return_value = cross_ref_rows or []

    db.execute = AsyncMock(side_effect=[cr_result, proj_result, xref_result])
    ctx.db = db
    return ctx


# ─── Tests: Normal Flow ──────────────────────────────────────────────────────


class TestA271RenderNormal:
    """Normal flow with saved data."""

    @pytest.mark.asyncio
    async def test_returns_header_data(self):
        """Saved header fields are returned correctly."""
        rows = [
            ChecklistRow("a271-header-date", "2026-06-01", None),
            ChecklistRow("a271-header-to", "信息技术部", None),
            ChecklistRow("a271-header-from", "审计项目组", None),
            ChecklistRow("a271-header-subject", "IT审计总结备忘录", None),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert result is not None
        assert result["header"]["date"] == "2026-06-01"
        assert result["header"]["to"] == "信息技术部"
        assert result["header"]["from_user"] == "审计项目组"
        assert result["header"]["subject"] == "IT审计总结备忘录"

    @pytest.mark.asyncio
    async def test_returns_chapter_data(self):
        """Chapter content and conclusions returned correctly."""
        rows = [
            ChecklistRow("a271-ch1-content", None, "公司使用SAP ERP系统"),
            ChecklistRow("a271-ch2-content", None, "IT风险评估结果"),
            ChecklistRow("a271-ch3-conclusion", "部分有效", None),
            ChecklistRow("a271-ch3-deficiency", None, "密码策略不完善"),
            ChecklistRow("a271-ch4-content", None, "详细缺陷描述"),
            ChecklistRow("a271-ch5-content", None, "信息处理控制测试"),
            ChecklistRow("a271-ch6-conclusion", "已有效", None),
            ChecklistRow("a271-ch7-content", None, "整体评估内容"),
            ChecklistRow("a271-ch7-conclusion", "存在一般缺陷", None),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        chapters = result["chapters"]
        assert len(chapters) == 7
        assert chapters[0]["content"] == "公司使用SAP ERP系统"
        assert chapters[1]["content"] == "IT风险评估结果"
        assert chapters[2]["conclusion"] == "部分有效"
        assert chapters[2]["deficiency"] == "密码策略不完善"
        assert chapters[3]["content"] == "详细缺陷描述"
        assert chapters[4]["content"] == "信息处理控制测试"
        assert chapters[5]["conclusion"] == "已有效"
        assert chapters[6]["content"] == "整体评估内容"
        assert chapters[6]["conclusion"] == "存在一般缺陷"

    @pytest.mark.asyncio
    async def test_returns_team_data(self):
        """Team table parsed from JSON remark."""
        team_json = json.dumps([
            {"name": "张三", "title": "IT审计经理"},
            {"name": "李四", "title": "IT审计助理"},
        ])
        rows = [ChecklistRow("a271-team", "2", team_json)]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        table = result["it_team_table"]
        assert len(table) == 2
        assert table[0]["index"] == 1
        assert table[0]["name"] == "张三"
        assert table[0]["title"] == "IT审计经理"
        assert table[1]["index"] == 2
        assert table[1]["name"] == "李四"
        assert table[1]["title"] == "IT审计助理"

    @pytest.mark.asyncio
    async def test_cross_references_loaded(self):
        """Cross-reference wp_ids loaded when present."""
        proj = ProjectRow("测试公司", 2025)
        xrefs = [
            CrossRefRow("B22A-4-3", "wp-b22a43"),
            CrossRefRow("C22", "wp-c22"),
            CrossRefRow("C21-1", "wp-c211"),
            CrossRefRow("B23-15", "wp-b2315"),
        ]
        ctx = _make_ctx(checklist_rows=[], project_row=proj, cross_ref_rows=xrefs)

        result = await render(ctx)

        cr = result["cross_references"]
        assert cr["b22a_4_3_wp_id"] == "wp-b22a43"
        assert cr["c22_wp_id"] == "wp-c22"
        assert cr["c21_1_wp_id"] == "wp-c211"
        assert cr["b23_15_wp_id"] == "wp-b2315"


# ─── Tests: Empty Responses ──────────────────────────────────────────────────


class TestA271RenderEmpty:
    """Empty/missing data scenarios."""

    @pytest.mark.asyncio
    async def test_empty_responses_returns_defaults(self):
        """No saved data returns default structure."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert result is not None
        assert result["header"]["date"] is None
        assert result["header"]["to"] is None
        assert result["header"]["from_user"] is None
        assert result["header"]["subject"] == "IT审计总结"  # default
        assert result["it_team_table"] == []
        assert len(result["chapters"]) == 7
        assert result["purpose_text"] is not None and len(result["purpose_text"]) > 0

    @pytest.mark.asyncio
    async def test_project_context_auto_fill(self):
        """Project context auto-fills client_name and audit_period."""
        proj = ProjectRow("自动填充公司", 2025)
        ctx = _make_ctx(checklist_rows=[], project_row=proj)

        result = await render(ctx)

        assert result["project_context"]["client_name"] == "自动填充公司"
        assert result["project_context"]["audit_period"] == "2025年度"
        assert result["meta_info"]["client_name"] == "自动填充公司"
        assert result["meta_info"]["index_no"] == "A27-1"


# ─── Tests: Partial Cross-Refs Absent ────────────────────────────────────────


class TestA271RenderPartialCrossRefs:
    """Some cross-reference workpapers absent."""

    @pytest.mark.asyncio
    async def test_partial_cross_refs(self):
        """Only some cross-ref workpapers exist."""
        proj = ProjectRow("测试公司", 2025)
        xrefs = [
            CrossRefRow("B22A-4-3", "wp-b22a43"),
            CrossRefRow("C22", "wp-c22"),
            # C21-1 and B23-15 absent
        ]
        ctx = _make_ctx(checklist_rows=[], project_row=proj, cross_ref_rows=xrefs)

        result = await render(ctx)

        cr = result["cross_references"]
        assert cr["b22a_4_3_wp_id"] == "wp-b22a43"
        assert cr["c22_wp_id"] == "wp-c22"
        assert cr["c21_1_wp_id"] is None
        assert cr["b23_15_wp_id"] is None

    @pytest.mark.asyncio
    async def test_no_cross_refs(self):
        """No cross-ref workpapers found — all None."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        cr = result["cross_references"]
        assert cr["b22a_4_3_wp_id"] is None
        assert cr["c22_wp_id"] is None
        assert cr["c21_1_wp_id"] is None
        assert cr["b23_15_wp_id"] is None


# ─── Tests: Team JSON Parsing ────────────────────────────────────────────────


class TestA271TeamJsonParsing:
    """IT team table JSON parsing edge cases."""

    @pytest.mark.asyncio
    async def test_invalid_json_team_graceful(self):
        """Invalid JSON in team remark does not crash."""
        rows = [ChecklistRow("a271-team", "1", "not valid json{{{")]
        ctx = _make_ctx(checklist_rows=rows, project_row=None)

        result = await render(ctx)

        assert result["it_team_table"] == []

    @pytest.mark.asyncio
    async def test_non_list_json_team(self):
        """JSON remark that is not a list is ignored."""
        rows = [ChecklistRow("a271-team", "1", json.dumps({"not": "a list"}))]
        ctx = _make_ctx(checklist_rows=rows, project_row=None)

        result = await render(ctx)

        assert result["it_team_table"] == []

    @pytest.mark.asyncio
    async def test_partial_team_items(self):
        """Team items with missing fields still parse with defaults."""
        team_json = json.dumps([{"name": "王五"}])  # Missing title
        rows = [ChecklistRow("a271-team", "1", team_json)]
        ctx = _make_ctx(checklist_rows=rows, project_row=None)

        result = await render(ctx)

        assert len(result["it_team_table"]) == 1
        assert result["it_team_table"][0]["name"] == "王五"
        assert result["it_team_table"][0]["title"] is None


# ─── Tests: Response Structure ───────────────────────────────────────────────


class TestA271RenderStructure:
    """Response structure validation."""

    @pytest.mark.asyncio
    async def test_response_has_7_top_keys(self):
        """Response always has exactly 7 top-level keys."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        expected = {"meta_info", "header", "purpose_text", "it_team_table",
                    "chapters", "cross_references", "project_context"}
        assert set(result.keys()) == expected

    @pytest.mark.asyncio
    async def test_chapters_always_7(self):
        """chapters array always has 7 entries."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert len(result["chapters"]) == 7
        for i, ch in enumerate(result["chapters"]):
            assert ch["number"] == i + 1
            assert "title" in ch
            assert "content" in ch
            assert "conclusion" in ch
            assert "deficiency" in ch
            assert "cross_ref" in ch
