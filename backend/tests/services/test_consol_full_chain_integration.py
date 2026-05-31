"""合并模块全链路集成测试（封板交付物 ①）

目标：用 **真实 SQLite DB + 真实 ORM 行 + 真实 service** 跑通整条合并管线，
捕捉单阶段 mock 测试抓不到的「跨阶段签名漂移」回归。这是会同时咬到以下两次
merge 回归的测试：
  1. Phase 1 把 generate_consol_reports_sync 改成 async，而 Phase 2 仍 sync 调用；
  2. Phase 1 删了 _execute_formula，令 Phase 2 报表公式失效。

与既有 test_consol_phase0_integration.py 的区别：那个是**纯函数**测试（喂内存
TreeNode/字典），不经 build_tree → ORM → upsert_trial_row 真实落库，因此抓不到
签名漂移 / NULL 主键 / async 未 await 等运行时缺陷。本测试用真实 DB 行。

覆盖：
- test_full_chain_subsidiary：aggregate_individual_sum → recalculate_trial →
  reconcile，断言 B1 恒等式 + provenance 自洽（Phase 0→0 真实 DB 链路）。
- test_cascade_refresh_awaits_async_report（回归守卫）：refresh_all 后 report 步
  必须在 steps_completed 且不在 errors，且无 "coroutine was never awaited" 警告。
- test_branch_consolidation_skips_elimination：母分汇总 consol_amount == individual_sum。
- test_approved_vs_draft_elimination：仅 approved 抵销影响 consol_elimination。

real-DB 测试范式：SQLite in-memory + JSONB/ARRAY 兼容 shim（先于模型导入），
PG-only SQL 路径在 service 内已有 sqlite dialect 兜底。
"""

from __future__ import annotations

import uuid
import warnings
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# SQLite 兼容 JSONB + ARRAY（必须先于任何模型导入，否则 create_all 编译报错）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"  # type: ignore[attr-defined]

from app.models.base import Base  # noqa: E402

# 注册全部模型子模块，确保 create_all 建出 FK 依赖的所有表
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.consolidation_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401

from app.models.audit_platform_models import AccountCategory, TrialBalance  # noqa: E402
from app.models.base import UserRole  # noqa: E402
from app.models.consolidation_models import (  # noqa: E402
    ConsolTrial,
    EliminationEntry,
    EliminationEntryType,
    ReviewStatusEnum,
)
from app.models.core import Project, User  # noqa: E402

from app.services.consol_individual_sum_service import aggregate_individual_sum  # noqa: E402
from app.services.consol_reconciliation_service import (  # noqa: E402
    reconcile_worksheet_vs_trial,
)
from app.services.consol_trial_service import recalculate_trial  # noqa: E402

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
YEAR = 2025


# ---------------------------------------------------------------------------
# Fixture：每个测试独立的内存数据库会话
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立的 SQLite 内存数据库（建全量表）。"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session

    await engine.dispose()


# ---------------------------------------------------------------------------
# 合成集团造数据 helper
# ---------------------------------------------------------------------------


def _tb_row(project_id: uuid.UUID, company_code: str, code: str, name: str,
            category: AccountCategory, amount: str) -> TrialBalance:
    """构造一行子公司审定试算（audited_amount 即 B1 取数源）。"""
    return TrialBalance(
        id=uuid.uuid4(),
        project_id=project_id,
        year=YEAR,
        company_code=company_code,
        standard_account_code=code,
        account_name=name,
        account_category=category,
        audited_amount=Decimal(amount),
        is_deleted=False,
    )


async def _seed_group(
    session: AsyncSession,
    *,
    consolidation_type: str = "subsidiary",
    n_children: int = 2,
) -> tuple[Project, list[Project]]:
    """造 1 母 N 子合成集团：母 report_scope=consolidated，子挂 parent_project_id，
    每个子公司带几行 trial_balance（audited_amount），commit 落库。

    返回 (parent, [children])。各子公司科目刻意部分重叠（验证跨公司加总）+
    部分独有（验证不丢科目）+ 含负数（累计折旧）。
    """
    user = User(
        id=uuid.uuid4(),
        username=f"uat_{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@uat.local",
        hashed_password="x",
        role=UserRole.admin,
    )
    session.add(user)

    parent = Project(
        id=uuid.uuid4(),
        name="合成集团母公司",
        client_name="【集成测试】合成集团母公司",
        company_code="GRP_PARENT",
        ultimate_company_code="GRP_PARENT",
        report_scope="consolidated",
        consolidation_type=consolidation_type,
        consol_level=2,
    )
    session.add(parent)

    children: list[Project] = []
    # 子公司科目矩阵：(code, name, category) → {child_index: amount}
    # 1001 货币资金（两家都有）/ 1601 累计折旧（负数，两家都有）/
    # 6001 营业收入（仅子A）/ 2001 应付账款（仅子B）
    child_specs = [
        # 子 A
        [
            ("1001", "货币资金", AccountCategory.asset, "1000000.50"),
            ("1601", "累计折旧", AccountCategory.asset, "-200000.00"),
            ("6001", "营业收入", AccountCategory.revenue, "300000.00"),
        ],
        # 子 B
        [
            ("1001", "货币资金", AccountCategory.asset, "250000.00"),
            ("1601", "累计折旧", AccountCategory.asset, "-80000.00"),
            ("2001", "应付账款", AccountCategory.liability, "150000.00"),
        ],
    ]
    for i in range(n_children):
        code_letter = chr(ord("A") + i)
        child = Project(
            id=uuid.uuid4(),
            name=f"子公司{code_letter}",
            client_name=f"【集成测试】子公司{code_letter}",
            company_code=f"GRP_SUB_{code_letter}",
            parent_company_code="GRP_PARENT",
            ultimate_company_code="GRP_PARENT",
            parent_project_id=parent.id,
            report_scope="standalone",
            consol_level=1,
        )
        session.add(child)
        children.append(child)
        spec = child_specs[i % len(child_specs)]
        for code, name, category, amount in spec:
            session.add(_tb_row(child.id, child.company_code, code, name, category, amount))

    await session.commit()
    return parent, children


