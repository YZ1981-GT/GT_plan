"""V220/R220 批量建项持久计划 PostgreSQL 契约。"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.core.database import engine
from app.core.migration_runner import MigrationRunner

ROOT = Path(__file__).resolve().parents[1]
V220 = ROOT / "migrations" / "V220__project_batch_import_plans.sql"
R220 = ROOT / "migrations" / "R220__rollback_project_batch_import_plans.sql"


async def _run_sql(connection, path: Path) -> None:
    for statement in MigrationRunner._split_sql_statements(path.read_text(encoding="utf-8")):
        await connection.exec_driver_sql(statement)


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_v220_schema_idempotent_and_r220_removes_only_plan_table():
    if engine.dialect.name != "postgresql":
        pytest.skip("需要 PostgreSQL")
    schema = f"batch_plan_{uuid.uuid4().hex[:12]}"
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            await connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            await connection.exec_driver_sql("CREATE TABLE users (id UUID PRIMARY KEY)")
            await _run_sql(connection, V220)
            await _run_sql(connection, V220)
            columns = {
                row[0]: row[1]
                for row in (await connection.execute(sa.text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema=:schema AND table_name='project_batch_import_plans'"
                ), {"schema": schema})).all()
            }
            assert columns["actor_user_id"] == "uuid"
            assert columns["rows"] == "jsonb"
            assert columns["receipt"] == "jsonb"
            indexes = {
                row[0] for row in (await connection.execute(sa.text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname=:schema "
                    "AND tablename='project_batch_import_plans'"
                ), {"schema": schema})).all()
            }
            assert "uq_project_batch_plans_actor_key" in indexes
            actor_id, first_id, second_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            await connection.execute(sa.text("INSERT INTO users(id) VALUES (:id)"), {"id": actor_id})
            insert = sa.text(
                "INSERT INTO project_batch_import_plans "
                "(id,actor_user_id,mode,status,file_name,file_sha256,request_hash,idempotency_key,expires_at) "
                "VALUES (:id,:actor,'project','validated','x.xlsx',:digest,:digest,'same-key',now()+interval '1 hour')"
            )
            await connection.execute(insert, {"id": first_id, "actor": actor_id, "digest": "a" * 64})
            savepoint = await connection.begin_nested()
            with pytest.raises(sa.exc.DBAPIError):
                await connection.execute(insert, {"id": second_id, "actor": actor_id, "digest": "b" * 64})
            await savepoint.rollback()
            assert await connection.scalar(sa.text(
                "SELECT count(*) FROM project_batch_import_plans WHERE actor_user_id=:actor"
            ), {"actor": actor_id}) == 1
            await _run_sql(connection, R220)
            exists = await connection.scalar(sa.text(
                "SELECT to_regclass(:qualified)"
            ), {"qualified": f"{schema}.project_batch_import_plans"})
            assert exists is None
            users_exists = await connection.scalar(sa.text(
                "SELECT to_regclass(:qualified)"
            ), {"qualified": f"{schema}.users"})
            assert users_exists is not None
        finally:
            await transaction.rollback()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_persisted_plan_pg_lock_makes_status_wait_and_apply_replays_once():
    """PG MVCC 下 status 必须等计划锁释放，双 apply 只能得到一份首次回执。"""
    if engine.dialect.name != "postgresql":
        pytest.skip("需要 PostgreSQL")

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.config import settings
    from app.models.base import UserRole
    from app.models.batch_project_models import ProjectBatchImportPlan
    from app.models.core import User
    from app.services.batch_project_execution import (
        apply_validation_plan,
        get_owned_plan,
        get_readable_plan,
        plan_status_response,
    )

    database_url = settings.DATABASE_URL
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    # 不复用模块级 engine：pytest 每个 async test 可能在不同事件循环，复用会把 asyncpg
    # 连接绑定到已关闭 loop，进而把真正的锁语义测试伪装成基础设施失败。
    test_engine = create_async_engine(database_url, pool_pre_ping=True)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    token = uuid.uuid4().hex
    plan_ids: list[uuid.UUID] = []
    actor_id: uuid.UUID | None = None
    try:
        async with factory() as session:
            actor = User(
                username=f"batch_pg_{token[:16]}",
                email=f"batch_pg_{token[:16]}@example.test",
                hashed_password="x",
                role=UserRole.admin,
            )
            session.add(actor)
            await session.flush()
            actor_id = actor.id
            for suffix in ("status", "apply"):
                plan = ProjectBatchImportPlan(
                    actor_user_id=actor.id,
                    mode="project",
                    status="validated",
                    file_name="【测试】批量建项.xlsx",
                    file_sha256="a" * 64,
                    request_hash="b" * 64,
                    idempotency_key=f"pg-{suffix}-{token[:20]}",
                    rows=[],
                    tree_preview=[],
                    summary={
                        "_plan_dependencies": {
                            "version": 1,
                            "inventory_entities": [],
                            "read_project_ids": [],
                            "edit_project_ids": [],
                        },
                    },
                    warnings=[],
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                )
                session.add(plan)
                await session.flush()
                plan_ids.append(plan.id)
            await session.commit()

        # 真实 PG 行锁：第二个会话的 status 不能读取 apply 事务未提交前的旧 validated 快照。
        async with factory() as writer:
            locked = await get_owned_plan(writer, plan_ids[0], actor, for_update=True)
            locked.status = "applying"
            await writer.flush()

            async def read_status() -> str:
                async with factory() as reader:
                    visible = await get_readable_plan(reader, plan_ids[0], actor, for_update=True)
                    return plan_status_response(visible).status

            waiter = asyncio.create_task(read_status())
            await asyncio.sleep(0.12)
            assert not waiter.done()
            locked.status = "applied"
            locked.receipt = {"success_count": 0, "fail_count": 0}
            await writer.commit()
            assert await waiter == "applied"

        async def apply_once() -> bool:
            async with factory() as session:
                result = await apply_validation_plan(
                    session,
                    plan_id=plan_ids[1],
                    actor=actor,
                    idempotency_key=f"pg-apply-{token[:20]}",
                )
                await session.commit()
                return result.idempotent

        first, second = await asyncio.gather(apply_once(), apply_once())
        assert sorted((first, second)) == [False, True]
    finally:
        try:
            if plan_ids or actor_id is not None:
                async with factory() as cleanup:
                    if plan_ids:
                        await cleanup.execute(sa.delete(ProjectBatchImportPlan).where(
                            ProjectBatchImportPlan.id.in_(plan_ids)
                        ))
                    if actor_id is not None:
                        await cleanup.execute(sa.delete(User).where(User.id == actor_id))
                    await cleanup.commit()
        finally:
            await test_engine.dispose()
