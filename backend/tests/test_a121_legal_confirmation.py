"""Unit tests for A12-1 法律事务确认函 render strategy.

Tests: normal flow, empty responses, multiple litigations, A5-3 absent.
"""

from __future__ import annotations

import json
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.wp_render_strategies._a121_legal_confirmation import render


# ─── Mock helpers ─────────────────────────────────────────────────────────────

ChecklistRow = namedtuple("ChecklistRow", ["item_id", "conclusion", "remark"])
ProjectRow = namedtuple("ProjectRow", ["client_name", "audit_year"])
CrossRefRow = namedtuple("CrossRefRow", ["wp_code", "wp_id"])


def _make_ctx(
    wp_id="wp-a121",
    project_id="proj-001",
    checklist_rows=None,
    project_row=None,
    cross_ref_row=None,
):
    """Build a minimal mock RenderContext for A12-1."""
    ctx = MagicMock()
    ctx.wp_id = wp_id
    ctx.project_id = project_id

    db = AsyncMock()

    # Build sequential execute results:
    # 1st call: checklist_responses (a121-%)
    # 2nd call: project context
    # 3rd call: cross-reference wp_id (A5-3)
    cr_result = MagicMock()
    cr_result.fetchall.return_value = checklist_rows or []

    proj_result = MagicMock()
    proj_result.fetchone.return_value = project_row

    xref_result = MagicMock()
    xref_result.fetchone.return_value = cross_ref_row

    db.execute = AsyncMock(side_effect=[cr_result, proj_result, xref_result])
    ctx.db = db
    return ctx


# ─── Tests: Normal Flow ──────────────────────────────────────────────────────


