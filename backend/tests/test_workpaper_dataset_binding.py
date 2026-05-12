"""F50 / Sprint 8.25: 底稿 / 附注 / 错报 / 报表绑定当前 active dataset 的测试。

验证 Sprint 8.17-8.19 下游对象快照绑定：
- WorkingPaper 生成时绑定当前 active dataset_id
- AuditReport 转 final 时锁定 bound_dataset_id
- DisclosureNote / UnadjustedMisstatement 创建时绑定
- 无 active dataset 时绑定字段保持 None（不抛异常）
- 多版本场景：V1→V2 切换后，新建对象绑定 V2，旧对象仍绑定 V1
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# SQLite 不支持 JSONB，需要编译器替换
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.models.base import Base  # noqa: E402

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

# 注册所有模型以便 create_all 建全量表
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401
import app.models.consolidation_models  # noqa: E402, F401
import app.models.staff_models  # noqa: E402, F401
import app.models.collaboration_models  # noqa: E402, F401
import app.models.ai_models  # noqa: E402, F401
import app.models.extension_models  # noqa: E402, F401
import app.models.phase13_models  # noqa: E402, F401
import app.models.eqcr_models  # noqa: E402, F401
import app.models.related_party_models  # noqa: E402, F401
import app.models.phase14_models  # noqa: E402, F401
import app.models.phase15_models  # noqa: E402, F401
import app.models.attachment_models  # noqa: E402, F401
import app.models.dataset_models  # noqa: E402, F401

from app.models.audit_platform_models import (  # noqa: E402
    MisstatementType,
    UnadjustedMisstatement,
)
from app.models.base import ProjectStatus, ProjectType, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.dataset_models import DatasetStatus, LedgerDataset  # noqa: E402
from app.models.report_models import (  # noqa: E402
    AuditReport,
    CompanyType,
    DisclosureNote,
    NoteStatus,
    OpinionType,
    ReportStatus,
)
from app.models.workpaper_models import (  # noqa: E402
    WorkingPaper,
    WpIndex,
    WpSourceType,
    WpStatus,
)
from app.services.dataset_query import bind_to_active_dataset  # noqa: E402

YEAR = 2024


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def project_with_dataset(db_session: AsyncSession):
    """项目 + 一个 active dataset。"""
    user = User(
        id=uuid.uuid4(),
        username="binding_tester",
        email="bt@example.com",
        hashed_password="x",
        role=UserRole.partner,
    )
    proj = Project(
        id=uuid.uuid4(),
        name="绑定测试项目",
        client_name="绑定测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        audit_period_end=date(YEAR, 12, 31),
    )
    db_session.add_all([user, proj])
    await db_session.flush()

    active_ds = LedgerDataset(
        id=uuid.uuid4(),
        project_id=proj.id,
        year=YEAR,
        status=DatasetStatus.active,
        source_type="import",
        created_by=user.id,
    )
    db_session.add(active_ds)
    await db_session.commit()

    return {"user": user, "project": proj, "active_dataset": active_ds}


@pytest_asyncio.fixture
async def project_without_dataset(db_session: AsyncSession):
    """项目但没有任何账套（对应先建底稿后导账套的场景）。"""
    user = User(
        id=uuid.uuid4(),
        username="no_ds_tester",
        email="nd@example.com",
        hashed_password="x",
        role=UserRole.partner,
    )
    proj = Project(
        id=uuid.uuid4(),
        name="无账套项目",
        client_name="无账套客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        audit_period_end=date(YEAR, 12, 31),
    )
    db_session.add_all([user, proj])
    await db_session.commit()
    return {"user": user, "project": proj}


# ---------------------------------------------------------------------------
# 场景 1：底稿绑定当前 active dataset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workpaper_binds_active_dataset(
    db_session: AsyncSession, project_with_dataset
):
    """新建底稿通过 bind_to_active_dataset 绑定当前 active dataset_id。"""
    proj = project_with_dataset["project"]
    active_ds = project_with_dataset["active_dataset"]

    wp_index = WpIndex(
        project_id=proj.id,
        wp_code="D100",
        wp_name="应收账款",
        audit_cycle="D",
        status=WpStatus.not_started,
    )
    db_session.add(wp_index)
    await db_session.flush()

    wp = WorkingPaper(
        project_id=proj.id,
        wp_index_id=wp_index.id,
        file_path="/tmp/d100.xlsx",
        source_type=WpSourceType.template,
    )
    db_session.add(wp)
    # 应用绑定
    bound_id = await bind_to_active_dataset(db_session, wp, proj.id, YEAR)
    await db_session.flush()

    assert bound_id == active_ds.id
    assert wp.bound_dataset_id == active_ds.id
    assert wp.dataset_bound_at is not None


# ---------------------------------------------------------------------------
# 场景 2：无 active dataset 时字段保持 None（不抛）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workpaper_binding_null_when_no_active_dataset(
    db_session: AsyncSession, project_without_dataset
):
    """没有 active dataset 时 bound_dataset_id 保持 None，不抛异常。"""
    proj = project_without_dataset["project"]

    wp_index = WpIndex(
        project_id=proj.id,
        wp_code="N100",
        wp_name="存货",
        audit_cycle="N",
        status=WpStatus.not_started,
    )
    db_session.add(wp_index)
    await db_session.flush()

    wp = WorkingPaper(
        project_id=proj.id,
        wp_index_id=wp_index.id,
        file_path="/tmp/n100.xlsx",
        source_type=WpSourceType.template,
    )
    db_session.add(wp)
    bound_id = await bind_to_active_dataset(db_session, wp, proj.id, YEAR)
    await db_session.flush()

    assert bound_id is None
    assert wp.bound_dataset_id is None
    assert wp.dataset_bound_at is None


# ---------------------------------------------------------------------------
# 场景 3：AuditReport 转 final 时锁定 dataset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_report_binds_on_final(
    db_session: AsyncSession, project_with_dataset
):
    """AuditReport 转 final 时通过 audit_report_service.update_status 锁定绑定。"""
    proj = project_with_dataset["project"]
    active_ds = project_with_dataset["active_dataset"]

    # 用 ReportStatus.eqcr_approved 起步（final 前的合法前态）
    report = AuditReport(
        id=uuid.uuid4(),
        project_id=proj.id,
        year=YEAR,
        opinion_type=OpinionType.unqualified,
        company_type=CompanyType.non_listed,
        status=ReportStatus.eqcr_approved,
        paragraphs={"关键审计事项段": "无需披露"},
    )
    db_session.add(report)
    await db_session.commit()

    # 直接调 service 更新状态
    from app.services.audit_report_service import AuditReportService

    svc = AuditReportService(db_session)
    result = await svc.update_status(report.id, ReportStatus.final)
    await db_session.commit()

    await db_session.refresh(result)
    assert result.status == ReportStatus.final
    assert result.bound_dataset_id == active_ds.id
    assert result.dataset_bound_at is not None


@pytest.mark.asyncio
async def test_audit_report_not_rebind_when_already_bound(
    db_session: AsyncSession, project_with_dataset
):
    """已绑定的报表重复 update_status(final) 不覆盖已有绑定 - 首次锁定不可变。"""
    proj = project_with_dataset["project"]
    active_ds = project_with_dataset["active_dataset"]

    # 预置一个"已签字但用旧 dataset 绑定"的报告
    old_ds_id = uuid.uuid4()
    report = AuditReport(
        id=uuid.uuid4(),
        project_id=proj.id,
        year=YEAR,
        opinion_type=OpinionType.unqualified,
        company_type=CompanyType.non_listed,
        status=ReportStatus.eqcr_approved,
        bound_dataset_id=old_ds_id,
    )
    db_session.add(report)
    await db_session.commit()

    from app.services.audit_report_service import AuditReportService

    svc = AuditReportService(db_session)
    await svc.update_status(report.id, ReportStatus.final)
    await db_session.commit()
    await db_session.refresh(report)

    # 绑定字段保持原值，未被 active_ds 覆盖
    assert report.bound_dataset_id == old_ds_id
    assert report.bound_dataset_id != active_ds.id


# ---------------------------------------------------------------------------
# 场景 4：DisclosureNote 创建时绑定
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disclosure_note_binds_on_create(
    db_session: AsyncSession, project_with_dataset
):
    """DisclosureNote 创建时通过 bind_to_active_dataset 绑定。"""
    proj = project_with_dataset["project"]
    active_ds = project_with_dataset["active_dataset"]

    note = DisclosureNote(
        project_id=proj.id,
        year=YEAR,
        note_section="1",
        section_title="公司基本情况",
        status=NoteStatus.draft,
    )
    db_session.add(note)
    await bind_to_active_dataset(db_session, note, proj.id, YEAR)
    await db_session.flush()

    assert note.bound_dataset_id == active_ds.id
    assert note.dataset_bound_at is not None


# ---------------------------------------------------------------------------
# 场景 5：UnadjustedMisstatement 通过 service 创建自动绑定
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_misstatement_binds_via_service(
    db_session: AsyncSession, project_with_dataset
):
    """misstatement_service.create_misstatement 内部调用 bind_to_active_dataset。"""
    from app.models.audit_platform_schemas import MisstatementCreate
    from app.services.misstatement_service import UnadjustedMisstatementService

    proj = project_with_dataset["project"]
    active_ds = project_with_dataset["active_dataset"]
    user = project_with_dataset["user"]

    svc = UnadjustedMisstatementService(db_session)
    payload = MisstatementCreate(
        year=YEAR,
        misstatement_description="测试错报",
        misstatement_amount=Decimal("12345.67"),
        misstatement_type=MisstatementType.factual,
        affected_account_code="1122",
        affected_account_name="应收账款",
    )
    result = await svc.create_misstatement(proj.id, payload, created_by=user.id)
    await db_session.commit()

    # 查回 DB 确认绑定
    row = (
        await db_session.execute(
            __import__("sqlalchemy").select(UnadjustedMisstatement).where(
                UnadjustedMisstatement.id == uuid.UUID(result.id)
                if isinstance(result.id, str)
                else UnadjustedMisstatement.id == result.id
            )
        )
    ).scalar_one()

    assert row.bound_dataset_id == active_ds.id
    assert row.dataset_bound_at is not None


# ---------------------------------------------------------------------------
# 场景 6：多版本 — 新建对象绑定最新 active，旧对象保留旧绑定
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_different_datasets_for_different_objects(
    db_session: AsyncSession, project_with_dataset
):
    """创建 V1 绑定的 wp → 切到 V2 → 新 wp 绑定 V2 → V1 的 wp 仍保持 V1 绑定。"""
    import sqlalchemy as sa

    proj = project_with_dataset["project"]
    v1 = project_with_dataset["active_dataset"]
    user = project_with_dataset["user"]

    # Phase 1: 创建一个底稿绑定 V1
    wp_index_1 = WpIndex(
        project_id=proj.id,
        wp_code="D101",
        wp_name="应收账款V1",
        audit_cycle="D",
        status=WpStatus.not_started,
    )
    db_session.add(wp_index_1)
    await db_session.flush()
    wp_v1 = WorkingPaper(
        project_id=proj.id,
        wp_index_id=wp_index_1.id,
        file_path="/tmp/d101.xlsx",
        source_type=WpSourceType.template,
    )
    db_session.add(wp_v1)
    await bind_to_active_dataset(db_session, wp_v1, proj.id, YEAR)
    await db_session.commit()
    assert wp_v1.bound_dataset_id == v1.id

    # Phase 2: 切换到 V2
    await db_session.execute(
        sa.update(LedgerDataset)
        .where(LedgerDataset.id == v1.id)
        .values(status=DatasetStatus.superseded)
    )
    v2 = LedgerDataset(
        id=uuid.uuid4(),
        project_id=proj.id,
        year=YEAR,
        status=DatasetStatus.active,
        source_type="import",
        previous_dataset_id=v1.id,
        created_by=user.id,
    )
    db_session.add(v2)
    await db_session.commit()

    # Phase 3: 新底稿绑定 V2
    wp_index_2 = WpIndex(
        project_id=proj.id,
        wp_code="D102",
        wp_name="应收账款V2",
        audit_cycle="D",
        status=WpStatus.not_started,
    )
    db_session.add(wp_index_2)
    await db_session.flush()
    wp_v2 = WorkingPaper(
        project_id=proj.id,
        wp_index_id=wp_index_2.id,
        file_path="/tmp/d102.xlsx",
        source_type=WpSourceType.template,
    )
    db_session.add(wp_v2)
    await bind_to_active_dataset(db_session, wp_v2, proj.id, YEAR)
    await db_session.commit()

    # 验证独立绑定
    await db_session.refresh(wp_v1)
    await db_session.refresh(wp_v2)
    assert wp_v1.bound_dataset_id == v1.id
    assert wp_v2.bound_dataset_id == v2.id
