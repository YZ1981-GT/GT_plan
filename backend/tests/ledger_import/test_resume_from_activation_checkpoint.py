"""F14 / Sprint 11.7: `resume_from_checkpoint` — 激活相关 phase 专项测试

补充 `test_resume_from_checkpoint.py` 在 "activating" 阶段的覆盖：
- `current_phase='activating'` 对应 `phases.PHASE_ACTIVATION_GATE_DONE`
  （pipeline 在 _mark("activation_gate_done") 后即进入激活阶段）
- `resume_from_checkpoint` 应该走 resume_from_activate_dataset 路径
- 失败后 staged dataset 仍能重新 activate 成功（语义验证：activate 幂等 + dataset 状态机正常）

这一测试关注"用户视角"：激活阶段崩溃 → 点恢复 → 数据可见。
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base
import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.dataset_models  # noqa: F401
from app.models.audit_platform_models import TbBalance
from app.models.dataset_models import (
    DatasetStatus,
    ImportJob,
    JobStatus,
    LedgerDataset,
)
from app.services.dataset_service import DatasetService
from app.services.import_job_runner import ImportJobRunner
from app.services.ledger_import.phases import (
    PHASE_ACTIVATE_DATASET_DONE,
    PHASE_ACTIVATION_GATE_DONE,
    PHASE_PARSE_WRITE_STREAMING_DONE,
)


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine_and_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield engine, factory
    await engine.dispose()


def _patch_runner_env(session_factory):
    async_session_patch = patch(
        "app.services.import_job_runner.async_session", session_factory
    )
    enqueue_patch = patch.object(ImportJobRunner, "enqueue", lambda job_id: None)
    return async_session_patch, enqueue_patch


async def _setup_failed_job_at_activation_gate(
    session_factory,
    *,
    phase: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """建 ImportJob(status=failed, phase=<phase>) + staged LedgerDataset + 写入 5 行。

    模拟 pipeline 在 activation_gate 通过后、activate 前崩溃场景。
    """
    project_id = uuid.uuid4()
    year = 2024
    job_id = uuid.uuid4()

    async with session_factory() as db:
        job = ImportJob(
            id=job_id,
            project_id=project_id,
            year=year,
            status=JobStatus.failed,
            current_phase=phase,
            error_message="simulated activation crash",
        )
        db.add(job)

        dataset = await DatasetService.create_staged(
            db, project_id=project_id, year=year, job_id=job_id,
        )
        # 5 行 staged 数据（B' 架构下 is_deleted=false）
        for i in range(5):
            db.add(TbBalance(
                id=uuid.uuid4(),
                project_id=project_id, year=year,
                dataset_id=dataset.id, company_code="001",
                account_code=f"100{i}", account_name=f"staged-{i}",
                currency_code="CNY", is_deleted=False,
            ))
        await db.commit()
        dataset_id = dataset.id

    return job_id, dataset_id, project_id


# ===========================================================================
# Case 1: phase=activation_gate_done → resume_from_activate_dataset
# ===========================================================================


@pytest.mark.asyncio
async def test_resume_from_activation_gate_done_reroutes_to_activate(
    engine_and_session,
):
    _, factory = engine_and_session
    job_id, dataset_id, _ = await _setup_failed_job_at_activation_gate(
        factory, phase=PHASE_ACTIVATION_GATE_DONE,
    )

    as_patch, enq_patch = _patch_runner_env(factory)
    with as_patch, enq_patch:
        result = await ImportJobRunner.resume_from_checkpoint(job_id)

    assert result["resumed"] is True
    assert result["action"] == "resume_from_activate_dataset"
    assert result["from_phase"] == PHASE_ACTIVATION_GATE_DONE

    # job 标 queued + staged 仍在
    async with factory() as db:
        job = (
            await db.execute(sa.select(ImportJob).where(ImportJob.id == job_id))
        ).scalar_one()
        assert job.status == JobStatus.queued
        assert job.error_message is None

        ds = (
            await db.execute(
                sa.select(LedgerDataset).where(LedgerDataset.id == dataset_id)
            )
        ).scalar_one()
        assert ds.status == DatasetStatus.staged  # 仍 staged，等 worker 重跑


# ===========================================================================
# Case 2: phase=activate_dataset_done → resume_from_rebuild_aux_summary
# ===========================================================================


@pytest.mark.asyncio
async def test_resume_from_activate_dataset_done_reroutes_to_rebuild(
    engine_and_session,
):
    _, factory = engine_and_session
    job_id, _, _ = await _setup_failed_job_at_activation_gate(
        factory, phase=PHASE_ACTIVATE_DATASET_DONE,
    )

    as_patch, enq_patch = _patch_runner_env(factory)
    with as_patch, enq_patch:
        result = await ImportJobRunner.resume_from_checkpoint(job_id)

    assert result["resumed"] is True
    assert result["action"] == "resume_from_rebuild_aux_summary"


# ===========================================================================
# Case 3: activation 阶段崩溃后手动调用 activate → 数据可见（幂等 + 状态机验证）
# ===========================================================================


@pytest.mark.asyncio
async def test_staged_dataset_can_be_activated_after_crash(engine_and_session):
    """验证用户视角：激活崩溃 → 重新 activate → 数据可见。

    这是 resume_from_checkpoint 的语义保证的基础：staged dataset 必须可再次激活。
    """
    _, factory = engine_and_session
    job_id, dataset_id, project_id = await _setup_failed_job_at_activation_gate(
        factory, phase=PHASE_ACTIVATION_GATE_DONE,
    )
    year = 2024

    # 直接调 activate 模拟 worker 重跑 activate 阶段
    async with factory() as db:
        activated = await DatasetService.activate(db, dataset_id)
        await db.commit()
    assert activated.status == DatasetStatus.active

    # 查询验证：get_active_filter 返回 5 行
    from app.services.dataset_query import get_active_filter

    async with factory() as db:
        cond = await get_active_filter(db, TbBalance.__table__, project_id, year)
        rows = (await db.execute(sa.select(TbBalance).where(cond))).scalars().all()
        assert len(rows) == 5


# ===========================================================================
# Case 4: activate 幂等 — crash 后 activate 再调仍返回成功
# ===========================================================================


@pytest.mark.asyncio
async def test_activate_idempotent_after_partial_commit(engine_and_session):
    """模拟：activate 第一次写了 dataset.status=active 但 outbox 写入失败重试。

    场景：pipeline 在 activate_dataset_done 后崩溃，resume 重跑 activate。
    依据 F29 / Sprint 10.39 幂等键：已 active 直接返回成功。
    """
    _, factory = engine_and_session
    project_id = uuid.uuid4()
    year = 2024

    async with factory() as db:
        staged = await DatasetService.create_staged(
            db, project_id=project_id, year=year,
        )
        await DatasetService.activate(db, staged.id)
        await db.commit()
        dataset_id = staged.id

    # 再 activate 一次（模拟 resume 触发的重跑）
    async with factory() as db:
        second = await DatasetService.activate(db, dataset_id)
        assert second.status == DatasetStatus.active
        assert second.id == dataset_id


# ===========================================================================
# Case 5: phase routes 表完备性 — 所有激活相关 phase 都有 resume 路径
# ===========================================================================


def test_phase_routes_cover_activation_lifecycle():
    """断言：phases.RESUME_FROM_PHASE 对激活生命周期的三个 checkpoint 都有映射。"""
    from app.services.ledger_import.phases import RESUME_FROM_PHASE

    expected = {
        PHASE_PARSE_WRITE_STREAMING_DONE: "activation_gate",
        PHASE_ACTIVATION_GATE_DONE: "activate_dataset",
        PHASE_ACTIVATE_DATASET_DONE: "rebuild_aux_summary",
    }
    for phase, label in expected.items():
        assert phase in RESUME_FROM_PHASE, f"{phase} 不在 RESUME_FROM_PHASE 路由表"
        got_label, recoverable = RESUME_FROM_PHASE[phase]
        assert got_label == label
        assert recoverable is True
