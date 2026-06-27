"""Unit tests for A17-7 独立性声明书 render strategy.

Tests: team variant, committee variant, empty responses, team pre-fill from assignments.
"""

from __future__ import annotations

import json
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.wp_render_strategies._a177_independence_declaration import render


# ─── Mock helpers ─────────────────────────────────────────────────────────────

ChecklistRow = namedtuple("ChecklistRow", ["item_id", "conclusion", "remark"])
ProjectRow = namedtuple("ProjectRow", ["client_name", "audit_year"])
AssignmentRow = namedtuple("AssignmentRow", ["display_name"])


def _make_ctx(
    wp_code="A17-7",
    wp_id="wp-001",
    project_id="proj-001",
    checklist_rows=None,
    project_row=None,
    assignment_rows=None,
):
    """Build a minimal mock RenderContext."""
    ctx = MagicMock()
    ctx.wp_id = wp_id
    ctx.project_id = project_id
    ctx.wp_code = wp_code

    db = AsyncMock()

    # Mock checklist_responses query
    checklist_result = MagicMock()
    checklist_result.fetchall.return_value = checklist_rows or []

    # Mock project query
    proj_result = MagicMock()
    proj_result.fetchone.return_value = project_row

    # Mock assignments query
    assign_result = MagicMock()
    assign_result.fetchall.return_value = assignment_rows or []

    # Sequential execute calls: 1=checklist, 2=project, 3=assignments
    db.execute = AsyncMock(side_effect=[checklist_result, proj_result, assign_result])
    ctx.db = db

    return ctx


# ─── Tests: Team Variant ──────────────────────────────────────────────────────


class TestA177TeamVariant:
    """Tests for variant='team' (wp_code=A17-7)."""

    @pytest.mark.asyncio
    async def test_returns_team_variant(self):
        """wp_code A17-7 produces variant='team'."""
        ctx = _make_ctx(wp_code="A17-7")
        result = await render(ctx)
        assert result["variant"] == "team"

    @pytest.mark.asyncio
    async def test_team_declaration_text(self):
        """Team variant has team-specific declaration text."""
        ctx = _make_ctx(wp_code="A17-7")
        result = await render(ctx)
        assert "本项目的业务期间" in result["declaration_text"]

    @pytest.mark.asyncio
    async def test_team_loads_period_data(self):
        """Saved period data is loaded for team variant."""
        rows = [
            ChecklistRow("a177-period-business-start", None, "2025-01-01"),
            ChecklistRow("a177-period-business-end", None, "2025-12-31"),
            ChecklistRow("a177-period-report-start", None, "2025-01-01"),
            ChecklistRow("a177-period-report-end", None, "2025-12-31"),
        ]
        ctx = _make_ctx(wp_code="A17-7", checklist_rows=rows)
        result = await render(ctx)
        assert result["period_data"]["business_start"] == "2025-01-01"
        assert result["period_data"]["business_end"] == "2025-12-31"
        assert result["period_data"]["report_start"] == "2025-01-01"
        assert result["period_data"]["report_end"] == "2025-12-31"

    @pytest.mark.asyncio
    async def test_team_loads_sign_table(self):
        """Saved sign table rows are loaded correctly."""
        rows = [
            ChecklistRow("a177-sign-1", None, json.dumps({"name": "张三", "signed": True, "date": "2025-06-01"})),
            ChecklistRow("a177-sign-2", None, json.dumps({"name": "李四", "signed": False, "date": None})),
        ]
        ctx = _make_ctx(wp_code="A17-7", checklist_rows=rows)
        result = await render(ctx)
        assert len(result["team_sign_table"]) == 2
        assert result["team_sign_table"][0]["name"] == "张三"
        assert result["team_sign_table"][0]["signed"] is True
        assert result["team_sign_table"][1]["name"] == "李四"
        assert result["team_sign_table"][1]["signed"] is False

    @pytest.mark.asyncio
    async def test_team_loads_partner_section(self):
        """Partner section Y/N and signs are loaded."""
        rows = [
            ChecklistRow("a177-partner-confirmed", "Y", None),
            ChecklistRow("a177-partner-sign", None, json.dumps({"name": "王五", "date": "2025-06-15"})),
            ChecklistRow("a177-manager-sign", None, json.dumps({"name": "赵六", "date": "2025-06-15"})),
        ]
        ctx = _make_ctx(wp_code="A17-7", checklist_rows=rows)
        result = await render(ctx)
        assert result["partner_section"]["confirmed"] is True
        assert result["partner_section"]["partner_sign"]["name"] == "王五"
        assert result["partner_section"]["manager_sign"]["name"] == "赵六"

    @pytest.mark.asyncio
    async def test_team_loads_threat_records(self):
        """Threat record rows are loaded by type."""
        rows = [
            ChecklistRow("a177-threat-economic-1", None, json.dumps({"member": "A", "type": "股票", "amount": "10万", "measure": "已处置"})),
            ChecklistRow("a177-threat-loan-1", None, json.dumps({"member": "B", "type": "贷款", "amount": "5万", "measure": "已还清"})),
            ChecklistRow("a177-threat-business-1", None, json.dumps({"member": "C", "description": "供应商", "measure": "终止"})),
        ]
        ctx = _make_ctx(wp_code="A17-7", checklist_rows=rows)
        result = await render(ctx)
        assert len(result["threat_records"]["economic_interest"]) == 1
        assert len(result["threat_records"]["loan_guarantee"]) == 1
        assert len(result["threat_records"]["business_relation"]) == 1
        assert result["threat_records"]["economic_interest"][0]["member"] == "A"


