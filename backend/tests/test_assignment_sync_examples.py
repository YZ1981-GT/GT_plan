"""委派同步按角色映射精确写入：示例测试（partner-manager-edit-permission 任务 4.1）。

被测：``AssignmentService._sync_project_users``（design §4.3、D4）与经它的 ``save_assignments``。都在真实的
SQLite 内存库上调用，不替换任何生产函数。Redis 两个客户端名换成本文件独占的 fakeredis，只为不写共享的开发
Redis（``save_assignments`` 末尾的 SSE 广播会异步写一条流），不观测它。

期望值按需求原文逐个写死（取值同需求 2.5 期望表 ``tests/role_map_expected.py``），不读生产代码的 ``ROLE_MAP``。

不在本文件：Property 2 及其固定样例（任务 4.2）；失败语义、``perm:*`` 零读写删与真 PG 用例（任务 4.3）。
SQLite 上 ``idx_project_users_project_user`` 不带删除条件（PG 上是部分唯一索引），「批次内用户只有已删除成员行
时新建」只能在真 PG 上验（需求 3.1），本文件不构造该情形。
"""
from __future__ import annotations

import logging
import uuid
from datetime import date

import fakeredis.aioredis
import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core import redis as core_redis
from app.models.base import Base, PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Notification, Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.wp_visibility_models import WpVisibilityInvalidationOutbox, WpVisibilityPolicyEpoch
from app.services.assignment_service import AssignmentService, MemberChange

_TABLES = [model.__table__ for model in (
    User, Project, StaffMember, ProjectAssignment, ProjectUser,
    Notification, WpVisibilityPolicyEpoch, WpVisibilityInvalidationOutbox,  # save_assignments 的通知与 epoch 写入
)]
_SCOPE = {"scope_cycles": "D,E", "scope_accounts": "1001,1002",
          "valid_from": date(2026, 1, 1), "valid_to": date(2026, 12, 31)}

Pair = tuple[str, str]  # （项目角色，项目级别）的字符串取值


@pytest_asyncio.fixture
async def db(monkeypatch: pytest.MonkeyPatch):
    fake = fakeredis.aioredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)
    monkeypatch.setattr(core_redis, "redis_client", fake)
    monkeypatch.setattr(core_redis, "_redis_client", fake)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
            yield session
    finally:
        await engine.dispose()
        await fake.aclose()


# ─── 造数与观测 ──────────────────────────────────────────────────────────────


async def _add(db: AsyncSession, row):
    db.add(row)
    await db.flush()
    return row


async def _project(db: AsyncSession) -> uuid.UUID:
    return (await _add(db, Project(name="【测试】委派同步项目", client_name="测试客户"))).id


async def _user(db: AsyncSession, global_role: UserRole = UserRole.auditor) -> uuid.UUID:
    tag = uuid.uuid4().hex[:12]
    return (await _add(db, User(
        username=f"sync-{tag}", email=f"{tag}@assignment-sync.test", hashed_password="x",
        role=global_role, is_active=True,
    ))).id


async def _staff(db: AsyncSession, user_id: uuid.UUID | None, *, deleted: bool = False) -> uuid.UUID:
    return (await _add(db, StaffMember(user_id=user_id, name="测试人员", is_deleted=deleted))).id


async def _member(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID, role: str, level: str,
                  *, deleted: bool = False, **scope) -> uuid.UUID:
    return (await _add(db, ProjectUser(
        project_id=project_id, user_id=user_id, role=ProjectUserRole(role),
        permission_level=PermissionLevel(level), is_deleted=deleted, **scope,
    ))).id


async def _assign(db: AsyncSession, project_id: uuid.UUID, staff_id: uuid.UUID, role: str) -> ProjectAssignment:
    return await _add(db, ProjectAssignment(project_id=project_id, staff_id=staff_id, role=role))


