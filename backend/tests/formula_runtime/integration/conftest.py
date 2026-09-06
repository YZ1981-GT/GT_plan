"""PostgreSQL integration test fixtures for formula_runtime.

Requires a live PostgreSQL database. Tests are marked with `@pytest.mark.pg_only`
and are skipped automatically when DATABASE_URL is not PostgreSQL.

The conftest uses real async sessions against the configured PG database,
creating test data in transactions and rolling back after each test.

**Validates: Requirements 14.1, 14.5**
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# ─── PG availability detection ─────────────────────────────────────────────────

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/audit_platform",
)
PG_AVAILABLE = DATABASE_URL.startswith("postgresql")


def _check_pg_connectivity() -> bool:
    """Attempt actual TCP connect to PG to avoid confusing skip vs failure."""
    if not PG_AVAILABLE:
        return False
    try:
        import asyncio
        import asyncpg

        async def _probe():
            # Parse from SQLAlchemy URL
            url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
            conn = await asyncpg.connect(url, timeout=3)
            await conn.close()

        # 🔴 探活必须**完全不触碰主线程的 asyncio 状态** —— 本函数在 import 期执行，
        #    而 import 期的任何 loop 操作都会波及**同一次 pytest 运行里的其他测试文件**：
        #      · `get_event_loop().run_until_complete(...)`（原实现）→ 在主线程留下一个
        #        全局 loop，与 pytest-asyncio 为每个测试新建的 loop 打架；
        #      · `asyncio.run(...)`（一度改成这样，实测更糟）→ 跑完**关闭并清空**全局
        #        loop 状态，导致后续依赖 `get_event_loop()` 的测试直接
        #        `RuntimeError: There is no current event loop in thread 'MainThread'`。
        #        实测代价：本文件 + test_draft_refresh_endpoint.py 同批 → 后者 10 个全挂，
        #        而两者单跑各自全绿。
        #    → 放到独立线程里跑一个自建自关的 loop：主线程 asyncio 状态零改动。
        import threading

        outcome: dict[str, bool] = {"ok": False}

        def _runner() -> None:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_probe())
                outcome["ok"] = True
            except Exception:
                outcome["ok"] = False
            finally:
                loop.close()

        th = threading.Thread(target=_runner, daemon=True)
        th.start()
        th.join(timeout=10)
        return outcome["ok"]
    except Exception:
        return False


PG_REACHABLE = _check_pg_connectivity()

# NOTE: We intentionally do NOT use pytest.mark.pg_only here.
# The root conftest skips pg_only tests when PG is unavailable, but Req 14.5
# demands explicit FAILURE not skip. Our _require_pg fixture handles this.


# ─── Engine + session factory (only instantiate if PG available) ────────────────

# 🔴 **不要**把 engine 做成模块级单例（本文件曾经如此，代价见下）
#
# `pytest-asyncio` 给**每个** async 测试开一个新 event loop，测试结束即关闭。
# 而 asyncpg 的连接是绑定在创建它的 loop 上的。一旦 engine 跨测试复用：
#   第 1 个测试跑完 → loop 关闭 → 池里留着绑在死 loop 上的连接
#   第 2 个测试取到那条连接 → `RuntimeError: Event loop is closed`
#                             / `AttributeError: 'NoneType' object has no attribute 'send'`
# 表现是「单跑全绿、同批从第二个起全挂」——本文件 6 个测试长期如此（2026-09-06 实测：
# 单跑 7 个里 6 绿，同批 3 failed + 3 errors）。
#
# 修法两条同时用：
#   1. engine 按测试创建、测试结束 `dispose()`，不跨 loop 复用；
#   2. `poolclass=NullPool` —— 不做连接池，用完即关，杜绝「池里残留死连接」。
# 代价是每个测试多一次 TCP 建连（本文件 7 个测试，可忽略）。
#
# 🔴 两条**各自独立充分**，不是「必须凑齐才生效」（2026-09-06 四组合实测）：
#       A 每测试新建 + NullPool  → 7 passed
#       B 共享 engine + NullPool → 7 passed
#       C 每测试新建 + 默认池    → 7 passed
#       D 共享 engine + 默认池   → 4 passed + 3 errors  ← 唯一打红，即原实现
#   即「跨测试复用连接」才是真因：去掉池、或不共享 engine，任一即可。
#   两条同时用属冗余加固；但**不要因为「另一条会兜住」而删掉其中一条** ——
#   删到只剩 D 那种组合就会立刻回归，而它的表现是「单跑全绿、同批从第二个起挂」，
#   极易被误判成偶发。
def _make_engine():
    """按调用方所在 event loop 新建 engine（调用方负责 dispose）。"""
    if not PG_AVAILABLE:
        return None
    connect_args = {"ssl": False} if os.getenv("DB_DISABLE_SSL", "True") == "True" else {}
    return create_async_engine(
        DATABASE_URL,
        echo=False,
        poolclass=NullPool,
        connect_args=connect_args,
    )


# ─── Fixtures ──────────────────────────────────────────────────────────────────

INTEGRATION_PROJECT_ID = uuid.UUID("5e193c68-0000-0000-0000-100000000001")
INTEGRATION_YEAR = 2025


@pytest.fixture(autouse=True)
def _require_pg():
    """Fail explicitly (not skip) when PG is unreachable — per Req 14.5."""
    if not PG_REACHABLE:
        pytest.fail(
            "PostgreSQL integration tests require a live PostgreSQL instance. "
            f"DATABASE_URL={DATABASE_URL!r} is not reachable. "
            "Ensure postgres docker container is running at localhost:5432."
        )


@pytest_asyncio.fixture()
async def pg_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a real PG async session that rolls back after each test.

    engine 在本 fixture 内创建并 dispose —— 与测试的 event loop 同生命周期
    （见文件上方 `_make_engine` 的注释：跨 loop 复用会让同批执行从第二个起全挂）。
    """
    engine = _make_engine()
    if engine is None:
        pytest.fail("PostgreSQL session factory unavailable")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            # Start a transaction that we will roll back after the test
            async with session.begin():
                yield session
                # Rollback ensures test isolation — no committed side effects
                await session.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture()
