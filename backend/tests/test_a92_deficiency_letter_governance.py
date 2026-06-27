"""Unit tests for A9-2 向治理层通报内部控制缺陷沟通函 render strategy.

Tests: governance structure, B22B absent returns warning, no general deficiencies.
"""

from __future__ import annotations

import json
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.wp_render_strategies._a92_deficiency_letter_governance import render


# ─── Mock helpers ─────────────────────────────────────────────────────────────

ChecklistRow = namedtuple("ChecklistRow", ["item_id", "conclusion", "remark"])
ProjectRow = namedtuple("ProjectRow", ["client_name", "audit_year"])
B22BRow = namedtuple("B22BRow", ["wp_id"])


def _make_ctx(
    wp_id="wp-a92",
    project_id="proj-a92",
    checklist_rows=None,
    project_row=None,
    b22b_wp_id=None,
    b22b_checklist_rows=None,
):
    """Build a minimal mock RenderContext for A9-2."""
    ctx = MagicMock()
    ctx.wp_id = wp_id
    ctx.project_id = project_id

    db = AsyncMock()

    # Build sequential execute results:
    # 1st call: A9-2 checklist_responses (prefix a92-)
    # 2nd call: B22B wp_index JOIN query
    # 3rd call (if b22b exists): B22B checklist_responses
    # 4th call: project context
    a92_result = MagicMock()
    a92_result.fetchall.return_value = checklist_rows or []

    b22b_wp_result = MagicMock()
    b22b_wp_result.fetchone.return_value = (
        B22BRow(b22b_wp_id) if b22b_wp_id else None
    )

    b22b_cr_result = MagicMock()
    b22b_cr_result.fetchall.return_value = b22b_checklist_rows or []

    proj_result = MagicMock()
    proj_result.fetchone.return_value = project_row

    if b22b_wp_id:
        db.execute = AsyncMock(
            side_effect=[a92_result, b22b_wp_result, b22b_cr_result, proj_result]
        )
    else:
        db.execute = AsyncMock(
            side_effect=[a92_result, b22b_wp_result, proj_result]
        )

    ctx.db = db
    return ctx


# ─── Tests: Governance Structure ─────────────────────────────────────────────


class TestA92GovernanceStructure:
    """A9-2 governance response structure tests."""

    @pytest.mark.asyncio
    async def test_returns_variant_governance(self):
        """Response variant is always 'governance'."""
        proj = ProjectRow("治理层测试", 2025)
        ctx = _make_ctx(checklist_rows=[], project_row=proj)

        result = await render(ctx)

        assert result is not None
        assert result["variant"] == "governance"

    @pytest.mark.asyncio
    async def test_no_response_in_section_data(self):
        """section_data does not contain 'response' key."""
        proj = ProjectRow("治理层测试", 2025)
        ctx = _make_ctx(checklist_rows=[], project_row=proj)

        result = await render(ctx)

        assert "response" not in result["section_data"]
        assert set(result["section_data"].keys()) == {
            "addressee", "independence", "committee", "signature"
        }

    @pytest.mark.asyncio
    async def test_no_general_in_deficiency_list(self):
        """deficiency_list does not contain 'general' key."""
        proj = ProjectRow("治理层测试", 2025)
        ctx = _make_ctx(checklist_rows=[], project_row=proj)

        result = await render(ctx)

        assert "general" not in result["deficiency_list"]
        assert set(result["deficiency_list"].keys()) == {"major", "significant"}

    @pytest.mark.asyncio
    async def test_top_level_has_5_keys(self):
        """Top-level response always has exactly 5 keys."""
        proj = ProjectRow("治理层测试", 2025)
        ctx = _make_ctx(checklist_rows=[], project_row=proj)

        result = await render(ctx)

        assert set(result.keys()) == {
            "variant", "section_data", "deficiency_list", "project_context", "b22b_warning"
        }

    @pytest.mark.asyncio
    async def test_b22b_general_deficiencies_filtered(self):
        """B22B general deficiencies are excluded from A9-2 result."""
        b22b_rows = [
            ChecklistRow(
                "b22b-deficiency-001", None,
                json.dumps({"id": "DEF-M", "description": "重大", "impact": "重大", "severity": "major", "index_ref": "B22B-1"}),
            ),
            ChecklistRow(
                "b22b-deficiency-002", None,
                json.dumps({"id": "DEF-S", "description": "重要", "impact": "较大", "severity": "significant", "index_ref": "B22B-2"}),
            ),
            ChecklistRow(
                "b22b-deficiency-003", None,
                json.dumps({"id": "DEF-G", "description": "一般", "impact": "轻微", "severity": "general", "index_ref": "B22B-3"}),
            ),
        ]
        proj = ProjectRow("治理层测试", 2025)
        ctx = _make_ctx(
            checklist_rows=[],
            project_row=proj,
            b22b_wp_id="b22b-wp-001",
            b22b_checklist_rows=b22b_rows,
        )

        result = await render(ctx)

        assert len(result["deficiency_list"]["major"]) == 1
        assert len(result["deficiency_list"]["significant"]) == 1
        assert "general" not in result["deficiency_list"]

    @pytest.mark.asyncio
    async def test_uses_a92_prefix_for_data(self):
        """Reads from checklist_responses with a92- prefix."""
        rows = [
            ChecklistRow("a92-independence-team_independent", "Y", None),
            ChecklistRow("a92-committee-applicability", "N", None),
            ChecklistRow("a92-signature-date", "2026-07-01", None),
        ]
        proj = ProjectRow("治理层测试", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj)

        result = await render(ctx)

        assert result["section_data"]["independence"]["team_independent"] == "Y"
        assert result["section_data"]["committee"]["applicability"] == "N"
        assert result["section_data"]["signature"]["date"] == "2026-07-01"


# ─── Tests: B22B Absent ──────────────────────────────────────────────────────


class TestA92B22BAbsent:
    """B22B workpaper not found — governance mode."""

    @pytest.mark.asyncio
    async def test_b22b_absent_returns_warning(self):
        """When B22B not found, returns empty deficiency list + warning."""
        proj = ProjectRow("治理层测试", 2025)
        ctx = _make_ctx(checklist_rows=[], project_row=proj, b22b_wp_id=None)

        result = await render(ctx)

        assert result["b22b_warning"] == "未找到B22B内控缺陷评价表"
        assert result["deficiency_list"]["major"] == []
        assert result["deficiency_list"]["significant"] == []

    @pytest.mark.asyncio
    async def test_b22b_absent_manual_deficiencies_still_work(self):
        """Manual deficiencies still returned in governance mode."""
        manual_items = [{"id": "M-001", "description": "手动重大缺陷", "impact": "重大", "recommendation": "整改"}]
        rows = [
            ChecklistRow("a92-deficiency-major", "1", json.dumps(manual_items)),
        ]
        proj = ProjectRow("治理层测试", 2025)
        ctx = _make_ctx(checklist_rows=rows, project_row=proj, b22b_wp_id=None)

        result = await render(ctx)

        assert len(result["deficiency_list"]["major"]) == 1
        assert result["deficiency_list"]["major"][0]["source"] == "manual"

    @pytest.mark.asyncio
    async def test_project_context_auto_fills(self):
        """Project context auto-fills correctly."""
        proj = ProjectRow("治理层公司", 2025)
        ctx = _make_ctx(checklist_rows=[], project_row=proj)

        result = await render(ctx)

        assert result["project_context"]["client_name"] == "治理层公司"
        assert result["project_context"]["audit_report_date"] == "2025年12月31日"
        assert result["section_data"]["addressee"]["client_name"] == "治理层公司"
