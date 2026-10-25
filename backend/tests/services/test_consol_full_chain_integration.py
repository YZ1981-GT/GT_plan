"""合并模块全链路集成测试（封板交付物 ①；spec consol-tree-three-code-autobuild 任务 7.6 按三码模型改写）

目标：用 **真实 SQLite DB + 真实 ORM 行 + 真实 service** 跑通整条合并管线，
捕捉单阶段 mock 测试抓不到的「跨阶段签名漂移」回归。这是会同时咬到以下两次
merge 回归的测试：
  1. Phase 1 把 generate_consol_reports_sync 改成 async，而 Phase 2 仍 sync 调用；
  2. Phase 1 删了 _execute_formula，令 Phase 2 报表公式失效。

覆盖：
- test_full_chain_subsidiary：aggregate_individual_sum → recalculate_trial → recalc_full → reconcile，
  断言合并恒等式 + 溯源自洽 + P8（差额表根合并数 == 试算合并数，对账 0 差异）。
- test_cascade_refresh_awaits_async_report（回归守卫）：refresh_all 后 report 步
  必须在 steps_completed 且不在 errors，且无 "coroutine was never awaited" 警告。
- test_mixed_group_branch_and_subsidiary：子公司与分公司并存 —— 合并差额与母分差额两处分录各自计入、
  孤儿分录两条路径都不计入、P10 科目方向归一、只在分录里出现的科目建行、P8 恒等。
- test_approved_vs_draft_elimination：仅 approved 抵销影响 consol_elimination。

有意的口径变更（旧断言不作为正确性依据，design §十二）：
- 企业树按三码推导：测试项目必须带审计年度、下级项目填上级代码；不再写 parent_project_id；
- 个别数汇总取全部数据叶子，**母公司本体计入**（旧版只取子公司叶子，F5）；
- 抵销金额按科目方向归一（贷方性质科目「借减贷」取反，F7）；
- 删除「consolidation_type=branch 时整体跳过抵销」—— 合并方式由下级关系推导，
  母分差额分录照常计入（旧测试 test_branch_consolidation_skips_elimination 改写为并存用例）。

real-DB 测试范式：SQLite in-memory + JSONB/ARRAY 兼容 shim（先于模型导入），
PG-only SQL 路径在 service 内已有 sqlite dialect 兜底。
"""

from __future__ import annotations

import uuid
import warnings
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
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
    ConsolWorksheet,
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
from app.services.consol_worksheet_engine import recalc_full  # noqa: E402

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


def _tb_row(project_id: uuid.UUID, code: str, name: str, category: AccountCategory, amount: str) -> TrialBalance:
    """构造一行单户审定试算（audited_amount 即个别数取数源）。"""
    return TrialBalance(
        id=uuid.uuid4(),
        project_id=project_id,
        year=YEAR,
        company_code="001",
        standard_account_code=code,
        account_name=name,
        account_category=category,
        audited_amount=Decimal(amount),
        is_deleted=False,
    )


def _project(code: str, name: str, scope: str, *, parent: str | None = None, relation: str | None = None) -> Project:
    return Project(
        id=uuid.uuid4(),
        name=f"{name}_{YEAR}",
        client_name=f"【集成测试】{name}",
        company_code=code,
        parent_company_code=parent,
        ultimate_company_code="GRP_PARENT",
        relation_to_parent=relation,
        report_scope=scope,
        audit_year=YEAR,
        consol_level=2 if scope == "consolidated" else 1,
    )


# 子公司科目矩阵：1001 货币资金（两家都有）/ 1602 累计折旧（贷方性质备抵，两家都有）/
# 6001 营业收入（仅子A）/ 2202 应付账款（仅子B）
_CHILD_SPECS = [
    [
        ("1001", "货币资金", AccountCategory.asset, "1000000.50"),
        ("1122", "应收账款", AccountCategory.asset, "30000.00"),
        ("1602", "累计折旧", AccountCategory.asset, "200000.00"),
        ("6001", "营业收入", AccountCategory.revenue, "300000.00"),
    ],
    [
        ("1001", "货币资金", AccountCategory.asset, "250000.00"),
        ("1602", "累计折旧", AccountCategory.asset, "80000.00"),
        ("2202", "应付账款", AccountCategory.liability, "150000.00"),
    ],
]
# 母公司本体（单户项目）
_PARENT_SPEC = [
    ("1001", "货币资金", AccountCategory.asset, "40000.00"),
    ("2202", "应付账款", AccountCategory.liability, "5000.00"),
]


