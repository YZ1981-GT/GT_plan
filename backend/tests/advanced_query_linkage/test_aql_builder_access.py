"""构建器准入（advanced-query-linkage-closure 任务 12；ADR-AQL-08，design §3.4；R3.6、R11.3；变异 #13）。

在 SQLite 权限世界里用真实的用户、项目与成员行判定（不替换 ``builder_access`` 的任何对象，它登记在
``authz_world.PRODUCTION_GATES`` / ``_GUARDED_MODULES``）：

- 系统角色 admin / partner / manager 准入，其余系统角色只有在未删除项目里是项目经理 / 合伙人（edit 级）才准入
  ——只读成员、复核级经理、已删项目里的经理、已删除的成员行都不算（AQ-21）；
- access 接口：admin / partner 不限项目（计数 null）；其余身份的计数 = 构建器作用域（可访问 − 已删项目，与执行时
  同一函数），为 0 时给「您当前没有可访问的项目」；不准入时给含合伙人与项目经理的原因（AQ-29）；
- 路由门禁与 access 接口经同一判定（``GateClient.assert_passed`` 观测生产代码确实执行过）。
"""
from __future__ import annotations

import pytest

from app.models.base import UserRole
from app.models.core import User
from app.routers import query_builder
from app.services.custom_query.builder_access import (
    FORBIDDEN_REASON,
    NO_PROJECT_REASON,
    builder_admission,
)
from tests.authz_world import AuthzWorld, sqlite_world

ADMISSION = "app.services.custom_query.builder_access.builder_admission"
ROUTE_GATE = "app.routers.query_builder.require_query_builder_access"


@pytest.mark.parametrize(("role", "allowed"), [
    (UserRole.admin, True), (UserRole.partner, True), (UserRole.manager, True),
    (UserRole.auditor, False), (UserRole.qc, False), (UserRole.readonly, False),
])
async def test_system_role_admission(role: UserRole, allowed: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    async with sqlite_world(monkeypatch) as world:
        admission = await builder_admission(await world.user(role), world.db)
    assert (admission.allowed, admission.basis) == ((True, "system_role") if allowed else (False, None))


async def _member_on_deleted_project(world: AuthzWorld) -> User:
    deleted = await world.project(name="【测试】已删项目", is_deleted=True)
    return (await world.member("edit", "manager", project=deleted)).user


async def _deleted_member_row(world: AuthzWorld) -> User:
    identity = await world.member("edit", "manager")
    identity.member.is_deleted = True
    await world.db.flush()
    return identity.user


@pytest.mark.parametrize(("case", "allowed"), [
    ("manager-edit", True), ("partner-edit", True), ("manager-review", False), ("auditor-edit", False),
    ("readonly-readonly", False), ("deleted-project", False), ("deleted-member-row", False),
])
async def test_project_member_admission(case: str, allowed: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    """系统角色为 auditor 的成员：只有未删除项目里的（manager | partner, edit）成员行才准入（变异 #13 打红第 1、2 例）。"""
    async with sqlite_world(monkeypatch) as world:
        if case == "deleted-project":
            user = await _member_on_deleted_project(world)
        elif case == "deleted-member-row":
            user = await _deleted_member_row(world)
        else:
            role, level = case.split("-")
            user = (await world.member(level, role)).user
        admission = await builder_admission(user, world.db)
    assert (admission.allowed, admission.basis) == ((True, "project_manager") if allowed else (False, None))


async def _access(world: AuthzWorld, user: User) -> dict:
    async with world.client(query_builder.router, user=user) as client:
        response = await client.get("/api/query/access")
        client.assert_passed(ADMISSION, times=1)
    assert response.status_code == 200, response.text
    return response.json()


async def test_access_counts_the_builder_scope_and_explains_empty_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    async with sqlite_world(monkeypatch) as world:
        # 项目经理：X 上（manager, edit），另在一个未删项目上只读、在一个已删项目上也有成员行 ⇒ 作用域 2（已删不计）
        pm = (await world.member("edit", "manager")).user
        other = await world.other_project()
        await world.member("readonly", "readonly", project=other, user=pm)
        deleted = await world.project(name="【测试】已删项目", is_deleted=True)
        await world.member("edit", "manager", project=deleted, user=pm)
        assert await _access(world, pm) == {
            "allowed": True, "basis": "project_manager", "reason": None, "all_projects": False,
            "accessible_project_count": 2}
        # 系统经理、没有任何成员行：准入但作用域为空
        assert await _access(world, await world.user(UserRole.manager)) == {
            "allowed": True, "basis": "system_role", "reason": NO_PROJECT_REASON, "all_projects": False,
            "accessible_project_count": 0}
        # 合伙人不限项目
        assert await _access(world, await world.user(UserRole.partner)) == {
            "allowed": True, "basis": "system_role", "reason": None, "all_projects": True,
            "accessible_project_count": None}
        # 不准入：原因含合伙人与项目经理（AQ-29）
        denied = await _access(world, (await world.readonly_member()).user)
    assert denied == {"allowed": False, "basis": None, "reason": FORBIDDEN_REASON, "all_projects": False,
                      "accessible_project_count": 0}
    assert "合伙人" in FORBIDDEN_REASON and "项目经理" in FORBIDDEN_REASON


async def test_route_gate_uses_the_same_admission(monkeypatch: pytest.MonkeyPatch) -> None:
    async with sqlite_world(monkeypatch) as world:
        pm = (await world.member("edit", "manager")).user
        auditor = (await world.member("edit", "auditor")).user
        async with world.client(query_builder.router, user=pm) as client:
            allowed = await client.get("/api/query/schema")
            client.assert_passed(ROUTE_GATE, times=1)
            client.assert_passed(ADMISSION, times=1)
        async with world.client(query_builder.router, user=auditor) as client:
            denied = await client.get("/api/query/schema")
            client.assert_passed(ADMISSION, times=1)
    assert allowed.status_code == 200, allowed.text
    assert denied.status_code == 403, denied.text
    assert denied.json()["detail"] == {"error_code": "ROLE_FORBIDDEN", "message": FORBIDDEN_REASON}
