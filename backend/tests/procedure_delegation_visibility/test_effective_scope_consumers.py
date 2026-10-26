# -*- coding: utf-8 -*-
"""有效循环范围的使用方（spec procedure-trim-generation-delegation-chain 需求 5 / 任务 14）。

用户裁决（2026-10-24）：经理、合伙人、质控、EQCR 默认看全部循环；审计员按团队分配时勾选的循环。
角色分类器、``get_user_scope_cycles``（试算表 / 调整 / 附注过滤）与委派校验同一来源
（``effective_scope.resolve_member_scope``）。

- 分类器：委派角色认中文别名（原先只认英文角色码）；主管范围 = 全部循环（原先 = ``project_users.scope_cycles``，
  主管也被截断 —— 旧用例按裁决改写，见 ``test_role_classifier``）；受限范围 = 团队分配勾选 ∪ 委派扩大。
  同一人员在同一项目只能有一条有效委派（``idx_assignment_project_staff`` 部分唯一索引），多份人员记录仍按受限。
- ``get_user_scope_cycles``：主管 ⇒ ``None``（不限）；受限 ⇒ 列表，可以为空（原先空 = 不限）。
- 附注目录树 / 就绪度：空范围、对不上章节的范围都返回空（原先对不上章节就不过滤 = 全部放行）。
- 调整分录：取循环科目失败按「一个都不对应」处理（原先异常即跳过过滤 = 全部放行）。
- 委派通知：受限成员没勾选循环写「未勾选」，不再写「全部」。

分类器与 ``get_user_scope_cycles`` 用真库（外层事务回滚）；路由过滤直接调用路由函数、替换取数层（只验过滤口径）。
"""
from __future__ import annotations

import types
from uuid import uuid4

import pytest

from app.core.pagination import PaginationParams
from app.deps import get_user_scope_cycles
from app.routers import adjustments as adj_router
from app.routers import disclosure_notes as dn_router
from app.services.assignment_service import _assignment_cycles_text
from app.services.mapping_service import get_codes_by_cycles
from app.services.wp_visibility.contracts import VisibilityRole
from app.services.wp_visibility.effective_scope import STANDARD_CYCLES
from app.services.wp_visibility.role_classifier import VisibilityRoleClassifier

from ._factories import IS_PG, mk_assignment, mk_project, mk_project_user, mk_staff, mk_user, mk_wp_index

pg = pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")


async def _member(s, project, *, roles=("auditor",), cycles=None, scope=None, system_role="auditor"):
    user = await mk_user(s, system_role)
    staff = await mk_staff(s, user_id=user.id)
    for role in roles:
        a = await mk_assignment(s, project.id, staff.id, role=role)
        a.assigned_cycles = list(cycles) if cycles else None
    await mk_project_user(s, project.id, user.id, scope_cycles=scope)
    await s.flush()
    return user


@pg
@pytest.mark.asyncio
async def test_classifier_supervisor_alias_multi_assignment_and_restricted_union(session):
    s = session
    project = await mk_project(s)
    await mk_wp_index(s, project.id, wp_code="Q1", audit_cycle="Q")
    alias_manager = await _member(s, project, roles=("项目经理",), scope="")
    qc_with_cycles = await _member(s, project, roles=("qc",), cycles=["D"], scope="E")
    auditor = await _member(s, project, cycles=["D"], scope="E")
    bare = await _member(s, project)
    clf = VisibilityRoleClassifier(s)

    for user in (alias_manager, qc_with_cycles):
        ctx = await clf.classify(user, project.id)
        assert ctx.role is VisibilityRole.supervisor
        assert ctx.scope_cycles == STANDARD_CYCLES | {"Q"}, "主管看本项目全部循环（含底稿索引里出现的），不受勾选截断"
    ctx = await clf.classify(auditor, project.id)
    assert ctx.role is VisibilityRole.restricted
    assert ctx.scope_cycles == {"D", "E"}, "团队分配勾选 ∪ 委派扩大"
    ctx = await clf.classify(bare, project.id)
    assert ctx.role is VisibilityRole.restricted and ctx.scope_cycles == frozenset()


