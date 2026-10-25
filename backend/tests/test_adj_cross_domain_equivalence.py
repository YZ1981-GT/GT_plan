"""P5：同一调整额公式在三个域求值等值。

spec: tb-adjustment-column-formula-closure Phase 1 Task 1.10（需求 3.2）

## 为什么需要这条守卫

Phase 0 的起因就是「三套取数口径各自注释声称同口径而实际三样」。Phase 1 把
`ADJ()` 收进 L1 单内核后，三个域（试算平衡表 / 报表 / 审定表回写）都经
`adj_net_batch` 填 `FormulaContext.adj_data`。本文件证明这个收敛**真的生效**：
同一份落库数据、同一条公式，三个域给出同一个数。

## 判据设计

🔴 **用真 DB 落一份数据，让三个域各自走自己的完整取数链路**，而不是
造三份 ctx 再比对 —— 后者只能证明"同样的输入给同样的输出"（L1 纯函数的
平凡属性），证明不了三个 L2 真的取到了同一份数。这是 memory 记录的
「mock/spy 只验接线不验语义」教训的直接应用。

覆盖 tasks 1.10 要求的**两种写法**：
- `ADJ(code,'aje_net')`  —— 实时汇总（本 spec 新增）
- `TB(code,'AJE调整')`   —— 持久化快照（既有）

两者在真实链路上**可以不等**（快照过期时），故分开断言：
- `ADJ()` 三域必须等值（都取实时）
- `TB(...,'AJE调整')` 只在试算平衡表与审定表回写两域有定义（报表域 tb_data 为空
  因 TB 已预替换），故对报表域不作此断言并在测试里说明

Validates: Requirements 3.2 · Property P5
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

_PID = uuid.UUID("dddddddd-0000-4000-8000-0000000005c1")
_UID = uuid.UUID("eeeeeeee-0000-4000-8000-0000000005c2")
_YEAR = 2098
_CO = "001"

# 收入类（贷方正常）—— 符号归一的关键样本
_REV = "6001"
_REV_NAME = "主营业务收入"
# 资产类（借方正常）—— 对照样本
_AR = "1122"
_AR_NAME = "应收账款"

#: 第一笔分录金额（origin=manual，**应被计入**）：借应收 / 贷收入
_CR_AMT = Decimal("10000")
#: 第二笔分录金额（origin=workpaper，**应被排除**）。
#: 取与 `_CR_AMT` 不同的值，这样漏过滤时差额可辨（若同值，某些错法会碰巧对上）。
_WP_AMT = Decimal("7000")


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        await _seed(s)
        yield s
    await engine.dispose()


async def _seed(db: AsyncSession) -> None:
    """落 trial_balance 两行 + 一笔 approved AJE（借应收 / 贷收入）。

    🔴 `trial_balance.aje_adjustment` 刻意留 **0**（模拟快照过期），
    这样 `ADJ()`（实时）与 `TB(...,'AJE调整')`（快照）的差异可被观测。
    """
    from app.models.audit_platform_models import (
        AccountCategory,
        Adjustment,
        AdjustmentEntry,
        AdjustmentType,
        TrialBalance,
    )
    # 🔴 不建 User/Project：三个取数域都不 JOIN 这两张表（实证 —— 去掉后测试仍通过）。
    # 建它们只会引入无关的 NOT NULL 约束（`users.role` 等），让 fixture 变脆。
    for code, name, cat in (
        (_AR, _AR_NAME, AccountCategory.asset),
        (_REV, _REV_NAME, AccountCategory.revenue),
    ):
        db.add(TrialBalance(
            project_id=_PID, year=_YEAR, company_code=_CO,
            standard_account_code=code, account_name=name, account_category=cat,
            unadjusted_amount=Decimal("100000"), audited_amount=Decimal("100000"),
            aje_adjustment=Decimal("0"),  # 🔴 快照刻意留 0
            rje_adjustment=Decimal("0"), opening_balance=Decimal("0"),
            is_deleted=False,
        ))

    adj_id, grp = uuid.uuid4(), uuid.uuid4()
    db.add(Adjustment(
        id=adj_id, project_id=_PID, year=_YEAR, company_code=_CO,
        adjustment_no="AJE-P5-001", adjustment_type=AdjustmentType.aje,
        account_code=_AR, account_name=_AR_NAME,  # 主表遗留冗余列（NOT NULL）
        debit_amount=_CR_AMT, credit_amount=Decimal("0"),
        entry_group_id=grp, review_status="approved", origin="manual",
        is_deleted=False, created_by=_UID,
    ))
    # 明细两行：借应收、贷收入（ADR-ADJ-001 科目列的权威源）
    db.add(AdjustmentEntry(
        id=uuid.uuid4(), adjustment_id=adj_id, entry_group_id=grp, line_no=1,
        standard_account_code=_AR, account_name=_AR_NAME,
        debit_amount=_CR_AMT, credit_amount=Decimal("0"), is_deleted=False,
    ))
    db.add(AdjustmentEntry(
        id=uuid.uuid4(), adjustment_id=adj_id, entry_group_id=grp, line_no=2,
        standard_account_code=_REV, account_name=_REV_NAME,
        debit_amount=Decimal("0"), credit_amount=_CR_AMT, is_deleted=False,
    ))

    # 🔴 第二笔：`origin="workpaper"` 的 approved 分录，**必须被三域一致排除**。
    #
    # 加这笔是变异检验抓出来的缺口：首版 fixture 只有 `origin="manual"`，
    # 于是"去掉 origin 过滤"这个变异**不打红**（分母为空，过滤生效与否无差异）。
    # 有了它，任何域漏掉 `exclude_origins={"workpaper"}` 都会让该域多算
    # `_WP_AMT`，等值断言立刻红。
    wp_id, wp_grp = uuid.uuid4(), uuid.uuid4()
    db.add(Adjustment(
        id=wp_id, project_id=_PID, year=_YEAR, company_code=_CO,
        adjustment_no="AJE-P5-WP", adjustment_type=AdjustmentType.aje,
        account_code=_AR, account_name=_AR_NAME,
        debit_amount=_WP_AMT, credit_amount=Decimal("0"),
        entry_group_id=wp_grp, review_status="approved",
        origin="workpaper",  # 变异靶：底稿来源，已由审定表 writeback 体现
        is_deleted=False, created_by=_UID,
    ))
    db.add(AdjustmentEntry(
        id=uuid.uuid4(), adjustment_id=wp_id, entry_group_id=wp_grp, line_no=1,
        standard_account_code=_AR, account_name=_AR_NAME,
        debit_amount=_WP_AMT, credit_amount=Decimal("0"), is_deleted=False,
    ))
    db.add(AdjustmentEntry(
        id=uuid.uuid4(), adjustment_id=wp_id, entry_group_id=wp_grp, line_no=2,
        standard_account_code=_REV, account_name=_REV_NAME,
        debit_amount=Decimal("0"), credit_amount=_WP_AMT, is_deleted=False,
    ))
    await db.flush()


# ─── 三域各自的完整取数链路 ─────────────────────────────────────────────────


async def _domain_adjudication(db: AsyncSession, formula: str) -> Decimal:
    """审定表回写域：`AdjudicationWritebackService.build_context`。"""
    from app.services.formula_engine import execute
    from app.services.formula_management.adjudication_writeback import (
        AdjudicationWritebackService,
    )

    ctx = await AdjudicationWritebackService(db).build_context(_PID, _YEAR)
    r = execute(formula, ctx)
    assert r.errors == [], f"审定表域求值报错：{r.errors}"
    return r.value


async def _domain_report(db: AsyncSession, formula: str) -> Decimal:
    """报表域：`ReportFormulaParser.execute`（内部经 `_get_adj_data`）。"""
    from app.services.report_engine import ReportFormulaParser

    parser = ReportFormulaParser(db, _PID, _YEAR)
    return await parser.execute(formula, {})


async def _domain_tb_summary(db: AsyncSession, formula: str) -> Decimal:
    """试算平衡表域：`tb_formula_context.build_tb_formula_data` + `adj_net_batch`。

    直接组装该域用的 ctx（与 `get_summary_with_adjustments` 内部同一条链路：
    同一个共享件 + 同一个 `adj_net_batch` 调用口径），避免为跑通整张报表
    去 seed report_config —— 那会把本测试变成报表配置测试。
    """
    from app.models.audit_platform_models import TrialBalance
    from app.services.adjustment_amount_source import (
        DEFAULT_INCLUDE_STATUSES,
        adj_net_batch,
    )
    from app.services.formula_engine import FormulaContext, execute
    from app.services.tb_formula_context import build_tb_formula_data

    adj_data = await adj_net_batch(
        db,
        project_id=_PID,
        year=_YEAR,
        account_codes={_AR, _REV},
        include_statuses=DEFAULT_INCLUDE_STATUSES,
        exclude_origins=frozenset({"workpaper"}),
    )

    def _adj(code: str, key: str) -> Decimal:
        return adj_data.get(code, {}).get(key, Decimal("0"))

    tb_data = await build_tb_formula_data(
        db,
        tb=TrialBalance.__table__,
        project_id=_PID,
        year=_YEAR,
        company_code=_CO,
        adj_lookup=_adj,
    )
    ctx = FormulaContext(tb_data=tb_data, adj_data=adj_data)
    r = execute(formula, ctx)
    assert r.errors == [], f"试算平衡表域求值报错：{r.errors}"
    return r.value


# ─── P5 断言 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [_AR, _REV])
@pytest.mark.parametrize("adj_type", ["aje_net", "AJE", "审计调整"])
async def test_p5_adj_equals_across_three_domains(db_session, code, adj_type):
    """🔴 P5 核心：`ADJ()` 在三个域等值。

    参数化覆盖两个科目方向（资产借方 / 收入贷方）× 三种第二参写法，
    确保等值性不依赖特定科目类别或特定字面量。
    """
    formula = f"ADJ('{code}','{adj_type}')"

    v_adjud = await _domain_adjudication(db_session, formula)
    v_report = await _domain_report(db_session, formula)
    v_tb = await _domain_tb_summary(db_session, formula)

    assert v_adjud == v_report == v_tb, (
        f"{formula} 三域不等值：审定表={v_adjud} 报表={v_report} 试算表={v_tb}"
    )


@pytest.mark.asyncio
async def test_p5_denominator_is_non_zero(db_session):
    """🔴 反向自检：等值断言的分母必须非零，否则上面是「三个 0 相等」的空转。

    这是「结构性零须配变异证明」的应用：如果 fixture 的分录没落进 ADJ()，
    三域会同时得 0 而 P5 照样通过。
    """
    v = await _domain_adjudication(db_session, f"ADJ('{_AR}','aje_net')")
    assert v != Decimal("0"), (
        "ADJ() 取到 0 ⇒ P5 的等值断言退化成「三个 0 相等」，证明不了收敛"
    )


@pytest.mark.asyncio
async def test_p5_sign_normalization_is_consistent_across_domains(db_session):
    """借方类与贷方类的**符号**在三域一致。

    一笔「借应收 / 贷收入」各 10000：
    - 应收（资产，借方正常）→ 借方增加 ⇒ 归一后为 **正**
    - 收入（贷方正常）→ 贷方增加 ⇒ 归一后也为 **正**

    这正是 Phase 0 修掉的 B4：用未归一的 `dr - cr` 会让收入类得 **-10000**。
    若某个域漏了归一，本测试会在该域打红。
    """
    for domain_fn, name in (
        (_domain_adjudication, "审定表"),
        (_domain_report, "报表"),
        (_domain_tb_summary, "试算平衡表"),
    ):
        v_ar = await domain_fn(db_session, f"ADJ('{_AR}','aje_net')")
        v_rev = await domain_fn(db_session, f"ADJ('{_REV}','aje_net')")
        assert v_ar > 0, f"{name}域：资产类借方调整应为正，实得 {v_ar}"
        assert v_rev > 0, (
            f"{name}域：收入类贷方调整归一后应为正，实得 {v_rev} —— "
            f"负值说明该域用了未归一的 dr-cr（B4 缺陷形态）"
        )


@pytest.mark.asyncio
async def test_p5_snapshot_vs_realtime_differs_in_both_tb_domains(db_session):
    """`TB(code,'AJE调整')`（快照）与 `ADJ()`（实时）在两个有 tb_data 的域都可区分。

    报表域不在此列：它的 `tb_data` 为空（TB/SUM_TB 已在 L2 预替换为数值），
    `TB(...)` 在 L1 侧取不到数是**设计如此**，不是缺陷。

    fixture 的 `aje_adjustment` 留 0 而实时汇总非 0 ⇒ 两者必须不等。
    相等则说明有人把两个口径「对齐」了，需求 3.3 的过期信号将永远观测不到。
    """
    snap = await _domain_adjudication(db_session, f"TB('{_AR}','AJE调整')")
    live = await _domain_adjudication(db_session, f"ADJ('{_AR}','aje_net')")
    assert snap == Decimal("0"), f"审定表域快照应为 0（fixture 如此），实得 {snap}"
    assert live != snap, "审定表域：实时值与快照相等 ⇒ 两口径被对齐"

    # 🔴 试算平衡表域的 tb_data["AJE调整"] 由 `adj_lookup` 注入实时值
    # （见 `tb_formula_context` 的来源表），故这里两者**相等**是正确的 ——
    # 该域刻意不读 trial_balance 的持久化列（Phase 0 的 B3 修复）。
    #
    # 🔴 用 **_REV（贷方正常类）** 而非 _AR：借方类的 `aje_dr` 与 `aje_net`
    # 数值相同，用它断言无法区分「取归一净额」与「取原始借方」。
    # 变异检验实证：把 `adj_lookup` 的 `_net` 换成 `_dr` 后，_AR 版本**不打红**，
    # _REV 版本立刻红（收入类 `aje_dr`=0 而 `aje_net`=10000）。
    snap_tb = await _domain_tb_summary(db_session, f"TB('{_REV}','AJE调整')")
    live_tb = await _domain_tb_summary(db_session, f"ADJ('{_REV}','aje_net')")
    assert snap_tb == live_tb, (
        f"试算平衡表域的 AJE调整 应来自 adj_lookup 的**归一净额**"
        f"（Phase 0 B3/B4 修复），实得 TB={snap_tb} vs ADJ={live_tb} —— "
        f"不等说明 adj_lookup 取了原始借贷（B4 缺陷形态）"
    )
    assert snap_tb != Decimal("0"), (
        "分母为 0 ⇒ 上一条退化成「两个 0 相等」的空转"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [_AR, _REV])
async def test_p5_workpaper_origin_excluded_in_all_three_domains(db_session, code):
    """🔴 `origin='workpaper'` 的 approved 分录必须被三域一致排除。

    fixture 落了两笔 approved：`manual` 10000 + `workpaper` 7000。
    三域都应只算 manual 那笔 ⇒ 值恰为 `_CR_AMT`，不是 17000。

    加这条是变异检验抓出来的：首版 fixture 只有 manual 一笔，"去掉 origin
    过滤"的变异**不打红**（分母为空）。现在漏过滤的域会多算 7000。
    """
    v = await _domain_adjudication(db_session, f"ADJ('{code}','aje_net')")
    assert v == _CR_AMT, (
        f"审定表域 {code} 得 {v}，期望 {_CR_AMT} —— "
        f"若为 {_CR_AMT + _WP_AMT} 说明 workpaper 来源未被排除（V124 双计）"
    )
    v_report = await _domain_report(db_session, f"ADJ('{code}','aje_net')")
    v_tb = await _domain_tb_summary(db_session, f"ADJ('{code}','aje_net')")
    assert v_report == v_tb == _CR_AMT, (
        f"origin 过滤在三域不一致：审定表={v} 报表={v_report} 试算表={v_tb}"
    )


@pytest.mark.asyncio
async def test_p5_draft_excluded_in_all_three_domains(db_session):
    """口径一致性的另一面：把分录改成 draft 后三域必须**同时**归零。

    只验"有数据时等值"不够 —— 若某个域漏了 `review_status` 过滤，
    它在 draft 场景会给出非零值而其余两域为 0。
    """
    import sqlalchemy as sa

    from app.models.audit_platform_models import Adjustment

    await db_session.execute(
        sa.update(Adjustment)
        .where(Adjustment.project_id == _PID)
        .values(review_status="draft")
    )
    await db_session.flush()

    formula = f"ADJ('{_AR}','aje_net')"
    v_adjud = await _domain_adjudication(db_session, formula)
    v_report = await _domain_report(db_session, formula)
    v_tb = await _domain_tb_summary(db_session, formula)

    assert v_adjud == v_report == v_tb == Decimal("0"), (
        f"draft 分录未被三域一致排除：审定表={v_adjud} 报表={v_report} 试算表={v_tb}"
    )
