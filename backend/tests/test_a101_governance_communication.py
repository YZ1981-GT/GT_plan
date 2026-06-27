"""A10-1 与治理层沟通函 — Unit Tests.

Tests: render strategy (normal, empty, cross-ref absent, service fees parsing).
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.wp_render_strategies._a101_governance_communication import (
    CHAPTERS_META,
    GUIDANCE_NOTES,
    SERVICE_FEE_NAMES,
    _load_cross_references,
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
    ctx.wp_id = "wp-a101-001"
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
        fees = [{"name": n, "amount": 1000.0 * (i + 1)} for i, n in enumerate(SERVICE_FEE_NAMES)]
        rows = [
            _row("a101-recipient", conclusion="XX公司董事会"),
            _row("a101-ch1-content", remark="审计范围说明"),
            _row("a101-ch3-content", remark="非审计服务说明"),
            _row("a101-fee", remark=json.dumps(fees)),
            _row("a101-sign-firm", conclusion="致同会计师事务所"),
            _row("a101-sign-partner", conclusion="李四"),
            _row("a101-sign-date", conclusion="2024-06-30"),
        ]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result is not None
        assert result["recipient"] == "XX公司董事会"
        assert result["chapters"][0]["content"] == "审计范围说明"
        assert result["chapters"][2]["content"] == "非审计服务说明"
        assert result["signing_section"]["firm_name"] == "致同会计师事务所"
        assert result["signing_section"]["partner_name"] == "李四"
        assert result["signing_section"]["date"] == "2024-06-30"
        assert result["service_fees"][0]["amount"] == 1000.0
        assert result["service_fees"][4]["amount"] == 5000.0

    def test_meta_info_has_client_and_period(self):
        ctx = _make_ctx(client_name="ABC有限公司", audit_year=2025)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["meta_info"]["client_name"] == "ABC有限公司"
        assert result["meta_info"]["audit_period"] == "2025年度"
        assert result["meta_info"]["index_no"] == "A10-1"

    def test_introduction_text_contains_period(self):
        ctx = _make_ctx(audit_year=2024)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert "2024年度" in result["introduction_text"][0]

    def test_guidance_notes_is_constant(self):
        ctx = _make_ctx()
        result = asyncio.get_event_loop().run_until_complete(render(ctx))
        assert result["guidance_notes"] == GUIDANCE_NOTES


class TestRenderEmpty:
    """Empty checklist_responses — all defaults."""

    def test_empty_returns_16_chapters_with_none_content(self):
        ctx = _make_ctx(checklist_rows=[])
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result is not None
        assert len(result["chapters"]) == 16
        for ch in result["chapters"]:
            assert ch["content"] is None

    def test_empty_returns_5_fees_with_none_amounts(self):
        ctx = _make_ctx(checklist_rows=[])
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert len(result["service_fees"]) == 5
        for fee in result["service_fees"]:
            assert fee["amount"] is None

    def test_empty_recipient_is_none(self):
        ctx = _make_ctx(checklist_rows=[])
        result = asyncio.get_event_loop().run_until_complete(render(ctx))
        assert result["recipient"] is None

    def test_empty_signing_uses_default_firm(self):
        ctx = _make_ctx(checklist_rows=[])
        result = asyncio.get_event_loop().run_until_complete(render(ctx))
        assert result["signing_section"]["firm_name"] == "致同会计师事务所（特殊普通合伙）"


class TestCrossReferences:
    """Cross-reference loading for A9-2, A13."""

    def test_cross_refs_absent(self):
        ctx = _make_ctx(xref_rows=[])
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["cross_references"]["a9_2_wp_id"] is None
        assert result["cross_references"]["a13_wp_id"] is None

    def test_cross_refs_present(self):
        xref_rows = [
            MagicMock(wp_code="A9-2", wp_id="wp-a92-uuid"),
            MagicMock(wp_code="A13", wp_id="wp-a13-uuid"),
        ]
        ctx = _make_ctx(xref_rows=xref_rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["cross_references"]["a9_2_wp_id"] == "wp-a92-uuid"
        assert result["cross_references"]["a13_wp_id"] == "wp-a13-uuid"

    def test_chapter9_has_a92_cross_ref(self):
        ctx = _make_ctx()
        result = asyncio.get_event_loop().run_until_complete(render(ctx))
        ch9 = result["chapters"][8]  # 0-indexed
        assert ch9["number"] == 9
        assert ch9["cross_ref"] == "A9-2"

    def test_chapter13_has_a13_cross_ref(self):
        ctx = _make_ctx()
        result = asyncio.get_event_loop().run_until_complete(render(ctx))
        ch13 = result["chapters"][12]
        assert ch13["number"] == 13
        assert ch13["cross_ref"] == "A13"


class TestServiceFeesParsing:
    """Service fees JSON parsing edge cases."""

    def test_partial_fees_fills_remaining_with_none(self):
        fees = [{"name": "审计服务", "amount": 5000}]
        rows = [_row("a101-fee", remark=json.dumps(fees))]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["service_fees"][0]["amount"] == 5000.0
        assert result["service_fees"][1]["amount"] is None

    def test_invalid_fee_json_returns_none_amounts(self):
        rows = [_row("a101-fee", remark="not valid json{")]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        for fee in result["service_fees"]:
            assert fee["amount"] is None

    def test_fee_with_null_amount(self):
        fees = [{"name": n, "amount": None} for n in SERVICE_FEE_NAMES]
        rows = [_row("a101-fee", remark=json.dumps(fees))]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        for fee in result["service_fees"]:
            assert fee["amount"] is None

    def test_fee_names_always_use_constants(self):
        """Even with custom names in JSON, the output uses standard names."""
        fees = [{"name": "自定义", "amount": 100}] * 5
        rows = [_row("a101-fee", remark=json.dumps(fees))]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        for i, fee in enumerate(result["service_fees"]):
            assert fee["name"] == SERVICE_FEE_NAMES[i]
