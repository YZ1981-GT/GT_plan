"""migration-runner-resilience spec / Sprint 1 / Task 1.5

P-1 修复测试：批不中断 + per-migration 异常隔离 + 失败追踪表。

覆盖 CI-1（单文件失败 → 后续仍执行 + failure 表写入 + schema_version 不写）。
所有 case 用 SQLite 内存库。
"""

import textwrap
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.migration_runner import MigrationRunner, RunPendingResult


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
    """基线 V001 + 一个 OK 表的 V002。"""
    d = tmp_path / "migs"
    d.mkdir()
    (d / "V001__init.sql").write_text("-- baseline\n", encoding="utf-8")
    (d / "V002__create_t1.sql").write_text(
        "CREATE TABLE IF NOT EXISTS t1 (id INTEGER PRIMARY KEY);\n",
        encoding="utf-8",
    )
    return d


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBatchResilience:
    """CI-1：单文件失败不阻塞后续迁移。"""

    async def test_bad_migration_does_not_block_subsequent(
        self, sqlite_engine, mig_dir_basic, patch_schema_version_ddl
    ):
        """V099 故意写错 SQL，V100 正常 → V100 仍 applied + V099 写入 failure 表。"""
        # V099 制造失败：引用不存在的表
        (mig_dir_basic / "V099__bad.sql").write_text(
            "INSERT INTO nonexistent_table (x) VALUES (1);\n", encoding="utf-8"
        )
        # V100 正常
        (mig_dir_basic / "V100__create_t2.sql").write_text(
            "CREATE TABLE IF NOT EXISTS t2 (id INTEGER PRIMARY KEY);\n",
            encoding="utf-8",
        )

        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=mig_dir_basic)
        result = await runner.run_pending()

        assert isinstance(result, RunPendingResult)
        # V001/V002/V100 成功；V099 失败
        assert "002" in result.executed
        assert "100" in result.executed
        assert "099" not in result.executed
        assert len(result.failed) == 1
        assert result.failed[0].version == "099"
        assert result.failed[0].error_type  # 不为空

        # schema_version 不含 099
        async with sqlite_engine.begin() as conn:
            rows = await conn.execute(text("SELECT version FROM schema_version"))
            versions = {r[0] for r in rows.fetchall()}
        assert "002" in versions
        assert "100" in versions
        assert "099" not in versions

        # schema_migration_failures 含 099
        async with sqlite_engine.begin() as conn:
            rows = await conn.execute(
                text("SELECT version, attempt_count FROM schema_migration_failures")
            )
            failures = {r[0]: r[1] for r in rows.fetchall()}
        assert failures.get("099") == 1

        # 业务表 t2 存在（证明 V100 真的跑了）
        async with sqlite_engine.begin() as conn:
            rows = await conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='t2'"
            ))
            assert rows.fetchone() is not None

    async def test_failure_retried_and_cleared_on_fix(
        self, sqlite_engine, mig_dir_basic, patch_schema_version_ddl
    ):
        """失败的迁移修复后下次启动重试成功 + failure 记录被清除。"""
        bad_path = mig_dir_basic / "V099__bad.sql"
        bad_path.write_text(
            "INSERT INTO nonexistent_table (x) VALUES (1);\n", encoding="utf-8"
        )

        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=mig_dir_basic)
        r1 = await runner.run_pending()
        assert "099" in {f.version for f in r1.failed}

        # 修复 V099
        bad_path.write_text(
            "CREATE TABLE IF NOT EXISTS t99 (id INTEGER PRIMARY KEY);\n",
            encoding="utf-8",
        )

        r2 = await runner.run_pending()
        assert "099" in r2.executed
        assert r2.failed == []

        # failure 表清空
        async with sqlite_engine.begin() as conn:
            rows = await conn.execute(
                text("SELECT COUNT(*) FROM schema_migration_failures WHERE version='099'")
            )
            assert rows.scalar() == 0

    async def test_multiple_consecutive_failures_do_not_stop_chain(
        self, sqlite_engine, mig_dir_basic, patch_schema_version_ddl
    ):
        """3 个连续失败的迁移 → 不影响后续 good 迁移。"""
        for v in ("097", "098", "099"):
            (mig_dir_basic / f"V{v}__bad.sql").write_text(
                "SELECT * FROM definitely_not_a_table;\n", encoding="utf-8"
            )
        (mig_dir_basic / "V100__good.sql").write_text(
            "CREATE TABLE IF NOT EXISTS t_after_bad (id INTEGER PRIMARY KEY);\n",
            encoding="utf-8",
        )

        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=mig_dir_basic)
        result = await runner.run_pending()

        assert "100" in result.executed
        assert {f.version for f in result.failed} == {"097", "098", "099"}

        # 验证 t_after_bad 真存在
        async with sqlite_engine.begin() as conn:
            rows = await conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='t_after_bad'"
            ))
            assert rows.fetchone() is not None

    async def test_attempt_count_increments_on_repeated_failures(
        self, sqlite_engine, mig_dir_basic, patch_schema_version_ddl
    ):
        """ON CONFLICT 正确递增 attempt_count（第 2/3 次启动 attempt_count=2/3）。"""
        (mig_dir_basic / "V099__bad.sql").write_text(
            "DELETE FROM nonexistent;\n", encoding="utf-8"
        )

        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=mig_dir_basic)
        await runner.run_pending()
        await runner.run_pending()
        await runner.run_pending()

        async with sqlite_engine.begin() as conn:
            rows = await conn.execute(text(
                "SELECT attempt_count FROM schema_migration_failures WHERE version='099'"
            ))
            count = rows.scalar()
        assert count == 3

    async def test_run_pending_result_backward_compat(
        self, sqlite_engine, mig_dir_basic, patch_schema_version_ddl
    ):
        """RunPendingResult 兼容旧调用：list 比较 / iter / len / bool。"""
        runner = MigrationRunner(engine=sqlite_engine, migrations_dir=mig_dir_basic)
        result = await runner.run_pending()

        # 旧风格：直接 == [list]
        assert result == result.executed
        # iter
        assert list(result) == result.executed
        # len
        assert len(result) == len(result.executed)
        # bool（首次 run 有 executed → True）
        assert bool(result) is True

        # 第二次运行无 pending
        result2 = await runner.run_pending()
        assert result2 == []
        assert bool(result2) is False
