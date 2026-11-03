"""公式中枢 spec 的真 PG 测试基座（spec formula-hub-integrity-closure，ADR-FHIC-25 第 3 点）。

夹具与收集钩子在同目录 ``conftest.py`` 登记，实现都在本模块（测试里要直接用的也从这里导入）。

- 开关：``GT_REQUIRE_PG=1`` 表示本轮必须真连 PostgreSQL —— 连不上即失败，不出现跳过。
- 目标库：环境变量 ``DATABASE_URL``（与根 conftest 判定 pg_only 是否跳过的来源相同）；
  被测代码读的 ``settings.DATABASE_URL`` 必须与它一致，否则夹具与被测代码会连到两个库。
- ``pg_tx_session``：独立连接 + 外层事务 + ``create_savepoint`` 会话（会话里的 commit 只释放保存点），
  退出时外层事务一律回滚。
- ``committed_project_scope``：只连库名以 ``fh_snap_`` 开头的快照库，或 ``GT_PG_DISPOSABLE_DB`` 精确点名的
  一次性库（CI service 容器）；提交型夹具绝不连共享库（点名也不放行）；
  真提交建【测试】项目，``add`` / ``track`` 登记的行与项目在退出时按主键删除并断言删净。
"""
from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

REQUIRE_PG_ENV = "GT_REQUIRE_PG"
SNAPSHOT_PREFIX = "fh_snap_"
#: CI 的一次性库（service 容器里新建、只跑过迁移）用它声明精确库名，提交型夹具与含 DDL 的用例才放行；
#: 「依赖真实数据」的快照库用例仍只认 ``fh_snap_`` 前缀（CI 库没有那份数据，照旧跳过）。
DISPOSABLE_DB_ENV = "GT_PG_DISPOSABLE_DB"
SHARED_DB_NAME = "audit_platform"
TEST_PROJECT_PREFIX = "【测试】"
#: 只供 committed_project 守卫的报错文案引用（测试按它断言守卫确实先于任何连接触发）
SNAPSHOT_GUARD_TEXT = "提交型夹具只连快照库"
REQUIRE_PG_USAGE_TEXT = "GT_REQUIRE_PG=1 但 DATABASE_URL 不是 PostgreSQL"


def pg_required() -> bool:
    return os.environ.get(REQUIRE_PG_ENV) == "1"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "")


def is_postgres_url(url: str) -> bool:
    try:
        return make_url(url).get_backend_name() == "postgresql"
    except Exception:  # noqa: BLE001 —— 解析不了的 URL 一律不是 PostgreSQL
        return False


def database_name(url: str) -> str:
    try:
        return make_url(url).database or ""
    except Exception:  # noqa: BLE001
        return ""


def redact(url: str) -> str:
    if not url:
        return "未设置"
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:  # noqa: BLE001
        return "<无法解析>"


def require_pg_usage_error() -> str | None:
    """``GT_REQUIRE_PG=1`` 而 ``DATABASE_URL`` 不是 PostgreSQL（或被测代码配置连到别处）时返回报错文案。"""
    if not pg_required():
        return None
    url = database_url()
    if not is_postgres_url(url):
        return (f"{REQUIRE_PG_USAGE_TEXT}（{redact(url)}）：真 PG 用例不得以跳过收场，"
                "按 ADR-FHIC-25 第 2 点设子进程环境（DATABASE_URL=快照库、GT_REQUIRE_PG=1、REDIS_URL=15 号库）")
    from app.core.config import settings

    if settings.DATABASE_URL != url:
        return (f"GT_REQUIRE_PG=1 但被测代码的 settings.DATABASE_URL（{redact(settings.DATABASE_URL)}）"
                f"与 DATABASE_URL（{redact(url)}）不一致：夹具与被测代码会连到不同的库")
    return None


def _unavailable(reason: str) -> None:
    """PG 不可用：本轮要求真 PG ⇒ 失败；否则跳过（与根 conftest 对 pg_only 的跳过口径一致）。"""
    if pg_required():
        pytest.fail(reason, pytrace=False)
    pytest.skip(reason)


def _async_pg_url() -> str:
    url = database_url()
    if not is_postgres_url(url):
        _unavailable(f"需要 PostgreSQL：DATABASE_URL={redact(url)}")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg":
        parsed = parsed.set(drivername="postgresql+asyncpg")
    return parsed.render_as_string(hide_password=False)


def make_engine() -> AsyncEngine:
    """夹具自用引擎：NullPool（连接不跨用例 / 事件循环复用），SSL 设置与应用一致。"""
    from app.core.config import settings

    connect_args = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    return create_async_engine(_async_pg_url(), poolclass=NullPool, connect_args=connect_args)


async def _connect(engine: AsyncEngine) -> AsyncConnection:
    try:
        return await engine.connect()
    except Exception as exc:  # noqa: BLE001 —— 连不上的原因原样带进报错
        _unavailable(f"连不上 PostgreSQL（{redact(database_url())}）：{type(exc).__name__}: {exc}")
        raise  # 不可达：_unavailable 总会抛出


@asynccontextmanager
async def pg_tx_session() -> AsyncIterator[AsyncSession]:
    """独立连接 + 外层事务 + ``create_savepoint`` 会话；退出时外层事务一律回滚。"""
    engine = make_engine()
    try:
        conn = await _connect(engine)
        trans = await conn.begin()
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            if trans.is_active:
                await trans.rollback()
            await conn.close()
    finally:
        await engine.dispose()


