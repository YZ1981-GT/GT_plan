# Feature: procedure-delegation-notification — Task 2 P35 数据库属性测试
"""P35: current revision 唯一且 fail-closed。

任意 template_code 最多一个 active current revision；零 current、多 current
或 reconcile_pending 时 materialize/overlay 均拒绝，不混合历史 definition。

本测试使用 Hypothesis 在 PostgreSQL 上验证：
1. 唯一性：同一 template_code 下 partial unique 禁止多 current。
2. fail-closed（零 current）：resolver 必须拒绝。
3. fail-closed（reconcile_pending）：resolver 必须拒绝。
4. 合法唯一 current：resolver 返回唯一 revision_hash。

**Validates: Requirements 15.1-15.2**
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings as app_settings
from app.core.migration_runner import MigrationRunner

_V105 = (
    Path(__file__).resolve().parent.parent.parent
    / "migrations"
    / "V105__procedure_row_tasks.sql"
)
_V112 = (
    Path(__file__).resolve().parent.parent.parent
    / "migrations"
    / "V112__procedure_current_revision_registry.sql"
)
_IS_PG = app_settings.DATABASE_URL.startswith("postgresql")


async def _apply_migrations(engine) -> None:
    for path in (_V105, _V112):
        sql = path.read_text(encoding="utf-8")
        statements = MigrationRunner._split_sql_statements(sql)
        async with engine.begin() as conn:
            for stmt in statements:
                await conn.exec_driver_sql(stmt)


@pytest_asyncio.fixture
async def pg_engine():
    if not _IS_PG:
        pytest.skip("need PostgreSQL (P35 property test)")
    engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")
    try:
        yield engine
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------
# Generate short template codes (8-12 hex chars to avoid collisions with real data)
_template_code_st = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    min_size=8,
    max_size=12,
).map(lambda s: f"P35_{s}")

# Generate 64-char hex revision hashes
_revision_hash_st = st.text(
    alphabet="0123456789abcdef",
    min_size=64,
    max_size=64,
)


async def _resolve_current(conn, template_code: str) -> str | None:
    """Resolve the unique current revision for a template_code.

    Returns revision_hash if exactly one current exists, None otherwise.
    This mirrors the fail-closed resolution logic required by D9.
    """
    rows = (
        await conn.execute(
            sa.text(
                "SELECT revision_hash, status FROM procedure_template_revisions "
                "WHERE template_code = :tc AND is_current = true"
            ),
            {"tc": template_code},
        )
    ).fetchall()
    if len(rows) != 1:
        return None  # zero or multiple → fail-closed
    row = rows[0]
    if row.status != "current":
        return None  # reconcile_pending with is_current somehow → fail-closed
    return row.revision_hash


async def _has_reconcile_pending(conn, template_code: str) -> bool:
    """Check if template_code has reconcile_pending revisions."""
    cnt = (
        await conn.execute(
            sa.text(
                "SELECT count(*) FROM procedure_template_revisions "
                "WHERE template_code = :tc AND status = 'reconcile_pending'"
            ),
            {"tc": template_code},
        )
    ).scalar()
    return cnt > 0


# ---------------------------------------------------------------------------
# P35 Property Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestP35CurrentRevisionProperty:
    """P35: current revision 唯一且 fail-closed。"""

    @settings(max_examples=5, deadline=None)
    @given(
        template_code=_template_code_st,
        hash1=_revision_hash_st,
        hash2=_revision_hash_st,
    )
    async def test_partial_unique_rejects_dual_current(
        self, pg_engine, template_code: str, hash1: str, hash2: str
    ):
        """同一 template_code 不可有两个 is_current=true。

        **Validates: Requirements 15.1**
        """
        if hash1 == hash2:
            return  # trivial; identity index would catch same hash
        await _apply_migrations(pg_engine)
        async with pg_engine.connect() as conn:
            trans = await conn.begin()
            try:
                # Insert first current — must succeed
                await conn.execute(
                    sa.text(
                        "INSERT INTO procedure_template_revisions "
                        "(template_code, revision_hash, status, is_current) "
                        "VALUES (:tc, :h, 'current', true) "
                        "ON CONFLICT (template_code, revision_hash) DO NOTHING"
                    ),
                    {"tc": template_code, "h": hash1},
                )
                # Attempt second current → must be rejected by partial unique
                rejected = False
                try:
                    async with conn.begin_nested():
                        await conn.execute(
                            sa.text(
                                "INSERT INTO procedure_template_revisions "
                                "(template_code, revision_hash, status, is_current) "
                                "VALUES (:tc, :h, 'current', true)"
                            ),
                            {"tc": template_code, "h": hash2},
                        )
                except IntegrityError:
                    rejected = True
                assert rejected, (
                    f"partial unique 未拒绝 template_code={template_code} 的第二个 current"
                )
            finally:
                await trans.rollback()

    @settings(max_examples=5, deadline=None)
    @given(template_code=_template_code_st)
    async def test_zero_current_fails_closed(self, pg_engine, template_code: str):
        """零 current 时 resolver 返回 None（fail-closed）。

        **Validates: Requirements 15.2**
        """
        await _apply_migrations(pg_engine)
        async with pg_engine.connect() as conn:
            trans = await conn.begin()
            try:
                # Ensure no current for this template_code (fresh generated code)
                result = await _resolve_current(conn, template_code)
                assert result is None, (
                    f"零 current 应 fail-closed，但 resolver 返回 {result}"
                )
            finally:
                await trans.rollback()

    @settings(max_examples=5, deadline=None)
    @given(
        template_code=_template_code_st,
        hash1=_revision_hash_st,
        hash2=_revision_hash_st,
    )
    async def test_reconcile_pending_fails_closed(
        self, pg_engine, template_code: str, hash1: str, hash2: str
    ):
        """reconcile_pending 状态时 resolver 必须 fail-closed。

        **Validates: Requirements 15.2**
        """
        if hash1 == hash2:
            return
        await _apply_migrations(pg_engine)
        async with pg_engine.connect() as conn:
            trans = await conn.begin()
            try:
                # Insert two reconcile_pending revisions (is_current=false)
                for h in (hash1, hash2):
                    await conn.execute(
                        sa.text(
                            "INSERT INTO procedure_template_revisions "
                            "(template_code, revision_hash, status, is_current) "
                            "VALUES (:tc, :h, 'reconcile_pending', false) "
                            "ON CONFLICT (template_code, revision_hash) DO NOTHING"
                        ),
                        {"tc": template_code, "h": h},
                    )
                # Resolver must fail-closed (no current)
                result = await _resolve_current(conn, template_code)
                assert result is None, (
                    f"reconcile_pending 应 fail-closed，但 resolver 返回 {result}"
                )
                # Verify reconcile_pending is flagged
                has_pending = await _has_reconcile_pending(conn, template_code)
                assert has_pending, "应存在 reconcile_pending 行"
            finally:
                await trans.rollback()

    @settings(max_examples=5, deadline=None)
    @given(template_code=_template_code_st, hash1=_revision_hash_st)
    async def test_unique_current_resolves_correctly(
        self, pg_engine, template_code: str, hash1: str
    ):
        """唯一 current 存在时 resolver 返回正确 revision_hash。

        **Validates: Requirements 15.1**
        """
        await _apply_migrations(pg_engine)
        async with pg_engine.connect() as conn:
            trans = await conn.begin()
            try:
                await conn.execute(
                    sa.text(
                        "INSERT INTO procedure_template_revisions "
                        "(template_code, revision_hash, status, is_current) "
                        "VALUES (:tc, :h, 'current', true) "
                        "ON CONFLICT (template_code, revision_hash) DO NOTHING"
                    ),
                    {"tc": template_code, "h": hash1},
                )
                result = await _resolve_current(conn, template_code)
                assert result == hash1, (
                    f"唯一 current 应返回 {hash1}，实际返回 {result}"
                )
            finally:
                await trans.rollback()

    @settings(max_examples=5, deadline=None)
    @given(
        template_code=_template_code_st,
        current_hash=_revision_hash_st,
        registered_hash=_revision_hash_st,
    )
    async def test_registered_revision_does_not_resolve(
        self, pg_engine, template_code: str, current_hash: str, registered_hash: str
    ):
        """仅 status='current' 的可解析，registered 不会混入。

        **Validates: Requirements 15.1-15.2**
        """
        if current_hash == registered_hash:
            return
        await _apply_migrations(pg_engine)
        async with pg_engine.connect() as conn:
            trans = await conn.begin()
            try:
                # Insert one current
                await conn.execute(
                    sa.text(
                        "INSERT INTO procedure_template_revisions "
                        "(template_code, revision_hash, status, is_current) "
                        "VALUES (:tc, :h, 'current', true) "
                        "ON CONFLICT (template_code, revision_hash) DO NOTHING"
                    ),
                    {"tc": template_code, "h": current_hash},
                )
                # Insert one registered (is_current=false)
                await conn.execute(
                    sa.text(
                        "INSERT INTO procedure_template_revisions "
                        "(template_code, revision_hash, status, is_current) "
                        "VALUES (:tc, :h, 'registered', false) "
                        "ON CONFLICT (template_code, revision_hash) DO NOTHING"
                    ),
                    {"tc": template_code, "h": registered_hash},
                )
                # Resolver returns only current, not registered
                result = await _resolve_current(conn, template_code)
                assert result == current_hash, (
                    f"应只返回 current({current_hash})，实际 {result}"
                )
            finally:
                await trans.rollback()
