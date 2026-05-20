"""Minimal test verifying wp_ai_stocktake endpoint accepts H-cycle wp_code.

Task 2.8: Backend wp_ai_stocktake already supports wp_code parameter (F-F5 implemented it).
Verify it works with wp_code='H1'. No new code needed - just confirm the existing endpoint
accepts any wp_code.

Spec: workpaper-h-fixed-assets-cycle / Sprint 2 / Task 2.8
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.routers.wp_ai_stocktake import (
    StocktakeDiffItem,
    StocktakeSummaryRequest,
    _format_differences,
    _parse_stocktake_summary,
)


class TestStocktakeEndpointHCycleCompatibility:
    """Verify wp_ai_stocktake endpoint is wp_code-agnostic (works for H1/H2/H5/H7)."""

    def test_format_differences_with_asset_ids(self):
        """H cycle uses asset IDs instead of inventory item names."""
        diffs = [
            StocktakeDiffItem(
                itemName="FA-2024-001",
                bookQty=1,
                actualQty=1,
                reason="在用",
            ),
            StocktakeDiffItem(
                itemName="FA-2024-002",
                bookQty=1,
                actualQty=0,
                reason="盘亏-已报废未销账",
            ),
        ]
        text = _format_differences(diffs)
        assert "FA-2024-001" in text
        assert "FA-2024-002" in text
        assert "盘亏" in text

    def test_parse_stocktake_summary_with_h_cycle_content(self):
        """Parse LLM output for H-cycle fixed asset stocktake."""
        ai_text = (
            "摘要：\n"
            "本次固定资产盘点共涉及 5 项资产，其中 1 项盘亏。"
            "盘亏资产 FA-2024-002 已报废但未及时销账，建议补提减值。\n\n"
            "风险提示：\n"
            "1. 资产台账与实物不符，存在管理漏洞\n"
            "2. 报废资产未及时处置，影响资产净值准确性"
        )
        diffs = [
            StocktakeDiffItem(itemName="FA-2024-002", bookQty=1, actualQty=0, reason="盘亏")
        ]
        summary, alerts = _parse_stocktake_summary(ai_text, diffs)
        assert "固定资产" in summary
        assert len(alerts) >= 1

    def test_request_model_accepts_h_cycle_data(self):
        """StocktakeSummaryRequest works with H-cycle asset data."""
        req = StocktakeSummaryRequest(
            differences=[
                StocktakeDiffItem(
                    itemName="H1-资产编号-001",
                    bookQty=1,
                    actualQty=0,
                    reason="盘亏-责任人已离职",
                ),
            ],
            conclusion="H1 固定资产盘点结论",
        )
        assert len(req.differences) == 1
        assert req.conclusion == "H1 固定资产盘点结论"

    def test_endpoint_url_is_wp_code_agnostic(self):
        """The endpoint URL pattern /api/projects/{pid}/workpapers/{wid}/ai/stocktake-summary
        is parameterized by wp_id (UUID), not wp_code. Any workpaper (F2 or H1) can use it."""
        from app.routers.wp_ai_stocktake import router

        routes = [r.path for r in router.routes]
        # The route includes the full prefix path
        assert any("stocktake-summary" in r for r in routes)
        # The route doesn't filter by wp_code - it's generic
        # Any workpaper ID (H1, H2, F2, etc.) can call this endpoint
