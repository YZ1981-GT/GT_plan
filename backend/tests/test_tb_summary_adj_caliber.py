"""试算平衡表调整列口径守卫 — P2 等价性 + B1~B4 四缺陷防回归.

spec: tb-adjustment-column-formula-closure · Phase 0 Task 0.9

## 守卫内容

- **P2** `get_summary_with_adjustments` 的调整列 **== `adj_net_batch` 同参数值**。
  🔴 **调同一函数比对**，不是各写一遍聚合再比 —— 后者只能证明"两套算法碰巧相等"，
  一旦两套同时错（改造前正是如此）就双双通过。
- **B1** draft 分录不得出现在试算平衡表调整列
- **B2** `origin='workpaper'` 不得计入（V124 防双计）
- **B3** 只往主表遗留冗余列塞数据时，调整列必须为 0（证明已不读那些列）
- **B4** 审定数用归一净额 ⇒ 贷方类科目方向正确
- 两条路径（`report_config` 主路径 / `_get_summary_from_mapping` fallback）**口径一致**

真 SQLite + 真 ORM 行 + 真 service，不 mock。

Validates: Requirements 1.1, 1.2, 1.3, 1.4 · Properties P2, P3, P4
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

_PID = uuid.UUID("bbbbbbbb-0000-4000-8000-00000000d201")
_UID = uuid.UUID("cccccccc-0000-4000-8000-00000000d202")
_YEAR = 2099
_CO = "001"
_STANDARD = "soe_standalone"          # = f"{template_type}_{report_scope}" 默认值
_REPORT_TYPE = "income_statement"

# 收入类（贷方正常）—— B4 的关键样本，截图缺陷现场就是这个类别
_REV = "6001"
_REV_NAME = "主营业务收入"
_REV_LINE = "IS-001"
_REV_LINE_NAME = "营业收入"
# 费用类（借方正常）—— 对照样本
_EXP = "6601"
_EXP_NAME = "销售费用"
_EXP_LINE = "IS-004"
_EXP_LINE_NAME = "销售费用"

_TB_STATUSES = frozenset({"approved"})
_TB_ORIGINS = frozenset({"workpaper"})


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        await _seed_base(s)
        yield s
    await engine.dispose()


async def _seed_base(db: AsyncSession) -> None:
    """User + Project + report_config + report_line_mapping + trial_balance。"""
    from app.models.audit_platform_models import (
        AccountCategory,
        ReportLineMapping,
        ReportLineMappingType,
        TrialBalance,
    )
    from app.models.core import Project, User
    from app.models.report_models import ReportConfig

    db.add(User(id=_UID, username="test_tbsum", email="tbsum@test.local",
                hashed_password="x", role="admin"))
    # ProjectStatus 合法值：created/planning/execution/completion/reporting/archived
    # （无 "active"——按命名习惯猜会打红）
    db.add(Project(id=_PID, name="tbsum_test", client_name="测试客户",
                   status="execution", created_by=_UID))

    # report_config：两行，均带公式（走主路径的「有公式」分支）
    #
    # 🔴 公式用 `未审数` 而非真库 IS-001 实际用的 `本期发生额` —— 因为后者在
    # 这条路径上**恒 0**（见文件末 test_b7_* 的 xfail 守卫）。本文件要守的是
    # 调整列口径，故取一个能取到未审数的列名，避免被 B7 掩盖。
    for i, (code, name, acct) in enumerate([
        (_REV_LINE, _REV_LINE_NAME, _REV),
        (_EXP_LINE, _EXP_LINE_NAME, _EXP),
    ], start=1):
        db.add(ReportConfig(
            id=uuid.uuid4(), report_type=_REPORT_TYPE, row_number=i,
            row_code=code, row_name=name, indent_level=1,
            formula=f"TB('{acct}','未审数')",
            applicable_standard=_STANDARD, is_total_row=False, is_deleted=False,
        ))

    # report_line_mapping：科目 → 行次（供 all_account_codes / line_accounts）
    for acct, line_code, line_name in [
        (_REV, _REV_LINE, _REV_LINE_NAME),
        (_EXP, _EXP_LINE, _EXP_LINE_NAME),
    ]:
        db.add(ReportLineMapping(
            id=uuid.uuid4(), project_id=_PID, report_type=_REPORT_TYPE,
            standard_account_code=acct, report_line_code=line_code,
            report_line_name=line_name, report_line_level=2,
            mapping_sign="add",
            # mapping_type 是 NOT NULL 枚举（ai_suggested / manual / reference_copied）
            mapping_type=ReportLineMappingType.manual,
            is_confirmed=True, is_deleted=False,
        ))

    # trial_balance：未审数（v2 自然正数）
    for acct, name, cat, unadj in [
        (_REV, _REV_NAME, AccountCategory.revenue, Decimal("100000")),
        (_EXP, _EXP_NAME, AccountCategory.expense, Decimal("20000")),
    ]:
        db.add(TrialBalance(
            id=uuid.uuid4(), project_id=_PID, year=_YEAR, company_code=_CO,
            standard_account_code=acct, account_name=name, account_category=cat,
            unadjusted_amount=unadj, aje_adjustment=Decimal("0"),
            rje_adjustment=Decimal("0"), audited_amount=unadj,
            opening_balance=Decimal("0"), is_deleted=False,
        ))
    await db.flush()


async def _seed_adj(
    db: AsyncSession, *, code: str, name: str, debit, credit,
    adj_type: str = "aje", review_status: str = "approved", origin: str = "manual",
    main_table_only: bool = False,
) -> None:
    """插入调整分录。

    main_table_only=True 时**只**写主表遗留冗余列、不建明细行 —— 用于 B3 守卫：
    证明收敛后已不再读那些列。
    """
    from app.models.audit_platform_models import Adjustment, AdjustmentEntry, AdjustmentType

    adj_id, grp = uuid.uuid4(), uuid.uuid4()
    db.add(Adjustment(
        id=adj_id, project_id=_PID, year=_YEAR, company_code=_CO,
        adjustment_no=f"ADJ-{adj_id.hex[:8]}", adjustment_type=AdjustmentType(adj_type),
        account_code=code, account_name=name,
        debit_amount=Decimal(str(debit)), credit_amount=Decimal(str(credit)),
        entry_group_id=grp, review_status=review_status, origin=origin,
        is_deleted=False, created_by=_UID,
    ))
    if not main_table_only:
        db.add(AdjustmentEntry(
            id=uuid.uuid4(), adjustment_id=adj_id, entry_group_id=grp, line_no=1,
            standard_account_code=code, account_name=name,
            debit_amount=Decimal(str(debit)), credit_amount=Decimal(str(credit)),
            is_deleted=False,
        ))
    await db.flush()


async def _summary(db: AsyncSession) -> dict[str, dict]:
    from app.services.trial_balance_service import TrialBalanceService

    rows = await TrialBalanceService(db).get_summary_with_adjustments(
        _PID, _YEAR, _REPORT_TYPE, _CO
    )
    return {r["row_code"]: r for r in rows}


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


# ───────────────────────────────────────────────────────────────────────────
# P2 — 与 adj_net_batch 调同一函数比对
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p2_summary_matches_adj_net_batch(db_session: AsyncSession):
    """🔴 P2：试算平衡表调整列 == `adj_net_batch` 同参数返回值。

    **调同一函数**取参照值，而非在测试里另写一遍聚合 —— 后者无法发现
    「生产代码与测试代码同时错」这类改造前的真实情形。
    """
    from app.services.adjustment_amount_source import adj_net_batch

    await _seed_adj(db_session, code=_REV, name=_REV_NAME, debit=0, credit=10000)
    await _seed_adj(db_session, code=_EXP, name=_EXP_NAME, debit=3000, credit=0)
    await _seed_adj(db_session, code=_EXP, name=_EXP_NAME, debit=0, credit=500,
                    adj_type="rje")

    summary = await _summary(db_session)
    reference = await adj_net_batch(
        db_session, project_id=_PID, year=_YEAR,
        account_codes=[_REV, _EXP],
        include_statuses=_TB_STATUSES, exclude_origins=_TB_ORIGINS,
    )

    for acct, line in [(_REV, _REV_LINE), (_EXP, _EXP_LINE)]:
        ref = reference.get(acct, {})
        row = summary[line]
        assert _d(row["aje_dr"]) == ref.get("aje_dr", Decimal("0")), f"{line} aje_dr"
        assert _d(row["aje_cr"]) == ref.get("aje_cr", Decimal("0")), f"{line} aje_cr"
        assert _d(row["rcl_dr"]) == ref.get("rje_dr", Decimal("0")), f"{line} rcl_dr"
        assert _d(row["rcl_cr"]) == ref.get("rje_cr", Decimal("0")), f"{line} rcl_cr"


@pytest.mark.asyncio
async def test_p2_audited_equals_unadj_plus_net(db_session: AsyncSession):
    """P2 延伸：审定数 == 未审数 + `adj_net_batch` 的归一净额（B4 口径）。"""
    from app.services.adjustment_amount_source import adj_net_batch

    await _seed_adj(db_session, code=_REV, name=_REV_NAME, debit=0, credit=10000)
    await _seed_adj(db_session, code=_EXP, name=_EXP_NAME, debit=3000, credit=0)

    summary = await _summary(db_session)
    reference = await adj_net_batch(
        db_session, project_id=_PID, year=_YEAR, account_codes=[_REV, _EXP],
        include_statuses=_TB_STATUSES, exclude_origins=_TB_ORIGINS,
    )

    for acct, line in [(_REV, _REV_LINE), (_EXP, _EXP_LINE)]:
        ref = reference.get(acct, {})
        row = summary[line]
        expected = (
            _d(row["unadjusted"])
            + ref.get("aje_net", Decimal("0"))
            + ref.get("rje_net", Decimal("0"))
        )
        assert _d(row["audited"]) == expected, (
            f"{line}: audited={row['audited']} ≠ unadj+net={expected}"
        )


# ───────────────────────────────────────────────────────────────────────────
# B4 — 贷方类审定数方向（本 spec 最关键的修正）
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_b4_revenue_credit_increases_audited(db_session: AsyncSession):
    """🔴 B4：收入类贷记 ⇒ 审定数**增大**（改造前会减小）。

    改造前：`audited = 100000 + 0 - 10000 = 90000`（收入被调减，方向错）
    改造后：`audited = 100000 + 10000 = 110000`（收入增加，正确）
    """
    await _seed_adj(db_session, code=_REV, name=_REV_NAME, debit=0, credit=10000)

    row = (await _summary(db_session))[_REV_LINE]

    assert _d(row["unadjusted"]) == Decimal("100000")
    assert _d(row["aje_cr"]) == Decimal("10000"), "展示列保留原始贷方金额"
    assert _d(row["audited"]) == Decimal("110000"), (
        f"收入贷记 10000 应使审定数由 100000 增至 110000，实得 {row['audited']}"
        "（若为 90000 ⇒ B4 未修，用了未归一的 dr-cr）"
    )


@pytest.mark.asyncio
async def test_b4_expense_debit_increases_audited(db_session: AsyncSession):
    """借方类（费用）借记 ⇒ 审定数增大（此方向改造前后一致，作对照）。"""
    await _seed_adj(db_session, code=_EXP, name=_EXP_NAME, debit=3000, credit=0)

    row = (await _summary(db_session))[_EXP_LINE]
    assert _d(row["unadjusted"]) == Decimal("20000")
    assert _d(row["aje_dr"]) == Decimal("3000")
    assert _d(row["audited"]) == Decimal("23000")


# ───────────────────────────────────────────────────────────────────────────
# B1 / B2 / B3 — 三个过滤的防回归
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_b1_draft_excluded_from_summary(db_session: AsyncSession):
    """B1：draft 分录不得出现在试算平衡表调整列。"""
    await _seed_adj(db_session, code=_REV, name=_REV_NAME, debit=0, credit=9999,
                    review_status="draft")

    row = (await _summary(db_session))[_REV_LINE]
    assert row["aje_cr"] is None, f"draft 不应计入，实得 aje_cr={row['aje_cr']}"
    assert _d(row["audited"]) == Decimal("100000"), "审定数应等于未审数（无 approved 调整）"


@pytest.mark.asyncio
async def test_b1_mutation_approved_appears(db_session: AsyncSession):
    """**双向变异**：同一条改 approved 后必须出现（防"恒空也通过"）。"""
    await _seed_adj(db_session, code=_REV, name=_REV_NAME, debit=0, credit=9999,
                    review_status="approved")

    row = (await _summary(db_session))[_REV_LINE]
    assert _d(row["aje_cr"]) == Decimal("9999")
    assert _d(row["audited"]) == Decimal("109999")


@pytest.mark.asyncio
async def test_b2_workpaper_origin_excluded_from_summary(db_session: AsyncSession):
    """B2：workpaper 来源不得计入（已由审定表 writeback 体现，防 V124 双计）。"""
    await _seed_adj(db_session, code=_REV, name=_REV_NAME, debit=0, credit=7777,
                    origin="workpaper")

    row = (await _summary(db_session))[_REV_LINE]
    assert row["aje_cr"] is None, f"workpaper 来源应排除，实得 {row['aje_cr']}"
    assert _d(row["audited"]) == Decimal("100000")


@pytest.mark.asyncio
async def test_b2_mutation_manual_origin_appears(db_session: AsyncSession):
    """**双向变异**：同一条改 manual 后必须出现。"""
    await _seed_adj(db_session, code=_REV, name=_REV_NAME, debit=0, credit=7777,
                    origin="manual")

    row = (await _summary(db_session))[_REV_LINE]
    assert _d(row["aje_cr"]) == Decimal("7777")


@pytest.mark.asyncio
async def test_b3_main_table_legacy_columns_not_read(db_session: AsyncSession):
    """🔴 B3：只写主表遗留冗余列（不建明细行）时，调整列必须为 0。

    这是「已不读 `adjustments.account_code/debit_amount/credit_amount`」的
    可执行证明 —— 改造前此测试会看到 8888。
    """
    await _seed_adj(db_session, code=_REV, name=_REV_NAME, debit=0, credit=8888,
                    main_table_only=True)

    row = (await _summary(db_session))[_REV_LINE]
    assert row["aje_cr"] is None, (
        f"主表遗留列不应再被读取，实得 aje_cr={row['aje_cr']}"
        "（非 None ⇒ B3 未修，仍在查废弃列）"
    )
    assert _d(row["audited"]) == Decimal("100000")


@pytest.mark.asyncio
async def test_b3_mutation_entry_row_appears(db_session: AsyncSession):
    """**双向变异**：补上明细行后必须出现（证明读的是明细表）。"""
    await _seed_adj(db_session, code=_REV, name=_REV_NAME, debit=0, credit=8888,
                    main_table_only=False)

    row = (await _summary(db_session))[_REV_LINE]
    assert _d(row["aje_cr"]) == Decimal("8888")


@pytest.mark.asyncio
async def test_soft_deleted_excluded_from_summary(db_session: AsyncSession):
    """软删除分录不得计入（真库 34 条全是此状态）。"""
    from app.models.audit_platform_models import Adjustment, AdjustmentEntry, AdjustmentType

    adj_id, grp = uuid.uuid4(), uuid.uuid4()
    db_session.add(Adjustment(
        id=adj_id, project_id=_PID, year=_YEAR, company_code=_CO,
        adjustment_no="ADJ-DEL", adjustment_type=AdjustmentType("aje"),
        account_code=_REV, account_name=_REV_NAME, entry_group_id=grp,
        review_status="approved", origin="manual", is_deleted=True, created_by=_UID,
    ))
    db_session.add(AdjustmentEntry(
        id=uuid.uuid4(), adjustment_id=adj_id, entry_group_id=grp, line_no=1,
        standard_account_code=_REV, account_name=_REV_NAME,
        debit_amount=Decimal("0"), credit_amount=Decimal("6666"), is_deleted=False,
    ))
    await db_session.flush()

    row = (await _summary(db_session))[_REV_LINE]
    assert row["aje_cr"] is None


# ───────────────────────────────────────────────────────────────────────────
# 两条路径口径一致（0.8 的守卫）
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fallback_path_same_caliber(db_session: AsyncSession):
    """🔴 `_get_summary_from_mapping` fallback 路径口径必须与主路径一致。

    只修主路径会留下「report_config 有配置时数对、无配置降级后数错」的隐蔽不一致。
    本测试删掉 report_config 触发降级，断言四个缺陷在降级路径同样已修。
    """
    import sqlalchemy as sa

    from app.models.report_models import ReportConfig

    # draft + workpaper + 主表遗留列 三种都不该计入；只有 approved+manual+明细行 该计入
    await _seed_adj(db_session, code=_REV, name=_REV_NAME, debit=0, credit=10000)
    await _seed_adj(db_session, code=_REV, name=_REV_NAME, debit=0, credit=999,
                    review_status="draft")
    await _seed_adj(db_session, code=_REV, name=_REV_NAME, debit=0, credit=888,
                    origin="workpaper")
    await _seed_adj(db_session, code=_REV, name=_REV_NAME, debit=0, credit=777,
                    main_table_only=True)

    # 触发 fallback：清空 report_config
    await db_session.execute(sa.delete(ReportConfig))
    await db_session.flush()

    summary = await _summary(db_session)
    # fallback 路径的 row_code 来自 report_line_mapping.report_line_code
    row = summary[_REV_LINE]

    assert _d(row["aje_cr"]) == Decimal("10000"), (
        f"fallback 路径应只计 approved+manual+明细行的 10000，实得 {row['aje_cr']}"
    )
    assert _d(row["audited"]) == Decimal("110000"), (
        f"fallback 路径审定数应用归一净额，实得 {row['audited']}"
    )


@pytest.mark.asyncio
async def test_summary_paths_preserve_workpaper_adjustment(db_session: AsyncSession):
    """主路径和 fallback 路径都把底稿发布分量带入审定数。"""
    from app.models.audit_platform_models import TrialBalance

    for code, amount in ((_REV, Decimal("1200")), (_EXP, Decimal("-300"))):
        row = (await db_session.execute(
            __import__("sqlalchemy").select(TrialBalance).where(
                TrialBalance.standard_account_code == code
            )
        )).scalar_one()
        row.wp_adjustment = amount
        row.audited_amount = row.unadjusted_amount + amount
    await db_session.flush()

    main = (await _summary(db_session))
    assert _d(main[_REV_LINE]["wp_adjustment"]) == Decimal("1200")
    assert _d(main[_REV_LINE]["audited"]) == Decimal("101200")
    assert _d(main[_EXP_LINE]["wp_adjustment"]) == Decimal("-300")
    assert _d(main[_EXP_LINE]["audited"]) == Decimal("19700")

    import sqlalchemy as sa
    from app.models.report_models import ReportConfig

    await db_session.execute(sa.delete(ReportConfig))
    await db_session.flush()
    fallback = await _summary(db_session)
    assert _d(fallback[_REV_LINE]["wp_adjustment"]) == Decimal("1200")
    assert _d(fallback[_REV_LINE]["audited"]) == Decimal("101200")
    assert _d(fallback[_EXP_LINE]["wp_adjustment"]) == Decimal("-300")
    assert _d(fallback[_EXP_LINE]["audited"]) == Decimal("19700")


# ───────────────────────────────────────────────────────────────────────────
# 🔴 B7 — 相邻缺陷：公式路径只支持 3 个列名，其余 11 个恒 0
#
# 本 Phase 的范围是**调整列**口径，B7 属**未审数列**取数，不在范围内。
# 但它与本 Phase 改动同处一条代码路径且影响面更大（整张利润表未审数全空），
# 故用 xfail(strict=True) 钉住：
#   - 现在必红（缺陷存在）
#   - 一旦有人修好，strict=True 会让它 **XPASS 变成失败**，强制回来删标记
# 这样缺陷不会被遗忘，也不会伪装成"已修"。
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_b7_period_amount_column_should_resolve(db_session: AsyncSession):
    """B7 已修：真库利润表公式用的 `本期发生额` 能取到值。

    修复前：`execute_formula(f, tb_map, row_values)` → `from_simple_map` 只产 3 键
    ⇒ `本期发生额` 落入 `_resolve_tb_column` 的「已注册但该科目无数据」态 ⇒ 恒 0
    （只留 trace 不报错，故界面空白而零告警）。真库 income_statement 78 行未审数全空。

    修复后：L2 显式预载 `本期发生额 = unadjusted − opening`（与 `report_engine`
    的 `_period_amount` 未审模式同口径），并经共享件补 `本期借方`/`本期贷方`。
    """
    import sqlalchemy as sa

    from app.models.report_models import ReportConfig

    # 把公式改成真库实际形态
    await db_session.execute(
        sa.update(ReportConfig)
        .where(ReportConfig.row_code == _REV_LINE)
        .values(formula=f"SUM_TB('{_REV}~6099','本期发生额')")
    )
    await db_session.flush()

    row = (await _summary(db_session))[_REV_LINE]
    assert _d(row["unadjusted"]) == Decimal("100000"), (
        f"`本期发生额` 应解析到未审数，实得 {row['unadjusted']}"
    )


@pytest.mark.asyncio
async def test_b7_all_registered_columns_are_resolvable(db_session: AsyncSession):
    """🔴 B7 防回归：`COLUMN_ALIASES` 的**每一个**注册列名在本路径都不得「无数据」。

    判据不是「值非 0」——`本期借方` 这类列在无 `tb_balance` 数据时 0 是**诚实的 0**
    （`aggregate_occurrence` 有意不产零值键）。真正的缺陷形态是
    `_resolve_tb_column` 记下「该科目列无数据（缺「X」）」这条 trace，
    即**规范名根本不在 tb_data 里**。故按 trace 判，不按值判。

    🔴 **必须探测生产代码真实预载的 tb_data**，不能在测试里自建一份 ——
    自建版本无论生产代码怎么退化都会通过（首版即此错，变异注入时没打红）。
    故用 monkeypatch 截获 `FormulaContext.__init__` 收到的 tb_data。
    """
    from app.services import trial_balance_service as tbs_mod
    from app.services.formula_engine import COLUMN_ALIASES, FormulaContext

    captured: list[dict] = []
    orig_init = FormulaContext.__init__

    def _spy(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        if self.tb_data:
            captured.append(self.tb_data)

    # 只在本测试内替换，退出即还原
    FormulaContext.__init__ = _spy  # type: ignore[method-assign]
    try:
        await tbs_mod.TrialBalanceService(db_session).get_summary_with_adjustments(
            _PID, _YEAR, _REPORT_TYPE, _CO
        )
    finally:
        FormulaContext.__init__ = orig_init  # type: ignore[method-assign]

    assert captured, "未截获到任何非空 tb_data —— 生产代码可能已不走 FormulaContext"

    tb_data = captured[-1]
    account_data = tb_data.get(_REV)
    assert account_data is not None, f"科目 {_REV} 未出现在预载 tb_data 中"

    # 每个注册列名的**规范名**都必须在 account_data 里
    missing = sorted({
        col for col in COLUMN_ALIASES
        if COLUMN_ALIASES[col] not in account_data
    })
    assert not missing, (
        f"以下注册列名在试算平衡表路径仍未预载（B7 复发）：{missing}\n"
        f"COLUMN_ALIASES 共 {len(COLUMN_ALIASES)} 个列名，"
        f"预载键为 {sorted(account_data)}。"
        "每个列名的规范名都必须出现在 L2 预载的 tb_data 里。"
    )


@pytest.mark.asyncio
async def test_b7_period_amount_matches_report_engine_caliber(db_session: AsyncSession):
    """`本期发生额` 口径 = `unadjusted − opening`，与 report_engine 未审模式一致。

    钉住口径本身，防止后续被改成 `audited − opening`（那会让未审数列变审定口径）。
    fixture 里 `_REV` 的 unadjusted=100000 / opening=0 ⇒ 本期发生额应为 100000。
    """
    import sqlalchemy as sa

    from app.models.report_models import ReportConfig

    await db_session.execute(
        sa.update(ReportConfig)
        .where(ReportConfig.row_code == _REV_LINE)
        .values(formula=f"TB('{_REV}','本期发生额')")
    )
    await db_session.flush()

    row = (await _summary(db_session))[_REV_LINE]
    assert _d(row["unadjusted"]) == Decimal("100000"), (
        f"本期发生额应为 unadjusted(100000) − opening(0) = 100000，实得 {row['unadjusted']}"
    )


@pytest.mark.asyncio
async def test_b7_opening_balance_column_resolves(db_session: AsyncSession):
    """`年初余额` / `期初余额`（同义别名）应取到 opening_balance。"""
    import sqlalchemy as sa

    from app.models.audit_platform_models import TrialBalance
    from app.models.report_models import ReportConfig

    await db_session.execute(
        sa.update(TrialBalance)
        .where(TrialBalance.standard_account_code == _REV)
        .values(opening_balance=Decimal("7777"))
    )
    await db_session.execute(
        sa.update(ReportConfig)
        .where(ReportConfig.row_code == _REV_LINE)
        .values(formula=f"TB('{_REV}','年初余额')")
    )
    await db_session.flush()

    row = (await _summary(db_session))[_REV_LINE]
    assert _d(row["unadjusted"]) == Decimal("7777"), (
        f"年初余额应取到 opening_balance=7777，实得 {row['unadjusted']}"
    )

