"""端点权限配方表（spec formula-hub-integrity-closure 任务 5 起；需求 7.3、7.4、17.2；design §10.3；ADR-FHIC-13、20）。

一、配方 ``Recipe`` = 方法 + 绝对路由（与生产应用 ``app.routes`` 的 path 相同）+ 按生产注册挂载的 router + 九种身份逐个归入
   放行 / 拒绝（拒绝写明 401 / 403）+ 拒绝时（行数, 内容摘要）不变的表 + 夹具（建资源并给出请求）+ 放行时的结果断言 +
   每个登录身份的请求都要执行到的生产门禁（可选；``GateTrace`` 观测代码对象开始执行，不替换）+ 下游写入桩
   ``stub_factory``（可选；只桩业务写入，门禁与判定一律拒绝打桩）。
二、身份（需求 17.2）：anon 未登录 / non_member 另一项目 B 的（manager, edit）成员 / ro（readonly）/ auditor（edit）/
   manager（edit）/ qc（review）/ eqcr（review，持 EQCR 现行委派）/ partner（edit）/ admin（不是成员）；成员行都在目标项目 A。
三、执行：每个（配方, 身份）一个用例、一个世界 —— TestClient 的事件循环线程里建 ``pg_tx_session``，夹具、请求、对账在同一外层
   事务里，用例结束回滚。只替换 ``get_current_user`` / ``get_db``（``assert_world_overrides`` 校验键集合，``require_project_access``
   等门禁不得替换；未登录不替换 ``get_current_user``，由真实依赖判 401），请求前 ``assert_gates_are_production`` 自检。
   放行 ``_assert_allowed``：2xx、门禁执行过、配方的结果断言；拒绝 ``_assert_denied``：状态码等于配方所写，列出的表不变（夹具后
   表非空，判据不空转），401 时门禁没执行、403 时门禁执行过。
四、对账（不连库）：配方涉及的路由模块里按生产注册得到的全部路由，要么在配方表、要么在 ``_UNCHANGED_ROUTES``；后者每条都须是
   这些模块里真实存在的路由（反向断言）且不与配方重叠；涉及的模块都在 design §10.3 列出的 14 个之内（任务 40 补齐为相等）。
五、发布记录（需求 7.4）：夹具与逐条期望见 ``_publish_fixtures``。配方断言八种登录身份的结果集逐条等于期望（时间倒序）且他项目
   信息裁掉；另测第一页（limit 1~4：最近 limit 条全不可见时仍返回其后的可见记录，同一时刻按 id 倒序、跨批不漏）与状态筛选；
   SQLite 直调 ``list_publishes`` 走 Python 判定，同一组期望。
六、处理待确认（任务 6，需求 8.2；design §10.3 配方行）：A 的本项目适配 + 其他项目推来的冲突待确认，请求带列表里的修订号
   「采用新定义」；放行断言事项结案、A 的定义换成推来的定义、发一次变更事件（事件桩成计数）；拒绝时 ``formula_sync_item``
   与 ``formula_setting`` 不变。修订号缺 / 不等的合同见 ``test_pending_revision.py``。
"""
from __future__ import annotations

import json
import re
import uuid
from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import text

import app.deps as deps
import app.routers.attachment_lineage as attachment_lineage_router
import app.routers.formula_settings as formula_settings_router
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.services.attachment_lineage_schema import clear_lineage_schema_cache
from app.services.formula_settings.pending import upsert_pending
from app.services.formula_settings.publish import list_publishes
from app.services.formula_settings.stores import get_store
from app.services.formula_settings.template_access import Viewer
from tests.authz_world import (
    TRACED_GATES,
    GateTrace,
    ServiceStub,
    _assert_stubbable,
    assert_gates_are_production,
    assert_world_overrides,
    build_app,
    production_registrations,
)
from tests.formula_hub import _publish_fixtures as pubfx
from tests.formula_hub._lineage_fixtures import insert_lineage, lineage_state, make_attachment
from tests.formula_hub._pg_harness import TEST_PROJECT_PREFIX, pg_tx_session

# ─── 身份（需求 17.2） ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class IdentitySpec:
    key: str
    label: str
    role: UserRole | None  # 全局角色；None = 未登录
    member: tuple[str, ProjectUserRole, PermissionLevel] | None = None  # （项目 A / B, 项目角色, 权限级别）
    eqcr_assignment: bool = False  # 在 A 持有一条 eqcr 现行委派