def _quote(conn: AsyncConnection, name: str) -> str:
    return conn.dialect.identifier_preparer.quote(name)


def _pk_clause(conn: AsyncConnection, pk: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    params = {f"p{i}": value for i, value in enumerate(pk.values())}
    clause = " AND ".join(f"{_quote(conn, col)} = :p{i}" for i, col in enumerate(pk))
    return clause, params


@dataclass
class CommittedProject:
    """已真提交的【测试】项目（只存在于快照库）。"""

    project_id: uuid.UUID
    name: str
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    tracked: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def session(self) -> AsyncSession:
        """独立会话（各自的连接与事务、真提交），供多会话并发用例使用。"""
        return self.sessionmaker()

    def track(self, table: str, **pk: Any) -> None:
        """登记一行（表名 + 主键列值）；退出时按登记的逆序删除，最后删项目。"""
        if not pk:
            raise ValueError("track 需要主键列值")
        self.tracked.append((table, dict(pk)))

    async def add(self, *objs: Any) -> None:
        """在一个独立会话里插入 ORM 对象并提交，按映射的主键自动登记。"""
        async with self.sessionmaker() as session:
            session.add_all(objs)
            await session.commit()
        for obj in objs:
            state = sa_inspect(obj)
            if state.identity is None:
                raise RuntimeError(f"{obj!r} 提交后没有主键，无法登记删除")
            mapper = state.mapper
            self.track(mapper.local_table.name, **{c.name: v for c, v in zip(mapper.primary_key, state.identity)})

    def _targets(self) -> list[tuple[str, dict[str, Any]]]:
        return [*reversed(self.tracked), ("projects", {"id": self.project_id})]

    async def remaining(self) -> dict[str, int]:
        """登记的行与项目在库里还剩几行（另开连接读，看到的是已提交状态）。"""
        left: dict[str, int] = {}
        async with self.engine.connect() as conn:
            for table, pk in self._targets():
                clause, params = _pk_clause(conn, pk)
                count = (await conn.execute(
                    text(f"SELECT count(*) FROM {_quote(conn, table)} WHERE {clause}"), params)).scalar_one()
                if count:
                    left[f"{table} {pk}"] = count
        return left

    async def cleanup(self) -> dict[str, Any]:
        """一个事务里按主键删除（登记的逆序、最后项目），返回删除失败原因与仍存在的行。"""
        problems: dict[str, Any] = {}
        try:
            async with self.engine.begin() as conn:
                for table, pk in self._targets():
                    clause, params = _pk_clause(conn, pk)
                    await conn.execute(text(f"DELETE FROM {_quote(conn, table)} WHERE {clause}"), params)
        except Exception as exc:  # noqa: BLE001 —— 删除失败要连同残留一起报出来
            problems["删除失败"] = f"{type(exc).__name__}: {exc}"
        problems.update(await self.remaining())
        return problems


def is_disposable_database(name: str) -> bool:
    """可真提交 / 可执行 DDL 的库：快照库（``fh_snap_`` 开头），或 ``GT_PG_DISPOSABLE_DB`` 精确点名的一次性库。

    共享库名永不放行（即使被点名）；没设环境变量时只认快照库前缀，本地默认口径不变。
    """
    if not name or name == SHARED_DB_NAME:
        return False
    if name.startswith(SNAPSHOT_PREFIX):
        return True
    declared = os.environ.get(DISPOSABLE_DB_ENV, "").strip()
    return bool(declared) and name == declared


def assert_snapshot_database() -> str:
    """提交型夹具的守卫：不是快照库或点名的一次性库即失败（先于任何连接）。"""
    name = database_name(database_url())
    if not is_disposable_database(name):
        pytest.fail(
            f"{SNAPSHOT_GUARD_TEXT}（库名以 {SNAPSHOT_PREFIX} 开头，或由 {DISPOSABLE_DB_ENV} 点名的一次性库），"
            f"当前库名 {name or '未知'}：绝不向共享库真提交",
            pytrace=False,
        )
    return name


@asynccontextmanager
async def committed_project_scope(label: str = "committed") -> AsyncIterator[CommittedProject]:
    """真提交建【测试】项目；退出时删除登记的行与项目，并断言按主键再查为 0 行。"""
    assert_snapshot_database()
    from app.models.core import Project

    engine = make_engine()
    try:
        await (await _connect(engine)).close()
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        name = f"{TEST_PROJECT_PREFIX}fh_{label}_{uuid.uuid4().hex[:10]}"
        project = Project(name=name, client_name=f"{TEST_PROJECT_PREFIX}公式中枢测试基座")
        async with maker() as session:
            session.add(project)
            await session.commit()
        handle = CommittedProject(project_id=project.id, name=name, engine=engine, sessionmaker=maker)
        try:
            yield handle
        except BaseException as exc:
            problems = await handle.cleanup()
            if problems:
                exc.add_note(f"committed_project 未删净：{problems}")
            raise
        problems = await handle.cleanup()
        if problems:
            pytest.fail(f"committed_project 未删净：{problems}", pytrace=False)
    finally:
        await engine.dispose()
