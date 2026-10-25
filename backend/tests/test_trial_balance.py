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


async def _add_adj(
    db: AsyncSession,
    *,
    pid,
    adj_type: AdjustmentType,
    account_code: str,
    account_name: str,
    debit: Decimal,
    credit: Decimal,
    adjustment_no: str,
    year: int = 2025,
    company_code: str = "001",
    review_status: ReviewStatus = ReviewStatus.approved,
    origin: str = "manual",
) -> None:
    """插入 Adjustment 主表 + AdjustmentEntry **明细行**。

    🔴 **必须建明细行**：`recalc_adjustments` 已按 ADR-ADJ-001 改为读
    `adjustment_entries.standard_account_code` + JOIN 主表。改造前本文件的
    fixture 只往主表塞 `account_code`/`debit_amount`/`credit_amount` 三个
    **遗留冗余列** ⇒ JOIN 结果为空 ⇒ 调整列恒 0 ⇒ 5 个测试长期红。
    （真库实测这三列全库 0 非零，已是废弃列。）

    🔴 **必须显式 `approved`**：`Adjustment.review_status` 的 server_default 是
    **`draft`**，而 `recalc_adjustments` 按 ADR-ADJ-003 只纳入 approved。
    不显式设置的话，就算建了明细行照样取不到数。

    🔴 **origin 必须非 workpaper**：ADR-ADJ-002 / V124 约定 TB 调整列排除
    workpaper 来源（底稿调整已由审定表 writeback 体现于 audited_amount）。
    """
    from app.models.audit_platform_models import AdjustmentEntry

    adj_id = uuid.uuid4()
    grp = uuid.uuid4()
    db.add(Adjustment(
        id=adj_id,
        project_id=pid, year=year, company_code=company_code,
        adjustment_no=adjustment_no, adjustment_type=adj_type,
        account_code=account_code, account_name=account_name,
        debit_amount=debit, credit_amount=credit,
        entry_group_id=grp, review_status=review_status, origin=origin,
        is_deleted=False, created_by=FAKE_USER_ID,
    ))
    db.add(AdjustmentEntry(
        id=uuid.uuid4(), adjustment_id=adj_id, entry_group_id=grp, line_no=1,
        standard_account_code=account_code, account_name=account_name,
        debit_amount=debit, credit_amount=credit, is_deleted=False,
    ))
    await db.flush()


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

    # 负债类标准科目（贷方正常，v2 下存正数）
    db_session.add(
        AccountChart(
            project_id=pid, account_code="2202", account_name="应付账款",
            direction=AccountDirection.credit, level=1,
            category=AccountCategory.liability, source=AccountSource.standard,
        )
    )

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

    # 负债类客户科目映射
    db_session.add(
        AccountMapping(
            project_id=pid, original_account_code="C2202",
            original_account_name="应付账款", standard_account_code="2202",
            mapping_type=MappingType.auto_exact, created_by=FAKE_USER_ID,
        )
    )

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

    # 负债类余额（v2 约定：应付账款贷方余额存正数 +8000）
    db_session.add(
        TbBalance(
            project_id=pid, year=2025, company_code="001",
            account_code="C2202", account_name="应付账款",
            opening_balance=Decimal("6000"), closing_balance=Decimal("8000"),
            debit_amount=Decimal("0"), credit_amount=Decimal("2000"),
        )
    )

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


