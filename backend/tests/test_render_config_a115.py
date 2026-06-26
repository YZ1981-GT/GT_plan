"""Integration tests — A1-15 render-config 返回结构验证.

Spec: .kiro/specs/a1-15-disclosure-checklist/
Task: 9.1

Tests the render function directly (no live database or API server).
Mocks database queries and verifies render output structure.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.wp_render_strategies._a115_disclosure import (
    CROSS_REFERENCE_MAP,
    format_a115_to_summary,
    render,
)

# ─── Mock template data (simplified) ─────────────────────────────────────────

MOCK_TEMPLATE = {
    "wp_code": "A1-15",
    "title": "企业会计准则有关财务报表列报及披露核对表",
    "sections": [
        {
            "id": "S01",
            "title": "一般列报要求",
            "items": [
                {
                    "id": "S01-001",
                    "type": "actionable",
                    "standard_ref": "CAS30.5",
                    "content": "财务报表应当按照规定列报",
                    "children": [],
                },
                {
                    "id": "S01-002",
                    "type": "header",
                    "standard_ref": "",
                    "content": "小节：一般原则",
                    "children": [],
                },
            ],
        },
        {
            "id": "S02",
            "title": "货币资金",
            "items": [
                {
                    "id": "S02-001",
                    "type": "actionable",
                    "standard_ref": "CAS31.8",
                    "content": "货币资金应当按照实际收到或支付的金额入账",
                    "children": [
                        {"id": "S02-001-a", "content": "详细披露要求", "standard_ref": "CAS31.8a"},
                    ],
                },
            ],
        },
    ],
    "toc": [
        {"id": "S01", "title": "一般列报要求", "applicable": True},
        {"id": "S02", "title": "货币资金", "applicable": True},
    ],
    "stats": {"total_actionable": 2, "total_guidance": 1, "total_sections": 2},
    "parsed_at": "2026-01-01T00:00:00",
}


# ─── Mock RenderContext fixture ───────────────────────────────────────────────

@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.wp_id = "wp-test-001"
    ctx.project_id = "proj-test"
    ctx.year = 2026
    ctx.db = AsyncMock()
    # Mock db.execute to return empty results
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    ctx.db.execute = AsyncMock(return_value=mock_result)
    return ctx


# ─── Test 1: render returns None when template not found ─────────────────────

@pytest.mark.asyncio
async def test_render_returns_none_when_template_not_found(mock_ctx):
    """When get_checklist_template raises FileNotFoundError, render returns None."""
    with patch(
        "app.services.checklist_docx_parser.get_checklist_template",
        new_callable=AsyncMock,
        side_effect=FileNotFoundError("A1-15 template not found"),
    ), patch(
        "app.services.field_override_service.FieldOverrideService.get_batch",
        new_callable=AsyncMock,
        return_value={},
    ):
        result = await render(mock_ctx)

    assert result is None


# ─── Test 2: render returns correct structure ─────────────────────────────────

@pytest.mark.asyncio
async def test_render_returns_correct_structure(mock_ctx):
    """When template exists, verify response has template/responses/cross_reference_map with correct types."""
    with patch(
        "app.services.checklist_docx_parser.get_checklist_template",
        new_callable=AsyncMock,
        return_value=MOCK_TEMPLATE,
    ), patch(
        "app.services.field_override_service.FieldOverrideService.get_batch",
        new_callable=AsyncMock,
        return_value={},
    ):
        result = await render(mock_ctx)

    assert result is not None
    # Top-level keys
    assert "template" in result
    assert "responses" in result
    assert "cross_reference_map" in result

    # Type checks
    assert isinstance(result["template"], dict)
    assert isinstance(result["responses"], dict)
    assert isinstance(result["cross_reference_map"], dict)

    # Template structure
    template = result["template"]
    assert template["wp_code"] == "A1-15"
    assert "title" in template
    assert "sections" in template
    assert "toc" in template
    assert "stats" in template
    assert isinstance(template["sections"], list)
    assert isinstance(template["toc"], list)
    assert isinstance(template["stats"], dict)


# ─── Test 3: CROSS_REFERENCE_MAP has required entries ─────────────────────────

def test_render_cross_reference_map_has_required_entries():
    """Verify CROSS_REFERENCE_MAP has ≥10 entries and contains D0, D1, D2, E1, G1, H1, I1, F1, F2, K1."""
    assert len(CROSS_REFERENCE_MAP) >= 10

    # Required wp_code values must exist in the map values
    required_wp_codes = {"D0", "D1", "D2", "E1", "G1", "H1", "I1", "F1", "F2", "K1"}
    actual_wp_codes = set(CROSS_REFERENCE_MAP.values())
    assert required_wp_codes.issubset(actual_wp_codes), (
        f"Missing wp_codes: {required_wp_codes - actual_wp_codes}"
    )


# ─── Test 4: responses structure ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_render_responses_structure(mock_ctx):
    """Verify responses.items is dict, responses.toc_applicability is dict."""
    with patch(
        "app.services.checklist_docx_parser.get_checklist_template",
        new_callable=AsyncMock,
        return_value=MOCK_TEMPLATE,
    ), patch(
        "app.services.field_override_service.FieldOverrideService.get_batch",
        new_callable=AsyncMock,
        return_value={},
    ):
        result = await render(mock_ctx)

    assert result is not None
    responses = result["responses"]

    assert "items" in responses
    assert "toc_applicability" in responses
    assert isinstance(responses["items"], dict)
    assert isinstance(responses["toc_applicability"], dict)


# ─── Test 5: format_a115_to_summary basic ─────────────────────────────────────

def test_format_a115_to_summary_basic():
    """Test format_a115_to_summary with a simple template produces expected output format."""
    summary = format_a115_to_summary(MOCK_TEMPLATE)

    # Should be a non-empty string
    assert isinstance(summary, str)
    assert len(summary) > 0

    # Should contain the title
    assert "企业会计准则有关财务报表列报及披露核对表" in summary

    # Should contain section IDs and titles
    assert "S01" in summary
    assert "一般列报要求" in summary
    assert "S02" in summary
    assert "货币资金" in summary

    # Should contain actionable counts per section
    # S01 has 1 actionable, S02 has 1 actionable
    assert "1 actionable" in summary

    # Should contain total stats
    assert "2 章节" in summary
    assert "2 actionable" in summary
    assert "1 guidance" in summary
