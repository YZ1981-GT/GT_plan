"""test_adj_amount_source_parity.py — 口径对账守卫：批量路径 vs 单点路径 逐值相等.

spec: adj-formula-repair-and-approval-gate-wiring · 阶段 0 任务 0.3
修复前红（adj_net / recalc_adjustments 尚未统一前应不一致）、统一后绿。

守卫内容：
1. P5 — 同 (project_id, year, account_code, adj_type)，批量路径写入 TB 列值
   与单点路径 adj_net 返回值逐值相等。
2. P6 — `exclude_origins={"workpaper"}` 与空集在存在 workpaper 来源分录时**必不相等**
   （origin 维度可参数化变异证明）。
3. P12 — 双向变异：正样本(有数据→非零) + 负样本(无数据→零)；
   workpaper 排除正/反样本配对。

真 SQLite + 真 ORM 行，不 mock DB 层。

Validates: Requirements 3.3 · Properties P5, P6, P12
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
_PROJECT_ID = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002")
_USER_ID = uuid.UUID("cccccccc-0000-4000-8000-000000000003")
_YEAR = 2099
_COMPANY = "001"
_ACCT_DEBIT = "1001"   # 资产类（借方正常方向） — 库存现金
_ACCT_CREDIT = "2202"  # 负债类（贷方正常方向） — 应付账款


# ---------------------------------------------------------------------------
# Fixture: 每个测试独立的 SQLite 内存 DB + session
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """全新内存 SQLite session（create_all → yield → dispose）。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# Helper: 插入 FK 先决行（Project + User）
# ---------------------------------------------------------------------------
async def _seed_fk_parents(db: AsyncSession) -> None:
    """插入 adjustments 所需 FK 父行（projects / users）。"""
    from app.models.core import Project, User

    db.add(User(id=_USER_ID, username="test_adj_parity", email="adj@test.local",
                hashed_password="x", role="admin"))
    db.add(Project(id=_PROJECT_ID, name="adj_parity_test", client_name="测试客户",
                   status="active", created_by=_USER_ID))
    await db.flush()


# ---------------------------------------------------------------------------
# Helper: 插入 Adjustment + AdjustmentEntry 行
# ---------------------------------------------------------------------------
async def _seed_adjustment(
    db: AsyncSession,
    *,
    adj_type: str,          # "aje" | "rje"
    account_code: str,
    debit: Decimal,
    credit: Decimal,
    review_status: str = "approved",
    origin: str = "manual",
    account_name: str = "",
) -> None:
    """插入一条 Adjustment 主表 + 一条 AdjustmentEntry 行。"""
    from app.models.audit_platform_models import Adjustment, AdjustmentEntry, AdjustmentType

    adj_id = uuid.uuid4()
    entry_group_id = uuid.uuid4()

    db.add(Adjustment(
        id=adj_id,
        project_id=_PROJECT_ID,
        year=_YEAR,
        company_code=_COMPANY,
        adjustment_no=f"ADJ-{adj_id.hex[:8]}",
        adjustment_type=AdjustmentType(adj_type),
        account_code=account_code,
        account_name=account_name,
        entry_group_id=entry_group_id,
        review_status=review_status,
        origin=origin,
        is_deleted=False,
        created_by=_USER_ID,
    ))
    db.add(AdjustmentEntry(
        id=uuid.uuid4(),
        adjustment_id=adj_id,
        entry_group_id=entry_group_id,
        line_no=1,
        standard_account_code=account_code,
        account_name=account_name,
        debit_amount=debit,
        credit_amount=credit,
        is_deleted=False,
    ))
    await db.flush()


# ---------------------------------------------------------------------------
# Helper: 插入 TrialBalance 行（batch 路径写入目标）
# ---------------------------------------------------------------------------
async def _seed_tb_row(db: AsyncSession, account_code: str, account_name: str = "") -> None:
    """插入一条 TrialBalance 行供 recalc_adjustments 写入。"""
    from app.models.audit_platform_models import TrialBalance, AccountCategory

    # 按编码首位判断类别（简化：1xxx=asset, 2xxx=liability）
    cat = AccountCategory.asset if account_code.startswith("1") else AccountCategory.liability

    db.add(TrialBalance(
        id=uuid.uuid4(),
        project_id=_PROJECT_ID,
        year=_YEAR,
        company_code=_COMPANY,
        standard_account_code=account_code,
        account_name=account_name,
        account_category=cat,
        unadjusted_amount=Decimal("10000"),
        rje_adjustment=Decimal("0"),
        aje_adjustment=Decimal("0"),
        audited_amount=Decimal("10000"),
        is_deleted=False,
    ))
    await db.flush()


