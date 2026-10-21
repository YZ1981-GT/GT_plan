"""角色映射单一真源与角色上下文兜底（partner-manager-edit-permission）。

一、角色映射的纯函数与推导常量（任务 2.1；需求 2.1、2.2、3.3、3.8、7.2）：
    ``resolve_member_mapping`` 的 EQCR 优先、取最高级别、项目角色按固定先后、与顺序无关、空输入报错；
    ``_ROLE_TIEBREAK`` 覆盖角色映射与 ``UNMAPPED_ROLE`` 写得出的全部项目角色。
二、角色上下文两处委派兜底的合并口径（任务 2.3；需求 2.3，design §4.2）：真实 SQLite 内存库，
    同一项目多条委派（经多条人员库记录）合并、``scope_cycles`` 取 ``assigned_at`` 最早一条、删除标记不计。
三、角色上下文兜底与角色映射对拍（任务 2.4；需求 2.2、2.3、2.4、2.8，design Property 1）：Property 1 的 hypothesis 测试
    与固定样例（``ROLE_MAP`` 每个键、五个未登记串），需求 2.8 样例（审计日志哈希链校验走真实端点），经用户第二条人员库记录
    持有的委派（N3）。

参数化固定样例的期望值按需求原文写出，不由被测函数推出。
"""
from __future__ import annotations

import asyncio
import itertools
import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from hypothesis import example, given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_log_models import AuditLogEntry
from app.models.base import Base, PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.routers import audit_logs
from app.services.assignment_service import (
    _LEVEL_RANK,
    _ROLE_TIEBREAK,
    EQCR_ROLE_ALIASES,
    PARTNER_MANAGER_ROLE_ALIASES,
    ROLE_MAP,
    UNMAPPED_ROLE,
    map_assignment_role,
    resolve_member_mapping,
)
from app.services.role_context_service import RoleContextService
from app.workers.audit_log_writer_worker import GENESIS_HASH
from app.workers.audit_log_writer_worker import _compute_entry_hash as _writer_entry_hash

R, L = ProjectUserRole, PermissionLevel
PARTNER_EDIT = (R.partner, L.edit)
MANAGER_EDIT = (R.manager, L.edit)
QC_REVIEW = (R.qc, L.review)
AUDITOR_EDIT = (R.auditor, L.edit)
EQCR_FORCED = (R.partner, L.review)
READONLY = (R.readonly, L.readonly)

# 未登记的委派角色：空串、大小写与首尾空白变体、枚举值同名串、任意中文（需求 2.2 精确匹配）
UNREGISTERED = ["", "Manager", " manager ", "manager ", "EQCR", " eqcr", "独立复核合伙人 ", "readonly", "观察员"]


# ═══════════════════════════════════════════════════════════════════════════
# 一、角色映射的纯函数与推导常量（任务 2.1）
# ═══════════════════════════════════════════════════════════════════════════


def test_map_assignment_role_is_exact_match() -> None:
    assert UNMAPPED_ROLE == READONLY
    for role in UNREGISTERED:
        assert map_assignment_role(role) == READONLY, repr(role)
    for role, value in ROLE_MAP.items():
        assert map_assignment_role(role) is value, role


def test_single_role_equals_map_assignment_role() -> None:
    """只有一条委派时，合并口径与单条查表逐值相等（design §4.2，角色上下文兜底依赖此等价）。"""
    for role in [*ROLE_MAP, *UNREGISTERED]:
        assert resolve_member_mapping([role]) == map_assignment_role(role), repr(role)


@pytest.mark.parametrize(
    "roles",
    [
        ["eqcr"],
        ["独立复核合伙人"],
        ["manager", "eqcr"],
        ["signing_partner", "独立复核合伙人", "auditor"],
        ["eqcr", "qc"],
        ["观察员", "eqcr"],
    ],
    ids=["eqcr", "cn-alias", "with-manager", "with-partner-and-auditor", "with-qc", "with-unregistered"],
)
def test_eqcr_alias_forces_partner_review(roles: list[str]) -> None:
    """任一委派属于 EQCR 别名集合 ⇒ (partner, review)，同时持有 edit 级角色也不升级（需求 3.3、3.8）。"""
    assert resolve_member_mapping(roles) == EQCR_FORCED


