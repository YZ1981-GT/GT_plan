"""Unit tests for A11-1 期后事项问询函 render strategy."""

from __future__ import annotations

from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.wp_render_strategies._a111_subsequent_events_inquiry import render

ChecklistRow = namedtuple("ChecklistRow", ["item_id", "conclusion", "remark"])
ProjectRow = namedtuple("ProjectRow", ["client_name", "balance_sheet_date"])


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


class TestA111RenderNormal:
    """正常场景：完整数据加载."""

    @pytest.mark.asyncio
    async def test_returns_meta_data(self):
        rows = [
            ChecklistRow("a111-meta-inquiry_date", "2026-03-20", ""),
            ChecklistRow("a111-meta-interviewee", None, "张三（财务总监）"),
            ChecklistRow("a111-meta-location", None, "公司会议室"),
            ChecklistRow("a111-meta-team_signature", None, "李四"),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("测试公司", "2025-12-31"))
        result = await render(ctx)

        assert result["meta_data"]["inquiry_date"] == "2026-03-20"
        assert result["meta_data"]["interviewee"] == "张三（财务总监）"
        assert result["meta_data"]["location"] == "公司会议室"
        assert result["meta_data"]["team_signature"] == "李四"

    @pytest.mark.asyncio
    async def test_returns_qa_answers(self):
        rows = [
            ChecklistRow("a111-qa-1", None, "无新增承诺"),
            ChecklistRow("a111-qa-5", None, "诉讼案件已结案"),
            ChecklistRow("a111-qa-10", None, "无其他重大事项"),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("测试公司", "2025-12-31"))
        result = await render(ctx)

        assert result["qa_list"][0]["answer"] == "无新增承诺"
        assert result["qa_list"][4]["answer"] == "诉讼案件已结案"
        assert result["qa_list"][9]["answer"] == "无其他重大事项"
        # Unanswered questions are None
        assert result["qa_list"][1]["answer"] is None
        assert result["qa_list"][2]["answer"] is None

    @pytest.mark.asyncio
    async def test_returns_evidence(self):
        rows = [
            ChecklistRow("a111-evidence-description", None, "已提供银行对账单和法律确认函"),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("测试公司", "2025-12-31"))
        result = await render(ctx)

        assert result["evidence"] == "已提供银行对账单和法律确认函"

    @pytest.mark.asyncio
    async def test_project_context(self):
        ctx = _make_ctx(checklist_rows=[], project_row=ProjectRow("深圳科技有限公司", "2025-12-31"))
        result = await render(ctx)

        assert result["project_context"]["client_name"] == "深圳科技有限公司"
        assert result["project_context"]["balance_sheet_date"] == "2025-12-31"

    @pytest.mark.asyncio
    async def test_questions_config_present(self):
        ctx = _make_ctx(checklist_rows=[], project_row=ProjectRow("测试公司", "2025-12-31"))
        result = await render(ctx)

        assert len(result["questions_config"]) == 10
        assert result["questions_config"][0]["title"] == "承诺、借款及担保"
        assert result["questions_config"][4]["has_guidance"] is True
        assert result["questions_config"][4]["guidance_text"] is not None


class TestA111RenderEmpty:
    """空数据场景."""

    @pytest.mark.asyncio
    async def test_empty_returns_defaults(self):
        ctx = _make_ctx(checklist_rows=[], project_row=None)
        result = await render(ctx)

        assert result["meta_data"]["inquiry_date"] is None
        assert result["meta_data"]["interviewee"] is None
        assert result["meta_data"]["location"] is None
        assert result["meta_data"]["team_signature"] is None
        for qa in result["qa_list"]:
            assert qa["answer"] is None
        assert result["evidence"] is None

    @pytest.mark.asyncio
    async def test_response_structure(self):
        ctx = _make_ctx(checklist_rows=[], project_row=None)
        result = await render(ctx)

        assert set(result.keys()) == {"meta_data", "qa_list", "evidence", "project_context", "questions_config"}
        assert len(result["qa_list"]) == 10
        assert len(result["questions_config"]) == 10

    @pytest.mark.asyncio
    async def test_qa_list_numbers_sequential(self):
        ctx = _make_ctx(checklist_rows=[], project_row=None)
        result = await render(ctx)

        for i, qa in enumerate(result["qa_list"]):
            assert qa["number"] == i + 1


class TestA111RenderMissingProjectContext:
    """项目上下文缺失场景."""

    @pytest.mark.asyncio
    async def test_missing_project_row(self):
        ctx = _make_ctx(checklist_rows=[], project_row=None)
        result = await render(ctx)

        assert result["project_context"]["client_name"] == ""
        assert result["project_context"]["balance_sheet_date"] is None

    @pytest.mark.asyncio
    async def test_project_with_null_fields(self):
        ctx = _make_ctx(checklist_rows=[], project_row=ProjectRow(None, None))
        result = await render(ctx)

        assert result["project_context"]["client_name"] == ""
        assert result["project_context"]["balance_sheet_date"] is None

    @pytest.mark.asyncio
    async def test_db_exception_handled_gracefully(self):
        """DB error for project context does not crash render."""
        ctx = MagicMock()
        ctx.wp_id = "wp-001"
        ctx.project_id = "proj-001"
        db = AsyncMock()
        checklist_result = MagicMock()
        checklist_result.fetchall.return_value = []
        # First call succeeds (checklist), second raises
        db.execute = AsyncMock(side_effect=[checklist_result, Exception("DB down")])
        ctx.db = db

        result = await render(ctx)

        assert result["project_context"]["client_name"] == ""
        assert result["project_context"]["balance_sheet_date"] is None
        # Rest of structure is intact
        assert len(result["qa_list"]) == 10
        assert len(result["questions_config"]) == 10