@pg
@pytest.mark.asyncio
async def test_get_user_scope_cycles_none_only_for_unrestricted(session):
    s = session
    project = await mk_project(s)
    admin = await mk_user(s, "admin")
    partner = await mk_user(s, "partner")
    manager = await _member(s, project, roles=("manager",))
    eqcr_alias = await _member(s, project, roles=("独立复核合伙人",))
    auditor = await _member(s, project, cycles=["E", "D"])
    bare = await _member(s, project)
    for user in (admin, partner, manager, eqcr_alias):
        assert await get_user_scope_cycles(user, project.id, s) is None
    assert await get_user_scope_cycles(auditor, project.id, s) == ["D", "E"]
    assert await get_user_scope_cycles(bare, project.id, s) == [], "受限且没勾选 ⇒ 空列表（原先返回 None = 不限）"


# ── 路由过滤口径：直接调用路由函数，替换取数层 ─────────────────────────────────────

_TREE = [{"note_section": "五、1"}, {"note_section": "五、2"}, {"note_section": "八、1"}]


def _user():
    return types.SimpleNamespace(id=uuid4(), role=types.SimpleNamespace(value="auditor"))


@pytest.fixture
def notes_env(monkeypatch):
    from app.services import note_readiness_service

    class _Engine:
        def __init__(self, db):
            pass

        async def get_notes_tree(self, project_id, year):
            return [dict(n) for n in _TREE]

    async def _findings(db, project_id, year):
        return {}, None

    async def _readiness(db, project_id, year):
        return {"summary": {"total": len(_TREE)}, "sections": [dict(n) for n in _TREE]}

    scope: dict = {"value": None}

    async def _scope(user, project_id, db):
        return scope["value"]

    monkeypatch.setattr(dn_router, "DisclosureEngine", _Engine)
    monkeypatch.setattr(note_readiness_service, "latest_findings_by_section", _findings)
    monkeypatch.setattr(note_readiness_service, "build_readiness", _readiness)
    monkeypatch.setattr(dn_router, "get_user_scope_cycles", _scope)
    return scope


@pytest.mark.asyncio
@pytest.mark.parametrize(("cycles", "expected"), [
    (None, ["五、1", "五、2", "八、1"]),
    (["E"], ["五、1"]),
    ([], []),
    (["A"], []),  # A 循环在映射里没有附注章节：原先不过滤 = 全部放行
])
async def test_notes_tree_and_readiness_filter_fail_closed(notes_env, cycles, expected):
    notes_env["value"] = cycles
    pid = uuid4()
    tree = await dn_router.get_notes_tree(project_id=pid, year=2025, db=None, current_user=_user())
    assert [n["note_section"] for n in tree] == expected
    data = await dn_router.get_notes_readiness(project_id=pid, year=2025, db=None, current_user=_user())
    assert [n["note_section"] for n in data["sections"]] == expected


@pytest.mark.asyncio
async def test_adjustments_filter_fails_closed_when_cycle_codes_unreadable(monkeypatch):
    d_code = sorted(await get_codes_by_cycles(uuid4(), ["D"]))[0]
    entries = [
        {"id": "a", "line_items": [{"standard_account_code": d_code}]},
        {"id": "b", "line_items": [{"standard_account_code": "ZZZZ"}]},
    ]

    async def _list_entries(self, project_id, year, **kw):
        return {"items": [dict(e) for e in entries], "total": len(entries)}

    async def _scope(user, project_id, db):
        return ["D"]

    async def _enrich(db, project_id, items):
        return None

    monkeypatch.setattr(adj_router.AdjustmentService, "list_entries", _list_entries)
    monkeypatch.setattr(adj_router, "get_user_scope_cycles", _scope)
    monkeypatch.setattr(adj_router, "_enrich_adjustment_list", _enrich)
    kwargs = dict(project_id=uuid4(), year=2025, adjustment_type=None, review_status=None, origin=None,
                  fields=None, pagination=PaginationParams(page=1, page_size=50), db=None, current_user=_user())
    out = await adj_router.list_adjustments(**kwargs)
    assert [e["id"] for e in out["items"]] == ["a"] and out["total"] == 1

    async def _boom(project_id, cycles):
        raise RuntimeError("映射文件读取失败")

    monkeypatch.setattr(adj_router, "get_codes_by_cycles", _boom)
    out = await adj_router.list_adjustments(**kwargs)
    assert out["items"] == [] and out["total"] == 0, "取循环科目失败不得放行全部分录"


def test_assignment_notification_cycles_text():
    assert _assignment_cycles_text("manager", None) == "全部"
    assert _assignment_cycles_text("项目经理", []) == "全部"
    assert _assignment_cycles_text("auditor", ["E", "D"]) == "D, E"
    assert _assignment_cycles_text("auditor", None).startswith("未勾选"), "受限成员没勾选循环看不到底稿，不是「全部」"