@pytest.mark.parametrize(
    "roles,expected",
    [
        (["qc", "auditor"], AUDITOR_EDIT),  # qc 在先后表里靠前，但级别低
        (["质控", "项目经理"], MANAGER_EDIT),
        (["质控", "观察员"], QC_REVIEW),
        (["观察员", "", "Manager"], READONLY),
        (["EQCR", "manager"], MANAGER_EDIT),  # 大小写变体不算 EQCR
        ([" eqcr", "质控"], QC_REVIEW),  # 首尾空白变体不算 EQCR
        (["manager", "manager"], MANAGER_EDIT),
    ],
    ids=["qc+auditor", "qc-cn+manager-cn", "qc-cn+unregistered", "all-unregistered",
         "upper-eqcr+manager", "spaced-eqcr+qc-cn", "duplicate"],
)
def test_highest_level_wins(roles: list[str], expected: tuple) -> None:
    """没有 EQCR 别名时取角色映射给出的最高级别（需求 3.8）。"""
    assert resolve_member_mapping(roles) == expected


@pytest.mark.parametrize(
    "roles,expected",
    [
        (["auditor", "manager"], MANAGER_EDIT),
        (["助理", "合伙人"], PARTNER_EDIT),
        (["项目经理", "signing_partner"], PARTNER_EDIT),
        (["assistant", "审计员", "manager", "partner"], PARTNER_EDIT),
        (["审计员", "assistant"], AUDITOR_EDIT),
    ],
    ids=["auditor+manager", "assistant-cn+partner-cn", "manager-cn+signing", "four-edit", "auditors-only"],
)
def test_project_role_tiebreak_in_fixed_order(roles: list[str], expected: tuple) -> None:
    """同一最高级别有多个项目角色候选时按 partner、manager、qc、auditor、readonly 取第一个（需求 3.8）。"""
    assert resolve_member_mapping(roles) == expected


def test_tiebreak_order_matches_requirement() -> None:
    assert _ROLE_TIEBREAK == (R.partner, R.manager, R.qc, R.auditor, R.readonly)


@pytest.mark.parametrize(
    "roles,expected",
    [
        (["auditor", "manager", "qc"], MANAGER_EDIT),
        (["助理", "eqcr", "合伙人"], EQCR_FORCED),
        (["观察员", "质控", "Manager"], QC_REVIEW),
        (["signing_partner", "项目经理", "审计员", "qc"], PARTNER_EDIT),
    ],
    ids=["manager-wins", "eqcr-wins", "qc-wins", "partner-wins"],
)
def test_result_independent_of_order(roles: list[str], expected: tuple) -> None:
    """全部排列结果相同；任意可迭代对象（含一次性迭代器）与列表结果相同（需求 3.8）。"""
    results = {resolve_member_mapping(list(p)) for p in itertools.permutations(roles)}
    assert results == {expected}
    assert resolve_member_mapping(iter(roles)) == expected
    assert resolve_member_mapping(tuple(roles)) == expected


@pytest.mark.parametrize("make_empty", [list, tuple, lambda: iter(())], ids=["list", "tuple", "iterator"])
def test_empty_roles_raise_value_error(make_empty) -> None:
    empty = make_empty()
    with pytest.raises(ValueError) as excinfo:
        resolve_member_mapping(empty)
    assert "需要至少一个委派角色" in str(excinfo.value)


def test_single_string_is_rejected() -> None:
    """单个字符串会被逐字拆开、静默落到未登记，按误用拒绝。"""
    with pytest.raises(TypeError) as excinfo:
        resolve_member_mapping("manager")
    assert "不接受单个字符串" in str(excinfo.value)


