"""Unit tests for A18-2 与监管层沟通函 render strategy."""

from __future__ import annotations

from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.wp_render_strategies._a182_regulatory_communication import render

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


class TestA182RenderNormal:
    """正常场景：完整数据加载."""

    @pytest.mark.asyncio
    async def test_returns_saved_recipient(self):
        rows = [
            ChecklistRow("a182-recipient-authority", None, "中国证券监督管理委员会"),
            ChecklistRow("a182-recipient-custom", None, ""),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("测试公司", 2025))
        result = await render(ctx)

        assert result["recipient"]["authority"] == "中国证券监督管理委员会"
        assert result["recipient"]["custom"] == ""

    @pytest.mark.asyncio
    async def test_returns_saved_matters(self):
        rows = [
            ChecklistRow("a182-matter1-applicability", None, "Y"),
            ChecklistRow("a182-matter1-content", None, "发现重大舞弊事项"),
            ChecklistRow("a182-matter2-applicability", None, "N"),
            ChecklistRow("a182-matter3-applicability", None, "NA"),
            ChecklistRow("a182-matter4-applicability", None, "Y"),
            ChecklistRow("a182-matter4-content", None, "其他需要沟通事项"),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("测试公司", 2025))
        result = await render(ctx)

        assert result["matters"][0]["applicability"] == "Y"
        assert result["matters"][0]["content"] == "发现重大舞弊事项"
        assert result["matters"][1]["applicability"] == "N"
        assert result["matters"][2]["applicability"] == "NA"
        assert result["matters"][3]["applicability"] == "Y"
        assert result["matters"][3]["content"] == "其他需要沟通事项"

    @pytest.mark.asyncio
    async def test_returns_saved_issuance(self):
        rows = [
            ChecklistRow("a182-sign-cpa1", None, "张三"),
            ChecklistRow("a182-sign-cpa2", None, "李四"),
            ChecklistRow("a182-sign-date", None, "2026-03-15"),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("测试公司", 2025))
        result = await render(ctx)

        assert result["issuance"]["cpa1"] == "张三"
        assert result["issuance"]["cpa2"] == "李四"
        assert result["issuance"]["date"] == "2026-03-15"

    @pytest.mark.asyncio
    async def test_project_context(self):
        ctx = _make_ctx(checklist_rows=[], project_row=ProjectRow("深圳科技有限公司", 2024))
        result = await render(ctx)

        assert result["project_context"]["client_name"] == "深圳科技有限公司"
        assert result["project_context"]["audit_year"] == "2024"
        assert result["project_context"]["firm_name"] == "致同会计师事务所（特殊普通合伙）"


class TestA182RenderEmpty:
    """空数据场景."""

    @pytest.mark.asyncio
    async def test_empty_returns_defaults(self):
        ctx = _make_ctx(checklist_rows=[], project_row=None)
        result = await render(ctx)

        assert result["recipient"]["authority"] == ""
        assert result["recipient"]["custom"] == ""
        assert all(m["applicability"] is None for m in result["matters"])
        assert all(m["content"] == "" for m in result["matters"])
        assert result["issuance"]["cpa1"] == ""
        assert result["issuance"]["cpa2"] == ""
        assert result["issuance"]["date"] == ""

    @pytest.mark.asyncio
    async def test_response_structure(self):
        ctx = _make_ctx(checklist_rows=[], project_row=None)
        result = await render(ctx)

        assert set(result.keys()) == {"recipient", "matters", "issuance", "project_context"}
        assert len(result["recipient"]) == 2
        assert len(result["matters"]) == 4
        for matter in result["matters"]:
            assert set(matter.keys()) == {"id", "title", "applicability", "content"}
        assert len(result["issuance"]) == 3
        assert len(result["project_context"]) == 3

    @pytest.mark.asyncio
    async def test_matter_titles_and_ids(self):
        ctx = _make_ctx(checklist_rows=[], project_row=None)
        result = await render(ctx)

        assert result["matters"][0]["id"] == 1
        assert result["matters"][0]["title"] == "舞弊"
        assert result["matters"][1]["id"] == 2
        assert result["matters"][1]["title"] == "重大违反法律法规行为"
        assert result["matters"][2]["id"] == 3
        assert result["matters"][2]["title"] == "年度报告中信息不一致或错报"
        assert result["matters"][3]["id"] == 4
        assert result["matters"][3]["title"] == "其他事项"


class TestA182RenderPartialApplicability:
    """部分适用性场景."""

    @pytest.mark.asyncio
    async def test_partial_matters_filled(self):
        rows = [
            ChecklistRow("a182-matter1-applicability", None, "Y"),
            ChecklistRow("a182-matter1-content", None, "内容1"),
            # matter2-4 未填写
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("部分公司", 2025))
        result = await render(ctx)

        assert result["matters"][0]["applicability"] == "Y"
        assert result["matters"][0]["content"] == "内容1"
        assert result["matters"][1]["applicability"] is None
        assert result["matters"][1]["content"] == ""
        assert result["matters"][2]["applicability"] is None
        assert result["matters"][3]["applicability"] is None

    @pytest.mark.asyncio
    async def test_custom_recipient(self):
        rows = [
            ChecklistRow("a182-recipient-authority", None, "其他"),
            ChecklistRow("a182-recipient-custom", None, "某省财政厅"),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("自定义公司", 2025))
        result = await render(ctx)

        assert result["recipient"]["authority"] == "其他"
        assert result["recipient"]["custom"] == "某省财政厅"
