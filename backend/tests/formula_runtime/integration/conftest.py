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

        asyncio.get_event_loop().run_until_complete(_probe())
        return True
    except Exception:
        return False


PG_REACHABLE = _check_pg_connectivity()

# NOTE: We intentionally do NOT use pytest.mark.pg_only here.
# The root conftest skips pg_only tests when PG is unavailable, but Req 14.5
# demands explicit FAILURE not skip. Our _require_pg fixture handles this.


# ─── Engine + session factory (only instantiate if PG available) ────────────────

_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None and PG_AVAILABLE:
        connect_args = {"ssl": False} if os.getenv("DB_DISABLE_SSL", "True") == "True" else {}
        _engine = create_async_engine(
            DATABASE_URL,
            echo=False,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        eng = _get_engine()
        if eng is not None:
            _session_factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    return _session_factory


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
    """Provide a real PG async session that rolls back after each test."""
    factory = _get_session_factory()
    if factory is None:
        pytest.fail("PostgreSQL session factory unavailable")

    async with factory() as session:
        # Start a transaction that we will roll back after the test
        async with session.begin():
            yield session
            # Rollback ensures test isolation — no committed side effects
            await session.rollback()


@pytest_asyncio.fixture()
async def pg_committed_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a real PG session that commits (for testing commit behavior).

    CAUTION: Tests using this fixture create real data.
    Use unique IDs and clean up in teardown.
    """
    factory = _get_session_factory()
    if factory is None:
        pytest.fail("PostgreSQL session factory unavailable")

    async with factory() as session:
        yield session
        # Cleanup: rollback any pending transaction
        await session.rollback()


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
