"""F15 / Sprint 4.8 — cancel 清理链集成测试

覆盖 pipeline._handle_cancel 的核心保证：
1. staged dataset + Tb* 行 → _handle_cancel → 行被删除，dataset.status=failed
2. ImportJob.artifact_id 关联的 ImportArtifact 被标 consumed（防止 retry 读旧 bundle）
3. recover_jobs orphan 清理逻辑：canceled job 的 staged dataset 兜底清理

Fixture 模式复用 test_dataset_rollback_view_refactor.py（SQLite in-memory）。
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 兼容适配：PG JSONB/UUID 降级到 JSON/uuid
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base
import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.dataset_models  # noqa: F401
from app.models.audit_platform_models import TbBalance
from app.models.dataset_models import (
    ArtifactStatus,
    DatasetStatus,
    ImportArtifact,
    ImportJob,
    JobStatus,
    LedgerDataset,
)
from app.services.dataset_service import DatasetService
from app.services.ledger_import.pipeline import _handle_cancel


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine_and_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield engine, session_factory
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine_and_session) -> AsyncSession:
    _, session_factory = engine_and_session
    async with session_factory() as session:
        yield session


def _patch_async_session(session_factory):
    """替换 _handle_cancel / DatasetService 内部用的 async_session 工厂。

    _handle_cancel 内部 `from app.core.database import async_session`，
    必须把那一处 symbol patch 成本测试的 session_factory。
    """
    return patch("app.core.database.async_session", session_factory)


# ---------------------------------------------------------------------------
# Task 4.8 Case 1：_handle_cancel 直接清理 staged 行 + 标记 dataset failed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_cancel_cleans_staged_rows_and_marks_failed(
    engine_and_session,
):
    engine, session_factory = engine_and_session
    project_id = uuid.uuid4()
    year = 2024
    job_id = uuid.uuid4()

    # ── 准备：staged dataset + 5 条 TbBalance 行（is_deleted=False，B' 架构） ──
    async with session_factory() as db:
        # 先创建 ImportJob（FK 目标）
        job = ImportJob(
            id=job_id,
            project_id=project_id,
            year=year,
            status=JobStatus.running,
            artifact_id=None,
        )
        db.add(job)
        await db.flush()

        staged = await DatasetService.create_staged(
            db, project_id=project_id, year=year, job_id=job_id,
        )
        staged_id = staged.id

        for i in range(5):
            db.add(TbBalance(
                project_id=project_id,
                year=year,
                company_code="C01",
                account_code=f"100{i}",
                account_name=f"staged-row-{i}",
                dataset_id=staged_id,
                is_deleted=False,
            ))
        await db.commit()

    # ── 执行：_handle_cancel 通过 patched async_session 工厂访问 DB ──
    with _patch_async_session(session_factory):
        await _handle_cancel(dataset_id=staged_id, job_id=job_id)

    # ── 断言：Tb* 行被删除 ──
    async with session_factory() as db:
        count = await db.execute(
            sa.select(sa.func.count())
            .select_from(TbBalance)
            .where(TbBalance.dataset_id == staged_id)
        )
        assert count.scalar_one() == 0

        # ── 断言：dataset.status == failed ──
        ds = (await db.execute(
            sa.select(LedgerDataset).where(LedgerDataset.id == staged_id)
        )).scalar_one()
        assert ds.status == DatasetStatus.failed


@pytest.mark.asyncio
async def test_handle_cancel_with_no_dataset_is_noop(engine_and_session):
    """dataset_id=None 时 _handle_cancel 不应抛异常（graceful skip）。"""
    _, session_factory = engine_and_session
    job_id = uuid.uuid4()
    with _patch_async_session(session_factory):
        # 没有 dataset，没有 artifact — 应 graceful skip 无异常
        await _handle_cancel(dataset_id=None, job_id=job_id)


@pytest.mark.asyncio
async def test_handle_cancel_marks_artifact_consumed(engine_and_session):
    """ImportJob.artifact_id 指向的 ImportArtifact 应被标记 consumed。"""
    _, session_factory = engine_and_session
    project_id = uuid.uuid4()
    year = 2024
    job_id = uuid.uuid4()
    artifact_id = uuid.uuid4()

    async with session_factory() as db:
        artifact = ImportArtifact(
            id=artifact_id,
            project_id=project_id,
            upload_token="token-" + uuid.uuid4().hex,
            status=ArtifactStatus.active,
            storage_uri="sharedfs:///tmp/test-bundle",
            total_size_bytes=1024,
            file_count=1,
        )
        db.add(artifact)
        job = ImportJob(
            id=job_id,
            project_id=project_id,
            year=year,
            status=JobStatus.running,
            artifact_id=artifact_id,
        )
        db.add(job)
        staged = await DatasetService.create_staged(
            db, project_id=project_id, year=year, job_id=job_id,
        )
        staged_id = staged.id
        await db.commit()

    with _patch_async_session(session_factory):
        await _handle_cancel(dataset_id=staged_id, job_id=job_id)

    async with session_factory() as db:
        art = (await db.execute(
            sa.select(ImportArtifact).where(ImportArtifact.id == artifact_id)
        )).scalar_one()
        assert art.status == ArtifactStatus.consumed


# ---------------------------------------------------------------------------
# Task 4.8 Case 2：recover_jobs orphan 清理逻辑（in-place 验证）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recover_jobs_orphan_cleanup_logic(engine_and_session):
    """验证 orphan cleanup 的核心 SQL 行为：

    设置两个场景：
    - A job canceled + dataset staged → 应被清理
    - B job canceled + dataset active → 不应被清理（已落地的成功历史）

    直接复刻 import_job_runner.recover_jobs 中的 orphan 查询 + 清理段，
    避免依赖 async_session 全局单例。
    """
    _, session_factory = engine_and_session
    project_a = uuid.uuid4()
    project_b = uuid.uuid4()

    async with session_factory() as db:
        # Case A: canceled job + staged dataset + 3 staged rows
        job_a = ImportJob(
            id=uuid.uuid4(), project_id=project_a, year=2024,
            status=JobStatus.canceled,
        )
        db.add(job_a)
        await db.flush()
        ds_a = await DatasetService.create_staged(
            db, project_id=project_a, year=2024, job_id=job_a.id,
        )
        for i in range(3):
            db.add(TbBalance(
                project_id=project_a, year=2024, company_code="A01",
                account_code=f"A00{i}", account_name=f"A-{i}",
                dataset_id=ds_a.id, is_deleted=False,
            ))

        # Case B: canceled job + active dataset — 不应被清理
        job_b = ImportJob(
            id=uuid.uuid4(), project_id=project_b, year=2024,
            status=JobStatus.canceled,
        )
        db.add(job_b)
        await db.flush()
        ds_b = await DatasetService.create_staged(
            db, project_id=project_b, year=2024, job_id=job_b.id,
        )
        # 强制切到 active 模拟"job 被取消前已完成激活"
        ds_b.status = DatasetStatus.active
        db.add(TbBalance(
            project_id=project_b, year=2024, company_code="B01",
            account_code="B001", account_name="B-active",
            dataset_id=ds_b.id, is_deleted=False,
        ))
        await db.commit()

    # ── 复刻 recover_jobs 中的 orphan 清理片段 ──
    async with session_factory() as db:
        canceled_orphans = await db.execute(
            sa.select(LedgerDataset.id, LedgerDataset.job_id)
            .join(ImportJob, LedgerDataset.job_id == ImportJob.id)
            .where(
                ImportJob.status == JobStatus.canceled,
                LedgerDataset.status == DatasetStatus.staged,
            )
        )
        orphan_rows = list(canceled_orphans.all())
        assert len(orphan_rows) == 1
        assert orphan_rows[0][0] == ds_a.id

        for ds_id, _jid in orphan_rows:
            await DatasetService.cleanup_dataset_rows(db, ds_id)
            await DatasetService.mark_failed(db, ds_id, cleanup_rows=False)
        await db.commit()

    # ── 断言：A 被清理，B 不动 ──
    async with session_factory() as db:
        count_a = (await db.execute(
            sa.select(sa.func.count()).select_from(TbBalance)
            .where(TbBalance.dataset_id == ds_a.id)
        )).scalar_one()
        assert count_a == 0
        ds_a_reload = (await db.execute(
            sa.select(LedgerDataset).where(LedgerDataset.id == ds_a.id)
        )).scalar_one()
        assert ds_a_reload.status == DatasetStatus.failed

        count_b = (await db.execute(
            sa.select(sa.func.count()).select_from(TbBalance)
            .where(TbBalance.dataset_id == ds_b.id)
        )).scalar_one()
        assert count_b == 1
        ds_b_reload = (await db.execute(
            sa.select(LedgerDataset).where(LedgerDataset.id == ds_b.id)
        )).scalar_one()
        assert ds_b_reload.status == DatasetStatus.active
