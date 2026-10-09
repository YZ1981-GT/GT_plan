"""任务15 P0-P2：合并模块真实 HTTP/ORM 收尾守卫。

本文件只验证真实 ASGI 路由、真实 SQLAlchemy ORM 行和实际 service 编排；
不以 mock service 返回值作为业务通过证据。worker 的下一层依赖可以故障注入，
但被测 worker、router、snapshot service 本身始终走生产实现。
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型与 SQLite 方言补丁
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, ProjectStatus, UserRole
from app.models.consol_note_data_models import ConsolNoteData
from app.models.consolidation_models import AccountCategory, ConsolScope, ConsolTrial
from app.models.core import Project, User
from app.models.report_models import FinancialReport, FinancialReportType

Y = 2025


@pytest_asyncio.fixture
async def task15_factory():
    """每个测试独立重建完整 ORM metadata，避免跨测试数据污染。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@dataclass
class _Actor:
    id: uuid.UUID
    username: str
    role: UserRole = UserRole.admin
    is_active: bool = True
    is_deleted: bool = False


def _admin() -> _Actor:
    actor_id = uuid.uuid4()
    return _Actor(actor_id, f"task15_{actor_id.hex[:8]}")


def _project(label: str) -> Project:
    return Project(
        id=uuid.uuid4(),
        name=f"任务15-{label}",
        client_name=f"任务15-{label}",
        status=ProjectStatus.execution,
        audit_year=Y,
    )


def _app_for(factory, *routers, user: _Actor | None = None) -> FastAPI:
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    actor = user or _admin()

    async def override_db():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: actor
    return app


async def _persist_projects(factory, *projects: Project) -> None:
    async with factory() as db:
        db.add_all(projects)
        await db.commit()


@pytest.mark.asyncio
async def test_scope_http_uses_path_project_and_hides_soft_deleted_rows(task15_factory):
    """scope CRUD 必须以 URL 项目为唯一归属，软删对象不可再读/改/删。"""
    from app.routers.consol_scope import router

    project_a = _project("A")
    project_b = _project("B")
    await _persist_projects(task15_factory, project_a, project_b)
    app = _app_for(task15_factory, router)
    body = {
        "project_id": str(project_b.id),
        "year": Y,
        "company_code": "A-001",
        "company_name": "路径项目A",
        "company_type": "parent",
        "ownership_ratio": "100",
        "is_included": True,
        "scope_change_type": "none",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/consolidation/scope",
            params={"project_id": str(project_a.id)},
            json=body,
        )
        assert created.status_code == 201, created.text
        scope_id = created.json()["id"]
        assert created.json()["project_id"] == str(project_a.id)

        listed_a = await client.get(
            "/api/consolidation/scope",
            params={"project_id": str(project_a.id), "year": Y},
        )
        listed_b = await client.get(
            "/api/consolidation/scope",
            params={"project_id": str(project_b.id), "year": Y},
        )
        assert listed_a.status_code == listed_b.status_code == 200
        assert [row["id"] for row in listed_a.json()] == [scope_id]
        assert listed_b.json() == []

        cross_update = await client.put(
            f"/api/consolidation/scope/{scope_id}",
            params={"project_id": str(project_b.id)},
            json={"is_included": False},
        )
        cross_delete = await client.delete(
            f"/api/consolidation/scope/{scope_id}",
            params={"project_id": str(project_b.id)},
        )
        assert cross_update.status_code == cross_delete.status_code == 404

        deleted = await client.delete(
            f"/api/consolidation/scope/{scope_id}",
            params={"project_id": str(project_a.id)},
        )
        assert deleted.status_code == 204
        assert (await client.get(
            "/api/consolidation/scope",
            params={"project_id": str(project_a.id), "year": Y},
        )).json() == []
        assert (await client.put(
            f"/api/consolidation/scope/{scope_id}",
            params={"project_id": str(project_a.id)},
            json={"is_included": False},
        )).status_code == 404
        assert (await client.delete(
            f"/api/consolidation/scope/{scope_id}",
            params={"project_id": str(project_a.id)},
        )).status_code == 404

    async with task15_factory() as db:
        row = await db.get(ConsolScope, uuid.UUID(scope_id))
        assert row is not None and row.project_id == project_a.id and row.is_deleted is True


