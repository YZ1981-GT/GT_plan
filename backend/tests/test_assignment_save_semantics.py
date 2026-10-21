"""委派保存的失败语义与真 PG 用例（partner-manager-edit-permission 任务 4.3；需求 3.1、3.6、3.7、9.5，design D12）。

被测：生产注册的 ``POST /api/projects/{project_id}/assignments``（``routers/assignments.py``）→
``AssignmentService.save_assignments`` → ``_sync_project_users``，由 router 统一 ``commit``。经 httpx 真发请求；生产的
``get_db`` 照常执行，只把它所用的会话工厂 ``app.core.database.async_session`` 指向权限世界的库（只提供数据），
因此「会话关闭即回滚」的生产语义原样生效。测试应用另挂 ``app/main.py`` 的两个异常处理器，失败响应与生产同形。

一、需求 3.7 / 9.5：三种失败 → 失败响应；委派、全部成员行，以及该次保存写的通知、可见性 epoch 与失效发件箱逐值保持保存前的值。
  - 兼任校验拒绝：真实输入触发（同一人员在同批既是 ``eqcr`` 又是 ``manager``），不替换任何函数 → 409。
  - 写库报错：在数据库驱动层（``before_cursor_execute``）让一条写语句按 DBAPI 错误失败。两处：成员行写入中途（第 2 条）、
    成员行全部写完之后（可见性 epoch）→ 500。
  - 提交报错：数据库驱动层的提交（``dialect.do_commit``）失败，此前该次保存的全部写语句都已发出 → 500。
  另有一条不注入的对照：同一请求保存成功，成员行按角色映射改写（失败用例里的「逐值不变」因此不是空转）。
二、D12（需求 3.6、3.7 的缓存条款）：权限缓存已移除，判据为保存过程对 ``perm:*`` 零读、零写、零删。记录器装在 redis-py 的
  命令入口（客户端 ``execute_command`` 与管道 ``execute``，异步、同步各一）上：本进程任何 Redis 客户端（不论经哪个名字取到）的
  命令都经过它；发往本世界 fakeredis 以外客户端的命令先记录再拦下（不连真实 Redis）。正向对照：经生产代码取客户端的两个名字
  （``redis_client``、``get_redis()`` 所用的 ``_redis_client``）发出的 ``perm:*`` 读、写、删、扫描都被记到，替身以外的客户端也被
  记到并拦下；成功对照里还记到保存链路自身的 SSE 写流（``XADD sse:project:<项目>``）。
三、需求 3.1（``pg_only``，权限世界 PG 版）：用户在本项目只有已删除成员行时，保存委派新建一条现行成员行，已删除行保持删除状态
  与原值。PG 上 ``idx_project_users_project_user`` 是带删除条件的部分唯一索引（SQLite 的 ``create_all`` 建不出，会误拒新建）。

本文件任何用例都不得经 ``app.core.database`` 的正式引擎（连本地开发库）发语句：autouse 守卫在该引擎上记录并拦下。
期望值按需求原文与需求 2.5 期望表（``tests/role_map_expected.py``）写死，不读生产代码的 ``ROLE_MAP``。
"""
from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

import fakeredis
import pytest
import pytest_asyncio
import redis.asyncio.client as redis_async
import redis.client as redis_sync
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import event, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.schema import CreateIndex, CreateTable

import app.core.database as core_database
import app.core.redis as core_redis
from app.deps import get_current_user
from app.middleware.error_handler import generic_exception_handler, http_exception_handler
from app.models.base import PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Notification, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.wp_visibility_models import WpVisibilityInvalidationOutbox, WpVisibilityPolicyEpoch
from app.routers.assignments import router as assignments_router
from tests.authz_world import (
    OTHER_PROJECT_ID,
    TARGET_PROJECT_ID,
    WORLD_TABLE_NAMES,
    AuthzWorld,
    GateClient,
    build_app,
    pg_engine,
    pg_world,
    sqlite_world,
)
from tests.role_map_expected import EXPECTED_ROLE_MAP