def test_role_tiebreak_covers_every_mappable_project_role() -> None:
    """先后表须覆盖角色映射写得出的全部项目角色，否则新增项目角色时 ``next`` 抛 StopIteration。"""
    mappable = {role for role, _ in ROLE_MAP.values()} | {UNMAPPED_ROLE[0]}
    assert set(_ROLE_TIEBREAK) == mappable
    assert len(_ROLE_TIEBREAK) == len(mappable)  # 无重复项
    assert set(_LEVEL_RANK) == set(PermissionLevel)
    assert sorted(PermissionLevel, key=_LEVEL_RANK.__getitem__) == [L.readonly, L.review, L.edit]


def test_derived_alias_sets() -> None:
    """两个别名集合由角色映射推导，结果等于术语表（需求 2.1、7.2）。"""
    assert type(EQCR_ROLE_ALIASES) is frozenset
    assert EQCR_ROLE_ALIASES == frozenset({"eqcr", "独立复核合伙人"})
    assert type(PARTNER_MANAGER_ROLE_ALIASES) is frozenset
    assert PARTNER_MANAGER_ROLE_ALIASES == frozenset({"signing_partner", "partner", "合伙人", "manager", "项目经理"})


# ═══════════════════════════════════════════════════════════════════════════
# 二、角色上下文两处委派兜底的合并口径（任务 2.3；design §4.2）
# ═══════════════════════════════════════════════════════════════════════════
# 真实 SQLite 内存库 + 真实 RoleContextService，不替换任何判定。只钉任务 2.4 用例以外的口径：
# 同一项目多条委派（各挂在用户的一条人员库记录上）的合并、scope_cycles 取 assigned_at 最早一条、删除标记。

_CTX_TABLES = [User.__table__, Project.__table__, ProjectUser.__table__,
               StaffMember.__table__, ProjectAssignment.__table__]


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_CTX_TABLES)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


async def _add(db: AsyncSession, row):
    db.add(row)
    await db.flush()
    return row


async def _auditor(db: AsyncSession) -> User:
    tag = uuid.uuid4().hex[:12]
    return await _add(db, User(username=f"u-{tag}", email=f"{tag}@test.local", hashed_password="x",
                               role=UserRole.auditor))


async def _project(db: AsyncSession, *, deleted: bool = False) -> Project:
    return await _add(db, Project(name="【测试】角色上下文", client_name="甲", is_deleted=deleted))


async def _assign(db: AsyncSession, project: Project, user: User, role: str, *, at: datetime | None = None,
                  cycles: list[str] | None = None, staff_deleted: bool = False, deleted: bool = False,
                  assignment_id: uuid.UUID | None = None, staff_id: uuid.UUID | None = None) -> ProjectAssignment:
    """每条委派挂在该用户的一条新人员库记录上（同一用户多条人员库记录，N3）。"""
    staff = await _add(db, StaffMember(id=staff_id or uuid.uuid4(), user_id=user.id, name="测试人员",
                                       is_deleted=staff_deleted))
    return await _add(db, ProjectAssignment(
        id=assignment_id or uuid.uuid4(), project_id=project.id, staff_id=staff.id, role=role,
        assigned_at=at, assigned_cycles=cycles, is_deleted=deleted))


def _at(month: int) -> datetime:
    return datetime(2026, month, 1, tzinfo=timezone.utc)


def _delegated(ctx: dict, project: Project) -> list[tuple[str, str]]:
    return [(p["role"], p["permission_level"]) for p in ctx["projects"] if p["project_id"] == str(project.id)]


async def test_context_fallback_merges_assignments_and_takes_earliest_scope(db: AsyncSession) -> None:
    """三条委派经三条人员库记录：取最高级别、项目角色按固定先后；scope_cycles 取 assigned_at 最早一条，
    空值排最后。插入顺序与日期顺序相反，「取第一条记录」得不出该结论。"""
    p, u = await _project(db), await _auditor(db)
    await _assign(db, p, u, "qc", at=None, cycles=["G"])
    await _assign(db, p, u, "manager", at=_at(2), cycles=["E", "F"])
    await _assign(db, p, u, "auditor", at=_at(1), cycles=["D"])
    svc = RoleContextService(db)
    assert await svc.get_project_role(u.id, p.id) == {
        "source": "project_assignments", "role": "manager", "permission_level": "edit", "scope_cycles": ["D"]}
    ctx = await svc.get_global_context(u.id)
    assert _delegated(ctx, p) == [("manager", "edit")]
    assert ctx["project_count"] == 1


