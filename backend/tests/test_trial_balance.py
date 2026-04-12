"""试算表计算引擎测试

Validates: Requirements 6.1-6.12
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.audit_platform_models import (
    AccountCategory,
    AccountChart,
    AccountDirection,
    AccountMapping,
    AccountSource,
    Adjustment,
    AdjustmentType,
    MappingType,
    ReviewStatus,
    TbBalance,
    TrialBalance,
)
from app.models.core import Project, ProjectStatus, ProjectType
from app.services.trial_balance_service import TrialBalanceService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()


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
    """创建试算表测试数据"""
    project = Project(
        id=uuid.uuid4(), name="试算表测试_2025",
        client_name="试算表测试", project_type=ProjectType.annual,
        status=ProjectStatus.planning, created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.flush()
    pid = project.id

    # 标准科目
    db_session.add_all([
        AccountChart(
            project_id=pid, account_code="1001", account_name="库存现金",
            direction=AccountDirection.debit, level=1,
            category=AccountCategory.asset, source=AccountSource.standard,
        ),
        AccountChart(
            project_id=pid, account_code="1002", account_name="银行存款",
            direction=AccountDirection.debit, level=1,
            category=AccountCategory.asset, source=AccountSource.standard,
        ),
        AccountChart(
            project_id=pid, account_code="6001", account_name="主营业务收入",
            direction=AccountDirection.credit, level=1,
            category=AccountCategory.revenue, source=AccountSource.standard,
        ),
    ])

    # 科目映射（客户科目 → 标准科目，含多对一）
    db_session.add_all([
        AccountMapping(
            project_id=pid, original_account_code="C1001",
            original_account_name="现金", standard_account_code="1001",
            mapping_type=MappingType.auto_exact, created_by=FAKE_USER_ID,
        ),
        AccountMapping(
            project_id=pid, original_account_code="C1002",
            original_account_name="工行存款", standard_account_code="1002",
            mapping_type=MappingType.auto_exact, created_by=FAKE_USER_ID,
        ),
        AccountMapping(
            project_id=pid, original_account_code="C1003",
            original_account_name="建行存款", standard_account_code="1002",
            mapping_type=MappingType.manual, created_by=FAKE_USER_ID,
        ),
        AccountMapping(
            project_id=pid, original_account_code="C6001",
            original_account_name="销售收入", standard_account_code="6001",
            mapping_type=MappingType.auto_exact, created_by=FAKE_USER_ID,
        ),
    ])

    # 客户余额表
    db_session.add_all([
        TbBalance(
            project_id=pid, year=2025, company_code="001",
            account_code="C1001", account_name="现金",
            opening_balance=Decimal("10000"), closing_balance=Decimal("12000"),
            debit_amount=Decimal("5000"), credit_amount=Decimal("3000"),
        ),
        TbBalance(
            project_id=pid, year=2025, company_code="001",
            account_code="C1002", account_name="工行存款",
            opening_balance=Decimal("30000"), closing_balance=Decimal("35000"),
            debit_amount=Decimal("10000"), credit_amount=Decimal("5000"),
        ),
        TbBalance(
            project_id=pid, year=2025, company_code="001",
            account_code="C1003", account_name="建行存款",
            opening_balance=Decimal("20000"), closing_balance=Decimal("22000"),
            debit_amount=Decimal("5000"), credit_amount=Decimal("3000"),
        ),
        TbBalance(
            project_id=pid, year=2025, company_code="001",
            account_code="C6001", account_name="销售收入",
            opening_balance=Decimal("0"), closing_balance=Decimal("100000"),
            debit_amount=Decimal("0"), credit_amount=Decimal("100000"),
        ),
    ])

    await db_session.commit()
    return pid


# ===== 未审数重算 =====

@pytest.mark.asyncio
async def test_recalc_unadjusted_full(db_session: AsyncSession, seeded_db):
    """全量重算未审数"""
    pid = seeded_db
    svc = TrialBalanceService(db_session)
    await svc.recalc_unadjusted(pid, 2025)
    await db_session.commit()

    rows = await svc.get_trial_balance(pid, 2025)
    tb_map = {r.standard_account_code: r for r in rows}

    assert tb_map["1001"].unadjusted_amount == Decimal("12000")
    # 1002 = 工行35000 + 建行22000 = 57000（多对一映射）
    assert tb_map["1002"].unadjusted_amount == Decimal("57000")
    assert tb_map["6001"].unadjusted_amount == Decimal("100000")


@pytest.mark.asyncio
async def test_recalc_unadjusted_incremental(db_session: AsyncSession, seeded_db):
    """增量重算指定科目"""
    pid = seeded_db
    svc = TrialBalanceService(db_session)
    # 先全量
    await svc.recalc_unadjusted(pid, 2025)
    # 再增量只算 1001
    await svc.recalc_unadjusted(pid, 2025, account_codes=["1001"])
    await db_session.commit()

    rows = await svc.get_trial_balance(pid, 2025)
    tb_map = {r.standard_account_code: r for r in rows}
    assert tb_map["1001"].unadjusted_amount == Decimal("12000")


# ===== 调整列重算 =====

@pytest.mark.asyncio
async def test_recalc_adjustments(db_session: AsyncSession, seeded_db):
    """调整列重算"""
    pid = seeded_db
    svc = TrialBalanceService(db_session)
    await svc.recalc_unadjusted(pid, 2025)

    # 添加调整分录
    group_id = uuid.uuid4()
    db_session.add_all([
        Adjustment(
            project_id=pid, year=2025, company_code="001",
            adjustment_no="AJE-001", adjustment_type=AdjustmentType.aje,
            account_code="1001", account_name="库存现金",
            debit_amount=Decimal("500"), credit_amount=Decimal("0"),
            entry_group_id=group_id, created_by=FAKE_USER_ID,
        ),
        Adjustment(
            project_id=pid, year=2025, company_code="001",
            adjustment_no="AJE-001", adjustment_type=AdjustmentType.aje,
            account_code="6001", account_name="主营业务收入",
            debit_amount=Decimal("0"), credit_amount=Decimal("500"),
            entry_group_id=group_id, created_by=FAKE_USER_ID,
        ),
    ])
    await db_session.flush()

    await svc.recalc_adjustments(pid, 2025)
    await db_session.commit()

    rows = await svc.get_trial_balance(pid, 2025)
    tb_map = {r.standard_account_code: r for r in rows}
    assert tb_map["1001"].aje_adjustment == Decimal("500")
    assert tb_map["6001"].aje_adjustment == Decimal("-500")


# ===== 审定数重算 =====

@pytest.mark.asyncio
async def test_recalc_audited(db_session: AsyncSession, seeded_db):
    """审定数 = 未审数 + rje + aje"""
    pid = seeded_db
    svc = TrialBalanceService(db_session)
    await svc.recalc_unadjusted(pid, 2025)

    group_id = uuid.uuid4()
    db_session.add(Adjustment(
        project_id=pid, year=2025, company_code="001",
        adjustment_no="RJE-001", adjustment_type=AdjustmentType.rje,
        account_code="1001", account_name="库存现金",
        debit_amount=Decimal("1000"), credit_amount=Decimal("0"),
        entry_group_id=group_id, created_by=FAKE_USER_ID,
    ))
    await db_session.flush()

    await svc.recalc_adjustments(pid, 2025)
    await svc.recalc_audited(pid, 2025)
    await db_session.commit()

    rows = await svc.get_trial_balance(pid, 2025)
    tb_map = {r.standard_account_code: r for r in rows}
    # 1001: 未审12000 + rje1000 + aje0 = 13000
    assert tb_map["1001"].audited_amount == Decimal("13000")


# ===== 全量重算 =====

@pytest.mark.asyncio
async def test_full_recalc(db_session: AsyncSession, seeded_db):
    """全量重算"""
    pid = seeded_db
    svc = TrialBalanceService(db_session)
    await svc.full_recalc(pid, 2025)
    await db_session.commit()

    rows = await svc.get_trial_balance(pid, 2025)
    assert len(rows) >= 3
    for r in rows:
        unadj = r.unadjusted_amount or Decimal("0")
        assert r.audited_amount == unadj + r.rje_adjustment + r.aje_adjustment


# ===== 一致性校验 =====

@pytest.mark.asyncio
async def test_consistency_check_pass(db_session: AsyncSession, seeded_db):
    """一致性校验通过"""
    pid = seeded_db
    svc = TrialBalanceService(db_session)
    await svc.full_recalc(pid, 2025)
    await db_session.commit()

    issues = await svc.check_consistency(pid, 2025)
    assert len(issues) == 0


@pytest.mark.asyncio
async def test_consistency_check_fail(db_session: AsyncSession, seeded_db):
    """人为制造不一致"""
    pid = seeded_db
    svc = TrialBalanceService(db_session)
    await svc.full_recalc(pid, 2025)

    # 手动篡改审定数
    rows = await svc.get_trial_balance(pid, 2025)
    rows[0].audited_amount = Decimal("999999")
    await db_session.commit()

    issues = await svc.check_consistency(pid, 2025)
    assert len(issues) > 0
    assert issues[0]["type"] == "audited_formula"


# ===== 多对一映射 =====

@pytest.mark.asyncio
async def test_many_to_one_mapping(db_session: AsyncSession, seeded_db):
    """多对一映射：工行+建行 → 银行存款"""
    pid = seeded_db
    svc = TrialBalanceService(db_session)
    await svc.full_recalc(pid, 2025)
    await db_session.commit()

    rows = await svc.get_trial_balance(pid, 2025)
    tb_map = {r.standard_account_code: r for r in rows}
    # 1002 = 35000 + 22000 = 57000
    assert tb_map["1002"].unadjusted_amount == Decimal("57000")
    assert tb_map["1002"].opening_balance == Decimal("50000")  # 30000 + 20000
