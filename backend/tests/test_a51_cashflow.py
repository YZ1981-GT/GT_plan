"""A5-1 现金流量表审计 — Backend Integration Tests.

Tests: render strategy returns correct {responses: {...}} structure.
Mock pattern follows test_a1721_kam.py.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.wp_render_strategies._a51_cashflow import render
from app.routers.wp_render_strategies._context import RenderContext


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_ctx(checklist_rows=None):
    """Create mock RenderContext for A5-1."""
    db = AsyncMock()

    cr_result = MagicMock()
    cr_result.fetchall.return_value = checklist_rows or []
    db.execute = AsyncMock(return_value=cr_result)

    ctx = MagicMock(spec=RenderContext)
    ctx.wp_id = "wp-a51-001"
    ctx.db = db
    return ctx


def _row(item_id, conclusion=None, remark=None):
    """Create a mock checklist_responses row."""
    r = MagicMock()
    r.item_id = item_id
    r.conclusion = conclusion
    r.remark = remark
    return r


# ─── Tests: Normal render ─────────────────────────────────────────────────────


class TestA51RenderNormal:
    """Normal render with various checklist_responses data."""

    def test_returns_responses_dict(self):
        rows = [
            _row("a51-audit-1.unadjusted", remark="1000"),
            _row("a51-audit-1.adjustment", remark="200"),
            _row("a51-program-step-1.conclusion", conclusion="Y", remark="已完成"),
        ]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result is not None
        assert "responses" in result
        assert isinstance(result["responses"], dict)

    def test_responses_contain_all_rows(self):
        rows = [
            _row("a51-audit-1.unadjusted", remark="1000"),
            _row("a51-audit-2.unadjusted", remark="500"),
            _row("a51-reconcile-1-1.amount", remark="300"),
        ]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert len(result["responses"]) == 3
        assert "a51-audit-1.unadjusted" in result["responses"]
        assert "a51-audit-2.unadjusted" in result["responses"]
        assert "a51-reconcile-1-1.amount" in result["responses"]

    def test_each_response_has_conclusion_and_remark(self):
        rows = [
            _row("a51-program-step-1.conclusion", conclusion="Y", remark="已执行"),
        ]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        entry = result["responses"]["a51-program-step-1.conclusion"]
        assert entry["conclusion"] == "Y"
        assert entry["remark"] == "已执行"

    def test_null_conclusion_preserved(self):
        rows = [
            _row("a51-audit-1.unadjusted", conclusion=None, remark="1000"),
        ]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        entry = result["responses"]["a51-audit-1.unadjusted"]
        assert entry["conclusion"] is None
        assert entry["remark"] == "1000"

    def test_null_remark_preserved(self):
        rows = [
            _row("a51-program-step-3.conclusion", conclusion="NA", remark=None),
        ]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        entry = result["responses"]["a51-program-step-3.conclusion"]
        assert entry["conclusion"] == "NA"
        assert entry["remark"] is None

    def test_many_responses(self):
        """A5-1 can have many item_ids (程序表+审定表+勾稽+核查+其他CF)."""
        rows = [_row(f"a51-field-{i}", remark=str(i * 10)) for i in range(50)]
        ctx = _make_ctx(checklist_rows=rows)
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert len(result["responses"]) == 50


# ─── Tests: Empty (no checklist_responses) ────────────────────────────────────


class TestA51RenderEmpty:
    """No checklist_responses → empty responses dict."""

    def test_empty_returns_responses_key(self):
        ctx = _make_ctx(checklist_rows=[])
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result is not None
        assert "responses" in result

    def test_empty_responses_is_empty_dict(self):
        ctx = _make_ctx(checklist_rows=[])
        result = asyncio.get_event_loop().run_until_complete(render(ctx))

        assert result["responses"] == {}


# ─── Tests: SQL query correctness ────────────────────────────────────────────


class TestA51SqlQuery:
    """Verify the correct query parameters are passed."""

    def test_query_uses_wp_id(self):
        ctx = _make_ctx(checklist_rows=[])
        asyncio.get_event_loop().run_until_complete(render(ctx))

        # Verify db.execute was called with the wp_id param
        call_args = ctx.db.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", {})
        assert params["wp_id"] == str(ctx.wp_id)

    def test_query_filters_by_a51_prefix(self):
        ctx = _make_ctx(checklist_rows=[])
        asyncio.get_event_loop().run_until_complete(render(ctx))

        # Verify the SQL text contains the a51- LIKE filter
        call_args = ctx.db.execute.call_args
        sql_text = str(call_args[0][0])
        assert "a51-%" in sql_text