@pytest.mark.asyncio
async def test_recalc_leaf_only_no_parent_child_double_count(
    db_session: AsyncSession, seeded_db
):
    """父子科目都映射到同一标准科目时，只汇总叶子节点，不重复累加。

    回归：客户科目表是多级树（1122 父 / 1122.01 子），父级余额=子级之和。
    account_mapping 把每级都映射到标准科目，若汇总父子全加会翻倍
    （试算表资产≠负债+权益）。recalc 必须只取叶子节点。
    """
    pid = seeded_db
    # 标准科目 1122 应收账款
    db_session.add(
        AccountChart(
            project_id=pid, account_code="1122", account_name="应收账款",
            direction=AccountDirection.debit, level=1,
            category=AccountCategory.asset, source=AccountSource.standard,
        )
    )
    # 客户科目：父级 1122（=子级之和 600）+ 两个叶子子级 1122.01=400 / 1122.02=200
    db_session.add_all([
        AccountMapping(
            project_id=pid, original_account_code="1122",
            original_account_name="应收账款", standard_account_code="1122",
            mapping_type=MappingType.auto_exact, created_by=FAKE_USER_ID,
        ),
        AccountMapping(
            project_id=pid, original_account_code="1122.01",
            original_account_name="应收账款_货款", standard_account_code="1122",
            mapping_type=MappingType.auto_exact, created_by=FAKE_USER_ID,
        ),
        AccountMapping(
            project_id=pid, original_account_code="1122.02",
            original_account_name="应收账款_质保金", standard_account_code="1122",
            mapping_type=MappingType.auto_exact, created_by=FAKE_USER_ID,
        ),
    ])
    db_session.add_all([
        TbBalance(
            project_id=pid, year=2025, company_code="001", level=1,
            account_code="1122", account_name="应收账款",
            opening_balance=Decimal("0"), closing_balance=Decimal("600"),
        ),
        TbBalance(
            project_id=pid, year=2025, company_code="001", level=2,
            account_code="1122.01", account_name="应收账款_货款",
            opening_balance=Decimal("0"), closing_balance=Decimal("400"),
        ),
        TbBalance(
            project_id=pid, year=2025, company_code="001", level=2,
            account_code="1122.02", account_name="应收账款_质保金",
            opening_balance=Decimal("0"), closing_balance=Decimal("200"),
        ),
    ])
    await db_session.commit()

    svc = TrialBalanceService(db_session)
    await svc.recalc_unadjusted(pid, 2025)
    await db_session.commit()

    rows = await svc.get_trial_balance(pid, 2025)
    tb_map = {r.standard_account_code: r for r in rows}
    # 只取叶子（1122.01 + 1122.02 = 600），父级 1122 被排除，不翻倍成 1200
    assert tb_map["1122"].unadjusted_amount == Decimal("600")


@pytest.mark.asyncio
async def test_recalc_unmapped_leaf_inherits_parent_mapping(
    db_session: AsyncSession, seeded_db
):
    """未映射叶子继承最近已映射父科目的标准码（映射口径根治回归）。

    回归：auto_match 常出现「父科目已映射、部分子科目漏映射」——如
    1651 使用权资产→1641 已映射，但叶子 1651.02 使用权资产_房屋及建筑物 漏映射。
    原实现 INNER JOIN 精确匹配会静默丢弃漏映射叶子 → 报表资产≠负债+权益。
    修复后：叶子按「最长前缀匹配」继承祖先映射（1651.02 → 祖先 1651 → 1641）。
    """
    pid = seeded_db
    db_session.add(
        AccountChart(
            project_id=pid, account_code="1641", account_name="使用权资产",
            direction=AccountDirection.debit, level=1,
            category=AccountCategory.asset, source=AccountSource.standard,
        )
    )
    # 仅父科目 1651 有映射；两个叶子子科目其中 1651.02 漏映射
    db_session.add_all([
        AccountMapping(
            project_id=pid, original_account_code="1651",
            original_account_name="使用权资产", standard_account_code="1641",
            mapping_type=MappingType.auto_exact, created_by=FAKE_USER_ID,
        ),
        AccountMapping(
            project_id=pid, original_account_code="1651.01",
            original_account_name="使用权资产_土地", standard_account_code="1641",
            mapping_type=MappingType.auto_fuzzy, created_by=FAKE_USER_ID,
        ),
        # 注意：1651.02 故意不加映射，验证其继承父级 1651→1641
    ])
    db_session.add_all([
        TbBalance(
            project_id=pid, year=2025, company_code="001", level=1,
            account_code="1651", account_name="使用权资产",
            opening_balance=Decimal("0"), closing_balance=Decimal("300"),
            opening_direction="debit", closing_direction="debit",
        ),
        TbBalance(
            project_id=pid, year=2025, company_code="001", level=2,
            account_code="1651.01", account_name="使用权资产_土地",
            opening_balance=Decimal("0"), closing_balance=Decimal("100"),
            opening_direction="debit", closing_direction="debit",
        ),
        TbBalance(
            project_id=pid, year=2025, company_code="001", level=2,
            account_code="1651.02", account_name="使用权资产_房屋及建筑物",
            opening_balance=Decimal("0"), closing_balance=Decimal("200"),
            opening_direction="debit", closing_direction="debit",
        ),
    ])
    await db_session.commit()

    svc = TrialBalanceService(db_session)
    await svc.recalc_unadjusted(pid, 2025)
    await db_session.commit()

    rows = await svc.get_trial_balance(pid, 2025)
    tb_map = {r.standard_account_code: r for r in rows}
    # 叶子 1651.01(100) + 1651.02(200，继承父映射) = 300 归入标准科目 1641，
    # 修复前 1651.02 被丢弃只得 100。
    assert "1641" in tb_map
    assert tb_map["1641"].unadjusted_amount == Decimal("300")


