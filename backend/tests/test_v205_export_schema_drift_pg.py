"""V205 在漂移库上可执行、两次幂等、R205 可回放，补出的列与 ORM 同型（spec note-pull-followup-closure R24）。

原 V205 第一句就是 ``ALTER TABLE word_export_task_versions ALTER COLUMN snapshot_id TYPE uuid``，而磁盘上没有任何
迁移加过这一列 ⇒ 在真实库上必报 42703、整个迁移从未应用过（全量重启后 /api/health 恒 degraded）。

临时 schema（search_path 只含它，迁移里不带 schema 的 ALTER 落不到 public）按改前真实库的形态建 4 张表：
``snapshot_id`` 仍是 varchar、``word_export_task_versions`` 没有 snapshot_id / file_sha256、``export_jobs_v2`` 没有
readiness、``export_job_attempts`` 还有孤立列 ``trigger``。用 runner 自己的拆句与执行方式跑 V205 两次 + R205。
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_MIGRATIONS = _BACKEND / "migrations"
_TABLES = ("export_jobs_v2", "export_job_items_v2", "export_job_attempts", "word_export_task_versions")
_OLD_FIRST_STATEMENT = "ALTER TABLE word_export_task_versions ALTER COLUMN snapshot_id TYPE uuid USING snapshot_id::uuid"


async def _run_sql_file(conn, path: Path) -> int:
    from app.core.migration_runner import MigrationRunner

    statements = MigrationRunner._split_sql_statements(path.read_text(encoding="utf-8"))
    for stmt in statements:
        await conn.exec_driver_sql(stmt)
    return len(statements)


async def _shape(conn) -> dict[tuple[str, str], tuple[str, int | None]]:
    rows = await conn.execute(sa.text(
        "SELECT table_name, column_name, udt_name, character_maximum_length FROM information_schema.columns "
        "WHERE table_schema = current_schema()"))
    return {(r[0], r[1]): (r[2], r[3]) for r in rows}


async def _scenario() -> dict:
    from app.core.database import engine

    if engine.dialect.name != "postgresql":
        return {"skip": True}
    schema = f"tmp_v205_{uuid.uuid4().hex[:10]}"
    snap = str(uuid.uuid4())
    out: dict = {}
    async with engine.begin() as conn:
        await conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text(f'SET search_path TO "{schema}"'))
            await conn.exec_driver_sql(
                "CREATE TABLE export_jobs_v2 (id uuid PRIMARY KEY, snapshot_id varchar(64))")
            await conn.exec_driver_sql(
                "CREATE TABLE export_job_items_v2 (id uuid PRIMARY KEY, snapshot_id varchar(64))")
            await conn.exec_driver_sql(
                "CREATE TABLE export_job_attempts (id uuid PRIMARY KEY, snapshot_id varchar(64), "
                "trigger varchar(20), trigger_source varchar(20))")
            await conn.exec_driver_sql("CREATE TABLE word_export_task_versions (id uuid PRIMARY KEY)")
            await conn.execute(sa.text("INSERT INTO export_jobs_v2 (id, snapshot_id) VALUES (:i, :s)"),
                               {"i": uuid.uuid4(), "s": snap})
            await conn.execute(sa.text("INSERT INTO export_job_items_v2 (id, snapshot_id) VALUES (:i, NULL)"),
                               {"i": uuid.uuid4()})

            # 夹具真的复现了缺陷：改前的第一句在这张表上报 42703（判据不空转）
            savepoint = await conn.begin_nested()
            try:
                await conn.exec_driver_sql(_OLD_FIRST_STATEMENT)
                out["old_error"] = None
            except sa.exc.DBAPIError as exc:
                out["old_error"] = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None) or str(exc)
            await savepoint.rollback()

            out["before"] = await _shape(conn)
            out["stmts_1"] = await _run_sql_file(conn, _MIGRATIONS / "V205__fix_export_schema_drift.sql")
            out["after_1"] = await _shape(conn)
            out["stmts_2"] = await _run_sql_file(conn, _MIGRATIONS / "V205__fix_export_schema_drift.sql")
            out["after_2"] = await _shape(conn)
            out["stmts_r"] = await _run_sql_file(conn, _MIGRATIONS / "R205__fix_export_schema_drift.sql")
            out["after_r"] = await _shape(conn)
            out["snap_after"] = (await conn.execute(sa.text("SELECT snapshot_id FROM export_jobs_v2"))).scalar_one()
            await conn.rollback()
    finally:
        async with engine.begin() as conn:
            await conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
    out["snap"] = snap
    return out


@pytest.fixture(scope="module")
def outcome() -> dict:
    out = asyncio.run(_scenario())
    if out.get("skip"):
        pytest.skip("需 PostgreSQL（V205 真 PG 幂等）")
    return out


def test_fixture_reproduces_the_42703(outcome) -> None:
    assert outcome["old_error"] == "42703", outcome["old_error"]
    assert ("word_export_task_versions", "snapshot_id") not in outcome["before"]


def test_v205_adds_missing_columns_with_orm_types(outcome) -> None:
    from app.models.phase13_models import ExportJob, WordExportTaskVersion

    after = outcome["after_1"]
    assert after[("export_jobs_v2", "readiness")] == ("jsonb", None)
    assert after[("word_export_task_versions", "snapshot_id")] == ("uuid", None)
    assert after[("word_export_task_versions", "file_sha256")] == ("varchar", 64)
    # 三层一致：与 ORM 声明同型
    assert ExportJob.__table__.c.readiness.type.__class__.__name__ == "JSONB"
    assert WordExportTaskVersion.__table__.c.snapshot_id.type.__class__.__name__ == "UUID"
    assert WordExportTaskVersion.__table__.c.file_sha256.type.length == 64


def test_v205_casts_snapshot_id_and_drops_orphan_trigger(outcome) -> None:
    after = outcome["after_1"]
    for table in _TABLES:
        assert after[(table, "snapshot_id")][0] == "uuid", table
    assert ("export_job_attempts", "trigger") not in after
    assert ("export_job_attempts", "trigger_source") in after
    assert str(outcome["snap_after"]) == outcome["snap"], "已有的 snapshot_id 值转成 uuid 后不变"


def test_v205_and_r205_are_rerunnable(outcome) -> None:
    assert outcome["stmts_1"] == outcome["stmts_2"] > 0
    assert outcome["after_2"] == outcome["after_1"], "第二次执行不改任何列"
    assert outcome["stmts_r"] > 0 and outcome["after_r"] == outcome["after_1"]