async def test_context_fallback_scope_tie_broken_by_assignment_id(db: AsyncSession) -> None:
    """同刻（同批保存）的两条委派按委派 id 升序取第一条。id 较大的一条先插入、人员库记录 id 也较小，
    按插入顺序或按人员库记录排序都会取到它。"""
    p, u = await _project(db), await _auditor(db)
    await _assign(db, p, u, "auditor", at=_at(3), cycles=["late"],
                  assignment_id=uuid.UUID(int=2), staff_id=uuid.UUID(int=1))
    await _assign(db, p, u, "auditor", at=_at(3), cycles=["early"],
                  assignment_id=uuid.UUID(int=1), staff_id=uuid.UUID(int=2))
    assert (await RoleContextService(db).get_project_role(u.id, p.id))["scope_cycles"] == ["early"]


async def test_context_fallback_eqcr_alias_wins_in_both_paths(db: AsyncSession) -> None:
    """manager 与「独立复核合伙人」两条委派：两处兜底都得 (partner, review)。"""
    p, u = await _project(db), await _auditor(db)
    await _assign(db, p, u, "manager", at=_at(1))
    await _assign(db, p, u, "独立复核合伙人", at=_at(2))
    svc = RoleContextService(db)
    r = await svc.get_project_role(u.id, p.id)
    assert (r["source"], r["role"], r["permission_level"]) == ("project_assignments", "partner", "review")
    assert _delegated(await svc.get_global_context(u.id), p) == [("partner", "review")]


async def test_context_fallback_ignores_deleted_rows(db: AsyncSession) -> None:
    """已删除的人员库记录、已删除的委派都不计；全局上下文另不含已删除项目。"""
    p, gone, u = await _project(db), await _project(db, deleted=True), await _auditor(db)
    await _assign(db, p, u, "manager", at=_at(1), staff_deleted=True)
    await _assign(db, p, u, "signing_partner", at=_at(1), deleted=True)
    await _assign(db, gone, u, "manager", at=_at(1))
    svc = RoleContextService(db)
    assert await svc.get_project_role(u.id, p.id) == {
        "source": "system_role_fallback", "role": "auditor", "permission_level": "readonly", "scope_cycles": None}
    ctx = await svc.get_global_context(u.id)
    assert (ctx["projects"], ctx["effective_role"]) == ([], "auditor")


# ═══════════════════════════════════════════════════════════════════════════
# 三、角色上下文兜底与角色映射对拍（任务 2.4；需求 2.2、2.3、2.4、2.8，design Property 1）
# ═══════════════════════════════════════════════════════════════════════════
# 被测：RoleContextService 的两处委派兜底 —— get_project_role（该项目没有未删除成员行时）与 get_global_context
# （仅由委派补充的项目条目）。真实 SQLite 内存库 + 真实服务，不替换任何判定。
# 模型：ROLE_MAP.get(r, (readonly, readonly)) 的字符串取值。以生产 ROLE_MAP 为对拍对象是需求 12.6 明文允许的例外
# （ROLE_MAP 由任务 2.2 的期望表 tests/role_map_expected.py 逐键钉住）；默认值用本文件的 READONLY 字面量，不读
# UNMAPPED_ROLE。hypothesis 样例各用一个独立的内存库（asyncio.run，同 test_eqcr_resolver_property.py）。每条委派挂在
# 用户的一条新人员库记录上，（项目，人员库记录）不重复，SQLite 上不带删除条件的 idx_assignment_project_staff 不会误拒。