@pytest.mark.asyncio
async def test_refresh_status_binds_job_to_project_and_year(task15_factory):
    """refresh-status 不能只凭 job_id 读取其他项目或年度的任务状态。"""
    from app.routers.consol_refresh import router
    from app.services.consol_refresh_job_service import _JOBS, create_job

    project_a = _project("刷新A")
    project_b = _project("刷新B")
    await _persist_projects(task15_factory, project_a, project_b)
    job = create_job(project_a.id, Y)
    app = _app_for(task15_factory, router)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            own = await client.get(
                f"/api/consolidation/{project_a.id}/{Y}/refresh-status/{job.job_id}"
            )
            cross_project = await client.get(
                f"/api/consolidation/{project_b.id}/{Y}/refresh-status/{job.job_id}"
            )
            cross_year = await client.get(
                f"/api/consolidation/{project_a.id}/{Y + 1}/refresh-status/{job.job_id}"
            )

        assert own.status_code == 200
        assert own.json()["job_id"] == job.job_id
        assert cross_project.status_code == 404
        assert cross_year.status_code == 404
    finally:
        _JOBS.pop(job.job_id, None)


@pytest.mark.asyncio
async def test_refresh_worker_uses_independent_session_and_commits_report_step(task15_factory):
    """真实 worker/cascade 使用独立 session，报表步骤 flush 后必须跨 session 持久化。"""
    from app.models.report_models import FinancialReport, FinancialReportType
    from app.services.consol_cascade_refresh_service import ReconciliationResult
    from app.services.consol_refresh_job_service import (
        SSE_COMPLETED,
        _JOBS,
        create_job,
        run_refresh_job,
    )
    from app.services.consol_tree_service import TreeNode

    project = _project("worker")
    await _persist_projects(task15_factory, project)
    job = create_job(project.id, Y)

    async def fake_report(db, project_id, year, *args, **kwargs):
        db.add(FinancialReport(
            project_id=project_id,
            year=year,
            report_type=FinancialReportType.balance_sheet,
            row_code="TASK15-REPORT",
            row_name="任务15报表提交守卫",
            current_period_amount=Decimal("123.45"),
        ))
        await db.flush()
        return {}

    async def fake_tree(db, project_id):
        return TreeNode(
            project_id=project_id,
            company_code="TASK15",
            company_name="任务15测试集团",
            parent_company_code=None,
            ultimate_company_code="TASK15",
            consol_level=1,
        )

    async def fake_reconcile(db, project_id, year):
        return ReconciliationResult(
            is_reconciled=True,
            tolerance=Decimal("0.01"),
        )

    with patch("app.services.consol_refresh_job_service.async_session_factory", task15_factory), \
         patch("app.services.consol_refresh_job_service.event_bus.broadcast_raw") as broadcast, \
         patch("app.services.consol_cascade_refresh_service.build_tree", new=fake_tree), \
         patch("app.services.consol_cascade_refresh_service.recalc_full", new=AsyncMock()), \
         patch("app.services.consol_cascade_refresh_service.recalculate_trial", new=AsyncMock()), \
         patch("app.services.consol_cascade_refresh_service.reconcile_worksheet_vs_trial", new=fake_reconcile), \
         patch("app.services.consol_cascade_refresh_service.generate_consol_reports_sync", new=fake_report):
        await run_refresh_job(job.job_id, str(project.id), Y)

    try:
        assert job.status == "completed"
        assert "report" in job.steps_completed
        events = [call.args[0] for call in broadcast.call_args_list]
        assert SSE_COMPLETED in events
        completed = [call.args[1] for call in broadcast.call_args_list if call.args[0] == SSE_COMPLETED]
        assert completed and completed[-1]["job_id"] == job.job_id
        assert completed[-1]["project_id"] == str(project.id)

        async with task15_factory() as db:
            report = (await db.execute(sa.select(FinancialReport).where(
                FinancialReport.project_id == project.id,
                FinancialReport.year == Y,
                FinancialReport.row_code == "TASK15-REPORT",
            ))).scalar_one_or_none()
        assert report is not None, "报表步骤只 flush 不能在 worker session 退出时丢失"
        assert report.current_period_amount == Decimal("123.45")
    finally:
        _JOBS.pop(job.job_id, None)


