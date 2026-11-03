"""「保存为模板」的分享目标（advanced-query-linkage-closure 任务 29，AQ-39；R9.1 页面版与弹窗 💾 三档）。

页面版原先取 ``GET /api/projects`` 的 ``can_edit`` 判定「指定项目共享」「公开」可不可选，而该接口从不下发此字段 ⇒ 两档恒
置灰（B8 浏览器验收，admin 亦然）。现在由 ``GET /api/custom-query/template-share-targets`` 给出本人可分享到的项目。

判据：与保存时对每个分享目标做的 ``require_project_access("edit")``（``deps.assert_project_permission``）同一口径 ——
每个身份 × 每个未删项目都拿门禁的真实结论对拍（已归档 423、无成员 / 级别不足 403 ⇒ 不列）；已删项目不列（界面下拉不含）。
端点经生产注册的 router 真发请求（只 override ``get_current_user`` / ``get_db``）。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi import HTTPException

from app import deps
from app.models.base import ProjectStatus, UserRole
from app.routers import custom_query
from app.services.custom_query.template_scope_guard import template_share_target_ids
from tests.authz_world import AuthzWorld, pg_world, sqlite_world

URL = "/api/custom-query/template-share-targets"


async def _gate_allows(world: AuthzWorld, user: Any, project_id: Any) -> bool:
    """门禁的真实结论（不替换归档守卫与成员级别查询；RLS 设置换成记录）。"""
    try:
        await deps.assert_project_permission(world.db, user, project_id, "edit")
    except HTTPException as exc:
        assert exc.status_code in (403, 423), exc.detail
        return False
    return True


async def _furnish(world: AuthzWorld) -> tuple[dict[str, Any], dict[str, Any]]:
    world.replace_rls()
    world.assert_not_replaced("archive_guard")
    projects = {
        "X": world.target,
        "Y": await world.other_project(),
        "archived": await world.project(name="【测试】分享目标·已归档", status=ProjectStatus.archived),
        "deleted": await world.project(name="【测试】分享目标·已删", is_deleted=True),
        "third": await world.project(name="【测试】分享目标·第三个"),
    }
    users: dict[str, Any] = {}
    edit_x = (await world.member("edit", "auditor")).user
    await world.member("edit", "auditor", project=projects["archived"], user=edit_x)
    await world.member("edit", "auditor", project=projects["deleted"], user=edit_x)
    await world.member("review", "qc", project=projects["third"], user=edit_x)
    users["edit_x"] = edit_x
    users["review"] = (await world.member("review", "qc")).user
    users["readonly"] = (await world.member("readonly", "readonly")).user
    removed = await world.member("edit", "manager")
    removed.member.is_deleted = True  # 成员行已删：门禁不认，分享目标也不列
    await world.db.flush()
    users["removed_member"] = removed.user
    users["manager_role_only"] = await world.user(UserRole.manager)
    users["partner"] = await world.user(UserRole.partner)
    users["edit_y"] = (await world.non_member_with_other_project(global_role=UserRole.manager)).user
    users["admin"] = (await world.admin_non_member()).user
    return users, projects


async def _assert_same_as_gate(world: AuthzWorld) -> dict[str, list[str]]:
    users, projects = await _furnish(world)
    live = {key: p for key, p in projects.items() if not p.is_deleted}
    got: dict[str, list[str]] = {}
    for name, user in users.items():
        targets = await template_share_target_ids(world.db, user)
        got[name] = targets
        assert targets == sorted(targets) and len(set(targets)) == len(targets), f"{name}：按文本排序且不重复"
        for key, project in live.items():
            allowed = await _gate_allows(world, user, project.id)
            assert (str(project.id) in targets) is allowed, (
                f"{name} × 项目 {key}：分享目标 {'含' if str(project.id) in targets else '不含'}，"
                f"而保存时的 edit 门禁{'放行' if allowed else '拒绝'}（两处口径不一致）")
        assert str(projects["deleted"].id) not in targets, f"{name}：已删项目不列"
    by_key = {key: str(p.id) for key, p in projects.items()}
    assert got["edit_x"] == [by_key["X"]], "只有本项目 edit 级成员行的项目（已归档、已删、review 级都不列）"
    assert got["edit_y"] == [by_key["Y"]]
    for name in ("review", "readonly", "removed_member", "manager_role_only", "partner"):
        assert got[name] == [], f"{name}：没有可分享的项目（系统角色 partner / manager 不因角色放行，与门禁一致）"
    assert got["admin"] == sorted([by_key["X"], by_key["Y"], by_key["third"]]), "admin：除已归档、已删外全部"
    return got


async def test_share_targets_equal_the_edit_gate_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    async with sqlite_world(monkeypatch) as world:
        await _assert_same_as_gate(world)


@pytest.mark.pg_only
async def test_share_targets_equal_the_edit_gate_pg(monkeypatch: pytest.MonkeyPatch) -> None:
    async with pg_world(monkeypatch) as world:
        await _assert_same_as_gate(world)


@asynccontextmanager
async def _client(world: AuthzWorld, user: Any):
    async with world.client(custom_query.router, user=user) as client:
        yield client


async def test_endpoint_lists_only_the_users_own_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    async with sqlite_world(monkeypatch) as world:
        users, projects = await _furnish(world)
        async with _client(world, None) as client:
            assert (await client.get(URL)).status_code == 401, "未登录 401"
        async with _client(world, users["edit_x"]) as client:
            response = await client.get(URL)
        assert response.status_code == 200, response.text
        assert response.json() == {"project_ids": [str(projects["X"].id)]}
        async with _client(world, users["readonly"]) as client:
            response = await client.get(URL)
        assert response.status_code == 200 and response.json() == {"project_ids": []}, response.text
        async with _client(world, users["admin"]) as client:
            response = await client.get(URL)
        assert response.status_code == 200, response.text
        assert set(response.json()["project_ids"]) == {str(projects[k].id) for k in ("X", "Y", "third")}