_ROLE_MAX_LEN = 30  # project_assignments.role 是 VARCHAR(30)
# 需求 2.4 的固定样例：空串、大小写变体、首尾带空格的别名、与项目级别同名的串、任意中文，都不是 ROLE_MAP 的键
_FIXED_UNREGISTERED = (
    pytest.param("", id="empty"),
    pytest.param("Manager", id="Manager"),
    pytest.param(" manager ", id="spaced-manager"),
    pytest.param("readonly", id="readonly"),
    pytest.param("观察员", id="observer-cn"),
)
_BLANKS = (" ", "  ", "\t", "\n", "\u3000")


def _model_pair(role: str) -> tuple[str, str]:
    """Property 1 的模型：ROLE_MAP 对 r 给出的值，未登记取 (readonly, readonly)，按字符串取值比较。"""
    project_role, level = ROLE_MAP.get(role, READONLY)
    return project_role.value, level.value


def _pad(key: str, blank: str, side: str) -> str:
    return (blank if side != "trail" else "") + key + (blank if side != "lead" else "")


_role_keys = st.sampled_from(sorted(ROLE_MAP))
_role_strings = st.one_of(
    _role_keys,
    _role_keys.flatmap(lambda key: st.sampled_from((key.upper(), key.capitalize(), key.swapcase(), key.title()))),
    st.builds(_pad, _role_keys, st.sampled_from(_BLANKS), st.sampled_from(("lead", "trail", "both"))),
    # PG 的 varchar 存不了 NUL；代理码位编码不了 UTF-8
    st.text(st.characters(exclude_categories=("Cs",), exclude_characters="\x00"), min_size=0, max_size=_ROLE_MAX_LEN),
)
# 该项目上一条已删除的成员行（「没有未删除成员行」仍成立）：无，或任意项目角色与级别
_stale_members = st.none() | st.tuples(st.sampled_from(list(ProjectUserRole)), st.sampled_from(list(PermissionLevel)))


def _str_pair(entry: dict) -> tuple[str, str]:
    """取（项目角色，项目级别）并核对是字符串（需求 2.3）：str 子类的枚举成员与其取值相等，只比相等测不出来。"""
    pair = (entry["role"], entry["permission_level"])
    assert [type(value) for value in pair] == [str, str], f"兜底返回的不是字符串：{pair!r}"
    return pair


async def _seed_single_delegation(
    db: AsyncSession, role: str, *, global_role: UserRole = UserRole.auditor,
    stale_member: tuple[ProjectUserRole, PermissionLevel] | None = None,
) -> tuple[User, Project]:
    """「在未删除项目上没有未删除成员行、只有一条角色为 r 的现行委派」的用户，只参与这一个项目。"""
    assert len(role) <= _ROLE_MAX_LEN, f"委派角色超出 VARCHAR(30)：{role!r}"
    tag = uuid.uuid4().hex[:12]
    user = await _add(db, User(username=f"u-{tag}", email=f"{tag}@test.local", hashed_password="x", role=global_role))
    project = await _project(db)
    if stale_member is not None:
        await _add(db, ProjectUser(project_id=project.id, user_id=user.id, role=stale_member[0],
                                   permission_level=stale_member[1], is_deleted=True))
    await _assign(db, project, user, role)
    return user, project


async def _assert_fallbacks_equal(db: AsyncSession, role: str, expected: tuple[str, str], **seed) -> None:
    """两处兜底返回的（项目角色，项目级别）都等于 expected。"""
    user, project = await _seed_single_delegation(db, role, **seed)
    svc = RoleContextService(db)
    single = await svc.get_project_role(user.id, project.id)
    assert single["source"] == "project_assignments", f"{role!r}：单项目查询没有走委派兜底（{single['source']}）"
    assert _str_pair(single) == expected, f"{role!r}：单项目角色查询的兜底与期望不符"
    ctx = await svc.get_global_context(user.id)
    entries = [_str_pair(p) for p in ctx["projects"] if p["project_id"] == str(project.id)]
    assert entries == [expected], f"{role!r}：全局上下文的委派补充条目与期望不符"
    assert ctx["project_count"] == 1


