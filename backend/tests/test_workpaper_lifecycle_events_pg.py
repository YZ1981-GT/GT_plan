"""底稿生命周期领域事件 —— 真实 PostgreSQL（spec procedure-chain-hardening-and-java-contracts R18）。

每个用例一个外层事务，结束回滚、不落库。真库在下次全量重启前可能还没有 V207 的表（开发服热重载不跑迁移），
所以用例在事务里先执行 V207 本身（DDL 在 PG 里可回滚）：同时验证迁移脚本能在真库上执行。

- ORM 列 = 迁移建出来的列（类型与可空一致）；
- 移入 / 恢复同事务写事件，旧 JSON 照写；只追加触发器拒绝 UPDATE / DELETE；CHECK 拒绝未知事件类型；
- 事件表不存在时（DROP 在事务里，回滚恢复）：移入照常完成、事务没有被弄成 aborted。
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.core.migration_runner import MigrationRunner
from app.models.base import ProjectStatus, UserRole
from app.models.core import Project, User
from app.models.workpaper_lifecycle_models import WorkpaperLifecycleEvent
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus
from app.services import workpaper_recycle_service as svc

pytestmark = [pytest.mark.pg_only, pytest.mark.asyncio]

V207 = Path(__file__).resolve().parents[1] / "migrations" / "V207__workpaper_lifecycle_events.sql"


async def _open():
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    conn = await engine.connect()
    trans = await conn.begin()
    db = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    return engine, conn, trans, db


async def _close(engine, conn, trans, db):
    await db.close()
    await trans.rollback()
    await conn.close()
    await engine.dispose()


async def _apply_v207(db: AsyncSession) -> None:
    for stmt in MigrationRunner._split_sql_statements(V207.read_text(encoding="utf-8")):
        await db.execute(sa.text(stmt))


async def _world(db: AsyncSession):
    user = User(username=f"lce_{uuid.uuid4().hex[:10]}", email=f"{uuid.uuid4().hex[:10]}@t.example",
                hashed_password="x", role=UserRole.auditor, is_active=True)
    project = Project(name="【测试】生命周期事件真库", client_name="【测试】生命周期事件真库", status=ProjectStatus.execution)
    db.add_all([user, project])
    await db.flush()
    for code in ("E1", "E2"):
        idx = WpIndex(project_id=project.id, wp_code=code, wp_name=f"底稿{code}", audit_cycle="E",
                      status=WpStatus.not_started)
        db.add(idx)
        await db.flush()
        db.add(WorkingPaper(project_id=project.id, wp_index_id=idx.id, file_path="", file_version=1,
                            source_type=WpSourceType.template))
    await db.flush()
    return user, project


async def test_orm_columns_match_v207_ddl():
    engine, conn, trans, db = await _open()
    try:
        await _apply_v207(db)
        rows = (await db.execute(sa.text(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_name = 'workpaper_lifecycle_events' ORDER BY column_name"))).all()
        db_cols = {r[0]: (r[1], r[2] == "YES") for r in rows}
        orm_cols = {c.name: c.nullable for c in WorkpaperLifecycleEvent.__table__.columns}
        assert set(db_cols) == set(orm_cols), (sorted(set(db_cols) ^ set(orm_cols)))
        assert {k: v[1] for k, v in db_cols.items()} == orm_cols, "可空性逐列一致"
        assert db_cols["working_paper_ids"][0] == "jsonb" and db_cols["created_at"][0] == "timestamp with time zone"
    finally:
        await _close(engine, conn, trans, db)


async def test_events_written_append_only_and_checked():
    engine, conn, trans, db = await _open()
    try:
        await _apply_v207(db)
        user, project = await _world(db)
        await svc.move_to_recycle_bin(db, project.id, ["E1", "E2"], kind="trim", reason="程序裁剪：E1",
                                      actor_user_id=user.id, trim_codes={"E1": ["E1"]}, request_id="req-pg")
        await svc.restore_from_recycle_bin(db, project.id, ["E2"], kind="trim", reason="恢复执行",
                                           actor_user_id=user.id, request_id="req-pg-2")
        rows = (await db.execute(sa.text(
            "SELECT wp_code, event_type, kind, request_id, trim_codes FROM workpaper_lifecycle_events "
            "WHERE project_id = :p ORDER BY created_at, wp_code"), {"p": project.id})).all()
        assert [tuple(r[:4]) for r in rows] == [
            ("E1", "recycled", "trim", "req-pg"), ("E2", "recycled", "trim", "req-pg"),
            ("E2", "restored", "trim", "req-pg-2")]
        assert rows[0][4] == ["E1"]
        lineage = (await db.execute(sa.text(
            "SELECT cross_ref_codes FROM wp_index WHERE project_id = :p AND wp_code = 'E2'"),
            {"p": project.id})).scalar_one()
        assert [x["action"] for x in lineage[svc.RECYCLE_LINEAGE_KEY]] == ["recycled", "restored"], "旧 JSON 照写"
        actors = await svc.latest_recycle_actors(db, [r for (r,) in (await db.execute(sa.text(
            "SELECT id FROM wp_index WHERE project_id = :p ORDER BY wp_code"), {"p": project.id})).all()])
        assert list(actors.values()) == [str(user.id)], "E1 最近是移入；E2 最近是恢复 ⇒ 不在结果"

        for sql in ("UPDATE workpaper_lifecycle_events SET reason = 'x' WHERE project_id = :p",
                    "DELETE FROM workpaper_lifecycle_events WHERE project_id = :p"):
            with pytest.raises(DBAPIError, match="append-only"):
                async with db.begin_nested():
                    await db.execute(sa.text(sql), {"p": project.id})
        with pytest.raises(DBAPIError, match="ck_wp_lifecycle_event_type"):
            async with db.begin_nested():
                await db.execute(sa.text(
                    "INSERT INTO workpaper_lifecycle_events (project_id, wp_index_id, wp_code, event_type) "
                    "VALUES (:p, gen_random_uuid(), 'X', 'purged')"), {"p": project.id})
        assert (await db.execute(sa.text("SELECT count(*) FROM workpaper_lifecycle_events WHERE project_id = :p"),
                                 {"p": project.id})).scalar_one() == 3, "被拒的改动都回滚到保存点，事务仍可用"
    finally:
        await _close(engine, conn, trans, db)


async def test_missing_events_table_degrades_and_keeps_transaction_alive():
    engine, conn, trans, db = await _open()
    try:
        await db.execute(sa.text("DROP TABLE IF EXISTS workpaper_lifecycle_events"))  # 事务内，回滚即恢复
        user, project = await _world(db)
        moved = await svc.move_to_recycle_bin(db, project.id, ["E1"], kind="manual", reason="手工删除",
                                              actor_user_id=user.id)
        assert moved == ["E1"]
        # 事务没有 aborted：后续查询照常；回收站读删除人回退 JSON
        e1 = (await db.execute(sa.select(WpIndex.id, WpIndex.is_deleted)
                               .where(WpIndex.project_id == project.id, WpIndex.wp_code == "E1"))).one()
        assert e1.is_deleted is True
        assert await svc.latest_recycle_actors(db, [e1.id]) == {}
        # 读事件失败也只回滚保存点：回收站列表随后还要查删除人姓名，事务必须仍可用
        assert (await db.execute(sa.text("SELECT 1"))).scalar_one() == 1
    finally:
        await _close(engine, conn, trans, db)
