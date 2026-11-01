"""V220/R220 批量建项持久计划 PostgreSQL 契约。"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi import HTTPException

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
    from app.models.base import PermissionLevel, ProjectUserRole, UserRole
    from app.models.batch_project_models import ProjectBatchImportPlan
    from app.models.core import Project, ProjectUser, User
    from app.services.batch_project_workbook import ParsedRow
    from app.services.batch_project_execution import (
        apply_validation_plan,
        get_owned_plan,
        get_readable_plan,
        plan_status_response,
        _lock_plan_memberships,
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
    locked_member_id: uuid.UUID | None = None
    locked_project_id: uuid.UUID | None = None
    locked_manager_id: uuid.UUID | None = None
    concurrent_company_code: str | None = None
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

        # 执行前取得成员行共享锁：撤权要么先完成并让权限检查失败，要么等待当前批次结束。
        async with factory() as session:
            manager = User(
                username=f"batch_lock_{token[:16]}",
                email=f"batch_lock_{token[:16]}@example.test",
                hashed_password="x",
                role=UserRole.manager,
            )
            project = Project(
                name="【测试】批量成员锁",
                client_name="【测试】批量成员锁",
                company_code=f"LOCK{token[:12]}",
                audit_year=2052,
                report_scope="standalone",
            )
            session.add_all([manager, project])
            await session.flush()
            member = ProjectUser(
                project_id=project.id,
                user_id=manager.id,
                role=ProjectUserRole.manager,
                permission_level=PermissionLevel.edit,
            )
            session.add(member)
            await session.flush()
            locked_manager_id = manager.id
            locked_project_id = project.id
            locked_member_id = member.id
            await session.commit()

        async with factory() as locker:
            await _lock_plan_memberships(
                locker,
                dependencies={
                    "read_project_ids": [str(locked_project_id)],
                    "edit_project_ids": [str(locked_project_id)],
                },
                actor=manager,
            )

            async def revoke_membership() -> None:
                async with factory() as revoker:
                    await revoker.execute(
                        sa.update(ProjectUser)
                        .where(ProjectUser.id == locked_member_id)
                        .values(is_deleted=True)
                    )
                    await revoker.commit()

            revoker = asyncio.create_task(revoke_membership())
            await asyncio.sleep(0.12)
            assert not revoker.done()
            await locker.commit()
            await asyncio.wait_for(revoker, timeout=2)

        # 两份不同计划从同一空库存出发时，唯一索引仍是最后防线；后一份必须得到可重校验的
        # 竞争失败，绝不能静默复用对方刚创建的项目。
        from app.services.uscc_validator import USCC_CHARSET, _CHAR_TO_VALUE, _WEIGHTS, validate_uscc
        prefix = f"91110000{token[:9].upper()}"
        check_digit = (31 - sum(_CHAR_TO_VALUE[value] * _WEIGHTS[index] for index, value in enumerate(prefix)) % 31) % 31
        concurrent_company_code = prefix + USCC_CHARSET[check_digit]
        assert validate_uscc(concurrent_company_code)[0]
        concurrent_year = 2053
        concurrent_row = ParsedRow(
            row_number=2,
            client_name="【测试】并发唯一键",
            company_code=concurrent_company_code,
            short_name="并发唯一",
            audit_year=concurrent_year,
            project_type="annual",
            accounting_standard="enterprise",
            report_scope="standalone",
            action="create",
        )
        dependencies = {
            "version": 1,
            "template_root_project_id": None,
            "inventory_entities": [{
                "company_code": concurrent_company_code,
                "audit_year": concurrent_year,
                "projects": [],
            }],
            "read_project_ids": [],
            "edit_project_ids": [],
            "creation_grants": [],
        }
        async with factory() as session:
            for suffix in ("first", "second"):
                plan = ProjectBatchImportPlan(
                    actor_user_id=actor.id,
                    mode="project",
                    status="validated",
                    file_name="【测试】并发建项.xlsx",
                    file_sha256="c" * 64,
                    request_hash=f"{suffix[0]}" * 64,
                    idempotency_key=f"pg-unique-{suffix}-{token[:16]}",
                    rows=[{"row": concurrent_row.model_dump(mode="json"), "errors": []}],
                    tree_preview=[],
                    summary={"_plan_dependencies": dependencies},
                    warnings=[],
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                )
                session.add(plan)
                await session.flush()
                plan_ids.append(plan.id)
            await session.commit()

        start_barrier = asyncio.Barrier(2)

        async def apply_unique(plan_id: uuid.UUID, suffix: str):
            async with factory() as session:
                await start_barrier.wait()
                try:
                    result = await apply_validation_plan(
                        session,
                        plan_id=plan_id,
                        actor=actor,
                        idempotency_key=f"pg-unique-{suffix}-{token[:16]}",
                    )
                    await session.commit()
                    return result
                except Exception as exc:
                    await session.rollback()
                    return exc

        unique_outcomes = await asyncio.wait_for(
            asyncio.gather(
                apply_unique(plan_ids[-2], "first"),
                apply_unique(plan_ids[-1], "second"),
            ),
            timeout=8,
        )
        successes = [value for value in unique_outcomes if not isinstance(value, Exception)]
        failures = [value for value in unique_outcomes if isinstance(value, Exception)]
        assert len(successes) == 1
        assert len(failures) == 1
        assert isinstance(failures[0], HTTPException)
        assert failures[0].status_code == 409
        assert failures[0].detail["error_code"] == "BATCH_PLAN_STALE"
    finally:
        try:
            if plan_ids or actor_id is not None or locked_member_id is not None or concurrent_company_code:
                async with factory() as cleanup:
                    if plan_ids:
                        await cleanup.execute(sa.delete(ProjectBatchImportPlan).where(
                            ProjectBatchImportPlan.id.in_(plan_ids)
                        ))
                    if concurrent_company_code:
                        await cleanup.execute(sa.delete(Project).where(
                            Project.company_code == concurrent_company_code,
                            Project.audit_year == 2053,
                        ))
                    if locked_member_id is not None:
                        await cleanup.execute(sa.delete(ProjectUser).where(ProjectUser.id == locked_member_id))
                    if locked_project_id is not None:
                        await cleanup.execute(sa.delete(Project).where(Project.id == locked_project_id))
                    if locked_manager_id is not None:
                        await cleanup.execute(sa.delete(User).where(User.id == locked_manager_id))
                    if actor_id is not None:
                        await cleanup.execute(sa.delete(User).where(User.id == actor_id))
                    await cleanup.commit()
        finally:
            await test_engine.dispose()
