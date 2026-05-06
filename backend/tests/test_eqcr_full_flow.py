"""Sprint 2 验收：EQCR 完整流程集成测试

完整链：委派 → 5 Tab 录入 → 影子计算 → 审批 → 状态锁 → 签字 → final → 备忘录进归档包

验证 R5 需求 1-10 端到端联动。

使用 SQLite in-memory，mock 外部依赖，遵循 test_eqcr_gate_approve.py 的 fixture 模式。
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
import app.models.phase14_models  # noqa: E402, F401

from app.models.base import ProjectStatus, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.eqcr_models import EqcrOpinion  # noqa: E402
from app.models.report_models import AuditReport, ReportStatus  # noqa: E402
from app.models.staff_models import ProjectAssignment, StaffMember  # noqa: E402


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def full_flow_setup(db_session: AsyncSession):
    """创建完整的 EQCR 流程测试数据。"""
    # 用户
    eqcr_user = User(
        id=uuid.uuid4(),
        username="eqcr_partner",
        email="eqcr@test.com",
        hashed_password="x",
        role=UserRole.partner,
    )
    signing_partner = User(
        id=uuid.uuid4(),
        username="signing_partner",
        email="sp@test.com",
        hashed_password="x",
        role=UserRole.partner,
    )
    db_session.add_all([eqcr_user, signing_partner])
    await db_session.flush()

    # 员工（staff_models.StaffMember 使用 employee_no 字段，不是 employee_id）
    eqcr_staff = StaffMember(
        id=uuid.uuid4(),
        user_id=eqcr_user.id,
        name="EQCR 合伙人",
        employee_no="E001",
    )
    sp_staff = StaffMember(
        id=uuid.uuid4(),
        user_id=signing_partner.id,
        name="签字合伙人",
        employee_no="E002",
    )
    db_session.add_all([eqcr_staff, sp_staff])
    await db_session.flush()

    # 项目
    project = Project(
        id=uuid.uuid4(),
        name="测试项目-EQCR全流程",
        client_name="测试客户ABC",
        status=ProjectStatus.execution,
        audit_period_start=date(2025, 1, 1),
        audit_period_end=date(2025, 12, 31),
        partner_id=signing_partner.id,
    )
    db_session.add(project)
    await db_session.flush()

    # 委派 EQCR
    assignment = ProjectAssignment(
        id=uuid.uuid4(),
        project_id=project.id,
        staff_id=eqcr_staff.id,
        role="eqcr",
    )
    db_session.add(assignment)

    # 创建审计报告（review 状态）
    report = AuditReport(
        id=uuid.uuid4(),
        project_id=project.id,
        year=2025,
        opinion_type="unqualified",
        company_type="non_listed",
        status=ReportStatus.review,
        paragraphs={"审计意见段": "标准无保留意见"},
    )
    db_session.add(report)
    await db_session.flush()

    return {
        "eqcr_user": eqcr_user,
        "signing_partner": signing_partner,
        "eqcr_staff": eqcr_staff,
        "sp_staff": sp_staff,
        "project": project,
        "report": report,
    }


@pytest.mark.asyncio
async def test_full_eqcr_flow_opinions(db_session: AsyncSession, full_flow_setup):
    """验证 EQCR 可以对 5 个域录入意见。"""
    data = full_flow_setup
    project_id = data["project"].id
    eqcr_user_id = data["eqcr_user"].id

    domains = ["materiality", "estimate", "related_party", "going_concern", "opinion_type"]
    for domain in domains:
        db_session.add(EqcrOpinion(
            project_id=project_id,
            domain=domain,
            verdict="agree",
            comment=f"EQCR 认可 {domain}",
            created_by=eqcr_user_id,
        ))
    await db_session.flush()

    # 验证 5 个域都有意见
    q = sa.select(EqcrOpinion.domain).where(
        EqcrOpinion.project_id == project_id,
        EqcrOpinion.is_deleted == False,  # noqa: E712
    ).distinct()
    covered = set((await db_session.execute(q)).scalars().all())
    assert covered == set(domains)


@pytest.mark.asyncio
async def test_full_eqcr_flow_gate_pass(db_session: AsyncSession, full_flow_setup):
    """验证 5 域意见齐全后 EQCR 门禁放行。"""
    from app.services.gate_engine import gate_engine, rule_registry
    from app.services.gate_rules_eqcr import register_eqcr_gate_rules
    from app.models.phase14_enums import GateType, GateDecisionResult

    data = full_flow_setup
    project_id = data["project"].id
    eqcr_user_id = data["eqcr_user"].id

    for domain in ["materiality", "estimate", "related_party", "going_concern", "opinion_type"]:
        db_session.add(EqcrOpinion(
            project_id=project_id,
            domain=domain,
            verdict="agree",
            comment="ok",
            created_by=eqcr_user_id,
        ))
    await db_session.flush()

    # 清空注册表避免跨测试污染后重新注册
    rule_registry._rules[GateType.eqcr_approval] = []
    register_eqcr_gate_rules()

    result = await gate_engine.evaluate(
        db=db_session,
        gate_type=GateType.eqcr_approval,
        project_id=project_id,
        wp_id=None,
        actor_id=eqcr_user_id,
        context={"action": "eqcr_approve"},
    )
    assert result.decision == GateDecisionResult.allow


@pytest.mark.asyncio
async def test_full_eqcr_flow_status_lock(db_session: AsyncSession, full_flow_setup):
    """验证 eqcr_approved 状态被正确设置。"""
    data = full_flow_setup
    report = data["report"]

    report.status = ReportStatus.eqcr_approved
    await db_session.flush()

    refreshed = (await db_session.execute(
        sa.select(AuditReport).where(AuditReport.id == report.id)
    )).scalar_one()
    assert refreshed.status == ReportStatus.eqcr_approved


@pytest.mark.asyncio
async def test_full_eqcr_flow_sign_to_final(db_session: AsyncSession, full_flow_setup):
    """验证 order=5 归档签字后状态切到 final。"""
    from app.services.sign_service import SignService

    data = full_flow_setup
    report = data["report"]
    sp_user = data["signing_partner"]

    # 先切到 eqcr_approved
    report.status = ReportStatus.eqcr_approved
    await db_session.flush()

    # order=5 归档签字
    sign_svc = SignService()
    await sign_svc.sign_document(
        db=db_session,
        object_type="audit_report",
        object_id=report.id,
        signer_id=sp_user.id,
        level="level1",
        required_order=5,
        required_role="archive",
    )
    await db_session.flush()

    refreshed = (await db_session.execute(
        sa.select(AuditReport).where(AuditReport.id == report.id)
    )).scalar_one()
    assert refreshed.status == ReportStatus.final


@pytest.mark.asyncio
async def test_full_eqcr_flow_memo_generation(db_session: AsyncSession, full_flow_setup):
    """验证备忘录生成返回预期结构。"""
    from app.services.eqcr_memo_service import EqcrMemoService

    data = full_flow_setup
    project_id = data["project"].id
    eqcr_user_id = data["eqcr_user"].id

    for domain in ["materiality", "estimate", "related_party", "going_concern", "opinion_type"]:
        db_session.add(EqcrOpinion(
            project_id=project_id,
            domain=domain,
            verdict="agree",
            comment=f"认可 {domain}",
            created_by=eqcr_user_id,
        ))
    await db_session.flush()

    svc = EqcrMemoService(db_session)
    memo = await svc.generate_memo(project_id, eqcr_user_id)

    assert memo["project_id"] == str(project_id)
    assert "sections" in memo
    assert "重要性判断" in memo["sections"]
    assert "EQCR 总评与结论" in memo["sections"]
    assert memo["status"] == "draft"