# ---------------------------------------------------------------------------
# 测试 2：Phase 0→0 真实 DB 全链路（aggregate → trial → reconcile）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_chain_subsidiary(db_session: AsyncSession):
    """母子合并真实链路：aggregate_individual_sum → recalculate_trial → reconcile。

    断言：
    - consol_trial 行实际落库（真实 ORM 写入，非 mock）。
    - B1 恒等式：consol_amount == individual_sum + consol_adjustment + consol_elimination。
    - provenance 自洽：consolidation_breakdown.by_company 金额合计 == individual_sum。
    - 跨公司加总数值正确（1001 两家相加 / 1601 负数相加 / 独有科目不丢）。
    - reconcile 不抛异常（B2 观测手段）。
    """
    parent, children = await _seed_group(db_session, consolidation_type="subsidiary")

    # ① B1 汇总
    agg = await aggregate_individual_sum(db_session, parent.id, YEAR)
    assert agg.companies_traversed == 2
    assert agg.accounts_aggregated == 4  # 1001 / 1601 / 6001 / 2001

    # ② 重算 trial（内部会再调 aggregate，再叠加抵销；只 flush）
    trials = await recalculate_trial(db_session, parent.id, YEAR)
    await db_session.commit()
    assert len(trials) == 4

    by_code = {t.standard_account_code: t for t in trials}

    # 跨公司加总数值
    assert by_code["1001"].individual_sum == Decimal("1250000.50")  # 1000000.50 + 250000.00
    assert by_code["1601"].individual_sum == Decimal("-280000.00")  # -200000 + -80000
    assert by_code["6001"].individual_sum == Decimal("300000.00")   # 仅子 A
    assert by_code["2001"].individual_sum == Decimal("150000.00")   # 仅子 B

    # B1 恒等式 + provenance 自洽
    for t in trials:
        assert t.consol_amount == t.individual_sum + t.consol_adjustment + t.consol_elimination, (
            f"B1 恒等式破坏：{t.standard_account_code}"
        )
        assert t.is_stale is False  # 重算后清除陈旧标记
        breakdown = t.consolidation_breakdown
        assert breakdown is not None and "by_company" in breakdown
        recomputed = sum(
            (Decimal(row["amount"]) for row in breakdown["by_company"]), Decimal("0")
        )
        assert recomputed == t.individual_sum, (
            f"provenance 不自洽：{t.standard_account_code} "
            f"by_company 合计={recomputed} ≠ individual_sum={t.individual_sum}"
        )

    # 1001 两家公司都贡献，provenance 应有 2 行
    assert len(by_code["1001"].consolidation_breakdown["by_company"]) == 2
    # 2001 仅子 B 贡献，provenance 应有 1 行
    assert len(by_code["2001"].consolidation_breakdown["by_company"]) == 1

    # ③ B2 对账（观测手段，永不抛）。worksheet 未跑，根节点 ws_map 为空，
    #    但 reconcile 必须正常返回（不阻断）。
    recon = await reconcile_worksheet_vs_trial(db_session, parent.id, YEAR)
    assert recon is not None
    assert isinstance(recon.diffs, list)


# ---------------------------------------------------------------------------
# 测试 3：cascade refresh 必须 await async 报表（回归守卫）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cascade_refresh_awaits_async_report(db_session: AsyncSession):
    """回归守卫：refresh_all 编排链中 report 步必须 await generate_consol_reports_sync。

    若 report 步被当同步调用（漏 await），协程不会真正执行：要么 report 步进 errors
    （TypeError），要么 Python 抛 "coroutine 'xxx' was never awaited" RuntimeWarning。
    本测试同时断言：
      - report 在 steps_completed，不在 errors；
      - 整个 refresh_all 过程不产生 "coroutine was never awaited" 警告。
    这正是 Phase 1 改 async / Phase 2 仍 sync 调用会触发的回归。
    """
    from app.services.consol_cascade_refresh_service import refresh_all, STEP_REPORT

    parent, children = await _seed_group(db_session, consolidation_type="subsidiary")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = await refresh_all(db_session, parent.id, YEAR)

    # 不应有"协程未被 await"警告
    never_awaited = [
        w for w in caught
        if "never awaited" in str(w.message) or "was never awaited" in str(w.message)
    ]
    assert not never_awaited, (
        f"检测到未 await 的协程警告（report 步签名漂移回归）：{[str(w.message) for w in never_awaited]}"
    )

    # report 步必须真实完成，且不在错误清单
    report_errors = [e for e in result.errors if e.get("step") == STEP_REPORT]
    assert not report_errors, f"report 步报错（应已 await async）：{report_errors}"
    assert STEP_REPORT in result.steps_completed, (
        f"report 步未完成。steps_completed={result.steps_completed} errors={result.errors}"
    )

    # 关键前置步骤也应完成（trial 是 report 的依赖）
    assert "trial" in result.steps_completed
    assert "worksheet" in result.steps_completed