@pytest.mark.asyncio
async def test_refresh_worker_failure_marks_failed_and_broadcasts_error(task15_factory):
    """worker 整体异常必须进入 failed，并广播带 job_id 的错误事件。"""
    from app.services.consol_refresh_job_service import (
        SSE_ERROR,
        _JOBS,
        create_job,
        run_refresh_job,
    )

    project = _project("worker-failed")
    await _persist_projects(task15_factory, project)
    job = create_job(project.id, Y)

    with patch("app.services.consol_refresh_job_service.async_session_factory", task15_factory), \
         patch("app.services.consol_refresh_job_service.refresh_all", new=AsyncMock(
             side_effect=RuntimeError("任务15故障注入")
         )), \
         patch("app.services.consol_refresh_job_service.event_bus.broadcast_raw") as broadcast:
        await run_refresh_job(job.job_id, str(project.id), Y)

    try:
        assert job.status == "failed"
        assert job.errors and "任务15故障注入" in job.errors[0]["error"]
        errors = [call.args[1] for call in broadcast.call_args_list if call.args[0] == SSE_ERROR]
        assert errors and errors[-1]["job_id"] == job.job_id
        assert errors[-1]["project_id"] == str(project.id)
        assert errors[-1]["status"] == "failed"
    finally:
        _JOBS.pop(job.job_id, None)