IDENTITY_SPECS: tuple[IdentitySpec, ...] = (
    IdentitySpec("anon", "未登录", None),
    IdentitySpec("non_member", "非成员（另一项目 B 的 manager + edit）", UserRole.auditor,
                 ("B", ProjectUserRole.manager, PermissionLevel.edit)),
    IdentitySpec("ro", "readonly 成员", UserRole.auditor, ("A", ProjectUserRole.readonly, PermissionLevel.readonly)),
    IdentitySpec("auditor", "审计员（edit）", UserRole.auditor, ("A", ProjectUserRole.auditor, PermissionLevel.edit)),
    IdentitySpec("manager", "经理（edit）", UserRole.manager, ("A", ProjectUserRole.manager, PermissionLevel.edit)),
    IdentitySpec("qc", "质控（review）", UserRole.qc, ("A", ProjectUserRole.qc, PermissionLevel.review)),
    IdentitySpec("eqcr", "EQCR（review）", UserRole.eqcr, ("A", ProjectUserRole.eqcr, PermissionLevel.review), True),
    IdentitySpec("partner", "合伙人（edit）", UserRole.partner, ("A", ProjectUserRole.partner, PermissionLevel.edit)),
    IdentitySpec("admin", "管理员（不是成员）", UserRole.admin),
)
SPEC_BY_KEY = {spec.key: spec for spec in IDENTITY_SPECS}
IDENTITIES: tuple[str, ...] = tuple(SPEC_BY_KEY)
LOGGED_IN = frozenset(IDENTITIES) - {"anon"}
A_MEMBERS = frozenset(s.key for s in IDENTITY_SPECS if s.member and s.member[0] == "A")
A_EDITORS = frozenset(s.key for s in IDENTITY_SPECS if s.member and s.member[0] == "A"
                      and s.member[2] is PermissionLevel.edit)


@dataclass
class World:
    projects: dict[str, uuid.UUID]  # A = 目标项目，B = non_member 的项目，C = 九种身份都不在
    names: dict[uuid.UUID, str]
    users: dict[str, User]  # 身份键 → 用户（anon 没有）
    extra: dict[str, Any] = field(default_factory=dict)  # 配方夹具的产物

    def members(self, identity: str) -> set[uuid.UUID]:
        member = SPEC_BY_KEY[identity].member
        return {self.projects[member[0]]} if member else set()


async def seed_world(session) -> World:
    """三个【测试】项目 + 八个登录身份的用户、成员行与 EQCR 委派（PG / SQLite 同一份 ORM 写法）。"""
    tag = uuid.uuid4().hex[:8]
    projects: dict[str, uuid.UUID] = {}
    names: dict[uuid.UUID, str] = {}
    for key in ("A", "B", "C"):
        project = Project(name=f"{TEST_PROJECT_PREFIX}fh_authz_{key}_{tag}", client_name=f"{TEST_PROJECT_PREFIX}端点权限配方表")
        session.add(project)
        await session.flush()
        projects[key], names[project.id] = project.id, project.name
    users: dict[str, User] = {}
    for spec in IDENTITY_SPECS:
        if spec.role is None:
            continue
        user = User(username=f"fh_authz_{spec.key}_{tag}", email=f"fh_authz_{spec.key}_{tag}@example.test",
                    hashed_password="x", role=spec.role, is_active=True)
        session.add(user)
        await session.flush()
        users[spec.key] = user
        if spec.member:
            project_key, role, level = spec.member
            session.add(ProjectUser(project_id=projects[project_key], user_id=user.id, role=role, permission_level=level))
        if spec.eqcr_assignment:
            staff = StaffMember(user_id=user.id, name=f"fh_authz_eqcr_{tag}")
            session.add(staff)
            await session.flush()
            session.add(ProjectAssignment(project_id=projects["A"], staff_id=staff.id, role="eqcr",
                                          assigned_at=datetime.now(timezone.utc)))
    await session.commit()  # pg_tx_session：只释放保存点
    return World(projects, names, users)


# ─── 配方表结构 ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Req:
    method: str
    url: str
    params: dict[str, Any] | None = None
    json: Any = None


@dataclass
class Ctx:
    client: TestClient
    session: Any
    api: FastAPI
    world: World | None = None

    def call(self, fn: Callable[..., Awaitable[Any]], *args: Any) -> Any:
        """在应用的事件循环线程里用本用例的会话执行 ``fn(session, *args)``。"""
        return self.client.portal.call(fn, self.session, *args)


@dataclass(frozen=True)
class Recipe:
    key: str
    method: str
    route: str
    routers: tuple[APIRouter, ...]
    allowed: frozenset[str]
    denied: Mapping[str, int]
    prepare: Callable[[Any, World], Awaitable[Req]]
    tables: tuple[str, ...] = ()
    check: Callable[[Ctx, str, Response], None] | None = None
    gate: str | None = None
    stub_factory: Callable[[pytest.MonkeyPatch, World], None] | None = None


