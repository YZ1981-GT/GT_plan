"""Integration test for A1-12 dual-mode checklist render strategy.

Validates: Requirements 6.1, 6.2, 6.3, 6.4
Verifies that render_a112_dual returns valid A112ChecklistData structure
when called with a mock RenderContext pointing to the real template.

Tests the render function directly — no running server required.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── 模板路径 ────────────────────────────────────────────────────────────────

_TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "wp_templates"
    / "A"
    / "A1-12 重大事项决定程序的履行情况核查表1105.docx"
)


@pytest.mark.asyncio
async def test_render_a112_dual_returns_valid_structure():
    """render() 返回 {checklistData, responses} 结构，checklistData 完整."""
    from app.routers.wp_render_strategies._a112_dual import render
    from app.routers.wp_render_strategies._context import RenderContext

    # ─── Mock RenderContext ──────────────────────────────────────────────
    mock_db = AsyncMock()
    mock_wp = MagicMock()
    mock_classification = MagicMock()

    ctx = RenderContext(
        db=mock_db,
        project_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        wp_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        wp_code="A1-12",
        working_paper=mock_wp,
        classification=mock_classification,
        component_type="a1-12-dual-checklist",
        sheet_html_data=None,
        sheet_schema=None,
        template_file_path=str(_TEMPLATE),
        year=2026,
        business_category="A",
    )

    # Mock FieldOverrideService.get_batch to return empty (no user responses)
    with patch(
        "app.services.field_override_service.FieldOverrideService.get_batch",
        new_callable=AsyncMock,
        return_value={},
    ):
        result = await render(ctx)

    # ─── 验证顶层结构 ────────────────────────────────────────────────────
    assert result is not None
    assert "checklistData" in result
    assert "responses" in result

    # ─── 验证 checklistData ──────────────────────────────────────────────
    checklist = result["checklistData"]
    assert "header" in checklist
    assert "categories" in checklist
    assert "signatures" in checklist

    # 2 categories
    assert len(checklist["categories"]) == 2

    # cat-1 有 14 items
    cat1 = checklist["categories"][0]
    assert cat1["id"] == "cat-1"
    assert len(cat1["items"]) == 14

    # cat-2 allow_custom
    cat2 = checklist["categories"][1]
    assert cat2["id"] == "cat-2"
    assert cat2["allow_custom"] is True

    # All items have unique IDs
    all_ids = [item["id"] for cat in checklist["categories"] for item in cat["items"]]
    assert len(all_ids) == len(set(all_ids))

    # All items have non-empty descriptions
    for cat in checklist["categories"]:
        for item in cat["items"]:
            assert item["description"].strip()

    # Signatures: 4 roles
    assert len(checklist["signatures"]) == 4

    # ─── 验证 responses 结构 ─────────────────────────────────────────────
    responses = result["responses"]
    assert "items" in responses
    assert "header" in responses
    assert "custom_items" in responses
    assert isinstance(responses["items"], dict)
    assert isinstance(responses["header"], dict)
    assert isinstance(responses["custom_items"], list)


@pytest.mark.asyncio
async def test_render_a112_dual_merges_field_overrides():
    """render() 正确合并 field_overrides 中的用户 responses."""
    from app.routers.wp_render_strategies._a112_dual import render
    from app.routers.wp_render_strategies._context import RenderContext

    mock_db = AsyncMock()
    mock_wp = MagicMock()
    mock_classification = MagicMock()

    ctx = RenderContext(
        db=mock_db,
        project_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        wp_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        wp_code="A1-12",
        working_paper=mock_wp,
        classification=mock_classification,
        component_type="a1-12-dual-checklist",
        sheet_html_data=None,
        sheet_schema=None,
        template_file_path=str(_TEMPLATE),
        year=2026,
        business_category="A",
    )

    # Simulate field_overrides with user data
    mock_overrides = {
        "item-1": {"applicable": "yes", "ref_index": "A17-3"},
        "item-5": {"applicable": "no", "ref_index": ""},
        "header": {"business_class": "A", "is_first_engagement": True},
        "custom_items": {"value": [{"id": "custom-1", "description": "自定义事项", "applicable": "yes", "ref_index": "B50-1"}]},
    }

    with patch(
        "app.services.field_override_service.FieldOverrideService.get_batch",
        new_callable=AsyncMock,
        return_value=mock_overrides,
    ):
        result = await render(ctx)

    responses = result["responses"]

    # item-1 response merged
    assert "item-1" in responses["items"]
    assert responses["items"]["item-1"]["applicable"] == "yes"
    assert responses["items"]["item-1"]["ref_index"] == "A17-3"

    # item-5 response merged
    assert "item-5" in responses["items"]
    assert responses["items"]["item-5"]["applicable"] == "no"

    # header merged
    assert responses["header"]["business_class"] == "A"
    assert responses["header"]["is_first_engagement"] is True

    # custom_items merged
    assert len(responses["custom_items"]) == 1
    assert responses["custom_items"][0]["id"] == "custom-1"


@pytest.mark.asyncio
async def test_render_a112_dual_graceful_on_missing_template():
    """模板文件不存在时 render() 返回空结构不崩溃."""
    from app.routers.wp_render_strategies._a112_dual import render
    from app.routers.wp_render_strategies._context import RenderContext

    mock_db = AsyncMock()
    mock_wp = MagicMock()
    mock_classification = MagicMock()

    ctx = RenderContext(
        db=mock_db,
        project_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        wp_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        wp_code="A1-12",
        working_paper=mock_wp,
        classification=mock_classification,
        component_type="a1-12-dual-checklist",
        sheet_html_data=None,
        sheet_schema=None,
        template_file_path="/nonexistent/path.docx",
        year=2026,
        business_category="A",
    )

    with patch(
        "app.services.field_override_service.FieldOverrideService.get_batch",
        new_callable=AsyncMock,
        return_value={},
    ):
        result = await render(ctx)

    # Should still return valid structure, just with empty categories
    assert result is not None
    assert "checklistData" in result
    assert "responses" in result
    assert result["checklistData"]["categories"] == []
    assert len(result["checklistData"]["signatures"]) == 4


@pytest.mark.asyncio
async def test_render_a112_dual_handles_field_override_failure():
    """field_overrides 查询失败时 responses 保持默认空结构."""
    from app.routers.wp_render_strategies._a112_dual import render
    from app.routers.wp_render_strategies._context import RenderContext

    mock_db = AsyncMock()
    mock_wp = MagicMock()
    mock_classification = MagicMock()

    ctx = RenderContext(
        db=mock_db,
        project_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        wp_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        wp_code="A1-12",
        working_paper=mock_wp,
        classification=mock_classification,
        component_type="a1-12-dual-checklist",
        sheet_html_data=None,
        sheet_schema=None,
        template_file_path=str(_TEMPLATE),
        year=2026,
        business_category="A",
    )

    with patch(
        "app.services.field_override_service.FieldOverrideService.get_batch",
        new_callable=AsyncMock,
        side_effect=RuntimeError("DB connection failed"),
    ):
        result = await render(ctx)

    # Should still return data with empty responses (graceful degradation)
    assert result is not None
    assert result["responses"]["items"] == {}
    assert result["responses"]["header"] == {}
    assert result["responses"]["custom_items"] == []
    # checklistData still populated from template
    assert len(result["checklistData"]["categories"]) == 2