async def _seed_group(session: AsyncSession, *, n_children: int = 2) -> tuple[Project, list[Project]]:
    """造 1 母 N 子合成集团：母公司合并 + 单户两个项目，子公司上级代码填母公司代码（三码建树）。

    返回 (合并项目, [子公司单户项目])。
    """
    session.add(User(
        id=uuid.uuid4(),
        username=f"uat_{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@uat.local",
        hashed_password="x",
        role=UserRole.admin,
    ))
    parent = _project("GRP_PARENT", "合成集团母公司", "consolidated")
    parent_standalone = _project("GRP_PARENT", "合成集团母公司", "standalone")
    session.add_all([parent, parent_standalone])
    for code, name, category, amount in _PARENT_SPEC:
        session.add(_tb_row(parent_standalone.id, code, name, category, amount))

    children: list[Project] = []
    for i in range(n_children):
        letter = chr(ord("A") + i)
        child = _project(f"GRP_SUB_{letter}", f"子公司{letter}", "standalone",
                         parent="GRP_PARENT", relation="subsidiary")
        session.add(child)
        children.append(child)
        for code, name, category, amount in _CHILD_SPECS[i % len(_CHILD_SPECS)]:
            session.add(_tb_row(child.id, code, name, category, amount))

    await session.commit()
    return parent, children


def _entry(project_id, no, entry_type, lines, *, status=ReviewStatusEnum.approved, branch=None):
    return EliminationEntry(
        id=uuid.uuid4(),
        project_id=project_id,
        year=YEAR,
        entry_no=no,
        entry_type=entry_type,
        account_code=lines[0][0],
        debit_amount=sum((Decimal(ln[2]) for ln in lines), Decimal("0")),
        credit_amount=sum((Decimal(ln[3]) for ln in lines), Decimal("0")),
        lines=[
            {"account_code": code, "account_name": name, "debit_amount": dr, "credit_amount": cr}
            for code, name, dr, cr in lines
        ],
        entry_group_id=uuid.uuid4(),
        branch_entity_code=branch,
        review_status=status,
        is_deleted=False,
    )


async def _root_worksheet(session: AsyncSession, project_id: uuid.UUID, root_key: str) -> dict[str, Decimal]:
    rows = (await session.execute(
        sa.select(ConsolWorksheet.account_code, ConsolWorksheet.consolidated_amount).where(
            ConsolWorksheet.project_id == project_id,
            ConsolWorksheet.node_company_code == root_key,
            ConsolWorksheet.is_deleted == sa.false(),
        )
    )).all()
    return {code: Decimal(str(amount)) for code, amount in rows}


