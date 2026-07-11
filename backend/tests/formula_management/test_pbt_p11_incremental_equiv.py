# Feature: formula-management-library, Property 11: 增量重算等价于全量重算且非受影响行不变
"""属性测试 P11：增量重算等价于全量重算且非受影响报表行保持不变（Task 8.3）。

**Property 11: 增量重算等价于全量重算且非受影响行不变**

*对任意*变更科目集，``ReportEngine.regenerate_affected`` 产出的报表结果与全量
``generate_all_reports`` 一致（含经 ``ROW()`` 传递的受影响闭包），且未引用变更审定数
的报表行值保持不变（Req 15.1 / 15.2 / 15.4）。

被测（model-based 等价对比）:
    ``app.services.report_engine.ReportEngine``
    - ``generate_all_reports`` —— 参照模型（全量重算，逐行从审定数重新求值）；
    - ``regenerate_affected(changed_accounts=...)`` —— 被测增量路径（仅重算直接引用
      变更审定数的行 + 经 ``ROW()`` 传递闭包连带受影响的行）。

方法学（model-based）:
    1. 在内存 sqlite 中种子最小 ``report_config`` + ``trial_balance``（含多级 ``ROW()``
       闭包 BS-002→BS-010→BS-021 与相互独立的分支，使"未受影响行"可观测）；
    2. 全量生成一次得到**基线** S0（写库并快照各行值）；
    3. 随机挑选一个变更科目子集并改写其 ``audited_amount``；
    4. 增量路径：``regenerate_affected(changed_accounts)`` → 快照增量结果 R_inc；
    5. 全量路径（参照模型）：``generate_all_reports`` 在同库重算 → 快照 R_full；
    6. 断言：
       - **等价性**：对每个报表行 ``R_inc[row] == R_full[row]``（含 ROW() 闭包）；
       - **非受影响行不变**：凡全量重算后与基线相等的行（即未引用变更审定数的行），
         其增量结果亦与基线相等（Req 15.2）。

隔离策略:
    每个 Hypothesis 样例在**独立**的内存 sqlite 引擎中建表 + 种子 + 运行场景，
    并在同一事件循环内创建/释放引擎，避免样例间状态泄漏与事件循环绑定问题。

Framework: hypothesis（遵循 conftest fast profile，max_examples 可经
HYPOTHESIS_MAX_EXAMPLES / HYPOTHESIS_PROFILE 覆盖，属性覆盖不减）。

**Validates: Requirements 15.1, 15.2, 15.4**
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import sqlalchemy as sa
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.report_models import (
    FinancialReport,
    FinancialReportType,
    ReportConfig,
)
from app.services.report_engine import ReportEngine

# sqlite 无原生 JSONB —— 复用现有测试口径把 JSONB 映射为 JSON。
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_TEST_STANDARD = "enterprise"
_YEAR = 2025


# ─────────────────────────────────────────────────────────────────────────────
# 最小种子：叶子科目（TB 取数源）+ 报表配置（含多级 ROW() 闭包与独立分支）。
# ─────────────────────────────────────────────────────────────────────────────
# (code, name, category, opening) —— audited 初值在种子时随机/固定给定。
_TB_ACCOUNTS: list[tuple[str, str, AccountCategory, Decimal]] = [
    # 资产（期末余额口径）
    ("1001", "库存现金", AccountCategory.asset, Decimal("0")),
    ("1002", "银行存款", AccountCategory.asset, Decimal("0")),
    ("1012", "其他货币资金", AccountCategory.asset, Decimal("0")),
    ("1101", "交易性金融资产", AccountCategory.asset, Decimal("0")),
    ("1122", "应收账款", AccountCategory.asset, Decimal("0")),
    ("1401", "存货", AccountCategory.asset, Decimal("0")),
    ("1601", "固定资产原值", AccountCategory.asset, Decimal("0")),
    ("1602", "累计折旧", AccountCategory.asset, Decimal("0")),
    # 负债
    ("2001", "短期借款", AccountCategory.liability, Decimal("0")),
    ("2202", "应付账款", AccountCategory.liability, Decimal("0")),
    # 权益
    ("4001", "实收资本", AccountCategory.equity, Decimal("0")),
    ("4104", "未分配利润", AccountCategory.equity, Decimal("0")),
    # 损益（本期发生额 = audited - opening，opening=0）
    ("6001", "主营业务收入", AccountCategory.revenue, Decimal("0")),
    ("6401", "主营业务成本", AccountCategory.expense, Decimal("0")),
    ("6801", "所得税费用", AccountCategory.expense, Decimal("0")),
]

_LEAF_CODES = [c[0] for c in _TB_ACCOUNTS]

# (row_code, row_number, name, indent, is_total, formula)
_BS_CONFIGS: list[tuple[str, int, str, int, bool, str]] = [
    ("BS-002", 2, "货币资金", 1, False,
     "TB('1001','期末余额') + TB('1002','期末余额') + TB('1012','期末余额')"),
    ("BS-003", 3, "交易性金融资产", 1, False, "TB('1101','期末余额')"),
    ("BS-005", 5, "应收账款", 1, False, "TB('1122','期末余额')"),
    ("BS-008", 8, "存货", 1, False, "TB('1401','期末余额')"),
    # 多级 ROW() 闭包：BS-010 汇总流动资产
    ("BS-010", 10, "流动资产合计", 0, True,
     "ROW('BS-002') + ROW('BS-003') + ROW('BS-005') + ROW('BS-008')"),
    ("BS-014", 14, "固定资产", 1, False,
     "TB('1601','期末余额') - TB('1602','期末余额')"),
    ("BS-020", 20, "非流动资产合计", 0, True, "ROW('BS-014')"),
    # 二级闭包：BS-021 引用 BS-010 / BS-020
    ("BS-021", 21, "资产总计", 0, True, "ROW('BS-010') + ROW('BS-020')"),
    # 相互独立的负债/权益分支（用于验证"非受影响行不变"）
    ("BS-031", 31, "短期借款", 1, False, "TB('2001','期末余额')"),
    ("BS-033", 33, "应付账款", 1, False, "TB('2202','期末余额')"),
    ("BS-039", 39, "流动负债合计", 0, True, "ROW('BS-031') + ROW('BS-033')"),
    ("BS-051", 51, "实收资本", 1, False, "TB('4001','期末余额')"),
    ("BS-055", 55, "未分配利润", 1, False, "TB('4104','期末余额')"),
    ("BS-056", 56, "所有者权益合计", 0, True, "ROW('BS-051') + ROW('BS-055')"),
    ("BS-057", 57, "负债和所有者权益总计", 0, True, "ROW('BS-039') + ROW('BS-056')"),
]

_IS_CONFIGS: list[tuple[str, int, str, int, bool, str]] = [
    # SUM_TB 范围闭包：改 6001 需经范围命中被识别为受影响
    ("IS-001", 1, "营业收入", 0, False, "SUM_TB('6001~6099','本期发生额')"),
    ("IS-002", 2, "营业成本", 0, False, "TB('6401','本期发生额')"),
    ("IS-010", 10, "营业利润", 0, True, "ROW('IS-001') - ROW('IS-002')"),
    ("IS-016", 16, "所得税费用", 0, False, "TB('6801','本期发生额')"),
    ("IS-019", 19, "净利润", 0, True, "ROW('IS-010') - ROW('IS-016')"),
]


async def _seed(session: AsyncSession, project_id: uuid.UUID, amounts: dict[str, Decimal]) -> None:
    """种子项目 + 试算表 + 报表配置。``amounts`` 给定各叶子科目的初始 audited 值。"""
    session.add(Project(
        id=project_id,
        name="P11_报表增量等价_2025",
        client_name="P11",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=uuid.uuid4(),
    ))
    await session.flush()

    for code, name, cat, opening in _TB_ACCOUNTS:
        audited = amounts[code]
        session.add(TrialBalance(
            project_id=project_id,
            year=_YEAR,
            company_code="001",
            standard_account_code=code,
            account_name=name,
            account_category=cat,
            unadjusted_amount=audited,
            audited_amount=audited,
            opening_balance=opening,
        ))

    for row_code, row_num, name, indent, is_total, formula in _BS_CONFIGS:
        session.add(ReportConfig(
            report_type=FinancialReportType.balance_sheet,
            row_number=row_num,
            row_code=row_code,
            row_name=name,
            indent_level=indent,
            is_total_row=is_total,
            formula=formula,
            applicable_standard=_TEST_STANDARD,
        ))
    for row_code, row_num, name, indent, is_total, formula in _IS_CONFIGS:
        session.add(ReportConfig(
            report_type=FinancialReportType.income_statement,
            row_number=row_num,
            row_code=row_code,
            row_name=name,
            indent_level=indent,
            is_total_row=is_total,
            formula=formula,
            applicable_standard=_TEST_STANDARD,
        ))
    await session.flush()
    await session.commit()


async def _snapshot_rows(session: AsyncSession, project_id: uuid.UUID) -> dict[tuple[str, str], Decimal]:
    """读取全部报表行值 → {(report_type, row_code): current_period_amount}。"""
    result = await session.execute(
        sa.select(FinancialReport).where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == _YEAR,
            FinancialReport.is_deleted == sa.false(),
        )
    )
    snap: dict[tuple[str, str], Decimal] = {}
    for row in result.scalars().all():
        rt = row.report_type.value if hasattr(row.report_type, "value") else str(row.report_type)
        amt = row.current_period_amount
        snap[(rt, row.row_code)] = Decimal(amt) if amt is not None else Decimal("0")
    return snap


async def _run_scenario(
    initial_amounts: dict[str, Decimal],
    changes: dict[str, Decimal],
) -> tuple[dict, dict, dict]:
    """在独立内存 sqlite 中运行 model-based 场景，返回 (baseline, incremental, full)。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        project_id = uuid.uuid4()

        async with session_factory() as session:
            await _seed(session, project_id, initial_amounts)

            report_engine = ReportEngine(session)

            # ① 基线全量生成 S0
            await report_engine.generate_all_reports(project_id, _YEAR, applicable_standard=_TEST_STANDARD)
            await session.commit()
            baseline = await _snapshot_rows(session, project_id)

            # ② 应用变更（改写 audited_amount）
            for code, new_amt in changes.items():
                res = await session.execute(
                    sa.select(TrialBalance).where(
                        TrialBalance.project_id == project_id,
                        TrialBalance.year == _YEAR,
                        TrialBalance.standard_account_code == code,
                    )
                )
                tb_row = res.scalar_one()
                tb_row.audited_amount = new_amt
            await session.flush()

            # ③ 增量重算（被测路径）
            await report_engine.regenerate_affected(
                project_id, _YEAR,
                changed_accounts=list(changes.keys()),
                applicable_standard=_TEST_STANDARD,
            )
            await session.commit()
            incremental = await _snapshot_rows(session, project_id)

            # ④ 全量重算（参照模型）
            await report_engine.generate_all_reports(project_id, _YEAR, applicable_standard=_TEST_STANDARD)
            await session.commit()
            full = await _snapshot_rows(session, project_id)

        return baseline, incremental, full
    finally:
        await engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# 智能生成器：各叶子科目初始金额 + 变更子集（非空、去重、真实改写）。
