"""EQCR 判定的性质测试（partner-manager-edit-permission 任务 2.7；需求 7.1、7.5、11.1；design Property 9、§8.3）。

被测：``app.services.eqcr_resolver`` 的 ``is_project_eqcr``、``project_eqcr_user_ids``，以及核对两者同口径时直接调用的
下层取数点 ``_count_project_eqcr_assignments``（即 ``is_project_eqcr`` 的委派分支）。都在真实 SQLite 库上调用，
本文件不替换任何函数。

- Property 9（``test_property_9_eqcr_resolver_matches_model``）：``is_project_eqcr(被测用户, P)`` 等于模型「全局角色为
  eqcr ∨ 存在 P 上的现行委派，其人员库记录关联到被测用户、委派角色属于 EQCR 别名集合」。模型在本文件独立计算：
  别名集合取需求 2.5 期望表（``tests/role_map_expected.py``）中取值为 (partner, review) 的键，不读生产代码的
  ``EQCR_ROLE_ALIASES`` / ``ROLE_MAP``。
- 需求 7.5 固定样例 ①~⑩（``test_property_9_fixed_examples``）：期望结论按需求原文写死，逐个断言。
- ``project_eqcr_user_ids(P)``（需求 11.1）：用同一生成器、同一组样例对拍模型「在 P 持有 EQCR 别名现行委派的用户集合」
  （不含全局角色分支）；并对数据里的每个用户断言「委派分支为真 ⇔ 属于该集合」与
  「``is_project_eqcr`` ⇔ 全局角色为 eqcr ∨ 属于该集合」。

生成维度（需求 7.5）：全局角色取 ``UserRole`` 全部取值；被测用户经 1~2 条人员库记录持有 0~4 条委派，项目取 P 或 Q，
委派与人员库记录各自删 / 未删，委派角色取期望表全部键、这些键的大小写与首尾空白变体、长度 0~30 的任意字符串，遵守 F4；
干扰数据为另一用户在 P 的 EQCR 委派、未关联用户的人员库记录在 P 的 EQCR 委派、被测用户在 P 的成员行（项目角色可取
eqcr，级别任取）。另加需求 7.1 细则中两个不应影响结论的维度：P 是否软删、人员状态。

测试库：每个样例一个独立的 SQLite 内存库，建 users / projects / staff_members / project_assignments / project_users。
``idx_assignment_project_staff`` 在模型里只声明了 ``postgresql_where``，SQLite 上 create_all 建出的是不带条件的唯一索引，
会拒绝 PG 上合法的「同一（项目，人员库记录）一条已删除委派 + 一条现行委派」。本文件建表后删掉它，按模型声明的列与条件
另建部分唯一索引（与 PG 上的 F4 等价），由 ``test_sqlite_assignment_index_is_f4_equivalent`` 钉住这一等价。
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base, PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.services.eqcr_resolver import _count_project_eqcr_assignments, is_project_eqcr, project_eqcr_user_ids
from tests.role_map_expected import EXPECTED_ROLE_MAP

# 模型的别名集合：需求 2.5 期望表中取值为 (partner, review) 的键（需求 7.5）；不读生产代码。
_MODEL_EQCR_ALIASES: frozenset[str] = frozenset(
    key for key, value in EXPECTED_ROLE_MAP.items() if value == ("partner", "review")
)
_ALIASES = tuple(sorted(_MODEL_EQCR_ALIASES))
_ROLE_KEYS = tuple(sorted(EXPECTED_ROLE_MAP))
_STAFF_STATUSES = ("active", "on_leave", "resigned")  # staff_members.status：在职 / 休假 / 离职
_ROLE_MAX_LEN = 30  # project_assignments.role 是 VARCHAR(30)


# ─── 数据描述 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Assign:
    """一条委派：项目（"P" 或 "Q"）、委派角色、是否已删除。"""

    project: str
    role: str
    deleted: bool = False


@dataclass(frozen=True)
class Staff:
    """一条人员库记录及经它持有的委派。"""

    assignments: tuple[Assign, ...] = ()
    deleted: bool = False
    status: str = "active"


@dataclass(frozen=True)
class Member:
    """在 P 的成员行（project_users）。"""

    role: ProjectUserRole
    level: PermissionLevel
    deleted: bool = False


@dataclass(frozen=True)
class Person:
    """一个登录用户：全局角色、关联到他的人员库记录、在 P 的成员行。"""

    global_role: UserRole
    staff: tuple[Staff, ...]
    member_in_p: Member | None = None


@dataclass(frozen=True)
class World:
    """一个样例的全部数据：被测用户与干扰数据。"""

    tested: Person
    others: tuple[Person, ...] = ()  # 干扰：其他用户，各持有一条 P 上的 EQCR 别名现行委派
    unlinked: tuple[Staff, ...] = ()  # 干扰：未关联用户（user_id 为空）的人员库记录
    p_deleted: bool = False  # P 是否软删（需求 7.1 细则：不影响结论）

    def people(self) -> tuple[tuple[str, Person], ...]:
        return (("tested", self.tested), *((f"other{i}", person) for i, person in enumerate(self.others, 1)))


# ─── 模型（需求 7.1 原文；不调用被测函数） ──────────────────────────────────


def _model_assignment_branch(person: Person) -> bool:
    """需求 7.1 第二项：P 上有一条委派，委派与其人员库记录都未删除，角色按字符串精确匹配属于别名集合。"""
    return any(
        not record.deleted and not item.deleted and item.project == "P" and item.role in _MODEL_EQCR_ALIASES
        for record in person.staff
        for item in record.assignments
    )


def _model_is_eqcr(person: Person) -> bool:
    """需求 7.1：全局角色为 eqcr ∨ 委派条件。admin 不豁免；成员行、人员状态、P 是否软删都不参与。"""
    return person.global_role.value == "eqcr" or _model_assignment_branch(person)


# ─── 生成器（需求 7.5） ──────────────────────────────────────────────────────

_BLANKS = (" ", "  ", "\t", "\n", "\u3000")
_base_keys = st.one_of(st.sampled_from(_ALIASES), st.sampled_from(_ROLE_KEYS))


def _pad(key: str, blank: str, side: str) -> str:
    return (blank if side != "trail" else "") + key + (blank if side != "lead" else "")


_role_strings = st.one_of(
    st.sampled_from(_ALIASES),  # 单列别名，让委派分支为真的样例常见一些
    st.sampled_from(_ROLE_KEYS),
    _base_keys.flatmap(lambda key: st.sampled_from((key.upper(), key.capitalize(), key.swapcase()))),
    st.builds(_pad, _base_keys, st.sampled_from(_BLANKS), st.sampled_from(("lead", "trail", "both"))),
    # PG 的 varchar 存不了 NUL，真实委派角色里不会有它
    st.text(st.characters(exclude_categories=("Cs",), exclude_characters="\x00"), max_size=_ROLE_MAX_LEN),
)


@st.composite
def _tested_people(draw: st.DrawFn) -> Person:
    """被测用户：1~2 条人员库记录合计持有 0~4 条委派；按 F4，同一记录在同一项目至多一条现行委派。"""
    n_staff = draw(st.integers(min_value=1, max_value=2))
    groups: list[list[Assign]] = [[] for _ in range(n_staff)]
    live: set[tuple[int, str]] = set()
    for _ in range(draw(st.integers(min_value=0, max_value=4))):
        idx = draw(st.integers(min_value=0, max_value=n_staff - 1))
        project = draw(st.sampled_from(("P", "Q")))
        role = draw(_role_strings)
        deleted = (idx, project) in live or draw(st.booleans())  # 已有现行委派 ⇒ 这一条只能是已删除的
        if not deleted:
            live.add((idx, project))
        groups[idx].append(Assign(project, role, deleted))
    staff = tuple(Staff(tuple(g), draw(st.booleans()), draw(st.sampled_from(_STAFF_STATUSES))) for g in groups)
    members = st.builds(
        Member, st.sampled_from(list(ProjectUserRole)), st.sampled_from(list(PermissionLevel)), st.booleans()
    )
    return Person(draw(st.sampled_from(list(UserRole))), staff, draw(st.none() | members))


_other_people = st.builds(
    lambda role, alias: Person(role, (Staff((Assign("P", alias),)),)),
    st.sampled_from(list(UserRole)),
    st.sampled_from(_ALIASES),
)
_unlinked_staff = st.builds(lambda alias: Staff((Assign("P", alias),)), st.sampled_from(_ALIASES))
_worlds = st.builds(
    World,
    tested=_tested_people(),
    others=st.lists(_other_people, max_size=1).map(tuple),
    unlinked=st.lists(_unlinked_staff, max_size=1).map(tuple),
    p_deleted=st.booleans(),
)


# ─── 测试库与观测 ────────────────────────────────────────────────────────────

_TABLES = [User.__table__, Project.__table__, StaffMember.__table__, ProjectAssignment.__table__, ProjectUser.__table__]
_ASSIGNMENT_INDEX = "idx_assignment_project_staff"


def _f4_index_ddl() -> str:
    """按模型声明（列、唯一、postgresql_where）给 SQLite 写一条等价的部分唯一索引。"""
    (index,) = [i for i in ProjectAssignment.__table__.indexes if i.name == _ASSIGNMENT_INDEX]
    assert index.unique is True, f"{_ASSIGNMENT_INDEX} 不再是唯一索引"
    columns = ", ".join(column.name for column in index.columns)
    where = index.dialect_options["postgresql"]["where"]
    return f"CREATE UNIQUE INDEX {index.name} ON {index.table.name} ({columns}) WHERE {where}"


async def _new_engine() -> AsyncEngine:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
        await conn.exec_driver_sql(f"DROP INDEX {_ASSIGNMENT_INDEX}")
        await conn.exec_driver_sql(_f4_index_ddl())
    return engine


@dataclass(frozen=True)
class _Observed:
    user_ids: dict[str, uuid.UUID]  # 用户键 → users.id
    is_eqcr: dict[str, bool]  # is_project_eqcr(用户, P)
    assignment_counts: dict[str, int]  # _count_project_eqcr_assignments(用户, P)：is_project_eqcr 的委派分支
    eqcr_user_ids: set[uuid.UUID]  # project_eqcr_user_ids(P)


async def _add_staff(
    db: AsyncSession, user_id: uuid.UUID | None, records: tuple[Staff, ...], pid: dict[str, uuid.UUID]
) -> None:
    for record in records:
        staff = StaffMember(user_id=user_id, name="测试人员", is_deleted=record.deleted, status=record.status)
        db.add(staff)
        await db.flush()
        for item in record.assignments:
            assert len(item.role) <= _ROLE_MAX_LEN, f"委派角色超出 VARCHAR(30)：{item.role!r}"
            db.add(ProjectAssignment(
                project_id=pid[item.project], staff_id=staff.id, role=item.role, is_deleted=item.deleted
            ))
        await db.flush()


async def _seed_and_observe(world: World) -> _Observed:
    engine = await _new_engine()
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            projects = {
                "P": Project(name="【测试】P", client_name="甲", is_deleted=world.p_deleted),
                "Q": Project(name="【测试】Q", client_name="乙", is_deleted=False),
            }
            db.add_all(list(projects.values()))
            await db.flush()
            pid = {key: project.id for key, project in projects.items()}
            users: dict[str, User] = {}
            for key, person in world.people():
                user = User(username=f"u-{key}", email=f"{key}@test.local", hashed_password="x", role=person.global_role)
                db.add(user)
                await db.flush()
                users[key] = user
                await _add_staff(db, user.id, person.staff, pid)
                if person.member_in_p is not None:
                    member = person.member_in_p
                    db.add(ProjectUser(project_id=pid["P"], user_id=user.id, role=member.role,
                                       permission_level=member.level, is_deleted=member.deleted))
            await _add_staff(db, None, world.unlinked, pid)
            await db.flush()
            p = pid["P"]
            return _Observed(
                user_ids={key: user.id for key, user in users.items()},
                is_eqcr={key: await is_project_eqcr(db, user, p) for key, user in users.items()},
                assignment_counts={
                    key: await _count_project_eqcr_assignments(db, user.id, p) for key, user in users.items()
                },
                eqcr_user_ids=await project_eqcr_user_ids(db, p),
            )
    finally:
        await engine.dispose()


def _observe(world: World) -> _Observed:
    """每个样例一个独立的 SQLite 内存库（同 test_deliverable_section_state_persist.py 的写法）。"""
    return asyncio.run(_seed_and_observe(world))


# ─── 显式样例 ────────────────────────────────────────────────────────────────

# 两条 hypothesis 测试共用的显式样例：补固定样例 ①~⑩ 没有覆盖的维度，结论按模型核对。
_EXAMPLE_INTERFERENCE = World(  # 干扰齐全；被测用户的别名只出现在大小写变体、他项目、已删除的人员库记录上 → 否
    tested=Person(
        UserRole.qc,
        (
            Staff((Assign("P", "EQCR"), Assign("Q", "eqcr"))),
            Staff((Assign("P", "独立复核合伙人"),), deleted=True, status="resigned"),
        ),
        Member(ProjectUserRole.eqcr, PermissionLevel.edit),
    ),
    others=(Person(UserRole.auditor, (Staff((Assign("P", "eqcr"),)),)),),
    unlinked=(Staff((Assign("P", "独立复核合伙人"),)),),
)
_EXAMPLE_F4_EDGE = World(  # 同一记录在 P、Q 各有一条已删除 + 一条现行委派（F4 允许）；现行的是变体 / 非别名；P 已软删 → 否
    tested=Person(
        UserRole.readonly,
        (
            Staff(
                (
                    Assign("P", "eqcr", deleted=True),
                    Assign("P", " eqcr"),
                    Assign("Q", "独立复核合伙人", deleted=True),
                    Assign("Q", "manager"),
                ),
                status="on_leave",
            ),
        ),
    ),
    p_deleted=True,
)
_EXAMPLE_ADMIN_SECOND_RECORD = World(  # admin 不豁免；第一条记录已删除，经第二条记录命中别名；含 30 字符任意串 → 是
    tested=Person(
        UserRole.admin,
        (
            Staff((Assign("P", "eqcr"),), deleted=True),
            Staff((Assign("P", "独立复核合伙人"), Assign("Q", "审计" * 15))),
        ),
        Member(ProjectUserRole.partner, PermissionLevel.review, deleted=True),
    ),
)


@dataclass(frozen=True)
class _Fixed:
    case_id: str
    world: World
    is_eqcr: bool  # 需求 7.5 写明的结论
    in_ids: bool  # 被测用户是否属于 project_eqcr_user_ids(P)：只看委派条件，不含全局角色分支（需求 11.1）


def _alone(role: UserRole, *staff: Staff, member: Member | None = None) -> World:
    return World(tested=Person(role, staff, member))


_FIXED = (
    # ① 全局 auditor，P 上委派「独立复核合伙人」→ 是
    _Fixed("ex1-auditor-cn-alias", _alone(UserRole.auditor, Staff((Assign("P", "独立复核合伙人"),))), True, True),
    # ② 全局 admin，P 上委派 eqcr → 是
    _Fixed("ex2-admin-eqcr", _alone(UserRole.admin, Staff((Assign("P", "eqcr"),))), True, True),
    # ③ 全局 eqcr，无任何委派 → 是；不属于 project_eqcr_user_ids（它不含全局角色分支）
    _Fixed("ex3-global-eqcr-no-assignment", _alone(UserRole.eqcr, Staff()), True, False),
    # ④ 全局 partner，P 上委派 manager → 否
    _Fixed("ex4-partner-manager", _alone(UserRole.partner, Staff((Assign("P", "manager"),))), False, False),
    # ⑤ 全局 auditor，P 上委派 EQCR → 否
    _Fixed("ex5-auditor-upper-case", _alone(UserRole.auditor, Staff((Assign("P", "EQCR"),))), False, False),
    # ⑥ 全局 auditor，P 上的 eqcr 委派已删除 → 否
    _Fixed(
        "ex6-assignment-deleted", _alone(UserRole.auditor, Staff((Assign("P", "eqcr", deleted=True),))), False, False
    ),
    # ⑦ 全局 auditor，P 上 eqcr 委派的人员库记录已删除 → 否
    _Fixed(
        "ex7-staff-record-deleted", _alone(UserRole.auditor, Staff((Assign("P", "eqcr"),), deleted=True)), False, False
    ),
    # ⑧ 全局 auditor，另一项目委派 eqcr、P 上委派 manager → 否
    _Fixed(
        "ex8-eqcr-on-other-project",
        _alone(UserRole.auditor, Staff((Assign("Q", "eqcr"), Assign("P", "manager")))),
        False,
        False,
    ),
    # ⑨ 全局 manager，经人员库记录甲在 P 上委派 manager、经人员库记录乙在 P 上委派 eqcr → 是
    _Fixed(
        "ex9-two-staff-records",
        _alone(UserRole.manager, Staff((Assign("P", "manager"),)), Staff((Assign("P", "eqcr"),))),
        True,
        True,
    ),
    # ⑩ 全局 auditor，P 上成员行项目角色为 eqcr、无委派 → 否
    _Fixed(
        "ex10-member-role-eqcr",
        _alone(UserRole.auditor, Staff(), member=Member(ProjectUserRole.eqcr, PermissionLevel.review)),
        False,
        False,
    ),
)


# ─── Property 9：is_project_eqcr 等于模型 ────────────────────────────────────


@settings(max_examples=5, deadline=None)
@given(world=_worlds)
@example(world=_EXAMPLE_INTERFERENCE)
@example(world=_EXAMPLE_F4_EDGE)
@example(world=_EXAMPLE_ADMIN_SECOND_RECORD)
def test_property_9_eqcr_resolver_matches_model(world: World) -> None:
    # Feature: partner-manager-edit-permission, Property 9: EQCR 判定等于模型
    expected = _model_is_eqcr(world.tested)
    actual = _observe(world).is_eqcr["tested"]
    assert actual is expected, f"is_project_eqcr(被测用户, P) 为 {actual}，模型为 {expected}"


@pytest.mark.parametrize(("world", "expected"), [pytest.param(c.world, c.is_eqcr, id=c.case_id) for c in _FIXED])
def test_property_9_fixed_examples(world: World, expected: bool) -> None:
    """Property 9 的固定样例：需求 7.5 的 ①~⑩，期望结论按需求原文写死；先核对模型，再断言被测函数。"""
    assert _model_is_eqcr(world.tested) is expected, "模型与需求 7.5 的固定样例不一致"
    actual = _observe(world).is_eqcr["tested"]
    assert actual is expected, f"is_project_eqcr(被测用户, P) 为 {actual}，需求 7.5 为 {expected}"


# ─── project_eqcr_user_ids：与 is_project_eqcr 同口径（需求 11.1） ────────────


def _assert_eqcr_user_ids(world: World, observed: _Observed) -> None:
    """project_eqcr_user_ids(P) 等于模型；数据里的每个用户逐个核对与 is_project_eqcr 同口径。"""
    expected_ids = {observed.user_ids[key] for key, person in world.people() if _model_assignment_branch(person)}
    assert observed.eqcr_user_ids == expected_ids, "project_eqcr_user_ids(P) 与模型不一致"
    for key, person in world.people():
        in_ids = observed.user_ids[key] in observed.eqcr_user_ids
        branch = observed.assignment_counts[key] > 0
        assert branch is in_ids, f"{key}：委派分支为 {branch}，属于 project_eqcr_user_ids(P) 为 {in_ids}"
        verdict = person.global_role.value == "eqcr" or in_ids
        actual = observed.is_eqcr[key]
        assert actual is verdict, f"{key}：is_project_eqcr 为 {actual}，「全局角色为 eqcr ∨ 属于该集合」为 {verdict}"


@settings(max_examples=5, deadline=None)
@given(world=_worlds)
@example(world=_EXAMPLE_INTERFERENCE)
@example(world=_EXAMPLE_F4_EDGE)
@example(world=_EXAMPLE_ADMIN_SECOND_RECORD)
def test_project_eqcr_user_ids_matches_model(world: World) -> None:
    """与 Property 9 同一生成器、同一组显式样例。"""
    _assert_eqcr_user_ids(world, _observe(world))


@pytest.mark.parametrize(("world", "in_ids"), [pytest.param(c.world, c.in_ids, id=c.case_id) for c in _FIXED])
def test_project_eqcr_user_ids_fixed_examples(world: World, in_ids: bool) -> None:
    """固定样例 ①~⑩ 上的 project_eqcr_user_ids：③（全局 eqcr、无委派）不在集合内。"""
    observed = _observe(world)
    actual = observed.user_ids["tested"] in observed.eqcr_user_ids
    assert actual is in_ids, f"被测用户属于 project_eqcr_user_ids(P) 为 {actual}，期望 {in_ids}"
    _assert_eqcr_user_ids(world, observed)


# ─── 测试库自检：委派唯一索引与 F4 等价 ──────────────────────────────────────


def test_sqlite_assignment_index_is_f4_equivalent() -> None:
    """建的是带删除条件的部分唯一索引：同一（项目，人员库记录）已删除的委派不占位，第二条现行委派被拒。"""

    async def _scenario() -> str:
        engine = await _new_engine()
        try:
            async with engine.connect() as conn:
                stored = (await conn.exec_driver_sql(
                    "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?", (_ASSIGNMENT_INDEX,)
                )).scalar_one()
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                project, staff = Project(name="【测试】P", client_name="甲"), StaffMember(name="测试人员")
                db.add_all([project, staff])
                await db.flush()
                for role, deleted in (("eqcr", True), ("manager", True), ("eqcr", False)):
                    db.add(ProjectAssignment(project_id=project.id, staff_id=staff.id, role=role, is_deleted=deleted))
                await db.flush()  # 两条已删除 + 一条现行：F4 允许
                db.add(ProjectAssignment(project_id=project.id, staff_id=staff.id, role="qc"))
                with pytest.raises(IntegrityError) as exc_info:
                    await db.flush()
                assert "UNIQUE constraint failed: project_assignments.project_id, project_assignments.staff_id" in str(
                    exc_info.value
                )
            return stored
        finally:
            await engine.dispose()

    assert asyncio.run(_scenario()) == _f4_index_ddl()
