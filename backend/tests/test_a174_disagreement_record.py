"""Unit tests for A17-4 重大专业分歧事项记录 render strategy.

Tests: normal flow, empty personnel, JSON failure, project context.
"""

from __future__ import annotations

import json
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.wp_render_strategies._a174_disagreement_record import render


# ─── Mock helpers ─────────────────────────────────────────────────────────────

ChecklistRow = namedtuple("ChecklistRow", ["item_id", "conclusion", "remark"])
ProjectRow = namedtuple("ProjectRow", ["client_name"])


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


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestA174RenderNormal:
    """Normal flow with saved data."""

    @pytest.mark.asyncio
    async def test_returns_personnel(self):
        """Personnel array is correctly parsed from JSON remark."""
        personnel_data = [
            {"name": "张三", "position": "审计经理", "role": "项目负责人"},
            {"name": "李四", "position": "高级审计师", "role": "现场负责人"},
        ]
        rows = [
            ChecklistRow("a174-personnel", None, json.dumps(personnel_data)),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("测试公司"))

        result = await render(ctx)

        assert result is not None
        assert len(result["personnel"]) == 2
        assert result["personnel"][0]["name"] == "张三"
        assert result["personnel"][1]["position"] == "高级审计师"

    @pytest.mark.asyncio
    async def test_returns_sections(self):
        """Section data is correctly loaded."""
        rows = [
            ChecklistRow("a174-sec1-parties", None, "分歧人员描述内容"),
            ChecklistRow("a174-sec2-cause", None, "分歧事由"),
            ChecklistRow("a174-sec3-procedures", None, "已执行程序"),
            ChecklistRow("a174-sec4-opinions", None, "监管意见"),
            ChecklistRow("a174-sec5-considerations", None, "各层级考虑"),
            ChecklistRow("a174-sec6-conclusion", None, "最终结论"),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=None)

        result = await render(ctx)

        assert result["sections"]["1"]["parties"] == "分歧人员描述内容"
        assert result["sections"]["2"]["cause"] == "分歧事由"
        assert result["sections"]["3"]["procedures"] == "已执行程序"
        assert result["sections"]["4"]["opinions"] == "监管意见"
        assert result["sections"]["5"]["considerations"] == "各层级考虑"
        assert result["sections"]["6"]["conclusion"] == "最终结论"

    @pytest.mark.asyncio
    async def test_returns_signature(self):
        """Signature data is loaded from conclusion/remark."""
        rows = [
            ChecklistRow("a174-signature-preparer", "编制人A", None),
            ChecklistRow("a174-signature-reviewer", "复核人B", None),
            ChecklistRow("a174-signature-date", "2026-06-20", None),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=None)

        result = await render(ctx)

        assert result["signature_data"]["preparer"] == "编制人A"
        assert result["signature_data"]["reviewer"] == "复核人B"
        assert result["signature_data"]["date"] == "2026-06-20"

    @pytest.mark.asyncio
    async def test_project_context_populated(self):
        """Project context is correctly populated."""
        ctx = _make_ctx(checklist_rows=[], project_row=ProjectRow("大华会计师事务所"))

        result = await render(ctx)

        assert result["project_context"]["client_name"] == "大华会计师事务所"


class TestA174RenderEmpty:
    """Empty/missing data scenarios."""

    @pytest.mark.asyncio
    async def test_empty_personnel(self):
        """No personnel remark returns empty list."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert result is not None
        assert result["personnel"] == []

    @pytest.mark.asyncio
    async def test_empty_returns_defaults(self):
        """No saved data returns empty strings for all sections."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        for sec_num in ("1", "2", "3", "4", "5", "6"):
            for val in result["sections"][sec_num].values():
                assert val == ""

    @pytest.mark.asyncio
    async def test_no_project_returns_empty_context(self):
        """Missing project returns empty context."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert result["project_context"]["client_name"] == ""
        assert result["project_context"]["current_user"] == ""


class TestA174RenderJsonFailure:
    """Personnel JSON parse failure scenarios."""

    @pytest.mark.asyncio
    async def test_invalid_json_returns_empty_personnel(self):
        """Invalid JSON in personnel remark returns empty list gracefully."""
        rows = [
            ChecklistRow("a174-personnel", None, "not valid json{["),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=None)

        result = await render(ctx)

        assert result["personnel"] == []

    @pytest.mark.asyncio
    async def test_non_list_json_returns_empty_personnel(self):
        """JSON that is not a list in personnel remark returns empty."""
        rows = [
            ChecklistRow("a174-personnel", None, '{"name": "test"}'),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=None)

        result = await render(ctx)

        assert result["personnel"] == []


class TestA174RenderStructure:
    """Response structure validation."""

    @pytest.mark.asyncio
    async def test_response_has_four_top_keys(self):
        """Response always has exactly 4 top-level keys."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert set(result.keys()) == {"personnel", "sections", "signature_data", "project_context"}

    @pytest.mark.asyncio
    async def test_sections_has_6_keys(self):
        """sections always has exactly 6 keys."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert len(result["sections"]) == 6
        assert set(result["sections"].keys()) == {"1", "2", "3", "4", "5", "6"}

    @pytest.mark.asyncio
    async def test_signature_has_3_keys(self):
        """signature_data always has exactly 3 keys."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert set(result["signature_data"].keys()) == {"preparer", "reviewer", "date"}