# ---------------------------------------------------------------------------
# 测试 1：真实 DB 全链路（aggregate → trial → worksheet → reconcile）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_chain_subsidiary(db_session: AsyncSession):
    """母子合并真实链路：aggregate_individual_sum → recalculate_trial → recalc_full → reconcile。

    断言：
    - consol_trial 行实际落库（真实 ORM 写入，非 mock）；
    - 个别数 = 全部数据叶子（母公司本体 + 两家子公司，口径变更：旧版不含母公司本体）；
    - 合并恒等式 consol_amount == individual_sum + consol_adjustment + consol_elimination；
    - 溯源自洽：by_company 合计 == individual_sum，且每行标注节点（node_key / role / entity_kind）；
    - P8：差额表根合并数与试算合并数逐科目相等，对账 0 差异。
    """
    parent, children = await _seed_group(db_session)
    db_session.add(_entry(parent.id, "IA-2025-001", EliminationEntryType.internal_ar_ap, [
        ("2202", "应付账款", "20000.00", "0"),
        ("1122", "应收账款", "0", "20000.00"),
    ]))
    await db_session.commit()

    # ① B1 汇总：3 个数据叶子（母公司、子A、子B）
    agg = await aggregate_individual_sum(db_session, parent.id, YEAR)
    assert agg.companies_traversed == 3
    assert agg.accounts_aggregated == 5  # 1001 / 1122 / 1602 / 6001 / 2202

    # ② 重算 trial（只 flush）
    trials = await recalculate_trial(db_session, parent.id, YEAR)
    await db_session.commit()
    assert len(trials) == 5
    by_code = {t.standard_account_code: t for t in trials}

    assert by_code["1001"].individual_sum == Decimal("1290000.50")  # 40000 + 1000000.50 + 250000
    assert by_code["1602"].individual_sum == Decimal("280000.00")   # 备抵科目正数口径相加
    assert by_code["6001"].individual_sum == Decimal("300000.00")   # 仅子 A
    assert by_code["2202"].individual_sum == Decimal("155000.00")   # 母公司 5000 + 子 B 150000
    # 应付账款贷方性质：借 20000 ⇒ −20000；应收账款借方性质：贷 20000 ⇒ −20000
    assert by_code["2202"].consol_elimination == Decimal("-20000.00")
    assert by_code["1122"].consol_elimination == Decimal("-20000.00")
    assert by_code["1122"].consol_amount == Decimal("10000.00")

    for t in trials:
        assert t.consol_amount == t.individual_sum + t.consol_adjustment + t.consol_elimination, (
            f"合并恒等式破坏：{t.standard_account_code}"
        )
        assert t.is_stale is False
        breakdown = t.consolidation_breakdown
        assert breakdown is not None and "by_company" in breakdown
        recomputed = sum((Decimal(row["amount"]) for row in breakdown["by_company"]), Decimal("0"))
        assert recomputed == t.individual_sum, f"溯源不自洽：{t.standard_account_code}"

    rows_1001 = by_code["1001"].consolidation_breakdown["by_company"]
    assert [(r["node_key"], r["role"], r["entity_kind"]) for r in rows_1001] == [
        ("GRP_PARENT:parent", "parent", "parent"),
        ("GRP_SUB_A:subsidiary", "subsidiary", "subsidiary"),
        ("GRP_SUB_B:subsidiary", "subsidiary", "subsidiary"),
    ]
    assert len(by_code["2202"].consolidation_breakdown["by_company"]) == 2

    # ③ 差额表 + ④ 对账：P8 逐科目相等
    await recalc_full(db_session, parent.id, YEAR)
    root = await _root_worksheet(db_session, parent.id, "GRP_PARENT:consol")
    assert root == {code: t.consol_amount for code, t in by_code.items()}
    recon = await reconcile_worksheet_vs_trial(db_session, parent.id, YEAR)
    assert recon.is_reconciled is True and recon.diffs == [] and recon.max_abs_diff == Decimal("0")


@pytest.mark.asyncio
async def test_recalculate_trial_zeroes_vanished_accounts(db_session: AsyncSession):
    """需求 5.6：科目从数据叶子与分录里都消失后，重算把该试算行清零（不残留旧数）。"""
    parent, children = await _seed_group(db_session)
    await recalculate_trial(db_session, parent.id, YEAR)
    await db_session.commit()

    tb = (await db_session.execute(
        sa.select(TrialBalance).where(
            TrialBalance.project_id == children[0].id, TrialBalance.standard_account_code == "6001")
    )).scalar_one()
    tb.is_deleted = True
    await db_session.commit()

    by_code = {t.standard_account_code: t for t in await recalculate_trial(db_session, parent.id, YEAR)}
    gone = by_code["6001"]
    assert (gone.individual_sum, gone.consol_amount) == (Decimal("0"), Decimal("0"))
    assert gone.consolidation_breakdown["by_company"] == []