@pytest.mark.asyncio
async def test_snapshot_http_orm_create_restore_compare_and_project_isolation(task15_factory):
    """快照通过真实 HTTP/ORM 完成创建、还原、对比，并校验项目归属。"""
    from app.models.consolidation_models import AccountCategory, ConsolTrial
    from app.models.core import User
    from app.routers.report_trace import router

    actor = _admin()
    project_a = _project("快照A")
    project_b = _project("快照B")
    await _persist_projects(task15_factory, project_a, project_b)
    async with task15_factory() as db:
        db.add(User(
            id=actor.id,
            username=actor.username,
            email=f"{actor.id.hex}@task15.local",
            hashed_password="x",
            role=UserRole.admin,
        ))
        trial = ConsolTrial(
            project_id=project_a.id,
            year=Y,
            standard_account_code="1001",
            account_name="库存现金",
            account_category=AccountCategory.asset,
            individual_sum=Decimal("100.00"),
            consol_adjustment=Decimal("0.00"),
            consol_elimination=Decimal("0.00"),
            consol_amount=Decimal("100.00"),
            consolidation_breakdown={"by_company": []},
        )
        db.add(trial)
        await db.commit()
        trial_id = trial.id

    app = _app_for(task15_factory, router, user=actor)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            f"/api/consolidation/{project_a.id}/snapshots",
            params={"year": Y, "reason": "manual"},
        )
        assert created.status_code == 200, created.text
        snapshot_id = created.json()["id"]

        restored = await client.get(
            f"/api/consolidation/{project_a.id}/snapshots/{snapshot_id}/restore"
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["hash_valid"] is True
        assert restored.json()["data"]["trial"][0]["consol_amount"] == "100.00"

        cross_project = await client.get(
            f"/api/consolidation/{project_b.id}/snapshots/{snapshot_id}/restore"
        )
        assert cross_project.status_code == 404

    async with task15_factory() as db:
        current = await db.get(ConsolTrial, trial_id)
        assert current is not None
        current.consol_amount = Decimal("125.00")
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        compared = await client.get(
            f"/api/consolidation/{project_a.id}/snapshots/{snapshot_id}/compare"
        )
    assert compared.status_code == 200, compared.text
    assert compared.json()["hash_valid"] is True
    assert compared.json()["changed_count"] == 1
    assert compared.json()["by_account"] == [{
        "account_code": "1001",
        "snapshot_amount": "100.00",
        "current_amount": "125.00",
        "changed": True,
    }]


def test_snapshot_migration_declares_runtime_table():
    """V174/R174、ORM 与运行时表的列集、可空性和索引必须三层一致。"""
    from app.models.phase10_models import ConsolSnapshot

    migration_dir = Path(__file__).resolve().parents[1] / "migrations"
    v174 = migration_dir / "V174__consol_snapshots.sql"
    r174 = migration_dir / "R174__rollback_consol_snapshots.sql"
    v175 = migration_dir / "V175__repair_consol_snapshots_schema.sql"
    r175 = migration_dir / "R175__rollback_repair_consol_snapshots_schema.sql"
    assert v174.is_file() and r174.is_file() and v175.is_file() and r175.is_file()
    assert [p.name for p in migration_dir.glob("V*.sql") if re.match(r"^V0*174__", p.name)] == [v174.name]
    assert [p.name for p in migration_dir.glob("V*.sql") if re.match(r"^V0*175__", p.name)] == [v175.name]
    ddl = re.sub(r"--[^\n]*", "", v174.read_text(encoding="utf-8"))
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+consol_snapshots\b",
        ddl,
        flags=re.IGNORECASE,
    ), "缺少 consol_snapshots 的运行时迁移 DDL"

    body_match = re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+consol_snapshots\s*\((.*?)\);",
        ddl,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert body_match, "V174 建表体缺失"
    ddl_columns = {}
    for segment in body_match.group(1).splitlines():
        match = re.match(r"\s*([a-z_][a-z0-9_]*)\s+[^,]+", segment, flags=re.IGNORECASE)
        if match and match.group(1).lower() not in {"primary", "foreign", "constraint"}:
            ddl_columns[match.group(1)] = "NOT NULL" in segment.upper() or "PRIMARY KEY" in segment.upper()
    orm_columns = {column.name: not column.nullable for column in ConsolSnapshot.__table__.columns}
    assert ddl_columns == orm_columns
    assert str(ConsolSnapshot.__table__.c.id.server_default.arg) == "gen_random_uuid()"
    assert ConsolSnapshot.__table__.c.created_at.type.timezone is True
    assert "now()" in str(ConsolSnapshot.__table__.c.created_at.server_default.arg).lower()

    repair = re.sub(r"--[^\n]*", "", v175.read_text(encoding="utf-8"))
    assert re.search(
        r"ALTER\s+TABLE\s+consol_snapshots\s+ALTER\s+COLUMN\s+id\s+SET\s+DEFAULT\s+gen_random_uuid\(\)",
        repair,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert re.search(r"ALTER\s+COLUMN\s+created_at\s+TYPE\s+TIMESTAMPTZ", repair, re.IGNORECASE)
    assert re.search(r"ALTER\s+COLUMN\s+created_at\s+SET\s+DEFAULT\s+now\(\)", repair, re.IGNORECASE)

    repair_rollback = re.sub(r"--[^\n]*", "", r175.read_text(encoding="utf-8"))
    assert re.search(r"ALTER\s+COLUMN\s+id\s+DROP\s+DEFAULT", repair_rollback, re.IGNORECASE)
    assert re.search(r"ALTER\s+COLUMN\s+created_at\s+TYPE\s+TIMESTAMP", repair_rollback, re.IGNORECASE)

    index_match = re.search(
        r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_consol_snapshots_project_year_created\s+"
        r"ON\s+consol_snapshots\s*\(([^)]*)\)",
        ddl,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert index_match
    orm_index = ConsolSnapshot.__table__.indexes
    index = next((item for item in orm_index if item.name == "idx_consol_snapshots_project_year_created"), None)
    assert index is not None
    ddl_index_columns = tuple(value.strip() for value in index_match.group(1).split(","))
    orm_index_columns = tuple(str(column).split(".")[-1] for column in index.expressions)
    assert ddl_index_columns == orm_index_columns == ("project_id", "year", "created_at DESC")

    rollback = re.sub(r"--[^\n]*", "", r174.read_text(encoding="utf-8"))
    assert re.search(r"DROP\s+INDEX\s+IF\s+EXISTS\s+idx_consol_snapshots_project_year_created", rollback, re.IGNORECASE)
    assert re.search(r"DROP\s+TABLE\s+IF\s+EXISTS\s+consol_snapshots", rollback, re.IGNORECASE)


@pytest.mark.asyncio
async def test_note_manual_save_respects_consol_lock(task15_factory):
    """附注手工 PUT 与按公式填入一样，合并锁定后必须返回 423。"""
    from app.routers.consol_note_sections import router

    project = _project("附注锁")
    await _persist_projects(task15_factory, project)
    app = _app_for(task15_factory, router)
    path = f"/api/consol-note-sections/data/{project.id}/{Y}/五-1-1"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        saved = await client.put(path, json={"data": {"rows": [["库存现金", "1.00"]]}})
        assert saved.status_code == 200, saved.text

        async with task15_factory() as db:
            current = await db.get(Project, project.id)
            assert current is not None
            current.consol_lock = True
            await db.commit()

        locked = await client.put(path, json={"data": {"rows": [["库存现金", "2.00"]]}})
        assert locked.status_code == 423, locked.text