def _run_in_fresh_db(scenario: Callable[[AsyncSession], Awaitable[None]]) -> None:
    """每个 hypothesis 样例一个独立的 SQLite 内存库（hypothesis 不能复用函数级的 db 夹具）。"""

    async def _main() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all, tables=_CTX_TABLES)
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                await scenario(session)
        finally:
            await engine.dispose()

    asyncio.run(_main())


@settings(max_examples=5, deadline=None)
@given(role=_role_strings, global_role=st.sampled_from(list(UserRole)), stale_member=_stale_members)
@example(role="", global_role=UserRole.auditor, stale_member=None)
@example(role="Manager", global_role=UserRole.auditor, stale_member=None)
@example(role=" manager ", global_role=UserRole.auditor, stale_member=None)
@example(role="readonly", global_role=UserRole.auditor, stale_member=None)
@example(role="观察员", global_role=UserRole.auditor, stale_member=None)
@example(role="signing_partner", global_role=UserRole.auditor, stale_member=None)  # 需求 2.8 的委派角色
# 全局 admin 与该项目上一条已删除的 (qc, review) 成员行，都不改变兜底结论
@example(role="项目经理", global_role=UserRole.admin, stale_member=(ProjectUserRole.qc, PermissionLevel.review))
def test_property_1_fallback_matches_role_map(
    role: str, global_role: UserRole, stale_member: tuple[ProjectUserRole, PermissionLevel] | None
) -> None:
    # Feature: partner-manager-edit-permission, Property 1: 角色上下文兜底与角色映射对拍
    _run_in_fresh_db(lambda db: _assert_fallbacks_equal(
        db, role, _model_pair(role), global_role=global_role, stale_member=stale_member))


@pytest.mark.parametrize("role", list(ROLE_MAP))
async def test_property_1_every_role_map_key(db: AsyncSession, role: str) -> None:
    """Property 1 的固定样例：ROLE_MAP 的每个键（含需求 2.8 的 signing_partner），两处兜底都等于该键的取值。"""
    await _assert_fallbacks_equal(db, role, _model_pair(role))


@pytest.mark.parametrize("role", _FIXED_UNREGISTERED)
async def test_property_1_unregistered_fixed_examples(db: AsyncSession, role: str) -> None:
    """Property 1 的固定样例（需求 2.4）：期望按需求 2.2、2.3 写死为 (readonly, readonly)，不由 ROLE_MAP 推出。"""
    assert role not in ROLE_MAP, f"{role!r} 已是 ROLE_MAP 的键，不再是未登记样例"
    await _assert_fallbacks_equal(db, role, ("readonly", "readonly"))


async def test_fallback_finds_delegation_on_second_staff_record(db: AsyncSession) -> None:
    """N3：P 上的委派挂在用户的第二条人员库记录上（第一条只在另一项目 Q 有委派），两处兜底都能识别。
    第一条记录先插入、id 也较小：按「只取第一条人员库记录」查不到 P 的委派。"""
    p, q, u = await _project(db), await _project(db), await _auditor(db)
    await _assign(db, q, u, "qc", at=_at(1), staff_id=uuid.UUID(int=1))
    await _assign(db, p, u, "manager", at=_at(2), cycles=["E"], staff_id=uuid.UUID(int=2))
    svc = RoleContextService(db)
    assert await svc.get_project_role(u.id, p.id) == {
        "source": "project_assignments", "role": "manager", "permission_level": "edit", "scope_cycles": ["E"]}
    ctx = await svc.get_global_context(u.id)
    assert (_delegated(ctx, p), _delegated(ctx, q), ctx["project_count"]) == (
        [("manager", "edit")], [("qc", "review")], 2)


# ─── 需求 2.8：signing_partner 委派的用户，含审计日志哈希链校验（真实端点） ────────────────
# 端点级：真发 GET /api/audit-logs/verify-chain，由真实 verify_chain → RoleContextService.get_project_role 判定；
# 只替换当前用户（get_current_user）与会话（get_db），审计日志条目、人员库记录、委派都以库中数据给出。


