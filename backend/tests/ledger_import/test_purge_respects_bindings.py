"""F53 / Sprint 8.44: purge_old_datasets 尊重 bound_dataset_id + retention_class。

覆盖范围（对应 design D13.4 + requirements F53 + F50）：
1. ``keep_count=0`` 时普通 transient + 未绑定的 superseded 会被清理
2. 被 AuditReport(final) 通过 ``bound_dataset_id`` 绑定的 superseded
   不会被清理（``skipped_due_to_binding`` 计数 +1）
3. artifact ``retention_class='archived'`` 的 superseded 不会被清理
   （``skipped_due_to_retention`` 计数 +1）
4. ``retention_class='legal_hold'`` 也不会被清理
5. 组合场景：被绑定 + archived + legal_hold + 普通 transient 各 1 份，
   ``keep_count=0`` 只清理普通 transient

Fixture 模式：SQLite 内存库 + PG JSONB/UUID 降级，同 test_cross_project_isolation.py。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 兼容适配（必须在 Base.metadata 构建前生效）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base  # noqa: E402
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.dataset_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401

from app.models.dataset_models import (  # noqa: E402
    ArtifactStatus,
    DatasetStatus,
    ImportArtifact,
    ImportJob,
    JobStatus,
    LedgerDataset,
)
from app.models.report_models import (  # noqa: E402
    AuditReport,
    CompanyType,
    OpinionType,
    ReportStatus,
)
from app.services.dataset_service import DatasetService  # noqa: E402


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


async def _make_dataset(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    year: int,
    status: DatasetStatus,
    retention_class: str = "transient",
) -> tuple[LedgerDataset, ImportArtifact, ImportJob]:
    """创建一份指定状态 + retention_class 的 dataset (含 job+artifact)。"""
    artifact = ImportArtifact(
        id=uuid.uuid4(),
        project_id=project_id,
        upload_token=f"tok-{uuid.uuid4().hex[:8]}",
        status=ArtifactStatus.active,
        storage_uri=f"local:///tmp/{uuid.uuid4().hex}",
        total_size_bytes=1024,
        file_count=1,
        retention_class=retention_class,
    )
    db.add(artifact)
    await db.flush()

    job = ImportJob(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        status=JobStatus.completed,
        artifact_id=artifact.id,
    )
    db.add(job)
    await db.flush()

    ds = LedgerDataset(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        status=status,
        source_type="import",
        job_id=job.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(ds)
    await db.flush()
    return ds, artifact, job


async def _bind_final_report(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    year: int,
    dataset_id: uuid.UUID,
) -> AuditReport:
    report = AuditReport(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        company_type=CompanyType.non_listed,
        opinion_type=OpinionType.unqualified,
        status=ReportStatus.final,
        paragraphs={},
        bound_dataset_id=dataset_id,
        dataset_bound_at=datetime.now(timezone.utc),
        is_deleted=False,
    )
    db.add(report)
    await db.flush()
    return report


async def _count_datasets(
    db: AsyncSession, project_id: uuid.UUID, year: int | None = None
) -> int:
    stmt = sa.select(sa.func.count()).select_from(LedgerDataset).where(
        LedgerDataset.project_id == project_id
    )
    if year is not None:
        stmt = stmt.where(LedgerDataset.year == year)
    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


# ---------------------------------------------------------------------------
# 基线：transient + 未绑定 → 真的被清理
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_removes_transient_unbound_superseded(
    db_session: AsyncSession,
) -> None:
    pid = uuid.uuid4()
    ds, _art, _job = await _make_dataset(
        db_session,
        project_id=pid,
        year=2025,
        status=DatasetStatus.superseded,
        retention_class="transient",
    )

    summary = await DatasetService.purge_old_datasets(
        db_session, pid, keep_count=0
    )
    await db_session.flush()

    assert summary["datasets_deleted"] == 1
    assert summary["skipped_due_to_binding"] == 0
    assert summary["skipped_due_to_retention"] == 0
    remaining = await _count_datasets(db_session, pid)
    assert remaining == 0


# ---------------------------------------------------------------------------
# F50：被 final 报表绑定的 superseded 不被清理
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_skips_dataset_bound_by_final_report(
    db_session: AsyncSession,
) -> None:
    pid = uuid.uuid4()
    ds, _art, _job = await _make_dataset(
        db_session,
        project_id=pid,
        year=2025,
        status=DatasetStatus.superseded,
        retention_class="transient",
    )
    await _bind_final_report(db_session, project_id=pid, year=2025, dataset_id=ds.id)

    summary = await DatasetService.purge_old_datasets(
        db_session, pid, keep_count=0
    )
    await db_session.flush()

    assert summary["datasets_deleted"] == 0
    assert summary["skipped_due_to_binding"] == 1
    assert summary["skipped_due_to_retention"] == 0
    remaining = await _count_datasets(db_session, pid)
    assert remaining == 1  # ds 保留


# ---------------------------------------------------------------------------
# F53：archived / legal_hold 的 superseded 不被清理
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_skips_archived_artifact(db_session: AsyncSession) -> None:
    pid = uuid.uuid4()
    ds, _art, _job = await _make_dataset(
        db_session,
        project_id=pid,
        year=2025,
        status=DatasetStatus.superseded,
        retention_class="archived",
    )

    summary = await DatasetService.purge_old_datasets(
        db_session, pid, keep_count=0
    )
    await db_session.flush()

    assert summary["datasets_deleted"] == 0
    assert summary["skipped_due_to_binding"] == 0
    assert summary["skipped_due_to_retention"] == 1
    assert await _count_datasets(db_session, pid) == 1


@pytest.mark.asyncio
async def test_purge_skips_legal_hold_artifact(db_session: AsyncSession) -> None:
    pid = uuid.uuid4()
    ds, _art, _job = await _make_dataset(
        db_session,
        project_id=pid,
        year=2025,
        status=DatasetStatus.superseded,
        retention_class="legal_hold",
    )

    summary = await DatasetService.purge_old_datasets(
        db_session, pid, keep_count=0
    )
    await db_session.flush()

    assert summary["datasets_deleted"] == 0
    assert summary["skipped_due_to_retention"] == 1
    assert await _count_datasets(db_session, pid) == 1


# ---------------------------------------------------------------------------
# 组合场景：绑定 + archived + legal_hold + transient 各一份
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_combined_bound_retention_transient(
    db_session: AsyncSession,
) -> None:
    pid = uuid.uuid4()
    ds_bound, _a1, _j1 = await _make_dataset(
        db_session,
        project_id=pid,
        year=2025,
        status=DatasetStatus.superseded,
        retention_class="transient",
    )
    await _bind_final_report(
        db_session, project_id=pid, year=2025, dataset_id=ds_bound.id,
    )

    ds_archived, _a2, _j2 = await _make_dataset(
        db_session,
        project_id=pid,
        year=2025,
        status=DatasetStatus.superseded,
        retention_class="archived",
    )
    ds_legal, _a3, _j3 = await _make_dataset(
        db_session,
        project_id=pid,
        year=2025,
        status=DatasetStatus.superseded,
        retention_class="legal_hold",
    )
    ds_transient, _a4, _j4 = await _make_dataset(
        db_session,
        project_id=pid,
        year=2025,
        status=DatasetStatus.superseded,
        retention_class="transient",
    )

    summary = await DatasetService.purge_old_datasets(
        db_session, pid, keep_count=0
    )
    await db_session.flush()

    # 四份 superseded：bound / archived / legal_hold 三份被保护
    # transient + 未绑定 的一份被删
    assert summary["datasets_deleted"] == 1
    assert summary["skipped_due_to_binding"] == 1
    assert summary["skipped_due_to_retention"] == 2

    # 确认剩 3 份（bound / archived / legal_hold）
    ids_left = set(
        (
            await db_session.execute(
                sa.select(LedgerDataset.id).where(LedgerDataset.project_id == pid)
            )
        ).scalars().all()
    )
    assert ds_bound.id in ids_left
    assert ds_archived.id in ids_left
    assert ds_legal.id in ids_left
    assert ds_transient.id not in ids_left


# ---------------------------------------------------------------------------
# active / staged / rolled_back 不受影响（只动 superseded）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_ignores_non_superseded_status(db_session: AsyncSession) -> None:
    pid = uuid.uuid4()
    for status in (DatasetStatus.active, DatasetStatus.staged, DatasetStatus.rolled_back):
        await _make_dataset(
            db_session,
            project_id=pid,
            year=2025,
            status=status,
            retention_class="transient",
        )

    summary = await DatasetService.purge_old_datasets(
        db_session, pid, keep_count=0
    )
    await db_session.flush()
    assert summary["datasets_deleted"] == 0
    assert summary["skipped_due_to_binding"] == 0
    assert summary["skipped_due_to_retention"] == 0
    assert await _count_datasets(db_session, pid) == 3


# ---------------------------------------------------------------------------
# keep_count 语义：最近 N 个 superseded 永远保留
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_keep_count_preserves_latest_n(
    db_session: AsyncSession,
) -> None:
    pid = uuid.uuid4()
    created = []
    # 4 个 transient 无绑定 superseded，按时间顺序
    for i in range(4):
        ds, _a, _j = await _make_dataset(
            db_session,
            project_id=pid,
            year=2025,
            status=DatasetStatus.superseded,
            retention_class="transient",
        )
        # 强制设置不同 created_at 保证排序
        ds.created_at = datetime(2026, 1, i + 1, tzinfo=timezone.utc)
        created.append(ds)
    await db_session.flush()

    # keep_count=2：保留最近 2 个（i=2, i=3），删最早 2 个（i=0, i=1）
    summary = await DatasetService.purge_old_datasets(
        db_session, pid, keep_count=2
    )
    await db_session.flush()
    assert summary["datasets_deleted"] == 2
    remaining = await _count_datasets(db_session, pid)
    assert remaining == 2
