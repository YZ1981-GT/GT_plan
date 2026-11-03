"""迁移 V227（``attachment_lineage.project_id``：可空列 + 回填 + 索引）的真 PG 验证。

spec formula-hub-integrity-closure 任务 3；需求 7.1；ADR-FHIC-13；D9；变异 #29。

判据：
1. 快照库确由 MigrationRunner 执行过当前这一版 V227：``schema_version`` 里 V227 的 checksum 等于磁盘文件按
   runner 自己的算法实算的值（改了 V227 而没重建快照会红）。
2. ``pg_tx``（外层事务，结束回滚）内先按 R227 删列（索引随之删除），造 1 条孤儿（附件不存在）与 1 条正常行，
   再按 MigrationRunner 的分句与执行方式（``exec_driver_sql``）重放 V227：不报错；正常行回填为附件所属项目；
   孤儿 ``project_id`` 为空且原行仍在（总行数不变）；可空 uuid 列与索引 (project_id, target_type, target_ref)
   存在；表上没有外键；迁移内 NOTICE 报的孤儿 / 仍为空行数等于独立 SQL 计数。再重放一次：行、索引不变（幂等）。
3. 空值行（孤儿、迁移后旧代码写入的行）对任何项目都不可见（任务 4 起 ``_query_attachments`` 按本项目过滤；
   任务 3 期间以 ``xfail(strict=True)`` 钉住，任务 4 落地后已删除该标记）。
4. 含 DDL 的重放只在快照库上做（``replay`` 先校验库名，ADR-FHIC-25）：库名不以 ``fh_snap_`` 开头即失败、不执行任何语句。
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.migration_runner import MigrationRunner
from app.services.attachment_lineage_schema import clear_lineage_schema_cache
from app.services.unified_lineage_service import UnifiedLineageService
from tests.formula_hub._lineage_fixtures import (
    MIGRATIONS_DIR,
    R227,
    V227,
    index_columns,
    insert_lineage,
    lineage_state,
    make_attachment,
    make_project,
    project_column,
    replay,
)

pytestmark = pytest.mark.pg_only

REF = "FH-T3-MIG!B5"
INDEX = ["project_id", "target_type", "target_ref"]
_ORPHAN_COUNT_SQL = ("SELECT count(*) FROM attachment_lineage al "
                     "WHERE NOT EXISTS (SELECT 1 FROM attachments a WHERE a.id = al.attachment_id)")
_NULL_COUNT_SQL = "SELECT count(*) FROM attachment_lineage WHERE project_id IS NULL"
_FK_COUNT_SQL = ("SELECT count(*) FROM pg_constraint "
                 "WHERE conrelid = 'attachment_lineage'::regclass AND contype = 'f'")


@pytest.fixture(autouse=True)
def _fresh_schema_cache():
    clear_lineage_schema_cache()
    yield
    clear_lineage_schema_cache()


async def _scalar(session, sql: str) -> int:
    return int((await session.execute(text(sql))).scalar_one())


@asynccontextmanager
async def _notices(session) -> AsyncIterator[list[str]]:
    """收集该连接上的 NOTICE（asyncpg 用 call_soon 派发监听器，读之前让出一次事件循环）。"""
    raw = await (await session.connection()).get_raw_connection()
    driver = raw.driver_connection
    messages: list[str] = []

    def listener(_connection, message) -> None:
        messages.append(message.message)

    driver.add_log_listener(listener)
    try:
        yield messages
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    finally:
        driver.remove_log_listener(listener)


async def test_snapshot_ran_current_v206_through_migration_runner(pg_tx):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        runner = MigrationRunner(engine=engine, migrations_dir=MIGRATIONS_DIR)
        (current,) = [mig for mig in runner.scan_migrations() if mig.filename == V227.name]
    finally:
        await engine.dispose()
    stored = (await pg_tx.execute(
        text("SELECT checksum FROM schema_version WHERE version = :v"), {"v": current.version})).scalar_one_or_none()
    assert stored == current.checksum, (
        f"快照库的 V{current.version} 不是当前文件（库内 {stored}，文件 {current.checksum}）："
        "先 snapshot_db.py drop / create / migrate")


async def test_v206_replay_backfills_keeps_orphans_and_creates_index(pg_tx):
    session = pg_tx
    assert await project_column(session) == ("uuid", "YES")
    assert await index_columns(session) == INDEX
    await replay(session, R227)  # 回滚事务内删列：R227 先删索引再删列
    assert await project_column(session) is None and await index_columns(session) is None

    project_id = await make_project(session, "v206")
    attachment_id = await make_attachment(session, project_id)
    normal = await insert_lineage(session, attachment_id=attachment_id, target_ref=REF, project_column=False)
    orphan = await insert_lineage(session, attachment_id=uuid.uuid4(), target_ref=REF, project_column=False)
    total_before = await _scalar(session, "SELECT count(*) FROM attachment_lineage")

    async with _notices(session) as notices:
        statements = await replay(session, V227)
    assert statements == 4, statements  # 加列、回填、建索引、计数块

    state = await lineage_state(session, [normal, orphan])
    assert state[normal]["project_id"] == str(project_id)
    assert orphan in state, "孤儿行被迁移删掉了：V227 不得删行"
    assert state[orphan]["project_id"] is None
    assert await _scalar(session, "SELECT count(*) FROM attachment_lineage") == total_before
    assert await project_column(session) == ("uuid", "YES")
    assert await index_columns(session) == INDEX
    assert await _scalar(session, _FK_COUNT_SQL) == 0
    orphans, nulls = await _scalar(session, _ORPHAN_COUNT_SQL), await _scalar(session, _NULL_COUNT_SQL)
    assert orphans >= 1 and nulls >= 1
    assert [m for m in notices if m.startswith("V227 ")] == [
        f"V227 attachment_lineage.project_id: 孤儿 {orphans} 行（附件已不存在，保持为空），project_id 仍为空 {nulls} 行"
    ], notices

    # 幂等：再重放一次，行与索引不变
    indexes_before = await _scalar(session, "SELECT count(*) FROM pg_indexes WHERE tablename = 'attachment_lineage'")
    await replay(session, V227)
    assert await lineage_state(session, [normal, orphan]) == state
    assert await index_columns(session) == INDEX
    assert await _scalar(session, "SELECT count(*) FROM pg_indexes WHERE tablename = 'attachment_lineage'") == (
        indexes_before)


async def test_ddl_replay_refuses_non_snapshot_database(monkeypatch):
    """重放迁移（含 DDL）先于任何语句校验库名：非 fh_snap_ 库直接失败，连会话都不碰（传 None 也不会走到执行）。"""
    shared = "postgresql+asyncpg://postgres:x@localhost:5432/audit_platform"
    monkeypatch.setenv("DATABASE_URL", shared)
    with pytest.raises(pytest.fail.Exception, match="只连快照库") as refused:
        await replay(None, R227)
    assert "当前库名 audit_platform" in str(refused.value)


async def test_null_project_rows_invisible_to_every_project(pg_tx):
    session = pg_tx
    project_a = await make_project(session, "v206_a")
    project_b = await make_project(session, "v206_b")
    attachment_id = await make_attachment(session, project_a)
    normal = await insert_lineage(session, attachment_id=attachment_id, target_ref=REF, project_id=project_a)
    await insert_lineage(session, attachment_id=uuid.uuid4(), target_ref=REF)  # 孤儿：附件不存在，project_id 空
    await insert_lineage(session, attachment_id=attachment_id, target_ref=REF)  # 迁移后旧代码写入：project_id 空
    service = UnifiedLineageService(session)
    seen_a = {row["id"] for row in await service._query_attachments(project_a, "wp_cell", REF)}
    seen_b = {row["id"] for row in await service._query_attachments(project_b, "wp_cell", REF)}
    assert seen_a == {str(normal)}, seen_a
    assert seen_b == set(), seen_b