# ---------------------------------------------------------------------------
# Helper: 读取 recalc_adjustments 批量路径写入的 TB 列值
# ---------------------------------------------------------------------------
async def _run_batch_and_read_tb(
    db: AsyncSession, account_code: str, adj_type: str
) -> Decimal:
    """运行批量 recalc_adjustments，然后读取 TB 行的 aje/rje_adjustment 列值。"""
    from app.models.audit_platform_models import TrialBalance
    from app.services.trial_balance_service import TrialBalanceService

    svc = TrialBalanceService(db)
    await svc.recalc_adjustments(_PROJECT_ID, _YEAR, _COMPANY, account_codes=[account_code])
    await db.flush()

    import sqlalchemy as sa
    q = sa.select(TrialBalance).where(
        TrialBalance.project_id == _PROJECT_ID,
        TrialBalance.year == _YEAR,
        TrialBalance.company_code == _COMPANY,
        TrialBalance.standard_account_code == account_code,
    )
    result = await db.execute(q)
    row = result.scalars().first()
    assert row is not None, f"TrialBalance 行 {account_code} 未找到"

    if adj_type in ("aje", "aje_net", "AJE", "审计调整"):
        return row.aje_adjustment
    else:
        return row.rje_adjustment


# ===========================================================================
# P5: 批量路径与单点路径逐值相等
# ===========================================================================
class TestBatchVsSinglePointParity:
    """同 (project_id, year, account_code, adj_type) 下，
    recalc_adjustments 写入 TB 的列值 == adj_net 返回值。

    Validates: Requirements 3.3 · Properties P5
    """

    @pytest.mark.asyncio
    async def test_aje_debit_account_parity(self, db_session: AsyncSession):
        """借方类科目（1001）AJE：批量 == 单点。"""
        await _seed_fk_parents(db_session)
        await _seed_tb_row(db_session, _ACCT_DEBIT, "库存现金")
        await _seed_adjustment(
            db_session, adj_type="aje", account_code=_ACCT_DEBIT,
            debit=Decimal("500"), credit=Decimal("0"), account_name="库存现金",
        )

        from app.services.adjustment_amount_source import adj_net

        single = await adj_net(
            db_session, project_id=_PROJECT_ID, year=_YEAR,
            account_code=_ACCT_DEBIT, adj_type="aje_net",
            # 与 recalc_adjustments 同口径：排除 workpaper + 仅 approved
            exclude_origins=frozenset({"workpaper"}),
        )
        batch = await _run_batch_and_read_tb(db_session, _ACCT_DEBIT, "aje")

        assert single == batch, (
            f"P5 违反：adj_net={single} != recalc_adjustments={batch}（AJE, 借方, {_ACCT_DEBIT}）"
        )

    @pytest.mark.asyncio
    async def test_rje_debit_account_parity(self, db_session: AsyncSession):
        """借方类科目（1001）RJE：批量 == 单点。"""
        await _seed_fk_parents(db_session)
        await _seed_tb_row(db_session, _ACCT_DEBIT, "库存现金")
        await _seed_adjustment(
            db_session, adj_type="rje", account_code=_ACCT_DEBIT,
            debit=Decimal("300"), credit=Decimal("0"), account_name="库存现金",
        )

        from app.services.adjustment_amount_source import adj_net

        single = await adj_net(
            db_session, project_id=_PROJECT_ID, year=_YEAR,
            account_code=_ACCT_DEBIT, adj_type="rje_net",
            exclude_origins=frozenset({"workpaper"}),
        )
        batch = await _run_batch_and_read_tb(db_session, _ACCT_DEBIT, "rje")

        assert single == batch, (
            f"P5 违反：adj_net={single} != recalc_adjustments={batch}（RJE, 借方, {_ACCT_DEBIT}）"
        )

    @pytest.mark.asyncio
    async def test_aje_credit_account_parity(self, db_session: AsyncSession):
        """贷方类科目（2202）AJE：批量 == 单点（符号归一一致性）。"""
        await _seed_fk_parents(db_session)
        await _seed_tb_row(db_session, _ACCT_CREDIT, "应付账款")
        # 贷记调整：debit=0, credit=1000 → SUM(d-c)=-1000 → 贷方类取反 → +1000
        await _seed_adjustment(
            db_session, adj_type="aje", account_code=_ACCT_CREDIT,
            debit=Decimal("0"), credit=Decimal("1000"), account_name="应付账款",
        )

        from app.services.adjustment_amount_source import adj_net

        single = await adj_net(
            db_session, project_id=_PROJECT_ID, year=_YEAR,
            account_code=_ACCT_CREDIT, adj_type="aje_net",
            exclude_origins=frozenset({"workpaper"}),
        )
        batch = await _run_batch_and_read_tb(db_session, _ACCT_CREDIT, "aje")

        assert single == batch, (
            f"P5 违反：adj_net={single} != recalc_adjustments={batch}（AJE, 贷方, {_ACCT_CREDIT}）"
        )

    @pytest.mark.asyncio
    async def test_multiple_entries_parity(self, db_session: AsyncSession):
        """同科目多笔分录：批量聚合 == 单点聚合。"""
        await _seed_fk_parents(db_session)
        await _seed_tb_row(db_session, _ACCT_DEBIT, "库存现金")
        # 两笔 AJE：debit 200 + debit 300 = net 500
        await _seed_adjustment(
            db_session, adj_type="aje", account_code=_ACCT_DEBIT,
            debit=Decimal("200"), credit=Decimal("0"), account_name="库存现金",
        )
        await _seed_adjustment(
            db_session, adj_type="aje", account_code=_ACCT_DEBIT,
            debit=Decimal("300"), credit=Decimal("0"), account_name="库存现金",
        )

        from app.services.adjustment_amount_source import adj_net

        single = await adj_net(
            db_session, project_id=_PROJECT_ID, year=_YEAR,
            account_code=_ACCT_DEBIT, adj_type="aje_net",
            exclude_origins=frozenset({"workpaper"}),
        )
        batch = await _run_batch_and_read_tb(db_session, _ACCT_DEBIT, "aje")

        assert single == batch, (
            f"P5 违反（多笔）：adj_net={single} != recalc_adjustments={batch}"
        )


