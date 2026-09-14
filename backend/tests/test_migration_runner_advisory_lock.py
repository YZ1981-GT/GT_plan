"""MigrationRunner advisory lock 并发锁测试。

迁移并发锁第①步（multi-worker 前置阻断）：
- PostgreSQL 下 run_pending 用 pg_advisory_lock 串行化多 worker 迁移
- 非 PG 方言（SQLite）无 advisory lock 概念 → _advisory_lock 走 yield 旁路
- 获取锁失败时降级不加锁，不阻塞启动

测试分两层：
1. SQLite 层（默认跑）：验证 yield 旁路 + run_pending 经锁包装后仍正常 + 降级兜底
2. pg_only 层（CI 连真 PG 跑）：两个 runner 并发竞态，验证 advisory lock 真正串行化
"""

import asyncio
import textwrap
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.migration_runner import (
    MigrationRunner,
    RunPendingResult,
    _MIGRATION_ADVISORY_LOCK_KEY,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def sqlite_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture
def patch_schema_version_ddl():
    """用 SQLite 兼容 DDL 替换 PG 版（DO $body$ 不支持）。"""
    import app.core.migration_runner as mod
    original = mod._SCHEMA_VERSION_DDL
    mod._SCHEMA_VERSION_DDL = textwrap.dedent("""\
        CREATE TABLE IF NOT EXISTS schema_version (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            version   VARCHAR(20)  NOT NULL UNIQUE,
            filename  VARCHAR(255) NOT NULL,
            applied_at TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
            checksum  VARCHAR(64)  NOT NULL
        );
    """)
    yield
    mod._SCHEMA_VERSION_DDL = original


@pytest.fixture
def mig_dir_basic(tmp_path: Path) -> Path:
    """基线 V001 + 一个建表 V002。"""
    d = tmp_path / "migs"
    d.mkdir()
    (d / "V001__init.sql").write_text("-- baseline\n", encoding="utf-8")
    (d / "V002__create_t1.sql").write_text(
        "CREATE TABLE IF NOT EXISTS t1 (id INTEGER PRIMARY KEY);\n",
        encoding="utf-8",
    )
    return d


# ---------------------------------------------------------------------------
# SQLite 层：非 PG 旁路 + 锁包装不破坏 run_pending + 降级兜底
# ---------------------------------------------------------------------------

class TestAdvisoryLockSqliteBypass:
    """非 PG 方言下 _advisory_lock 走 yield 旁路，不调用 pg_advisory_lock。"""

    async def test_sqlite_dialect_skips_advisory_lock(self, sqlite_engine):
        """SQLite 引擎：_advisory_lock 直接 yield，全程不开新连接、不执行锁 SQL。"""
        runner = MigrationRunner(engine=sqlite_engine)
        # 若误在 SQLite 上执行 pg_advisory_lock，SQLite 会抛 "no such function"
        async with runner._advisory_lock():
            pass  # 进得来即说明走了 yield 旁路

    async def test_run_pending_still_works_through_lock(
        self, sqlite_engine, mig_dir_basic, patch_schema_version_ddl
    ):
        """run_pending 经 advisory lock 包装后，SQLite 下迁移仍正常执行。"""
        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=mig_dir_basic)
        result = await runner.run_pending()

        assert isinstance(result, RunPendingResult)
        assert "002" in result.executed
        assert result.failed == []
        # 建表生效
        async with sqlite_engine.begin() as conn:
            rows = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='t1'")
            )
            assert rows.fetchone() is not None

    async def test_second_run_noop_through_lock(
        self, sqlite_engine, mig_dir_basic, patch_schema_version_ddl
    ):
        """第二次 run_pending（锁包装下）应无 pending，干净返回空。"""
        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=mig_dir_basic)
        await runner.run_pending()
        result2 = await runner.run_pending()

        assert result2.executed == []
        assert result2.failed == []


class _FakeDialect:
    def __init__(self, name):
        self.name = name


class _ConnectFailEngine:
    """伪 AsyncEngine：dialect.name='postgresql' 但 connect() 抛错。

    用于隔离验证 _advisory_lock 在"获取锁连接失败"时的降级语义，
    避免 patch 真实 AsyncEngine 的只读属性。
    """

    def __init__(self):
        self.dialect = _FakeDialect("postgresql")

    async def connect(self):
        raise RuntimeError("simulated connect failure for lock")


class TestAdvisoryLockDegradation:
    """获取锁失败时降级为不加锁执行（不阻塞启动）。"""

    async def test_lock_acquire_failure_degrades_to_yield(self):
        """PG 方言但取锁连接失败 → _advisory_lock 不抛错，仍正常 yield（降级不加锁）。"""
        runner = MigrationRunner.__new__(MigrationRunner)
        runner._engine = _ConnectFailEngine()
        runner._owns_engine = False

        entered = False
        async with runner._advisory_lock():
            entered = True  # 能进入 = 降级成功，未因取锁失败而阻塞/抛错
        assert entered, "取锁失败应降级 yield，而非抛出阻塞启动"

    async def test_sqlite_bypass_yields_without_connection(self):
        """SQLite 方言：_advisory_lock 走旁路 yield，连 connect 都不调用。"""
        class _NeverConnectEngine:
            def __init__(self):
                self.dialect = _FakeDialect("sqlite")

            async def connect(self):  # pragma: no cover - 不应被调用
                raise AssertionError("SQLite 旁路不应调用 connect()")

        runner = MigrationRunner.__new__(MigrationRunner)
        runner._engine = _NeverConnectEngine()
        runner._owns_engine = False

        async with runner._advisory_lock():
            pass  # 进得来且 connect 未被调用即通过


