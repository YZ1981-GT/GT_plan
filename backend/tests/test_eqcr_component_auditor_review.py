"""Sprint 3 验收：组成部分审计师 EQCR 复核集成测试

验证：
- 合并项目的 EQCR 可录入 domain='component_auditor' 意见
- 组成部分审计师聚合查询正常
- 年度独立性声明服务功能完整
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

# 注册所有模型
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401
import app.models.consolidation_models  # noqa: E402, F401
import app.models.staff_models  # noqa: E402, F401
import app.models.collaboration_models  # noqa: E402, F401
import app.models.ai_models  # noqa: E402, F401
import app.models.extension_models  # noqa: E402, F401
import app.models.gt_coding_models  # noqa: E402, F401
import app.models.t_account_models  # noqa: E402, F401
import app.models.attachment_models  # noqa: E402, F401
import app.models.phase13_models  # noqa: E402, F401
import app.models.eqcr_models  # noqa: E402, F401
import app.models.related_party_models  # noqa: E402, F401
import app.models.independence_models  # noqa: E402, F401

from app.models.base import ProjectStatus, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.staff_models import ProjectAssignment, StaffMember  # noqa: E402
from app.models.eqcr_models import EqcrOpinion  # noqa: E402
from app.models.consolidation_models import ComponentAuditor, CompetenceRating  # noqa: E402


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def consolidated_project_setup(db_session: AsyncSession):
    """创建合并审计项目 + 组成部分审计师 + EQCR 委派。"""
    eqcr_user = User(
        id=uuid.uuid4(),
        username="eqcr_consol",
        email="eqcr_consol@test.com",
        hashed_password="x",
        role=UserRole.partner,
    )
    db_session.add(eqcr_user)
    await db_session.flush()

    eqcr_staff = StaffMember(
        id=uuid.uuid4(),
        user_id=eqcr_user.id,
        name="EQCR 合伙人（合并）",
        employee_no="EC01",
    )
    db_session.add(eqcr_staff)
    await db_session.flush()

    project = Project(
        id=uuid.uuid4(),
        name="集团审计项目",
        client_name="集团客户",
        status=ProjectStatus.execution,
        audit_period_start=date(2025, 1, 1),
        audit_period_end=date(2025, 12, 31),
        report_scope="consolidated",
    )
    db_session.add(project)
    await db_session.flush()

    assignment = ProjectAssignment(
        id=uuid.uuid4(),
        project_id=project.id,
        staff_id=eqcr_staff.id,
        role="eqcr",
    )
    db_session.add(assignment)

    # 组成部分审计师（reliable + unreliable 对应 design "A 级 + D 级"）
    auditor1 = ComponentAuditor(
        id=uuid.uuid4(),
        project_id=project.id,
        company_code="SUB001",
        firm_name="子公司审计师A",
        competence_rating=CompetenceRating.reliable,
        independence_confirmed=True,
    )
    auditor2 = ComponentAuditor(
        id=uuid.uuid4(),
        project_id=project.id,
        company_code="SUB002",
        firm_name="子公司审计师B",
        competence_rating=CompetenceRating.unreliable,
        independence_confirmed=False,
    )
    db_session.add_all([auditor1, auditor2])
    await db_session.flush()

    return {
        "eqcr_user": eqcr_user,
        "project": project,
        "auditor1": auditor1,
        "auditor2": auditor2,
    }


@pytest.mark.asyncio
async def test_component_auditor_opinion_storage(
    db_session: AsyncSession, consolidated_project_setup
):
    """EQCR 对 D 级组成部分审计师录入异议，domain='component_auditor'。"""
    data = consolidated_project_setup
    project_id = data["project"].id
    auditor2_id = data["auditor2"].id
    eqcr_user_id = data["eqcr_user"].id

    opinion = EqcrOpinion(
        project_id=project_id,
        domain="component_auditor",
        verdict="disagree",
        comment="能力评级 D，不建议依赖其审计结果",
        extra_payload={
            "auditor_id": str(auditor2_id),
            "auditor_name": "子公司审计师B",
        },
        created_by=eqcr_user_id,
    )
    db_session.add(opinion)
    await db_session.flush()

    q = sa.select(EqcrOpinion).where(
        EqcrOpinion.project_id == project_id,
        EqcrOpinion.domain == "component_auditor",
    )
    stored = (await db_session.execute(q)).scalar_one()
    assert stored.verdict == "disagree"
    assert stored.extra_payload["auditor_id"] == str(auditor2_id)


@pytest.mark.asyncio
async def test_component_auditor_aggregation_query(
    db_session: AsyncSession, consolidated_project_setup
):
    """验证组成部分审计师聚合查询返回正确数据。"""
    data = consolidated_project_setup
    project_id = data["project"].id

    q = (
        sa.select(ComponentAuditor)
        .where(
            ComponentAuditor.project_id == project_id,
            ComponentAuditor.is_deleted == False,  # noqa: E712
        )
        .order_by(ComponentAuditor.company_code)
    )
    auditors = list((await db_session.execute(q)).scalars().all())
    assert len(auditors) == 2
    assert auditors[0].firm_name == "子公司审计师A"


@pytest.mark.asyncio
async def test_annual_independence_service_loads_questions(db_session: AsyncSession):
    """验证年度独立性声明服务加载问题集。"""
    from app.services.eqcr_independence_service import EqcrIndependenceService

    svc = EqcrIndependenceService(db_session)
    questions = svc.get_annual_questions()
    assert len(questions) >= 30
    # 第一题应该是持股类
    assert questions[0]["category"] == "持股"


@pytest.mark.asyncio
async def test_annual_independence_service_submit_and_check(db_session: AsyncSession):
    """验证年度独立性声明提交和检查流程。"""
    from app.services.eqcr_independence_service import EqcrIndependenceService

    # 创建用户
    user = User(
        id=uuid.uuid4(),
        username="annual_test",
        email="annual@test.com",
        hashed_password="x",
        role=UserRole.partner,
    )
    db_session.add(user)
    await db_session.flush()

    svc = EqcrIndependenceService(db_session)

    # 初始：无声明
    has = await svc.check_annual_declaration(user.id, year=2026)
    assert has is False

    # 提交
    result = await svc.submit_annual_declaration(
        user_id=user.id,
        year=2026,
        answers={"1": "no", "2": "yes", "3": "no"},
    )
    await db_session.flush()
    assert result["status"] == "submitted"
    assert result["year"] == 2026
    assert result["risk_flagged_count"] == 1  # 一个 "yes"

    # 提交后：已声明
    has = await svc.check_annual_declaration(user.id, year=2026)
    assert has is True

    # 不同年份仍未声明
    has_2027 = await svc.check_annual_declaration(user.id, year=2027)
    assert has_2027 is False


@pytest.mark.asyncio
async def test_annual_independence_questions_categories(db_session: AsyncSession):
    """验证问题集覆盖所有必要类别。"""
    from app.services.eqcr_independence_service import EqcrIndependenceService

    svc = EqcrIndependenceService(db_session)
    questions = svc.get_annual_questions()

    categories = set(q["category"] for q in questions)
    required = {"持股", "家庭成员", "过去服务", "非审计服务", "经济依赖"}
    assert required.issubset(categories)
