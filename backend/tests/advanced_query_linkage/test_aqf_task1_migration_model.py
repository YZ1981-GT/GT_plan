"""高级查询证据任务 1：迁移、ORM 与迁移未落库降级守卫。"""
from __future__ import annotations

import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.config import settings  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.query_evidence_models import QueryArtifact, QueryRun  # noqa: E402
from app.services.custom_query.query_evidence import query_evidence_available  # noqa: E402

_MIGRATION = _BACKEND / "migrations" / "V267__query_runs_and_artifacts.sql"
_ROLLBACK = _BACKEND / "migrations" / "R267__rollback_query_runs_and_artifacts.sql"


def test_v267_and_r267_are_a_unique_pair_with_idempotent_ddl():
    """迁移号、V/R 配对、表/索引/触发器的物理契约均来自文件内容。"""
    v_sql = _MIGRATION.read_text(encoding="utf-8")
    r_sql = _ROLLBACK.read_text(encoding="utf-8")
    assert _MIGRATION.name.startswith("V267__")
    assert _ROLLBACK.name.startswith("R267__")
    assert "CREATE TABLE IF NOT EXISTS query_runs" in v_sql
    assert "CREATE TABLE IF NOT EXISTS query_artifacts" in v_sql
    assert v_sql.count("CREATE INDEX IF NOT EXISTS") == 7
    assert "CREATE OR REPLACE FUNCTION gt_query_run_immutable" in v_sql
    assert "CREATE OR REPLACE FUNCTION gt_query_artifact_immutable" in v_sql
    assert "DROP TRIGGER IF EXISTS trg_query_run_immutable" in v_sql
    assert "DROP TRIGGER IF EXISTS trg_query_artifact_immutable" in v_sql
    assert "DROP TABLE IF EXISTS query_artifacts" in r_sql
    assert "DROP TABLE IF EXISTS query_runs" in r_sql
    assert "DROP FUNCTION IF EXISTS gt_query_run_immutable()" in r_sql
    assert "DROP FUNCTION IF EXISTS gt_query_artifact_immutable()" in r_sql


def test_query_evidence_orm_columns_match_v267_schema():
    expected_run = {
        "id", "user_id", "entry", "origin", "template_id", "project_id", "year",
        "source_key", "definition", "definition_hash", "definition_version", "scope",
        "labels", "version_vector", "vector_hash", "vector_weak", "captured_at",
        "execution_count", "first_executed_at", "last_executed_at", "last_total",
        "last_warnings", "hidden_at", "created_at", "updated_at",
    }
    expected_artifact = {
        "id", "run_id", "user_id", "entry", "project_id", "year", "source_key",
        "definition_hash", "version_vector", "vector_hash", "scope", "status",
        "file_name", "storage_key", "media_type", "byte_size", "sha256", "row_count",
        "columns", "manifest", "manifest_sha256", "retention_until", "purged_at",
        "created_at", "updated_at",
    }
    assert set(QueryRun.__table__.columns.keys()) == expected_run
    assert set(QueryArtifact.__table__.columns.keys()) == expected_artifact
    migration = _MIGRATION.read_text(encoding="utf-8")
    for column in expected_run | expected_artifact:
        assert re.search(rf"\b{re.escape(column)}\b", migration), column


@pytest.mark.asyncio
async def test_query_evidence_available_uses_sqlite_master(tmp_path):
    """SQLite 接线按 sqlite_master 判断两张表，不把缺表误报为可用。"""
    missing_engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'missing.sqlite'}", poolclass=NullPool
    )
    try:
        async with async_sessionmaker(missing_engine, class_=AsyncSession)() as session:
            assert await query_evidence_available(session) is False
    finally:
        await missing_engine.dispose()

    present_engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'present.sqlite'}", poolclass=NullPool
    )
    try:
        async with present_engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    sync_conn, tables=[QueryRun.__table__, QueryArtifact.__table__]
                )
            )
        async with async_sessionmaker(present_engine, class_=AsyncSession)() as session:
            assert await query_evidence_available(session) is True
    finally:
        await present_engine.dispose()