# ---------------------------------------------------------------------------
# 测试 2：cascade refresh 必须 await async 报表（回归守卫）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cascade_refresh_awaits_async_report(db_session: AsyncSession):
    """回归守卫：refresh_all 编排链中 report 步必须 await generate_consol_reports_sync。

    若 report 步被当同步调用（漏 await），协程不会真正执行：要么 report 步进 errors
    （TypeError），要么 Python 抛 "coroutine 'xxx' was never awaited" RuntimeWarning。
    本测试同时断言：
      - report 在 steps_completed，不在 errors；
      - 整个 refresh_all 过程不产生 "coroutine was never awaited" 警告；
      - 对账步两条路径同源、0 差异（P8）。
    """
    from app.services.consol_cascade_refresh_service import refresh_all, STEP_REPORT

    parent, children = await _seed_group(db_session)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = await refresh_all(db_session, parent.id, YEAR)

    never_awaited = [
        w for w in caught
        if "never awaited" in str(w.message) or "was never awaited" in str(w.message)
    ]
    assert not never_awaited, (
        f"检测到未 await 的协程警告（report 步签名漂移回归）：{[str(w.message) for w in never_awaited]}"
    )

    report_errors = [e for e in result.errors if e.get("step") == STEP_REPORT]
    assert not report_errors, f"report 步报错（应已 await async）：{report_errors}"
    assert STEP_REPORT in result.steps_completed, (
        f"report 步未完成。steps_completed={result.steps_completed} errors={result.errors}"
    )
    assert "trial" in result.steps_completed
    assert "worksheet" in result.steps_completed
    # 三节点模型：合并、合并差额、母公司 + 两家子公司
    assert result.nodes_refreshed == 5
    assert result.reconciliation is not None and result.reconciliation.is_reconciled is True


# ---------------------------------------------------------------------------
# 测试 3：子公司与分公司并存（需求 4.2 / 5.x / 6.x）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mixed_group_branch_and_subsidiary(db_session: AsyncSession):
    """母公司同时有子公司与分公司：合并差额与母分差额两处分录各自计入（口径变更：旧版
    ``consolidation_type=branch`` 时整体跳过抵销，现由关系推导、两类差额节点并存）。

    - P10：借方性质科目（应收账款）借 100 ⇒ 合并数 +100；贷方性质科目（应付账款）贷 100 ⇒ +100；
    - 「其他调整」进调整列；只在分录里出现的科目（其他应付款 2241）在合并试算建行；
    - 归属到不存在的母分差额节点的分录是孤儿：两条路径都不计入，重算结果列出；
    - P8：差额表根合并数 == 试算合并数，对账 0 差异。
    """
    parent, children = await _seed_group(db_session, n_children=1)
    branch = _project("GRP_BR_1", "合成集团母公司上海分公司", "standalone", parent="GRP_PARENT", relation="branch")
    db_session.add(branch)
    db_session.add(_tb_row(branch.id, "1001", "货币资金", AccountCategory.asset, "7000.00"))
    db_session.add(_tb_row(branch.id, "2202", "应付账款", AccountCategory.liability, "3000.00"))
    db_session.add_all([
        # 合并差额（branch_entity_code 为空）
        _entry(parent.id, "IA-2025-001", EliminationEntryType.internal_ar_ap, [
            ("1122", "应收账款", "100.00", "0"), ("1001", "货币资金", "0", "100.00"),
        ]),
        # 母分差额（归属母公司自己的母分差额节点）：贷 应付账款 100 ⇒ +100
        _entry(parent.id, "IA-2025-002", EliminationEntryType.internal_ar_ap, [
            ("1001", "货币资金", "100.00", "0"), ("2202", "应付账款", "0", "100.00"),
        ], branch="GRP_PARENT"),
        # 其他调整：只在分录里出现的科目 2241
        _entry(parent.id, "OT-2025-001", EliminationEntryType.other, [
            ("1001", "货币资金", "30.00", "0"), ("2241", "其他应付款", "0", "30.00"),
        ]),
        # 孤儿：子公司A 没有分公司 ⇒ 没有母分差额节点
        _entry(parent.id, "IA-2025-003", EliminationEntryType.internal_ar_ap, [
            ("1001", "货币资金", "999.00", "0"), ("1122", "应收账款", "0", "999.00"),
        ], branch="GRP_SUB_A"),
    ])
    await db_session.commit()

    ws = await recalc_full(db_session, parent.id, YEAR)
    assert [o["entry_no"] for o in ws["orphan_entries"]] == ["IA-2025-003"]

    by_code = {t.standard_account_code: t for t in await recalculate_trial(db_session, parent.id, YEAR)}
    await db_session.commit()

    # 个别数：母公司本部 40000 + 分公司 7000 + 子A 1000000.50
    assert by_code["1001"].individual_sum == Decimal("1047000.50")
    # 1001：合并差额 贷 100 ⇒ −100；母分差额 借 100 ⇒ +100；其他调整 借 30 ⇒ 调整 +30；孤儿不计
    assert by_code["1001"].consol_elimination == Decimal("0.00")
    assert by_code["1001"].consol_adjustment == Decimal("30.00")
    assert by_code["1122"].consol_elimination == Decimal("100.00")   # P10 借方性质借 100 ⇒ +100
    assert by_code["2202"].consol_elimination == Decimal("100.00")   # P10 贷方性质贷 100 ⇒ +100
    assert by_code["2241"].individual_sum == Decimal("0")
    assert by_code["2241"].consol_adjustment == Decimal("30.00")
    assert by_code["2241"].account_name == "其他应付款"

    # 溯源：母公司有分公司 ⇒ 本部 + 分公司两行（均属母公司汇总），子公司一行
    rows = by_code["1001"].consolidation_breakdown["by_company"]
    assert [(r["node_key"], r["entity_kind"]) for r in rows] == [
        ("GRP_PARENT:hq", "parent"), ("GRP_BR_1:branch", "branch"), ("GRP_SUB_A:subsidiary", "subsidiary"),
    ]

    # 母分差额节点金额在差额表里单列，母公司汇总节点 = 母分差额 + 本部 + 分公司
    branch_elim = await _root_worksheet(db_session, parent.id, "GRP_PARENT:branch_elim")
    assert branch_elim["2202"] == Decimal("100.00") and branch_elim["1001"] == Decimal("100.00")
    parent_agg = await _root_worksheet(db_session, parent.id, "GRP_PARENT:parent")
    assert parent_agg["1001"] == Decimal("47100.00")

    root = await _root_worksheet(db_session, parent.id, "GRP_PARENT:consol")
    assert root == {code: t.consol_amount for code, t in by_code.items()}
    recon = await reconcile_worksheet_vs_trial(db_session, parent.id, YEAR)
    assert recon.is_reconciled is True and recon.diffs == []


