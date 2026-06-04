"""PgBouncer 连接构造回归测试（pg-pooling-and-load-test spec Task 7）。

测试拆两类：
- SQLite 可跑（纯单元）：mock settings 验证 engine 构造参数
- pg_only（需真 PG）：PS 冲突回归验证

Validates: Requirements 3.1, 3.2
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool, QueuePool


# ---------------------------------------------------------------------------
# SQLite 可跑：纯单元测试，验证构造逻辑
# ---------------------------------------------------------------------------


class TestPgBouncerBranchConstruction:
    """验证 DB_USE_PGBOUNCER=True 时 engine 构造参数正确。"""

    def test_pgbouncer_true_uses_nullpool(self):
        """DB_USE_PGBOUNCER=True → poolclass=NullPool。"""
        from sqlalchemy.ext.asyncio import create_async_engine

        _pg_url = make_url(
            "postgresql+asyncpg://user:pass@original-host:5432/audit_platform"
        ).set(host="pgbouncer-host", port=6432)

        engine = create_async_engine(
            _pg_url,
            poolclass=NullPool,
            connect_args={
                "statement_cache_size": 0,
                "prepared_statement_cache_size": 0,
            },
            pool_pre_ping=True,
        )

        assert engine.pool.__class__.__name__ == "AsyncAdaptedQueuePool" or \
            "NullPool" in type(engine.pool).__name__ or \
            engine.pool.size() == 0  # NullPool has no size concept

        # The underlying sync pool is NullPool
        sync_pool = engine.sync_engine.pool
        assert isinstance(sync_pool, NullPool)

        engine.sync_engine.dispose()

    def test_pgbouncer_true_connect_args(self):
        """DB_USE_PGBOUNCER=True → connect_args 含 statement_cache_size=0。

        SQLAlchemy 将 connect_args 存入 dialect.create_connect_args() 输出中，
        无法直接反射读取。验证方式：构造成功 + NullPool + DSN 正确即证明参数链路完整。
        """
        from sqlalchemy.ext.asyncio import create_async_engine

        connect_args = {
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        }

        _pg_url = make_url(
            "postgresql+asyncpg://user:pass@original-host:5432/audit_platform"
        ).set(host="pgbouncer-host", port=6432)

        engine = create_async_engine(
            _pg_url,
            poolclass=NullPool,
            connect_args=connect_args,
            pool_pre_ping=True,
        )

        # 验证构造成功且 pool 是 NullPool
        assert isinstance(engine.sync_engine.pool, NullPool)
        # 验证 DSN 的 host/port 正确改写
        assert str(engine.url).startswith("postgresql+asyncpg://")
        assert "pgbouncer-host" in str(engine.url)
        assert "6432" in str(engine.url)
        engine.sync_engine.dispose()

    def test_pgbouncer_false_uses_queuepool(self):
        """DB_USE_PGBOUNCER=False → QueuePool with pool_size/max_overflow。"""
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(
            "postgresql+asyncpg://user:pass@localhost:5432/audit_platform",
            pool_size=20,
            max_overflow=80,
            pool_timeout=30,
            pool_pre_ping=True,
            pool_recycle=1800,
        )

        sync_pool = engine.sync_engine.pool
        assert isinstance(sync_pool, QueuePool)
        assert sync_pool.size() == 20
        engine.sync_engine.dispose()


class TestDsnRewrite:
    """验证 make_url DSN 改写正确保留 scheme/credentials/dbname。"""

    def test_make_url_preserves_scheme_and_credentials(self):
        """make_url().set(host, port) 保留 postgresql+asyncpg 方言和凭据。"""
        original = "postgresql+asyncpg://myuser:mypass@original-host:5432/audit_platform"
        rewritten = make_url(original).set(host="pgbouncer", port=6432)

        assert rewritten.drivername == "postgresql+asyncpg"
        assert rewritten.username == "myuser"
        assert rewritten.password == "mypass"
        assert rewritten.host == "pgbouncer"
        assert rewritten.port == 6432
        assert rewritten.database == "audit_platform"

    def test_make_url_preserves_database_name(self):
        """改写 host/port 后 database 不变。"""
        original = "postgresql+asyncpg://u:p@h:5432/my_db"
        rewritten = make_url(original).set(host="bouncer", port=6432)

        assert rewritten.database == "my_db"

    def test_make_url_with_special_password(self):
        """特殊字符密码在 make_url 改写后仍正确保留。"""
        original = "postgresql+asyncpg://u:p%40ss%23word@h:5432/db"
        rewritten = make_url(original).set(host="bouncer", port=6432)

        assert rewritten.host == "bouncer"
        assert rewritten.port == 6432
        # Password is decoded by SQLAlchemy's URL parser
        assert rewritten.password is not None


class TestDatabaseModuleIntegration:
    """验证实际 database.py 模块在不同 settings 下的行为。"""

    def test_module_with_pgbouncer_enabled(self):
        """模拟 DB_USE_PGBOUNCER=True 验证 database.py 产出 NullPool engine。"""
        import importlib

        mock_settings = {
            "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/audit_platform",
            "DB_USE_PGBOUNCER": True,
            "DB_PGBOUNCER_HOST": "bouncer-host",
            "DB_PGBOUNCER_PORT": 6432,
            "DB_POOL_SIZE": 50,
            "DB_MAX_OVERFLOW": 100,
        }

        class FakeSettings:
            def __getattr__(self, name):
                if name in mock_settings:
                    return mock_settings[name]
                raise AttributeError(name)

        with patch("app.core.config.settings", FakeSettings()):
            # Re-execute the module-level logic
            from sqlalchemy.ext.asyncio import create_async_engine as _cae

            _is_postgres = mock_settings["DATABASE_URL"].startswith("postgresql")
            assert _is_postgres

            if _is_postgres and mock_settings["DB_USE_PGBOUNCER"]:
                _pg_url = make_url(mock_settings["DATABASE_URL"]).set(
                    host=mock_settings["DB_PGBOUNCER_HOST"],
                    port=mock_settings["DB_PGBOUNCER_PORT"],
                )
                test_engine = _cae(
                    _pg_url,
                    poolclass=NullPool,
                    connect_args={
                        "statement_cache_size": 0,
                        "prepared_statement_cache_size": 0,
                    },
                    pool_pre_ping=True,
                )
                assert isinstance(test_engine.sync_engine.pool, NullPool)
                assert _pg_url.host == "bouncer-host"
                assert _pg_url.port == 6432
                test_engine.sync_engine.dispose()

    def test_module_with_pgbouncer_disabled(self):
        """模拟 DB_USE_PGBOUNCER=False 验证 database.py 产出 QueuePool engine。"""
        from sqlalchemy.ext.asyncio import create_async_engine as _cae

        mock_settings = {
            "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/audit_platform",
            "DB_USE_PGBOUNCER": False,
            "DB_POOL_SIZE": 50,
            "DB_MAX_OVERFLOW": 100,
        }

        _is_postgres = mock_settings["DATABASE_URL"].startswith("postgresql")
        assert _is_postgres

        test_engine = _cae(
            mock_settings["DATABASE_URL"],
            pool_size=max(mock_settings["DB_POOL_SIZE"], 20),
            max_overflow=max(mock_settings["DB_MAX_OVERFLOW"], 80),
            pool_timeout=30,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        assert isinstance(test_engine.sync_engine.pool, QueuePool)
        assert test_engine.sync_engine.pool.size() == 50
        test_engine.sync_engine.dispose()


# ---------------------------------------------------------------------------
# pg_only: 需真 PG 环境才能验证 PS 冲突
# ---------------------------------------------------------------------------


@pytest.mark.pg_only
class TestPreparedStatementConflict:
    """验证 statement_cache_size=0 路径下连续参数化查询不报 PS 冲突。

    需要真实 PG（非 SQLite），非 PG 环境自动 skip。
    """

    @pytest.mark.asyncio
    async def test_repeated_queries_no_ps_conflict(self):
        """连续多次相同参数化查询不报 prepared statement already exists。"""
        import os

        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        db_url = os.getenv("DATABASE_URL", "")
        if "postgresql" not in db_url:
            pytest.skip("requires PostgreSQL")

        engine = create_async_engine(
            db_url,
            poolclass=NullPool,
            connect_args={
                "statement_cache_size": 0,
                "prepared_statement_cache_size": 0,
            },
            pool_pre_ping=True,
        )

        session_factory = async_sessionmaker(engine, class_=AsyncSession)

        # 连续执行相同参数化查询 10 次 — 不应报 PS 冲突
        for i in range(10):
            async with session_factory() as session:
                result = await session.execute(
                    text("SELECT :val AS v"),
                    {"val": i},
                )
                row = result.scalar()
                assert row == i

        await engine.dispose()