# ===== 调整列重算 =====

@pytest.mark.asyncio
async def test_recalc_adjustments(db_session: AsyncSession, seeded_db):
    """调整列重算"""
    pid = seeded_db
    svc = TrialBalanceService(db_session)
    await svc.recalc_unadjusted(pid, 2025)

    # 添加调整分录（借 1001 / 贷 6001，一借一贷成对）
    await _add_adj(
        db_session, pid=pid, adj_type=AdjustmentType.aje,
        account_code="1001", account_name="库存现金",
        debit=Decimal("500"), credit=Decimal("0"), adjustment_no="AJE-001",
    )
    await _add_adj(
        db_session, pid=pid, adj_type=AdjustmentType.aje,
        account_code="6001", account_name="主营业务收入",
        debit=Decimal("0"), credit=Decimal("500"), adjustment_no="AJE-001",
    )

    await svc.recalc_adjustments(pid, 2025)
    await db_session.commit()

    rows = await svc.get_trial_balance(pid, 2025)
    tb_map = {r.standard_account_code: r for r in rows}
    assert tb_map["1001"].aje_adjustment == Decimal("500")
    # v2 约定：6001 收入类（贷方正常），一笔贷记 500 应使审定数增加，
    # 归一到自然方向后 aje 应为正数 +500（而非旧约定借正贷负的 -500）。
    assert tb_map["6001"].aje_adjustment == Decimal("500")


@pytest.mark.asyncio
async def test_recalc_unadjusted_preserves_workpaper_adjustment(
    db_session: AsyncSession, seeded_db
):
    """重导入未审数时保留已发布的底稿调整分量。"""
    pid = seeded_db
    svc = TrialBalanceService(db_session)
    await svc.recalc_unadjusted(pid, 2025)

    row = (await svc.get_trial_balance(pid, 2025))[0]
    row.wp_adjustment = Decimal("250")
    row.audited_amount = row.unadjusted_amount + Decimal("250")
    await db_session.flush()

    # 模拟重新导入余额表：未审数应更新，但底稿发布分量不能被清零。
    await svc.recalc_unadjusted(pid, 2025)
    await db_session.commit()

    refreshed = {
        item.standard_account_code: item
        for item in await svc.get_trial_balance(pid, 2025)
    }[row.standard_account_code]
    assert refreshed.unadjusted_amount == Decimal("12000")
    assert refreshed.wp_adjustment == Decimal("250")
    assert refreshed.audited_amount == Decimal("12250")


@pytest.mark.asyncio
async def test_recalc_audited_and_consistency_use_four_components(
    db_session: AsyncSession, seeded_db
):
    """审定数重算和一致性校验都使用四项公式。"""
    pid = seeded_db
    svc = TrialBalanceService(db_session)
    await svc.recalc_unadjusted(pid, 2025)

    row = (await svc.get_trial_balance(pid, 2025))[0]
    row.rje_adjustment = Decimal("10")
    row.aje_adjustment = Decimal("-20")
    row.wp_adjustment = Decimal("30")
    row.audited_amount = Decimal("0")
    await db_session.flush()

    await svc.recalc_audited(pid, 2025, account_codes=[row.standard_account_code])
    await db_session.commit()

    refreshed = {
        item.standard_account_code: item
        for item in await svc.get_trial_balance(pid, 2025)
    }[row.standard_account_code]
    expected = Decimal("12020.00")
    assert refreshed.audited_amount == expected
    assert await svc.check_consistency(pid, 2025) == []

    refreshed.audited_amount = Decimal("12000")
    await db_session.commit()
    issues = await svc.check_consistency(pid, 2025)
    assert len(issues) == 1
    assert issues[0]["type"] == "audited_formula"
    assert issues[0]["account_code"] == row.standard_account_code
    assert Decimal(issues[0]["expected"]) == expected
    assert Decimal(issues[0]["actual"]) == Decimal("12000")


# ===== 审定数重算 =====

