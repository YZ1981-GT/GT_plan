"""审定表→试算表显式发布端点：writeback_rows 预算行路径扩展测试（M0 / Task 1）

spec: .kiro/specs/tb-writeback-explicit-publish-gate/  需求 6/7/4/3

验证 ``publish_determination_to_tb`` 的入参向后兼容扩展：
  - 路径②（writeback_rows）：前端预算好的最终审定数直传，跳过三分量重算，
    parsed_data.rows 各科目 audited == 传入值（不被 未审+AJE+RJE 覆盖）。
  - amount_kind="occurrence"（发生额）语义标注透传进 extra.amount_kinds。
  - 路径①（html_data.audit_rows 三分量）零回归：audited == 未审+AJE+RJE。
  - 多科目 writeback_rows：parsed_data.rows 全含。
  - sheet_name 不可解 [D-N]{n}-1 → 400。
  - 两路径都为空 → 400（无可发布内容）。
  - 两路径同给 → writeback_rows 优先。
  - 幂等：同内容 writeback_rows 两次调用合成同一 publish_token（供 handler tb_publish_ack 去重）。

均直调 handler 函数（与 test_publish_determination_to_tb.py 同风格），mock db +
patch 取数/year/event_bus.publish，断言真实端点逻辑而非重实现。
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


@pytest.fixture(autouse=True)
def _patch_deps(monkeypatch):
    """patch 审定数取数 + year + event_bus.publish（避免真实 DB/事件总线）。

    _fake_tb 故意返回非零三分量，用来证明 writeback_rows 路径**不**触发三分量重算
    （若被覆盖，audited 会变），同时供三分量路径零回归断言。
    """
    async def _fake_tb(audit_rows, *, db, project_id):
        # 若路径①被走到，为每行提供三分量默认（证明零回归口径）。
        out = {}
        for r in audit_rows:
            if isinstance(r, dict) and r.get("id"):
                out[r["id"]] = {"current_unadjusted": 999, "sys_aje": 1, "sys_rje": 0}
        return out

    async def _fake_year(db, project_id):
        return 2025

    published = []

    async def _fake_publish(payload):
        published.append(payload)

    monkeypatch.setattr(
        "app.services.wp_audit_sheet_tb_service.fetch_audit_sheet_tb_values", _fake_tb
    )
    monkeypatch.setattr(
        "app.routers.wp_html_save.fetch_project_audit_year", _fake_year
    )
    monkeypatch.setattr(
        "app.services.event_bus.event_bus.publish", _fake_publish
    )
    return published


async def _call(role, body_overrides, db=None):
    from app.routers.wp_html_save import PublishToTbRequest, publish_determination_to_tb

    fields = {"sheet_name": "审定表K12-1"}
    fields.update(body_overrides or {})
    body = PublishToTbRequest(**fields)
    return await publish_determination_to_tb(
        wp_id=_WP_ID,
        body=body,
        db=db if db is not None else _admin_db(),
        current_user=_make_user(role),
    )


@pytest.mark.asyncio
async def test_writeback_rows_uses_prebudgeted_audited(_patch_deps):
    """writeback_rows 路径：audited 直取传入值，不被三分量重算覆盖。"""
    resp = await _call(
        UserRole.admin,
        {"writeback_rows": [{"account_code": "6301", "audited_amount": 12345.67}]},
    )
    assert resp.published is True
    assert resp.wp_code == "K12-1"
    assert len(_patch_deps) == 1
    extra = _patch_deps[0].extra
    assert extra["publish_confirmed"] is True
    assert extra["confirmed_by"]
    rows = extra["parsed_data"]["rows"]
    assert len(rows) == 1
    assert rows[0]["account_code"] == "6301"
    # 关键：== 传入值 12345.67，而非三分量 999+1+0=1000
    assert rows[0]["audited_amount"] == pytest.approx(12345.67)


@pytest.mark.asyncio
async def test_writeback_rows_occurrence_kind_passthrough(_patch_deps):
    """amount_kind="occurrence" 透传进 extra.amount_kinds。"""
    await _call(
        UserRole.admin,
        {"writeback_rows": [
            {"account_code": "6301", "audited_amount": 100.0, "amount_kind": "occurrence"},
        ]},
    )
    extra = _patch_deps[0].extra
    assert extra["amount_kinds"] == {"6301": "occurrence"}


@pytest.mark.asyncio
async def test_writeback_rows_multi_account(_patch_deps):
    """多科目 writeback_rows：parsed_data.rows 全含各自审定数。"""
    resp = await _call(
        UserRole.admin,
        {"sheet_name": "审定表K1-1", "writeback_rows": [
            {"account_code": "1221", "audited_amount": 500.0},
            {"account_code": "1231", "audited_amount": -30.0, "amount_kind": "balance"},
        ]},
    )
    assert resp.wp_code == "K1-1"
    rows = _patch_deps[0].extra["parsed_data"]["rows"]
    by_code = {r["account_code"]: r["audited_amount"] for r in rows}
    assert by_code["1221"] == pytest.approx(500.0)
    assert by_code["1231"] == pytest.approx(-30.0)
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_audit_rows_three_component_no_regression(_patch_deps):
    """路径①三分量零回归：audited == 未审(1000)+AJE(50)+RJE(0)=1050；无 amount_kinds。"""
    resp = await _call(
        UserRole.admin,
        {"sheet_name": "审定表D2-1", "html_data": {"audit_rows": [
            {"id": "r1", "account_code": "1122", "current_unadjusted": 1000, "adj_amount": 50, "reclass_amount": 0},
        ]}},
    )
    assert resp.wp_code == "D2-1"
    rows = _patch_deps[0].extra["parsed_data"]["rows"]
    assert len(rows) == 1
    assert rows[0]["account_code"] == "1122"
    assert rows[0]["audited_amount"] == pytest.approx(1050.0)
    # 路径①不携带语义标注
    assert "amount_kinds" not in _patch_deps[0].extra


@pytest.mark.asyncio
async def test_writeback_rows_takes_priority_over_html_data(_patch_deps):
    """两路径同给 → writeback_rows 优先（三分量被跳过）。"""
    resp = await _call(
        UserRole.admin,
        {
            "sheet_name": "审定表D2-1",
            "writeback_rows": [{"account_code": "6301", "audited_amount": 777.0}],
            "html_data": {"audit_rows": [
                {"id": "r1", "account_code": "1122", "current_unadjusted": 1000, "adj_amount": 50},
            ]},
        },
    )
    rows = _patch_deps[0].extra["parsed_data"]["rows"]
    assert len(rows) == 1
    assert rows[0]["account_code"] == "6301"
    assert rows[0]["audited_amount"] == pytest.approx(777.0)


@pytest.mark.asyncio
async def test_400_when_sheet_name_unresolvable(_patch_deps):
    """sheet_name 无 [D-N]{n}-1 子码 → 400，不发布。"""
    with pytest.raises(HTTPException) as ei:
        await _call(
            UserRole.admin,
            {"sheet_name": "K12 明细表", "writeback_rows": [
                {"account_code": "6301", "audited_amount": 1.0},
            ]},
        )
    assert ei.value.status_code == 400
    assert _patch_deps == []


@pytest.mark.asyncio
async def test_400_when_both_paths_empty(_patch_deps):
    """writeback_rows 与 html_data 都空 → 400，不发布。"""
    with pytest.raises(HTTPException) as ei:
        await _call(UserRole.admin, {"sheet_name": "审定表K12-1"})
    assert ei.value.status_code == 400
    assert _patch_deps == []


@pytest.mark.asyncio
async def test_writeback_rows_empty_list_falls_back_and_400(_patch_deps):
    """writeback_rows=[] 空列表回退路径①，html_data 缺失 → 400。"""
    with pytest.raises(HTTPException) as ei:
        await _call(UserRole.admin, {"sheet_name": "审定表K12-1", "writeback_rows": []})
    assert ei.value.status_code == 400
    assert _patch_deps == []


@pytest.mark.asyncio
async def test_idempotent_token_stable_for_same_writeback_rows(_patch_deps):
    """同内容 writeback_rows 两次调用合成同一 publish_token（供 handler tb_publish_ack 去重）。"""
    body = {"sheet_name": "审定表K12-1", "writeback_rows": [
        {"account_code": "6301", "audited_amount": 100.0},
        {"account_code": "6302", "audited_amount": 200.0},
    ]}
    r1 = await _call(UserRole.admin, dict(body))
    r2 = await _call(UserRole.admin, dict(body))
    assert r1.publish_token == r2.publish_token
    assert _patch_deps[0].extra["publish_token"] == _patch_deps[1].extra["publish_token"]


@pytest.mark.asyncio
async def test_explicit_publish_token_passthrough_for_writeback_rows(_patch_deps):
    """显式传 publish_token 时透传（writeback_rows 路径）。"""
    resp = await _call(
        UserRole.admin,
        {"publish_token": "occ-token-9", "writeback_rows": [
            {"account_code": "6301", "audited_amount": 1.0, "amount_kind": "occurrence"},
        ]},
    )
    assert resp.publish_token == "occ-token-9"
    assert _patch_deps[0].extra["publish_token"] == "occ-token-9"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.readonly, UserRole.qc])
async def test_writeback_rows_denied_for_non_write_roles(_patch_deps, role):
    """readonly/qc → 403（authorize_wp_edit 拦下），不发布。"""
    db = AsyncMock()
    db.execute = AsyncMock()
    with pytest.raises(HTTPException) as ei:
        await _call(
            role,
            {"writeback_rows": [{"account_code": "6301", "audited_amount": 1.0}]},
            db=db,
        )
    assert ei.value.status_code == 403
    assert _patch_deps == []