async def _live(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> list[Pair]:
    """该用户在该项目的全部未删除成员行的（项目角色，级别）。"""
    rows = (await db.execute(select(ProjectUser.role, ProjectUser.permission_level).where(
        ProjectUser.project_id == project_id, ProjectUser.user_id == user_id,
        ProjectUser.is_deleted == False,  # noqa: E712
    ))).all()
    return [(r.role.value, r.permission_level.value) for r in rows]


async def _member_rows(db: AsyncSession) -> dict[uuid.UUID, tuple]:
    """全部成员行（含已删除）按行 id：（项目，用户，项目角色，级别，循环范围，科目范围，起，止，已删除）。"""
    rows = (await db.execute(select(
        ProjectUser.id, ProjectUser.project_id, ProjectUser.user_id, ProjectUser.role,
        ProjectUser.permission_level, ProjectUser.scope_cycles, ProjectUser.scope_accounts,
        ProjectUser.valid_from, ProjectUser.valid_to, ProjectUser.is_deleted,
    ))).all()
    return {r.id: (r.project_id, r.user_id, r.role.value, r.permission_level.value, r.scope_cycles,
                   r.scope_accounts, r.valid_from, r.valid_to, r.is_deleted) for r in rows}


def _changes(changes: list[MemberChange]) -> dict[uuid.UUID, tuple[Pair | None, Pair]]:
    """返回的改动列表 → {用户: (改写前, 改写后)}，同一用户只许出现一次。"""
    out: dict[uuid.UUID, tuple[Pair | None, Pair]] = {}
    for change in changes:
        assert change.user_id not in out, f"同一用户出现两条改动：{change.user_id}"
        before = None if change.before is None else (change.before[0].value, change.before[1].value)
        out[change.user_id] = (before, (change.after[0].value, change.after[1].value))
    return out


# ─── 示例 ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_new_member_rows_take_role_map_values(db):
    """需求 3.1：没有未删除成员行的用户新建一条，取值为角色映射对委派角色给出的值；未登记角色取 (readonly, readonly)。"""
    pid = await _project(db)
    expected: dict[str, Pair] = {"partner": ("partner", "edit"), "观察员": ("readonly", "readonly"),
                                 "助理": ("auditor", "edit")}
    users: dict[str, uuid.UUID] = {}
    batch = []
    for role in expected:
        users[role] = await _user(db)
        batch.append(await _assign(db, pid, await _staff(db, users[role]), role))

    changes = await AssignmentService(db)._sync_project_users(pid, batch)

    for role, pair in expected.items():
        assert await _live(db, pid, users[role]) == [pair], role
    assert _changes(changes) == {users[role]: (None, pair) for role, pair in expected.items()}


@pytest.mark.asyncio
async def test_existing_rows_rewritten_in_place_up_and_down(db):
    """需求 3.2：已有未删除成员行时就地改写项目角色与级别，可升可降，全局角色（含 admin）不影响；
    循环范围、科目范围、有效期保持原值；取值本就相同的行不改、不计入改动。"""
    pid = await _project(db)
    plan: list[tuple[UserRole, Pair, str, Pair]] = [  # （全局角色，改写前，本次委派角色，期望）
        (UserRole.auditor, ("auditor", "edit"), "质控", ("qc", "review")),  # edit → review
        (UserRole.admin, ("readonly", "readonly"), "项目经理", ("manager", "edit")),  # readonly → edit
        (UserRole.manager, ("qc", "review"), "观察员", ("readonly", "readonly")),  # review → readonly
        (UserRole.auditor, ("manager", "edit"), "manager", ("manager", "edit")),  # 取值相同
    ]
    seeded, batch = [], []
    for global_role, before, role, after in plan:
        uid = await _user(db, global_role)
        row_id = await _member(db, pid, uid, *before, **_SCOPE)
        batch.append(await _assign(db, pid, await _staff(db, uid), role))
        seeded.append((uid, row_id, before, after))
    before_rows = await _member_rows(db)

    changes = await AssignmentService(db)._sync_project_users(pid, batch)

    after_rows = await _member_rows(db)
    assert set(after_rows) == set(before_rows), "应就地改写：不新建、不删除成员行"
    for uid, row_id, _before, after in seeded:
        assert after_rows[row_id] == (pid, uid, *after, *_SCOPE.values(), False)
    assert _changes(changes) == {uid: (before, after) for uid, _, before, after in seeded if before != after}


@pytest.mark.asyncio
async def test_eqcr_alias_writes_partner_review(db):
    """需求 3.3：委派角色属于 EQCR 别名集合时写 (partner, review)：成员行尚不存在（中文别名）、原为 readonly（英文别名）。"""
    pid = await _project(db)
    fresh, was_readonly = await _user(db), await _user(db, UserRole.eqcr)
    await _member(db, pid, was_readonly, "readonly", "readonly")
    batch = [await _assign(db, pid, await _staff(db, fresh), "独立复核合伙人"),
             await _assign(db, pid, await _staff(db, was_readonly), "eqcr")]

    changes = await AssignmentService(db)._sync_project_users(pid, batch)

    assert await _live(db, pid, fresh) == [("partner", "review")]
    assert await _live(db, pid, was_readonly) == [("partner", "review")]
    assert _changes(changes) == {fresh: (None, ("partner", "review")),
                                 was_readonly: (("readonly", "readonly"), ("partner", "review"))}


@pytest.mark.asyncio
async def test_same_user_via_two_staff_records_gets_one_merged_row(db):
    """需求 3.8：两份人员库记录关联同一用户时只写一组取值，与委派先后无关：取最高级别，
    同一级别按 partner、manager、qc、auditor、readonly 的先后取项目角色。正序、倒序各在一个项目上跑一次。"""
    forward_pid, reverse_pid = await _project(db), await _project(db)
    plan: list[tuple[tuple[str, str], Pair]] = [
        (("审计员", "质控"), ("auditor", "edit")),  # edit 高于 review
        (("assistant", "合伙人"), ("partner", "edit")),  # 同为 edit：partner 先于 auditor
        (("观察员", "qc"), ("qc", "review")),  # review 高于未登记的 readonly
    ]
    users, forward, reverse = [], [], []
    for roles, _pair in plan:
        uid = await _user(db)
        staff = [await _staff(db, uid) for _ in roles]
        users.append(uid)
        forward += [await _assign(db, forward_pid, sid, role) for sid, role in zip(staff, roles)]
        reverse += [await _assign(db, reverse_pid, sid, role) for sid, role in zip(staff, roles)]
    reverse.reverse()

    svc = AssignmentService(db)
    changes = {pid: _changes(await svc._sync_project_users(pid, batch))
               for pid, batch in ((forward_pid, forward), (reverse_pid, reverse))}

    expected_rows = {uid: [pair] for uid, (_roles, pair) in zip(users, plan)}
    for pid in (forward_pid, reverse_pid):
        assert {uid: await _live(db, pid, uid) for uid in users} == expected_rows, pid
    expected_changes = {uid: (None, pair) for uid, (_roles, pair) in zip(users, plan)}
    assert changes == {forward_pid: expected_changes, reverse_pid: expected_changes}


@pytest.mark.asyncio
async def test_rows_outside_the_batch_are_untouched(db):
    """需求 3.4：批次外用户（含本次被移出团队的）在本项目的成员行、批次内用户在其他项目的成员行、已删除的成员行，
    各项取值与删除状态保持原值；只为批次内用户写本项目的那一条。"""
    pid, other_pid = await _project(db), await _project(db)
    in_batch, removed, deleted = await _user(db), await _user(db), await _user(db)
    await _member(db, other_pid, in_batch, "auditor", "edit", **_SCOPE)  # 批次内用户在其他项目
    await _member(db, pid, removed, "manager", "edit")  # 批次外：本次被移出团队
    await _member(db, pid, deleted, "partner", "review", deleted=True)  # 批次外：已删除的成员行
    before_rows = await _member_rows(db)
    batch = [await _assign(db, pid, await _staff(db, in_batch), "qc")]

    changes = await AssignmentService(db)._sync_project_users(pid, batch)

    after_rows = await _member_rows(db)
    assert {row_id: after_rows[row_id] for row_id in before_rows} == before_rows
    assert [after_rows[row_id][:4] for row_id in set(after_rows) - set(before_rows)] == [
        (pid, in_batch, "qc", "review")]
    assert _changes(changes) == {in_batch: (None, ("qc", "review"))}


@pytest.mark.asyncio
async def test_save_assignments_skips_unlinked_and_deleted_staff_and_only_flushes(db, caplog):
    """需求 3.9 与 D4：人员库记录未关联登录用户、或已删除（视同未关联）的人员跳过，不新建也不改写成员行，
    委派照常保存；``save_assignments`` 返回值不变、只 flush 不 commit，成员行改动记一条 info 日志。"""
    pid = await _project(db)
    unlinked = await _staff(db, None)
    holder = await _user(db)
    await _member(db, pid, holder, "qc", "review")  # 若经已删除的记录同步，会被改写为 (partner, edit)
    deleted_staff = await _staff(db, holder, deleted=True)
    linked_user = await _user(db)
    linked = await _staff(db, linked_user)
    commits: list[object] = []
    event.listen(db.sync_session, "after_commit", commits.append)
    batch = [{"staff_id": unlinked, "role": "manager"}, {"staff_id": deleted_staff, "role": "partner"},
             {"staff_id": linked, "role": "qc", "assigned_cycles": ["D"]}]

    with caplog.at_level(logging.INFO, logger="app.services.assignment_service"):
        created = await AssignmentService(db).save_assignments(pid, batch)

    expected_saved = [(unlinked, "manager"), (deleted_staff, "partner"), (linked, "qc")]
    assert [(pa.staff_id, pa.role) for pa in created] == expected_saved
    saved = (await db.execute(select(ProjectAssignment.staff_id, ProjectAssignment.role).where(
        ProjectAssignment.project_id == pid, ProjectAssignment.is_deleted == False,  # noqa: E712
    ))).all()
    assert sorted(map(tuple, saved), key=str) == sorted(expected_saved, key=str)
    members = (await db.execute(select(ProjectUser.user_id, ProjectUser.role, ProjectUser.permission_level).where(
        ProjectUser.project_id == pid))).all()
    assert sorted((m.user_id, m.role.value, m.permission_level.value) for m in members) == sorted(
        [(holder, "qc", "review"), (linked_user, "qc", "review")])
    assert commits == []
    assert db.in_transaction()
    logged = [r.getMessage() for r in caplog.records if r.name == "app.services.assignment_service"]
    assert logged == [f"save_assignments: project={pid}, member rows changed (1): {linked_user}: 新建 → qc/review"]
