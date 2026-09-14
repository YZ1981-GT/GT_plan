"""A17-2-1 关键审计事项(KAM) — Unit Tests.

Tests: render strategy (normal/empty KAM/applicability switch on/JSON failure).
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.wp_render_strategies._a1721_kam import render
from app.routers.wp_render_strategies._context import RenderContext


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_ctx(
    checklist_rows=None,
    client_name="测试公司",
    audit_year=2024,
):
    """Create mock RenderContext for A17-2-1."""
    db = AsyncMock()

    cr_result = MagicMock()
    cr_result.fetchall.return_value = checklist_rows or []

    proj_row = MagicMock()
    proj_row.client_name = client_name
    proj_row.audit_year = audit_year
    proj_result = MagicMock()
    proj_result.fetchone.return_value = proj_row

    db.execute = AsyncMock(side_effect=[cr_result, proj_result])

    ctx = MagicMock(spec=RenderContext)
    ctx.wp_id = "wp-a1721-001"
    ctx.db = db
    ctx.project_id = "proj-001"
    return ctx


def _row(item_id, conclusion=None, remark=None):
    r = MagicMock()
    r.item_id = item_id
    r.conclusion = conclusion
    r.remark = remark
    return r


# ─── Tests: Normal render ─────────────────────────────────────────────────────


class TestRenderNormal:
    """Normal render with candidates + kams + notes + applicability all populated."""

    def test_returns_all_top_level_keys(self):
        candidates_data = [
            {"description": "收入确认", "risk_level": "高", "communicate": "Y", "reason": "重大风险"},
            {"description": "存货跌价", "risk_level": "中", "communicate": "N", "reason": ""},
        ]
        kam1_data = {
            "basic": "收入确认相关KAM",
            "policy": "收入确认会计政策",
            "reason": "重大风险领域",
            "response": "执行了细节测试",
            "result": "未发现重大错报",
            "ref_index": "D3-1",
        }
        rows = [
            _row("a1721-candidates", remark=json.dumps(candidates_data)),
            _row("a1721-kam1", remark=json.dumps(kam1_data)),
            _row("a1721-notes-1", remark="附注五(二十三)"),
            _row("a1721-applicability", conclusion="N", remark=None),
        ]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result is not None
        expected_keys = {"candidates", "kams", "notes", "applicability", "project_context"}
        assert set(result.keys()) == expected_keys

    def test_candidates_loaded_correctly(self):
        candidates_data = [
            {"description": "收入确认", "risk_level": "高", "communicate": "Y", "reason": "重大风险"},
        ]
        rows = [_row("a1721-candidates", remark=json.dumps(candidates_data))]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert len(result["candidates"]) == 1
        assert result["candidates"][0]["description"] == "收入确认"
        assert result["candidates"][0]["communicate"] == "Y"

    def test_kams_loaded_with_all_6_fields(self):
        kam_data = {
            "basic": "基本情况",
            "policy": "会计政策",
            "reason": "认定原因",
            "response": "审计应对",
            "result": "审计结果",
            "ref_index": "D1-1",
        }
        rows = [_row("a1721-kam1", remark=json.dumps(kam_data))]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert len(result["kams"]) == 1
        k = result["kams"][0]
        assert k["index"] == 1
        assert k["basic"] == "基本情况"
        assert k["policy"] == "会计政策"
        assert k["reason"] == "认定原因"
        assert k["response"] == "审计应对"
        assert k["result"] == "审计结果"
        assert k["ref_index"] == "D1-1"

    def test_multiple_kams_sorted_by_index(self):
        kam2 = {"basic": "第二个", "policy": "", "reason": "", "response": "", "result": "", "ref_index": ""}
        kam1 = {"basic": "第一个", "policy": "", "reason": "", "response": "", "result": "", "ref_index": ""}
        rows = [
            _row("a1721-kam2", remark=json.dumps(kam2)),
            _row("a1721-kam1", remark=json.dumps(kam1)),
        ]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert len(result["kams"]) == 2
        assert result["kams"][0]["index"] == 1
        assert result["kams"][0]["basic"] == "第一个"
        assert result["kams"][1]["index"] == 2
        assert result["kams"][1]["basic"] == "第二个"

    def test_notes_loaded_and_sorted(self):
        rows = [
            _row("a1721-notes-2", remark="附注2内容"),
            _row("a1721-notes-1", remark="附注1内容"),
        ]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert len(result["notes"]) == 2
        assert result["notes"][0]["kam_index"] == 1
        assert result["notes"][0]["content"] == "附注1内容"
        assert result["notes"][1]["kam_index"] == 2
        assert result["notes"][1]["content"] == "附注2内容"

    def test_applicability_no_kam_false(self):
        rows = [_row("a1721-applicability", conclusion="N", remark=None)]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["applicability"]["no_kam"] is False
        assert result["applicability"]["reason"] is None

    def test_project_context_filled(self):
        ctx = _make_ctx(client_name="ABC有限公司", audit_year=2025)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["project_context"]["client_name"] == "ABC有限公司"
        assert result["project_context"]["audit_period"] == "2025年度"


# ─── Tests: Empty (no checklist_responses) ────────────────────────────────────


class TestRenderEmpty:
    """No checklist_responses → default empty structure."""

    def test_empty_returns_default_structure(self):
        ctx = _make_ctx(checklist_rows=[])
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result is not None
        assert result["candidates"] == []
        assert result["kams"] == []
        assert result["notes"] == []
        assert result["applicability"] == {"no_kam": False, "reason": None}

    def test_empty_project_context_has_defaults(self):
        ctx = _make_ctx(checklist_rows=[])
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert "client_name" in result["project_context"]
        assert "audit_period" in result["project_context"]


# ─── Tests: Applicability switch on ──────────────────────────────────────────


class TestApplicabilitySwitchOn:
    """no_kam=True, reason filled."""

    def test_applicability_on_with_reason(self):
        rows = [_row("a1721-applicability", conclusion="Y", remark="本年度不存在关键审计事项")]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["applicability"]["no_kam"] is True
        assert result["applicability"]["reason"] == "本年度不存在关键审计事项"

    def test_applicability_on_without_reason(self):
        rows = [_row("a1721-applicability", conclusion="Y", remark=None)]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["applicability"]["no_kam"] is True
        assert result["applicability"]["reason"] is None

    def test_applicability_on_still_returns_kams_if_present(self):
        """Even with no_kam=True, existing KAMs are still loaded (data integrity)."""
        kam_data = {"basic": "遗留", "policy": "", "reason": "", "response": "", "result": "", "ref_index": ""}
        rows = [
            _row("a1721-applicability", conclusion="Y", remark="不适用"),
            _row("a1721-kam1", remark=json.dumps(kam_data)),
        ]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["applicability"]["no_kam"] is True
        # KAMs still loaded (front-end hides them, but data is intact)
        assert len(result["kams"]) == 1


# ─── Tests: JSON failure ──────────────────────────────────────────────────────


class TestJsonFailure:
    """Invalid JSON in candidates/kam remark → graceful fallback."""

    def test_invalid_candidates_json_returns_empty_list(self):
        rows = [_row("a1721-candidates", remark="not valid json{{{")]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["candidates"] == []

    def test_non_array_candidates_json_returns_empty_list(self):
        rows = [_row("a1721-candidates", remark=json.dumps({"key": "value"}))]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["candidates"] == []

    def test_invalid_kam_json_skips_that_kam(self):
        kam_good = {"basic": "有效", "policy": "", "reason": "", "response": "", "result": "", "ref_index": ""}
        rows = [
            _row("a1721-kam1", remark=json.dumps(kam_good)),
            _row("a1721-kam2", remark="broken json!!!"),
        ]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        # Only the valid KAM is loaded
        assert len(result["kams"]) == 1
        assert result["kams"][0]["basic"] == "有效"

    def test_non_dict_kam_json_skips_that_kam(self):
        rows = [_row("a1721-kam1", remark=json.dumps([1, 2, 3]))]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["kams"] == []

    def test_null_remark_for_kam_skips(self):
        rows = [_row("a1721-kam1", remark=None)]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["kams"] == []
