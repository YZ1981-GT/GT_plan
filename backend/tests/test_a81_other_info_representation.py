"""Unit tests for A8-1 管理层对其他信息的书面声明 render strategy."""

from __future__ import annotations

from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.wp_render_strategies._a81_other_info_representation import render

ChecklistRow = namedtuple("ChecklistRow", ["item_id", "conclusion", "remark"])
ProjectRow = namedtuple("ProjectRow", ["client_name", "audit_report_date"])


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


class TestA81RenderNormal:
    """正常场景：完整数据加载."""

    @pytest.mark.asyncio
    async def test_returns_file_lists(self):
        rows = [
            ChecklistRow("a81-statement-1-files", "3", '["董事会报告","监事会报告","财务报告"]'),
            ChecklistRow("a81-statement-4-files", "2", '["审计报告","管理层声明书"]'),
            ChecklistRow("a81-statement-5-files", "1", '["补充说明"]'),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("测试公司", "2026-03-31"))
        result = await render(ctx)

        assert result["statements"]["1"]["files"] == ["董事会报告", "监事会报告", "财务报告"]
        assert result["statements"]["4"]["files"] == ["审计报告", "管理层声明书"]
        assert result["statements"]["5"]["files"] == ["补充说明"]

    @pytest.mark.asyncio
    async def test_returns_date(self):
        rows = [
            ChecklistRow("a81-statement-2-date", "2026-04-30", ""),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("测试公司", "2026-03-31"))
        result = await render(ctx)

        assert result["statements"]["2"]["date"] == "2026-04-30"

    @pytest.mark.asyncio
    async def test_returns_consistency_y(self):
        rows = [
            ChecklistRow("a81-statement-3-consistency", "Y", ""),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("测试公司", "2026-03-31"))
        result = await render(ctx)

        assert result["statements"]["3"]["consistency"] == "Y"

    @pytest.mark.asyncio
    async def test_returns_consistency_n_with_explanation(self):
        rows = [
            ChecklistRow("a81-statement-3-consistency", "N", ""),
            ChecklistRow("a81-statement-3-explanation", None, "存在不一致事项说明"),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("测试公司", "2026-03-31"))
        result = await render(ctx)

        assert result["statements"]["3"]["consistency"] == "N"
        assert result["statements"]["3"]["explanation"] == "存在不一致事项说明"

    @pytest.mark.asyncio
    async def test_returns_other_text(self):
        rows = [
            ChecklistRow("a81-statement-6-other", None, "其他补充说明内容"),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("测试公司", "2026-03-31"))
        result = await render(ctx)

        assert result["statements"]["6"]["other"] == "其他补充说明内容"

    @pytest.mark.asyncio
    async def test_returns_signature_data(self):
        rows = [
            ChecklistRow("a81-signature-representative", None, "张三"),
            ChecklistRow("a81-signature-date", None, "2026-03-31"),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("测试公司", "2026-03-31"))
        result = await render(ctx)

        assert result["signature_data"]["representative"] == "张三"
        assert result["signature_data"]["signature_date"] == "2026-03-31"

    @pytest.mark.asyncio
    async def test_project_context(self):
        ctx = _make_ctx(checklist_rows=[], project_row=ProjectRow("深圳科技有限公司", "2026-03-31"))
        result = await render(ctx)

        assert result["project_context"]["client_name"] == "深圳科技有限公司"
        assert result["project_context"]["audit_report_date"] == "2026-03-31"


class TestA81RenderEmpty:
    """空数据场景."""

    @pytest.mark.asyncio
    async def test_empty_returns_defaults(self):
        ctx = _make_ctx(checklist_rows=[], project_row=None)
        result = await render(ctx)

        assert result["statements"]["1"]["files"] == []
        assert result["statements"]["2"]["date"] is None
        assert result["statements"]["3"]["consistency"] is None
        assert result["statements"]["3"]["explanation"] is None
        assert result["statements"]["4"]["files"] == []
        assert result["statements"]["5"]["files"] == []
        assert result["statements"]["6"]["other"] is None
        assert result["signature_data"]["representative"] is None
        assert result["signature_data"]["signature_date"] is None

    @pytest.mark.asyncio
    async def test_response_structure(self):
        ctx = _make_ctx(checklist_rows=[], project_row=None)
        result = await render(ctx)

        assert set(result.keys()) == {"statements", "signature_data", "project_context"}
        assert set(result["statements"].keys()) == {"1", "2", "3", "4", "5", "6"}
        assert set(result["signature_data"].keys()) == {"representative", "signature_date"}
        assert set(result["project_context"].keys()) == {"client_name", "audit_report_date", "cpa_names"}

    @pytest.mark.asyncio
    async def test_project_context_defaults(self):
        ctx = _make_ctx(checklist_rows=[], project_row=None)
        result = await render(ctx)

        assert result["project_context"]["client_name"] == ""
        assert result["project_context"]["audit_report_date"] is None
        assert result["project_context"]["cpa_names"] == []


class TestA81RenderJsonFailure:
    """JSON 解析失败场景."""

    @pytest.mark.asyncio
    async def test_invalid_json_in_file_list_returns_empty(self):
        rows = [
            ChecklistRow("a81-statement-1-files", None, "not valid json"),
            ChecklistRow("a81-statement-4-files", None, "{invalid}"),
            ChecklistRow("a81-statement-5-files", None, ""),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("测试公司", "2026-03-31"))
        result = await render(ctx)

        assert result["statements"]["1"]["files"] == []
        assert result["statements"]["4"]["files"] == []
        assert result["statements"]["5"]["files"] == []

    @pytest.mark.asyncio
    async def test_non_array_json_returns_empty(self):
        rows = [
            ChecklistRow("a81-statement-1-files", None, '{"key": "value"}'),
        ]
        ctx = _make_ctx(checklist_rows=rows, project_row=ProjectRow("测试公司", "2026-03-31"))
        result = await render(ctx)

        assert result["statements"]["1"]["files"] == []


class TestA81RenderMissingProjectContext:
    """项目上下文缺失场景."""

    @pytest.mark.asyncio
    async def test_missing_project_row(self):
        ctx = _make_ctx(checklist_rows=[], project_row=None)
        result = await render(ctx)

        assert result["project_context"]["client_name"] == ""
        assert result["project_context"]["audit_report_date"] is None

    @pytest.mark.asyncio
    async def test_project_with_null_fields(self):
        ctx = _make_ctx(checklist_rows=[], project_row=ProjectRow(None, None))
        result = await render(ctx)

        assert result["project_context"]["client_name"] == ""
        assert result["project_context"]["audit_report_date"] is None
