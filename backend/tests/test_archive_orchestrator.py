"""ArchiveOrchestrator 编排测试（refinement-round1 需求 5；spec attachment-archive-and-a-class-evidence 需求 2 改造）

覆盖：
1. 全部成功 ⇒ succeeded、项目与底稿锁定、manifest_hash / output_url / 完整性记录写入
2. gate / package / push_to_cloud 任一步失败 ⇒ failed、失败步骤与问题清单落进度、项目不锁
3. 重试从第一个未成功的步骤继续（已成功的不重跑）；推送用打包步骤留下的包，包被改动 ⇒ 失败
4. section_progress 真实落库（换会话重新读）
5. get_job 字段

改造前：wp_storage 步失败只返回 ``{"error"}``、编排照样成功；保留期与哈希持久化失败不阻断；不改项目状态；
section_progress 原地改 JSONB 从未落库 —— 旧用例全在 mock 上断言内存对象，测不出这些。
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.models.archive_models import ArchiveJob
from app.models.base import Base
from app.models.core import Project
from app.models.phase16_models import EvidenceHashCheck
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.archive_orchestrator import ArchiveOrchestrator
from app.services.archive_package_builder import ArchivePackageError, PackageResult

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
FAKE_USER_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, poolclass=sa.pool.StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(factory) -> AsyncSession:
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def project(db_session) -> Project:
    p = Project(id=uuid.uuid4(), name="编排测试项目", client_name="编排测试客户", status="execution",
                audit_period_end=date(2025, 12, 31))
    db_session.add(p)
    await db_session.flush()
    idx = WpIndex(project_id=p.id, wp_code="D2-1", wp_name="审定表")
    db_session.add(idx)
    await db_session.flush()
    source = list(WorkingPaper.__table__.c.source_type.type.enum_class)[0]
    db_session.add(WorkingPaper(project_id=p.id, wp_index_id=idx.id, file_path="", source_type=source))
    await db_session.commit()
    return p


GATE = "app.services.archive_gate.archive_gate_problems"


def _gate(verdict: str = "allow"):
    """门禁替身（组合判据另有专测 attachment_archive_evidence/test_archive_gate.py）。"""
    return AsyncMock(return_value=[] if verdict == "allow" else ["完整性自检｜未签字底稿｜Test blocking reason"])


def _fake_package(tmp_path, calls: list):
    async def build(db, project_id, job_id):
        calls.append(job_id)
        path = tmp_path / f"{job_id}.zip"
        path.write_bytes(b"PK-fake-" + str(job_id).encode())
        return PackageResult(path=path, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), size=path.stat().st_size,
                             manifest_hash="m" * 64, counts={"workpaper_data": 1}, skipped=1)
    return build


def _patches(tmp_path, calls, *, gate="allow", push=None):
    ps = [
        patch(GATE, new=_gate(gate)),
        patch("app.services.archive_package_builder.build_archive_package", new=_fake_package(tmp_path, calls)),
        patch("app.services.archive_orchestrator.ArchiveOrchestrator._notify_project_members", new_callable=AsyncMock),
    ]
    if push is not None:
        ps.append(patch("app.services.cloud_storage_service.CloudStorageService.upload_archive_package", new=push))
    return ps


class _Many:
    def __init__(self, ps):
        self.ps = ps

    def __enter__(self):
        for p in self.ps:
            p.__enter__()

    def __exit__(self, *exc):
        for p in reversed(self.ps):
            p.__exit__(*exc)


async def _wp_statuses(db, project_id):
    rows = (await db.execute(sa.select(WorkingPaper.status).where(WorkingPaper.project_id == project_id))).scalars()
    return {getattr(s, "value", s) for s in rows}


async def test_happy_path_locks_project_and_records_package(db_session, project, tmp_path, factory):
    calls: list = []
    with _Many(_patches(tmp_path, calls)):
        job = await ArchiveOrchestrator(db_session).orchestrate(project_id=project.id, initiated_by=FAKE_USER_ID)
        await db_session.commit()
    assert (job.status, job.failed_section, job.failed_reason) == ("succeeded", None, None)
    assert job.last_succeeded_section == "lock"
    assert job.manifest_hash == "m" * 64
    assert job.output_url == f"/api/projects/{project.id}/archive/jobs/{job.id}/package"
    # 换会话读：进度、锁定、完整性记录都真实落库
    async with factory() as s2:
        fresh = await s2.get(ArchiveJob, job.id)
        assert list(fresh.section_progress) == ["gate", "package", "lock"]
        assert fresh.section_progress["package"]["sha256"] == hashlib.sha256((tmp_path / f"{job.id}.zip").read_bytes()).hexdigest()
        assert fresh.section_progress["lock"]["workpapers_locked"] == 1
        p = await s2.get(Project, project.id)
        assert getattr(p.status, "value", p.status) == "archived"
        assert p.archived_at is not None and p.retention_until is not None
        assert await _wp_statuses(s2, project.id) == {"archived"}
        checks = (await s2.execute(sa.select(EvidenceHashCheck).where(EvidenceHashCheck.export_id == str(job.id)))).scalars().all()
        assert [c.file_path for c in checks] == [fresh.section_progress["package"]["path"]]


async def test_gate_failure_does_not_lock(db_session, project, tmp_path):
    calls: list = []
    with _Many(_patches(tmp_path, calls, gate="block")):
        job = await ArchiveOrchestrator(db_session).orchestrate(project_id=project.id)
        await db_session.commit()
    assert (job.status, job.failed_section) == ("failed", "gate")
    assert job.failed_reason.startswith("归档门禁未通过：1 项阻断") and "Test blocking reason" in job.failed_reason
    assert job.section_progress["gate"]["problems"] == ["完整性自检｜未签字底稿｜Test blocking reason"]
    assert calls == []
    await db_session.refresh(project)
    assert getattr(project.status, "value", project.status) == "execution"


async def test_package_failure_records_problems_and_does_not_lock(db_session, project, tmp_path):
    async def broken(db, project_id, job_id):
        raise ArchivePackageError(["底稿文件｜D2-1 审定表｜底稿文件不存在（路径已配置但磁盘上找不到）", "附件｜回函.pdf｜附件文件不存在"])

    with _Many(_patches(tmp_path, [])), patch("app.services.archive_package_builder.build_archive_package", new=broken):
        job = await ArchiveOrchestrator(db_session).orchestrate(project_id=project.id)
        await db_session.commit()
    assert (job.status, job.failed_section, job.last_succeeded_section) == ("failed", "package", "gate")
    assert job.failed_reason.startswith("归档包有 2 项读不到")
    assert job.section_progress["package"]["status"] == "failed"
    assert len(job.section_progress["package"]["problems"]) == 2
    assert job.manifest_hash is None and job.output_url is None
    await db_session.refresh(project)
    assert getattr(project.status, "value", project.status) == "execution"
    assert await _wp_statuses(db_session, project.id) != {"archived"}


async def test_push_failure_then_retry_resumes_without_repackaging(db_session, project, tmp_path):
    calls: list = []
    push = AsyncMock(side_effect=RuntimeError("SFTP 连接被拒绝"))
    with _Many(_patches(tmp_path, calls, push=push)):
        job = await ArchiveOrchestrator(db_session).orchestrate(project_id=project.id, push_to_cloud=True)
        await db_session.commit()
    assert (job.status, job.failed_section) == ("failed", "push_to_cloud")
    assert "SFTP 连接被拒绝" in job.failed_reason
    await db_session.refresh(project)
    assert getattr(project.status, "value", project.status) == "execution"

    gate = _gate()
    ok_push = AsyncMock(return_value={"status": "success", "method": "local", "remote_key": "k"})
    with patch(GATE, new=gate), \
            patch("app.services.archive_package_builder.build_archive_package", new=_fake_package(tmp_path, calls)), \
            patch("app.services.cloud_storage_service.CloudStorageService.upload_archive_package", new=ok_push), \
            patch("app.services.archive_orchestrator.ArchiveOrchestrator._notify_project_members", new_callable=AsyncMock):
        retried = await ArchiveOrchestrator(db_session).retry(job_id=job.id)
        await db_session.commit()
    assert retried.status == "succeeded" and retried.failed_section is None
    assert gate.call_count == 0 and len(calls) == 1  # gate / package 不重跑
    pushed_path = ok_push.call_args.args[3]
    assert str(pushed_path.resolve()) == retried.section_progress["package"]["path"]
    assert retried.section_progress["push_to_cloud"]["remote_key"] == "k"


async def test_push_refuses_tampered_package(db_session, project, tmp_path):
    calls: list = []
    push = AsyncMock(side_effect=RuntimeError("down"))
    with _Many(_patches(tmp_path, calls, push=push)):
        job = await ArchiveOrchestrator(db_session).orchestrate(project_id=project.id, push_to_cloud=True)
        await db_session.commit()
    (tmp_path / f"{job.id}.zip").write_bytes(b"tampered")
    ok_push = AsyncMock(return_value={"status": "success"})
    with patch("app.services.cloud_storage_service.CloudStorageService.upload_archive_package", new=ok_push):
        retried = await ArchiveOrchestrator(db_session).retry(job_id=job.id)
    assert (retried.status, retried.failed_section) == ("failed", "push_to_cloud")
    assert retried.failed_reason == "归档包文件不存在或已被改动，请重新归档"
    assert ok_push.call_count == 0


async def test_lock_failure_when_project_missing(db_session, tmp_path):
    with _Many(_patches(tmp_path, [])):
        job = await ArchiveOrchestrator(db_session).orchestrate(project_id=uuid.uuid4())
    assert (job.status, job.failed_section, job.failed_reason) == ("failed", "lock", "项目不存在，无法锁定")


async def test_retry_invalid_status(db_session, project, tmp_path):
    with _Many(_patches(tmp_path, [])):
        job = await ArchiveOrchestrator(db_session).orchestrate(project_id=project.id)
        await db_session.commit()
    with pytest.raises(ValueError, match="cannot retry"):
        await ArchiveOrchestrator(db_session).retry(job_id=job.id)


async def test_get_job_fields_and_not_found(db_session, project, tmp_path):
    with _Many(_patches(tmp_path, [])):
        job = await ArchiveOrchestrator(db_session).orchestrate(project_id=project.id, initiated_by=FAKE_USER_ID)
        await db_session.commit()
    result = await ArchiveOrchestrator(db_session).get_job(job.id)
    assert result["id"] == str(job.id)
    assert result["project_id"] == str(project.id)
    assert (result["status"], result["scope"], result["push_to_cloud"], result["purge_local"]) == (
        "succeeded", "final", False, False)
    assert result["last_succeeded_section"] == "lock"
    assert result["output_url"].endswith(f"/archive/jobs/{job.id}/package")
    assert result["initiated_by"] == str(FAKE_USER_ID)
    assert await ArchiveOrchestrator(db_session).get_job(uuid.uuid4()) is None


async def test_retry_skips_succeeded_sections_via_progress(db_session, project, tmp_path):
    now_iso = datetime.now(timezone.utc).isoformat()
    job = ArchiveJob(
        id=uuid.uuid4(), project_id=project.id, scope="final", status="failed", push_to_cloud=False,
        purge_local=False, failed_section="package", failed_reason="old",
        section_progress={"gate": {"status": "succeeded", "finished_at": now_iso}},
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.commit()
    calls: list = []
    gate = _gate()
    with patch(GATE, new=gate), \
            patch("app.services.archive_package_builder.build_archive_package", new=_fake_package(tmp_path, calls)), \
            patch("app.services.archive_orchestrator.ArchiveOrchestrator._notify_project_members", new_callable=AsyncMock):
        retried = await ArchiveOrchestrator(db_session).retry(job_id=job.id)
        await db_session.commit()
    assert gate.call_count == 0 and calls == [job.id]
    assert retried.status == "succeeded"
    assert list(retried.section_progress) == ["gate", "package", "lock"]


async def test_purge_local_runs_after_lock(db_session, project, tmp_path):
    order: list[str] = []
    purge = AsyncMock(side_effect=lambda pid: order.append("purge") or {"archived": True})
    with _Many(_patches(tmp_path, [])), \
            patch("app.services.data_lifecycle_service.DataLifecycleService.archive_project_data", new=purge):
        job = await ArchiveOrchestrator(db_session).orchestrate(project_id=project.id, purge_local=True)
    assert job.status == "succeeded"
    assert list(job.section_progress) == ["gate", "package", "lock", "purge_local"]
    assert order == ["purge"]


async def test_push_without_audit_year_fails_instead_of_guessing(db_session, tmp_path):
    """审计年度解析不出 ⇒ 推送失败如实报错（不按今年 / 写死 2025 建云端目录，audit-year-calendar-fallback-ratchet）。"""
    bare = Project(id=uuid.uuid4(), name="无年度项目", client_name="客户", status="execution")
    db_session.add(bare)
    await db_session.commit()
    push = AsyncMock(return_value={"status": "success"})
    with _Many(_patches(tmp_path, [], push=push)):
        job = await ArchiveOrchestrator(db_session).orchestrate(project_id=bare.id, push_to_cloud=True)
    assert (job.status, job.failed_section) == ("failed", "push_to_cloud")
    assert "未设置审计年度" in job.failed_reason
    assert push.call_count == 0