# ---------------------------------------------------------------------------
# 测试 4：母分汇总（branch）跳过抵销
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_branch_consolidation_skips_elimination(db_session: AsyncSession):
    """母分汇总（consolidation_type="branch"）：直接加总，无抵销，
    consol_amount == individual_sum（走 recalculate_trial 的 branch 分支）。
    即使存在已审批抵销分录，branch 也不应消费它。
    """
    parent, children = await _seed_group(db_session, consolidation_type="branch")

    # 故意塞一条 approved 抵销，验证 branch 分支不会消费它
    db_session.add(EliminationEntry(
        id=uuid.uuid4(),
        project_id=parent.id,
        year=YEAR,
        entry_no="ELIM-BRANCH-01",
        entry_type=EliminationEntryType.internal_trade,
        account_code="1001",
        debit_amount=Decimal("0"),
        credit_amount=Decimal("99999.00"),
        lines=[{"account_code": "1001", "debit_amount": "0", "credit_amount": "99999.00"}],
        entry_group_id=uuid.uuid4(),
        review_status=ReviewStatusEnum.approved,
        is_deleted=False,
    ))
    await db_session.commit()

    trials = await recalculate_trial(db_session, parent.id, YEAR)
    await db_session.commit()

    for t in trials:
        assert t.consol_elimination == Decimal("0"), (
            f"branch 不应有抵销：{t.standard_account_code} elim={t.consol_elimination}"
        )
        assert t.consol_adjustment == Decimal("0")
        assert t.consol_amount == t.individual_sum, (
            f"branch 合并数应等于汇总数：{t.standard_account_code}"
        )


# ---------------------------------------------------------------------------
# 测试 5：仅 approved 抵销影响 consol_elimination（draft 不消费）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approved_vs_draft_elimination(db_session: AsyncSession):
    """母子合并：draft 抵销不消费，仅 approved 影响 consol_elimination。

    验证 recalculate_trial 的 APPROVED-only 过滤 + ReviewStatusEnum 小写成员修复。
    """
    parent, children = await _seed_group(db_session, consolidation_type="subsidiary")

    # 一条 draft（不应生效）+ 一条 approved（应生效），都打到 1001
    db_session.add(EliminationEntry(
        id=uuid.uuid4(),
        project_id=parent.id,
        year=YEAR,
        entry_no="ELIM-DRAFT-01",
        entry_type=EliminationEntryType.internal_ar_ap,
        account_code="1001",
        debit_amount=Decimal("0"),
        credit_amount=Decimal("777777.00"),
        lines=[{"account_code": "1001", "debit_amount": "0", "credit_amount": "777777.00"}],
        entry_group_id=uuid.uuid4(),
        review_status=ReviewStatusEnum.draft,
        is_deleted=False,
    ))
    db_session.add(EliminationEntry(
        id=uuid.uuid4(),
        project_id=parent.id,
        year=YEAR,
        entry_no="ELIM-APPR-01",
        entry_type=EliminationEntryType.internal_ar_ap,
        account_code="1001",
        debit_amount=Decimal("0"),
        credit_amount=Decimal("50000.00"),
        lines=[{"account_code": "1001", "debit_amount": "0", "credit_amount": "50000.00"}],
        entry_group_id=uuid.uuid4(),
        review_status=ReviewStatusEnum.approved,
        is_deleted=False,
    ))
    await db_session.commit()

    trials = await recalculate_trial(db_session, parent.id, YEAR)
    await db_session.commit()

    by_code = {t.standard_account_code: t for t in trials}
    t1001 = by_code["1001"]

    # 仅 approved 的 credit 50000 生效：elim = debit(0) - credit(50000) = -50000
    assert t1001.consol_elimination == Decimal("-50000.00"), (
        f"应只消费 approved 抵销，得到 {t1001.consol_elimination}（draft 777777 不应生效）"
    )
    # 恒等式仍成立
    assert t1001.consol_amount == t1001.individual_sum + t1001.consol_adjustment + t1001.consol_elimination
    assert t1001.consol_amount == Decimal("1250000.50") + Decimal("-50000.00")

    # 未涉及抵销的科目 elim 为 0
    assert by_code["2001"].consol_elimination == Decimal("0")
