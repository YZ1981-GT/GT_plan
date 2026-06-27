"""A17-1 重大事项概要汇总 — Unit Tests.

Tests: render strategy (normal, empty, JSON parse failure, missing context).
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.wp_render_strategies._a171_audit_summary import (
    CHAPTERS_META,
    SIGNATURE_ROLES,
    render,
)
from app.routers.wp_render_strategies._context import RenderContext


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_ctx(
    checklist_rows=None,
    client_name="测试公司",
    audit_year=2024,
    xref_rows=None,
):
    """Create mock RenderContext."""
    db = AsyncMock()

    cr_result = MagicMock()
    cr_result.fetchall.return_value = checklist_rows or []

    proj_row = MagicMock()
    proj_row.client_name = client_name
    proj_row.audit_year = audit_year
    proj_result = MagicMock()
    proj_result.fetchone.return_value = proj_row

    xref_result = MagicMock()
    xref_result.fetchall.return_value = xref_rows or []

    db.execute = AsyncMock(side_effect=[cr_result, proj_result, xref_result])

    ctx = MagicMock(spec=RenderContext)
    ctx.wp_id = "wp-a171-001"
    ctx.db = db
    ctx.project_id = "proj-001"
    return ctx


def _row(item_id, conclusion=None, remark=None):
    r = MagicMock()
    r.item_id = item_id
    r.conclusion = conclusion
    r.remark = remark
    return r


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestRenderNormal:
    """Normal render with populated data."""

    def test_normal_render_returns_all_keys(self):
        ch6_data = [{"risk": "存货跌价", "response": "盘点", "result": "无异常", "conclusion": "已复核"}]
        ch8_data = [{"item": "营业收入", "amount": 1000000.0, "note": "同比增长10%"}]
        rows = [
            _row("a171-ch1-content", remark="审计工作概况内容"),
            _row("a171-ch6-table", remark=json.dumps(ch6_data)),
            _row("a171-ch8-table", remark=json.dumps(ch8_data)),
            _row("a171-ch9-yn", conclusion="Y", remark="发现舞弊迹象"),
            _row("a171-ch10-yn", conclusion="N", remark=None),
            _row("a171-signature-0-name", conclusion="张三"),
            _row("a171-signature-0-date", conclusion="2024-06-30"),
        ]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result is not None
        assert set(result.keys()) == {"chapters", "signature_table", "cross_references", "project_context"}

        # textarea chapter
        assert result["chapters"]["1"]["content"] == "审计工作概况内容"
        assert result["chapters"]["1"]["type"] == "textarea"

        # table chapter 6
        assert result["chapters"]["6"]["type"] == "table"
        assert len(result["chapters"]["6"]["rows"]) == 1
        assert result["chapters"]["6"]["rows"][0]["risk"] == "存货跌价"

        # table chapter 8
        assert result["chapters"]["8"]["type"] == "table"
        assert result["chapters"]["8"]["rows"][0]["amount"] == 1000000.0

        # yn chapter 9
        assert result["chapters"]["9"]["type"] == "yn"
        assert result["chapters"]["9"]["answer"] == "Y"
        assert result["chapters"]["9"]["explanation"] == "发现舞弊迹象"

        # yn chapter 10 with N
        assert result["chapters"]["10"]["answer"] == "N"
        assert result["chapters"]["10"]["explanation"] is None

        # signature
        assert result["signature_table"][0]["role"] == "编制人"
        assert result["signature_table"][0]["name"] == "张三"
        assert result["signature_table"][0]["date"] == "2024-06-30"

    def test_project_context_filled(self):
        ctx = _make_ctx(client_name="ABC有限公司", audit_year=2025)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["project_context"]["client_name"] == "ABC有限公司"
        assert result["project_context"]["audit_period"] == "2025年度"

    def test_16_chapters_all_present(self):
        ctx = _make_ctx()
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert len(result["chapters"]) == 16
        for i in range(1, 17):
            assert str(i) in result["chapters"]

    def test_chapter_types_correct(self):
        ctx = _make_ctx()
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        textarea_nums = [1, 2, 3, 4, 5, 7, 13, 14, 15, 16]
        for num in textarea_nums:
            assert result["chapters"][str(num)]["type"] == "textarea"

        for num in [6, 8]:
            assert result["chapters"][str(num)]["type"] == "table"

        for num in [9, 10, 11, 12]:
            assert result["chapters"][str(num)]["type"] == "yn"


class TestRenderEmpty:
    """Empty checklist_responses — all defaults."""

    def test_empty_returns_16_chapters(self):
        ctx = _make_ctx(checklist_rows=[])
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result is not None
        assert len(result["chapters"]) == 16

    def test_empty_textarea_chapters_have_none_content(self):
        ctx = _make_ctx(checklist_rows=[])
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        for num in [1, 2, 3, 4, 5, 7, 13, 14, 15, 16]:
            assert result["chapters"][str(num)]["content"] is None

    def test_empty_table_chapters_have_empty_rows(self):
        ctx = _make_ctx(checklist_rows=[])
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["chapters"]["6"]["rows"] == []
        assert result["chapters"]["8"]["rows"] == []

    def test_empty_yn_chapters_have_none_answer(self):
        ctx = _make_ctx(checklist_rows=[])
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        for num in [9, 10, 11, 12]:
            assert result["chapters"][str(num)]["answer"] is None
            assert result["chapters"][str(num)]["explanation"] is None

    def test_empty_signature_table_has_10_rows(self):
        ctx = _make_ctx(checklist_rows=[])
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert len(result["signature_table"]) == 10
        for i, row in enumerate(result["signature_table"]):
            assert row["role"] == SIGNATURE_ROLES[i]
            assert row["name"] is None
            assert row["date"] is None


class TestJsonParseFailure:
    """Table JSON parse failures gracefully degrade."""

    def test_invalid_json_returns_empty_rows(self):
        rows = [_row("a171-ch6-table", remark="not valid json{")]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["chapters"]["6"]["rows"] == []

    def test_non_array_json_returns_empty_rows(self):
        rows = [_row("a171-ch8-table", remark=json.dumps({"key": "value"}))]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["chapters"]["8"]["rows"] == []


class TestMissingContext:
    """Missing project context handled gracefully."""

    def test_missing_project_row(self):
        db = AsyncMock()
        cr_result = MagicMock()
        cr_result.fetchall.return_value = []
        proj_result = MagicMock()
        proj_result.fetchone.return_value = None
        xref_result = MagicMock()
        xref_result.fetchall.return_value = []
        db.execute = AsyncMock(side_effect=[cr_result, proj_result, xref_result])

        ctx = MagicMock(spec=RenderContext)
        ctx.wp_id = "wp-a171-001"
        ctx.db = db
        ctx.project_id = "proj-001"

        result = asyncio.get_event_loop().run_until_complete(render(ctx))
        assert result is not None
        assert result["project_context"]["client_name"] == ""
        assert result["project_context"]["audit_period"] == ""


class TestCrossReferences:
    """Cross-reference loading for B50, A13, A1-15."""

    def test_cross_refs_absent(self):
        ctx = _make_ctx(xref_rows=[])
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["cross_references"]["b50_wp_id"] is None
        assert result["cross_references"]["a13_wp_id"] is None
        assert result["cross_references"]["a115_wp_id"] is None

    def test_cross_refs_present(self):
        xref_rows = [
            MagicMock(wp_code="B50", wp_id="wp-b50-uuid"),
            MagicMock(wp_code="A13", wp_id="wp-a13-uuid"),
            MagicMock(wp_code="A1-15", wp_id="wp-a115-uuid"),
        ]
        ctx = _make_ctx(xref_rows=xref_rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["cross_references"]["b50_wp_id"] == "wp-b50-uuid"
        assert result["cross_references"]["a13_wp_id"] == "wp-a13-uuid"
        assert result["cross_references"]["a115_wp_id"] == "wp-a115-uuid"


class TestSignatureData:
    """Signature table data loading."""

    def test_signature_partial_fill(self):
        rows = [
            _row("a171-signature-0-name", conclusion="编制人姓名"),
            _row("a171-signature-4-name", conclusion="合伙人姓名"),
            _row("a171-signature-4-date", conclusion="2024-12-31"),
        ]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["signature_table"][0]["name"] == "编制人姓名"
        assert result["signature_table"][0]["date"] is None
        assert result["signature_table"][4]["name"] == "合伙人姓名"
        assert result["signature_table"][4]["date"] == "2024-12-31"
        # Others remain None
        assert result["signature_table"][1]["name"] is None
