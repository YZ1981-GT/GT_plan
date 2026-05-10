"""F53 / Sprint 8.43: retention_class 自动决策集成测试。

覆盖范围（对应 design D13.4 + requirements F53）：
1. ``compute_retention_class`` 三档决策优先级：legal_hold > archived > transient
2. ``compute_expires_at`` 三档过期时长：transient 90 天 / archived 10 年 /
   legal_hold 返回 None
3. ``DatasetService.activate`` 激活时自动把 retention 写回关联 ImportArtifact
4. final / eqcr_approved 报表绑定触发 archived 升级

Fixture 模式：SQLite 内存库 + PG JSONB/UUID 降级，同 test_cross_project_isolation.py。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
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
from app.services.ledger_import.retention_policy import (  # noqa: E402
    ARCHIVED_RETENTION,
    TRANSIENT_RETENTION,
    apply_retention_to_artifact,
    compute_expires_at,
    compute_retention_class,
)


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


async def _seed_dataset(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    year: int = 2025,
    with_job: bool = True,
    source_summary: dict | None = None,
) -> tuple[LedgerDataset, ImportJob | None, ImportArtifact | None]:
    """创建 staged dataset（可带 job+artifact）。"""
    artifact: ImportArtifact | None = None
    job: ImportJob | None = None
    if with_job:
        artifact = ImportArtifact(
            id=uuid.uuid4(),
            project_id=project_id,
            upload_token=f"tok-{uuid.uuid4().hex[:8]}",
            status=ArtifactStatus.active,
            storage_uri=f"local:///tmp/uploads/{uuid.uuid4().hex}",
            total_size_bytes=1024,
            file_count=1,
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

    ds = await DatasetService.create_staged(
        db,
        project_id=project_id,
        year=year,
        source_summary=source_summary,
        job_id=job.id if job else None,
    )
    return ds, job, artifact


async def _create_final_audit_report_bound(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    year: int,
    dataset_id: uuid.UUID,
    status: ReportStatus = ReportStatus.final,
) -> AuditReport:
    report = AuditReport(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        company_type=CompanyType.non_listed,
        opinion_type=OpinionType.unqualified,
        status=status,
        paragraphs={},
        bound_dataset_id=dataset_id,
        dataset_bound_at=datetime.now(timezone.utc),
        is_deleted=False,
    )
    db.add(report)
    await db.flush()
    return report


# ---------------------------------------------------------------------------
# compute_expires_at
# ---------------------------------------------------------------------------


def test_compute_expires_at_transient_is_90_days() -> None:
    now = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    exp = compute_expires_at("transient", now=now)
    assert exp == now + TRANSIENT_RETENTION
    assert exp == now + timedelta(days=90)


def test_compute_expires_at_archived_is_10_years() -> None:
    now = datetime(2026, 5, 10, tzinfo=timezone.utc)
    exp = compute_expires_at("archived", now=now)
    assert exp == now + ARCHIVED_RETENTION
    assert exp == now + timedelta(days=365 * 10)


def test_compute_expires_at_legal_hold_is_none() -> None:
    assert compute_expires_at("legal_hold") is None


def test_compute_expires_at_default_now_is_aware() -> None:
    exp = compute_expires_at("transient")
    assert exp is not None
    assert exp.tzinfo is not None


# ---------------------------------------------------------------------------
# compute_retention_class
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_retention_class_default_transient(db_session: AsyncSession) -> None:
    pid = uuid.uuid4()
    ds, _job, _art = await _seed_dataset(db_session, project_id=pid)
    rc = await compute_retention_class(db_session, ds)
    assert rc == "transient"


@pytest.mark.asyncio
async def test_compute_retention_class_archived_when_final_report_bound(
    db_session: AsyncSession,
) -> None:
    pid = uuid.uuid4()
    ds, _job, _art = await _seed_dataset(db_session, project_id=pid)
    await DatasetService.activate(db_session, ds.id)
    await db_session.flush()
    await _create_final_audit_report_bound(
        db_session, project_id=pid, year=ds.year, dataset_id=ds.id,
    )
    rc = await compute_retention_class(db_session, ds)
    assert rc == "archived"


@pytest.mark.asyncio
async def test_compute_retention_class_archived_when_eqcr_approved_bound(
    db_session: AsyncSession,
) -> None:
    pid = uuid.uuid4()
    ds, _job, _art = await _seed_dataset(db_session, project_id=pid)
    await DatasetService.activate(db_session, ds.id)
    await db_session.flush()
    await _create_final_audit_report_bound(
        db_session,
        project_id=pid,
        year=ds.year,
        dataset_id=ds.id,
        status=ReportStatus.eqcr_approved,
    )
    rc = await compute_retention_class(db_session, ds)
    assert rc == "archived"


@pytest.mark.asyncio
async def test_compute_retention_class_legal_hold_flag_beats_archived(
    db_session: AsyncSession,
) -> None:
    """legal_hold 标记优先于 final 报表绑定（三档优先级第一档）。"""
    pid = uuid.uuid4()
    ds, _job, _art = await _seed_dataset(
        db_session, project_id=pid, source_summary={"legal_hold": True}
    )
    await DatasetService.activate(db_session, ds.id)
    await db_session.flush()
    # 绑定 final 报表模拟"既有 legal_hold 又被 final 绑定"
    await _create_final_audit_report_bound(
        db_session, project_id=pid, year=ds.year, dataset_id=ds.id,
    )
    rc = await compute_retention_class(db_session, ds)
    assert rc == "legal_hold"


@pytest.mark.asyncio
async def test_compute_retention_class_ignores_draft_review_status(
    db_session: AsyncSession,
) -> None:
    """draft / review 状态的报表绑定不触发 archived 升级。"""
    pid = uuid.uuid4()
    ds, _job, _art = await _seed_dataset(db_session, project_id=pid)
    await DatasetService.activate(db_session, ds.id)
    await db_session.flush()
    await _create_final_audit_report_bound(
        db_session,
        project_id=pid,
        year=ds.year,
        dataset_id=ds.id,
        status=ReportStatus.draft,
    )
    rc = await compute_retention_class(db_session, ds)
    assert rc == "transient"


# ---------------------------------------------------------------------------
# apply_retention_to_artifact / activate 集成
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_activate_writes_transient_retention_to_artifact(
    db_session: AsyncSession,
) -> None:
    pid = uuid.uuid4()
    ds, _job, art = await _seed_dataset(db_session, project_id=pid)
    # 断言预期状态
    assert art is not None
    assert art.retention_class == "transient"
    assert art.retention_expires_at is None

    await DatasetService.activate(db_session, ds.id)
    await db_session.flush()
    await db_session.refresh(art)

    assert art.retention_class == "transient"
    assert art.retention_expires_at is not None
    # 过期时间 ≈ now + 90 天（容差 2 分钟）
    # SQLite 下 DateTime(timezone=True) 返回 naive datetime；统一去 tz 做比较
    actual = art.retention_expires_at
    if actual.tzinfo is not None:
        actual = actual.replace(tzinfo=None)
    expected = datetime.now(timezone.utc).replace(tzinfo=None) + TRANSIENT_RETENTION
    delta = abs((actual - expected).total_seconds())
    assert delta < 120


@pytest.mark.asyncio
async def test_activate_writes_archived_when_bound_by_final_report(
    db_session: AsyncSession,
) -> None:
    pid = uuid.uuid4()
    ds, _job, art = await _seed_dataset(db_session, project_id=pid)
    await DatasetService.activate(db_session, ds.id)
    await db_session.flush()

    # 第一次 activate：无绑定 → transient
    await db_session.refresh(art)
    assert art.retention_class == "transient"

    # 绑 final 报表 + 再次计算 retention（模拟后续 sign_off）
    await _create_final_audit_report_bound(
        db_session, project_id=pid, year=ds.year, dataset_id=ds.id,
    )

    # 直接调用 apply_retention_to_artifact（activate 是幂等操作，对已 active 的
    # dataset 不再触发 retention apply）
    rc, exp, art_id = await apply_retention_to_artifact(db_session, ds)
    await db_session.flush()
    await db_session.refresh(art)
    assert rc == "archived"
    assert art.retention_class == "archived"
    assert art.retention_expires_at is not None
    # SQLite 下无 tzinfo，统一去 tz 做比较
    actual = art.retention_expires_at
    if actual.tzinfo is not None:
        actual = actual.replace(tzinfo=None)
    expected = datetime.now(timezone.utc).replace(tzinfo=None) + ARCHIVED_RETENTION
    # 过期时间 ≈ now + 10 年
    assert abs((actual - expected).total_seconds()) < 120
    assert art_id == art.id


@pytest.mark.asyncio
async def test_apply_retention_without_job_is_safe(db_session: AsyncSession) -> None:
    """没有 job 关联的 dataset（如迁移数据）调用不抛异常。"""
    pid = uuid.uuid4()
    ds, _job, _art = await _seed_dataset(db_session, project_id=pid, with_job=False)
    rc, exp, art_id = await apply_retention_to_artifact(db_session, ds)
    assert rc == "transient"
    assert exp is not None
    assert art_id is None  # 没有 artifact


@pytest.mark.asyncio
async def test_apply_retention_legal_hold_expires_at_is_none(
    db_session: AsyncSession,
) -> None:
    pid = uuid.uuid4()
    ds, _job, art = await _seed_dataset(
        db_session, project_id=pid, source_summary={"legal_hold": True}
    )
    rc, exp, art_id = await apply_retention_to_artifact(db_session, ds)
    assert rc == "legal_hold"
    assert exp is None
    await db_session.flush()
    await db_session.refresh(art)
    assert art.retention_class == "legal_hold"
    assert art.retention_expires_at is None