async def pg_committed_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a real PG session that commits (for testing commit behavior).

    CAUTION: Tests using this fixture create real data.
    Use unique IDs and clean up in teardown.

    engine 同 `pg_session`：按测试创建 + dispose，不跨 event loop 复用。
    """
    engine = _make_engine()
    if engine is None:
        pytest.fail("PostgreSQL session factory unavailable")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
            # Cleanup: rollback any pending transaction
            await session.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture()
async def integration_project_id(pg_session: AsyncSession) -> uuid.UUID:
    """Use a real existing project or create one with proper schema."""
    # First try to use an existing active project
    result = await pg_session.execute(
        text("SELECT id FROM projects WHERE is_deleted = false LIMIT 1"),
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    # Fallback: create with proper schema (all NOT NULL fields satisfied)
    project_id = INTEGRATION_PROJECT_ID
    await pg_session.execute(
        text("""
            INSERT INTO projects
                (id, name, client_name, status, version, consol_level, scenario,
                 audit_year, is_deleted, created_at, updated_at)
            VALUES
                (:pid, 'Formula Runtime Integration', 'Test Client',
                 'planning', 1, 0, 'normal', :year, false, NOW(), NOW())
            ON CONFLICT (id) DO NOTHING
        """),
        {"pid": str(project_id), "year": INTEGRATION_YEAR},
    )
    return project_id


@pytest_asyncio.fixture()
async def integration_wp_id(pg_session: AsyncSession, integration_project_id: uuid.UUID) -> uuid.UUID:
    """Create a test working paper for integration tests."""
    wp_id = uuid.uuid4()
    await pg_session.execute(
        text("""
            INSERT INTO working_paper (id, project_id, name, status, created_at, updated_at)
            VALUES (:wid, :pid, :name, 'active', NOW(), NOW())
            ON CONFLICT (id) DO NOTHING
        """),
        {"wid": str(wp_id), "pid": str(integration_project_id), "name": "Integration Test WP"},
    )
    return wp_id


@pytest_asyncio.fixture()
async def integration_run_id(
    pg_session: AsyncSession, integration_project_id: uuid.UUID
) -> uuid.UUID:
    """Create a draft_refresh_audit run for integration tests."""
    run_id = uuid.uuid4()
    await pg_session.execute(
        text("""
            INSERT INTO draft_refresh_audit
                (id, project_id, year, operator_id, operator_role, scope,
                 tb_snapshot_hash, affected_count, result_status, detail,
                 transaction_mode, revision_fingerprint)
            VALUES
                (:rid, :pid, :year, :oid, 'partner', 'report',
                 :hash, 0, 'success', '{}',
                 'all_or_nothing', :fp)
        """),
        {
            "rid": str(run_id),
            "pid": str(integration_project_id),
            "year": INTEGRATION_YEAR,
            "oid": str(uuid.uuid4()),
            "hash": "abc123" * 10 + "abcd",
            "fp": "fp_" + uuid.uuid4().hex[:60],
        },
    )
    return run_id
