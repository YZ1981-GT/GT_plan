"""Phase 8 Task 8 鉴权定级的端点级守卫：该放行的角色真能用，该拦的真拦住。

背景（2026-10-19 复核）：补项目级鉴权时，复核 / 发起签署 / 程序裁剪 / 执行校验也被挂成 edit，而 edit 门只放行
edit 级成员与 admin ⇒ review 级成员会被 403。这几个写操作定为 review 门：按 ``assignment_service.ROLE_MAP``，
合伙人（含签字合伙人）、经理、审计员 / 助理是 edit 级（partner-manager-edit-permission 起），质控、EQCR 是 review 级，
review 门对两类都放行；不收紧为 edit，是为了让 review 级的质控 / EQCR 继续能用（需求 9.4）。
``test_phase8_endpoint_auth_fires`` 只测「不带令牌被拒」，测不出「该放行的人被拦」这一类，所以单独钉住。

做法（memory ㉕；partner-manager-edit-permission 需求 12.1）：请求经权限世界（``tests/authz_world.py``）真发。
身份是世界里的真实用户、成员行与委派：成员行取 ``ROLE_MAP`` 对委派角色给出的值（未登记角色取 ``UNMAPPED_ROLE``），
并带一条该角色的现行委派；判定由生产的 ``require_project_access`` / ``assert_project_permission`` 作出，门禁、归档
守卫都不替换，每个请求都核对生产门禁的代码确实执行过。可替换的只有当前用户、数据库会话、RLS
上下文与业务 service（打桩计数：放行恰 1 次、拒绝 0 次）。

挂载：四个 router 按生产注册挂；程序裁剪 / 标记程序完成所在的 ``wp_procedures.router`` 在生产注册时另挂底稿可见性门
``dedicated_wp_gate``（procedure-delegation-visibility-isolation，先于项目级门禁执行），本文件只测项目级定级，这个
router 按其自身声明挂、不带这道门（与改写前相同）：可见性门的拒绝路径经独立会话（``app.core.database.async_session``）
向配置的数据库写安全审计 outbox，测试走到它就是往开发库写；它的结论由该 spec 的测试覆盖。
``test_wp_procedures_registration_adds_only_the_visibility_gate`` 钉住「只少了这一道」。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.models.base import PermissionLevel, ProjectUserRole
from app.routers import review_workflow, wp_cross_check, wp_procedures
from app.routers._wp_gate import dedicated_wp_gate
from app.services.assignment_service import EQCR_ROLE_ALIASES, ROLE_MAP, map_assignment_role
from tests.authz_world import (
    TARGET_PROJECT_ID, AuthzWorld, Identity, ServiceStub, build_app, production_registrations, sqlite_world,
)
from tests.role_map_expected import EXPECTED_EQCR_ALIASES, EXPECTED_ROLE_MAP

PID = TARGET_PROJECT_ID
OTHER = uuid.UUID("22222222-2222-2222-2222-222222222222")
WP = "33333333-3333-3333-3333-333333333333"
PROC = "44444444-4444-4444-4444-444444444444"

GATE = "app.deps.assert_project_permission"
GATE_DENIED = {"detail": "权限不足"}  # assert_project_permission 的 403 响应体
NOT_SELF = {"detail": "只能签署或查看本人的独立性声明"}
UNREGISTERED = "观察员"  # 未登记的委派角色 → UNMAPPED_ROLE（readonly, readonly）

# 需求 9.4 的身份分组；别名取自需求 2.5 期望表（不读生产代码），成员行取生产 ROLE_MAP 的值
EDIT_ALIASES = sorted(k for k, (_, lv) in EXPECTED_ROLE_MAP.items() if lv == "edit")  # 合伙人 / 经理 / 审计员别名
REVIEW_ALIASES = sorted(k for k, (_, lv) in EXPECTED_ROLE_MAP.items() if lv == "review")  # 质控 / EQCR 别名

_REGISTERED_ROUTERS = (  # 生产注册不附加依赖的四个 router
    review_workflow.router, review_workflow.signing_router, review_workflow.my_signing_router, wp_cross_check.router,
)
_RW, _SIG = review_workflow.ReviewWorkflowService, review_workflow.IndependenceSigningService
_PROC = wp_procedures.WpProcedureService
# 桩名 → （所属对象，属性，返回值）
_BUSINESS = {
    "save_review": (_RW, "save_review", {"saved": True}),
    "link_conversation": (_RW, "link_conversation", True),
    "unlink_conversation": (_RW, "unlink_conversation", True),
    "initiate_signing": (_SIG, "initiate_signing", {"created": 0}),
    "sign": (_SIG, "sign", {"success": True}),
    "get_my_pending_tasks": (_SIG, "get_my_pending_tasks", []),
    "trim_procedure": (_PROC, "trim_procedure", {"id": PROC}),
    "mark_complete": (_PROC, "mark_complete", {"id": PROC}),
    "recalc_quality_score": (wp_procedures, "recalc_quality_score", None),
    "cross_check_execute": (wp_cross_check.CrossCheckService, "execute", []),
}

_SUMMARY = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "errors": 0}
# (说明, METHOD, 路径, 请求体, 放行时的响应体, 放行时各业务桩的调用次数) —— review 级成员（质控 / EQCR）必须能用的
# 写操作，edit 级成员同样放行
_REVIEW_WRITES = [
    ("复核保存", "post", f"/api/projects/{PID}/review-workflow/2025/save",
     {"template_code": "A17-1", "items": [], "opinion": "", "submit": False}, {"saved": True}, {"save_review": 1}),
    ("关联复核对话", "post", f"/api/projects/{PID}/review-workflow/2025/link-conversation",
     {"conversation_id": str(OTHER), "checklist_ref": "1"}, {"success": True}, {"link_conversation": 1}),
    ("取消关联", "post", f"/api/projects/{PID}/review-workflow/2025/unlink-conversation?conversation_id={OTHER}",
     None, {"success": True}, {"unlink_conversation": 1}),
    ("发起独立性签署", "post", f"/api/projects/{PID}/signing/2025/initiate?template_code=A17-7", None,
     {"created": 0}, {"initiate_signing": 1}),
    ("程序裁剪", "patch", f"/api/projects/{PID}/workpapers/{WP}/procedures/{PROC}/trim", {"reason": "不适用"},
     {"id": PROC}, {"trim_procedure": 1, "recalc_quality_score": 1}),
    ("执行跨表校验", "post", f"/api/projects/{PID}/cross-check/execute", {"year": 2025, "trigger": "sign_off"},
     {"results": [], "summary": _SUMMARY}, {"cross_check_execute": 1}),
]
_IDS = [c[0] for c in _REVIEW_WRITES]
_DENY_CASES = [c[:4] for c in _REVIEW_WRITES]
_ALLOW_ARGS = ("alias", "name", "method", "path", "body", "expected", "calls")


def _allow_cases(aliases: list[str]) -> list:
    return [pytest.param(alias, *case, id=f"{case[0]}-{alias}") for alias in aliases for case in _REVIEW_WRITES]


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch) as w:
        yield w


def _stub_business(world: AuthzWorld) -> dict[str, ServiceStub]:
    return {key: world.stub(owner, attr, returns=value) for key, (owner, attr, value) in _BUSINESS.items()}


def _counts(stubs: dict[str, ServiceStub]) -> dict[str, int]:
    return {key: stub.count for key, stub in stubs.items() if stub.count}


async def _delegated(world: AuthzWorld, alias: str) -> Identity:
    """委派为 ``alias`` 的成员（全局角色 auditor）：成员行取 ROLE_MAP 对该角色给出的值（未登记取 UNMAPPED_ROLE），
    另建一条该角色的现行委派（``eqcr_assignment`` 按任意委派角色建人员库记录与委派）。"""
    role, level = map_assignment_role(alias)
    identity = await world.member(level, role)
    await world.eqcr_assignment(alias, user=identity.user)
    return identity


def _member_row(identity: Identity) -> tuple[str, str]:
    return identity.member.role.value, identity.member.permission_level.value


def _phase8_app() -> FastAPI:
    """四个 router 按生产注册挂；``wp_procedures.router`` 按自身声明挂，不带生产注册附加的可见性门（见模块 docstring）。"""
    api = build_app(*_REGISTERED_ROUTERS)
    api.include_router(wp_procedures.router)
    return api


async def _send(world: AuthzWorld, user, method: str, path: str, body):
    async with world.client_for_app(_phase8_app(), user=user) as client:
        response = await client.request(method.upper(), path, **({"json": body} if body is not None else {}))
    return response, client


def test_premise_role_map_matches_expected_table() -> None:
    """前提：``ROLE_MAP`` 逐键等于需求 2.5 期望表（``tests/role_map_expected.py``）—— 合伙人（含签字合伙人）、经理、
    审计员 / 助理是 edit 级，质控、EQCR 是 review 级；取值为 (partner, review) 的键恰是 EQCR 别名集合。
    增删任一键、改动任一取值都打红：ROLE_MAP 一变，本文件的定级理由就要重审。"""
    actual, expected = set(ROLE_MAP), set(EXPECTED_ROLE_MAP)
    assert actual == expected, (
        f"ROLE_MAP 的键与期望表不一致：多出 {sorted(actual - expected)}，缺少 {sorted(expected - actual)}")
    for key, (want_role, want_level) in EXPECTED_ROLE_MAP.items():
        role, level = ROLE_MAP[key]
        assert (type(role), type(level)) == (ProjectUserRole, PermissionLevel), (
            f"{key}：取值类型为 {type(role).__name__} / {type(level).__name__}")
        assert (role.value, level.value) == (want_role, want_level), (
            f"{key}：ROLE_MAP 为 ({role.value}, {level.value})，期望表为 ({want_role}, {want_level})")
    partner_review = {k for k, (r, lv) in ROLE_MAP.items() if (r.value, lv.value) == ("partner", "review")}
    assert partner_review == EXPECTED_EQCR_ALIASES, (
        f"取值为 (partner, review) 的键 {sorted(partner_review)} 不等于 EQCR 别名集合 {sorted(EXPECTED_EQCR_ALIASES)}")
    assert EQCR_ROLE_ALIASES == EXPECTED_EQCR_ALIASES, f"EQCR_ROLE_ALIASES 为 {sorted(EQCR_ROLE_ALIASES)}"


def test_wp_procedures_registration_adds_only_the_visibility_gate() -> None:
    """``_phase8_app`` 与生产注册的唯一差别：``wp_procedures.router`` 少挂了生产注册附加的 ``dedicated_wp_gate``。
    生产注册对它再加别的依赖、前缀或参数即打红（须重审本文件的挂载口径）；另外四个 router 生产注册不附加依赖。"""
    registrations = production_registrations()
    procedures = [kwargs for router, kwargs in registrations if router is wp_procedures.router]
    assert [(sorted(set(kw) - {"tags"}), [d.dependency for d in kw["dependencies"]]) for kw in procedures] == [
        (["dependencies"], [dedicated_wp_gate])]
    for router in _REGISTERED_ROUTERS:
        added = [kwargs.get("dependencies") or [] for registered, kwargs in registrations if registered is router]
        assert added == [[]], router.prefix


@pytest.mark.parametrize(_ALLOW_ARGS, _allow_cases(REVIEW_ALIASES))
async def test_review_level_member_can_use(world, alias, name, method, path, body, expected, calls) -> None:
    """质控 / EQCR 别名（review 级，各带一条该角色的现行委派）：六个端点放行，业务恰 1 次（需求 9.4）。"""
    stubs = _stub_business(world)
    identity = await _delegated(world, alias)
    assert _member_row(identity) == EXPECTED_ROLE_MAP[alias]
    resp, client = await _send(world, identity.user, method, path, body)
    assert (resp.status_code, resp.json()) == (200, expected), f"{name}：review 级成员（{alias}）被拒 {resp.text}"
    assert _counts(stubs) == calls, name
    client.assert_passed(GATE, times=2)  # 路由级 readonly + 端点级 review


@pytest.mark.parametrize(_ALLOW_ARGS, _allow_cases(EDIT_ALIASES))
async def test_edit_level_member_can_use(world, alias, name, method, path, body, expected, calls) -> None:
    """合伙人（含签字合伙人）/ 经理 / 审计员 / 助理别名（edit 级）：六个端点放行，业务恰 1 次（需求 9.4）。"""
    stubs = _stub_business(world)
    identity = await _delegated(world, alias)
    assert _member_row(identity) == EXPECTED_ROLE_MAP[alias]
    resp, client = await _send(world, identity.user, method, path, body)
    assert (resp.status_code, resp.json()) == (200, expected), f"{name}：edit 级成员（{alias}）被拒 {resp.text}"
    assert _counts(stubs) == calls, name
    client.assert_passed(GATE, times=2)


@pytest.mark.parametrize(("name", "method", "path", "body"), _DENY_CASES, ids=_IDS)
async def test_readonly_member_is_blocked(world, name, method, path, body) -> None:
    """未登记的委派角色（成员行 readonly 级）：403「权限不足」，业务一次都不执行（需求 9.4）。"""
    stubs = _stub_business(world)
    identity = await _delegated(world, UNREGISTERED)
    assert _member_row(identity) == ("readonly", "readonly")
    resp, client = await _send(world, identity.user, method, path, body)
    assert (resp.status_code, resp.json()) == (403, GATE_DENIED), f"{name}：只读成员未被拦 {resp.status_code}"
    assert _counts(stubs) == {}, name
    client.assert_passed(GATE, times=2)  # 路由级 readonly 放行，端点级 review 拒绝


@pytest.mark.parametrize(("name", "method", "path", "body"), _DENY_CASES, ids=_IDS)
async def test_non_member_is_blocked(world, name, method, path, body) -> None:
    """非成员（在另一项目是 edit 级）：403「权限不足」，在路由级 readonly 门禁就被拦下（需求 9.4）。"""
    stubs = _stub_business(world)
    identity = await world.non_member()
    resp, client = await _send(world, identity.user, method, path, body)
    assert (resp.status_code, resp.json()) == (403, GATE_DENIED), f"{name}：非成员未被拦 {resp.status_code}"
    assert _counts(stubs) == {}, name
    client.assert_passed(GATE, times=1)


@pytest.mark.parametrize("alias", REVIEW_ALIASES)
async def test_edit_endpoints_still_block_reviewers(world, alias) -> None:
    """对照：编制类写操作（标记程序完成）仍是 edit 门，没有被一起放宽 —— review 级（质控 / EQCR）被拒，
    edit 级（经理）放行。"""
    path = f"/api/projects/{PID}/workpapers/{WP}/procedures/{PROC}/complete"
    stubs = _stub_business(world)
    reviewer, preparer = await _delegated(world, alias), await _delegated(world, "manager")
    denied, _ = await _send(world, reviewer.user, "patch", path, {"user_id": str(reviewer.user.id)})
    assert (denied.status_code, denied.json()) == (403, GATE_DENIED), denied.text
    assert _counts(stubs) == {}
    allowed, client = await _send(world, preparer.user, "patch", path, {"user_id": str(preparer.user.id)})
    assert (allowed.status_code, allowed.json()) == (200, {"id": PROC}), allowed.text
    assert _counts(stubs) == {"mark_complete": 1, "recalc_quality_score": 1}
    client.assert_passed(GATE, times=2)


async def test_member_signs_only_for_self(world) -> None:
    """签署只要求是项目成员（readonly 级即可），且只能签本人。"""
    stubs = _stub_business(world)
    identity = await _delegated(world, UNREGISTERED)
    me = identity.user.id
    base = f"/api/projects/{PID}/signing/2025/sign?template_code=A17-7&user_id="
    own, client = await _send(world, identity.user, "post", base + str(me), None)
    assert (own.status_code, own.json()) == (200, {"success": True}), own.text
    assert [args for args, _ in stubs["sign"].calls] == [(PID, me, "A17-7")]
    client.assert_passed(GATE, times=1)
    other, _ = await _send(world, identity.user, "post", base + str(OTHER), None)
    assert (other.status_code, other.json()) == (403, NOT_SELF)
    bad, _ = await _send(world, identity.user, "post", base + "undefined", None)
    assert (bad.status_code, bad.json()) == (422, {"detail": "user_id 不是合法的用户 ID"})
    assert _counts(stubs) == {"sign": 1}  # 后两次一次业务都没有


async def test_non_member_cannot_sign(world) -> None:
    stubs = _stub_business(world)
    identity = await world.non_member()
    resp, client = await _send(
        world, identity.user, "post", f"/api/projects/{PID}/signing/2025/sign?user_id={identity.user.id}", None)
    assert (resp.status_code, resp.json()) == (403, GATE_DENIED), resp.text
    assert _counts(stubs) == {}
    client.assert_passed(GATE, times=1)


async def test_my_signing_tasks_requires_login_and_self(world) -> None:
    """无 project_id，不看项目级别（用不是本项目成员的用户）：要求登录，且只能查本人。"""
    stubs = _stub_business(world)
    identity = await world.non_member()
    path = "/api/my/signing-tasks?user_id="
    own, client = await _send(world, identity.user, "get", path + str(identity.user.id), None)
    assert (own.status_code, own.json()) == (200, []), own.text
    assert [args for args, _ in stubs["get_my_pending_tasks"].calls] == [(identity.user.id,)]
    client.assert_passed(GATE, times=0)
    other, _ = await _send(world, identity.user, "get", path + str(OTHER), None)
    assert (other.status_code, other.json()) == (403, NOT_SELF)
    anonymous, _ = await _send(world, None, "get", path + str(identity.user.id), None)
    assert (anonymous.status_code, anonymous.json()) == (401, {"detail": "Not authenticated"})
    assert _counts(stubs) == {"get_my_pending_tasks": 1}
