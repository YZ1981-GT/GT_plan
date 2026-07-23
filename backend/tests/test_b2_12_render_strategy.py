"""B2-12 对前任评价底稿 render 策略冒烟测试。

Validates:
- render 返回 responses_snapshot（B2-12-* 快照）+ project_context（client_name/audit_year）
- checklist 查询异常时优雅降级（不抛错，返回空 snapshot）

对应 spec: b2-predecessor-communication-hardening Task 7
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.wp_render_strategies._b2_12_evaluation import render


def _row(item_id: str, conclusion, remark):
    r = MagicMock()
    r.item_id = item_id
    r.conclusion = conclusion
    r.remark = remark
    return r


def _make_ctx(*, checklist_rows=None, proj_row=None, checklist_raises=False):
    ctx = MagicMock()
    ctx.wp_id = uuid.uuid4()
    ctx.project_id = uuid.uuid4()
    db = AsyncMock()

    async def _execute(stmt, params=None):
        sql = str(getattr(stmt, "text", stmt)).lower()
        if "checklist_responses" in sql:
            if checklist_raises:
                raise RuntimeError("db down")
            res = MagicMock()
            res.fetchall.return_value = checklist_rows or []
            return res
        if "from projects" in sql:
            res = MagicMock()
            res.fetchone.return_value = proj_row
            return res
        res = MagicMock()
        res.fetchall.return_value = []
        res.fetchone.return_value = None
        return res

    db.execute = _execute
    ctx.db = db
    return ctx


@pytest.mark.asyncio
async def test_render_returns_snapshot_and_context():
    proj = MagicMock()
    proj.client_name = "北京测试科技有限公司"
    proj.audit_year = 2025
    rows = [
        _row("B2-12-steps", None, '[{"record":"李某，10年"}]'),
        _row("B2-12-conclusions", None, '[{"exists":"是","measure":"扩大程序"}]'),
        _row("B2-12-note", None, "综合评价说明"),
    ]
    ctx = _make_ctx(checklist_rows=rows, proj_row=proj)
    out = await render(ctx)
    assert out is not None
    assert set(out.keys()) == {"responses_snapshot", "project_context"}
    assert out["responses_snapshot"]["B2-12-steps"]["remark"] == '[{"record":"李某，10年"}]'
    assert out["responses_snapshot"]["B2-12-conclusions"]["conclusion"] is None
    assert out["project_context"]["client_name"] == "北京测试科技有限公司"
    assert out["project_context"]["audit_year"] == "2025"


@pytest.mark.asyncio
async def test_render_empty_when_no_data():
    ctx = _make_ctx(checklist_rows=[], proj_row=None)
    out = await render(ctx)
    assert out["responses_snapshot"] == {}
    assert out["project_context"] == {"client_name": "", "audit_year": ""}


@pytest.mark.asyncio
async def test_render_graceful_on_checklist_error():
    """checklist 查询异常 → 不抛错，snapshot 为空，仍返回 project_context。"""
    proj = MagicMock()
    proj.client_name = "某公司"
    proj.audit_year = 2024
    ctx = _make_ctx(checklist_raises=True, proj_row=proj)
    out = await render(ctx)
    assert out["responses_snapshot"] == {}
    assert out["project_context"]["client_name"] == "某公司"