# ===========================================================================
# P6: exclude_origins 参数化变异证明
# ===========================================================================
class TestOriginParameterization:
    """存在 workpaper 来源分录时，exclude_origins={"workpaper"} 与空集必不相等。

    Validates: Requirements 3.3 · Properties P6, P12
    """

    @pytest.mark.asyncio
    async def test_workpaper_origin_excluded_differs(self, db_session: AsyncSession):
        """P6: 有 workpaper 分录时，排除 vs 不排除必产生不同结果。"""
        await _seed_fk_parents(db_session)

        # 一笔 manual 来源 + 一笔 workpaper 来源（同科目同类型）
        await _seed_adjustment(
            db_session, adj_type="aje", account_code=_ACCT_DEBIT,
            debit=Decimal("1000"), credit=Decimal("0"),
            origin="manual", account_name="库存现金",
        )
        await _seed_adjustment(
            db_session, adj_type="aje", account_code=_ACCT_DEBIT,
            debit=Decimal("500"), credit=Decimal("0"),
            origin="workpaper", account_name="库存现金",
        )

        from app.services.adjustment_amount_source import adj_net

        # 不排除 workpaper（ADJ() 底稿呈现口径）
        val_inclusive = await adj_net(
            db_session, project_id=_PROJECT_ID, year=_YEAR,
            account_code=_ACCT_DEBIT, adj_type="aje_net",
            exclude_origins=frozenset(),
        )
        # 排除 workpaper（TB 调整列口径）
        val_exclusive = await adj_net(
            db_session, project_id=_PROJECT_ID, year=_YEAR,
            account_code=_ACCT_DEBIT, adj_type="aje_net",
            exclude_origins=frozenset({"workpaper"}),
        )

        assert val_inclusive != val_exclusive, (
            f"P6 违反：有 workpaper 分录时排除/不排除应不同，"
            f"inclusive={val_inclusive}, exclusive={val_exclusive}"
        )
        # 进一步验证方向：排除后应更小
        assert val_exclusive < val_inclusive, (
            f"排除 workpaper 后应更小：exclusive={val_exclusive} >= inclusive={val_inclusive}"
        )

    @pytest.mark.asyncio
    async def test_no_workpaper_origin_same(self, db_session: AsyncSession):
        """P12 配对反样本：无 workpaper 分录时，排除/不排除结果相等。"""
        await _seed_fk_parents(db_session)

        # 只有 manual 来源
        await _seed_adjustment(
            db_session, adj_type="aje", account_code=_ACCT_DEBIT,
            debit=Decimal("800"), credit=Decimal("0"),
            origin="manual", account_name="库存现金",
        )

        from app.services.adjustment_amount_source import adj_net

        val_inclusive = await adj_net(
            db_session, project_id=_PROJECT_ID, year=_YEAR,
            account_code=_ACCT_DEBIT, adj_type="aje_net",
            exclude_origins=frozenset(),
        )
        val_exclusive = await adj_net(
            db_session, project_id=_PROJECT_ID, year=_YEAR,
            account_code=_ACCT_DEBIT, adj_type="aje_net",
            exclude_origins=frozenset({"workpaper"}),
        )

        assert val_inclusive == val_exclusive, (
            f"P12 配对：无 workpaper 时排除/不排除应相同，"
            f"inclusive={val_inclusive}, exclusive={val_exclusive}"
        )


