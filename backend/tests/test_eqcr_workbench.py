"""EQCR 工作台集成测试

Sprint 1 验收：覆盖完整流程
  委派 EQCR → 列出项目 → 录意见 → 影子计算 → 验证 overview 反映所有变更

测试使用 SQLite in-memory，mock 外部依赖（Redis / consistency_replay_engine）。
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
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

from app.models.base import ProjectStatus, ProjectType, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.eqcr_models import EqcrOpinion, EqcrShadowComputation  # noqa: E402
from app.models.staff_models import ProjectAssignment, StaffMember  # noqa: E402
from app.services.eqcr_service import (  # noqa: E402
    EQCR_CORE_DOMAINS,
    PROGRESS_DISAGREE,
    PROGRESS_IN_PROGRESS,
    PROGRESS_NOT_STARTED,
    EqcrService,
)
from app.services.eqcr_shadow_compute_service import EqcrShadowComputeService  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
async def setup_data(db_session: AsyncSession):
    """创建用户 + 员工 + 项目 + EQCR 委派。"""
    user = User(
        id=uuid.uuid4(),
        username="eqcr_partner",
        email="eqcr@test.com",
        hashed_password="x",
        role=UserRole.partner,
    )
    db_session.add(user)
    await db_session.flush()

    staff = StaffMember(
        id=uuid.uuid4(),
        user_id=user.id,
        name="张 EQCR",
        employee_no="E-EQCR-001",
    )
    db_session.add(staff)
    await db_session.flush()

    project = Project(
        id=uuid.uuid4(),
        name="集成测试项目",
        client_name="集成测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        audit_period_end=date.today() + timedelta(days=15),
    )
    db_session.add(project)
    await db_session.flush()

    # 委派 EQCR 角色
    assignment = ProjectAssignment(
        project_id=project.id,
        staff_id=staff.id,
        role="eqcr",
    )
    db_session.add(assignment)
    await db_session.flush()

    return {"user": user, "staff": staff, "project": project}


# ---------------------------------------------------------------------------
# 集成测试：完整流程
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_eqcr_workflow(db_session: AsyncSession, setup_data):
    """完整流程：委派 EQCR → 列出项目 → 录意见 → 影子计算 → overview 反映变更。"""
    user = setup_data["user"]
    project = setup_data["project"]

    eqcr_svc = EqcrService(db_session)
    shadow_svc = EqcrShadowComputeService(db_session)

    # ---------------------------------------------------------------
    # Step 1: list_my_projects → 验证项目出现
    # ---------------------------------------------------------------
    cards = await eqcr_svc.list_my_projects(user.id)
    assert len(cards) == 1
    card = cards[0]
    assert card["project_id"] == str(project.id)
    assert card["project_name"] == "集成测试项目"
    assert card["my_progress"] == PROGRESS_NOT_STARTED
    assert card["judgment_counts"] == {"unreviewed": 5, "reviewed": 0}

    # ---------------------------------------------------------------
    # Step 2: 录入 2 条意见（materiality=agree, estimate=disagree）
    # ---------------------------------------------------------------
    op1 = await eqcr_svc.create_opinion(
        project_id=project.id,
        domain="materiality",
        verdict="agree",
        comment="整体重要性设定合理",
        extra_payload=None,
        user_id=user.id,
    )
    assert op1["domain"] == "materiality"
    assert op1["verdict"] == "agree"

    op2 = await eqcr_svc.create_opinion(
        project_id=project.id,
        domain="estimate",
        verdict="disagree",
        comment="应收账款减值估计偏乐观",
        extra_payload=None,
        user_id=user.id,
    )
    assert op2["domain"] == "estimate"
    assert op2["verdict"] == "disagree"
    await db_session.flush()

    # 验证进度变为 disagree（有 disagree 意见）
    cards = await eqcr_svc.list_my_projects(user.id)
    assert cards[0]["my_progress"] == PROGRESS_DISAGREE
    assert cards[0]["judgment_counts"] == {"unreviewed": 3, "reviewed": 2}

    # ---------------------------------------------------------------
    # Step 3: 影子计算
    # ---------------------------------------------------------------
    mock_layer = MagicMock()
    mock_layer.from_table = "tb_balance"
    mock_layer.to_table = "trial_balance"
    mock_layer.status = "consistent"
    mock_layer.diffs = []

    mock_result = MagicMock()
    mock_result.snapshot_id = "snap_integration"
    mock_result.overall_status = "consistent"
    mock_result.blocking_count = 0
    mock_result.layers = [mock_layer]

    with patch(
        "app.services.consistency_replay_engine.consistency_replay_engine"
    ) as mock_engine:
        mock_engine.replay_consistency = AsyncMock(return_value=mock_result)

        shadow_result = await shadow_svc.execute_shadow_compute(
            project_id=project.id,
            computation_type="debit_credit_balance",
            params={"year": 2025},
            user_id=user.id,
        )
        await db_session.flush()

    assert shadow_result["computation_type"] == "debit_credit_balance"
    assert shadow_result["project_id"] == str(project.id)
    assert "id" in shadow_result

    # 验证影子计算记录可列出
    shadow_list = await shadow_svc.list_shadow_computations(project.id)
    assert len(shadow_list) == 1

    # ---------------------------------------------------------------
    # Step 4: get_project_overview 反映所有变更
    # ---------------------------------------------------------------
    overview = await eqcr_svc.get_project_overview(user.id, project.id)
    assert overview is not None

    # 项目信息
    assert overview["project"]["name"] == "集成测试项目"
    assert overview["my_role_confirmed"] is True

    # 意见汇总
    by_domain = overview["opinion_summary"]["by_domain"]
    assert by_domain["materiality"] == "agree"
    assert by_domain["estimate"] == "disagree"
    assert by_domain["related_party"] is None
    assert by_domain["going_concern"] is None
    assert by_domain["opinion_type"] is None
    assert overview["opinion_summary"]["total"] == 2

    # 异议计数（estimate=disagree → 1 条未解决异议）
    assert overview["disagreement_count"] == 1

    # 影子计算计数
    assert overview["shadow_comp_count"] == 1


@pytest.mark.asyncio
async def test_eqcr_workflow_no_assignment_returns_empty(db_session: AsyncSession):
    """无 EQCR 委派的用户看不到任何项目。"""
    user = User(
        id=uuid.uuid4(),
        username="non_eqcr",
        email="non@test.com",
        hashed_password="x",
        role=UserRole.partner,
    )
    db_session.add(user)
    await db_session.flush()

    svc = EqcrService(db_session)
    cards = await svc.list_my_projects(user.id)
    assert cards == []


@pytest.mark.asyncio
async def test_eqcr_workflow_multiple_opinions_progress(
    db_session: AsyncSession, setup_data
):
    """录入所有 5 个 domain 的 agree 意见后，进度仍为 in_progress（需 eqcr_approved 状态才算 approved）。"""
    user = setup_data["user"]
    project = setup_data["project"]

    eqcr_svc = EqcrService(db_session)

    # 录入全部 5 个 domain 的 agree 意见
    for domain in EQCR_CORE_DOMAINS:
        await eqcr_svc.create_opinion(
            project_id=project.id,
            domain=domain,
            verdict="agree",
            comment=f"{domain} 认可",
            extra_payload=None,
            user_id=user.id,
        )
    await db_session.flush()

    cards = await eqcr_svc.list_my_projects(user.id)
    assert len(cards) == 1
    # 全部 agree 但 report_status 不是 eqcr_approved → in_progress
    assert cards[0]["my_progress"] == PROGRESS_IN_PROGRESS
    assert cards[0]["judgment_counts"] == {"unreviewed": 0, "reviewed": 5}
