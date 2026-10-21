"""委派同步的性质测试（partner-manager-edit-permission 任务 4.2；需求 3.1~3.5、3.8、3.9；design Property 2、§4.3、§8.3）。

被测：``AssignmentService._sync_project_users``（design §4.3、D4）。每个样例在两个独立的 SQLite 内存库上各跑一次：
造数相同，批次内委派一次按原顺序、一次按打乱后的顺序落库并传入。不替换任何生产函数，不用 monkeypatch（被测函数
只用传入的会话，不碰 Redis）。

- Property 2（``test_property_2_sync_matches_model_and_is_order_independent``）：两次运行结果相同，且都等于模型——
  批次内每个已关联用户在 P 恰有一条未删除成员行，取值为模型给出的值（已有未删除行就地改写，循环范围、科目范围、
  有效期不变；没有则新建）；其余成员行（批次外用户、只经未关联或已删除人员库记录出现的用户、已删除的行、另一项目
  Q 的行）各项取值与删除状态逐值不变；返回的改动恰为新建与取值有变的那些用户。
- 需求 3.5 的三个固定样例（``test_property_2_fixed_examples``）：edit 改派为 EQCR、edit 改派为未登记角色、同一用户
  manager 与 eqcr 各一条。期望取值按需求原文写死；先核对模型，再跑 Property 2 的全部断言。

模型（不调用被测函数，不读生产代码的 ``ROLE_MAP`` / ``resolve_member_mapping``）：取值表用需求 2.5 期望表
``tests/role_map_expected.py``；任一委派角色属于 EQCR 别名集合 ⇒ (partner, review)（3.3）；否则取最高级别，项目角色
在该级别的候选中按 partner、manager、qc、auditor、readonly 的先后取第一个（3.8）；未登记角色取 (readonly, readonly)
（3.1）；人员库记录未关联登录用户或已删除的委派跳过（3.9、D4）；全局角色不参与（3.2）。

生成维度（需求 3.5、design §8.3）：0~6 条委派，每条一份独立的人员库记录（F4）；委派角色取期望表 13 个键、两个 EQCR
别名、键的大写与首尾空格变体、长度 0~30 的任意串；约三分之一的人员库记录未关联登录用户、约三分之一已删除；同一用户
可经多份人员库记录出现；1~4 名批次内候选用户，各自在 P 的未删除成员行取「无 / readonly / review / edit」（项目角色
任取）、另带 0~1 条已删除成员行、在 Q 有一条成员行；另置 1~2 名批次外成员；成员行带三种循环 / 科目范围与有效期；
全局角色任取；委派另带循环范围（不应流入成员行）；打乱后的顺序为批次下标的任意排列。

测试库：``idx_project_users_project_user`` 在模型里只声明了 ``postgresql_where``，SQLite 上建出的是不带条件的唯一索引，
会拒绝 PG 上合法的「同一（项目，用户）已删除 + 未删除成员行各一条」，也会误拒「只有已删除成员行时新建」（3.1）。
本文件建表后删掉它，按模型声明的列与条件另建部分唯一索引（与 PG 等价），由 ``test_sqlite_member_index_is_pg_equivalent``
钉住这一等价（写法同 ``test_eqcr_resolver_property.py`` 的 ``_f4_index_ddl``）。
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.base import Base, PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.services.assignment_service import AssignmentService
from tests.role_map_expected import EXPECTED_EQCR_ALIASES, EXPECTED_ROLE_MAP

Pair = tuple[str, str]  # （项目角色，项目级别）的字符串取值，与 project_users 的存储口径相同
Scope = tuple[str | None, str | None, date | None, date | None]  # 循环范围、科目范围、有效期起、止


# ─── 模型（需求 3.1~3.3、3.8、3.9 原文；不调用被测函数） ─────────────────────

_EQCR_PAIR: Pair = ("partner", "review")  # 需求 3.3
_UNREGISTERED: Pair = ("readonly", "readonly")  # 需求 3.1：未登记角色
_LEVEL_ORDER = ("readonly", "review", "edit")  # 需求 3.8：取最高级别
_ROLE_ORDER = ("partner", "manager", "qc", "auditor", "readonly")  # 需求 3.8：同一级别按此先后取项目角色


def _model_mapping(roles: list[str]) -> Pair:
    """同一用户在本项目的一组委派角色 → 一组成员行取值（与先后顺序无关）。"""
    if any(role in EXPECTED_EQCR_ALIASES for role in roles):
        return _EQCR_PAIR
    pairs = {EXPECTED_ROLE_MAP.get(role, _UNREGISTERED) for role in roles}
    best = max((level for _, level in pairs), key=_LEVEL_ORDER.index)
    return next(role for role in _ROLE_ORDER if (role, best) in pairs), best


# ─── 数据描述 ────────────────────────────────────────────────────────────────

_NO_SCOPE: Scope = (None, None, None, None)
_SCOPE_A: Scope = ("D,E", "1001,1002", date(2026, 1, 1), date(2026, 12, 31))
_SCOPE_B: Scope = ("F", None, date(2025, 7, 1), None)
_DELETED_AT = datetime(2026, 3, 1, 9, 30)  # 造数时已删除成员行的删除时间


@dataclass(frozen=True)
class Row:
    """一条成员行的取值。"""

    role: ProjectUserRole
    level: PermissionLevel
    scope: Scope = _NO_SCOPE


@dataclass(frozen=True)
class Person:
    """一个登录用户：全局角色与造数时的成员行（同一（项目，用户）至多一条未删除，与 PG 的部分唯一索引一致）。"""

    global_role: UserRole = UserRole.auditor
    live_p: Row | None = None  # 在 P 的未删除成员行
    deleted_p: tuple[Row, ...] = ()  # 在 P 的已删除成员行
    live_q: Row | None = None  # 在另一项目 Q 的未删除成员行


@dataclass(frozen=True)
class Assign:
    """一条委派及其人员库记录（每条委派一份独立的记录，F4）。owner 为 people 下标，None 表示未关联登录用户。"""

    owner: int | None
    role: str
    staff_deleted: bool = False  # 人员库记录已删除：视同未关联（D4）
    cycles: tuple[str, ...] | None = None  # 委派的循环范围：不应流入成员行


@dataclass(frozen=True)
class World:
    """一个样例：用户（标签 u0、u1…）、本次委派批次（目标项目 P）、打乱后的委派顺序。"""

    people: tuple[Person, ...]
    batch: tuple[Assign, ...] = ()
    shuffled: tuple[int, ...] | None = None  # 批次下标的一个排列；None 表示倒序
    name: str = field(default="generated", compare=False)


def _row(role: str, level: str, scope: Scope = _NO_SCOPE) -> Row:
    return Row(ProjectUserRole(role), PermissionLevel(level), scope)


def _seeded_rows(u: int, person: Person) -> Iterator[tuple[str, str, Row, bool]]:
    """造数时的成员行：（标签，项目，取值，已删除）。"""
    user = f"u{u}"
    if person.live_p is not None:
        yield f"P/{user}/live", "P", person.live_p, False
    for k, row in enumerate(person.deleted_p):
        yield f"P/{user}/deleted{k}", "P", row, True
    if person.live_q is not None:
        yield f"Q/{user}/live", "Q", person.live_q, False


def _view(project: str, user: str, pair: Pair, scope: Scope, deleted: bool) -> tuple:
    return (project, user, *pair, *scope, deleted, _DELETED_AT if deleted else None)


@dataclass(frozen=True)
class Observed:
    """一次同步之后的观测（或模型给出的期望）。"""

    seeded: dict[str, tuple]  # 造数时已有的成员行：标签 → （项目，用户，项目角色，级别，循环，科目，起，止，已删除，删除时间）
    created: list[tuple]  # 同步新建的成员行：（项目，用户，项目角色，级别，已删除），已排序
    changes: dict[str, tuple[Pair | None, Pair]]  # 返回的改动：用户 → （改写前，改写后），新建时改写前为 None


def _model_targets(world: World) -> dict[int, Pair]:
    """批次内已关联用户 → 模型取值；未关联登录用户或已删除的人员库记录上的委派跳过（需求 3.9、D4）。"""
    roles: dict[int, list[str]] = defaultdict(list)
    for item in world.batch:
        if item.owner is not None and not item.staff_deleted:
            roles[item.owner].append(item.role)
    return {u: _model_mapping(user_roles) for u, user_roles in roles.items()}


def _expected(world: World) -> Observed:
    """模型给出的同步结果：批次内用户按 3.1~3.3、3.8 写本项目的那一条，其余成员行逐值不变（3.4）。"""
    targets = _model_targets(world)
    seeded: dict[str, tuple] = {}
    created: list[tuple] = []
    changes: dict[str, tuple[Pair | None, Pair]] = {}
    for u, person in enumerate(world.people):
        user = f"u{u}"
        for label, project, row, deleted in _seeded_rows(u, person):
            seeded[label] = _view(project, user, (row.role.value, row.level.value), row.scope, deleted)
        target = targets.get(u)
        if target is None:  # 不在批次内（含只经未关联 / 已删除人员库记录出现的用户）：都不动
            continue
        if person.live_p is None:  # 3.1：新建；已删除的成员行不动
            created.append(("P", user, *target, False))
            changes[user] = (None, target)
            continue
        before = (person.live_p.role.value, person.live_p.level.value)  # 3.2：就地改写，范围与有效期不动
        seeded[f"P/{user}/live"] = _view("P", user, target, person.live_p.scope, False)
        if before != target:
            changes[user] = (before, target)
    return Observed(seeded, sorted(created), changes)


# ─── 测试库与观测 ────────────────────────────────────────────────────────────

_TABLES = [User.__table__, Project.__table__, StaffMember.__table__, ProjectAssignment.__table__, ProjectUser.__table__]
_MEMBER_INDEX = "idx_project_users_project_user"
_NS = uuid.UUID("5b1c2d7e-8a43-4f0e-9d61-2c7a4e9b3f15")  # 造数 id 的固定名字空间：两次运行的 id 逐个相同


def _id(label: str) -> uuid.UUID:
    return uuid.uuid5(_NS, label)


def _member_index_ddl() -> str:
    """按模型声明（列、唯一、postgresql_where）给 SQLite 写一条等价的部分唯一索引。"""
    (index,) = [i for i in ProjectUser.__table__.indexes if i.name == _MEMBER_INDEX]
    assert index.unique is True, f"{_MEMBER_INDEX} 不再是唯一索引"
    columns = ", ".join(column.name for column in index.columns)
    where = index.dialect_options["postgresql"]["where"]
    return f"CREATE UNIQUE INDEX {index.name} ON {index.table.name} ({columns}) WHERE {where}"


async def _new_engine() -> AsyncEngine:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
        await conn.exec_driver_sql(f"DROP INDEX {_MEMBER_INDEX}")
        await conn.exec_driver_sql(_member_index_ddl())
    return engine


async def _seed(db: AsyncSession, world: World) -> dict[uuid.UUID, str]:
    """建 P、Q 两个项目、全部用户与成员行、每条委派的人员库记录；返回 id → 标签（项目、用户、成员行）。"""
    names: dict[uuid.UUID, str] = {}
    for key in ("P", "Q"):
        db.add(Project(id=_id(key), name=f"【测试】委派同步性质 {key}", client_name="测试客户"))
        names[_id(key)] = key
    for u, person in enumerate(world.people):
        user = f"u{u}"
        db.add(User(id=_id(user), username=f"sync-prop-{u}", email=f"{user}@assignment-sync-property.test",
                    hashed_password="x", role=person.global_role, is_active=True))
        names[_id(user)] = user
        for label, project, row, deleted in _seeded_rows(u, person):
            db.add(ProjectUser(
                id=_id(label), project_id=_id(project), user_id=_id(user), role=row.role,
                permission_level=row.level, scope_cycles=row.scope[0], scope_accounts=row.scope[1],
                valid_from=row.scope[2], valid_to=row.scope[3], is_deleted=deleted,
                deleted_at=_DELETED_AT if deleted else None,
            ))
            names[_id(label)] = label
    for i, item in enumerate(world.batch):
        owner = None if item.owner is None else _id(f"u{item.owner}")
        db.add(StaffMember(id=_id(f"s{i}"), user_id=owner, name="测试人员", is_deleted=item.staff_deleted))
    await db.flush()
    return names


async def _snapshot(db: AsyncSession, names: dict[uuid.UUID, str]) -> tuple[dict[str, tuple], list[tuple]]:
    """全部成员行（含已删除）：造数时已有的按标签，同步新建的另列。"""
    rows = (await db.execute(select(
        ProjectUser.id, ProjectUser.project_id, ProjectUser.user_id, ProjectUser.role, ProjectUser.permission_level,
        ProjectUser.scope_cycles, ProjectUser.scope_accounts, ProjectUser.valid_from, ProjectUser.valid_to,
        ProjectUser.is_deleted, ProjectUser.deleted_at,
    ))).all()
    seeded: dict[str, tuple] = {}
    created: list[tuple] = []
    for r in rows:
        project, user = names[r.project_id], names[r.user_id]
        if r.id in names:
            seeded[names[r.id]] = (project, user, r.role.value, r.permission_level.value, r.scope_cycles,
                                   r.scope_accounts, r.valid_from, r.valid_to, r.is_deleted, r.deleted_at)
        else:
            created.append((project, user, r.role.value, r.permission_level.value, r.is_deleted))
    return seeded, sorted(created)


def _changes(changes: list, names: dict[uuid.UUID, str]) -> dict[str, tuple[Pair | None, Pair]]:
    """返回的 MemberChange 列表 → {用户: (改写前, 改写后)}，同一用户只许出现一次。"""
    out: dict[str, tuple[Pair | None, Pair]] = {}
    for change in changes:
        user = names[change.user_id]
        assert user not in out, f"同一用户出现两条改动：{user}"
        before = None if change.before is None else (change.before[0].value, change.before[1].value)
        out[user] = (before, (change.after[0].value, change.after[1].value))
    return out


async def _sync_once(world: World, order: tuple[int, ...]) -> Observed:
    """独立的 SQLite 内存库：造数 → 按 order 落库并传入本批委派 → 同步 → 观测。"""
    engine = await _new_engine()
    try:
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
            names = await _seed(db, world)
            batch: list[ProjectAssignment] = []
            for i in order:
                item = world.batch[i]
                cycles = None if item.cycles is None else list(item.cycles)
                batch.append(ProjectAssignment(project_id=_id("P"), staff_id=_id(f"s{i}"), role=item.role,
                                               assigned_cycles=cycles))
            db.add_all(batch)
            await db.flush()  # 同 save_assignments：先落库新委派，再同步成员行
            changes = await AssignmentService(db)._sync_project_users(_id("P"), batch)
            seeded, created = await _snapshot(db, names)
            return Observed(seeded, created, _changes(changes, names))
    finally:
        await engine.dispose()


def _check_property(world: World) -> None:
    """Property 2：原顺序与打乱后的顺序各同步一次，两次结果相同，且都等于模型。"""
    forward = tuple(range(len(world.batch)))
    shuffled = forward[::-1] if world.shuffled is None else world.shuffled
    assert sorted(shuffled) == list(forward), f"{world.name}：shuffled 不是批次下标的排列"
    first = asyncio.run(_sync_once(world, forward))
    second = asyncio.run(_sync_once(world, shuffled))
    assert second == first, f"{world.name}：打乱批次内委派顺序后结果不同（需求 3.5、3.8）"
    assert first == _expected(world), f"{world.name}：同步结果与模型不一致"


# ─── 生成器（需求 3.5、design §8.3） ────────────────────────────────────────

_ROLE_KEYS = tuple(sorted(EXPECTED_ROLE_MAP))
_EQCR_KEYS = tuple(sorted(EXPECTED_EQCR_ALIASES))
_role_strings = st.one_of(
    st.sampled_from(_ROLE_KEYS),
    st.sampled_from(_EQCR_KEYS),  # 单列 EQCR 别名，让「EQCR 优先」的样例常见一些
    st.sampled_from(_ROLE_KEYS).flatmap(lambda key: st.sampled_from((key.upper(), f" {key}", f"{key} "))),
    # PG 的 varchar 存不了 NUL；project_assignments.role 是 VARCHAR(30)
    st.text(st.characters(exclude_categories=("Cs",), exclude_characters="\x00"), max_size=30),
)
_rows = st.builds(
    Row, st.sampled_from(list(ProjectUserRole)), st.sampled_from(list(PermissionLevel)),
    st.sampled_from((_NO_SCOPE, _SCOPE_A, _SCOPE_B)),
)
_maybe_rows = st.sampled_from((False, True, True, True)).flatmap(lambda has: _rows if has else st.none())  # 约四分之一「无」
_deleted_rows = st.lists(_rows, max_size=1).map(tuple)
_global_roles = st.sampled_from(list(UserRole))
_cycles = st.sampled_from((None, ("D",), ("D", "E")))


@st.composite
def _worlds(draw: st.DrawFn) -> World:
    n_in = draw(st.integers(min_value=1, max_value=4))  # 批次内候选用户：u0 … u{n_in-1}
    people = [Person(draw(_global_roles), draw(_maybe_rows), draw(_deleted_rows), draw(_rows)) for _ in range(n_in)]
    n_out = draw(st.integers(min_value=1, max_value=2))  # 批次外成员（需求 3.5：1~2 名）
    people += [Person(draw(_global_roles), draw(_rows), draw(_deleted_rows), draw(_maybe_rows)) for _ in range(n_out)]
    batch: list[Assign] = []
    for _ in range(draw(st.integers(min_value=0, max_value=6))):
        linked = draw(st.sampled_from((True, True, False)))  # 约三分之一未关联登录用户
        owner = draw(st.integers(min_value=0, max_value=n_in - 1)) if linked else None
        staff_deleted = draw(st.sampled_from((False, False, True)))  # 约三分之一人员库记录已删除
        batch.append(Assign(owner, draw(_role_strings), staff_deleted, draw(_cycles)))
    return World(tuple(people), tuple(batch), tuple(draw(st.permutations(range(len(batch))))))


# ─── 显式样例（性质测试的 @example：补固定样例没有覆盖的维度，结论按模型核对） ──

_E1 = World(  # 已删除的成员行与被跳过的人员库记录；5 条委派
    people=(
        # u0：在 P 只有已删除成员行 → 新建 (qc, review)，已删除的行保持原值（3.1）
        Person(UserRole.admin, deleted_p=(_row("partner", "edit", _SCOPE_A),), live_q=_row("manager", "edit")),
        # u1：唯一一份人员库记录已删除（视同未关联，D4）→ 成员行不动
        Person(UserRole.auditor, live_p=_row("auditor", "edit", _SCOPE_A)),
        # u2：在 P 没有成员行；已删除的记录上是 eqcr、现行的记录上是 manager → 只按现行的取 (manager, edit)
        Person(UserRole.eqcr, live_q=_row("readonly", "readonly")),
        # u3：批次外，未删除与已删除成员行各一条
        Person(UserRole.manager, live_p=_row("manager", "edit", _SCOPE_B),
               deleted_p=(_row("auditor", "edit", _SCOPE_A),), live_q=_row("qc", "review")),
    ),
    batch=(
        Assign(0, "qc"),
        Assign(1, "eqcr", staff_deleted=True),
        Assign(None, "partner"),  # 未关联登录用户的人员（3.9）
        Assign(2, "eqcr", staff_deleted=True),
        Assign(2, "manager", cycles=("D", "E")),
    ),
    shuffled=(4, 2, 0, 3, 1),
    name="E1-deleted-rows-and-skipped-staff",
)
_E2 = World(  # 同一用户多条委派的合并、精确匹配、就地改写（可升可降）；5 条委派
    people=(
        # u0：assistant 与 合伙人 同为 edit → 按固定先后取 partner（3.8），(readonly, readonly) 就地升为 (partner, edit)
        Person(UserRole.auditor, live_p=_row("readonly", "readonly", _SCOPE_B), live_q=_row("auditor", "edit")),
        # u1：首部带空格的「 manager」是未登记角色 → (qc, review) 降为 (readonly, readonly)；全局 admin 同样改写（3.2）
        Person(UserRole.admin, live_p=_row("qc", "review"), live_q=_row("partner", "edit", _SCOPE_A)),
        # u2：审计员（edit）+ 质控（review）→ 取最高级别 (auditor, edit)；原为 (partner, review)
        Person(UserRole.partner, live_p=_row("partner", "review", _SCOPE_A), live_q=_row("qc", "review")),
        # u3：批次外
        Person(UserRole.auditor, live_p=_row("auditor", "edit"), live_q=_row("manager", "edit", _SCOPE_B)),
    ),
    batch=(
        Assign(0, "assistant"),
        Assign(1, " manager"),
        Assign(0, "合伙人", cycles=("D",)),
        Assign(2, "审计员"),
        Assign(2, "质控"),
    ),
    shuffled=(4, 2, 0, 3, 1),  # u0、u2 各自的两条委派先后都反过来
    name="E2-merge-tiebreak-exact-match",
)
_E3 = World(  # 空批次：任何成员行都不动，返回的改动为空
    people=(
        Person(UserRole.auditor, live_p=_row("manager", "edit", _SCOPE_A), live_q=_row("auditor", "edit")),
        Person(UserRole.qc, deleted_p=(_row("qc", "review"),)),
    ),
    name="E3-empty-batch",
)


# ─── 需求 3.5 的固定样例（被测用户都是 u0；u1 为批次外成员） ─────────────────

_FIXED: tuple[tuple[World, Pair], ...] = (
    (  # edit 改派为 EQCR：(manager, edit) → (partner, review)，就地改写，范围与有效期不变（3.2、3.3）
        World(
            people=(
                Person(UserRole.auditor, live_p=_row("manager", "edit", _SCOPE_A), live_q=_row("auditor", "edit", _SCOPE_B)),
                Person(UserRole.manager, live_p=_row("qc", "review"), live_q=_row("manager", "edit")),
            ),
            batch=(Assign(0, "独立复核合伙人", cycles=("D",)),),
            name="F1-edit-to-eqcr",
        ),
        ("partner", "review"),
    ),
    (  # edit 改派为未登记角色：(auditor, edit) → (readonly, readonly)（3.1、3.2）
        World(
            people=(
                Person(UserRole.partner, live_p=_row("auditor", "edit", _SCOPE_B), live_q=_row("qc", "review", _SCOPE_A)),
                Person(UserRole.auditor, live_p=_row("partner", "edit", _SCOPE_A), deleted_p=(_row("qc", "review"),)),
            ),
            batch=(Assign(0, "观察员"),),
            name="F2-edit-to-unregistered",
        ),
        ("readonly", "readonly"),
    ),
    (  # 同一用户经两份人员库记录 manager 与 eqcr 各一条：EQCR 优先 → 新建 (partner, review)；倒序再跑一次（3.3、3.8）
        World(
            people=(
                Person(UserRole.manager, live_q=_row("manager", "edit", _SCOPE_A)),
                Person(UserRole.qc, live_p=_row("auditor", "edit", _SCOPE_B)),
            ),
            batch=(Assign(0, "manager"), Assign(0, "eqcr")),
            name="F3-manager-and-eqcr-same-user",
        ),
        ("partner", "review"),
    ),
)


# ─── Property 2 ──────────────────────────────────────────────────────────────


@settings(max_examples=5, deadline=None)
@given(world=_worlds())
@example(world=_E1)
@example(world=_E2)
@example(world=_E3)
def test_property_2_sync_matches_model_and_is_order_independent(world: World) -> None:
    # Feature: partner-manager-edit-permission, Property 2: 委派同步按映射精确写入，且与委派顺序无关
    _check_property(world)


@pytest.mark.parametrize(("world", "expected"), [pytest.param(w, e, id=w.name) for w, e in _FIXED])
def test_property_2_fixed_examples(world: World, expected: Pair) -> None:
    """需求 3.5 的三个固定样例：u0 的期望取值按需求原文写死；先核对模型，再跑 Property 2 的全部断言。"""
    assert _model_targets(world)[0] == expected, f"{world.name}：模型与需求原文不一致"
    _check_property(world)


# ─── 测试库自检：成员行唯一索引与 PG 的部分唯一索引等价 ──────────────────────


def test_sqlite_member_index_is_pg_equivalent() -> None:
    """建的是带删除条件的部分唯一索引：已删除的成员行不占位，同一（项目，用户）第二条未删除成员行被拒。"""

    async def _scenario() -> str:
        engine = await _new_engine()
        try:
            async with engine.connect() as conn:
                stored = (await conn.exec_driver_sql(
                    "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?", (_MEMBER_INDEX,)
                )).scalar_one()
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                project = Project(name="【测试】P", client_name="甲")
                user = User(username="u", email="u@test.local", hashed_password="x", role=UserRole.auditor)
                db.add_all([project, user])
                await db.flush()
                for deleted in (True, True, False):
                    db.add(ProjectUser(project_id=project.id, user_id=user.id, role=ProjectUserRole.qc,
                                       permission_level=PermissionLevel.review, is_deleted=deleted))
                await db.flush()  # 两条已删除 + 一条未删除：PG 的部分唯一索引允许
                db.add(ProjectUser(project_id=project.id, user_id=user.id, role=ProjectUserRole.readonly,
                                   permission_level=PermissionLevel.readonly))
                with pytest.raises(IntegrityError) as exc_info:
                    await db.flush()
                assert "UNIQUE constraint failed: project_users.project_id, project_users.user_id" in str(
                    exc_info.value
                )
            return stored
        finally:
            await engine.dispose()

    assert asyncio.run(_scenario()) == _member_index_ddl()