# ===========================================================================
# P12: 双向变异守卫（正样本非零 + 负样本为零）
# ===========================================================================
class TestBidirectionalMutation:
    """每条「结构性零」断言都配正样本非零断言。

    Validates: Properties P12
    """

    @pytest.mark.asyncio
    async def test_positive_sample_nonzero(self, db_session: AsyncSession):
        """正样本：有 approved 分录 → adj_net 返回非零。"""
        await _seed_fk_parents(db_session)
        await _seed_adjustment(
            db_session, adj_type="aje", account_code=_ACCT_DEBIT,
            debit=Decimal("777"), credit=Decimal("0"), account_name="库存现金",
        )

        from app.services.adjustment_amount_source import adj_net

        val = await adj_net(
            db_session, project_id=_PROJECT_ID, year=_YEAR,
            account_code=_ACCT_DEBIT, adj_type="aje_net",
        )
        assert val != Decimal("0"), f"正样本应非零，得到 {val}"
        assert val == Decimal("777"), f"预期 777，得到 {val}"

    @pytest.mark.asyncio
    async def test_negative_sample_zero(self, db_session: AsyncSession):
        """负样本：无分录 → adj_net 返回零。"""
        await _seed_fk_parents(db_session)

        from app.services.adjustment_amount_source import adj_net

        val = await adj_net(
            db_session, project_id=_PROJECT_ID, year=_YEAR,
            account_code=_ACCT_DEBIT, adj_type="aje_net",
        )
        assert val == Decimal("0"), f"负样本应为零，得到 {val}"

    @pytest.mark.asyncio
    async def test_draft_not_included_in_default_scope(self, db_session: AsyncSession):
        """P12 变异：草稿分录不进默认口径（ADR-ADJ-003 仅 approved）。

        正样本：approved → 非零；反样本：draft → 零（默认口径下）。
        """
        await _seed_fk_parents(db_session)

        # 只有 draft 分录
        await _seed_adjustment(
            db_session, adj_type="aje", account_code=_ACCT_DEBIT,
            debit=Decimal("999"), credit=Decimal("0"),
            review_status="draft", account_name="库存现金",
        )

        from app.services.adjustment_amount_source import adj_net

        # 默认口径（仅 approved）→ draft 不进 → 零
        val_default = await adj_net(
            db_session, project_id=_PROJECT_ID, year=_YEAR,
            account_code=_ACCT_DEBIT, adj_type="aje_net",
        )
        assert val_default == Decimal("0"), (
            f"draft 不应进默认口径，得到 {val_default}"
        )

        # 显式传空 statuses（不过滤）→ draft 进 → 非零
        val_all = await adj_net(
            db_session, project_id=_PROJECT_ID, year=_YEAR,
            account_code=_ACCT_DEBIT, adj_type="aje_net",
            include_statuses=frozenset(),
        )
        assert val_all != Decimal("0"), (
            f"显式不过滤 status 时 draft 应进口径，得到 {val_all}"
        )

    @pytest.mark.asyncio
    async def test_batch_positive_sample_nonzero(self, db_session: AsyncSession):
        """P12 配对：批量路径正样本（有 approved 分录 → TB 列非零）。"""
        await _seed_fk_parents(db_session)
        await _seed_tb_row(db_session, _ACCT_DEBIT, "库存现金")
        await _seed_adjustment(
            db_session, adj_type="aje", account_code=_ACCT_DEBIT,
            debit=Decimal("400"), credit=Decimal("0"), account_name="库存现金",
        )

        batch_val = await _run_batch_and_read_tb(db_session, _ACCT_DEBIT, "aje")
        assert batch_val != Decimal("0"), f"批量正样本应非零，得到 {batch_val}"

    @pytest.mark.asyncio
    async def test_batch_negative_sample_zero(self, db_session: AsyncSession):
        """P12 配对：批量路径负样本（无分录 → TB 列为零）。"""
        await _seed_fk_parents(db_session)
        await _seed_tb_row(db_session, _ACCT_DEBIT, "库存现金")

        batch_val = await _run_batch_and_read_tb(db_session, _ACCT_DEBIT, "aje")
        assert batch_val == Decimal("0"), f"批量负样本应为零，得到 {batch_val}"
