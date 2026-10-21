"""级别回填迁移真 PG 测试的数据世界与执行器驱动（partner-manager-edit-permission 任务 7.2 起；design §5.2、§8.3 性质 3~5）。

夹具模块，不是测试文件（文件名不匹配 ``test_*.py``，不被收集）。使用方：``test_level_backfill_migration_pg.py``。

一、迁移文件
- 按文件名后缀在 ``backend/migrations/`` 现找 ``V<n>__partner_manager_edit_level_backfill.sql`` 与
  ``R<n>__rollback_partner_manager_edit_level_backfill.sql``：必须各恰好一个、版本号相同（号段可能再顺延，测试不写死 n）。
- ``copy_backfill_migrations`` 把这两个文件逐字节复制进一个空的临时目录，作为执行器的 ``migrations_dir``：空 schema 里
  执行器只扫得到这两个文件，不会去跑其余版本。

二、隔离：一个世界一个提交型临时 schema
- 执行器的每次库访问都经 ``engine.begin()`` / ``connect()`` 取新连接，不接受外部连接或事务，所以不能用权限世界 PG 版
  ``pg_world`` 的「同一事务 + ``SET LOCAL search_path`` + 整体回滚」驱动它：未提交的 schema 对其他连接不可见，
  ``SET LOCAL`` 也只作用于那一条连接。这里改为：管理引擎先提交 ``CREATE SCHEMA authz_world_bf_<随机>``；世界引擎用
  ``NullPool`` 与 asyncpg 会话参数 ``server_settings={"search_path": <该 schema>}``，每条新连接的 search_path 都只含它
  （``current_schemas(false)`` 现查），不带 schema 的表名、类型名解析不到 public 的正式对象。
- 建表用权限世界同一份 ``create_world_schema``（枚举类型在临时 schema 内按 ORM 取值新建，六张表与部分唯一索引同 ORM
  声明）。另按开发库现状建 7 列的 ``schema_version``：执行器自己的 DDL 再加回滚追踪列 ``operator`` / ``rollback_note``——
  执行器 ``ensure_schema_version_table`` 的 DO 块查 ``information_schema.columns`` 时不限定 schema，会看到 public 上已有的
  这两列而跳过补列。
- 结束（含失败）``DROP SCHEMA … CASCADE``，现查该 schema 已不存在，引擎全部 dispose；不在 public 建任何对象，不写 public 的
  任何表（含 ``schema_version``）。
- 连接串只取进程环境变量 ``DATABASE_URL``（口径同 ``authz_world.pg_engine``：非 PostgreSQL 即报错；用例由 ``pg_only`` 先跳过）。

三、执行
- 正向：``MigrationRunner(engine=<世界引擎>, migrations_dir=<临时目录>).run_pending()``，与启动（``startup_registry`` 的迁移
  任务、``run_uvicorn`` 的预引导）同一入口：advisory lock → 建两张系统表 → 现扫待执行 → ``_apply_migration``（整文件一个
  事务）→ 失败记入 ``schema_migration_failures``。advisory lock 是全库共用的同一个键，只在单次执行的毫秒级窗口内持有。
- 本模块建出的执行器实例上 ``_run_backup`` 换成「一调用即失败」：它对 ``settings.DATABASE_URL``（本地开发库）跑 ``pg_dump``，
  只有 ``rollback_to`` 会调用它，正向用例都不应走到；回滚入口 ``BackfillWorld.rollback`` 另把它换成只记录调用的替身（见「五」）。

四、第二次执行（任务 7.3 起）
- 同一个世界里再调 ``run_pending()``，执行器按 ``schema_version`` 判定本版本已应用、不再执行 V 副本（``executed == []``）；也不能
  再调 ``_apply_migration``（它会再插一次同版本，撞 ``schema_version.version`` 的唯一约束）。``run_forward_twice`` 因此先
  ``forget_version`` 删掉临时 schema ``schema_version`` 中本版本那一行，再走同一个 ``run_pending()``：两次都经启动路径（建系统表
  时临时 ``schema_version`` 为空、迁移目录里没有 V001，执行器不补登记基线，与第一次相同）。
- 两次之间除这一行登记外不写任何表。需求 4.5 的用例另经 ``override_member_rows`` 只改指定成员行的（项目角色，级别）两列：原生
  UPDATE，不经 ORM（``updated_at`` 的 ``onupdate`` 会顺带改写它）。

五、回滚（任务 7.4 起）
- ``BackfillWorld.rollback`` 调执行器的运维回滚入口 ``rollback_to(n − 1)``（与 ``python -m app.core.migration_runner --rollback``
  同一方法，参数取默认：不带 ``confirm``、``operator``），只把实例上的 ``_run_backup`` 换成记录调用的替身（不跑 ``pg_dump``、
  不建 ``backend/backups/``），R 副本由 ``rollback_to`` 自己查找并执行。
- ``rollback_to`` 各分支在临时 schema 里的走向（现读）：``APP_ENV`` 非生产时不要求 ``confirm``；``ensure_schema_version_table``
  见表已有 7 列且非空，不补列、不补登记基线；当前版本取 ``MAX(version)``（字符串比较），只登记了 n，即 n；目标须小于它（按
  数值比较）；待回滚 = 已登记且大于目标的版本 = [n]，须都有 R 脚本（临时目录里有 R 副本）；随后调 ``_run_backup``；R 副本在
  一个事务里逐句 ``text()`` 执行；另一个事务删 ``schema_version`` 中 ``version > 目标`` 的行（字符串比较，n 与 n − 1 位数相同时
  成立），再按 ``version = 目标`` 写 ``operator`` / ``rollback_note``——临时 schema 里没有目标版本那一行，匹配 0 行、不报错。
- ``run_roundtrip``：正向执行一次或两次（第二次同 ``run_forward_twice``，两次之间不写任何表）→ 依次套用他途改动（每步经
  ``override_member_rows``）→ ``rollback`` → 快照。

六、执行语义（任务 7.5；需求 4.1、4.10）
- ``rollback_attempt``：同 ``BackfillWorld.rollback``（``rollback_to(n − 1)``，只替换 ``_run_backup``），但把抛出的异常收下作为
  观测值，由测试断言其类型与信息。正向从未执行、或已经回滚过一次时，临时 ``schema_version`` 为空，``rollback_to`` 在
  ``get_current_version()`` 之后即抛 ``RuntimeError``，走不到 R 脚本（现读）。
- ``execute_rollback_script``：这两种状态下按执行器同口径执行 R 副本——取执行器 ``scan_rollback_scripts()`` 扫到的本版本 R 脚本，
  交给 ``_execute_rollback_script``（``rollback_to`` 执行每个 R 脚本所用的同一函数：执行器分句，一个事务内逐句 ``text()``）。
  没有改用「先在临时 ``schema_version`` 登记本版本再 ``rollback_to``」：那样造出的是「本版本已应用、却没有回填记录表」，不是
  「正向从未执行」。
- ``execute_sql``：在临时 schema 里执行测试数据语句制造冲突（预建不兼容的同名表、给回填记录表建依赖视图），不改写迁移副本。
- 流程：``run_rollback_twice``、``run_rollback_only``、``run_forward_failure``、``run_rollback_failure``（都捕获异常作观测值，
  红落在测试的断言上）。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.migration_runner import _SCHEMA_VERSION_DDL, MigrationRunner, RunPendingResult
from app.models.base import PermissionLevel, ProjectStatus, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from tests.authz_world import WORLD_TABLES, create_world_schema

# ─── 常量 ────────────────────────────────────────────────────────────────────

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
FORWARD_SUFFIX = "__partner_manager_edit_level_backfill.sql"
ROLLBACK_SUFFIX = "__rollback_partner_manager_edit_level_backfill.sql"
BACKFILL_TABLE = "project_user_level_backfill"
SCHEMA_PREFIX = "authz_world_bf_"  # 与权限世界 PG 版的 authz_world_ 同前缀：运行后按同一前缀核对无残留
WORLD_TABLE_NAMES: tuple[str, ...] = tuple(table.name for table in WORLD_TABLES)
ROLE_MAX_LEN = 30  # project_assignments.role 是 VARCHAR(30)

# 执行器 DDL 之外，按开发库现状补的两列（public.schema_version 现查为 7 列）
_SCHEMA_VERSION_TRACKING_COLUMNS = (
    "ALTER TABLE schema_version ADD COLUMN operator VARCHAR(100)",
    "ALTER TABLE schema_version ADD COLUMN rollback_note TEXT",
)
_DELETED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
_ASSIGNED_AT = datetime(2025, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
_SCOPED = {"scope_cycles": "D,E", "scope_accounts": "1001,1122", "valid_from": date(2025, 1, 1), "valid_to": date(2025, 12, 31)}
_UNSCOPED = dict.fromkeys(_SCOPED)

Pair = tuple[str, str]  # （项目角色，项目级别），取枚举的字符串值（project_users 的存储口径）
Outcome = tuple[str, str, str]  # 被改动行的（目标项目角色，目标级别，rule）
RowKey = tuple[int, int]  # （用户下标，该用户的成员行下标）


# ─── 一个样例的数据描述 ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class Asg:
    """一条委派：项目键、委派角色（原样写入 ``project_assignments.role``）、是否已删除。"""

    project: str
    role: str
    deleted: bool = False


@dataclass(frozen=True)
class Staff:
    """一条人员库记录及经它持有的委派；``linked=False`` 时 ``user_id`` 为空（未关联登录用户）。"""

    assignments: tuple[Asg, ...] = ()
    deleted: bool = False
    linked: bool = True


@dataclass(frozen=True)
class Row:
    """一条成员行。``expect`` 只用于固定样例：按需求原文写死的（项目角色，级别，rule），``None`` 表示不改、不记。"""

    project: str
    role: str
    level: str
    deleted: bool = False
    scoped: bool = False  # 带循环 / 科目范围与有效期（迁移不应碰这些列）
    expect: Outcome | None = None

@dataclass(frozen=True)
class Person:
    """一个登录用户：全局角色、关联到他的人员库记录、他的成员行。"""

    global_role: str = "auditor"
    staff: tuple[Staff, ...] = ()
    rows: tuple[Row, ...] = ()


@dataclass(frozen=True)
class World:
    """一个样例的全部数据。``projects`` 为（项目键，是否已软删）。"""

    projects: tuple[tuple[str, bool], ...]
    people: tuple[Person, ...] = ()
    name: str = ""

    def row_keys(self) -> list[RowKey]:
        return [(pi, ri) for pi, person in enumerate(self.people) for ri in range(len(person.rows))]

    def check(self) -> None:
        """造数前核对真实约束：项目键已声明；同一（项目，用户）至多一条未删除成员行（``idx_project_users_project_user``）；
        同一（项目，人员库记录）至多一条现行委派（``idx_assignment_project_staff``）；委派角色不超过 VARCHAR(30)。"""
        keys = [key for key, _ in self.projects]
        if len(set(keys)) != len(keys):
            raise ValueError(f"{self.name}：项目键重复 {keys}")
        for pi, person in enumerate(self.people):
            live_rows = [row.project for row in person.rows if not row.deleted]
            if len(set(live_rows)) != len(live_rows):
                raise ValueError(f"{self.name}：用户{pi} 在同一项目有多条未删除成员行 {live_rows}")
            for si, staff in enumerate(person.staff):
                live = [item.project for item in staff.assignments if not item.deleted]
                if len(set(live)) != len(live):
                    raise ValueError(f"{self.name}：用户{pi} 的人员库记录{si} 在同一项目有多条现行委派 {live}")
                for item in staff.assignments:
                    if item.project not in keys or len(item.role) > ROLE_MAX_LEN:
                        raise ValueError(f"{self.name}：委派 {item} 的项目未声明或角色超长")
            for row in person.rows:
                if row.project not in keys:
                    raise ValueError(f"{self.name}：成员行 {row} 的项目未声明")


# ─── 迁移文件 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BackfillMigrations:
    """临时迁移目录里的两个副本，及其在 ``backend/migrations/`` 的原文件。"""

    version: str
    forward: Path
    rollback: Path
    source_forward: Path
    source_rollback: Path

    @property
    def directory(self) -> Path:
        return self.forward.parent

    def forward_checksum(self) -> str:
        """与执行器 ``scan_migrations`` 同口径：``read_text(utf-8)`` 后再按 utf-8 编码取 sha256。"""
        return hashlib.sha256(self.forward.read_text(encoding="utf-8").encode("utf-8")).hexdigest()

def locate_backfill_migrations(directory: Path = MIGRATIONS_DIR) -> tuple[str, Path, Path]:
    """按文件名后缀现找正向与回滚脚本：各恰好一个、版本号相同（文件名前缀大小写口径同执行器的 ``re.IGNORECASE``）。"""
    found: dict[str, list[tuple[str, Path]]] = {"V": [], "R": []}
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        for kind, suffix in (("V", FORWARD_SUFFIX), ("R", ROLLBACK_SUFFIX)):
            match = re.fullmatch(rf"{kind}(\d+){re.escape(suffix)}", path.name, flags=re.IGNORECASE)
            if match:
                found[kind].append((match.group(1), path))
    if len(found["V"]) != 1 or len(found["R"]) != 1:
        names = {kind: [path.name for _, path in items] for kind, items in found.items()}
        raise RuntimeError(f"{directory} 里应恰有一个 V*{FORWARD_SUFFIX} 与一个 R*{ROLLBACK_SUFFIX}，实际 {names}")
    (forward_version, forward), (rollback_version, rollback) = found["V"][0], found["R"][0]
    if forward_version != rollback_version:
        raise RuntimeError(f"正向与回滚脚本的版本号不同：{forward.name} / {rollback.name}")
    return forward_version, forward, rollback


def copy_backfill_migrations(destination: Path) -> BackfillMigrations:
    """把两个脚本逐字节复制进空目录 ``destination``，作为执行器的 ``migrations_dir``。"""
    version, forward, rollback = locate_backfill_migrations()
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise RuntimeError(f"临时迁移目录 {destination} 须为空")
    for source in (forward, rollback):
        data = source.read_bytes()
        (destination / source.name).write_bytes(data)
        if (destination / source.name).read_bytes() != data:
            raise RuntimeError(f"{source.name} 复制后与原文件不一致")
    return BackfillMigrations(version, destination / forward.name, destination / rollback.name, forward, rollback)


# ─── 引擎 ────────────────────────────────────────────────────────────────────


def database_url() -> str:
    """连接串只取进程环境变量 ``DATABASE_URL``（不读 .env、不回显）。"""
    url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in url:
        raise RuntimeError("级别回填测试只取进程环境变量 DATABASE_URL，且须指向 PostgreSQL（仅供 pg_only 用例）")
    return url


def make_engine(search_path: str | None = None) -> AsyncEngine:
    """``NullPool`` 引擎（每次访问一条新连接）；``search_path`` 给定时经 asyncpg 会话参数作用于每条连接。SSL 口径同
    ``app.core.database`` / ``authz_world.pg_engine``。"""
    from app.core.config import settings

    connect_args: dict[str, Any] = {"ssl": False} if settings.DB_DISABLE_SSL else {}
    if search_path is not None:
        connect_args["server_settings"] = {"search_path": search_path}
    return create_async_engine(database_url(), poolclass=NullPool, connect_args=connect_args)


def _no_backup(*_args: object, **_kwargs: object) -> Path:
    raise AssertionError("级别回填测试不应走到 _run_backup：它对 settings.DATABASE_URL（本地开发库）跑 pg_dump")

# ─── 造数 ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Seeded:
    """造数时生成的 id（字符串，与快照的口径相同）。"""

    project_ids: dict[str, str]
    user_ids: tuple[str, ...]
    row_ids: dict[RowKey, str]  # 成员行键 → project_users.id


def _deleted(flag: bool) -> dict[str, Any]:
    return {"is_deleted": flag, "deleted_at": _DELETED_AT if flag else None}


async def _seed(conn: AsyncConnection, world: World, tag: str) -> Seeded:
    """按外键先后写入：项目 → 用户 → 人员库记录 → 委派 → 成员行（Core insert，应用 ORM 的 Python 侧默认值）。"""
    project_ids = {key: uuid.uuid4() for key, _ in world.projects}
    user_ids = tuple(uuid.uuid4() for _ in world.people)
    projects = [
        {"id": project_ids[key], "name": f"【测试】级别回填世界 {key}", "client_name": "级别回填世界",
         "status": ProjectStatus.execution, **_deleted(deleted)}
        for key, deleted in world.projects
    ]
    users = [
        {"id": user_id, "username": f"bf-{tag}-{index}", "email": f"bf-{tag}-{index}@level-backfill.test",
         "hashed_password": "x", "role": UserRole(person.global_role), "is_active": True, "is_deleted": False}
        for index, (user_id, person) in enumerate(zip(user_ids, world.people, strict=True))
    ]
    staff_rows: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    members: list[dict[str, Any]] = []
    row_ids: dict[RowKey, str] = {}
    for pi, person in enumerate(world.people):
        for staff in person.staff:
            staff_id = uuid.uuid4()
            staff_rows.append({"id": staff_id, "user_id": user_ids[pi] if staff.linked else None,
                               "name": "级别回填世界人员", **_deleted(staff.deleted)})
            assignments.extend(
                {"id": uuid.uuid4(), "project_id": project_ids[item.project], "staff_id": staff_id,
                 "role": item.role, "assigned_at": _ASSIGNED_AT, **_deleted(item.deleted)}
                for item in staff.assignments
            )
        for ri, row in enumerate(person.rows):
            row_id = uuid.uuid4()
            row_ids[(pi, ri)] = str(row_id)
            members.append({"id": row_id, "project_id": project_ids[row.project], "user_id": user_ids[pi],
                            "role": ProjectUserRole(row.role), "permission_level": PermissionLevel(row.level),
                            **_deleted(row.deleted), **(_SCOPED if row.scoped else _UNSCOPED)})
    for table, rows in (
        (Project.__table__, projects), (User.__table__, users), (StaffMember.__table__, staff_rows),
        (ProjectAssignment.__table__, assignments), (ProjectUser.__table__, members),
    ):
        if rows:
            await conn.execute(insert(table), rows)
    return Seeded({key: str(value) for key, value in project_ids.items()}, tuple(map(str, user_ids)), row_ids)

# ─── 快照 ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Snapshot:
    """临时 schema 里的全表快照：六张表逐行全列、回填记录表（不存在为 ``None``）、两张执行器系统表。"""

    tables: dict[str, dict[str, dict[str, Any]]]  # 表名 → id → 列 → 值
    backfill: dict[str, dict[str, Any]] | None  # project_user_id → 列 → 值
    schema_version: tuple[dict[str, Any], ...]
    failures: tuple[dict[str, Any], ...] | None  # schema_migration_failures；表不存在为 None


def _norm(value: Any) -> Any:
    return str(value) if isinstance(value, uuid.UUID) else value


async def _fetch(conn: AsyncConnection, sql: str) -> list[dict[str, Any]]:
    result = await conn.exec_driver_sql(sql)
    return [{key: _norm(value) for key, value in row._mapping.items()} for row in result]


class BackfillWorld:
    """一个已造数的临时 schema：世界引擎（search_path 只含该 schema）、造数 id、快照与执行器入口。"""

    def __init__(self, schema: str, engine: AsyncEngine, seeded: Seeded) -> None:
        self.schema = schema
        self.engine = engine
        self.seeded = seeded

    async def search_path(self) -> tuple[str, ...]:
        async with self.engine.connect() as conn:
            return tuple((await conn.execute(text("SELECT current_schemas(false)"))).scalar_one())

    async def exists(self, table: str) -> bool:
        """``table`` 是否在本世界的临时 schema 里（按 schema 限定名查，不经 search_path）。"""
        async with self.engine.connect() as conn:
            found = await conn.execute(text("SELECT to_regclass(:name) IS NOT NULL"), {"name": f'"{self.schema}"."{table}"'})
            return bool(found.scalar_one())

    async def snapshot(self) -> Snapshot:
        has_backfill = await self.exists(BACKFILL_TABLE)
        has_failures = await self.exists("schema_migration_failures")
        async with self.engine.connect() as conn:
            tables: dict[str, dict[str, dict[str, Any]]] = {}
            for name in WORLD_TABLE_NAMES:
                tables[name] = {row["id"]: row for row in await _fetch(conn, f'SELECT * FROM "{name}" ORDER BY id')}
            backfill = None
            if has_backfill:
                rows = await _fetch(conn, f"SELECT * FROM {BACKFILL_TABLE} ORDER BY project_user_id")
                backfill = {row["project_user_id"]: row for row in rows}
            versions = await _fetch(
                conn, "SELECT version, filename, checksum, operator, rollback_note FROM schema_version ORDER BY id")
            failures = None
            if has_failures:
                failures = tuple(await _fetch(conn, "SELECT version, filename, error_type, error_message, attempt_count "
                                                    "FROM schema_migration_failures ORDER BY version"))
        return Snapshot(tables, backfill, tuple(versions), failures)

    def runner(self, migrations: BackfillMigrations) -> MigrationRunner:
        """执行器：与启动同一个类与入口，引擎为本世界引擎，迁移目录为只含两个副本的临时目录。"""
        runner = MigrationRunner(engine=self.engine, migrations_dir=migrations.directory)
        runner._run_backup = _no_backup  # type: ignore[method-assign]  # 见模块说明「三、执行」
        return runner

    async def run_pending(self, migrations: BackfillMigrations) -> RunPendingResult:
        return await self.runner(migrations).run_pending()

    async def forget_version(self, version: str) -> int:
        """删掉临时 schema ``schema_version`` 中该版本的登记，返回删除的行数（见模块说明「四」）。"""
        async with self.engine.begin() as conn:
            result = await conn.execute(text("DELETE FROM schema_version WHERE version = :version"), {"version": version})
            return int(result.rowcount)

    async def override_member_rows(self, pairs: dict[str, Pair]) -> tuple[str, ...]:
        """他途改动：按 id 只改成员行的（项目角色，级别）两列（见模块说明「四」）；返回没有恰好改到一行的 id。"""
        missed: list[str] = []
        async with self.engine.begin() as conn:
            for row_id, (role, level) in pairs.items():
                result = await conn.execute(
                    text("UPDATE project_users SET role = :role, permission_level = :level WHERE id = :id"),
                    {"role": role, "level": level, "id": uuid.UUID(row_id)})
                if result.rowcount != 1:
                    missed.append(row_id)
        return tuple(missed)

    async def rollback(self, migrations: BackfillMigrations) -> tuple[str, list[str], tuple[tuple[str, str], ...]]:
        """经 ``rollback_to(n − 1)`` 执行 R 副本（见模块说明「五」）；返回（目标版本，``rollback_to`` 的返回值，``_run_backup``
        替身记下的（当前版本，目标版本））。"""
        target = str(int(migrations.version) - 1)
        runner = self.runner(migrations)
        calls: list[tuple[str, str]] = []

        def record_backup(from_version: str, to_version: str) -> Path:
            calls.append((from_version, to_version))
            return Path("未备份-级别回填测试替身")  # 只进执行器日志，不建该文件

        runner._run_backup = record_backup  # type: ignore[method-assign]  # 只替换这一项
        rolled_back = await runner.rollback_to(target)
        return target, rolled_back, tuple(calls)

# ─── 建世界 / 删世界 ─────────────────────────────────────────────────────────


@asynccontextmanager
async def backfill_world(world: World) -> AsyncIterator[BackfillWorld]:
    """提交一个随机名临时 schema，建表、建 7 列 ``schema_version``、造数；退出（含失败）时删掉该 schema 并现查已不存在。"""
    world.check()
    tag = uuid.uuid4().hex[:12]
    schema = f"{SCHEMA_PREFIX}{tag}"
    admin = make_engine()
    scoped: AsyncEngine | None = None
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        scoped = make_engine(schema)
        async with scoped.begin() as conn:
            await conn.run_sync(create_world_schema)
            await conn.execute(text(_SCHEMA_VERSION_DDL))
            for ddl in _SCHEMA_VERSION_TRACKING_COLUMNS:
                await conn.exec_driver_sql(ddl)
            seeded = await _seed(conn, world, tag)
        yield BackfillWorld(schema, scoped, seeded)
    finally:
        try:
            if scoped is not None:
                await scoped.dispose()
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            async with admin.connect() as conn:
                left = (await conn.execute(
                    text("SELECT count(*) FROM pg_namespace WHERE nspname = :name"), {"name": schema})).scalar_one()
        finally:
            await admin.dispose()
        if left:
            raise RuntimeError(f"临时 schema {schema} 没有删掉")


# ─── 正向执行一次（性质 3） ─────────────────────────────────────────────────


@dataclass(frozen=True)
class ForwardRun:
    """一个世界正向执行一次的全部观测。"""

    schema: str
    search_path: tuple[str, ...]  # 世界连接的 current_schemas(false)
    seeded: Seeded
    before: Snapshot
    after: Snapshot
    result: RunPendingResult
    backfill_in_schema: bool  # 回填记录表建在了临时 schema 里


async def _run_first(bw: BackfillWorld, migrations: BackfillMigrations) -> ForwardRun:
    search_path = await bw.search_path()
    before = await bw.snapshot()
    result = await bw.run_pending(migrations)
    after = await bw.snapshot()
    in_schema = await bw.exists(BACKFILL_TABLE)
    return ForwardRun(bw.schema, search_path, bw.seeded, before, after, result, in_schema)


async def _forward_once(world: World, migrations: BackfillMigrations) -> ForwardRun:
    async with backfill_world(world) as bw:
        return await _run_first(bw, migrations)


def run_forward_once(world: World, migrations: BackfillMigrations) -> ForwardRun:
    """一个世界：建临时 schema → 造数 → 快照 → ``run_pending()`` 一次 → 快照 → 删 schema（每个样例各用一个新 schema）。"""
    return asyncio.run(_forward_once(world, migrations))


# ─── 正向执行两次（性质 4、需求 4.5） ───────────────────────────────────────


@dataclass(frozen=True)
class RepeatRun:
    """同一个世界正向执行两次的全部观测。"""

    first: ForwardRun  # 第一次（``first.after`` 即快照 A）
    missed: tuple[str, ...]  # 他途改动没有恰好改到一行的成员行 id（应为空）
    between: Snapshot  # 他途改动之后、第二次执行之前（没有他途改动时即快照 A 的状态）
    forgotten: int  # 第二次执行前从临时 schema_version 删掉的本版本登记行数（应为 1）
    second: RunPendingResult
    again: Snapshot  # 快照 B（第二次执行之后）


async def _forward_twice(world: World, migrations: BackfillMigrations, overrides: dict[RowKey, Pair]) -> RepeatRun:
    async with backfill_world(world) as bw:
        first = await _run_first(bw, migrations)
        missed: tuple[str, ...] = ()
        if overrides:
            missed = await bw.override_member_rows({bw.seeded.row_ids[key]: pair for key, pair in overrides.items()})
        between = await bw.snapshot()
        forgotten = await bw.forget_version(migrations.version)
        second = await bw.run_pending(migrations)
        return RepeatRun(first, missed, between, forgotten, second, await bw.snapshot())


def run_forward_twice(world: World, migrations: BackfillMigrations,
                      overrides: dict[RowKey, Pair] | None = None) -> RepeatRun:
    """一个世界：建临时 schema → 造数 → 正向执行一次（快照 A）→ 他途改动 ``overrides``（成员行键 → 改成的（项目角色，级别）；
    Property 4 本体不传）→ 删本版本登记 → 同一个 ``run_pending()`` 再执行一次（快照 B）→ 删 schema。"""
    return asyncio.run(_forward_twice(world, migrations, overrides or {}))


# ─── 正向执行一次或两次，他途改动，再回滚（性质 5） ─────────────────────────


@dataclass(frozen=True)
class RoundTrip:
    """同一个世界：正向执行一次或两次 → 他途改动 → ``rollback_to(n − 1)`` 的全部观测。"""

    first: ForwardRun  # 第一次正向执行（``first.before`` 即迁移前快照）
    repeat: RepeatRun | None  # 第二次正向执行（同 ``run_forward_twice``，两次之间没有他途改动）；只执行一次为 None
    missed: tuple[str, ...]  # 他途改动没有恰好改到一行的成员行 id（应为空）
    overridden: Snapshot  # 他途改动之后、回滚之前
    target: str  # rollback_to 的目标版本
    rolled_back: list[str]  # rollback_to 的返回值
    backups: tuple[tuple[str, str], ...]  # _run_backup 替身记下的调用
    after: Snapshot  # 回滚之后
    backfill_in_schema: bool  # 回滚之后回填记录表是否还在临时 schema 里

    @property
    def forward(self) -> Snapshot:
        """正向全部执行完、他途改动之前的快照。"""
        return self.repeat.again if self.repeat is not None else self.first.after


async def _roundtrip(world: World, migrations: BackfillMigrations, runs: int,
                     steps: tuple[dict[RowKey, Pair], ...]) -> RoundTrip:
    if runs not in (1, 2):
        raise ValueError(f"正向执行次数只能是 1 或 2，实际 {runs}")
    async with backfill_world(world) as bw:
        first = await _run_first(bw, migrations)
        repeat: RepeatRun | None = None
        if runs == 2:
            between = await bw.snapshot()
            forgotten = await bw.forget_version(migrations.version)
            second = await bw.run_pending(migrations)
            repeat = RepeatRun(first, (), between, forgotten, second, await bw.snapshot())
        missed: list[str] = []
        for step in steps:
            missed += await bw.override_member_rows({bw.seeded.row_ids[key]: pair for key, pair in step.items()})
        overridden = await bw.snapshot()
        target, rolled_back, backups = await bw.rollback(migrations)
        after = await bw.snapshot()
        return RoundTrip(first, repeat, tuple(missed), overridden, target, rolled_back, backups, after,
                         await bw.exists(BACKFILL_TABLE))


def run_roundtrip(world: World, migrations: BackfillMigrations, runs: int = 1,
                  steps: tuple[dict[RowKey, Pair], ...] = ()) -> RoundTrip:
    """一个世界：建临时 schema → 造数 → 正向执行 ``runs``（1 或 2）次 → 依次套用他途改动 ``steps``（每步：成员行键 → 改成的
    （项目角色，级别））→ ``rollback_to(n − 1)`` → 快照 → 删 schema（见模块说明「五」）。"""
    return asyncio.run(_roundtrip(world, migrations, runs, tuple(steps)))


# ─── 执行语义：重复回滚、正向从未执行、失败不登记（需求 4.1、4.10，任务 7.5） ──


@dataclass(frozen=True)
class RollbackAttempt:
    """一次 ``rollback_to(n − 1)`` 的观测：返回值与抛出的异常恰有其一；``backups`` 为 ``_run_backup`` 替身记下的调用。"""

    target: str
    rolled_back: list[str] | None
    error: Exception | None
    backups: tuple[tuple[str, str], ...]


async def execute_sql(bw: BackfillWorld, statements: tuple[str, ...]) -> None:
    """在本世界的临时 schema 里（一个事务）逐句执行测试数据语句，用来制造冲突状态；不经执行器（见模块说明「六」）。"""
    async with bw.engine.begin() as conn:
        for statement in statements:
            await conn.exec_driver_sql(statement)


async def rollback_attempt(bw: BackfillWorld, migrations: BackfillMigrations) -> RollbackAttempt:
    """同 ``BackfillWorld.rollback``，但把 ``rollback_to`` 抛出的异常收下作为观测值（见模块说明「六」）。"""
    target = str(int(migrations.version) - 1)
    runner = bw.runner(migrations)
    calls: list[tuple[str, str]] = []

    def record_backup(from_version: str, to_version: str) -> Path:
        calls.append((from_version, to_version))
        return Path("未备份-级别回填测试替身")  # 只进执行器日志，不建该文件

    runner._run_backup = record_backup  # type: ignore[method-assign]  # 只替换这一项
    try:
        rolled_back = await runner.rollback_to(target)
    except Exception as exc:
        return RollbackAttempt(target, None, exc, tuple(calls))
    return RollbackAttempt(target, rolled_back, None, tuple(calls))


async def execute_rollback_script(bw: BackfillWorld, migrations: BackfillMigrations) -> Exception | None:
    """按执行器同口径执行 R 副本：执行器 ``scan_rollback_scripts()`` 扫到的本版本 R 脚本交给 ``_execute_rollback_script``（不经
    ``rollback_to`` 的版本检查与 ``schema_version`` 更新）；返回抛出的异常，没有则为 None（见模块说明「六」）。"""
    runner = bw.runner(migrations)
    scripts = [mig for mig in runner.scan_rollback_scripts() if mig.version == migrations.version]
    if [mig.path for mig in scripts] != [migrations.rollback]:
        raise RuntimeError(f"执行器在临时迁移目录里应恰扫到 R 副本 {migrations.rollback.name}，实际 {scripts}")
    try:
        await runner._execute_rollback_script(scripts[0])
    except Exception as exc:
        return exc
    return None


@dataclass(frozen=True)
class RollbackTwice:
    """正向一次 → ``rollback_to(n − 1)`` → 再按执行器同口径执行一次 R 副本（需求 4.1）的全部观测。"""

    first: ForwardRun
    rollback: RollbackAttempt  # 第一次回滚（rollback_to）
    once: Snapshot  # 第一次回滚之后
    refused: RollbackAttempt  # 此时再调 rollback_to（本版本登记已删）
    mid: Snapshot  # 被拒绝之后
    second_error: Exception | None  # 第二次执行 R 副本抛出的异常
    twice: Snapshot  # 第二次执行 R 副本之后
    exists_once: bool  # 第一次回滚后回填记录表是否还在临时 schema 里
    exists_twice: bool


async def _rollback_twice(world: World, migrations: BackfillMigrations) -> RollbackTwice:
    async with backfill_world(world) as bw:
        first = await _run_first(bw, migrations)
        rollback = await rollback_attempt(bw, migrations)
        once, exists_once = await bw.snapshot(), await bw.exists(BACKFILL_TABLE)
        refused = await rollback_attempt(bw, migrations)
        mid = await bw.snapshot()
        second_error = await execute_rollback_script(bw, migrations)
        return RollbackTwice(first, rollback, once, refused, mid, second_error, await bw.snapshot(), exists_once,
                             await bw.exists(BACKFILL_TABLE))


def run_rollback_twice(world: World, migrations: BackfillMigrations) -> RollbackTwice:
    """一个世界：建临时 schema → 造数 → 正向一次 → ``rollback_to(n − 1)`` → 快照 → 再调 ``rollback_to``（应被拒绝）→ 快照 →
    按执行器同口径执行 R 副本 → 快照 → 删 schema。"""
    return asyncio.run(_rollback_twice(world, migrations))


@dataclass(frozen=True)
class RollbackOnly:
    """正向从未执行时回滚（需求 4.1）的全部观测。"""

    schema: str
    search_path: tuple[str, ...]
    before: Snapshot
    refused: RollbackAttempt  # rollback_to(n − 1)（临时 schema_version 为空）
    mid: Snapshot  # 被拒绝之后
    error: Exception | None  # 按执行器同口径执行 R 副本抛出的异常
    after: Snapshot
    exists_before: bool  # 回填记录表是否在临时 schema 里
    exists_after: bool


async def _rollback_only(world: World, migrations: BackfillMigrations) -> RollbackOnly:
    async with backfill_world(world) as bw:
        search_path = await bw.search_path()
        before, exists_before = await bw.snapshot(), await bw.exists(BACKFILL_TABLE)
        refused = await rollback_attempt(bw, migrations)
        mid = await bw.snapshot()
        error = await execute_rollback_script(bw, migrations)
        return RollbackOnly(bw.schema, search_path, before, refused, mid, error, await bw.snapshot(), exists_before,
                            await bw.exists(BACKFILL_TABLE))


def run_rollback_only(world: World, migrations: BackfillMigrations) -> RollbackOnly:
    """一个世界：建临时 schema → 造数（不正向执行）→ 快照 → ``rollback_to``（应被拒绝）→ 快照 → 按执行器同口径执行 R 副本 →
    快照 → 删 schema。"""
    return asyncio.run(_rollback_only(world, migrations))


@dataclass(frozen=True)
class FailedForward:
    """制造冲突后经 ``run_pending()`` 正向执行两次（需求 4.10；第二次即下一次启动的重试）的全部观测。"""

    schema: str
    search_path: tuple[str, ...]
    before: Snapshot  # 造数并制造冲突之后、正向之前
    first: RunPendingResult
    after: Snapshot
    second: RunPendingResult
    again: Snapshot


async def _forward_failure(world: World, migrations: BackfillMigrations, setup: tuple[str, ...]) -> FailedForward:
    async with backfill_world(world) as bw:
        await execute_sql(bw, setup)
        search_path, before = await bw.search_path(), await bw.snapshot()
        first = await bw.run_pending(migrations)
        after = await bw.snapshot()
        second = await bw.run_pending(migrations)
        return FailedForward(bw.schema, search_path, before, first, after, second, await bw.snapshot())


def run_forward_failure(world: World, migrations: BackfillMigrations, setup: tuple[str, ...]) -> FailedForward:
    """一个世界：建临时 schema → 造数 → 执行测试数据语句 ``setup`` → 快照 → ``run_pending()`` → 快照 → 再 ``run_pending()`` →
    快照 → 删 schema。"""
    return asyncio.run(_forward_failure(world, migrations, tuple(setup)))


@dataclass(frozen=True)
class FailedRollback:
    """正向成功后制造冲突、再 ``rollback_to(n − 1)``（需求 4.10）的全部观测。"""

    first: ForwardRun
    before: Snapshot  # 制造冲突之后、回滚之前
    attempt: RollbackAttempt
    after: Snapshot
    exists_after: bool  # 回滚失败后回填记录表是否还在临时 schema 里
    probe_after: bool  # 测试数据建的对象是否还在


async def _rollback_failure(world: World, migrations: BackfillMigrations, setup: tuple[str, ...],
                            probe: str) -> FailedRollback:
    async with backfill_world(world) as bw:
        first = await _run_first(bw, migrations)
        await execute_sql(bw, setup)
        before = await bw.snapshot()
        attempt = await rollback_attempt(bw, migrations)
        after = await bw.snapshot()
        return FailedRollback(first, before, attempt, after, await bw.exists(BACKFILL_TABLE), await bw.exists(probe))


def run_rollback_failure(world: World, migrations: BackfillMigrations, setup: tuple[str, ...],
                         probe: str) -> FailedRollback:
    """一个世界：建临时 schema → 造数 → 正向一次 → 执行测试数据语句 ``setup`` → 快照 → ``rollback_to(n − 1)`` → 快照 → 查
    回填记录表与 ``probe`` 是否还在 → 删 schema。"""
    return asyncio.run(_rollback_failure(world, migrations, tuple(setup), probe))
