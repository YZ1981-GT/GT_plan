"""审定表→试算表显式发布端点测试（P0-项3）

spec: .kiro/specs/d4-dual-mode-formula-governance/

验证 ``publish_determination_to_tb``（POST /api/workpapers/{wp_id}/audit-determination/publish-to-tb）：
  - 有编辑权 + 有效审定表 → 发布**带 publish_confirmed 信号**的 WORKPAPER_SAVED（区别于普通保存）。
  - readonly/qc/非成员 → 403（authorize_wp_edit 拦下），不发布。
  - 非审定表 sheet / 无 audit_rows → 400。
  - 幂等 token：不传时服务端按内容合成；传入时透传（供 handler 侧 tb_publish_ack 去重）。

背景：普通保存不再自动回写 TB（见 wp_html_save._maybe_publish_determination_writeback 注释），
TB 回写仅经本端点显式确认触发（handler 侧再校验发布者权限 + 幂等）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.base import UserRole


_WP_ID = uuid4()
_PROJECT_ID = uuid4()


def _make_user(role: UserRole):
    u = MagicMock()
    u.id = uuid4()
    u.role = MagicMock(value=role.value)
    return u


def _scalar(value):
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=value)
    return res


def _admin_db():
    """mock db：authorize_wp_edit(admin) 查底稿 → project_id；consol_lock → 未锁。"""
    db = AsyncMock()

    def _side(stmt, *a, **k):
        sql = str(getattr(stmt, "text", stmt)).lower()
        if "consol_lock" in sql:
            return _scalar(False)
        return _scalar(_PROJECT_ID)

    db.execute = AsyncMock(side_effect=_side)
    return db


def _valid_html():
    return {
        "audit_rows": [
            {"id": "r1", "account_code": "1122", "current_unadjusted": 1000, "adj_amount": 50, "reclass_amount": 0},
            {"id": "r2", "account_code": "6001", "current_unadjusted": 2000},
        ]
    }


@pytest.fixture(autouse=True)
def _patch_deps(monkeypatch):
    """patch 审定数取数 + year + event_bus.publish（避免真实 DB/事件总线）。"""
    async def _fake_tb(audit_rows, *, db, project_id):
        return {}  # 取数为空 → 用 row 自带值

    async def _fake_year(db, project_id):
        return 2025

    published = []

    async def _fake_publish(payload):
        published.append(payload)

    monkeypatch.setattr(
        "app.services.wp_audit_sheet_tb_service.fetch_audit_sheet_tb_values", _fake_tb
    )
    # 端点在模块顶层 import 了 fetch_project_audit_year，故 patch 端点模块内的引用
    monkeypatch.setattr(
        "app.routers.wp_html_save.fetch_project_audit_year", _fake_year
    )
    monkeypatch.setattr(
        "app.services.event_bus.event_bus.publish", _fake_publish
    )
    # extract_determination_wp_code 是纯函数，正常工作，无需 patch
    return published


async def _call(role, body_overrides=None, db=None):
    from app.routers.wp_html_save import PublishToTbRequest, publish_determination_to_tb

    fields = {"sheet_name": "审定表D2-1", "html_data": _valid_html()}
    fields.update(body_overrides or {})
    body = PublishToTbRequest(**fields)
    return await publish_determination_to_tb(
        wp_id=_WP_ID,
        body=body,
        db=db if db is not None else _admin_db(),
        current_user=_make_user(role),
    )


@pytest.mark.asyncio
async def test_publish_emits_confirmed_signal(_patch_deps):
    """admin 发布 → 事件带 publish_confirmed=True + confirmed_by + publish_token。"""
    resp = await _call(UserRole.admin)
    assert resp.published is True
    assert resp.wp_code == "D2-1"
    assert len(_patch_deps) == 1
    extra = _patch_deps[0].extra
    assert extra["publish_confirmed"] is True
    assert extra["confirmed_by"]
    assert extra["publish_token"] == resp.publish_token
    assert extra["wp_code"] == "D2-1"
    # 两行都是可回写科目行
    assert len(extra["parsed_data"]["rows"]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.readonly, UserRole.qc])
async def test_publish_denied_for_non_write_roles(_patch_deps, role):
    """readonly/qc → 403（authorize_wp_edit 查库前即拒），不发布。"""
    db = AsyncMock()
    db.execute = AsyncMock()
    with pytest.raises(HTTPException) as ei:
        await _call(role, db=db)
    assert ei.value.status_code == 403
    assert _patch_deps == []  # 未发布


@pytest.mark.asyncio
async def test_publish_400_for_non_determination_sheet(_patch_deps):
    """非审定表 sheet（无 [D-N]n-1 子码）→ 400，不发布。"""
    with pytest.raises(HTTPException) as ei:
        await _call(UserRole.admin, body_overrides={"sheet_name": "D4-2 明细表"})
    assert ei.value.status_code == 400
    assert _patch_deps == []


@pytest.mark.asyncio
async def test_publish_token_passthrough(_patch_deps):
    """传入 publish_token 时透传（供 handler 幂等 ack）。"""
    resp = await _call(UserRole.admin, body_overrides={"publish_token": "my-token-123"})
    assert resp.publish_token == "my-token-123"
    assert _patch_deps[0].extra["publish_token"] == "my-token-123"


@pytest.mark.asyncio
async def test_publish_400_when_no_audit_rows(_patch_deps):
    """审定表无 audit_rows → 400。"""
    with pytest.raises(HTTPException) as ei:
        await _call(UserRole.admin, body_overrides={"html_data": {"audit_rows": []}})
    assert ei.value.status_code == 400
    assert _patch_deps == []