# ---------------------------------------------------------------------------
# 测试 4：仅 approved 抵销影响 consol_elimination（draft 不消费）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approved_vs_draft_elimination(db_session: AsyncSession):
    """母子合并：draft 抵销不消费，仅 approved 影响 consol_elimination。

    口径变更：货币资金是借方性质科目，贷 50000 ⇒ −50000（与旧版「借减贷」同号）；
    个别数含母公司本体 40000。
    """
    parent, children = await _seed_group(db_session)
    db_session.add_all([
        _entry(parent.id, "ELIM-DRAFT-01", EliminationEntryType.internal_ar_ap, [
            ("1001", "货币资金", "0", "777777.00"), ("2202", "应付账款", "777777.00", "0"),
        ], status=ReviewStatusEnum.draft),
        _entry(parent.id, "ELIM-APPR-01", EliminationEntryType.internal_ar_ap, [
            ("1001", "货币资金", "0", "50000.00"), ("2202", "应付账款", "50000.00", "0"),
        ]),
    ])
    await db_session.commit()

    trials = await recalculate_trial(db_session, parent.id, YEAR)
    await db_session.commit()
    by_code = {t.standard_account_code: t for t in trials}
    t1001 = by_code["1001"]

    assert t1001.consol_elimination == Decimal("-50000.00"), (
        f"应只消费 approved 抵销，得到 {t1001.consol_elimination}（draft 777777 不应生效）"
    )
    assert t1001.consol_amount == t1001.individual_sum + t1001.consol_adjustment + t1001.consol_elimination
    assert t1001.consol_amount == Decimal("1290000.50") + Decimal("-50000.00")
    # 应付账款贷方性质：借 50000 ⇒ −50000
    assert by_code["2202"].consol_elimination == Decimal("-50000.00")
    # 未涉及抵销的科目 elim 为 0
    assert by_code["6001"].consol_elimination == Decimal("0")