@pytest.mark.asyncio
async def test_recalc_audited(db_session: AsyncSession, seeded_db):
    """审定数 = 未审数 + rje + aje"""
    pid = seeded_db
    svc = TrialBalanceService(db_session)
    await svc.recalc_unadjusted(pid, 2025)

    await _add_adj(
        db_session, pid=pid, adj_type=AdjustmentType.rje,
        account_code="1001", account_name="库存现金",
        debit=Decimal("1000"), credit=Decimal("0"), adjustment_no="RJE-001",
    )

    await svc.recalc_adjustments(pid, 2025)
    await svc.recalc_audited(pid, 2025)
    await db_session.commit()

    rows = await svc.get_trial_balance(pid, 2025)
    tb_map = {r.standard_account_code: r for r in rows}
    # 1001: 未审12000 + rje1000 + aje0 = 13000
    assert tb_map["1001"].audited_amount == Decimal("13000")


# ===== 负债类调整方向（需求 6.7，v2 自然正数约定） =====

@pytest.mark.asyncio
async def test_recalc_audited_liability_credit_increase(db_session: AsyncSession, seeded_db):
    """负债类贷记增加：unadjusted=+8000，AJE 贷记 1000 → audited=9000（方向正确）

    v2 约定下负债贷方余额存正数。一笔贷记负债增加的调整，归一到自然方向后
    aje 应为正数，使审定数增大；若沿用旧"借正贷负"净额会错误地减少负债。
    """
    pid = seeded_db
    svc = TrialBalanceService(db_session)
    await svc.recalc_unadjusted(pid, 2025)

    await _add_adj(
        db_session, pid=pid, adj_type=AdjustmentType.aje,
        account_code="2202", account_name="应付账款",
        debit=Decimal("0"), credit=Decimal("1000"), adjustment_no="AJE-LIAB-INC",
    )

    await svc.recalc_adjustments(pid, 2025)
    await svc.recalc_audited(pid, 2025)
    await db_session.commit()

    rows = await svc.get_trial_balance(pid, 2025)
    tb_map = {r.standard_account_code: r for r in rows}
    # 贷记增加归一为 +1000
    assert tb_map["2202"].aje_adjustment == Decimal("1000")
    # 审定数 = 8000 + 1000 = 9000（负债增加，方向正确）
    assert tb_map["2202"].audited_amount == Decimal("9000")


@pytest.mark.asyncio
async def test_recalc_audited_liability_debit_decrease(db_session: AsyncSession, seeded_db):
    """负债类借记减少：unadjusted=+8000，AJE 借记 1000 → audited=7000（方向正确）"""
    pid = seeded_db
    svc = TrialBalanceService(db_session)
    await svc.recalc_unadjusted(pid, 2025)

    await _add_adj(
        db_session, pid=pid, adj_type=AdjustmentType.aje,
        account_code="2202", account_name="应付账款",
        debit=Decimal("1000"), credit=Decimal("0"), adjustment_no="AJE-LIAB-DEC",
    )

    await svc.recalc_adjustments(pid, 2025)
    await svc.recalc_audited(pid, 2025)
    await db_session.commit()

    rows = await svc.get_trial_balance(pid, 2025)
    tb_map = {r.standard_account_code: r for r in rows}
    # 借记减少归一为 -1000
    assert tb_map["2202"].aje_adjustment == Decimal("-1000")
    # 审定数 = 8000 - 1000 = 7000（负债减少，方向正确）
    assert tb_map["2202"].audited_amount == Decimal("7000")


@pytest.mark.asyncio
async def test_recalc_audited_revenue_credit_increase(db_session: AsyncSession, seeded_db):
    """收入类贷记增加：unadjusted=+100000，AJE 贷记 500 → audited=100500（方向正确）"""
    pid = seeded_db
    svc = TrialBalanceService(db_session)
    await svc.recalc_unadjusted(pid, 2025)

    await _add_adj(
        db_session, pid=pid, adj_type=AdjustmentType.aje,
        account_code="6001", account_name="主营业务收入",
        debit=Decimal("0"), credit=Decimal("500"), adjustment_no="AJE-REV-INC",
    )

    await svc.recalc_adjustments(pid, 2025)
    await svc.recalc_audited(pid, 2025)
    await db_session.commit()

    rows = await svc.get_trial_balance(pid, 2025)
    tb_map = {r.standard_account_code: r for r in rows}
    assert tb_map["6001"].aje_adjustment == Decimal("500")
    assert tb_map["6001"].audited_amount == Decimal("100500")


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
        assert r.audited_amount == (
            unadj
            + (r.rje_adjustment or Decimal("0"))
            + (r.aje_adjustment or Decimal("0"))
            + (r.wp_adjustment or Decimal("0"))
        )


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