# ─── 期望与常量 ──────────────────────────────────────────────────────────────

SAVE_URL = f"/api/projects/{TARGET_PROJECT_ID}/assignments"
SERVER_ERROR = (500, {"code": 500, "message": "服务器内部错误"})  # generic_exception_handler
SOD_CONFLICT = (409, {"code": 409, "message": {  # http_exception_handler 包 router 的 detail；文案见任务 2.9 基线实测
    "error_code": "SOD_EQCR_INDEPENDENCE_CONFLICT",
    "message": "同项目内该人员已是 manager 角色，不能再担任 EQCR（独立复核合伙人）",
}})
# 委派保存在世界六张表之外还写这三张；连同委派与成员行，就是一次成功保存写到的全部表
SAVE_TABLES = (Notification.__table__, WpVisibilityPolicyEpoch.__table__, WpVisibilityInvalidationOutbox.__table__)
OBSERVED_TABLES = (ProjectAssignment.__table__, ProjectUser.__table__, *SAVE_TABLES)
SAVE_WRITES = frozenset(table.name for table in OBSERVED_TABLES)
SCOPE = {"scope_cycles": "D,E", "scope_accounts": "1001,1002", "valid_from": date(2026, 1, 1), "valid_to": date(2026, 12, 31)}
EARLIER = datetime(2026, 9, 1, 9, 30, tzinfo=timezone.utc)

# 本次保存的批次：（人员，委派角色，循环范围）。u1 由 auditor 改派 eqcr（edit → review），u2 由 manager 改派质控，u3 新加入。
BATCH = (("u1", "eqcr", None), ("u2", "质控", ["D"]), ("u3", "partner", None))
SOD_BATCH = (("u1", "eqcr", None), ("u1", "manager", None), *BATCH[1:])  # u1 同批兼任 eqcr 与 manager
# 写库报错的注入点：（命中的写语句，第几条失败，失败语句所在表，失败前已发出的成员行写语句条数）
WRITE_FAULTS: dict[str, tuple[str, int, str, int]] = {
    # 成员行写入中途：第 2 条成员行写语句失败
    "member-row-midway": (r"\s*(?:INSERT\s+INTO|UPDATE)\s+project_users\b", 2, "project_users", 1),
    # 成员行全部写完之后：随后的可见性 epoch 写入失败
    "after-member-rows": (r"\s*INSERT\s+INTO\s+wp_visibility_policy_epoch\b", 1, "wp_visibility_policy_epoch", 3),
}
_DML = re.compile(r"\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+\"?(\w+)", re.IGNORECASE)


# ─── Redis 命令记录器（D12 判据） ────────────────────────────────────────────


@dataclass(frozen=True)
class RedisCommand:
    via: str  # 入口：async / async-pipeline / sync / sync-pipeline
    on_fake: bool  # 是否发往本世界的 fakeredis（按连接池判定）
    args: tuple[str, ...]  # 命令名与参数，逐个转成字符串

    @property
    def name(self) -> str:
        return self.args[0].upper()

    @property
    def touches_perm(self) -> bool:
        return any("perm:" in arg for arg in self.args)