# ---------------------------------------------------------------------------
# pg_only 层：真 PG 下两个 runner 并发竞态，验证 advisory lock 真正串行化
# ---------------------------------------------------------------------------

@pytest.mark.pg_only
class TestAdvisoryLockRealRace:
    """真 PostgreSQL：advisory lock 串行化多进程/多 worker 并发迁移。

    需 DATABASE_URL 指向真实 PG（conftest 的 pytest_collection_modifyitems 会在
    非 PG 环境自动 skip 本类）。
    """

    # 用远超真实最高版本（V050）的版本号 + 独立表名，避免与已应用迁移撞号
    _V_A = "99001"
    _V_B = "99002"
    _TEST_TABLE = "_test_advlock_t1"

    @pytest.fixture
    def mig_dir_high_version(self, tmp_path: Path) -> Path:
        """专供 PG 竞态测试的迁移目录：高版本号 + 独立表名，绝不与真实迁移撞号。"""
        d = tmp_path / "migs_high"
        d.mkdir()
        (d / f"V{self._V_A}__advlock_base.sql").write_text(
            "-- advlock test baseline\n", encoding="utf-8"
        )
        (d / f"V{self._V_B}__advlock_create.sql").write_text(
            f"CREATE TABLE IF NOT EXISTS {self._TEST_TABLE} (id INTEGER PRIMARY KEY);\n",
            encoding="utf-8",
        )
        return d

    @pytest.fixture
    def _pg_url(self):
        import os
        url = os.getenv("DATABASE_URL", "")
        # 统一成 asyncpg driver
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    async def test_advisory_lock_held_blocks_second_acquirer(self, _pg_url):
        """持锁期间，第二个连接的 pg_try_advisory_lock 拿不到锁。

        直接验证锁语义：runner A 持锁时，独立连接 try-lock 同一 key 必失败。
        """
        engine_a = create_async_engine(_pg_url, pool_pre_ping=True)
        engine_probe = create_async_engine(_pg_url, pool_pre_ping=True)
        try:
            runner_a = MigrationRunner(engine=engine_a)
            async with runner_a._advisory_lock():
                # A 持锁中，探针连接 try-lock 同一 key 应失败（False）
                async with engine_probe.connect() as probe:
                    got = await probe.execute(
                        text("SELECT pg_try_advisory_lock(:k)"),
                        {"k": _MIGRATION_ADVISORY_LOCK_KEY},
                    )
                    assert got.scalar() is False, "持锁期间第二个 acquirer 不应拿到锁"
            # A 释放后，探针应能拿到锁
            async with engine_probe.connect() as probe:
                got = await probe.execute(
                    text("SELECT pg_try_advisory_lock(:k)"),
                    {"k": _MIGRATION_ADVISORY_LOCK_KEY},
                )
                assert got.scalar() is True, "锁释放后应可重新获取"
                await probe.execute(
                    text("SELECT pg_advisory_unlock(:k)"),
                    {"k": _MIGRATION_ADVISORY_LOCK_KEY},
                )
        finally:
            await engine_a.dispose()
            await engine_probe.dispose()

    async def test_concurrent_run_pending_serialized(self, _pg_url, mig_dir_high_version):
        """两个 runner 并发 run_pending 同一迁移目录：不报错、迁移恰执行一次。

        advisory lock 串行化后，先抢到锁的执行迁移，另一个等锁释放后看到已最新 → 空执行。
        合计 executed 计数中高版本建表迁移只应出现一次（不重复执行建表）。
        用高版本号(99001/99002)+独立表名，避免与真实库已应用的 V001-V050 撞号。
        """
        v_a, v_b, tbl = self._V_A, self._V_B, self._TEST_TABLE
        engine1 = create_async_engine(_pg_url, pool_pre_ping=True)
        engine2 = create_async_engine(_pg_url, pool_pre_ping=True)
        try:
            # 预清理：确保从干净状态开始（drop 测试表 + schema_version 测试行）
            async with engine1.begin() as conn:
                await conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))
                await conn.execute(
                    text("DELETE FROM schema_version WHERE version IN (:a, :b)"),
                    {"a": v_a, "b": v_b},
                )

            runner1 = MigrationRunner(engine=engine1, migrations_dir=mig_dir_high_version)
            runner2 = MigrationRunner(engine=engine2, migrations_dir=mig_dir_high_version)

            r1, r2 = await asyncio.gather(
                runner1.run_pending(),
                runner2.run_pending(),
                return_exceptions=True,
            )

            # 两个调用都不应抛异常（advisory lock 防止竞态崩溃）
            assert not isinstance(r1, Exception), f"runner1 抛错: {r1}"
            assert not isinstance(r2, Exception), f"runner2 抛错: {r2}"

            # 建表迁移合计只被执行一次（串行化后另一个看到已最新）
            executed_b = list(r1.executed).count(v_b) + list(r2.executed).count(v_b)
            assert executed_b == 1, (
                f"{v_b} 迁移应恰执行一次，实际 {executed_b} 次 "
                f"(r1={r1.executed}, r2={r2.executed})"
            )

            # 表确实建好
            async with engine1.connect() as conn:
                rows = await conn.execute(text(f"SELECT to_regclass('public.{tbl}')"))
                assert rows.scalar() is not None
        finally:
            # 清理测试残留
            async with engine1.begin() as conn:
                await conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))
                await conn.execute(
                    text("DELETE FROM schema_version WHERE version IN (:a, :b)"),
                    {"a": v_a, "b": v_b},
                )
            await engine1.dispose()
            await engine2.dispose()