# ─────────────────────────────────────────────────────────────────────────────
_AMOUNT = st.integers(min_value=0, max_value=5_000_000).map(lambda v: Decimal(v))


@st.composite
def _scenario(draw):
    initial = {code: draw(_AMOUNT) for code in _LEAF_CODES}
    changed_codes = draw(
        st.lists(st.sampled_from(_LEAF_CODES), min_size=1, max_size=5, unique=True)
    )
    changes = {code: draw(_AMOUNT) for code in changed_codes}
    return initial, changes


@given(case=_scenario())
def test_p11_incremental_equals_full_and_unaffected_unchanged(case):
    """P11：增量重算 == 全量重算（含 ROW() 闭包）且非受影响行值不变。

    **Validates: Requirements 15.1, 15.2, 15.4**
    """
    initial_amounts, changes = case
    baseline, incremental, full = asyncio.run(_run_scenario(initial_amounts, changes))

    # 三份快照覆盖的报表行集合一致（生成/重算不新增或丢行）。
    assert set(incremental.keys()) == set(full.keys()) == set(baseline.keys()), (
        "增量 / 全量 / 基线快照的报表行集合应一致"
    )

    # ── 等价性（Req 15.1）：增量结果逐行等于全量重算结果（含 ROW() 传递闭包）──
    for key in full:
        assert incremental[key] == full[key], (
            f"增量重算与全量重算不一致 @ {key}："
            f"增量={incremental[key]} 全量={full[key]}；changes={changes}"
        )

    # ── 非受影响行不变（Req 15.2）：全量重算后与基线相等的行（未引用变更审定数），
    #    其增量结果亦与基线相等，未被增量路径改动 ──
    for key in full:
        if full[key] == baseline[key]:
            assert incremental[key] == baseline[key], (
                f"未受影响报表行在增量重算后被改动 @ {key}："
                f"基线={baseline[key]} 增量={incremental[key]}；changes={changes}"
            )
