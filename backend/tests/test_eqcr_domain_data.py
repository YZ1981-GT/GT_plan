"""EQCR 5 判断域聚合 API + 意见 CRUD 单元测试

Refinement Round 5 任务 5 验证目标：

1. ``test_materiality_aggregation`` — 现有 Materiality 行被正确聚合，
   当前年度与上年分离；现有意见历史按时间切分 current / history。
2. ``test_estimates_keyword_fallback`` — WpIndex.wp_name 含估计关键词
   （"减值"/"折旧"等）时被识别为会计估计底稿。
3. ``test_related_parties_crud_aggregation`` — 注册表 + 交易明细 + 计数摘要。
4. ``test_going_concern_reuses_existing_model`` — 直接复用
   ``GoingConcernEvaluation / GoingConcernIndicator`` 模型。
5. ``test_opinion_type_from_audit_report`` — 从 ``AuditReport`` 获取当前意见类型。
6. ``test_create_and_update_opinion_crud`` — create_opinion / update_opinion
   含参数校验（非法 domain / verdict → ValueError）。
7. ``test_opinion_history_split`` — 多次录意见时 current 是最新一条、
   history 是更早的。
8. ``test_domain_api_empty_project`` — 空项目返回占位 shape，不炸。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
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

# SQLite 兼容 JSONB（与 test_eqcr_service.py 做法一致）
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

from app.models.audit_platform_models import Materiality  # noqa: E402
from app.models.base import ProjectStatus, ProjectType, UserRole  # noqa: E402
from app.models.collaboration_models import (  # noqa: E402
    GoingConcernConclusion,
    GoingConcernEvaluation,
    GoingConcernIndicator,
    SeverityLevel,
)
from app.models.core import Project, User  # noqa: E402
from app.models.eqcr_models import EqcrOpinion  # noqa: E402
from app.models.related_party_models import (  # noqa: E402
    RelatedPartyRegistry,
    RelatedPartyTransaction,
)
from app.models.report_models import (  # noqa: E402
    AuditReport,
    CompanyType,
    OpinionType,
    ReportStatus,
)
from app.models.workpaper_models import WorkingPaper, WpIndex  # noqa: E402
from app.services.eqcr_service import EQCR_CORE_DOMAINS, EqcrService  # noqa: E402


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


async def _make_user(db: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username=f"u-{uuid.uuid4().hex[:6]}",
        email=f"{uuid.uuid4().hex[:6]}@test.com",
        hashed_password="x",
        role=UserRole.partner,
    )
    db.add(user)
    await db.flush()
    return user


async def _make_project(db: AsyncSession, *, name: str = "项目 A") -> Project:
    proj = Project(
        id=uuid.uuid4(),
        name=name,
        client_name="客户 A",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
    )
    db.add(proj)
    await db.flush()
    return proj


# ---------------------------------------------------------------------------
# 测试 1：重要性聚合
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_materiality_aggregation(db_session):
    user = await _make_user(db_session)
    proj = await _make_project(db_session)

    # 录两年的 Materiality 数据：2024（上年）和 2025（本年）
    db_session.add_all(
        [
            Materiality(
                project_id=proj.id,
                year=2024,
                benchmark_type="pre_tax_profit",
                benchmark_amount=Decimal("10000000"),
                overall_percentage=Decimal("5.00"),
                overall_materiality=Decimal("500000"),
                performance_ratio=Decimal("75.00"),
                performance_materiality=Decimal("375000"),
                trivial_ratio=Decimal("5.00"),
                trivial_threshold=Decimal("25000"),
            ),
            Materiality(
                project_id=proj.id,
                year=2025,
                benchmark_type="pre_tax_profit",
                benchmark_amount=Decimal("20000000"),
                overall_percentage=Decimal("5.00"),
                overall_materiality=Decimal("1000000"),
                performance_ratio=Decimal("75.00"),
                performance_materiality=Decimal("750000"),
                trivial_ratio=Decimal("5.00"),
                trivial_threshold=Decimal("50000"),
            ),
        ]
    )
    await db_session.flush()

    # 录 2 条意见（旧 → 新）
    db_session.add(
        EqcrOpinion(
            project_id=proj.id,
            domain="materiality",
            verdict="need_more_evidence",
            comment="第一轮：需要基准解释",
            created_by=user.id,
        )
    )
    await db_session.flush()
    db_session.add(
        EqcrOpinion(
            project_id=proj.id,
            domain="materiality",
            verdict="agree",
            comment="第二轮：认可",
            created_by=user.id,
        )
    )
    await db_session.flush()

    svc = EqcrService(db_session)
    result = await svc.get_materiality(proj.id)

    assert result["project_id"] == str(proj.id)
    assert result["domain"] == "materiality"
    # 本年度为 2025，上年为 2024
    assert result["data"]["current"]["year"] == 2025
    # Decimal 序列化为字符串，SQLite roundtrip 后带 .00 小数位
    assert result["data"]["current"]["overall_materiality"] in ("1000000", "1000000.00")
    assert len(result["data"]["prior_years"]) == 1
    assert result["data"]["prior_years"][0]["year"] == 2024

    # current_opinion 为最新那条（verdict=agree）
    assert result["current_opinion"]["verdict"] == "agree"
    # history 为更早那条
    assert len(result["history_opinions"]) == 1
    assert result["history_opinions"][0]["verdict"] == "need_more_evidence"


# ---------------------------------------------------------------------------
# 测试 2：会计估计关键词匹配
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_estimates_keyword_fallback(db_session):
    """wp_name 含估计/减值/折旧等关键词的底稿被列为会计估计项。"""
    user = await _make_user(db_session)
    proj = await _make_project(db_session)

    # 3 个 wp_index：2 个命中关键词，1 个不命中
    wp1 = WpIndex(
        id=uuid.uuid4(),
        project_id=proj.id,
        wp_code="D01",
        wp_name="应收账款减值测试",
    )
    wp2 = WpIndex(
        id=uuid.uuid4(),
        project_id=proj.id,
        wp_code="F01",
        wp_name="固定资产折旧复核",
    )
    wp3 = WpIndex(
        id=uuid.uuid4(),
        project_id=proj.id,
        wp_code="A01",
        wp_name="银行存款函证",
    )
    db_session.add_all([wp1, wp2, wp3])
    await db_session.flush()

    svc = EqcrService(db_session)
    result = await svc.get_estimates(proj.id)

    assert result["domain"] == "estimate"
    items = result["data"]["items"]
    # 只有 D01 和 F01 命中（A01 不含关键词）
    codes = {it["wp_code"] for it in items}
    assert codes == {"D01", "F01"}
    # keywords 暴露给前端供 UI 说明"本次匹配策略"
    assert "减值" in result["data"]["keywords"]
    assert result["data"]["match_strategy"] == "wp_name_keyword"


# ---------------------------------------------------------------------------
# 测试 3：关联方 Tab 聚合
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_related_parties_crud_aggregation(db_session):
    user = await _make_user(db_session)
    proj = await _make_project(db_session)

    rp1 = RelatedPartyRegistry(
        project_id=proj.id,
        name="母公司 A",
        relation_type="parent",
        is_controlled_by_same_party=False,
    )
    rp2 = RelatedPartyRegistry(
        project_id=proj.id,
        name="关键管理层 B",
        relation_type="key_management",
    )
    db_session.add_all([rp1, rp2])
    await db_session.flush()

    db_session.add(
        RelatedPartyTransaction(
            project_id=proj.id,
            related_party_id=rp1.id,
            amount=Decimal("1500000.00"),
            transaction_type="sales",
            is_arms_length=True,
        )
    )
    await db_session.flush()

    svc = EqcrService(db_session)
    result = await svc.get_related_parties(proj.id)

    assert result["domain"] == "related_party"
    assert result["data"]["summary"]["registry_count"] == 2
    assert result["data"]["summary"]["transaction_count"] == 1
    # 交易金额保留字符串（Decimal → str 序列化）
    assert result["data"]["transactions"][0]["amount"] in (
        "1500000.00",
        "1500000",
    )
    # 没录意见 → None/[]
    assert result["current_opinion"] is None
    assert result["history_opinions"] == []


# ---------------------------------------------------------------------------
# 测试 4：持续经营复用既有模型
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_going_concern_reuses_existing_model(db_session):
    user = await _make_user(db_session)
    proj = await _make_project(db_session)

    evaluation = GoingConcernEvaluation(
        project_id=proj.id,
        evaluation_date=date.today(),
        conclusion=GoingConcernConclusion.no_material_uncertainty,
        management_plan="继续经营",
        auditor_conclusion="无重大不确定性",
    )
    db_session.add(evaluation)
    await db_session.flush()

    db_session.add_all(
        [
            GoingConcernIndicator(
                evaluation_id=evaluation.id,
                indicator_type="flow_crisis",
                indicator_value="现金流充裕",
                is_triggered=False,
                severity=SeverityLevel.low,
            ),
            GoingConcernIndicator(
                evaluation_id=evaluation.id,
                indicator_type="debt_covenant",
                indicator_value="无违约",
                is_triggered=False,
                severity=SeverityLevel.low,
            ),
        ]
    )
    await db_session.flush()

    svc = EqcrService(db_session)
    result = await svc.get_going_concern(proj.id)

    assert result["domain"] == "going_concern"
    assert result["data"]["current_evaluation"]["conclusion"] == "no_material_uncertainty"
    assert len(result["data"]["indicators"]) == 2
    assert result["data"]["prior_evaluations"] == []


# ---------------------------------------------------------------------------
# 测试 5：审计意见 Tab
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_opinion_type_from_audit_report(db_session):
    user = await _make_user(db_session)
    proj = await _make_project(db_session)

    db_session.add_all(
        [
            AuditReport(
                project_id=proj.id,
                year=2024,
                opinion_type=OpinionType.unqualified,
                company_type=CompanyType.non_listed,
                status=ReportStatus.final,
            ),
            AuditReport(
                project_id=proj.id,
                year=2025,
                opinion_type=OpinionType.qualified,
                company_type=CompanyType.non_listed,
                status=ReportStatus.review,
            ),
        ]
    )
    await db_session.flush()

    svc = EqcrService(db_session)
    result = await svc.get_opinion_type(proj.id)

    assert result["domain"] == "opinion_type"
    # 当前报告为 2025 年保留意见
    assert result["data"]["current_report"]["year"] == 2025
    assert result["data"]["current_report"]["opinion_type"] == "qualified"
    assert result["data"]["current_report"]["status"] == "review"
    # 上年为 2024 无保留
    assert len(result["data"]["prior_reports"]) == 1
    assert result["data"]["prior_reports"][0]["year"] == 2024
    assert result["data"]["prior_reports"][0]["opinion_type"] == "unqualified"


# ---------------------------------------------------------------------------
# 测试 6：意见 CRUD + 参数校验
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_update_opinion_crud(db_session):
    user = await _make_user(db_session)
    proj = await _make_project(db_session)

    svc = EqcrService(db_session)

    # 新建意见
    created = await svc.create_opinion(
        project_id=proj.id,
        domain="materiality",
        verdict="agree",
        comment="初次意见",
        extra_payload={"source": "initial"},
        user_id=user.id,
    )
    assert created["domain"] == "materiality"
    assert created["verdict"] == "agree"
    assert created["comment"] == "初次意见"
    assert created["extra_payload"]["source"] == "initial"

    # 更新意见
    updated = await svc.update_opinion(
        opinion_id=uuid.UUID(created["id"]),
        user_id=user.id,
        verdict="disagree",
        comment="复议后改判",
    )
    assert updated is not None
    assert updated["verdict"] == "disagree"
    assert updated["comment"] == "复议后改判"
    # extra_payload 未传 → 保持原值
    assert updated["extra_payload"]["source"] == "initial"

    # 非法 domain → ValueError
    with pytest.raises(ValueError):
        await svc.create_opinion(
            project_id=proj.id,
            domain="xxx-unknown",
            verdict="agree",
            comment=None,
            extra_payload=None,
            user_id=user.id,
        )

    # 非法 verdict → ValueError
    with pytest.raises(ValueError):
        await svc.create_opinion(
            project_id=proj.id,
            domain="materiality",
            verdict="not-a-verdict",
            comment=None,
            extra_payload=None,
            user_id=user.id,
        )

    # 更新不存在的 opinion → None
    assert (
        await svc.update_opinion(
            opinion_id=uuid.uuid4(), user_id=user.id, verdict="agree"
        )
        is None
    )


# ---------------------------------------------------------------------------
# 测试 7：空项目下 5 域接口不会炸
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_domain_api_empty_project(db_session):
    """空项目：所有 5 个接口都应返回合法 shape，而非异常。"""
    user = await _make_user(db_session)
    proj = await _make_project(db_session)

    svc = EqcrService(db_session)

    m = await svc.get_materiality(proj.id)
    assert m["data"]["current"] is None
    assert m["data"]["prior_years"] == []
    assert m["current_opinion"] is None

    e = await svc.get_estimates(proj.id)
    assert e["data"]["items"] == []

    rp = await svc.get_related_parties(proj.id)
    assert rp["data"]["summary"] == {"registry_count": 0, "transaction_count": 0}

    gc = await svc.get_going_concern(proj.id)
    assert gc["data"]["current_evaluation"] is None
    assert gc["data"]["indicators"] == []

    ot = await svc.get_opinion_type(proj.id)
    assert ot["data"]["current_report"] is None
    assert ot["data"]["prior_reports"] == []


# ---------------------------------------------------------------------------
# 测试 8：多条意见时 current/history 切分
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_opinion_history_split(db_session):
    user = await _make_user(db_session)
    proj = await _make_project(db_session)

    # 录 3 条意见
    for i, verdict in enumerate(["need_more_evidence", "disagree", "agree"]):
        db_session.add(
            EqcrOpinion(
                project_id=proj.id,
                domain="going_concern",
                verdict=verdict,
                comment=f"第 {i+1} 轮",
                created_by=user.id,
            )
        )
        await db_session.flush()

    svc = EqcrService(db_session)
    result = await svc.get_going_concern(proj.id)

    # 最新一条（最后录入）→ current
    assert result["current_opinion"]["verdict"] == "agree"
    # 早两条 → history，按时间升序
    assert len(result["history_opinions"]) == 2
    assert result["history_opinions"][0]["verdict"] == "need_more_evidence"
    assert result["history_opinions"][1]["verdict"] == "disagree"


# ---------------------------------------------------------------------------
# 测试 9：5 域接口的结果都包含统一 shape 字段
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_domain_apis_return_unified_shape(db_session):
    """所有 5 个接口都必须返回 {project_id, domain, data, current_opinion, history_opinions}。"""
    user = await _make_user(db_session)
    proj = await _make_project(db_session)

    svc = EqcrService(db_session)

    results = {
        "materiality": await svc.get_materiality(proj.id),
        "estimate": await svc.get_estimates(proj.id),
        "related_party": await svc.get_related_parties(proj.id),
        "going_concern": await svc.get_going_concern(proj.id),
        "opinion_type": await svc.get_opinion_type(proj.id),
    }

    required_keys = {"project_id", "domain", "data", "current_opinion", "history_opinions"}
    for name, res in results.items():
        assert set(res.keys()) >= required_keys, f"{name} 缺字段"
        assert res["project_id"] == str(proj.id)
        assert res["domain"] == name
        assert isinstance(res["data"], dict)
        assert res["history_opinions"] == []


# ---------------------------------------------------------------------------
# 测试 10：核心常量稳定（EQCR_CORE_DOMAINS 是 5 域基线）
# ---------------------------------------------------------------------------


def test_eqcr_core_domains_constant_stable():
    """保证基础 5 域（不含 component_auditor 扩展）稳定。"""
    assert set(EQCR_CORE_DOMAINS) == {
        "materiality",
        "estimate",
        "related_party",
        "going_concern",
        "opinion_type",
    }