class RedisRecorder:
    """装在 redis-py 命令入口上：本进程全部 Redis 命令（含读）都经过；发往替身以外客户端的命令记录后拦下。"""

    STRAY = "测试期间 Redis 命令发往了本世界 fakeredis 以外的客户端，已拦下（未连接真实 Redis）"

    def __init__(self, fake: Any) -> None:
        self.fake_pool = fake.connection_pool
        self.commands: list[RedisCommand] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> RedisRecorder:
        record = self.record
        async_execute, async_pipeline = redis_async.Redis.execute_command, redis_async.Pipeline.execute
        sync_execute, sync_pipeline = redis_sync.Redis.execute_command, redis_sync.Pipeline.execute

        async def execute_command(client: Any, *args: Any, **options: Any) -> Any:
            record("async", client, [args])
            return await async_execute(client, *args, **options)

        async def pipeline_execute(pipe: Any, raise_on_error: bool = True) -> Any:
            record("async-pipeline", pipe, [args for args, _options in pipe.command_stack])
            return await async_pipeline(pipe, raise_on_error)

        def sync_execute_command(client: Any, *args: Any, **options: Any) -> Any:
            record("sync", client, [args])
            return sync_execute(client, *args, **options)

        def sync_pipeline_execute(pipe: Any, raise_on_error: bool = True) -> Any:
            record("sync-pipeline", pipe, [args for args, _options in pipe.command_stack])
            return sync_pipeline(pipe, raise_on_error)

        monkeypatch.setattr(redis_async.Redis, "execute_command", execute_command)
        monkeypatch.setattr(redis_async.Pipeline, "execute", pipeline_execute)
        monkeypatch.setattr(redis_sync.Redis, "execute_command", sync_execute_command)
        monkeypatch.setattr(redis_sync.Pipeline, "execute", sync_pipeline_execute)
        return self

    def record(self, via: str, client: Any, batch: list[tuple[Any, ...]]) -> None:
        on_fake = getattr(client, "connection_pool", None) is self.fake_pool
        self.commands.extend(RedisCommand(via, on_fake, tuple(str(arg) for arg in args)) for args in batch)
        if not on_fake:
            raise RuntimeError(self.STRAY)

    def perm_commands(self) -> list[RedisCommand]:
        return [command for command in self.commands if command.touches_perm]

    def stray_commands(self) -> list[RedisCommand]:
        return [command for command in self.commands if not command.on_fake]


# ─── 数据库：补建三张表、会话工厂隔离、驱动层故障注入、快照 ──────────────────


def _create_save_tables(conn: Connection) -> None:
    """在权限世界的库里补建委派保存另写的三张表（外键只指向世界里已有的表）。"""
    present = set(WORLD_TABLE_NAMES)
    for table in SAVE_TABLES:
        referred = {fk.referred_table.name for fk in table.foreign_key_constraints}
        assert referred <= present, f"{table.name} 的外键指向世界之外的表：{sorted(referred - present)}"
        conn.execute(CreateTable(table))
        for index in sorted(table.indexes, key=lambda item: item.name):
            conn.execute(CreateIndex(index))
        present.add(table.name)


async def _add_save_tables(world: AuthzWorld) -> None:
    connection = await world.db.connection()
    await connection.run_sync(_create_save_tables)


class CountingSessionFactory:
    """生产 ``get_db`` 所用会话工厂的替身：会话开在权限世界的库上，并记开过几个会话。"""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory
        self.opened = 0

    def __call__(self) -> AsyncSession:
        self.opened += 1
        return self.factory()


def _isolate_sessions(world: AuthzWorld, monkeypatch: pytest.MonkeyPatch) -> CountingSessionFactory:
    """PG 版：请求会话以 SAVEPOINT 加入世界的外层事务（提交只释放保存点，关闭即回滚到保存点）。"""
    options = {"join_transaction_mode": "create_savepoint"} if world.dialect == "postgresql" else {}
    factory = CountingSessionFactory(
        async_sessionmaker(world.db.bind, class_=AsyncSession, expire_on_commit=False, **options))
    monkeypatch.setattr(core_database, "async_session", factory)
    return factory


