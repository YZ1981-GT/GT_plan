"""底稿模型测试 — 验证8张底稿相关表的创建和基本CRUD

Validates: Requirements 10.1-10.8
"""

import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.models.workpaper_models import (
    RegionType,
    ReviewCommentStatus,
    ReviewRecord,
    WorkingPaper,
    WpCrossRef,
    WpFileStatus,
    WpIndex,
    WpQcResult,
    WpSourceType,
    WpStatus,
    WpTemplate,
    WpTemplateMeta,
    WpTemplateSet,
    WpTemplateStatus,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """创建基础测试数据：用户和项目"""
    user = User(
        id=FAKE_USER_ID,
        username="wp_test_user",
        email="wp_test@example.com",
        hashed_password="hashed",
        role=UserRole.admin,
    )
    db_session.add(user)
    await db_session.flush()

    project = Project(
        id=FAKE_PROJECT_ID,
        name="底稿测试项目_2025",
        client_name="底稿测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.commit()
    return FAKE_PROJECT_ID


# ===== 1. wp_template =====


@pytest.mark.asyncio
async def test_wp_template_crud(db_session: AsyncSession):
    """wp_template 表基本CRUD"""
    tpl = WpTemplate(
        template_code="E1-1",
        template_name="货币资金审定表",
        audit_cycle="货币资金",
        applicable_standard="enterprise",
        version_major=1,
        version_minor=0,
        status=WpTemplateStatus.draft,
        file_path="templates/E1-1/1.0/E1-1.xlsx",
        description="货币资金审定表模板",
        created_by=FAKE_USER_ID,
    )
    db_session.add(tpl)
    await db_session.commit()

    result = await db_session.execute(
        select(WpTemplate).where(WpTemplate.template_code == "E1-1")
    )
    row = result.scalar_one()
    assert row.template_name == "货币资金审定表"
    assert row.audit_cycle == "货币资金"
    assert row.version_major == 1
    assert row.version_minor == 0
    assert row.status == WpTemplateStatus.draft
    assert row.is_deleted is False


@pytest.mark.asyncio
async def test_wp_template_version_update(db_session: AsyncSession):
    """wp_template 版本更新"""
    tpl = WpTemplate(
        template_code="E1-2",
        template_name="银行存款审定表",
        file_path="templates/E1-2/1.0/E1-2.xlsx",
        version_major=1,
        version_minor=0,
    )
    db_session.add(tpl)
    await db_session.flush()

    tpl.version_minor = 1
    tpl.status = WpTemplateStatus.published
    await db_session.commit()

    result = await db_session.execute(
        select(WpTemplate).where(WpTemplate.id == tpl.id)
    )
    row = result.scalar_one()
    assert row.version_minor == 1
    assert row.status == WpTemplateStatus.published


# ===== 2. wp_template_meta =====


@pytest.mark.asyncio
async def test_wp_template_meta_crud(db_session: AsyncSession):
    """wp_template_meta 表基本CRUD"""
    tpl = WpTemplate(
        template_code="E1-3",
        template_name="测试模板",
        file_path="templates/E1-3/1.0/E1-3.xlsx",
    )
    db_session.add(tpl)
    await db_session.flush()

    meta = WpTemplateMeta(
        template_id=tpl.id,
        range_name="WP_CONCLUSION",
        region_type=RegionType.conclusion,
        description="结论区域",
    )
    db_session.add(meta)
    await db_session.commit()

    result = await db_session.execute(
        select(WpTemplateMeta).where(WpTemplateMeta.template_id == tpl.id)
    )
    row = result.scalar_one()
    assert row.range_name == "WP_CONCLUSION"
    assert row.region_type == RegionType.conclusion


@pytest.mark.asyncio
async def test_wp_template_meta_all_region_types(db_session: AsyncSession):
    """验证所有区域类型枚举"""
    tpl = WpTemplate(
        template_code="E1-4",
        template_name="区域类型测试",
        file_path="templates/E1-4/1.0/E1-4.xlsx",
    )
    db_session.add(tpl)
    await db_session.flush()

    for rt in RegionType:
        meta = WpTemplateMeta(
            template_id=tpl.id,
            range_name=f"TEST_{rt.value}",
            region_type=rt,
        )
        db_session.add(meta)
    await db_session.commit()

    result = await db_session.execute(
        select(WpTemplateMeta).where(WpTemplateMeta.template_id == tpl.id)
    )
    rows = result.scalars().all()
    types = {r.region_type for r in rows}
    assert types == {
        RegionType.formula,
        RegionType.manual,
        RegionType.ai_fill,
        RegionType.conclusion,
        RegionType.cross_ref,
    }


# ===== 3. wp_template_set =====


@pytest.mark.asyncio
async def test_wp_template_set_crud(db_session: AsyncSession):
    """wp_template_set 表基本CRUD"""
    ts = WpTemplateSet(
        set_name="标准年审",
        template_codes=["E1-1", "E1-2", "F1-1"],
        applicable_audit_type="annual",
        applicable_standard="enterprise",
        description="标准年审模板集",
    )
    db_session.add(ts)
    await db_session.commit()

    result = await db_session.execute(
        select(WpTemplateSet).where(WpTemplateSet.set_name == "标准年审")
    )
    row = result.scalar_one()
    assert row.template_codes == ["E1-1", "E1-2", "F1-1"]
    assert row.applicable_audit_type == "annual"
    assert row.is_deleted is False


# ===== 4. wp_index =====


@pytest.mark.asyncio
async def test_wp_index_crud(db_session: AsyncSession, seeded_db):
    """wp_index 表基本CRUD"""
    pid = seeded_db
    idx = WpIndex(
        project_id=pid,
        wp_code="E1-1",
        wp_name="货币资金审定表",
        audit_cycle="货币资金",
        status=WpStatus.not_started,
        cross_ref_codes=["E1-2", "E1-3"],
    )
    db_session.add(idx)
    await db_session.commit()

    result = await db_session.execute(
        select(WpIndex).where(WpIndex.project_id == pid)
    )
    row = result.scalar_one()
    assert row.wp_code == "E1-1"
    assert row.status == WpStatus.not_started
    assert row.cross_ref_codes == ["E1-2", "E1-3"]
    assert row.assigned_to is None
    assert row.reviewer is None


@pytest.mark.asyncio
async def test_wp_index_status_update(db_session: AsyncSession, seeded_db):
    """wp_index 状态更新"""
    pid = seeded_db
    idx = WpIndex(
        project_id=pid,
        wp_code="E1-5",
        wp_name="测试底稿",
    )
    db_session.add(idx)
    await db_session.flush()

    idx.status = WpStatus.in_progress
    idx.assigned_to = FAKE_USER_ID
    await db_session.commit()

    result = await db_session.execute(
        select(WpIndex).where(WpIndex.id == idx.id)
    )
    row = result.scalar_one()
    assert row.status == WpStatus.in_progress
    assert row.assigned_to == FAKE_USER_ID


# ===== 5. working_paper =====


@pytest.mark.asyncio
async def test_working_paper_crud(db_session: AsyncSession, seeded_db):
    """working_paper 表基本CRUD"""
    pid = seeded_db
    idx = WpIndex(
        project_id=pid,
        wp_code="E1-6",
        wp_name="底稿文件测试",
    )
    db_session.add(idx)
    await db_session.flush()

    wp = WorkingPaper(
        project_id=pid,
        wp_index_id=idx.id,
        file_path=f"/{pid}/2025/E1-6.xlsx",
        source_type=WpSourceType.template,
        status=WpFileStatus.draft,
        file_version=1,
        created_by=FAKE_USER_ID,
    )
    db_session.add(wp)
    await db_session.commit()

    result = await db_session.execute(
        select(WorkingPaper).where(WorkingPaper.project_id == pid)
    )
    row = result.scalar_one()
    assert row.source_type == WpSourceType.template
    assert row.status == WpFileStatus.draft
    assert row.file_version == 1
    assert row.last_parsed_at is None


@pytest.mark.asyncio
async def test_working_paper_version_increment(db_session: AsyncSession, seeded_db):
    """working_paper 版本递增"""
    pid = seeded_db
    idx = WpIndex(
        project_id=pid,
        wp_code="E1-7",
        wp_name="版本测试",
    )
    db_session.add(idx)
    await db_session.flush()

    wp = WorkingPaper(
        project_id=pid,
        wp_index_id=idx.id,
        file_path=f"/{pid}/2025/E1-7.xlsx",
        source_type=WpSourceType.template,
    )
    db_session.add(wp)
    await db_session.flush()

    wp.file_version = 2
    wp.status = WpFileStatus.edit_complete
    wp.last_parsed_at = datetime.now()
    await db_session.commit()

    result = await db_session.execute(
        select(WorkingPaper).where(WorkingPaper.id == wp.id)
    )
    row = result.scalar_one()
    assert row.file_version == 2
    assert row.status == WpFileStatus.edit_complete
    assert row.last_parsed_at is not None


# ===== 6. wp_cross_ref =====


@pytest.mark.asyncio
async def test_wp_cross_ref_crud(db_session: AsyncSession, seeded_db):
    """wp_cross_ref 表基本CRUD"""
    pid = seeded_db
    idx = WpIndex(
        project_id=pid,
        wp_code="E1-8",
        wp_name="交叉引用测试",
    )
    db_session.add(idx)
    await db_session.flush()

    wp = WorkingPaper(
        project_id=pid,
        wp_index_id=idx.id,
        file_path=f"/{pid}/2025/E1-8.xlsx",
        source_type=WpSourceType.template,
    )
    db_session.add(wp)
    await db_session.flush()

    xref = WpCrossRef(
        project_id=pid,
        source_wp_id=wp.id,
        target_wp_code="E1-9",
        cell_reference="B5",
    )
    db_session.add(xref)
    await db_session.commit()

    result = await db_session.execute(
        select(WpCrossRef).where(WpCrossRef.project_id == pid)
    )
    row = result.scalar_one()
    assert row.target_wp_code == "E1-9"
    assert row.cell_reference == "B5"


# ===== 7. wp_qc_results =====


@pytest.mark.asyncio
async def test_wp_qc_result_crud(db_session: AsyncSession, seeded_db):
    """wp_qc_results 表基本CRUD"""
    pid = seeded_db
    idx = WpIndex(
        project_id=pid,
        wp_code="E1-10",
        wp_name="QC测试",
    )
    db_session.add(idx)
    await db_session.flush()

    wp = WorkingPaper(
        project_id=pid,
        wp_index_id=idx.id,
        file_path=f"/{pid}/2025/E1-10.xlsx",
        source_type=WpSourceType.template,
    )
    db_session.add(wp)
    await db_session.flush()

    qc = WpQcResult(
        working_paper_id=wp.id,
        check_timestamp=datetime.now(),
        findings=[
            {
                "rule_id": "QC-01",
                "severity": "blocking",
                "message": "结论区未填写",
            }
        ],
        passed=False,
        blocking_count=1,
        warning_count=0,
        info_count=0,
        checked_by=FAKE_USER_ID,
    )
    db_session.add(qc)
    await db_session.commit()

    result = await db_session.execute(
        select(WpQcResult).where(WpQcResult.working_paper_id == wp.id)
    )
    row = result.scalar_one()
    assert row.passed is False
    assert row.blocking_count == 1
    assert len(row.findings) == 1
    assert row.findings[0]["rule_id"] == "QC-01"


@pytest.mark.asyncio
async def test_wp_qc_result_passed(db_session: AsyncSession, seeded_db):
    """wp_qc_results 通过场景"""
    pid = seeded_db
    idx = WpIndex(
        project_id=pid,
        wp_code="E1-11",
        wp_name="QC通过测试",
    )
    db_session.add(idx)
    await db_session.flush()

    wp = WorkingPaper(
        project_id=pid,
        wp_index_id=idx.id,
        file_path=f"/{pid}/2025/E1-11.xlsx",
        source_type=WpSourceType.template,
    )
    db_session.add(wp)
    await db_session.flush()

    qc = WpQcResult(
        working_paper_id=wp.id,
        check_timestamp=datetime.now(),
        findings=[],
        passed=True,
        blocking_count=0,
        warning_count=0,
        info_count=0,
    )
    db_session.add(qc)
    await db_session.commit()

    result = await db_session.execute(
        select(WpQcResult).where(WpQcResult.working_paper_id == wp.id)
    )
    row = result.scalar_one()
    assert row.passed is True
    assert row.blocking_count == 0


# ===== 8. review_records =====


@pytest.mark.asyncio
async def test_review_record_crud(db_session: AsyncSession, seeded_db):
    """review_records 表基本CRUD"""
    pid = seeded_db
    idx = WpIndex(
        project_id=pid,
        wp_code="E1-12",
        wp_name="复核测试",
    )
    db_session.add(idx)
    await db_session.flush()

    wp = WorkingPaper(
        project_id=pid,
        wp_index_id=idx.id,
        file_path=f"/{pid}/2025/E1-12.xlsx",
        source_type=WpSourceType.template,
    )
    db_session.add(wp)
    await db_session.flush()

    review = ReviewRecord(
        working_paper_id=wp.id,
        cell_reference="C10",
        comment_text="此处数据需要核实",
        commenter_id=FAKE_USER_ID,
        status=ReviewCommentStatus.open,
    )
    db_session.add(review)
    await db_session.commit()

    result = await db_session.execute(
        select(ReviewRecord).where(ReviewRecord.working_paper_id == wp.id)
    )
    row = result.scalar_one()
    assert row.comment_text == "此处数据需要核实"
    assert row.status == ReviewCommentStatus.open
    assert row.cell_reference == "C10"
    assert row.reply_text is None


@pytest.mark.asyncio
async def test_review_record_reply_and_resolve(db_session: AsyncSession, seeded_db):
    """review_records 回复和解决"""
    pid = seeded_db
    idx = WpIndex(
        project_id=pid,
        wp_code="E1-13",
        wp_name="复核流程测试",
    )
    db_session.add(idx)
    await db_session.flush()

    wp = WorkingPaper(
        project_id=pid,
        wp_index_id=idx.id,
        file_path=f"/{pid}/2025/E1-13.xlsx",
        source_type=WpSourceType.template,
    )
    db_session.add(wp)
    await db_session.flush()

    review = ReviewRecord(
        working_paper_id=wp.id,
        comment_text="请补充说明",
        commenter_id=FAKE_USER_ID,
    )
    db_session.add(review)
    await db_session.flush()

    # Reply
    review.status = ReviewCommentStatus.replied
    review.reply_text = "已补充完毕"
    review.replier_id = FAKE_USER_ID
    review.replied_at = datetime.now()
    await db_session.commit()

    result = await db_session.execute(
        select(ReviewRecord).where(ReviewRecord.id == review.id)
    )
    row = result.scalar_one()
    assert row.status == ReviewCommentStatus.replied
    assert row.reply_text == "已补充完毕"

    # Resolve
    row.status = ReviewCommentStatus.resolved
    row.resolved_by = FAKE_USER_ID
    row.resolved_at = datetime.now()
    await db_session.commit()

    result = await db_session.execute(
        select(ReviewRecord).where(ReviewRecord.id == review.id)
    )
    resolved = result.scalar_one()
    assert resolved.status == ReviewCommentStatus.resolved
    assert resolved.resolved_by == FAKE_USER_ID
    assert resolved.resolved_at is not None


# ===== 枚举类型测试 =====


@pytest.mark.asyncio
async def test_all_wp_statuses(db_session: AsyncSession, seeded_db):
    """验证所有底稿索引状态枚举"""
    pid = seeded_db
    for i, st in enumerate(WpStatus):
        idx = WpIndex(
            project_id=pid,
            wp_code=f"STATUS-{i}",
            wp_name=f"状态测试-{st.value}",
            status=st,
        )
        db_session.add(idx)
    await db_session.commit()

    result = await db_session.execute(
        select(WpIndex).where(WpIndex.project_id == pid)
    )
    rows = result.scalars().all()
    statuses = {r.status for r in rows}
    assert statuses == {
        WpStatus.not_started,
        WpStatus.in_progress,
        WpStatus.draft_complete,
        WpStatus.review_passed,
        WpStatus.archived,
    }


@pytest.mark.asyncio
async def test_all_wp_file_statuses(db_session: AsyncSession, seeded_db):
    """验证所有底稿文件状态枚举"""
    pid = seeded_db
    for i, st in enumerate(WpFileStatus):
        idx = WpIndex(
            project_id=pid,
            wp_code=f"FSTATUS-{i}",
            wp_name=f"文件状态测试-{st.value}",
        )
        db_session.add(idx)
        await db_session.flush()

        wp = WorkingPaper(
            project_id=pid,
            wp_index_id=idx.id,
            file_path=f"/{pid}/2025/FSTATUS-{i}.xlsx",
            source_type=WpSourceType.template,
            status=st,
        )
        db_session.add(wp)
    await db_session.commit()

    result = await db_session.execute(
        select(WorkingPaper).where(WorkingPaper.project_id == pid)
    )
    rows = result.scalars().all()
    statuses = {r.status for r in rows}
    assert statuses == {
        WpFileStatus.draft,
        WpFileStatus.edit_complete,
        WpFileStatus.review_level1_passed,
        WpFileStatus.review_level2_passed,
        WpFileStatus.archived,
    }