def stub(monkeypatch: pytest.MonkeyPatch, owner: Any, attr: str, returns: Any = None) -> ServiceStub:
    """``stub_factory`` 用：把下游业务写入换成计数桩；门禁、判定与可替换点拒绝打桩（同 ``AuthzWorld.stub``）。"""
    _assert_stubbable(owner, attr)
    service = ServiceStub(target=f"{getattr(owner, '__name__', owner)}.{attr}", returns=returns)
    monkeypatch.setattr(owner, attr, service)
    return service


_GATE = "app.deps.assert_project_permission"
_TABLE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")
PUBLISHES = "/api/formula-settings/publishes"
PENDING_RESOLVE = "/api/projects/{project_id}/formula-settings/pending/resolve"
LINK_REF = "FH-T5-AUTHZ!B5"


# ─── 附件三端点（需求 7.3） ──────────────────────────────────────────────────


async def _seed_attachment(session, world: World) -> uuid.UUID:
    attachment = await make_attachment(session, world.projects["A"])
    link = await insert_lineage(session, attachment_id=attachment, target_ref="FH-T5-AUTHZ", project_id=world.projects["A"])
    await session.commit()
    world.extra.update(attachment=attachment, link=link)
    return attachment


async def _prepare_link(session, world: World) -> Req:
    attachment = await _seed_attachment(session, world)
    return Req("POST", f"/api/attachments/{attachment}/link", json={"target_type": "wp_cell", "target_ref": LINK_REF})


async def _prepare_links(session, world: World) -> Req:
    return Req("GET", f"/api/attachments/{await _seed_attachment(session, world)}/links")


async def _prepare_unlink(session, world: World) -> Req:
    attachment = await _seed_attachment(session, world)
    return Req("DELETE", f"/api/attachments/{attachment}/link/{world.extra['link']}")


def _check_link_created(ctx: Ctx, _identity: str, response: Response) -> None:
    body = response.json()
    assert (body["attachment_id"], body["target_ref"]) == (str(ctx.world.extra["attachment"]), LINK_REF), body
    stored = ctx.call(lineage_state, [uuid.UUID(body["id"])])
    assert [row["project_id"] for row in stored.values()] == [str(ctx.world.projects["A"])], stored


def _check_links_listed(ctx: Ctx, _identity: str, response: Response) -> None:
    assert [item["id"] for item in response.json()] == [str(ctx.world.extra["link"])], response.text


def _check_link_deleted(ctx: Ctx, _identity: str, response: Response) -> None:
    assert ctx.call(lineage_state, [ctx.world.extra["link"]]) == {}, "放行的删除没有删掉关联行"


# ─── 发布记录（需求 7.4，ADR-FHIC-20） ───────────────────────────────────────


async def _prepare_publishes(session, world: World) -> Req:
    scenario = await pubfx.seed_publishes(session, projects=world.projects, names=world.names,
                                          users={key: user.id for key, user in world.users.items()})
    await session.commit()
    world.extra["publishes"] = scenario
    return Req("GET", PUBLISHES, params={"scope": scenario.scope, "limit": 200})


def _check_publishes(ctx: Ctx, identity: str, response: Response) -> None:
    pubfx.assert_items(ctx.world.extra["publishes"], identity, response.json()["items"], response.text,
                       members=ctx.world.members(identity), projects=ctx.world.names)


# ─── 处理待确认（需求 8.2，ADR-FHIC-11） ─────────────────────────────────────

_SYNC_DOMAIN = "tb_detail"
_SYNC_LOCAL = {"formula": "TB('1001','审定数')", "formula_category": "auto_calc"}
_SYNC_UPSTREAM = {"formula": "TB('1001','期末余额')*2", "formula_category": "auto_calc"}


async def _prepare_resolve(session, world: World) -> Req:
    """A 的本项目适配 + 其他项目推来的冲突待确认（生产 ``upsert_pending``）；请求带列表里的修订号「采用新定义」。"""
    project, slot = world.projects["A"], f"FH-T6-AUTHZ-{uuid.uuid4().hex[:6]}"
    await get_store(_SYNC_DOMAIN).write_project(session, project, slot, definition=_SYNC_LOCAL, base_definition=None,
                                                base_version=None, pinned=False, base_origin=None,
                                                base_template_id=None, user_id=None, label="库存现金")
    item = await upsert_pending(session, project_id=project, domain=_SYNC_DOMAIN, slot_key=slot, slot_label="库存现金",
                                reason="conflict", base_definition=None, upstream_definition=_SYNC_UPSTREAM,
                                upstream_version=None, local_definition=_SYNC_LOCAL, publish_id=None,
                                upstream_origin="project")
    await session.commit()
    world.extra.update(sync_item=item.id, sync_slot=slot)
    return Req("POST", PENDING_RESOLVE.format(project_id=project), json={"resolutions": [
        {"item_id": str(item.id), "choice": "adopt", "revision": item.revision}]})


