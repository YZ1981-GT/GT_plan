"""全部可见底稿（spec platform-perf-hotspots R5）：与分页端点逐页拼接逐条相等。

``list_all_workpapers`` 复用分页端点的可见集 / 业务过滤 / 去重 / 项结构，一次取完；三种可见性
（admin / supervisor / restricted）、带过滤、空可见集下都与 ``list_workpapers`` 逐页拼接逐条相等。
真实 PostgreSQL，每用例事务回滚。
"""
from __future__ import annotations

from uuid import UUID

import pytest

from app.models.workpaper_models import WpFileStatus
from app.routers import working_paper as wp_router
from app.services.wp_visibility.contracts import VisibilityContext, VisibilityRole
from app.services.wp_visibility.workpaper_list_query import (
    WorkpaperListFilters,
    WorkpaperListQueryService,
)

from ._factories import IS_PG, mk_project, mk_row_task, mk_staff, mk_user, mk_working_paper, mk_wp_index

pytestmark = [pytest.mark.skipif(not IS_PG, reason="need PostgreSQL"), pytest.mark.asyncio]


def _ctx(user_id: UUID, project_id: UUID, role: VisibilityRole, scope=()) -> VisibilityContext:
    is_admin = role is VisibilityRole.admin
    return VisibilityContext(
        user_id=user_id, project_id=project_id, role=role, is_admin=is_admin,
        scope_cycles=frozenset() if is_admin else frozenset(scope),
    )


async def _world(s):
    """D 循环：本人主编 / 他人主编 / 未生成 / 程序行指派给本人 / 文件已删；K 循环：本人主编。"""
    proj = await mk_project(s)
    user, other, admin = await mk_user(s), await mk_user(s), await mk_user(s, role="admin")
    staff = await mk_staff(s, user_id=user.id)

    async def lead(code: str, cycle: str, owner, **kw):
        wi = await mk_wp_index(s, proj.id, wp_code=code, audit_cycle=cycle)
        wp = await mk_working_paper(s, proj.id, wi.id, **kw)
        wp.assigned_to = owner.id
        return wi, wp

    _, wp_d21 = await lead("D2-1", "D", user)
    wp_d21.status = WpFileStatus.draft
    await lead("D2-2", "D", other)
    await mk_wp_index(s, proj.id, wp_code="D2-3", audit_cycle="D")           # 未生成（nullable wp）
    wi_row = await mk_wp_index(s, proj.id, wp_code="D2-4", audit_cycle="D")
    await mk_working_paper(s, proj.id, wi_row.id)
    await mk_row_task(s, proj.id, wi_row.id, sheet_key="D2A", sheet_name="页", assignee_staff_id=staff.id)
    await lead("D1-1", "D", user, is_deleted=True)                            # 文件已删 ⇒ 按未生成计
    await lead("K1-1", "K", user)
    await mk_wp_index(s, proj.id, wp_code="D9-9", audit_cycle="D", is_deleted=True)  # 索引已删 ⇒ 不出现
    await s.flush()
    return proj, user, admin


async def _concat_pages(svc: WorkpaperListQueryService, ctx, filters=None) -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        out = await svc.list_workpapers(ctx, page=page, page_size=2, sort="wp_code", sort_dir="asc", filters=filters)
        items.extend(out["items"])
        if not out["items"] or len(items) >= out["total"]:
            return items
        page += 1


@pytest.mark.parametrize("role", ["admin", "supervisor", "restricted"])
@pytest.mark.parametrize("filters", [None, WorkpaperListFilters(audit_cycle="D"),
                                     WorkpaperListFilters(file_status="draft")], ids=["none", "cycle", "file"])
async def test_all_equals_concatenated_pages(session, role, filters) -> None:
    proj, user, admin = await _world(session)
    ctx = (_ctx(admin.id, proj.id, VisibilityRole.admin) if role == "admin"
           else _ctx(user.id, proj.id, VisibilityRole(role), {"D"}))
    svc = WorkpaperListQueryService(session)
    got = await svc.list_all_workpapers(ctx, filters=filters)
    expected = await _concat_pages(svc, ctx, filters)
    assert set(got) == {"items", "total"}
    assert got["items"] == expected
    assert got["total"] == len(expected)


async def test_world_actually_differs_by_role(session) -> None:
    """三种可见性的结果确实不同（否则上面的逐页对拍对角色不敏感）。"""
    proj, user, admin = await _world(session)
    svc = WorkpaperListQueryService(session)
    codes = {}
    for role, ctx in {
        "admin": _ctx(admin.id, proj.id, VisibilityRole.admin),
        "supervisor": _ctx(user.id, proj.id, VisibilityRole.supervisor, {"D"}),
        "restricted": _ctx(user.id, proj.id, VisibilityRole.restricted, {"D"}),
    }.items():
        codes[role] = [it["wp_code"] for it in (await svc.list_all_workpapers(ctx))["items"]]
    assert codes["admin"] == ["D1-1", "D2-1", "D2-2", "D2-3", "D2-4", "K1-1"]
    assert "K1-1" not in codes["supervisor"] and "K1-1" not in codes["restricted"]
    assert set(codes["restricted"]) < set(codes["admin"])
    assert "D2-2" not in codes["restricted"]  # 他人主编、未委派给本人


async def test_empty_visible_set_returns_empty(session) -> None:
    proj, user, _ = await _world(session)
    out = await WorkpaperListQueryService(session).list_all_workpapers(
        _ctx(user.id, proj.id, VisibilityRole.restricted, set()))
    assert out == {"items": [], "total": 0}


async def test_route_classifies_caller_and_returns_service_output(session) -> None:
    """路由按服务端角色分类（admin ⇒ 全部），返回与服务层相同的 {items,total}。"""
    proj, _, admin = await _world(session)
    got = await wp_router.list_all_workpapers(
        project_id=proj.id, audit_cycle=None, index_status=None, file_status=None,
        assigned_to=None, db=session, current_user=admin,
    )
    expected = await WorkpaperListQueryService(session).list_all_workpapers(
        _ctx(admin.id, proj.id, VisibilityRole.admin))
    assert got == expected
    assert got["total"] == 6