# ─── Tests: Committee Variant ─────────────────────────────────────────────────


class TestA177CommitteeVariant:
    """Tests for variant='committee' (wp_code=A17-7A)."""

    @pytest.mark.asyncio
    async def test_returns_committee_variant(self):
        """wp_code A17-7A produces variant='committee'."""
        ctx = _make_ctx(wp_code="A17-7A")
        result = await render(ctx)
        assert result["variant"] == "committee"

    @pytest.mark.asyncio
    async def test_committee_declaration_text(self):
        """Committee variant has committee-specific declaration text."""
        ctx = _make_ctx(wp_code="A17-7A")
        result = await render(ctx)
        assert "专业技术委员会审核委员" in result["declaration_text"]

    @pytest.mark.asyncio
    async def test_committee_uses_a177a_prefix(self):
        """Committee variant reads items with a177a- prefix."""
        rows = [
            ChecklistRow("a177a-period-business-start", None, "2025-03-01"),
        ]
        ctx = _make_ctx(wp_code="A17-7A", checklist_rows=rows)
        result = await render(ctx)
        assert result["period_data"]["business_start"] == "2025-03-01"


# ─── Tests: Empty Responses ───────────────────────────────────────────────────


class TestA177EmptyResponses:
    """Tests for empty/missing data scenarios."""

    @pytest.mark.asyncio
    async def test_empty_returns_all_keys(self):
        """Empty data still returns all 9 top-level keys."""
        ctx = _make_ctx(checklist_rows=[], project_row=None)
        result = await render(ctx)
        assert set(result.keys()) == {
            "variant", "meta_info", "declaration_text", "period_data",
            "team_sign_table", "partner_section", "threat_records",
            "guidance_notes", "project_context",
        }

    @pytest.mark.asyncio
    async def test_empty_period_data_is_none(self):
        """Empty period data has None values."""
        ctx = _make_ctx(checklist_rows=[])
        result = await render(ctx)
        assert result["period_data"]["business_start"] is None
        assert result["period_data"]["report_end"] is None

    @pytest.mark.asyncio
    async def test_empty_partner_section_defaults(self):
        """Empty partner section has None confirmed."""
        ctx = _make_ctx(checklist_rows=[])
        result = await render(ctx)
        assert result["partner_section"]["confirmed"] is None

    @pytest.mark.asyncio
    async def test_guidance_notes_always_5(self):
        """Guidance notes always returns exactly 5 items."""
        ctx = _make_ctx(checklist_rows=[])
        result = await render(ctx)
        assert len(result["guidance_notes"]) == 5


# ─── Tests: Team Pre-fill from Assignments ────────────────────────────────────


class TestA177TeamPreFill:
    """Tests for team sign table pre-fill from project assignments."""

    @pytest.mark.asyncio
    async def test_prefill_from_assignments_when_empty(self):
        """When no saved sign rows, pre-fill from assignments."""
        assignments = [
            AssignmentRow("张三"),
            AssignmentRow("李四"),
            AssignmentRow("王五"),
        ]
        ctx = _make_ctx(checklist_rows=[], assignment_rows=assignments)
        result = await render(ctx)
        assert len(result["team_sign_table"]) == 3
        assert result["team_sign_table"][0]["name"] == "张三"
        assert result["team_sign_table"][1]["name"] == "李四"
        assert result["team_sign_table"][2]["name"] == "王五"
        # Pre-filled rows should not be signed
        assert all(row["signed"] is False for row in result["team_sign_table"])

    @pytest.mark.asyncio
    async def test_no_prefill_when_saved_rows_exist(self):
        """When saved sign rows exist, do NOT override with assignments."""
        rows = [
            ChecklistRow("a177-sign-1", None, json.dumps({"name": "已保存成员", "signed": True, "date": "2025-01-01"})),
        ]
        assignments = [
            AssignmentRow("张三"),
            AssignmentRow("李四"),
        ]
        ctx = _make_ctx(checklist_rows=rows, assignment_rows=assignments)
        result = await render(ctx)
        # Should use saved data, not override
        assert len(result["team_sign_table"]) == 1
        assert result["team_sign_table"][0]["name"] == "已保存成员"

    @pytest.mark.asyncio
    async def test_project_context_contains_team_members(self):
        """project_context.team_members always populated from assignments."""
        assignments = [AssignmentRow("A"), AssignmentRow("B")]
        ctx = _make_ctx(checklist_rows=[], assignment_rows=assignments)
        result = await render(ctx)
        assert len(result["project_context"]["team_members"]) == 2
        assert result["project_context"]["team_members"][0]["name"] == "A"

    @pytest.mark.asyncio
    async def test_auto_fill_meta_from_project(self):
        """Meta client_name and audit_year auto-fill from project."""
        proj = ProjectRow("测试公司", 2025)
        ctx = _make_ctx(checklist_rows=[], project_row=proj)
        result = await render(ctx)
        assert result["meta_info"]["client_name"] == "测试公司"
        assert result["meta_info"]["audit_year"] == "2025"