@pytest.mark.asyncio
async def test_v267_pg_immutable_triggers_and_r267_rollback():
    """在真实 PG 的一个最终回滚事务内验证 P9，不把测试对象留在共享库。"""
    database_url = str(settings.DATABASE_URL)
    if not database_url.startswith("postgresql"):
        pytest.skip("P9 需要真实 PostgreSQL；当前 DATABASE_URL 不是 PostgreSQL")

    connect_args = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(database_url, poolclass=NullPool, connect_args=connect_args)
    from app.core.migration_runner import MigrationRunner

    runner = MigrationRunner(engine=engine)
    conn = await engine.connect()
    transaction = await conn.begin()
    try:
        # 测试自身清理同名对象，且所有 DDL 都在最终回滚事务中。
        await conn.exec_driver_sql("DROP TABLE IF EXISTS query_artifacts, query_runs CASCADE")
        await conn.exec_driver_sql("DROP FUNCTION IF EXISTS gt_query_artifact_immutable()")
        await conn.exec_driver_sql("DROP FUNCTION IF EXISTS gt_query_run_immutable()")
        for statement in runner._split_sql_statements(_MIGRATION.read_text(encoding="utf-8")):
            await conn.exec_driver_sql(statement)

        async with AsyncSession(bind=conn, expire_on_commit=False) as session:
            assert await query_evidence_available(session) is True

        trigger_count = (
            await conn.execute(
                sa.text(
                    "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal "
                    "AND tgname IN ('trg_query_run_immutable', 'trg_query_artifact_immutable')"
                )
            )
        ).scalar_one()
        assert trigger_count == 2
        user_id = (
            await conn.execute(sa.text("SELECT id FROM users LIMIT 1"))
        ).scalar_one_or_none()
        assert user_id is not None, "P9 需要已迁移且存在用户的真实 PG"

        run_id = uuid.uuid4()
        digest = "a" * 64
        now = datetime.now(timezone.utc)
        await conn.execute(
            sa.text(
                "INSERT INTO query_runs "
                "(id, user_id, entry, source_key, definition, definition_hash, "
                "version_vector, vector_hash, captured_at) "
                "VALUES (:id, :user_id, 'business', 'trial_balance', "
                "CAST(:definition AS jsonb), :definition_hash, CAST(:vector AS jsonb), "
                ":vector_hash, :captured_at)"
            ),
            {
                "id": run_id,
                "user_id": user_id,
                "definition": "{}",
                "definition_hash": digest,
                "vector": "{}",
                "vector_hash": "b" * 64,
                "captured_at": now,
            },
        )

        async def rejected(statement: sa.TextClause, params: dict | None = None):
            with pytest.raises(sa.exc.DBAPIError) as caught:
                async with conn.begin_nested():
                    await conn.execute(statement, params or {})
            assert getattr(caught.value.orig, "sqlstate", None) == "23514"

        await rejected(
            sa.text("UPDATE query_runs SET source_key = 'report' WHERE id = :id"),
            {"id": run_id},
        )
        await conn.execute(
            sa.text("UPDATE query_runs SET execution_count = 2 WHERE id = :id"),
            {"id": run_id},
        )

        artifact_id = uuid.uuid4()
        await conn.execute(
            sa.text(
                "INSERT INTO query_artifacts "
                "(id, run_id, user_id, entry, source_key, definition_hash, version_vector, "
                "vector_hash, file_name, storage_key, media_type, byte_size, sha256, "
                "row_count, columns, manifest, manifest_sha256, retention_until) "
                "VALUES (:id, :run_id, :user_id, 'business', 'trial_balance', :definition_hash, "
                "CAST(:vector AS jsonb), :vector_hash, 'q.xlsx', :storage_key, "
                "'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 0, :sha256, "
                "0, CAST(:columns AS jsonb), CAST(:manifest AS jsonb), :manifest_sha256, :retention)"
            ),
            {
                "id": artifact_id,
                "run_id": run_id,
                "user_id": user_id,
                "definition_hash": digest,
                "vector": "{}",
                "vector_hash": "b" * 64,
                "storage_key": f"2026/11/{artifact_id}.xlsx",
                "sha256": "c" * 64,
                "columns": "[]",
                "manifest": "{}",
                "manifest_sha256": "d" * 64,
                "retention": now,
            },
        )
        await rejected(
            sa.text("UPDATE query_artifacts SET file_name = 'other.xlsx' WHERE id = :id"),
            {"id": artifact_id},
        )
        await conn.execute(
            sa.text("UPDATE query_artifacts SET status = 'purged', purged_at = NOW() WHERE id = :id"),
            {"id": artifact_id},
        )
        await rejected(
            sa.text("UPDATE query_artifacts SET status = 'ready', purged_at = NULL WHERE id = :id"),
            {"id": artifact_id},
        )

        for statement in runner._split_sql_statements(_ROLLBACK.read_text(encoding="utf-8")):
            await conn.exec_driver_sql(statement)
        assert (await conn.execute(sa.text("SELECT to_regclass('public.query_runs')"))).scalar() is None
        assert (await conn.execute(sa.text("SELECT to_regclass('public.query_artifacts')"))).scalar() is None
        assert (
            await conn.execute(
                sa.text(
                    "SELECT count(*) FROM pg_proc WHERE proname IN "
                    "('gt_query_run_immutable', 'gt_query_artifact_immutable')"
                )
            )
        ).scalar_one() == 0
    finally:
        await transaction.rollback()
        await conn.close()
        await engine.dispose()
