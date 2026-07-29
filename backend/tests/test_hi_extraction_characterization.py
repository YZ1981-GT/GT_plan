"""Characterization zero-regression baseline: HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED=False.

When the feature flag is OFF, render output for H/I strategies does NOT contain
`adjudication_segment_prefill` or `hi_extraction_enabled` keys.
Existing keys (component_type, account_codes, responses_snapshot, tb_values) ARE present.

Representative strategies tested:
- H5 oil_gas_assets (multi-segment asset, 1631+1632)
- I4 long_term_prepaid (single-account, 1801)
- I6 research_development_expense (income-statement, 6602)
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.config import settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_mock_ctx(wp_code: str, prefix: str, business_category: str = "manufacturing"):
    """Build a minimal mock RenderContext using types.SimpleNamespace."""
    mock_db = MagicMock()

    # Mock db.execute to return empty results by default
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_result.fetchone.return_value = None

    async def _mock_execute(*args, **kwargs):
        return mock_result

    mock_db.execute = _mock_execute

    classification = types.SimpleNamespace(
        sheet_name=f"审定表{prefix}-1",
        wp_code=wp_code,
        component_type=f"{prefix.lower()}-placeholder",
    )

    ctx = types.SimpleNamespace(
        db=mock_db,
        project_id=uuid4(),
        wp_id=uuid4(),
        wp_code=wp_code,
        working_paper=MagicMock(),
        classification=classification,
        component_type="",
        sheet_html_data=None,
        sheet_schema=None,
        template_file_path=None,
        year=2025,
        business_category=business_category,
        cross_ref_items=[],
        prep_info=None,
        classifications=[],
        audit_cycle=None,
        source_files=[],
        user_id=None,
    )
    return ctx


# ---------------------------------------------------------------------------
# H5 Oil & Gas Assets (multi-segment)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_h5_render_flag_off_no_extraction_keys(monkeypatch):
    """H5: flag=False → output has NO adjudication_segment_prefill / hi_extraction_enabled."""
    monkeypatch.setattr(settings, "HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)

    from app.routers.wp_render_strategies._h5_oil_gas_assets import render

    # H5 requires oil_gas industry to not return industry_error
    ctx = _make_mock_ctx("H5", "H5", business_category="oil_gas")
    result = await render(ctx)

    assert result is not None
    assert "adjudication_segment_prefill" not in result
    assert "hi_extraction_enabled" not in result

    # Existing keys ARE present
    assert result["component_type"] == "h5-oil-gas-assets"
    assert "account_codes" in result
    assert "responses_snapshot" in result
    assert "tb_values" in result


# ---------------------------------------------------------------------------
# I4 Long-Term Prepaid (single-account)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_i4_render_flag_off_no_extraction_keys(monkeypatch):
    """I4: flag=False → output has NO adjudication_segment_prefill / hi_extraction_enabled."""
    monkeypatch.setattr(settings, "HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)

    from app.routers.wp_render_strategies._i4_long_term_prepaid import render

    ctx = _make_mock_ctx("I4", "I4")
    result = await render(ctx)

    assert result is not None
    assert "adjudication_segment_prefill" not in result
    assert "hi_extraction_enabled" not in result

    # Existing keys ARE present
    assert result["component_type"] == "i4-long-term-prepaid"
    assert "account_codes" in result
    assert "responses_snapshot" in result
    assert "tb_values" in result


# ---------------------------------------------------------------------------
# I6 Research & Development Expense (income-statement)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_i6_render_flag_off_no_extraction_keys(monkeypatch):
    """I6: flag=False → output has NO adjudication_segment_prefill / hi_extraction_enabled."""
    monkeypatch.setattr(settings, "HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)

    from app.routers.wp_render_strategies._i6_research_development_expense import render

    ctx = _make_mock_ctx("I6", "I6")
    result = await render(ctx)

    assert result is not None
    assert "adjudication_segment_prefill" not in result
    assert "hi_extraction_enabled" not in result

    # Existing keys ARE present
    assert result["component_type"] == "i6-research-development-expense"
    assert "account_codes" in result
    assert "responses_snapshot" in result
    assert "tb_values" in result
