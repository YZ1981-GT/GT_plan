"""解除归档是锁定的逆操作（spec attachment-archive-and-a-class-evidence 需求 6.4，ADR-AE-13）。

改造前解除归档只把项目状态改回「执行中」：归档时锁成「已归档」的底稿恒只读（WOPI / 上传 / 在线编辑都拒）；
归档时间不清 ⇒ 独立性门禁按「已归档」跳过、准则切换被拒；24 小时内再归档命中旧的成功作业、不再锁定。
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.core.database import get_db
from app.deps import get_current_user
from app.models.archive_models import ArchiveJob
from app.models.audit_log_models import AuditLogEntry
from app.models.base import Base, ProjectStatus, UserRole
from app.models.core import Project
from app.models.workpaper_models import WorkingPaper, WpFileStatus, WpIndex
from app.routers.archived_exception import unarchive_router
from app.services.archive_orchestrator import ArchiveOrchestrator, restore_after_unarchive
from app.services.archive_package_builder import PackageResult

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


class _Admin:
    id = uuid.uuid4()
    username = "admin"
    role = UserRole.admin
    is_active = True
    is_deleted = False


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, poolclass=sa.pool.StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(factory) -> AsyncSession:
    async with factory() as session:
        yield session


STARTING = ["draft", "review_passed", "edit_complete", "archived"]


@pytest_asyncio.fixture
async def world(db):
    p = Project(id=uuid.uuid4(), name="【测试】解除归档", client_name="客户", status="execution",
                audit_period_end=date(2025, 12, 31))
    db.add(p)
    await db.flush()
    source = list(WorkingPaper.__table__.c.source_type.type.enum_class)[0]
    wps = []
    for i, status in enumerate(STARTING):
        idx = WpIndex(project_id=p.id, wp_code=f"D{i}", wp_name=f"底稿{i}")
        db.add(idx)
        await db.flush()
        wp = WorkingPaper(project_id=p.id, wp_index_id=idx.id, file_path="", source_type=source,
                          status=WpFileStatus(status))
        db.add(wp)
        wps.append(wp)
    await db.commit()
    return p, wps


def _patches(tmp_path, calls):
    async def build(db, project_id, job_id):
        calls.append(job_id)
        path = tmp_path / f"{job_id}.zip"
        path.write_bytes(b"PK" + str(job_id).encode())
        return PackageResult(path=path, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), size=path.stat().st_size,
                             manifest_hash="m" * 64, counts={}, skipped=0)

    @patch("app.services.archive_gate.archive_gate_problems", new=AsyncMock(return_value=[]))
    @patch("app.services.archive_package_builder.build_archive_package", new=build)
    @patch("app.services.archive_orchestrator.ArchiveOrchestrator._notify_project_members", new_callable=AsyncMock)
    async def run(db, project_id, _notify):
        job = await ArchiveOrchestrator(db).orchestrate(project_id=project_id)
        await db.commit()
        return job

    return run


async def _statuses(db, wps) -> list[str]:
    rows = dict((await db.execute(sa.select(WorkingPaper.id, WorkingPaper.status))).all())
    return [getattr(rows[w.id], "value", rows[w.id]) for w in wps]


async def _unarchive(db, project) -> tuple[int, dict]:
    app = FastAPI()
    app.include_router(unarchive_router)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: _Admin()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(f"/api/projects/{project.id}/unarchive",
                         json={"reason": "补充程序", "project_code": project.name})
    return r.status_code, r.json()


async def test_unarchive_restores_statuses_and_clears_archive_time(db, world, tmp_path, factory):
    project, wps = world
    job = await _patches(tmp_path, [])(db, project.id)
    assert job.status == "succeeded"
    assert await _statuses(db, wps) == ["archived"] * 4
    recorded = job.section_progress["lock"]["previous_wp_statuses"]
    assert recorded == {str(w.id): s for w, s in zip(wps, STARTING) if s != "archived"}
    public = await ArchiveOrchestrator(db).get_job(job.id)
    assert "previous_wp_statuses" not in public["section_progress"]["lock"]
    assert public["section_progress"]["lock"]["previous_wp_status_count"] == 3

    code, body = await _unarchive(db, project)
    assert code == 200 and body["workpapers_restored"] == 3 and body["new_status"] == "execution"
    async with factory() as s2:
        assert await _statuses(s2, wps) == STARTING  # 归档前就是「已归档」的那张不动
        p = await s2.get(Project, project.id)
        assert getattr(p.status, "value", p.status) == "execution"
        assert p.archived_at is None and p.retention_until is None
        lock = (await s2.get(ArchiveJob, job.id)).section_progress["lock"]
        assert lock["restored_at"] and lock["workpapers_restored"] == 3
        log = (await s2.execute(sa.select(AuditLogEntry).where(AuditLogEntry.action_type == "archive_unarchive"))).scalar_one()
        assert (log.payload["workpapers_restored"], log.payload["archive_job_id"]) == (3, str(job.id))


async def test_status_changed_while_archived_is_kept(db, world, tmp_path):
    project, wps = world
    await _patches(tmp_path, [])(db, project.id)
    await db.execute(sa.update(WorkingPaper).where(WorkingPaper.id == wps[0].id).values(status=WpFileStatus.review_passed))
    await db.commit()
    code, body = await _unarchive(db, project)
    assert code == 200 and body["workpapers_restored"] == 2
    assert await _statuses(db, wps) == ["review_passed", "review_passed", "edit_complete", "archived"]


async def test_rearchive_after_unarchive_runs_again_and_uses_the_new_record(db, world, tmp_path):
    project, wps = world
    calls: list = []
    run = _patches(tmp_path, calls)
    first = await run(db, project.id)
    assert (await run(db, project.id)).id == first.id and len(calls) == 1  # 仍归档 ⇒ 幂等命中
    await _unarchive(db, project)
    await db.execute(sa.update(WorkingPaper).where(WorkingPaper.id == wps[0].id).values(status=WpFileStatus.edit_complete))
    await db.commit()

    second = await run(db, project.id)
    assert second.id != first.id and len(calls) == 2  # 改造前命中旧作业：回执成功、项目却没锁
    assert second.status == "succeeded"
    assert await _statuses(db, wps) == ["archived"] * 4
    code, body = await _unarchive(db, project)
    assert code == 200 and body["workpapers_restored"] == 3
    assert await _statuses(db, wps) == ["edit_complete", "review_passed", "edit_complete", "archived"]


async def test_restore_record_is_used_once(db, world, tmp_path):
    project, wps = world
    await _patches(tmp_path, [])(db, project.id)
    await _unarchive(db, project)
    # 之后经别的路径（交付件全部归档）项目又成了「已归档」：旧记录已用过，不再拿它改底稿
    await db.execute(sa.update(Project).where(Project.id == project.id).values(status=ProjectStatus.archived))
    await db.execute(sa.update(WorkingPaper).where(WorkingPaper.id == wps[0].id).values(status=WpFileStatus.archived))
    await db.commit()
    code, body = await _unarchive(db, project)
    assert code == 200 and body["workpapers_restored"] == 0
    assert (await _statuses(db, wps))[0] == "archived"


async def test_project_archived_without_job_only_clears_time(db, world):
    project, wps = world
    await db.execute(sa.update(Project).where(Project.id == project.id).values(
        status=ProjectStatus.archived, archived_at=datetime.now(timezone.utc), retention_until=datetime.now(timezone.utc)))
    await db.commit()
    result = await restore_after_unarchive(db, project.id)
    assert result == {"workpapers_restored": 0, "job_id": None}
    await db.commit()
    await db.refresh(project)
    assert project.archived_at is None and project.retention_until is None
    assert await _statuses(db, wps) == STARTING