class DbFaults:
    """权限世界引擎上的驱动层故障注入（被测函数的下一层）与写语句记录；只在 ``armed`` 期间生效。"""

    def __init__(self, world: AuthzWorld, monkeypatch: pytest.MonkeyPatch) -> None:
        self.sync_engine = world.db.bind.sync_engine
        self.dialect = self.sync_engine.dialect
        self.armed = False
        self.dml: list[str] = []  # armed 期间发出的写语句所在表（按先后，含被注入失败的那条）
        self.failed: list[str] = []  # 实际注入的故障
        self._pattern: re.Pattern[str] | None = None
        self._nth = 0
        self._hits = 0
        self._fail_commit = False
        self._do_commit = self.dialect.do_commit
        self._listener = self._before_execute
        event.listen(self.sync_engine, "before_cursor_execute", self._listener)
        monkeypatch.setattr(self.dialect, "do_commit", self._commit)

    def remove(self) -> None:
        event.remove(self.sync_engine, "before_cursor_execute", self._listener)

    def fail_statement(self, pattern: str, nth: int) -> None:
        self._pattern, self._nth = re.compile(pattern, re.IGNORECASE), nth

    def fail_next_commit(self) -> None:
        self._fail_commit = True

    def _before_execute(self, _conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        match = _DML.match(statement) if self.armed else None
        if match is None:
            return
        table = match.group(1).lower()
        self.dml.append(table)
        if self._pattern is not None and self._pattern.match(statement):
            self._hits += 1
            if self._hits == self._nth:
                self.failed.append(f"写语句：{table}")
                raise self.dialect.loaded_dbapi.OperationalError("注入：写库失败")

    def _commit(self, dbapi_connection: Any) -> None:
        if self.armed and self._fail_commit:
            self._fail_commit = False
            self.failed.append("提交")
            # 按生产库（PG）的语义注入：服务端拒绝 COMMIT 时整笔事务随之作废，驱动随后报错。只抛错不回滚是 SQLite 的
            # 提交失败语义（事务仍开着）：SQLAlchemy 在提交失败后归还连接时跳过回滚（transaction_was_reset），本世界
            # StaticPool 只有一条连接，未提交的写入会被下一个会话的 commit 带进库，测到的就不是被测代码了。
            self.dialect.do_rollback(dbapi_connection)
            raise self.dialect.loaded_dbapi.OperationalError("注入：提交失败")
        self._do_commit(dbapi_connection)


async def _snapshot(db: AsyncSession) -> dict[str, dict[str, dict[str, Any]]]:
    """观测表的全部行（含已删除）：表名 → {主键: 全部列}。按列读，不经 ORM 身份映射；读完即结束本会话的事务。"""
    snapshot: dict[str, dict[str, dict[str, Any]]] = {}
    for table in OBSERVED_TABLES:
        keys = [column.name for column in table.primary_key.columns]
        rows = (await db.execute(select(table))).mappings().all()
        snapshot[table.name] = {"|".join(str(row[key]) for key in keys): dict(row) for row in rows}
    await db.commit()
    return snapshot


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


# ─── 请求 ────────────────────────────────────────────────────────────────────


async def _settle() -> None:
    """等请求里 fire-and-forget 的后台任务（SSE 广播写流）结束，再读 Redis 记录。"""
    current = asyncio.current_task()
    pending = [task for task in asyncio.all_tasks() if task is not current and not task.done()]
    if pending:
        _done, still = await asyncio.wait(pending, timeout=5)
        assert not still, f"5 秒内未结束的后台任务：{sorted(task.get_name() for task in still)}"


async def _post_save(user: User, body: dict[str, Any]) -> Response:
    """按生产注册挂委派路由，以 ``user`` 身份真发一次保存请求。"""
    api = build_app(assignments_router)
    api.add_exception_handler(HTTPException, http_exception_handler)  # 与 app/main.py 相同的两个处理器
    api.add_exception_handler(Exception, generic_exception_handler)

    async def _current_user() -> User:
        return user

    api.dependency_overrides[get_current_user] = _current_user
    # 未处理异常照生产返回 500 响应，不抛进测试（默认 True 会把异常直接抛出、拿不到响应）
    transport = ASGITransport(app=api, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://authz-world") as http:
        response = await GateClient(http, api).post(SAVE_URL, json=body)
    await _settle()
    return response


# ─── 场景 ────────────────────────────────────────────────────────────────────


@dataclass
class Scene:
    lead: User  # 发起保存的项目经理（批次外）
    users: dict[str, uuid.UUID]
    staff: dict[str, uuid.UUID]
    rows: dict[str, uuid.UUID]  # 成员行 id

    def body(self, batch: tuple[tuple[str, str, list[str] | None], ...]) -> dict[str, Any]:
        return {"assignments": [{"staff_id": str(self.staff[key]), "role": role, "assigned_cycles": cycles}
                                for key, role, cycles in batch]}


async def _add(db: AsyncSession, row: Any) -> Any:
    db.add(row)
    await db.flush()
    return row


async def _arrange(world: AuthzWorld) -> Scene:
    """保存前：u1 / u2 / u4 有现行委派与成员行（u2 另有一条已删除的旧委派），u3 两者都没有；
    批次外另有发起人、已删除成员行（u5）、u1 在另一项目的成员行。"""
    db = world.db
    await world.other_project()
    lead = await world.user(UserRole.manager)
    users = {"u1": await world.user(), "u2": await world.user(), "u3": await world.user(),
             "u4": await world.user(UserRole.qc), "u5": await world.user()}
    staff = {key: (await _add(db, StaffMember(user_id=users[key].id, name=f"委派保存{key}"))).id
             for key in ("u1", "u2", "u3", "u4")}
    for key, role, cycles, deleted in (("u1", "auditor", ["D"], False), ("u2", "manager", None, False),
                                       ("u4", "qc", None, False), ("u2", "auditor", None, True)):
        await _add(db, ProjectAssignment(
            project_id=TARGET_PROJECT_ID, staff_id=staff[key], role=role, assigned_cycles=cycles,
            assigned_at=EARLIER, is_deleted=deleted, deleted_at=EARLIER if deleted else None,
        ))
    rows: dict[str, uuid.UUID] = {}
    for key, user, project_id, role, level, extra in (
        ("lead", lead, TARGET_PROJECT_ID, "manager", "edit", {}),
        ("u1", users["u1"], TARGET_PROJECT_ID, "auditor", "edit", SCOPE),
        ("u1_other", users["u1"], OTHER_PROJECT_ID, "auditor", "edit", {}),
        ("u2", users["u2"], TARGET_PROJECT_ID, "manager", "edit", {}),
        ("u4", users["u4"], TARGET_PROJECT_ID, "qc", "review", {}),
        ("u5", users["u5"], TARGET_PROJECT_ID, "partner", "review", {"is_deleted": True, "deleted_at": EARLIER}),
    ):
        rows[key] = (await _add(db, ProjectUser(
            project_id=project_id, user_id=user.id, role=ProjectUserRole(role),
            permission_level=PermissionLevel(level), **extra,
        ))).id
    return Scene(lead=lead, users={key: user.id for key, user in users.items()}, staff=staff, rows=rows)


@dataclass
class Saving:
    world: AuthzWorld
    scene: Scene
    before: dict[str, dict[str, dict[str, Any]]]
    sessions: CountingSessionFactory
    recorder: RedisRecorder
    faults: DbFaults

    async def save(self, batch: tuple[tuple[str, str, list[str] | None], ...]) -> Response:
        self.faults.armed = True
        try:
            return await _post_save(self.scene.lead, self.scene.body(batch))
        finally:
            self.faults.armed = False

    async def assert_unchanged(self) -> None:
        """需求 3.7：委派与全部成员行（及该次保存另写的三张表）逐值保持保存前的值；D12：零 ``perm:*`` 读写删。"""
        assert await _snapshot(self.world.db) == self.before
        assert self.sessions.opened == 1  # 生产 get_db 用的是隔离后的会话工厂
        assert self.recorder.perm_commands() == []
        assert self.recorder.stray_commands() == []


@pytest.fixture(autouse=True)
def _dev_database_untouched():
    """本文件任何用例都不得经 ``app.core.database`` 的正式引擎（连本地开发库）发语句：记录并拦下。"""
    hits: list[str] = []
    target = core_database.engine.sync_engine

    def _deny(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        hits.append(" ".join(statement.split()[:3]))
        raise RuntimeError("测试期间禁止经 app.core.database.engine 访问本地开发库")

    event.listen(target, "before_cursor_execute", _deny)
    yield
    event.remove(target, "before_cursor_execute", _deny)
    assert hits == [], f"经正式引擎（本地开发库）发出了语句：{hits}"


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch) as w:
        yield w


@pytest_asyncio.fixture
async def saving(world: AuthzWorld, monkeypatch: pytest.MonkeyPatch):
    """保存前的现场：补建三张表、造数并提交、取快照，再隔离会话工厂、装 Redis 记录器与驱动层故障注入。"""
    await _add_save_tables(world)
    scene = await _arrange(world)
    before = await _snapshot(world.db)
    sessions = _isolate_sessions(world, monkeypatch)
    recorder = RedisRecorder(world.redis).install(monkeypatch)
    faults = DbFaults(world, monkeypatch)
    try:
        yield Saving(world, scene, before, sessions, recorder, faults)
    finally:
        faults.remove()


# ─── 一、对照：不注入时保存成功 ──────────────────────────────────────────────


async def test_save_without_injection_succeeds(saving: Saving) -> None:
    """同一请求不注入：200；保存前的现行委派软删、现行委派恰为本批三条；u1、u2 的成员行就地按角色映射改写
    （范围与有效期不动），u3 新建一条，其余成员行逐值不变。D12：零 ``perm:*`` 读写删，且记到了保存链路自身的 SSE 写流。"""
    scene, before = saving.scene, saving.before
    response = await saving.save(BATCH)

    assert (response.status_code, response.json()) == (200, {"message": "已委派 3 名成员", "count": 3})
    assert saving.faults.failed == []
    assert set(saving.faults.dml) == SAVE_WRITES
    after = await _snapshot(saving.world.db)

    old = before["project_assignments"]
    assert {key: after["project_assignments"][key]["is_deleted"] for key in old} == dict.fromkeys(old, True)
    deleted_before = {key: row for key, row in old.items() if row["is_deleted"]}
    assert {key: after["project_assignments"][key] for key in deleted_before} == deleted_before
    live = sorted((row["staff_id"], row["role"]) for row in after["project_assignments"].values() if not row["is_deleted"])
    assert live == sorted((scene.staff[key], role) for key, role, _cycles in BATCH)

    members_before, members_after = before["project_users"], after["project_users"]
    rewritten = {str(scene.rows["u1"]): EXPECTED_ROLE_MAP["eqcr"], str(scene.rows["u2"]): EXPECTED_ROLE_MAP["质控"]}
    for key, (role, level) in rewritten.items():
        expected = {**members_before[key], "role": role, "permission_level": level}
        assert {**members_after[key], "updated_at": None} == {**expected, "updated_at": None}, key
    untouched = {key: row for key, row in members_before.items() if key not in rewritten}
    assert {key: members_after[key] for key in untouched} == untouched
    created = [row for key, row in members_after.items() if key not in members_before]
    assert [(row["project_id"], row["user_id"], _value(row["role"]), _value(row["permission_level"]), row["is_deleted"])
            for row in created] == [(TARGET_PROJECT_ID, scene.users["u3"], *EXPECTED_ROLE_MAP["partner"], False)]

    assert saving.sessions.opened == 1
    assert saving.recorder.perm_commands() == []
    assert saving.recorder.stray_commands() == []
    assert [command.args[:2] for command in saving.recorder.commands if command.name == "XADD"] == [
        ("XADD", f"sse:project:{TARGET_PROJECT_ID}")]


# ─── 一、三种失败：失败响应，保存前的值原样保留 ──────────────────────────────


async def test_sod_rejection_returns_409_and_keeps_everything(saving: Saving) -> None:
    """兼任校验拒绝（需求 3.7、9.5）：真实输入触发，409 沿用 ``error_code`` / ``message``；校验先于任何写入。"""
    response = await saving.save(SOD_BATCH)

    assert (response.status_code, response.json()) == SOD_CONFLICT
    assert saving.faults.dml == []
    await saving.assert_unchanged()


@pytest.mark.parametrize("point", list(WRITE_FAULTS))
async def test_write_error_returns_500_and_keeps_everything(saving: Saving, point: str) -> None:
    """写库报错（需求 3.7）：驱动层让一条写语句失败 → 500；此前已发出的委派与成员行写入随会话关闭回滚。"""
    pattern, nth, table, member_writes = WRITE_FAULTS[point]
    saving.faults.fail_statement(pattern, nth)
    response = await saving.save(BATCH)

    assert (response.status_code, response.json()) == SERVER_ERROR
    assert saving.faults.failed == [f"写语句：{table}"]
    assert saving.faults.dml[-1] == table
    assert saving.faults.dml[0] == "project_assignments"  # 软删旧委派是第一条写语句
    assert saving.faults.dml[:-1].count("project_users") == member_writes
    await saving.assert_unchanged()


async def test_commit_error_returns_500_and_keeps_everything(saving: Saving) -> None:
    """提交报错（需求 3.7）：驱动层提交失败 → 500；提交前该次保存写到的全部表都已发出写语句，随会话关闭回滚。"""
    saving.faults.fail_next_commit()
    response = await saving.save(BATCH)

    assert (response.status_code, response.json()) == SERVER_ERROR
    assert saving.faults.failed == ["提交"]
    assert set(saving.faults.dml) == SAVE_WRITES
    assert saving.faults.dml.count("project_users") == 3
    await saving.assert_unchanged()


# ─── 二、D12 判据的正向对照 ──────────────────────────────────────────────────


async def test_perm_recorder_positive_control(world: AuthzWorld, monkeypatch: pytest.MonkeyPatch) -> None:
    """零次不是空转：生产代码取 Redis 客户端的两个名字都指向本世界替身；经它们发出的 ``perm:*`` 写、读、删（管道）、
    扫描全部被记到；替身以外的客户端（异步、同步各一）发出的 ``perm:*`` 命令也被记到并拦下，不连真实 Redis。"""
    assert core_redis.redis_client is world.redis
    assert core_redis._redis_client is world.redis
    recorder = RedisRecorder(world.redis).install(monkeypatch)
    key = f"perm:{uuid.uuid4()}:{TARGET_PROJECT_ID}"

    client = await core_redis.get_redis()  # 委派保存链路的 SSE 写流经它取 _redis_client
    assert client is world.redis
    await core_redis.redis_client.set(key, "edit", ex=300)
    assert await client.get(key) == "edit"
    pipe = core_redis.redis_client.pipeline()
    pipe.ttl(key)
    pipe.delete(key)
    assert (await pipe.execute())[1] == 1
    await client.scan(match="perm:*")
    stray_async = redis_async.Redis(host="127.0.0.1", port=9)
    with pytest.raises(RuntimeError) as async_exc:
        await stray_async.get(key)
    assert str(async_exc.value) == RedisRecorder.STRAY
    await stray_async.aclose()
    stray_sync = fakeredis.FakeRedis(server=fakeredis.FakeServer())
    with pytest.raises(RuntimeError) as sync_exc:
        stray_sync.delete(key)
    assert str(sync_exc.value) == RedisRecorder.STRAY

    assert [(command.via, command.on_fake, command.name) for command in recorder.perm_commands()] == [
        ("async", True, "SET"), ("async", True, "GET"), ("async-pipeline", True, "TTL"),
        ("async-pipeline", True, "DEL"), ("async", True, "SCAN"), ("async", False, "GET"), ("sync", False, "DEL"),
    ]
    assert [command.name for command in recorder.commands if not command.touches_perm] == ["PING"]
    assert recorder.stray_commands() == [RedisCommand("async", False, ("GET", key)),
                                         RedisCommand("sync", False, ("DEL", key))]


# ─── 三、需求 3.1：真 PG，只有已删除成员行时新建 ─────────────────────────────


async def _pg_count(sql: str, **params: object) -> int:
    """另开一条连接只读计数（不在权限世界的事务里）。"""
    engine = pg_engine()
    try:
        async with engine.connect() as conn:
            return int((await conn.execute(text(sql), params)).scalar_one())
    finally:
        await engine.dispose()


@pytest.mark.pg_only
async def test_pg_only_deleted_member_rows_then_new_live_row(monkeypatch: pytest.MonkeyPatch) -> None:
    async with pg_world(monkeypatch) as world:
        schema = world.schema
        indexdef = (await world.db.execute(text(
            "SELECT indexdef FROM pg_indexes WHERE schemaname = :s AND indexname = 'idx_project_users_project_user'"
        ), {"s": schema})).scalar_one()
        assert indexdef.endswith("WHERE (is_deleted = false)"), indexdef  # 被验证的正是这个部分唯一索引
        await _add_save_tables(world)
        lead = await world.user(UserRole.manager)
        user = await world.user()
        staff = await _add(world.db, StaffMember(user_id=user.id, name="委派保存（只有已删除成员行）"))
        for role, level, extra in (("manager", "edit", SCOPE), ("qc", "review", {})):
            await _add(world.db, ProjectUser(
                project_id=TARGET_PROJECT_ID, user_id=user.id, role=ProjectUserRole(role),
                permission_level=PermissionLevel(level), is_deleted=True, deleted_at=EARLIER, **extra,
            ))
        uid, sid = user.id, staff.id
        before = await _snapshot(world.db)
        sessions = _isolate_sessions(world, monkeypatch)
        recorder = RedisRecorder(world.redis).install(monkeypatch)

        response = await _post_save(lead, {"assignments": [{"staff_id": str(sid), "role": "partner"}]})

        assert (response.status_code, response.json()) == (200, {"message": "已委派 1 名成员", "count": 1})
        after = await _snapshot(world.db)
        members_before, members_after = before["project_users"], after["project_users"]
        assert [row["is_deleted"] for row in members_before.values()] == [True, True]
        assert {key: members_after[key] for key in members_before} == members_before  # 已删除行：删除状态与各项原值
        created = [row for key, row in members_after.items() if key not in members_before]
        assert [(row["project_id"], row["user_id"], _value(row["role"]), _value(row["permission_level"]),
                 row["is_deleted"], row["deleted_at"], row["scope_cycles"], row["scope_accounts"],
                 row["valid_from"], row["valid_to"]) for row in created] == [
            (TARGET_PROJECT_ID, uid, *EXPECTED_ROLE_MAP["partner"], False, None, None, None, None, None)]
        assert sessions.opened == 1
        assert recorder.perm_commands() == []
        assert recorder.stray_commands() == []

    # 世界结束整体回滚：临时 schema 不复存在，本地开发库 public 下没有本用例的任何行
    assert await _pg_count("SELECT count(*) FROM pg_namespace WHERE nspname = :s", s=schema) == 0
    residue = {
        "project_users": await _pg_count("SELECT count(*) FROM public.project_users WHERE user_id = :u", u=uid),
        "staff_members": await _pg_count("SELECT count(*) FROM public.staff_members WHERE id = :s", s=sid),
        "project_assignments": await _pg_count(
            "SELECT count(*) FROM public.project_assignments WHERE staff_id = :s", s=sid),
        "notifications": await _pg_count("SELECT count(*) FROM public.notifications WHERE recipient_id = :u", u=uid),
        "projects": await _pg_count("SELECT count(*) FROM public.projects WHERE id = :p", p=TARGET_PROJECT_ID),
    }
    assert residue == dict.fromkeys(residue, 0)