class TestA121RenderNormal:
    """Normal flow with saved data."""

    @pytest.mark.asyncio
    async def test_returns_recipient_data(self):
        """Saved recipient fields are returned correctly."""
        rows = [
            ChecklistRow("a121-send-recipient-firm", "大成律师事务所", None),
            ChecklistRow("a121-send-recipient-lawyer", "张律师", None),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert result is not None
        assert result["send_section"]["recipient"]["firm_name"] == "大成律师事务所"
        assert result["send_section"]["recipient"]["lawyer_name"] == "张律师"

    @pytest.mark.asyncio
    async def test_returns_inquiry_data(self):
        """Inquiry 2 and 3 content returned correctly."""
        rows = [
            ChecklistRow("a121-send-inquiry2-content", None, "其他法律责任事件描述"),
            ChecklistRow("a121-send-inquiry3-content", None, "律师费结算情况"),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert result["send_section"]["inquiry_2"]["content"] == "其他法律责任事件描述"
        assert result["send_section"]["inquiry_3"]["content"] == "律师费结算情况"

    @pytest.mark.asyncio
    async def test_returns_sign_info(self):
        """Sign info returned correctly."""
        rows = [
            ChecklistRow("a121-send-sign-company", "测试有限公司", None),
            ChecklistRow("a121-send-sign-date", "2026-06-01", None),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert result["send_section"]["sign_info"]["company_name"] == "测试有限公司"
        assert result["send_section"]["sign_info"]["date"] == "2026-06-01"

    @pytest.mark.asyncio
    async def test_returns_reply_info_table(self):
        """Reply info table returned correctly."""
        rows = [
            ChecklistRow("a121-send-reply-address", "北京市朝阳区", None),
            ChecklistRow("a121-send-reply-phone", "010-12345678", None),
            ChecklistRow("a121-send-reply-contact", "王先生", None),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        table = result["send_section"]["reply_info_table"]
        assert table["address"] == "北京市朝阳区"
        assert table["phone"] == "010-12345678"
        assert table["contact"] == "王先生"

    @pytest.mark.asyncio
    async def test_returns_reply_section(self):
        """Reply section with litigation and fee status."""
        rows = [
            ChecklistRow("a121-reply-status", "has_litigation", None),
            ChecklistRow("a121-reply-details", None, "涉及合同纠纷一案"),
            ChecklistRow("a121-reply-fee-status", "has_outstanding", None),
            ChecklistRow("a121-reply-fee-amount", "50000.00", None),
            ChecklistRow("a121-reply-sign-firm", "大成律师事务所", None),
            ChecklistRow("a121-reply-sign-lawyer", "张律师", None),
            ChecklistRow("a121-reply-sign-date", "2026-06-15", None),
        ]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        reply = result["reply_section"]
        assert reply["litigation_status"] == "has_litigation"
        assert reply["litigation_details"] == "涉及合同纠纷一案"
        assert reply["fee_status"] == "has_outstanding"
        assert reply["outstanding_amount"] == 50000.0
        assert reply["sign"]["firm_name"] == "大成律师事务所"
        assert reply["sign"]["lawyer_name"] == "张律师"
        assert reply["sign"]["date"] == "2026-06-15"

    @pytest.mark.asyncio
    async def test_cross_reference_loaded(self):
        """A5-3 cross-reference wp_id loaded when present."""
        proj = ProjectRow("测试公司", 2025)
        xref = CrossRefRow("A5-3", "wp-a53")
        ctx = _make_ctx(checklist_rows=[], project_row=proj, cross_ref_row=xref)

        result = await render(ctx)

        assert result["cross_references"]["a5_3_wp_id"] == "wp-a53"


# ─── Tests: Empty Responses ──────────────────────────────────────────────────


class TestA121RenderEmpty:
    """Empty/missing data scenarios."""

    @pytest.mark.asyncio
    async def test_empty_responses_returns_defaults(self):
        """No saved data returns default structure."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert result is not None
        assert result["send_section"]["recipient"]["firm_name"] is None
        assert result["send_section"]["recipient"]["lawyer_name"] is None
        assert result["send_section"]["inquiry_1"]["litigation_list"] == []
        assert result["send_section"]["inquiry_2"]["content"] is None
        assert result["send_section"]["inquiry_3"]["content"] is None
        assert result["send_section"]["explanation_text"] is not None
        assert len(result["send_section"]["explanation_text"]) > 0
        assert result["send_section"]["simplified_note"] is not None

    @pytest.mark.asyncio
    async def test_project_context_auto_fill(self):
        """Project context auto-fills client_name and audit_period."""
        proj = ProjectRow("自动填充公司", 2025)
        ctx = _make_ctx(checklist_rows=[], project_row=proj)

        result = await render(ctx)

        assert result["project_context"]["client_name"] == "自动填充公司"
        assert result["project_context"]["audit_period"] == "2025年度"
        assert result["meta_info"]["client_name"] == "自动填充公司"
        assert result["meta_info"]["index_no"] == "A12-1"

    @pytest.mark.asyncio
    async def test_company_name_auto_fill_from_project(self):
        """Sign company auto-fills from project client_name when empty."""
        proj = ProjectRow("自动公司名", 2025)
        ctx = _make_ctx(checklist_rows=[], project_row=proj)

        result = await render(ctx)

        assert result["send_section"]["sign_info"]["company_name"] == "自动公司名"


# ─── Tests: Multiple Litigations ─────────────────────────────────────────────


class TestA121MultipleLitigations:
    """Litigation list parsing."""

    @pytest.mark.asyncio
    async def test_multiple_litigation_records(self):
        """Multiple litigation records parsed from JSON."""
        litigation_json = json.dumps([
            {"description": "合同纠纷案", "opinion": "败诉可能性大", "estimated_loss": 100000.0},
            {"description": "劳动争议案", "opinion": "胜诉可能性大", "estimated_loss": None},
            {"description": "知识产权案", "opinion": "结果不确定", "estimated_loss": 50000.0},
        ])
        rows = [ChecklistRow("a121-send-litigation", None, litigation_json)]
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        lit_list = result["send_section"]["inquiry_1"]["litigation_list"]
        assert len(lit_list) == 3
        assert lit_list[0]["description"] == "合同纠纷案"
        assert lit_list[0]["opinion"] == "败诉可能性大"
        assert lit_list[0]["estimated_loss"] == 100000.0
        assert lit_list[1]["description"] == "劳动争议案"
        assert lit_list[1]["estimated_loss"] is None
        assert lit_list[2]["estimated_loss"] == 50000.0

    @pytest.mark.asyncio
    async def test_invalid_json_litigation_graceful(self):
        """Invalid JSON in litigation remark does not crash."""
        rows = [ChecklistRow("a121-send-litigation", None, "not valid json{{{")]
        ctx = _make_ctx(checklist_rows=rows, project_row=None)

        result = await render(ctx)

        assert result["send_section"]["inquiry_1"]["litigation_list"] == []

    @pytest.mark.asyncio
    async def test_non_list_json_litigation(self):
        """JSON remark that is not a list is ignored."""
        rows = [ChecklistRow("a121-send-litigation", None, json.dumps({"not": "a list"}))]
        ctx = _make_ctx(checklist_rows=rows, project_row=None)

        result = await render(ctx)

        assert result["send_section"]["inquiry_1"]["litigation_list"] == []

    @pytest.mark.asyncio
    async def test_empty_litigation_list(self):
        """Empty JSON array returns empty list."""
        rows = [ChecklistRow("a121-send-litigation", None, "[]")]
        ctx = _make_ctx(checklist_rows=rows, project_row=None)

        result = await render(ctx)

        assert result["send_section"]["inquiry_1"]["litigation_list"] == []


# ─── Tests: A5-3 Absent ─────────────────────────────────────────────────────


class TestA121CrossRefAbsent:
    """A5-3 cross-reference absent."""

    @pytest.mark.asyncio
    async def test_no_cross_ref(self):
        """No A5-3 workpaper found — None."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        assert result["cross_references"]["a5_3_wp_id"] is None


# ─── Tests: Response Structure ───────────────────────────────────────────────


class TestA121RenderStructure:
    """Response structure validation."""

    @pytest.mark.asyncio
    async def test_response_has_5_top_keys(self):
        """Response always has exactly 5 top-level keys."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)

        result = await render(ctx)

        expected = {"meta_info", "send_section", "reply_section",
                    "cross_references", "project_context"}
        assert set(result.keys()) == expected

    @pytest.mark.asyncio
    async def test_fee_amount_parsing(self):
        """Outstanding amount parsed as float."""
        rows = [ChecklistRow("a121-reply-fee-amount", "12345.67", None)]
        ctx = _make_ctx(checklist_rows=rows, project_row=None)

        result = await render(ctx)

        assert result["reply_section"]["outstanding_amount"] == 12345.67

    @pytest.mark.asyncio
    async def test_invalid_fee_amount_graceful(self):
        """Invalid fee amount does not crash."""
        rows = [ChecklistRow("a121-reply-fee-amount", "not-a-number", None)]
        ctx = _make_ctx(checklist_rows=rows, project_row=None)

        result = await render(ctx)

        assert result["reply_section"]["outstanding_amount"] is None
