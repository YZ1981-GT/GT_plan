"""RiskSummaryService smoke test (R8 复盘 P0 修正)

覆盖：
- 空项目：summary.can_sign=true, total_blockers=0
- 有重大错报（超阈值）：total_blockers > 0, can_sign=false
- 有未解决复核意见（通过 WorkingPaper join 反查）：total_warnings > 0
- 有被拒 AJE 未转错报：total_blockers > 0
- 持续经营风险（GoingConcernConclusion 非 no_material_uncertainty）：total_blockers += 1

使用 SQLite in-memory + 与 test_eqcr_gate_approve 相同的 fixture 模板。
目的：验证修正后的字段访问路径不抛 AttributeError，且业务分类正确。
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

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

# 注册所有模型（必须 include 所有被 join 的表）
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

from app.models.base import ProjectStatus, ProjectType, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.audit_platform_models import (  # noqa: E402
    Adjustment,
    AdjustmentType,
    Materiality,
    MisstatementType,
    UnadjustedMisstatement,
)
from app.models.workpaper_models import ReviewRecord, WorkingPaper, WpIndex, WpSourceType  # noqa: E402
from app.services.risk_summary_service import RiskSummaryService  # noqa: E402


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
async def project(db_session: AsyncSession):
    user = User(
        id=uuid.uuid4(),
        username="tester",
        hashed_password="x",
        email="t@example.com",
        role=UserRole.partner,
    )
    proj = Project(
        id=uuid.uuid4(),
        name="测试项目",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        audit_period_end=date(YEAR, 12, 31),
    )
    # Materiality：performance_materiality = 100,000
    mat = Materiality(
        id=uuid.uuid4(),
        project_id=proj.id,
        year=YEAR,
        benchmark_type="pre_tax_profit",
        benchmark_amount=Decimal("10000000"),
        overall_percentage=Decimal("5.00"),
        overall_materiality=Decimal("500000"),
        performance_ratio=Decimal("20.00"),
        performance_materiality=Decimal("100000"),
        trivial_ratio=Decimal("5.00"),
        trivial_threshold=Decimal("5000"),
    )
    db_session.add_all([user, proj, mat])
    await db_session.commit()
    return {"user": user, "project": proj, "materiality": mat}


# ---------------------------------------------------------------------------
# 场景 1：空项目
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_project_can_sign(db_session: AsyncSession, project):
    """空项目（无错报/复核/问题单）→ can_sign=true"""
    svc = RiskSummaryService(db_session)
    result = await svc.aggregate(project["project"].id, year=YEAR)

    assert result["year"] == YEAR
    assert result["high_findings"] == []
    assert result["unresolved_comments"] == []
    assert result["material_misstatements"] == []
    assert result["unconverted_rejected_aje"] == []
    assert result["going_concern_flag"] is False
    assert result["summary"]["total_blockers"] == 0
    assert result["summary"]["can_sign"] is True


# ---------------------------------------------------------------------------
# 场景 2：超重要性错报
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_material_misstatement_blocks_sign(
    db_session: AsyncSession, project
):
    """存在超重要性错报（amount > performance_materiality）→ 阻塞签字"""
    proj = project["project"]
    # 200,000 > 100,000（阈值）→ 超阈值
    mis = UnadjustedMisstatement(
        id=uuid.uuid4(),
        project_id=proj.id,
        year=YEAR,
        misstatement_description="应收账款高估",
        misstatement_amount=Decimal("200000"),
        misstatement_type=MisstatementType.factual,
        affected_account_code="1122",
        affected_account_name="应收账款",
        created_by=project["user"].id,
    )
    db_session.add(mis)
    await db_session.commit()

    svc = RiskSummaryService(db_session)
    result = await svc.aggregate(proj.id, year=YEAR)

    assert len(result["material_misstatements"]) == 1
    assert result["material_misstatements"][0]["amount"] == 200000.0
    assert result["material_misstatements"][0]["description"] == "应收账款高估"
    assert result["summary"]["total_blockers"] >= 1
    assert result["summary"]["can_sign"] is False


@pytest.mark.asyncio
async def test_below_threshold_misstatement_not_material(
    db_session: AsyncSession, project
):
    """未超重要性的错报不进 material_misstatements"""
    proj = project["project"]
    mis = UnadjustedMisstatement(
        id=uuid.uuid4(),
        project_id=proj.id,
        year=YEAR,
        misstatement_description="小额错报",
        misstatement_amount=Decimal("50000"),  # < 100,000 阈值
        misstatement_type=MisstatementType.factual,
        created_by=project["user"].id,
    )
    db_session.add(mis)
    await db_session.commit()

    svc = RiskSummaryService(db_session)
    result = await svc.aggregate(proj.id, year=YEAR)

    assert result["material_misstatements"] == []
    assert result["summary"]["can_sign"] is True


# ---------------------------------------------------------------------------
# 场景 3：未解决复核意见（ReviewRecord join WorkingPaper 反查）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unresolved_review_comments_as_warning(
    db_session: AsyncSession, project
):
    """未解决 ReviewRecord 通过 WorkingPaper 反查 → total_warnings > 0

    验证修正：ReviewRecord 无 project_id，必须通过 join WorkingPaper 反查
    """
    proj = project["project"]
    wp_idx = WpIndex(
        id=uuid.uuid4(),
        project_id=proj.id,
        wp_code="D.1",
        wp_name="货币资金",
    )
    db_session.add(wp_idx)
    await db_session.flush()

    wp = WorkingPaper(
        id=uuid.uuid4(),
        project_id=proj.id,
        wp_index_id=wp_idx.id,
        file_path="/fake/D.1.xlsx",
        source_type=WpSourceType.template,
    )
    db_session.add(wp)
    await db_session.flush()

    # 未解决（resolved_at=None）
    rev = ReviewRecord(
        id=uuid.uuid4(),
        working_paper_id=wp.id,
        comment_text="请补充原始凭证",
        commenter_id=project["user"].id,
        resolved_at=None,
    )
    db_session.add(rev)
    await db_session.commit()

    svc = RiskSummaryService(db_session)
    result = await svc.aggregate(proj.id, year=YEAR)

    assert len(result["unresolved_comments"]) == 1
    assert result["unresolved_comments"][0]["comment_text"] == "请补充原始凭证"
    assert result["unresolved_comments"][0]["working_paper_id"] == str(wp.id)
    # warning 不阻塞签字
    assert result["summary"]["total_warnings"] == 1


# ---------------------------------------------------------------------------
# 场景 4：被拒未转错报的 AJE
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rejected_aje_not_converted_blocks(
    db_session: AsyncSession, project
):
    """被拒 AJE 且未被任何 UnadjustedMisstatement.source_adjustment_id 引用 → 阻塞

    验证修正：不再用不存在的 Adjustment.converted_to_misstatement_id 字段
    """
    proj = project["project"]
    adj_rejected = Adjustment(
        id=uuid.uuid4(),
        project_id=proj.id,
        year=YEAR,
        company_code="SELF",
        adjustment_no="AJE-001",
        adjustment_type=AdjustmentType.aje,
        entry_group_id=uuid.uuid4(),
        description="被拒调整分录",
        account_code="1122",
        review_status="rejected",
        created_by=project["user"].id,
    )
    adj_converted = Adjustment(
        id=uuid.uuid4(),
        project_id=proj.id,
        year=YEAR,
        company_code="SELF",
        adjustment_no="AJE-002",
        adjustment_type=AdjustmentType.aje,
        entry_group_id=uuid.uuid4(),
        description="已转错报分录",
        account_code="1122",
        review_status="rejected",
        created_by=project["user"].id,
    )
    db_session.add_all([adj_rejected, adj_converted])
    await db_session.flush()

    # 为 adj_converted 创建对应的 UnadjustedMisstatement
    mis = UnadjustedMisstatement(
        id=uuid.uuid4(),
        project_id=proj.id,
        year=YEAR,
        source_adjustment_id=adj_converted.id,
        misstatement_description="已从 AJE-002 转来",
        misstatement_amount=Decimal("30000"),  # 小额，不触发 material
        misstatement_type=MisstatementType.factual,
        created_by=project["user"].id,
    )
    db_session.add(mis)
    await db_session.commit()

    svc = RiskSummaryService(db_session)
    result = await svc.aggregate(proj.id, year=YEAR)

    # 只有 adj_rejected 应出现在 unconverted 列表
    ids = [item["id"] for item in result["unconverted_rejected_aje"]]
    assert str(adj_rejected.id) in ids
    assert str(adj_converted.id) not in ids
    assert result["summary"]["total_blockers"] >= 1


# ---------------------------------------------------------------------------
# 场景 5：持续经营风险（GoingConcernConclusion 非 no_material_uncertainty）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_going_concern_disclosure_flag(
    db_session: AsyncSession, project
):
    """GoingConcernConclusion 非 no_material_uncertainty → going_concern_flag=true"""
    from app.models.collaboration_models import (
        GoingConcernEvaluation,
        GoingConcernConclusion,
    )
    proj = project["project"]
    evalm = GoingConcernEvaluation(
        id=uuid.uuid4(),
        project_id=proj.id,
        evaluation_date=date(YEAR, 12, 31),
        conclusion=GoingConcernConclusion.material_uncertainty_disclosed,
    )
    db_session.add(evalm)
    await db_session.commit()

    svc = RiskSummaryService(db_session)
    result = await svc.aggregate(proj.id, year=YEAR)

    assert result["going_concern_flag"] is True
    assert result["summary"]["total_blockers"] >= 1
    assert result["summary"]["can_sign"] is False


@pytest.mark.asyncio
async def test_going_concern_appropriate_not_flagged(
    db_session: AsyncSession, project
):
    """GoingConcernConclusion=no_material_uncertainty → 无风险标记"""
    from app.models.collaboration_models import (
        GoingConcernEvaluation,
        GoingConcernConclusion,
    )
    proj = project["project"]
    evalm = GoingConcernEvaluation(
        id=uuid.uuid4(),
        project_id=proj.id,
        evaluation_date=date(YEAR, 12, 31),
        conclusion=GoingConcernConclusion.no_material_uncertainty,
    )
    db_session.add(evalm)
    await db_session.commit()

    svc = RiskSummaryService(db_session)
    result = await svc.aggregate(proj.id, year=YEAR)

    assert result["going_concern_flag"] is False


# ---------------------------------------------------------------------------
# 场景 6：year 参数自动推断
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_year_auto_inferred_from_materiality(
    db_session: AsyncSession, project
):
    """不传 year 时自动取最新 Materiality.year"""
    svc = RiskSummaryService(db_session)
    result = await svc.aggregate(project["project"].id)  # 不传 year
    assert result["year"] == YEAR
