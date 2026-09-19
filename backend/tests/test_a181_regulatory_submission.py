"""Unit tests for A18-1 向监管部门报送审计小结 render strategy."""

from __future__ import annotations

from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.wp_render_strategies._a181_regulatory_submission import render

ChecklistRow = namedtuple("ChecklistRow", ["item_id", "conclusion", "remark"])
ProjectRow = namedtuple("ProjectRow", ["client_name", "audit_year"])


def _make_ctx(wp_id="wp-001", project_id="proj-001", checklist_rows=None, project_row=None):
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


class TestA181RenderNormal:
    @pytest.mark.asyncio
    async def test_returns_saved_fields(self):
        rows = [
            ChecklistRow("a181-recipient-bureau", None, "深圳市财政局"),
            ChecklistRow("a181-body-contact_person", None, "李合伙人"),
            ChecklistRow("a181-body-contact_phone", None, "0755-12345678"),
            ChecklistRow("a181-issuance-partner", None, "王签字"),
            ChecklistRow("a181-issuance-date", None, "2026-03-15"),
        ]
        proj = ProjectRow("深圳科技有限公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert result["recipient"]["bureau"] == "深圳市财政局"
        assert result["body"]["contact_person"] == "李合伙人"
        assert result["body"]["contact_phone"] == "0755-12345678"
        assert result["issuance"]["partner"] == "王签字"
        assert result["issuance"]["date"] == "2026-03-15"

    @pytest.mark.asyncio
    async def test_project_context(self):
        proj = ProjectRow("广州制造有限公司", 2024)
        ctx = _make_ctx(checklist_rows=[], project_row=proj)

        result = await render(ctx)

        assert result["project_context"]["client_name"] == "广州制造有限公司"
        assert result["project_context"]["audit_year"] == "2024"
        assert result["project_context"]["firm_name"] == "致同会计师事务所（特殊普通合伙）"


class TestA181RenderEmpty:
    @pytest.mark.asyncio
    async def test_empty_returns_defaults(self):
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert result["recipient"]["bureau"] == ""
        assert result["body"]["contact_person"] == ""
        assert result["issuance"]["partner"] == ""
        assert result["project_context"]["client_name"] == ""

    @pytest.mark.asyncio
    async def test_response_structure(self):
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert set(result.keys()) == {"recipient", "body", "issuance", "project_context"}
        assert len(result["recipient"]) == 1
        assert len(result["body"]) == 2
        assert len(result["issuance"]) == 2
        assert len(result["project_context"]) == 4
