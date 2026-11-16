"""V273/R273（合并入 dev1.0 时由 V271/R271 改号） 与 LedgerImportAttempt 的隔离迁移合同测试。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.migration_runner import MigrationFile, MigrationRunner
from app.models.dataset_models import LedgerImportAttempt

_BACKEND = Path(__file__).resolve().parents[1]
_MIGRATIONS = _BACKEND / "migrations"
_V273 = _MIGRATIONS / "V273__ledger_import_attempts.sql"
_R273 = _MIGRATIONS / "R273__rollback_ledger_import_attempts.sql"
_REQUIRED_COLUMNS = {
    "id",
    "project_id",
    "year",
    "dataset_id",
    "base_dataset_id",
    "base_unit_contract_digest",
    "upload_token",
    "status",
    "current_phase",
    "created_by",
    "created_at",
    "updated_at",
    "payload_style",
    "unit_confirmation",
}


def _migration_file(path: Path, version: str) -> MigrationFile:
    content = path.read_text(encoding="utf-8")
    return MigrationFile(
        version=version,
        filename=path.name,
        path=path,
        checksum=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


def test_v273_is_current_unique_vr_pair_and_model_shape() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    runner = MigrationRunner(engine=engine, migrations_dir=_MIGRATIONS)
    try:
        versions = [migration for migration in runner.scan_migrations() if migration.version == "273"]
        rollbacks = [migration for migration in runner.scan_rollback_scripts() if migration.version == "273"]
        assert [migration.filename for migration in versions] == [_V273.name]
        assert [migration.filename for migration in rollbacks] == [_R273.name]
        assert max(int(migration.version) for migration in runner.scan_migrations()) == 273
    finally:
        # scan_migrations 不会打开连接，但释放测试引擎避免资源告警。
        import asyncio

        asyncio.run(engine.dispose())

    assert _REQUIRED_COLUMNS <= set(LedgerImportAttempt.__table__.c.keys())
    assert not LedgerImportAttempt.__table__.c.unit_confirmation.nullable
    assert "ck_ledger_import_attempt_status" in {
        constraint.name for constraint in LedgerImportAttempt.__table__.constraints
    }
    assert "RAISE EXCEPTION" in _R273.read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS ledger_import_attempts" in _R273.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_v273_and_r273_run_without_pg_syntax_on_empty_sqlite_table() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    runner = MigrationRunner(engine=engine, migrations_dir=_MIGRATIONS)
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("CREATE TABLE projects (id UUID PRIMARY KEY)")
            await conn.exec_driver_sql("CREATE TABLE users (id UUID PRIMARY KEY)")
            await conn.exec_driver_sql("CREATE TABLE ledger_datasets (id UUID PRIMARY KEY)")
            for statement in runner._split_sql_statements(_V273.read_text(encoding="utf-8")):
                await conn.exec_driver_sql(statement)
            columns = {
                row[1]
                for row in (await conn.execute(text("PRAGMA table_info(ledger_import_attempts)"))).fetchall()
            }
            assert _REQUIRED_COLUMNS <= columns

        await runner._execute_rollback_script(_migration_file(_R273, "273"))
        async with engine.connect() as conn:
            exists = await conn.execute(text(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ledger_import_attempts'"
            ))
            assert exists.scalar_one_or_none() is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_r273_sqlite_protection_rejects_non_empty_attempts() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    runner = MigrationRunner(engine=engine, migrations_dir=_MIGRATIONS)
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("CREATE TABLE ledger_import_attempts (id INTEGER PRIMARY KEY)")
            await conn.exec_driver_sql("INSERT INTO ledger_import_attempts (id) VALUES (1)")

        with pytest.raises(RuntimeError, match="仍有数据"):
            await runner._execute_rollback_script(_migration_file(_R273, "273"))

        async with engine.connect() as conn:
            row = await conn.execute(text("SELECT COUNT(*) FROM ledger_import_attempts"))
            assert row.scalar_one() == 1
    finally:
        await engine.dispose()
