"""tb_balance → trial_balance 符号传递集成测试（真实 PG）。

Task 3.4 / 需求 9.1-9.5、9.2：验证 v2 约定（category_natural_positive）下，
从 tb_balance 生成 trial_balance 时符号**无二次翻转**、全链路单一约定。

核心不变量：
1. 资产/成本/费用类：tb_balance 入库已是借方自然正数 → trial_balance.unadjusted_amount
   原样传递同一正数（无中间翻转，值与符号都一致）。
2. 负债/权益/收入类：v2 入库存自然正数 → trial_balance.unadjusted_amount 保持正数
   （应付账款 2202 / 主营业务收入 6001 等贷方正常类不被翻成负数）。
3. recalc_adjustments + recalc_audited 后 audited 方向正确：
   负债贷记增加→审定数增大，借记减少→审定数减小。
4. 链路 tb_balance → trial_balance 资产负债表科目符号一一对应（端到端无符号累积翻转）。

需真实 PG（与 test_ledger_dedup.py 同款 fixture），PG 不可达则 skip。

Validates: Requirements 9.1, 9.2, 9.4, 9.5
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.audit_platform_models import (
    AccountCategory,
    AccountChart,
    AccountDirection,
    AccountMapping,
    AccountSource,
    Adjustment,
    AdjustmentType,
    MappingType,
    TbBalance,
    TrialBalance,
)
from app.services.trial_balance_service import TrialBalanceService

_TEST_PROJECT_ID = uuid.UUID("519c0de0-0000-4000-8000-000000000abc")
_TEST_YEAR = 2097
_COMPANY = "001"
_IS_PG = settings.DATABASE_URL.startswith("postgresql")


@pytest_asyncio.fixture
async def pg_factory():
    """真实 PG session factory + 测试项目 seed + 收尾清理。"""
    if not _IS_PG:
        pytest.skip("need PostgreSQL (sign passthrough integration test)")

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")

    factory = async_sessionmaker(engine, expire_on_commit=False)

    from app.models.core import Project, ProjectStatus, ProjectType, User

    async def _cleanup():
        async with factory() as db:
            for tbl in (TrialBalance, Adjustment, TbBalance, AccountMapping, AccountChart):
                await db.execute(
                    sa.delete(tbl).where(tbl.project_id == _TEST_PROJECT_ID)
                )
            await db.commit()

    await _cleanup()

    async with factory() as db:
        user = (
            await db.execute(
                sa.select(User).where(User.username == "_sign_passthrough_user")
            )
        ).scalar_one_or_none()
        if user:
            uid = user.id
        else:
            uid = uuid.uuid4()
            db.add(
                User(
                    id=uid,
                    username="_sign_passthrough_user",
                    email="signpass@test.com",
                    hashed_password="x",
                    role="admin",
                )
            )
            await db.flush()
        if not (
            await db.execute(
                sa.select(Project).where(Project.id == _TEST_PROJECT_ID)
            )
        ).scalar_one_or_none():
            db.add(
                Project(
                    id=_TEST_PROJECT_ID,
                    name="sign-passthrough-test",
                    client_name="X",
                    project_type=ProjectType.annual,
                    status=ProjectStatus.execution,
                    created_by=uid,
                )
            )
        await db.commit()

    yield factory, uid
    await _cleanup()
    await engine.dispose()


async def _seed_balances(factory, uid):
    """构造 v2 自然正数账套：资产借方正、负债/权益/收入贷方正。"""
    async with factory() as db:
        pid = _TEST_PROJECT_ID
        # 标准科目（提供 category，供 recalc 类别判断）
        db.add_all([
            AccountChart(
                project_id=pid, account_code="1001", account_name="库存现金",
                direction=AccountDirection.debit, level=1,
                category=AccountCategory.asset, source=AccountSource.standard,
            ),
            AccountChart(
                project_id=pid, account_code="1122", account_name="应收账款",
                direction=AccountDirection.debit, level=1,
                category=AccountCategory.asset, source=AccountSource.standard,
            ),
            AccountChart(
                project_id=pid, account_code="2202", account_name="应付账款",
                direction=AccountDirection.credit, level=1,
                category=AccountCategory.liability, source=AccountSource.standard,
            ),
            AccountChart(
                project_id=pid, account_code="4001", account_name="实收资本",
                direction=AccountDirection.credit, level=1,
                category=AccountCategory.equity, source=AccountSource.standard,
            ),
            AccountChart(
                project_id=pid, account_code="6001", account_name="主营业务收入",
                direction=AccountDirection.credit, level=1,
                category=AccountCategory.revenue, source=AccountSource.standard,
            ),
        ])
        # 客户科目 → 标准科目 1:1 映射
        db.add_all([
            AccountMapping(
                project_id=pid, original_account_code="C1001",
                original_account_name="现金", standard_account_code="1001",
                mapping_type=MappingType.auto_exact, created_by=uid,
            ),
            AccountMapping(
                project_id=pid, original_account_code="C1122",
                original_account_name="应收账款", standard_account_code="1122",
                mapping_type=MappingType.auto_exact, created_by=uid,
            ),
            AccountMapping(
                project_id=pid, original_account_code="C2202",
                original_account_name="应付账款", standard_account_code="2202",
                mapping_type=MappingType.auto_exact, created_by=uid,
            ),
            AccountMapping(
                project_id=pid, original_account_code="C4001",
                original_account_name="实收资本", standard_account_code="4001",
                mapping_type=MappingType.auto_exact, created_by=uid,
            ),
            AccountMapping(
                project_id=pid, original_account_code="C6001",
                original_account_name="销售收入", standard_account_code="6001",
                mapping_type=MappingType.auto_exact, created_by=uid,
            ),
        ])
        # tb_balance：v2 约定自然正数入库
        db.add_all([
            # 资产借方正数
            TbBalance(
                project_id=pid, year=_TEST_YEAR, company_code=_COMPANY,
                account_code="C1001", account_name="现金",
                opening_balance=Decimal("10000"), closing_balance=Decimal("12000"),
                debit_amount=Decimal("5000"), credit_amount=Decimal("3000"),
                closing_direction="debit", sign_convention_version="v2_category_natural_positive",
            ),
            TbBalance(
                project_id=pid, year=_TEST_YEAR, company_code=_COMPANY,
                account_code="C1122", account_name="应收账款",
                opening_balance=Decimal("40000"), closing_balance=Decimal("50000"),
                debit_amount=Decimal("20000"), credit_amount=Decimal("10000"),
                closing_direction="debit", sign_convention_version="v2_category_natural_positive",
            ),
            # 负债贷方余额：v2 存正数 +8000
            TbBalance(
                project_id=pid, year=_TEST_YEAR, company_code=_COMPANY,
                account_code="C2202", account_name="应付账款",
                opening_balance=Decimal("6000"), closing_balance=Decimal("8000"),
                debit_amount=Decimal("0"), credit_amount=Decimal("2000"),
                closing_direction="credit", sign_convention_version="v2_category_natural_positive",
            ),
            # 权益贷方余额：v2 存正数 +30000
            TbBalance(
                project_id=pid, year=_TEST_YEAR, company_code=_COMPANY,
                account_code="C4001", account_name="实收资本",
                opening_balance=Decimal("30000"), closing_balance=Decimal("30000"),
                debit_amount=Decimal("0"), credit_amount=Decimal("0"),
                closing_direction="credit", sign_convention_version="v2_category_natural_positive",
            ),
            # 收入类：期末已结转为 0，本期贷方发生额 100000
            TbBalance(
                project_id=pid, year=_TEST_YEAR, company_code=_COMPANY,
                account_code="C6001", account_name="销售收入",
                opening_balance=Decimal("0"), closing_balance=Decimal("0"),
                debit_amount=Decimal("0"), credit_amount=Decimal("100000"),
                closing_direction="credit", sign_convention_version="v2_category_natural_positive",
            ),
        ])
        await db.commit()
    return pid


@pytest.mark.asyncio
async def test_unadjusted_balance_sheet_signs_passthrough(pg_factory):
    """资产/负债/权益类：tb_balance v2 正数 → trial_balance.unadjusted_amount 原样正数（无翻转）。

    Validates: Requirements 9.1, 9.2, 9.4
    """
    factory, uid = pg_factory
    pid = await _seed_balances(factory, uid)

    async with factory() as db:
        svc = TrialBalanceService(db)
        await svc.recalc_unadjusted(pid, _TEST_YEAR, _COMPANY)
        await db.commit()
        rows = await svc.get_trial_balance(pid, _TEST_YEAR, _COMPANY)

    tb_map = {r.standard_account_code: r for r in rows}
    # 资产借方正数原样传递
    assert tb_map["1001"].unadjusted_amount == Decimal("12000")
    assert tb_map["1122"].unadjusted_amount == Decimal("50000")
    # 负债/权益贷方余额：v2 保持正数，不被翻成负数
    assert tb_map["2202"].unadjusted_amount == Decimal("8000")
    assert tb_map["4001"].unadjusted_amount == Decimal("30000")
    # 全部为非负（资产负债表科目均自然正数）
    for code in ("1001", "1122", "2202", "4001"):
        assert tb_map[code].unadjusted_amount >= 0


@pytest.mark.asyncio
async def test_unadjusted_revenue_credit_positive(pg_factory):
    """收入类（贷方正常）：本期贷方发生额 → trial_balance 存自然正数（非旧约定 -total_cr）。

    Validates: Requirements 9.1, 9.2
    """
    factory, uid = pg_factory
    pid = await _seed_balances(factory, uid)

    async with factory() as db:
        svc = TrialBalanceService(db)
        await svc.recalc_unadjusted(pid, _TEST_YEAR, _COMPANY)
        await db.commit()
        rows = await svc.get_trial_balance(pid, _TEST_YEAR, _COMPANY)

    tb_map = {r.standard_account_code: r for r in rows}
    # 6001 收入：贷方发生额 100000 → v2 自然正数 +100000（旧约定会存 -100000）
    assert tb_map["6001"].unadjusted_amount == Decimal("100000")


@pytest.mark.asyncio
async def test_full_chain_no_second_flip(pg_factory):
    """链路 tb_balance.closing_balance → trial_balance.unadjusted_amount 资产负债表科目逐一对应。

    端到端断言：来源 tb_balance 的 v2 符号在 trial_balance 生成中保持单一约定，
    无中间二次翻转（值与符号都相等）。

    Validates: Requirements 9.4, 9.5
    """
    factory, uid = pg_factory
    pid = await _seed_balances(factory, uid)

    async with factory() as db:
        svc = TrialBalanceService(db)
        await svc.full_recalc(pid, _TEST_YEAR, _COMPANY)
        await db.commit()

        # 来源 tb_balance：客户科目 closing（资产负债表科目，1:1 映射）
        bal_rows = (
            await db.execute(
                sa.select(TbBalance).where(
                    TbBalance.project_id == pid,
                    TbBalance.year == _TEST_YEAR,
                    TbBalance.is_deleted == sa.false(),
                )
            )
        ).scalars().all()
        rows = await svc.get_trial_balance(pid, _TEST_YEAR, _COMPANY)

    tb_map = {r.standard_account_code: r for r in rows}
    # 客户科目 → 标准科目映射（1:1，资产负债表科目）
    bs_pairs = {"C1001": "1001", "C1122": "1122", "C2202": "2202", "C4001": "4001"}
    bal_by_code = {b.account_code: b for b in bal_rows}
    for client_code, std_code in bs_pairs.items():
        src_closing = bal_by_code[client_code].closing_balance
        tb_unadj = tb_map[std_code].unadjusted_amount
        # 符号一致（无翻转）
        assert (src_closing >= 0) == (tb_unadj >= 0), (
            f"{std_code} 符号被翻转: 来源 {src_closing} vs trial {tb_unadj}"
        )
        # 值一致（资产负债表科目直接传递，未做二次处理）
        assert tb_unadj == src_closing, (
            f"{std_code} 值不一致: 来源 {src_closing} vs trial {tb_unadj}"
        )


@pytest.mark.asyncio
async def test_audited_liability_credit_increase_direction(pg_factory):
    """负债贷记增加：unadjusted +8000 + AJE 贷记 1000 → audited 9000（方向正确，负债增加）。

    Validates: Requirements 9.4
    """
    factory, uid = pg_factory
    pid = await _seed_balances(factory, uid)

    async with factory() as db:
        svc = TrialBalanceService(db)
        await svc.recalc_unadjusted(pid, _TEST_YEAR, _COMPANY)
        group_id = uuid.uuid4()
        db.add(Adjustment(
            project_id=pid, year=_TEST_YEAR, company_code=_COMPANY,
            adjustment_no="AJE-LIAB-INC", adjustment_type=AdjustmentType.aje,
            account_code="2202", account_name="应付账款",
            debit_amount=Decimal("0"), credit_amount=Decimal("1000"),
            entry_group_id=group_id, created_by=uid,
        ))
        await db.flush()
        await svc.recalc_adjustments(pid, _TEST_YEAR, _COMPANY)
        await svc.recalc_audited(pid, _TEST_YEAR, _COMPANY)
        await db.commit()
        rows = await svc.get_trial_balance(pid, _TEST_YEAR, _COMPANY)

    tb_map = {r.standard_account_code: r for r in rows}
    # 贷记增加归一为 +1000，审定数 8000 + 1000 = 9000
    assert tb_map["2202"].aje_adjustment == Decimal("1000")
    assert tb_map["2202"].audited_amount == Decimal("9000")


@pytest.mark.asyncio
async def test_audited_revenue_credit_increase_direction(pg_factory):
    """收入贷记增加：unadjusted +100000 + AJE 贷记 500 → audited 100500（方向正确）。

    Validates: Requirements 9.4
    """
    factory, uid = pg_factory
    pid = await _seed_balances(factory, uid)

    async with factory() as db:
        svc = TrialBalanceService(db)
        await svc.recalc_unadjusted(pid, _TEST_YEAR, _COMPANY)
        group_id = uuid.uuid4()
        db.add(Adjustment(
            project_id=pid, year=_TEST_YEAR, company_code=_COMPANY,
            adjustment_no="AJE-REV-INC", adjustment_type=AdjustmentType.aje,
            account_code="6001", account_name="主营业务收入",
            debit_amount=Decimal("0"), credit_amount=Decimal("500"),
            entry_group_id=group_id, created_by=uid,
        ))
        await db.flush()
        await svc.recalc_adjustments(pid, _TEST_YEAR, _COMPANY)
        await svc.recalc_audited(pid, _TEST_YEAR, _COMPANY)
        await db.commit()
        rows = await svc.get_trial_balance(pid, _TEST_YEAR, _COMPANY)

    tb_map = {r.standard_account_code: r for r in rows}
    assert tb_map["6001"].aje_adjustment == Decimal("500")
    assert tb_map["6001"].audited_amount == Decimal("100500")
