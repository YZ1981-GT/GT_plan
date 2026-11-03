"""V233/R233 精确 USCC 建项授权 PostgreSQL 契约。"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.database import engine as app_engine
from app.core.migration_runner import MigrationRunner

ROOT = Path(__file__).resolve().parents[1]
V227 = ROOT / "migrations" / "V233__project_creation_grants.sql"
R227 = ROOT / "migrations" / "R233__rollback_project_creation_grants.sql"
V228 = ROOT / "migrations" / "V234__project_creation_grant_uscc_checksum.sql"
R228 = ROOT / "migrations" / "R234__rollback_project_creation_grant_uscc_checksum.sql"
CODE = "91110000300000000G"
# 字符集合法、校验码错误：V227 回填会接受，统一校验 validate_uscc 会拒绝。
BAD_CHECKSUM_CODE = "91110000300000000H"


async def _run_sql(connection, path: Path) -> None:
    for statement in MigrationRunner._split_sql_statements(path.read_text(encoding="utf-8")):
        await connection.exec_driver_sql(statement)


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_v227_schema_backfill_idempotence_and_rollback():
    if app_engine.dialect.name != "postgresql":
        pytest.skip("需要 PostgreSQL")
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, pool_pre_ping=True)
    schema = f"creation_grant_{uuid.uuid4().hex[:12]}"
    manager_id, project_id = uuid.uuid4(), uuid.uuid4()
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                await connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", public')
                await connection.exec_driver_sql(
                    "CREATE TABLE users (id UUID PRIMARY KEY, role TEXT NOT NULL, "
                    "is_active BOOLEAN NOT NULL, is_deleted BOOLEAN NOT NULL)"
                )
                await connection.exec_driver_sql(
                    "CREATE TABLE projects (id UUID PRIMARY KEY, company_code TEXT, "
                    "is_deleted BOOLEAN NOT NULL)"
                )
                await connection.exec_driver_sql(
                    "CREATE TABLE project_users (id UUID PRIMARY KEY, project_id UUID NOT NULL, "
                    "user_id UUID NOT NULL, permission_level TEXT NOT NULL, is_deleted BOOLEAN NOT NULL)"
                )
                await connection.execute(
                    sa.text("INSERT INTO users VALUES (:uid, 'manager', true, false)"),
                    {"uid": manager_id},
                )
                await connection.execute(
                    sa.text("INSERT INTO projects VALUES (:pid, :code, false)"),
                    {"pid": project_id, "code": CODE},
                )
                await connection.execute(sa.text(
                    "INSERT INTO project_users VALUES (:puid, :pid, :uid, 'edit', false)"
                ), {"uid": manager_id, "pid": project_id, "puid": uuid.uuid4()})
                await _run_sql(connection, V227)
                await _run_sql(connection, V227)
                columns = {
                    row[0] for row in (await connection.execute(sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema=:schema AND table_name='project_creation_grants'"
                    ), {"schema": schema})).all()
                }
                assert {"grantee_user_id", "company_code", "version", "revoked_at"} <= columns
                indexes = {
                    row[0] for row in (await connection.execute(sa.text(
                        "SELECT indexname FROM pg_indexes WHERE schemaname=:schema "
                        "AND tablename='project_creation_grants'"
                    ), {"schema": schema})).all()
                }
                assert "uq_project_creation_grants_active" in indexes
                backfill = (await connection.execute(sa.text(
                    "SELECT grantee_user_id, company_code, source, version "
                    "FROM project_creation_grants"
                ))).one()
                assert backfill == (manager_id, CODE, "existing_project_edit_backfill", 1)
                assert await connection.scalar(sa.text(
                    "SELECT count(*) FROM project_creation_grants"
                )) == 1

                await _run_sql(connection, R227)
                assert await connection.scalar(sa.text(
                    "SELECT to_regclass(:name)"
                ), {"name": f"{schema}.project_creation_grants"}) is None
                assert await connection.scalar(sa.text(
                    "SELECT to_regclass(:name)"
                ), {"name": f"{schema}.users"}) is not None
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_locked_actor_role_ignores_request_identity_map_after_role_change():
    """请求已缓存的 User 不能掩盖另一事务已提交的角色降级。"""
    if app_engine.dialect.name != "postgresql":
        pytest.skip("需要 PostgreSQL")
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sqlalchemy.pool import NullPool

    from app.models.base import UserRole
    from app.models.core import User
    from app.models.project_creation_grant_models import ProjectCreationGrant
    from app.services.project_creation_grant_service import (
        ProjectCreationGrantStale,
        authorize_creation_codes,
        grant_many,
        lock_and_revalidate_creation_codes,
    )

    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    token = uuid.uuid4().hex[:16]
    manager_id = admin_id = None
    try:
        async with factory() as setup:
            manager = User(
                username=f"grant_role_{token}",
                email=f"grant_role_{token}@example.test",
                hashed_password="x",
                role=UserRole.manager,
            )
            administrator = User(
                username=f"grant_admin_{token}",
                email=f"grant_admin_{token}@example.test",
                hashed_password="x",
                role=UserRole.admin,
            )
            setup.add_all([manager, administrator])
            await setup.flush()
            manager_id, admin_id = manager.id, administrator.id
            await grant_many(
                setup,
                manager_user_id=manager.id,
                company_codes=[CODE],
                valid_until=None,
                reason="角色并发重验",
                actor=administrator,
            )
            await setup.commit()

        async with factory() as request:
            actor = await request.get(User, manager_id)
            assert actor is not None and actor.role == UserRole.manager
            snapshots = await authorize_creation_codes(
                request, actor, [CODE], entrypoint="identity_map_pg",
            )
            async with factory() as admin_change:
                await admin_change.execute(
                    sa.update(User)
                    .where(User.id == manager_id)
                    .values(role=UserRole.auditor)
                )
                await admin_change.commit()
            with pytest.raises(ProjectCreationGrantStale):
                await lock_and_revalidate_creation_codes(
                    request, actor, [CODE], expected_snapshots=snapshots,
                )
            await request.rollback()
    finally:
        try:
            if manager_id is not None or admin_id is not None:
                async with factory() as cleanup:
                    if manager_id is not None:
                        await cleanup.execute(sa.delete(ProjectCreationGrant).where(
                            ProjectCreationGrant.grantee_user_id == manager_id
                        ))
                    ids = [value for value in (manager_id, admin_id) if value is not None]
                    if ids:
                        await cleanup.execute(sa.delete(User).where(User.id.in_(ids)))
                    await cleanup.commit()
        finally:
            await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_batch_apply_rechecks_grant_expiry_after_waiting_for_year_lock():
    """grant 在年度锁等待期间到期时，apply 必须 stale 且零项目写入。"""
    if app_engine.dialect.name != "postgresql":
        pytest.skip("需要 PostgreSQL")
    import asyncio
    from datetime import datetime, timedelta, timezone

    from fastapi import HTTPException
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sqlalchemy.pool import NullPool

    from app.models.base import UserRole
    from app.models.batch_project_models import ProjectBatchImportPlan
    from app.models.core import Project, User
    from app.models.project_creation_grant_models import ProjectCreationGrant
    from app.services.batch_project_execution import apply_validation_plan
    from app.services.batch_project_workbook import ParsedRow
    from app.services.group_topology_lock import lock_topology_years
    from app.services.project_creation_grant_service import authorize_creation_codes, grant_many
    from app.services.uscc_validator import USCC_CHARSET, _CHAR_TO_VALUE, _WEIGHTS

    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    token = uuid.uuid4().hex
    numeric = int(token[:12], 16) % 10**15
    prefix = f"91{numeric:015d}"
    check = (31 - sum(
        _CHAR_TO_VALUE[value] * _WEIGHTS[index]
        for index, value in enumerate(prefix)
    ) % 31) % 31
    code = prefix + USCC_CHARSET[check]
    year = 2096
    manager_id = admin_id = plan_id = None
    try:
        async with factory() as setup:
            manager = User(
                username=f"grant_expiry_{token[:16]}",
                email=f"grant_expiry_{token[:16]}@example.test",
                hashed_password="x",
                role=UserRole.manager,
            )
            administrator = User(
                username=f"grant_expiry_admin_{token[:10]}",
                email=f"grant_expiry_admin_{token[:10]}@example.test",
                hashed_password="x",
                role=UserRole.admin,
            )
            setup.add_all([manager, administrator])
            await setup.flush()
            manager_id, admin_id = manager.id, administrator.id
            await grant_many(
                setup,
                manager_user_id=manager.id,
                company_codes=[code],
                valid_until=datetime.now(timezone.utc) + timedelta(seconds=1.2),
                reason="年度锁等待到期测试",
                actor=administrator,
            )
            snapshots = await authorize_creation_codes(
                setup, manager, [code], entrypoint="expiry_pg",
            )
            parsed = ParsedRow(
                row_number=2,
                client_name="【测试】授权等待到期",
                company_code=code,
                short_name="授权等待到期",
                audit_year=year,
                project_type="annual",
                accounting_standard="enterprise",
                report_scope="standalone",
                action="create",
            )
            plan = ProjectBatchImportPlan(
                actor_user_id=manager.id,
                mode="project",
                status="validated",
                file_name="【测试】授权等待到期.xlsx",
                file_sha256="d" * 64,
                request_hash="e" * 64,
                idempotency_key=f"grant-expiry-{token[:20]}",
                rows=[{"row": parsed.model_dump(mode="json"), "errors": []}],
                tree_preview=[],
                summary={"_plan_dependencies": {
                    "version": 1,
                    "template_root_project_id": None,
                    "inventory_entities": [{
                        "company_code": code,
                        "audit_year": year,
                        "projects": [],
                    }],
                    "read_project_ids": [],
                    "edit_project_ids": [],
                    "creation_grants": snapshots,
                }},
                warnings=[],
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
            setup.add(plan)
            await setup.commit()
            plan_id = plan.id

        async with factory() as holder:
            await lock_topology_years(holder, [year])

            async def run_apply():
                async with factory() as request:
                    actor = await request.get(User, manager_id)
                    try:
                        await apply_validation_plan(
                            request,
                            plan_id=plan_id,
                            actor=actor,
                            idempotency_key=f"grant-expiry-{token[:20]}",
                        )
                    except Exception as exc:
                        await request.rollback()
                        return exc
                    raise AssertionError("过期授权不应创建项目")

            pending = asyncio.create_task(run_apply())
            await asyncio.sleep(1.35)
            assert not pending.done()
            await holder.rollback()
            outcome = await asyncio.wait_for(pending, timeout=3)
            assert isinstance(outcome, HTTPException)
            assert outcome.status_code == 409
            assert outcome.detail["error_code"] == "BATCH_PLAN_STALE"

        async with factory() as verify:
            assert await verify.scalar(sa.select(sa.func.count()).select_from(Project).where(
                Project.company_code == code,
                Project.audit_year == year,
            )) == 0
    finally:
        try:
            async with factory() as cleanup:
                if plan_id is not None:
                    await cleanup.execute(sa.delete(ProjectBatchImportPlan).where(
                        ProjectBatchImportPlan.id == plan_id
                    ))
                if manager_id is not None:
                    await cleanup.execute(sa.delete(ProjectCreationGrant).where(
                        ProjectCreationGrant.grantee_user_id == manager_id
                    ))
                ids = [value for value in (manager_id, admin_id) if value is not None]
                if ids:
                    await cleanup.execute(sa.delete(User).where(User.id.in_(ids)))
                await cleanup.commit()
        finally:
            await engine.dispose()


def _uscc_samples() -> list[str]:
    """确定性样本：每个随机前缀配一个正确校验码和两个错误校验码。"""
    import random

    from app.services.uscc_validator import USCC_CHARSET, _CHAR_TO_VALUE, _WEIGHTS

    rng = random.Random(20261031)
    samples: list[str] = []
    for _ in range(120):
        prefix = "".join(rng.choice(USCC_CHARSET) for _ in range(17))
        total = sum(_CHAR_TO_VALUE[prefix[i]] * _WEIGHTS[i] for i in range(17))
        good = USCC_CHARSET[(31 - total % 31) % 31]
        wrong = [ch for ch in USCC_CHARSET if ch != good]
        samples.extend([prefix + good, prefix + rng.choice(wrong), prefix + rng.choice(wrong)])
    # 边界：非法字符、长度、小写、含 I/O/S/V/Z。
    samples += ["", "1", "9111000030000000", "91110000300000000g", "91110000300000000I",
                "91110000300000000Z", "O1110000300000000G", "911100003000000000G"]
    return samples


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_v228_matches_validator_cleans_invalid_backfill_and_constrains_active_rows():
    if app_engine.dialect.name != "postgresql":
        pytest.skip("需要 PostgreSQL")
    from app.services.uscc_validator import validate_uscc

    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, pool_pre_ping=True)
    schema = f"creation_grant_v228_{uuid.uuid4().hex[:10]}"
    manager_id = uuid.uuid4()
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                await connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", public')
                await connection.exec_driver_sql(
                    "CREATE TABLE users (id UUID PRIMARY KEY, role TEXT NOT NULL, "
                    "is_active BOOLEAN NOT NULL, is_deleted BOOLEAN NOT NULL)"
                )
                await connection.exec_driver_sql(
                    "CREATE TABLE projects (id UUID PRIMARY KEY, company_code TEXT, "
                    "is_deleted BOOLEAN NOT NULL)"
                )
                await connection.exec_driver_sql(
                    "CREATE TABLE project_users (id UUID PRIMARY KEY, project_id UUID NOT NULL, "
                    "user_id UUID NOT NULL, permission_level TEXT NOT NULL, is_deleted BOOLEAN NOT NULL)"
                )
                await connection.execute(
                    sa.text("INSERT INTO users VALUES (:uid, 'manager', true, false)"),
                    {"uid": manager_id},
                )
                for code in (CODE, BAD_CHECKSUM_CODE):
                    project_id = uuid.uuid4()
                    await connection.execute(
                        sa.text("INSERT INTO projects VALUES (:pid, :code, false)"),
                        {"pid": project_id, "code": code},
                    )
                    await connection.execute(sa.text(
                        "INSERT INTO project_users VALUES (:puid, :pid, :uid, 'edit', false)"
                    ), {"puid": uuid.uuid4(), "pid": project_id, "uid": manager_id})
                await _run_sql(connection, V227)
                # 前提：V227 确实把校验码错误的代码回填成了未撤销授权，否则本用例是空转。
                assert set((await connection.execute(sa.text(
                    "SELECT company_code FROM project_creation_grants WHERE is_deleted = false"
                ))).scalars().all()) == {CODE, BAD_CHECKSUM_CODE}

                await _run_sql(connection, V228)
                await _run_sql(connection, V228)

                samples = _uscc_samples()
                pg_values = (await connection.execute(sa.text(
                    "SELECT code, gt_is_valid_uscc(code) FROM unnest(CAST(:codes AS text[])) AS code"
                ), {"codes": samples})).all()
                mismatches = [
                    (code, pg_valid) for code, pg_valid in pg_values
                    if bool(pg_valid) != validate_uscc(code)[0]
                ]
                assert len(pg_values) == len(samples)
                assert mismatches == []
                assert sum(validate_uscc(code)[0] for code in samples) == 120

                rows = {
                    row.company_code: row for row in (await connection.execute(sa.text(
                        "SELECT company_code, is_deleted, revoked_at, deleted_at, version "
                        "FROM project_creation_grants"
                    ))).all()
                }
                assert rows[CODE].is_deleted is False and rows[CODE].version == 1
                bad = rows[BAD_CHECKSUM_CODE]
                assert bad.is_deleted is True and bad.revoked_at is not None
                assert bad.deleted_at is not None and bad.version == 2, "重跑 V228 不得再次递增版本"

                insert_sql = sa.text(
                    "INSERT INTO project_creation_grants "
                    "(id, grantee_user_id, company_code, reason, is_deleted) "
                    "VALUES (:id, :uid, :code, '约束测试', :deleted)"
                )
                savepoint = await connection.begin_nested()
                with pytest.raises(sa.exc.IntegrityError):
                    await connection.execute(insert_sql, {
                        "id": uuid.uuid4(), "uid": manager_id,
                        "code": "911100005000000008", "deleted": False,
                    })
                await savepoint.rollback()
                # 已撤销历史行允许保留错误代码（V228 清理结果本身就是这种行）。
                await connection.execute(insert_sql, {
                    "id": uuid.uuid4(), "uid": manager_id,
                    "code": "911100005000000008", "deleted": True,
                })

                constraint_sql = sa.text(
                    "SELECT count(*) FROM pg_constraint "
                    "WHERE conname = 'ck_project_creation_grants_code_checksum' "
                    "AND conrelid = to_regclass(:qualified)"
                )
                qualified = {"qualified": f'"{schema}".project_creation_grants'}
                # 只数隔离 schema 的表：共享库 public 表同样带这条约束，不能混入计数。
                assert await connection.scalar(constraint_sql, qualified) == 1
                await _run_sql(connection, R228)
                assert await connection.scalar(constraint_sql, qualified) == 0
                assert await connection.scalar(sa.text(
                    "SELECT to_regprocedure(:signature)"
                ), {"signature": f'"{schema}".gt_is_valid_uscc(text)'}) is None
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