@pytest_asyncio.fixture
async def chain_db():
    """db 夹具的五张表之外另建审计日志表。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[*_CTX_TABLES, AuditLogEntry.__table__])
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


async def _seed_project_chain(db: AsyncSession, project: Project, user: User, length: int = 2) -> None:
    """按写入端（audit_log_writer_worker）的算法在项目上写一条完整的哈希链，由校验端点逐条重算。"""
    prev_hash = GENESIS_HASH
    for seq in range(length):
        ts = datetime(2026, 10, 20, 9, seq)  # 不带时区：与 SQLite 往返后的 isoformat 一致
        action_type, payload = "note_edit", {"project_id": str(project.id), "seq": seq}
        entry_hash = _writer_entry_hash(ts.isoformat(), str(user.id), action_type, None,
                                        json.dumps(payload, sort_keys=True, ensure_ascii=False), prev_hash)
        await _add(db, AuditLogEntry(id=uuid.uuid4(), ts=ts, user_id=user.id, action_type=action_type,
                                     object_type="disclosure_note", payload=payload, prev_hash=prev_hash,
                                     entry_hash=entry_hash))
        prev_hash = entry_hash


async def _verify_chain(db: AsyncSession, user: User, project: Project) -> Response:
    api = FastAPI()
    api.include_router(audit_logs.router, prefix="/api")  # 与 router_registry/system.py 的注册前缀相同

    async def _db():
        yield db

    async def _user():  # override 不能带 *args/**kwargs：FastAPI 会把它们当成必填查询参数（422）
        return user

    api.dependency_overrides[get_db] = _db
    api.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        return await client.get("/api/audit-logs/verify-chain", params={"project_id": str(project.id)})


async def _seed_requirement_2_8(db: AsyncSession) -> tuple[User, Project]:
    """需求 2.8 的用户：全局 auditor、只参与一个项目、在该项目没有成员行、只有一条 signing_partner 现行委派。"""
    p, u = await _project(db), await _auditor(db)
    await _assign(db, p, u, "signing_partner", at=_at(1), cycles=["D", "E"])
    return u, p


async def test_requirement_2_8_fallbacks_and_effective_role(db: AsyncSession) -> None:
    """需求 2.8：两处兜底都得 (partner, edit)，全局最高角色为 partner（改动前兜底为 (auditor, edit)，最高角色 auditor）。"""
    u, p = await _seed_requirement_2_8(db)
    svc = RoleContextService(db)
    assert await svc.get_project_role(u.id, p.id) == {
        "source": "project_assignments", "role": "partner", "permission_level": "edit", "scope_cycles": ["D", "E"]}
    ctx = await svc.get_global_context(u.id)
    assert ctx["projects"] == [{"project_id": str(p.id), "project_name": p.name, "client_name": p.client_name,
                                "role": "partner", "permission_level": "edit"}]
    assert (ctx["system_role"], ctx["effective_role"], ctx["project_count"]) == ("auditor", "partner", 1)


async def test_requirement_2_8_audit_chain_verification_allowed(chain_db: AsyncSession) -> None:
    """需求 2.8：审计日志哈希链校验对该用户在该项目放行（改动前兜底为 (auditor, edit)，被拒）。
    对照：同一项目上只持有未登记委派的另一用户，被同一端点以 403 拒绝 —— 放行来自角色判定，不是端点不设防。"""
    db = chain_db
    u, p = await _seed_requirement_2_8(db)
    await _seed_project_chain(db, p, u)
    allowed = await _verify_chain(db, u, p)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json() == {"valid": True, "entries_checked": 2}

    outsider = await _auditor(db)
    await _assign(db, p, outsider, "观察员", at=_at(1))
    denied = await _verify_chain(db, outsider, p)
    assert denied.status_code == 403, denied.text
    assert denied.json()["detail"]["error_code"] == "FORBIDDEN_AUDIT_CHAIN"
    assert denied.json()["detail"]["message"] == "当前用户无权查询该项目的审计哈希链"
