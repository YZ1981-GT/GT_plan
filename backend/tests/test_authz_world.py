"""权限世界夹具的自测（partner-manager-edit-permission 任务 3.1；design §8.2、D11；需求 12.1、12.2、12.4）。

一、世界本身：恰好六张表；三个部分唯一索引与 PG 同语义；Redis 客户端是本世界独占、初始为空的 fakeredis。
二、八种身份的数据按需求 12.2 / 12.4 原文逐项核对（读库，不读 Identity 对象）；「是否 EQCR」由真实 ``is_project_eqcr`` 判定。
三、八种身份 × 三个级别经真实 ``assert_project_permission`` 的结论，期望按需求原文与该函数的现行口径写死；每个用例一个独立的世界。
四、经 HTTP 真发请求：生产注册的 ``wp_cross_check`` 路由 ``POST …/cross-check/rules/custom``（路由级 readonly 门禁 + 端点级 edit
    门禁，业务 service 打桩计数）。放行（桩恰 1 次且 200）、拒绝（0 次）、归档 423、admin 放行、未登录 401；每个请求都核对
    生产门禁的代码确实执行过。选这个端点是因为本 spec 不改它的门禁级别，自测不会随后续任务改口径。
五、「门禁 is 生产对象」自检及其反向对照（反向对照只注入查找函数或换一个不经门禁的应用，不替换任何门禁）。
六、PG 同构版（``pg_only``）：临时 schema 隔离、同样六张表与结论、HTTP 放行与拒绝，结束后不留对象。
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.routing import APIRoute
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import app
import app.core.redis as core_redis
import app.deps as deps
import app.services.eqcr_resolver as eqcr_resolver
from app.core.database import get_db
from app.core.redis import get_redis
from app.deps import get_current_user
from app.models.base import PermissionLevel, ProjectStatus, ProjectUserRole
from app.models.core import Project, ProjectUser, User
from app.models.report_models import DisclosureNote
from app.models.staff_models import ProjectAssignment, StaffMember
from app.routers import wp_cross_check
from app.services.eqcr_resolver import is_project_eqcr
from app.services.wp_cross_check_service import CrossCheckService
from tests.authz_world import (
    IDENTITY_LABELS,
    OTHER_PROJECT_ID,
    PRODUCTION_GATE_OBJECTS,
    PRODUCTION_GATES,
    STANDARD_IDENTITIES,
    SUPPLEMENTARY_IDENTITIES,
    TARGET_NOTE_ID,
    TARGET_PROJECT_ID,
    TRACED_GATES,
    WORLD_TABLE_NAMES,
    AuthzWorld,
    GateClient,
    ServiceStub,
    assert_gates_are_production,
    build_app,
    pg_engine,
    pg_world,
    production_registrations,
    sqlite_world,
)
from tests.role_map_expected import EXPECTED_EQCR_ALIASES

# ─── 期望（按需求原文写死，不由被测函数推出） ────────────────────────────────

ALLOW = "放行"
DENIED = (403, "权限不足")  # assert_project_permission 的拒绝文案
ARCHIVED = (423, {
    "error_code": "PROJECT_ARCHIVED", "message": "项目已归档，无法编辑", "message_en": "Project archived (read-only)",
})
LEVELS = ("readonly", "review", "edit")

# 身份 → 在 readonly / review / edit 三个级别上的结论（需求 12.2、12.4；assert_project_permission 的现行口径：
# 非 readonly 级先判归档 → 423；admin 跳过成员判定；否则成员级别不低于所测级别才放行，非成员 403）。
# ⑤ 在 review 级放行：EQCR 只读由附注编辑门禁另判，不是 assert_project_permission 的职责。
EXPECTED_VERDICTS: dict[str, tuple[object, object, object]] = {
    "edit_member": (ALLOW, ALLOW, ALLOW),
    "review_member": (ALLOW, ALLOW, DENIED),
    "readonly_member": (ALLOW, DENIED, DENIED),
    "non_member": (DENIED, DENIED, DENIED),
    "project_eqcr": (ALLOW, ALLOW, DENIED),
    "archived_edit_member": (ALLOW, ARCHIVED, ARCHIVED),
    "qc_review_member": (ALLOW, ALLOW, DENIED),
    "admin_non_member": (ALLOW, ALLOW, ALLOW),
}

# 需求 12.2 / 12.4 的身份定义：（全局角色，目标项目上的成员行，另一项目上的成员行，全世界 EQCR 别名现行委派条数）
IDENTITY_DEFINITIONS: dict[str, tuple[str, tuple[str, str] | None, tuple[str, str] | None, int]] = {
    "edit_member": ("auditor", ("manager", "edit"), None, 0),
    "review_member": ("auditor", ("qc", "review"), None, 0),
    "readonly_member": ("auditor", ("readonly", "readonly"), None, 0),
    "non_member": ("auditor", None, ("manager", "edit"), 0),
    "project_eqcr": ("auditor", ("partner", "review"), None, 1),
    "archived_edit_member": ("auditor", ("manager", "edit"), None, 0),
    "qc_review_member": ("qc", ("qc", "review"), None, 0),
    "admin_non_member": ("admin", None, None, 0),
}

GATE = "app.deps.assert_project_permission"
GATE_CLOSURE = "app.deps.require_project_access.<locals>.dependency"
RULES_PATH = f"/api/projects/{TARGET_PROJECT_ID}/cross-check/rules/custom"
RULE_BODY = {"description": "权限世界自测规则", "formula": "1 = 1"}
STUB_RESULT = {"id": "stub-rule"}


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch) as w:
        yield w


async def _verdict(world: AuthzWorld, user: User, level: str) -> object:
    """真实 assert_project_permission 对（用户，目标项目，级别）的结论：放行，或（状态码，detail）。"""
    assert_gates_are_production()
    try:
        returned = await deps.assert_project_permission(world.db, user, TARGET_PROJECT_ID, level)
    except HTTPException as exc:
        return (exc.status_code, exc.detail)
    assert returned is user, "放行时应原样返回当前用户"
    return ALLOW


async def _post_rule(world: AuthzWorld, user: User | None) -> tuple[object, ServiceStub, GateClient]:
    """对目标项目发一次「新增自定义校验规则」请求；业务 service 换成计数桩。"""
    stub = world.stub(CrossCheckService, "add_custom_rule", returns=STUB_RESULT)
    async with world.client(wp_cross_check.router, user=user) as client:
        response = await client.post(RULES_PATH, json=RULE_BODY)
    return response, stub, client


# ═══ 一、世界本身 ═══════════════════════════════════════════════════════════


def test_identity_registry_matches_requirements() -> None:
    """五种标准身份（需求 12.2 ①~⑤）与三种补充情形（12.4 ⑥~⑧）各一个工厂方法。"""
    assert STANDARD_IDENTITIES == ("edit_member", "review_member", "readonly_member", "non_member", "project_eqcr")
    assert SUPPLEMENTARY_IDENTITIES == ("archived_edit_member", "qc_review_member", "admin_non_member")
    assert list(IDENTITY_LABELS) == [*STANDARD_IDENTITIES, *SUPPLEMENTARY_IDENTITIES]
    assert set(EXPECTED_VERDICTS) == set(IDENTITY_DEFINITIONS) == set(IDENTITY_LABELS)
    assert [key for key in IDENTITY_LABELS if not callable(getattr(AuthzWorld, key, None))] == []


async def test_world_has_exactly_the_six_tables(world: AuthzWorld) -> None:
    names = (await world.db.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))).scalars().all()
    assert set(names) == WORLD_TABLE_NAMES == {
        "users", "projects", "project_users", "staff_members", "project_assignments", "disclosure_notes",
    }
    target = (await world.db.execute(
        select(Project.status, Project.consol_lock, Project.is_deleted).where(Project.id == TARGET_PROJECT_ID)
    )).one()
    assert tuple(target) == (ProjectStatus.execution, False, False)  # 目标项目：未归档、未合并锁定、未删除
    note = await world.add_note()
    assert (note.id, note.project_id) == (TARGET_NOTE_ID, TARGET_PROJECT_ID)


async def _same_key_rows(world: AuthzWorld, table: str):
    """返回一个按「是否已删除」建行的函数，建出的行在 ``table`` 的部分唯一索引上键相同。"""
    if table == "project_users":
        user = await world.user()
        return lambda deleted: ProjectUser(project_id=TARGET_PROJECT_ID, user_id=user.id, role=ProjectUserRole.qc,
                                           permission_level=PermissionLevel.review, is_deleted=deleted)
    if table == "project_assignments":
        staff = StaffMember(name="权限世界人员")
        world.db.add(staff)
        await world.db.flush()
        return lambda deleted: ProjectAssignment(project_id=TARGET_PROJECT_ID, staff_id=staff.id, role="qc",
                                                 is_deleted=deleted)
    return lambda deleted: DisclosureNote(project_id=TARGET_PROJECT_ID, year=2025, note_section="五、1",
                                          section_title="货币资金", is_deleted=deleted)


_UNIQUE_KEYS = {
    "project_users": "project_users.project_id, project_users.user_id",
    "project_assignments": "project_assignments.project_id, project_assignments.staff_id",
    "disclosure_notes": "disclosure_notes.project_id, disclosure_notes.year, disclosure_notes.note_section",
}


@pytest.mark.parametrize("table", list(_UNIQUE_KEYS))
async def test_partial_unique_indexes_follow_pg_semantics(world: AuthzWorld, table: str) -> None:
    """已删除行不占唯一键（PG 部分唯一索引的语义）；同一键上第二条现行行被拒。"""
    make = await _same_key_rows(world, table)
    world.db.add_all([make(True), make(True), make(False)])
    await world.db.flush()
    world.db.add(make(False))
    with pytest.raises(IntegrityError) as exc_info:
        await world.db.flush()
    assert f"UNIQUE constraint failed: {_UNIQUE_KEYS[table]}" in str(exc_info.value)


async def test_cache_storage_is_this_worlds_empty_fakeredis(world: AuthzWorld) -> None:
    """Redis 客户端换成本世界独占的 fakeredis：两个客户端名与生产取用入口都指向它，初始为空。"""
    assert core_redis.redis_client is world.redis
    assert await get_redis() is world.redis
    assert await world.redis.dbsize() == 0
    # 取值形态与生产客户端（from_url(..., decode_responses=True)）相同：取回的是 str，不是 bytes
    await world.redis.set("authz-world:shape", "edit")
    assert type(await world.redis.get("authz-world:shape")) is str
    await world.redis.delete("authz-world:shape")


# ═══ 二、身份数据 ═══════════════════════════════════════════════════════════


@pytest.mark.parametrize("key", list(IDENTITY_DEFINITIONS))
async def test_identity_data_matches_requirement_definition(world: AuthzWorld, key: str) -> None:
    """读库核对：全局角色、成员行、另一项目成员行、EQCR 别名委派条数、目标项目状态；Redis 替身里不预置任何键。"""
    identity = await world.identity(key)
    global_role, target_member, other_member, eqcr_assignments = IDENTITY_DEFINITIONS[key]
    db = world.db
    assert (identity.key, identity.label, identity.project.id) == (key, IDENTITY_LABELS[key], TARGET_PROJECT_ID)
    role = (await db.execute(select(User.role).where(User.id == identity.user.id))).scalar_one()
    assert role.value == global_role
    rows = (await db.execute(
        select(ProjectUser.project_id, ProjectUser.role, ProjectUser.permission_level, ProjectUser.is_deleted)
        .where(ProjectUser.user_id == identity.user.id)
    )).all()
    expected_rows = {(TARGET_PROJECT_ID, *target_member, False)} if target_member else set()
    if other_member:
        expected_rows.add((OTHER_PROJECT_ID, *other_member, False))
    assert sorted((pid, r.value, lv.value, gone) for pid, r, lv, gone in rows) == sorted(expected_rows)
    alias_assignments = (await db.execute(
        select(func.count(ProjectAssignment.id))
        .where(ProjectAssignment.role.in_(sorted(EXPECTED_EQCR_ALIASES)), ProjectAssignment.is_deleted == False)  # noqa: E712
    )).scalar_one()
    assert alias_assignments == eqcr_assignments  # 全世界只有身份⑤持有 EQCR 别名委派
    status, consol_lock, is_deleted = (await db.execute(
        select(Project.status, Project.consol_lock, Project.is_deleted).where(Project.id == TARGET_PROJECT_ID)
    )).one()
    expected_status = ProjectStatus.archived if key == "archived_edit_member" else ProjectStatus.execution
    assert (status, consol_lock, is_deleted) == (expected_status, False, False)
    assert await is_project_eqcr(db, identity.user, TARGET_PROJECT_ID) is (key == "project_eqcr")
    assert await world.redis.dbsize() == 0


# ═══ 三、经真实 assert_project_permission 的结论 ═══════════════════════════


_VERDICT_CASES = [
    pytest.param(key, level, EXPECTED_VERDICTS[key][i], id=f"{key}-{level}")
    for key in EXPECTED_VERDICTS
    for i, level in enumerate(LEVELS)
]


@pytest.mark.parametrize(("key", "level", "expected"), _VERDICT_CASES)
async def test_identity_verdicts_from_real_gate(world: AuthzWorld, key: str, level: str, expected: object) -> None:
    """每个用例一个独立的世界；判定的下层（归档、委派查询、RLS）都没有替换。"""
    identity = await world.identity(key)
    world.assert_not_replaced("archive_guard", "eqcr_query", "rls")
    assert await _verdict(world, identity.user, level) == expected, f"{IDENTITY_LABELS[key]} 在 {level} 级"


# ═══ 四、经 HTTP 真发请求 ═══════════════════════════════════════════════════


async def test_http_edit_member_is_allowed_through_production_gates(world: AuthzWorld) -> None:
    """放行用例：业务桩恰 1 次且 200；路由级 readonly 与端点级 edit 两道生产门禁都执行了。"""
    identity = await world.edit_member()
    response, stub, client = await _post_rule(world, identity.user)
    assert response.status_code == 200, response.text
    assert response.json() == STUB_RESULT
    ((args, kwargs),) = stub.calls
    assert (args[0], args[1]["description"], args[1]["formula"], kwargs) == (
        TARGET_PROJECT_ID, RULE_BODY["description"], RULE_BODY["formula"], {})
    client.assert_passed(GATE, times=2)
    client.assert_passed(GATE_CLOSURE, times=2)
    assert set(client.app.dependency_overrides) == {get_current_user, get_db}
    assert world.rls_calls == [str(TARGET_PROJECT_ID), str(TARGET_PROJECT_ID)]


async def test_http_review_member_is_denied_before_business(world: AuthzWorld) -> None:
    """拒绝用例：403「权限不足」，业务桩 0 次；拒绝来自生产门禁（readonly 门禁放行后，edit 门禁拒绝）。"""
    identity = await world.review_member()
    response, stub, client = await _post_rule(world, identity.user)
    assert response.status_code == 403, response.text
    assert response.json() == {"detail": "权限不足"}
    assert stub.count == 0
    client.assert_passed(GATE, times=2)


async def test_http_archived_project_is_423(world: AuthzWorld) -> None:
    """⑥：观测归档结论，归档守卫未替换；edit 门禁返回 423，业务桩 0 次。"""
    identity = await world.archived_edit_member()
    response, stub, client = await _post_rule(world, identity.user)
    world.assert_not_replaced("archive_guard")
    assert response.status_code == 423, response.text
    assert response.json() == {"detail": ARCHIVED[1]}
    assert stub.count == 0
    client.assert_passed(GATE, times=2)


async def test_http_admin_non_member_is_allowed(world: AuthzWorld) -> None:
    identity = await world.admin_non_member()
    response, stub, client = await _post_rule(world, identity.user)
    assert response.status_code == 200, response.text
    assert stub.count == 1
    client.assert_passed(GATE, times=2)


async def test_http_anonymous_request_is_401_and_never_reaches_the_gate(world: AuthzWorld) -> None:
    """未登录：不 override 当前用户，真实 get_current_user 拒绝；门禁函数本体一次也没执行，业务桩 0 次。"""
    response, stub, client = await _post_rule(world, None)
    assert response.status_code == 401, response.text
    assert response.json() == {"detail": "Not authenticated"}  # FastAPI HTTPBearer 缺凭据时的自带文案
    assert stub.count == 0
    client.assert_passed(GATE, times=0)
    client.assert_passed(GATE_CLOSURE, times=0)
    assert set(client.app.dependency_overrides) == {get_db}


# ═══ 五、「门禁 is 生产对象」自检 ═══════════════════════════════════════════


def test_gate_snapshot_is_the_production_code_of_this_tree() -> None:
    """快照即各模块里定义的生产函数，源文件在与本测试同一棵树的 app 包内（不会指到另一个 worktree）。"""
    app_dir = Path(app.__file__).resolve().parent
    assert app_dir == Path(__file__).resolve().parents[1] / "app"
    assert PRODUCTION_GATES == (
        "app.deps.require_project_access",
        "app.deps.assert_project_permission",
        "app.services.eqcr_resolver.is_project_eqcr",
        "app.routers.deliverable._guard_action",
        "app.services.note_edit_gate.assert_note_edit_access",
        "app.services.note_edit_gate.require_note_edit_access",
        "app.services.note_edit_gate.assert_note_edit_access_for_object",
        "app.services.note_edit_gate.assert_note_edit_access_on_projects",
        "app.services.note_edit_gate.assert_note_role_access",
    )
    for dotted in PRODUCTION_GATES:
        module_name, _, attr = dotted.rpartition(".")
        module = importlib.import_module(module_name)
        fn = PRODUCTION_GATE_OBJECTS[dotted]
        assert fn is getattr(module, attr), dotted
        assert (fn.__module__, fn.__qualname__) == (module_name, attr)
        source = Path(fn.__code__.co_filename).resolve()
        assert source == Path(module.__file__).resolve() and source.is_relative_to(app_dir), dotted
    assert TRACED_GATES == (
        "app.deps.assert_project_permission",
        "app.deps.require_project_access",
        "app.deps.require_project_access.<locals>.dependency",
        "app.routers.deliverable._guard_action",
        "app.services.eqcr_resolver.is_project_eqcr",
        "app.services.note_edit_gate.assert_note_edit_access",
        "app.services.note_edit_gate.assert_note_edit_access_for_object",
        "app.services.note_edit_gate.assert_note_edit_access_on_projects",
        "app.services.note_edit_gate.assert_note_role_access",
        "app.services.note_edit_gate.require_note_edit_access",
        "app.services.note_edit_gate.require_note_edit_access.<locals>.dependency",
    )
    assert_gates_are_production()


def test_gate_check_names_a_lookalike() -> None:
    """反向对照：查找函数返回一个同名替身（模块属性不动），自检必须指名失败。"""

    async def assert_project_permission(db, current_user, project_id, min_permission="readonly"):
        return current_user

    def lookup(module, attr):
        if (module.__name__, attr) == ("app.deps", "assert_project_permission"):
            return assert_project_permission
        return getattr(module, attr)

    with pytest.raises(AssertionError) as exc_info:
        assert_gates_are_production(lookup)
    assert "app.deps.assert_project_permission 已被替换为" in str(exc_info.value)


async def test_trace_flags_a_request_that_skips_the_gate(world: AuthzWorld) -> None:
    """反向对照：不经门禁的端点照样 200，但观测到的门禁执行次数全为 0，``assert_passed`` 必须指名失败。"""
    probe = APIRouter()

    @probe.post("/api/projects/{project_id}/authz-world-probe")
    async def _probe(project_id: str) -> dict:
        return {"project_id": project_id}

    api = FastAPI()
    api.include_router(probe)
    identity = await world.edit_member()
    async with world.client_for_app(api, user=identity.user) as client:
        response = await client.post(f"/api/projects/{TARGET_PROJECT_ID}/authz-world-probe")
    assert response.status_code == 200, response.text
    assert client.gate_runs == dict.fromkeys(TRACED_GATES, 0)
    with pytest.raises(AssertionError) as exc_info:
        client.assert_passed(GATE)
    assert f"上一个请求没有执行生产门禁 {GATE}" in str(exc_info.value)


def test_build_app_mounts_the_production_registration() -> None:
    registrations = [kwargs for router, kwargs in production_registrations() if router is wp_cross_check.router]
    assert len(registrations) == 1  # 生产只注册一次
    api = build_app(wp_cross_check.router)
    routes = {(method, route.path) for route in api.routes if isinstance(route, APIRoute) for method in route.methods}
    base = "/api/projects/{project_id}/cross-check"
    assert routes == {
        ("POST", f"{base}/execute"), ("GET", f"{base}/results"), ("GET", f"{base}/rules"), ("POST", f"{base}/rules/custom"),
    }


def test_build_app_refuses_an_unregistered_router() -> None:
    with pytest.raises(LookupError) as exc_info:
        build_app(APIRouter(prefix="/api/authz-world-unregistered"))
    assert "没有经 router_registry 注册" in str(exc_info.value)


_NOT_STUBBABLE = [
    pytest.param(deps, "assert_project_permission", id="gate-in-deps"),
    pytest.param(deps, "_check_project_not_archived", id="archive-guard"),
    pytest.param(eqcr_resolver, "is_project_eqcr", id="eqcr-gate"),
    pytest.param(eqcr_resolver, "_count_project_eqcr_assignments", id="eqcr-query"),
    pytest.param(wp_cross_check, "require_project_access", id="gate-factory-imported-by-router"),
]


@pytest.mark.parametrize(("owner", "attr"), _NOT_STUBBABLE)
async def test_stub_refuses_gates_and_replaceable_points(world: AuthzWorld, owner, attr: str) -> None:
    original = getattr(owner, attr)
    with pytest.raises(ValueError) as exc_info:
        world.stub(owner, attr)
    assert "不能当业务 service 打桩" in str(exc_info.value)
    assert getattr(owner, attr) is original


# ═══ 六、PG 同构版 ═══════════════════════════════════════════════════════════


async def _flush_in_savepoint(db: AsyncSession, row: object) -> None:
    async with db.begin_nested():
        db.add(row)
        await db.flush()


async def _pg_count(sql: str, **params: object) -> int:
    """另开一条连接只读计数（不在权限世界的事务里）。"""
    engine = pg_engine()
    try:
        async with engine.connect() as conn:
            return int((await conn.execute(text(sql), params)).scalar_one())
    finally:
        await engine.dispose()


@pytest.mark.pg_only
async def test_pg_world_is_isomorphic_and_leaves_no_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    async with pg_world(monkeypatch) as world:
        schema, db = world.schema, world.db
        assert world.dialect == "postgresql"
        assert (await db.execute(text("SELECT current_schemas(false)"))).scalar_one() == [schema]
        tables = await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = :s"), {"s": schema})
        assert set(tables.scalars()) == WORLD_TABLE_NAMES

        # 五种标准身份在同一个世界、同一个目标项目上：结论与 SQLite 版相同
        identities = {key: await world.identity(key) for key in STANDARD_IDENTITIES}
        for key, identity in identities.items():
            for level, expected in zip(LEVELS, EXPECTED_VERDICTS[key], strict=True):
                assert await _verdict(world, identity.user, level) == expected, f"{IDENTITY_LABELS[key]} 在 {level} 级"
        eqcr_keys = [key for key, identity in identities.items() if await is_project_eqcr(db, identity.user, TARGET_PROJECT_ID)]
        assert eqcr_keys == ["project_eqcr"]

        # 成员行部分唯一索引：PG 原生带删除条件
        user = await world.user()

        def member_row(deleted: bool) -> ProjectUser:
            return ProjectUser(project_id=TARGET_PROJECT_ID, user_id=user.id, role=ProjectUserRole.qc,
                               permission_level=PermissionLevel.review, is_deleted=deleted)

        db.add_all([member_row(True), member_row(True), member_row(False)])
        await db.flush()
        with pytest.raises(IntegrityError) as exc_info:
            await _flush_in_savepoint(db, member_row(False))
        assert 'duplicate key value violates unique constraint "idx_project_users_project_user"' in str(exc_info.value)
        assert (await world.add_note()).id == TARGET_NOTE_ID

        # HTTP：端点里的 commit 只释放保存点
        allowed, allowed_stub, allowed_client = await _post_rule(world, identities["edit_member"].user)
        assert allowed.status_code == 200, allowed.text
        assert allowed_stub.count == 1
        allowed_client.assert_passed(GATE, times=2)
        denied, denied_stub, denied_client = await _post_rule(world, identities["review_member"].user)
        assert (denied.status_code, denied.json()) == (403, {"detail": "权限不足"})
        assert denied_stub.count == 0
        denied_client.assert_passed(GATE, times=2)

        # ⑥ 放在最后：它把目标项目置为已归档
        archived = await world.archived_edit_member()
        assert await _verdict(world, archived.user, "edit") == ARCHIVED

        # 世界里的数据没有落到 public 的正式表
        assert await _pg_count("SELECT count(*) FROM public.projects WHERE id = :pid", pid=TARGET_PROJECT_ID) == 0

    assert await _pg_count("SELECT count(*) FROM pg_namespace WHERE nspname = :s", s=schema) == 0
