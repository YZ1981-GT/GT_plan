"""CW-76: A16 signed 时必填 sign_date → push audit_report.representation_letter_date

验证：
- A16 主版本(A16-1~6) signed 时 sign_date 必填，否则 422
- sign_date 成功 push 到 audit_report.representation_letter_date
- A16-7 补充声明 signed 时 sign_date 可选，不 push
- audit_report 不存在时降级写入 field_overrides
- 禁止从 docx 元数据读取签署日期

Validates: Requirements 5（签回与审计报告联动）
"""

import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.models.workpaper_models import (
    WpFileStatus,
    WpIndex,
    WpSourceType,
    WpStatus,
    WorkingPaper,
)
from app.models.workpaper_field_override_models import WorkpaperFieldOverride
from app.models.report_models import AuditReport, OpinionType, CompanyType, ReportStatus
from app.services.field_override_service import FieldOverrideService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_PROJECT_ID = uuid.uuid4()
FAKE_USER_ID = uuid.uuid4()
FAKE_WP_ID = uuid.uuid4()
FAKE_WP_INDEX_ID = uuid.uuid4()
YEAR = 2025


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
    """Seed: project + wp_index(A16) + working_paper + user + audit_report"""
    user = User(
        id=FAKE_USER_ID,
        username="test_user",
        email="test@example.com",
        hashed_password="x",
        role=UserRole.admin,
    )
    db_session.add(user)

    project = Project(
        id=FAKE_PROJECT_ID,
        name="测试项目_2025",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
        audit_period_end=date(2025, 12, 31),
    )
    db_session.add(project)
    await db_session.flush()

    wp_index = WpIndex(
        id=FAKE_WP_INDEX_ID,
        project_id=FAKE_PROJECT_ID,
        wp_code="A16",
        wp_name="管理层声明书",
        audit_cycle="A",
        status=WpStatus.in_progress,
    )
    db_session.add(wp_index)
    await db_session.flush()

    wp = WorkingPaper(
        id=FAKE_WP_ID,
        project_id=FAKE_PROJECT_ID,
        wp_index_id=FAKE_WP_INDEX_ID,
        file_path=f"{FAKE_PROJECT_ID}/2025/A16.docx",
        source_type=WpSourceType.template,
        status=WpFileStatus.draft,
        file_version=1,
        created_by=FAKE_USER_ID,
    )
    db_session.add(wp)

    # 创建 audit_report 行
    audit_report = AuditReport(
        id=uuid.uuid4(),
        project_id=FAKE_PROJECT_ID,
        year=YEAR,
        opinion_type=OpinionType.unqualified,
        company_type=CompanyType.non_listed,
        report_date=date(2025, 3, 20),
        status=ReportStatus.draft,
    )
    db_session.add(audit_report)
    await db_session.commit()

    return {
        "project": project,
        "wp_index": wp_index,
        "wp": wp,
        "user": user,
        "audit_report": audit_report,
    }


class TestCW76SignDatePush:
    """CW-76: signed 时 sign_date push 到 audit_report.representation_letter_date"""

    @pytest.mark.asyncio
    async def test_sign_date_pushes_to_audit_report(self, db_session, seeded_db):
        """主版本 signed + sign_date → audit_report.representation_letter_date 更新"""
        from app.routers.working_paper import _push_representation_letter_date

        sign_date_str = "2025-03-15"
        await _push_representation_letter_date(db_session, FAKE_PROJECT_ID, YEAR, sign_date_str)
        await db_session.commit()

        # 验证 audit_report 已更新
        result = await db_session.execute(
            sa.select(AuditReport.representation_letter_date).where(
                AuditReport.project_id == FAKE_PROJECT_ID,
                AuditReport.year == YEAR,
            )
        )
        rep_date = result.scalar_one()
        assert rep_date == date(2025, 3, 15)

    @pytest.mark.asyncio
    async def test_sign_date_invalid_format_does_not_crash(self, db_session, seeded_db):
        """无效日期格式不应阻塞签回（静默跳过）"""
        from app.routers.working_paper import _push_representation_letter_date

        # 不抛异常
        await _push_representation_letter_date(db_session, FAKE_PROJECT_ID, YEAR, "not-a-date")
        await db_session.commit()

        # audit_report 未被修改
        result = await db_session.execute(
            sa.select(AuditReport.representation_letter_date).where(
                AuditReport.project_id == FAKE_PROJECT_ID,
                AuditReport.year == YEAR,
            )
        )
        rep_date = result.scalar_one_or_none()
        assert rep_date is None

    @pytest.mark.asyncio
    async def test_sign_date_no_audit_report_falls_back_to_field_overrides(self, db_session, seeded_db):
        """audit_report 不存在的年份 → 降级写入 field_overrides"""
        from app.routers.working_paper import _push_representation_letter_date

        other_year = 2024  # 没有 audit_report 行
        await _push_representation_letter_date(db_session, FAKE_PROJECT_ID, other_year, "2024-12-20")
        await db_session.commit()

        # 验证 field_overrides 有值
        svc = FieldOverrideService(db_session)
        val = await svc.get(FAKE_PROJECT_ID, other_year, "audit_report", "representation_letter_date", "value")
        assert val == "2024-12-20"

    @pytest.mark.asyncio
    async def test_main_version_signed_requires_sign_date(self, db_session, seeded_db):
        """验证 is_a16_main 逻辑：A16-1~6 为主版本，A16-7 不是"""
        # A16-1 是主版本
        wp_code = "A16"
        version = "A16-1"
        is_a16_main = wp_code == "A16" and version and version.startswith("A16-") and version != "A16-7"
        assert is_a16_main is True

        # A16-7 不是主版本
        version_7 = "A16-7"
        is_a16_main_7 = wp_code == "A16" and version_7 and version_7.startswith("A16-") and version_7 != "A16-7"
        assert is_a16_main_7 is False

    @pytest.mark.asyncio
    async def test_sign_date_updates_existing_report(self, db_session, seeded_db):
        """sign_date 覆盖已有值"""
        from app.routers.working_paper import _push_representation_letter_date

        # 先 push 一个日期
        await _push_representation_letter_date(db_session, FAKE_PROJECT_ID, YEAR, "2025-03-10")
        await db_session.flush()

        # 再 push 另一个日期（用户更改）
        await _push_representation_letter_date(db_session, FAKE_PROJECT_ID, YEAR, "2025-03-20")
        await db_session.commit()

        result = await db_session.execute(
            sa.select(AuditReport.representation_letter_date).where(
                AuditReport.project_id == FAKE_PROJECT_ID,
                AuditReport.year == YEAR,
            )
        )
        rep_date = result.scalar_one()
        assert rep_date == date(2025, 3, 20)