async def _resolve_state(session, world: World) -> tuple[Any, ...]:
    item = (await session.execute(text("SELECT status, resolution FROM formula_sync_item WHERE id = :i"),
                                  {"i": world.extra["sync_item"]})).one()
    formula = (await session.execute(text(
        "SELECT definition->>'formula' FROM formula_setting WHERE domain = :d AND layer = 'project' "
        "AND project_id = :p AND slot_key = :s AND NOT is_deleted"),
        {"d": _SYNC_DOMAIN, "p": world.projects["A"], "s": world.extra["sync_slot"]})).scalar_one()
    return (*item, formula)


def _check_resolved(ctx: Ctx, _identity: str, response: Response) -> None:
    body = response.json()
    assert (body["resolved"], body["recalc_domains"]) == ([str(ctx.world.extra["sync_item"])], [_SYNC_DOMAIN]), body
    assert ctx.call(_resolve_state, ctx.world) == ("resolved", "adopt", _SYNC_UPSTREAM["formula"])
    assert ctx.world.extra["events"].count == 1, "提交后应发一次变更事件"


def _stub_resolve_events(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    """变更事件会经事件总线另开会话做传播（不在本用例的回滚事务里）：桩成计数。"""
    world.extra["events"] = stub(monkeypatch, formula_settings_router, "publish_events", returns=0)


# ─── 配方表与豁免表 ──────────────────────────────────────────────────────────

_ATTACHMENT_ROUTERS = (attachment_lineage_router.router,)
_EDIT_DENIED = {"anon": 401, "non_member": 403, "ro": 403, "qc": 403, "eqcr": 403}
RECIPES: tuple[Recipe, ...] = (
    Recipe("publishes", "GET", PUBLISHES, (formula_settings_router.router,), allowed=LOGGED_IN,
           denied={"anon": 401}, prepare=_prepare_publishes, check=_check_publishes),
    Recipe("attachment-link", "POST", "/api/attachments/{attachment_id}/link", _ATTACHMENT_ROUTERS,
           allowed=A_EDITORS | {"admin"}, denied=_EDIT_DENIED, prepare=_prepare_link, tables=("attachment_lineage",),
           check=_check_link_created, gate=_GATE),
    Recipe("attachment-links", "GET", "/api/attachments/{attachment_id}/links", _ATTACHMENT_ROUTERS,
           allowed=A_MEMBERS | {"admin"}, denied={"anon": 401, "non_member": 403}, prepare=_prepare_links,
           check=_check_links_listed, gate=_GATE),
    Recipe("attachment-unlink", "DELETE", "/api/attachments/{attachment_id}/link/{link_id}", _ATTACHMENT_ROUTERS,
           allowed=A_EDITORS | {"admin"}, denied=_EDIT_DENIED, prepare=_prepare_unlink, tables=("attachment_lineage",),
           check=_check_link_deleted, gate=_GATE),
    Recipe("pending-resolve", "POST", PENDING_RESOLVE, (formula_settings_router.project_router,),
           allowed=A_EDITORS | {"admin"}, denied=_EDIT_DENIED, prepare=_prepare_resolve,
           tables=("formula_sync_item", "formula_setting"), check=_check_resolved, gate=_GATE,
           stub_factory=_stub_resolve_events),
)

_FS = "/api/formula-settings"
_PFS = "/api/projects/{project_id}/formula-settings"
_NOT_CHANGED = "本 spec 不改权限、所有权与请求 / 响应合同"
_VALIDATOR = "权限不变；写入前校验的合同由 test_formula_definition_validator.py 覆盖（design §10.3）"
_RC = "/api/report-config"
_WF = "/api/projects/{project_id}/workflow"
#: 配方涉及的路由模块里、不进配方表的路由 → 理由（每条须真实存在；改了权限 / 所有权 / 合同的任务把它移入配方表）
#: 第 2 轮：design §10.3 其余 19 条已移入 ``test_formula_hub_endpoint_authz_r2.RECIPES_R2``（形态 / 对账两条用例合并两表）
_UNCHANGED_ROUTES: dict[tuple[str, str], str] = {
    # ── formula_settings（两个 router 共 16 条） ──
    ("GET", f"{_FS}/domains"): "权限与响应结构不变（任务 36 只改 wired 的取值来源）",
    ("GET", f"{_FS}/{{domain}}/global"): _NOT_CHANGED,
    ("POST", f"{_FS}/{{domain}}/global/preview"): _NOT_CHANGED,
    ("POST", f"{_FS}/{{domain}}/global/publish"): _VALIDATOR,
    ("POST", f"{_FS}/candidates/{{publish_id}}/preview"): _NOT_CHANGED,
    ("POST", f"{_FS}/candidates/{{publish_id}}/review"): _VALIDATOR,
    ("GET", f"{_PFS}/{{domain}}/effective"): _NOT_CHANGED,
    ("PUT", f"{_PFS}/{{domain}}/overrides"): _VALIDATOR,
    ("GET", f"{_PFS}/pending"): "权限不变；任务 6 只在列表项增加 revision 字段（test_pending_revision.py 覆盖）",
    ("GET", f"{_PFS}/apply-targets"): _NOT_CHANGED,
    ("POST", f"{_PFS}/{{domain}}/apply-preview"): _NOT_CHANGED,
    ("POST", f"{_PFS}/{{domain}}/apply"): _VALIDATOR,
    ("GET", f"{_PFS}/dependencies"): _NOT_CHANGED,
    # ── formula（公式中央 API） ──
    ("DELETE", "/api/formula/custom-functions/{name}"): "admin only；权限不变",
    ("GET", "/api/formula/custom-functions"): _NOT_CHANGED,
    ("GET", "/api/formula/functions"): _NOT_CHANGED,
    # ── formula_debug ──
    # ── report_config ──
    ("GET", f"{_RC}"): _NOT_CHANGED,
    ("GET", f"{_RC}/types"): _NOT_CHANGED,
    ("GET", f"{_RC}/row-note-mapping"): _NOT_CHANGED,
    ("GET", f"{_RC}/{{config_id}}"): _NOT_CHANGED,
    ("POST", f"{_RC}"): _VALIDATOR,
    ("POST", f"{_RC}/clone"): _NOT_CHANGED,
    ("POST", f"{_RC}/seed"): _NOT_CHANGED,
    ("POST", f"{_RC}/fill-formulas"): _VALIDATOR,
    ("PUT", f"{_RC}/{{config_id}}"): _VALIDATOR,
    ("DELETE", f"{_RC}/{{config_id}}"): _NOT_CHANGED,
    # ── formula_audit_log ──
    # ── wp_formula ──
    ("GET", "/api/workpapers/{wp_id}/formulas"): _NOT_CHANGED,
    ("PUT", "/api/workpapers/{wp_id}/formulas"): _VALIDATOR,
    ("PUT", "/api/workpapers/{wp_id}/formulas/batch"): _VALIDATOR,
    # ── formula_templates ──
    ("GET", "/api/formula-templates"): _NOT_CHANGED,
    ("GET", "/api/formula-templates/{template_id}"): _NOT_CHANGED,
    ("GET", "/api/formula-templates/{template_id}/subscribers"): _NOT_CHANGED,
    ("GET", "/api/formula-templates/{template_id}/versions"): _NOT_CHANGED,
    ("POST", "/api/formula-templates"): _NOT_CHANGED,
    ("PUT", "/api/formula-templates/{template_id}"): _NOT_CHANGED,
    ("POST", "/api/formula-templates/{template_id}/promote"): _NOT_CHANGED,
    ("POST", "/api/formula-templates/{template_id}/promote-preview"): _NOT_CHANGED,
    ("POST", "/api/formula-templates/{template_id}/publish"): _NOT_CHANGED,
    ("POST", "/api/formula-templates/{template_id}/publish-preview"): _NOT_CHANGED,
    ("GET", "/api/projects/{project_id}/formula-templates/subscriptions"): _NOT_CHANGED,
    ("POST", "/api/projects/{project_id}/formula-templates/subscribe"): _NOT_CHANGED,
    ("POST", "/api/projects/{project_id}/formula-templates/subscribe-preview"): _NOT_CHANGED,
    ("POST", "/api/projects/{project_id}/formula-templates/unsubscribe"): _NOT_CHANGED,
    ("POST", "/api/projects/{project_id}/formula-templates/unsubscribe-preview"): _NOT_CHANGED,
    # ── draft_refresh ──
    ("POST", "/api/workpapers/draft-refresh/{run_id}/rollback"): _NOT_CHANGED,
    # ── lineage ──
    # ── formula_timeline ──
    # ── qc_vr_heatmap ──
    # ── chain_workflow ──
    ("POST", f"{_WF}/execute-full-chain"): _NOT_CHANGED,
    ("POST", f"{_WF}/retry/{{execution_id}}"): _NOT_CHANGED,
    ("GET", f"{_WF}/executions"): _NOT_CHANGED,
    ("GET", f"{_WF}/progress/{{execution_id}}"): _NOT_CHANGED,
    ("GET", f"{_WF}/compare/{{execution_id}}"): _NOT_CHANGED,
    ("GET", f"{_WF}/data-health"): _NOT_CHANGED,
    ("POST", f"{_WF}/notes/sync-from-report"): _NOT_CHANGED,
    ("POST", f"{_WF}/notes/trim-and-sort"): _NOT_CHANGED,
    ("POST", "/api/workflow/batch-execute"): _NOT_CHANGED,
    # ── partner_dashboard ──
    ("GET", "/api/partner/overview"): _NOT_CHANGED,
    ("GET", "/api/partner/team-efficiency"): _NOT_CHANGED,
    ("POST", "/api/projects/{project_id}/partner/workpaper-readiness"): _NOT_CHANGED,
}
#: design §10.3 列出的路由模块（配方涉及的模块须在其中；任务 40 补齐后两者相等）
_DESIGN_ROUTE_MODULES = frozenset(f"app.routers.{name}" for name in (
    "formula", "formula_debug", "report_config", "attachment_lineage", "formula_settings", "formula_audit_log",
    "wp_formula", "formula_templates", "draft_refresh", "lineage", "formula_timeline", "qc_vr_heatmap",
    "chain_workflow", "partner_dashboard"))


# ─── 执行与判定 ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _fresh_lineage_schema_cache():
    clear_lineage_schema_cache()
    yield
    clear_lineage_schema_cache()


@contextmanager
def _endpoint(*routers: APIRouter) -> Iterator[Ctx]:
    """按生产注册挂 ``routers`` 的应用 + TestClient + 建在其事件循环线程里的 pg_tx 会话（``get_db`` 指向它）。"""
    api = build_app(*routers)
    with TestClient(api) as client:
        with client.portal.wrap_async_context_manager(pg_tx_session()) as session:
            async def _db():
                yield session

            api.dependency_overrides[get_db] = _db
            yield Ctx(client, session, api)


def _send(ctx: Ctx, identity: str, req: Req) -> tuple[Response, dict[str, int]]:
    """以 ``identity`` 发请求，返回响应与请求期间各生产门禁代码开始执行的次数。"""
    overrides = ctx.api.dependency_overrides
    if identity == "anon":
        overrides.pop(get_current_user, None)
    else:
        user = ctx.world.users[identity]

        async def _user() -> User:
            return user

        overrides[get_current_user] = _user
    assert_world_overrides(ctx.api)
    assert_gates_are_production()
    with GateTrace() as trace:
        response = ctx.client.request(req.method, req.url, params=req.params, json=req.json)
    return response, dict(trace.counts)


async def _tables_state(session, tables: tuple[str, ...]) -> dict[str, tuple[int, str]]:
    """逐表（行数, 全部行 ``row_to_json`` 排序后的 md5），同一外层事务内读。"""
    state: dict[str, tuple[int, str]] = {}
    for table in tables:
        row = (await session.execute(text(
            "SELECT count(*), coalesce(md5(string_agg(row_to_json(t)::text, '|' ORDER BY row_to_json(t)::text)), '') "
            f"FROM {table} t"))).one()
        state[table] = (int(row[0]), str(row[1]))
    return state


def _assert_allowed(ctx: Ctx, recipe: Recipe, identity: str, response: Response, gate_runs: Mapping[str, int]) -> None:
    assert 200 <= response.status_code < 300, (recipe.key, identity, response.status_code, response.text[:800])
    if recipe.gate is not None:
        assert gate_runs[recipe.gate] >= 1, (recipe.key, identity, "放行的请求没有经过生产门禁", recipe.gate)
    if recipe.check is not None:
        recipe.check(ctx, identity, response)


def _assert_denied(recipe: Recipe, identity: str, response: Response, gate_runs: Mapping[str, int],
                   before: Mapping[str, tuple[int, str]], after: Mapping[str, tuple[int, str]]) -> None:
    expected = recipe.denied[identity]
    assert response.status_code == expected, (recipe.key, identity, response.status_code, response.text[:800])
    assert all(count > 0 for count, _ in before.values()), (recipe.key, "拒绝前表为空，内容不变的判据会空转", before)
    assert after == before, (recipe.key, identity, "拒绝后表内容变了", before, after)
    if recipe.gate is not None:
        runs = gate_runs[recipe.gate]
        assert (runs == 0) if expected == 401 else (runs >= 1), (recipe.key, identity, recipe.gate, runs)


_CASES = [(recipe, identity) for recipe in RECIPES for identity in IDENTITIES]


@pytest.mark.pg_only
@pytest.mark.parametrize(("recipe", "identity"), _CASES, ids=[f"{r.key}-{i}" for r, i in _CASES])
def test_recipe(recipe: Recipe, identity: str, monkeypatch: pytest.MonkeyPatch) -> None:
    with _endpoint(*recipe.routers) as ctx:
        ctx.world = ctx.call(seed_world)
        req = ctx.call(recipe.prepare, ctx.world)
        if recipe.stub_factory is not None:
            recipe.stub_factory(monkeypatch, ctx.world)
        before = ctx.call(_tables_state, recipe.tables)
        response, gate_runs = _send(ctx, identity, req)
        after = ctx.call(_tables_state, recipe.tables)
        if identity in recipe.allowed:
            _assert_allowed(ctx, recipe, identity, response, gate_runs)
        else:
            _assert_denied(recipe, identity, response, gate_runs, before, after)


@pytest.mark.pg_only
@pytest.mark.parametrize("identity", ["ro", "non_member", "auditor", "admin"])
def test_publishes_first_page_and_status_filter(identity: str) -> None:
    """limit 1~4 的第一页 = 最新的 limit 条可见记录；按状态筛选后同样只剩可见记录（PG：①~③ 由 SQL 条件过滤）。"""
    with _endpoint(formula_settings_router.router) as ctx:
        ctx.world = ctx.call(seed_world)
        ctx.call(_prepare_publishes, ctx.world)
        scenario = ctx.world.extra["publishes"]
        newest = [r.key for r in scenario.records[:3]]
        assert newest == ["tpl_personal_1", "tpl_personal_2", "tpl_personal_3"], newest  # 夹具前提，见夹具模块说明
        if identity != "admin":
            assert not set(newest) & {r.key for r in scenario.expected(identity)}, "前提：最新三条对该身份全不可见"
        pages = {limit: _send(ctx, identity, Req("GET", PUBLISHES, params={"scope": scenario.scope, "limit": limit}))[0]
                 for limit in (1, 2, 3, 4)}
        by_status = {status: _send(ctx, identity, Req("GET", PUBLISHES, params={"scope": scenario.scope,
                                                                                  "status": status}))[0]
                     for status in ("pending", "rejected", "published")}
    members = ctx.world.members(identity)
    for limit, response in pages.items():
        assert response.status_code == 200, response.text
        pubfx.assert_items(scenario, identity, response.json()["items"], response.text, members=members,
                           projects=ctx.world.names, limit=limit)
    for status, response in by_status.items():
        assert response.status_code == 200, response.text
        pubfx.assert_items(scenario, identity, response.json()["items"], response.text, members=members,
                           projects=ctx.world.names, status=status)


async def test_list_publishes_sqlite_rules_match_expectations() -> None:
    """SQLite（单测）四条规则都在 Python 判定，与 PG 用例同一组期望（ADR-FHIC-20 末句）。"""
    from tests.formula_settings._env import make_db

    async with make_db(extra_models=(StaffMember, ProjectAssignment)) as factory, factory() as db:
        assert db.get_bind().dialect.name == "sqlite"
        world = await seed_world(db)
        scenario = await pubfx.seed_publishes(db, projects=world.projects, names=world.names,
                                              users={key: user.id for key, user in world.users.items()})
        await db.commit()
        for identity in sorted(LOGGED_IN):
            viewer = await Viewer.load(db, world.users[identity])
            for limit, status in [(1, None), (2, None), (3, None), (4, None), (200, None),
                                  (200, "pending"), (200, "rejected"), (200, "published")]:
                items = await list_publishes(db, viewer=viewer, scope=scenario.scope, status=status, limit=limit)
                pubfx.assert_items(scenario, identity, items, json.dumps(items, ensure_ascii=False),
                                   members=world.members(identity), projects=world.names, status=status,
                                   limit=None if limit == 200 else limit)


# ─── 配方表自检与对账（不连库） ──────────────────────────────────────────────


def _routes_of(api: FastAPI, modules: set[str]) -> dict[tuple[str, str], str]:
    return {(method, route.path): route.endpoint.__module__ for route in api.routes
            if isinstance(route, APIRoute) and route.endpoint.__module__ in modules for method in route.methods}


def _production_routes(modules: set[str]) -> dict[tuple[str, str], str]:
    """按生产注册（前缀、注册时附加的依赖与生产相同）挂上含这些模块端点的 router，取（方法, 绝对路径）→ 模块。"""
    api = FastAPI()
    for router, kwargs in production_registrations():
        if any(isinstance(route, APIRoute) and route.endpoint.__module__ in modules for route in router.routes):
            api.include_router(router, **kwargs)
    return _routes_of(api, modules)


def _all_recipes() -> tuple[Any, ...]:
    """本文件的配方 + 第 2 轮补齐的配方（那个文件从本文件导入夹具 ⇒ 用时再导，避免循环导入）。"""
    from tests.formula_hub.test_formula_hub_endpoint_authz_r2 import RECIPES_R2

    return (*RECIPES, *RECIPES_R2)


def test_recipe_table_shape() -> None:
    """每条配方把九种身份恰好分一次、拒绝码只有 401 / 403（底稿绑定路由另有 404）且未登录恒 401；（方法, 路由）不重复；门禁与表名合法。"""
    assert len(IDENTITY_SPECS) == 9 and pubfx.LOGGED_IN == LOGGED_IN and pubfx.A_MEMBERS == A_MEMBERS
    recipes = _all_recipes()
    keys = [(r.method, r.route) for r in recipes]
    assert len(keys) == len(set(keys)) and len({r.key for r in recipes}) == len(recipes), keys
    for recipe in recipes:
        assert recipe.allowed.isdisjoint(recipe.denied) and recipe.allowed | set(recipe.denied) == set(IDENTITIES), recipe.key
        codes = {401, 403} | ({404} if "{wp_id}" in recipe.route else set())  # 底稿绑定路由另有可见性门（404）
        assert set(recipe.denied.values()) <= codes and recipe.denied.get("anon") == 401, recipe.key
        assert recipe.gate is None or recipe.gate in TRACED_GATES, (recipe.key, recipe.gate)
        assert all(_TABLE_NAME.match(table) for table in recipe.tables), (recipe.key, recipe.tables)
        assert recipe.method in {"GET", "POST", "PUT", "PATCH", "DELETE"}, recipe.key


def test_routes_reconcile_with_recipes_and_unchanged() -> None:
    """配方涉及的模块：全部 14 个模块的生产路由 = 配方路由 ∪ 豁免路由（不重叠）；豁免每条都真实存在。"""
    recipe_routes: dict[tuple[str, str], str] = {}
    for recipe in _all_recipes():
        mounted = _routes_of(build_app(*recipe.routers), {
            route.endpoint.__module__ for router in recipe.routers for route in router.routes if isinstance(route, APIRoute)})
        assert (recipe.method, recipe.route) in mounted, (recipe.key, "配方路由不在按生产注册挂载的 router 里")
        recipe_routes[(recipe.method, recipe.route)] = mounted[(recipe.method, recipe.route)]
    recipe_modules = set(recipe_routes.values())
    assert recipe_modules <= _DESIGN_ROUTE_MODULES, sorted(recipe_modules - _DESIGN_ROUTE_MODULES)
    # 全部 14 个模块的生产路由
    production = _production_routes(_DESIGN_ROUTE_MODULES)
    # 配方 ∪ 豁免覆盖的模块 == design §10.3 的 14 个
    unchanged_modules = {production[k] for k in _UNCHANGED_ROUTES if k in production}
    covered = recipe_modules | unchanged_modules
    assert covered == _DESIGN_ROUTE_MODULES, sorted(covered.symmetric_difference(_DESIGN_ROUTE_MODULES))
    assert set(recipe_routes) <= set(production), sorted(set(recipe_routes) - set(production))
    assert set(recipe_routes).isdisjoint(_UNCHANGED_ROUTES), sorted(set(recipe_routes) & set(_UNCHANGED_ROUTES))
    stale = sorted(set(_UNCHANGED_ROUTES) - set(production))
    assert stale == [], f"_UNCHANGED_ROUTES 有不存在（或不在配方涉及模块里）的路由：{stale}"
    unregistered = sorted(set(production) - set(recipe_routes) - set(_UNCHANGED_ROUTES))
    assert unregistered == [], f"配方涉及的模块里有路由既不在配方表也不在 _UNCHANGED_ROUTES：{unregistered}"
    assert all(reason.strip() for reason in _UNCHANGED_ROUTES.values())


def test_stub_factory_refuses_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    """``stub`` 只桩业务写入：门禁本身与门禁所在模块里的对象拒绝打桩（需求 17.2「鉴权链真实运行」）。"""
    for owner, attr in ((deps, "assert_project_permission"), (deps, "require_project_access"), (deps, "get_current_user")):
        with pytest.raises(ValueError, match="不能当业务 service 打桩"):
            stub(monkeypatch, owner, attr)
    service = stub(monkeypatch, attachment_lineage_router, "ensure_lineage_project_column")
    assert attachment_lineage_router.ensure_lineage_project_column is service and service.count == 0
